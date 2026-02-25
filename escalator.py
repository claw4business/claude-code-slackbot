#!/usr/bin/env python3
"""
Slack escalator hook for Claude Code AskUserQuestion.

Behavior:
- PreToolUse (`pre-hook`) intercepts AskUserQuestion calls.
- Posts the question to Slack #claude immediately.
- Spawns a background watcher that polls Slack every 5s and writes answer to a file.
- Always DENIES AskUserQuestion with a reason that instructs Claude to:
  1) Print the question/options as plain text
  2) Run a wait-for-reply command that blocks up to 60s watching for Slack answer
  3) If Slack answer found, use it; otherwise wait for terminal input
  4) Do not call AskUserQuestion again

Modes:
  pre-hook          - PreToolUse handler
  post-hook         - PostToolUse handler (cleanup)
  check-slack-reply - One-shot check for Slack reply
  watch-slack       - Background watcher (polls every 5s, writes answer file)
  wait-for-reply    - Blocks up to N seconds watching for answer file
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------- Config ----------

# Path to .env file containing SLACK_BOT_TOKEN — update to YOUR .env location
ENV_FILE = Path(__file__).resolve().parent / ".env"
VENV_LIB_ROOT = Path(__file__).resolve().parent / "venv" / "lib"
# Use the current interpreter (matches however the hook was invoked)
VENV_PYTHON = sys.executable
TMP_DIR = Path("/tmp")

_SLACK_CHANNEL_ID_DEFAULT = "YOUR_CHANNEL_ID"
SCRIPT_PATH = str(Path(__file__).resolve())

WATCH_INTERVAL = 5       # background watcher polls every 5 seconds
WATCH_TIMEOUT = 900      # watcher gives up after 15 minutes
WAIT_TIMEOUT_DEFAULT = 900  # wait-for-reply blocks up to 15 minutes


# ---------- File paths ----------

def log_file(sid: str) -> Path:
    return TMP_DIR / f"claude-q-{sid}.log"

def meta_file(sid: str) -> Path:
    return TMP_DIR / f"claude-q-{sid}.meta.json"

def answer_file(sid: str) -> Path:
    return TMP_DIR / f"claude-q-{sid}.slack-answer.txt"

def watcher_pid_file(sid: str) -> Path:
    return TMP_DIR / f"claude-q-{sid}.watch.pid"


# ---------- Helpers ----------

def log(msg: str, sid: str | None = None) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, file=sys.stderr, flush=True)
    if sid:
        try:
            with log_file(sid).open("a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            pass


def load_env() -> None:
    if not ENV_FILE.exists():
        return
    for raw_line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


def get_channel_id() -> str:
    load_env()
    return os.environ.get("SLACK_CHANNEL_ID", _SLACK_CHANNEL_ID_DEFAULT)


def get_slack_client():
    load_env()
    for p in VENV_LIB_ROOT.glob("python*/site-packages"):
        p_str = str(p)
        if p_str not in sys.path:
            sys.path.insert(0, p_str)
    from slack_sdk import WebClient
    token = os.environ.get("SLACK_BOT_TOKEN") or os.environ.get("SIMULATOR_SLACK_TOKEN", "")
    return WebClient(token=token)


def safe_json_load(path: Path, default: dict) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def safe_json_dump(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")


# ---------- Formatting ----------

def format_terminal_questions(questions: list[dict]) -> str:
    lines: list[str] = []
    for qi, q in enumerate(questions, start=1):
        q_text = str(q.get("question", "")).strip()
        header = f"Question {qi}: " if len(questions) > 1 else ""
        lines.append(header + q_text)
        options = q.get("options", []) or []
        for oi, opt in enumerate(options, start=1):
            label = str(opt.get("label", "")).strip()
            desc = str(opt.get("description", "")).strip()
            if desc:
                lines.append(f"  {oi}. {label} — {desc}")
            else:
                lines.append(f"  {oi}. {label}")
        lines.append("")
    return "\n".join(lines).strip()


def format_slack_message(questions: list[dict], sid: str) -> str:
    lines: list[str] = [":robot_face: *Claude Code needs your input:*\n"]
    for qi, q in enumerate(questions, start=1):
        q_text = str(q.get("question", "")).strip()
        if len(questions) > 1:
            lines.append(f"*Q{qi}:* {q_text}")
        else:
            lines.append(f"*{q_text}*")
        lines.append("")
        options = q.get("options", []) or []
        for oi, opt in enumerate(options, start=1):
            label = str(opt.get("label", "")).strip()
            desc = str(opt.get("description", "")).strip()
            if desc:
                lines.append(f"  *{oi}.* `{label}` — {desc}")
            else:
                lines.append(f"  *{oi}.* `{label}`")
        lines.append("")
    lines.append("_Reply with the option number (e.g._ `1`_) or type your own answer._")
    return "\n".join(lines)


def parse_slack_reply(reply_text: str, options: list[dict]) -> str:
    text = reply_text.strip()
    if not text:
        return ""
    try:
        idx = int(text)
        if 1 <= idx <= len(options):
            return str(options[idx - 1].get("label", text)).strip() or text
    except ValueError:
        pass
    lowered = text.lower()
    for opt in options:
        label = str(opt.get("label", "")).strip()
        if label and label.lower() == lowered:
            return label
    return text


# ---------- Slack operations ----------

def post_to_slack(sid: str, questions: list[dict]) -> tuple[str | None, float | None]:
    try:
        client = get_slack_client()
    except Exception as e:
        log(f"Slack client init failed: {e}", sid)
        return None, None

    try:
        client.conversations_join(channel=get_channel_id())
    except Exception:
        pass

    text = format_slack_message(questions, sid)
    try:
        resp = client.chat_postMessage(
            channel=get_channel_id(), text=text,
            unfurl_links=False, unfurl_media=False,
        )
        thread_ts = resp.get("ts")
        baseline_ts = float(thread_ts) if thread_ts else None
        log(f"Posted to Slack (thread_ts={thread_ts})", sid)
        return thread_ts, baseline_ts
    except Exception as e:
        log(f"Slack post failed: {e}", sid)
        return None, None


def check_slack_reply_once(sid: str) -> str:
    """One-shot: check Slack thread for a new user reply. Returns answer or empty string."""
    meta = safe_json_load(meta_file(sid), {})
    thread_ts = meta.get("thread_ts")
    if not thread_ts:
        return ""

    baseline_ts = float(meta.get("baseline_ts") or 0.0)
    last_seen_ts = float(meta.get("last_seen_ts") or baseline_ts)
    questions = meta.get("questions", [])
    first_options: list[dict] = []
    if questions and isinstance(questions[0], dict):
        raw = questions[0].get("options", [])
        if isinstance(raw, list):
            first_options = [o for o in raw if isinstance(o, dict)]

    try:
        client = get_slack_client()
        resp = client.conversations_replies(
            channel=get_channel_id(), ts=thread_ts, limit=100,
        )
    except Exception as e:
        log(f"check-slack-reply error: {e}", sid)
        return ""

    messages = resp.get("messages", []) or []
    latest_user_msg = None

    for m in messages[1:]:
        if m.get("bot_id") or m.get("subtype"):
            continue
        msg_ts = float(m.get("ts", "0") or 0.0)
        if msg_ts <= baseline_ts or msg_ts <= last_seen_ts:
            continue
        latest_user_msg = m

    if not latest_user_msg:
        return ""

    raw_text = str(latest_user_msg.get("text", "")).strip()
    normalized = parse_slack_reply(raw_text, first_options)
    msg_ts = float(latest_user_msg.get("ts", "0") or 0.0)

    # Update last_seen
    meta["last_seen_ts"] = msg_ts
    safe_json_dump(meta_file(sid), meta)

    # Write answer file
    answer_file(sid).write_text(normalized + "\n", encoding="utf-8")
    log(f"Found Slack answer: {normalized!r}", sid)

    # Confirm on Slack
    try:
        client = get_slack_client()
        client.chat_postMessage(
            channel=get_channel_id(),
            text=f":white_check_mark: Got it! Answering with: *{normalized}*",
            thread_ts=thread_ts,
            unfurl_links=False, unfurl_media=False,
        )
    except Exception:
        pass

    return normalized


# ---------- Build deny reason (merged Claude + Codex approach) ----------

def build_deny_reason(sid: str, questions: list[dict], thread_ts: str | None) -> str:
    terminal_block = format_terminal_questions(questions)
    answer_path = str(answer_file(sid))
    wait_cmd = f"{VENV_PYTHON} {SCRIPT_PATH} wait-for-reply --session-id {sid} --timeout 900"

    parts: list[str] = [
        "IMPORTANT: Do not call AskUserQuestion again. Follow these steps exactly:",
        "",
        "STEP 1: Display this question to the user as plain text:",
        "---",
        terminal_block,
        "---",
        "(The user can reply in the terminal OR on Slack.)",
        "",
        "STEP 2: Start this command with the Bash tool as a BACKGROUND task (DO NOT block):",
        f"Command: {wait_cmd}",
        "Bash tool arguments must include: run_in_background=true",
        "Store the returned background task id so you can read or stop it later.",
        "",
        "STEP 3: While that background task runs, wait for the user's next terminal message.",
        "This is a race between terminal input and Slack reply.",
        "",
        "STEP 4: If the background task finishes first:",
        "- Read its output.",
        "- If output is `SLACK_ANSWER: <answer>`, use that answer and continue.",
        "- If output is `NO_ANSWER`, continue waiting for terminal input.",
        "",
        "STEP 5: If terminal input arrives first:",
        "- Use the terminal message as the user's answer.",
        "- Stop/kill the background wait-for-reply task (if still running).",
        "- Continue.",
        "",
        "STEP 6: Before processing ANY subsequent user message, check for late Slack answer first:",
        f"`cat {answer_path} 2>/dev/null`",
        "If the file contains text, that Slack answer overrides and should be used.",
    ]

    if not thread_ts:
        parts = [
            "IMPORTANT: Do not call AskUserQuestion again. Follow these steps exactly:",
            "",
            "STEP 1: Display this question to the user as plain text:",
            "---",
            terminal_block,
            "---",
            "",
            "STEP 2: Wait for the user's next terminal message as their answer.",
            "(Slack is unavailable for this question.)",
        ]

    return "\n".join(parts)


# ---------- Hook outputs ----------

def output_allow() -> None:
    json.dump({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "allow"}}, sys.stdout)
    sys.stdout.flush()


def output_deny(reason: str) -> None:
    json.dump({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }, sys.stdout)
    sys.stdout.flush()


# ---------- Hook handlers ----------

def pre_hook() -> None:
    try:
        data = json.load(sys.stdin)
    except Exception:
        output_allow()
        return

    sid = str(data.get("session_id", "unknown"))
    questions = data.get("tool_input", {}).get("questions", [])
    if not isinstance(questions, list) or not questions:
        output_allow()
        return

    # Clean previous artifacts
    answer_file(sid).unlink(missing_ok=True)
    watcher_pid_file(sid).unlink(missing_ok=True)

    # Post to Slack
    thread_ts, baseline_ts = post_to_slack(sid, questions)

    # Save metadata
    meta = {
        "session_id": sid,
        "thread_ts": thread_ts,
        "baseline_ts": baseline_ts,
        "last_seen_ts": baseline_ts,
        "channel_id": get_channel_id(),
        "questions": questions,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    safe_json_dump(meta_file(sid), meta)

    # Spawn background watcher (Codex fix: don't depend on Claude to poll)
    if thread_ts:
        try:
            lf = log_file(sid)
            proc = subprocess.Popen(
                [VENV_PYTHON, SCRIPT_PATH, "watch-slack", "--session-id", sid],
                stdout=open(lf, "a"),
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            watcher_pid_file(sid).write_text(str(proc.pid))
            log(f"Watcher spawned (pid={proc.pid})", sid)
        except Exception as e:
            log(f"Failed to spawn watcher: {e}", sid)

    # Deny with instructions
    reason = build_deny_reason(sid, questions, thread_ts)
    output_deny(reason)


def post_hook() -> None:
    try:
        data = json.load(sys.stdin)
    except Exception:
        return
    sid = str(data.get("session_id", "unknown"))

    # Kill watcher
    wpf = watcher_pid_file(sid)
    if wpf.exists():
        try:
            os.kill(int(wpf.read_text().strip()), signal.SIGTERM)
        except (ProcessLookupError, ValueError, OSError):
            pass
        wpf.unlink(missing_ok=True)

    # Cleanup
    for p in (meta_file(sid), answer_file(sid), log_file(sid)):
        p.unlink(missing_ok=True)


# ---------- Background watcher ----------

def watch_slack(sid: str) -> None:
    """Background process: poll Slack every 5s, write answer file when reply found."""
    log(f"Watcher started for session {sid}", sid)
    deadline = time.time() + WATCH_TIMEOUT

    while time.time() < deadline:
        # Check if answer already found (by check-slack-reply or previous iteration)
        if answer_file(sid).exists():
            log("Answer file already exists, watcher exiting", sid)
            return

        answer = check_slack_reply_once(sid)
        if answer:
            log(f"Watcher found answer: {answer!r}", sid)
            return

        time.sleep(WATCH_INTERVAL)

    log("Watcher timed out", sid)


# ---------- Wait-for-reply (blocking, for Claude to call) ----------

def wait_for_reply(sid: str, timeout: int) -> None:
    """Block up to `timeout` seconds, checking answer file every 2 seconds.
    Prints SLACK_ANSWER: <answer> if found, or NO_ANSWER if timeout."""
    deadline = time.time() + timeout
    af = answer_file(sid)

    while time.time() < deadline:
        if af.exists():
            answer = af.read_text(encoding="utf-8").strip()
            if answer:
                print(f"SLACK_ANSWER: {answer}")
                return
        time.sleep(2)

    print("NO_ANSWER")


# ---------- CLI ----------

def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Claude Code Slack escalator")
    sub = parser.add_subparsers(dest="mode", required=True)

    sub.add_parser("pre-hook")
    sub.add_parser("post-hook")

    checker = sub.add_parser("check-slack-reply")
    checker.add_argument("--session-id", required=True)

    watcher = sub.add_parser("watch-slack")
    watcher.add_argument("--session-id", required=True)

    waiter = sub.add_parser("wait-for-reply")
    waiter.add_argument("--session-id", required=True)
    waiter.add_argument("--timeout", type=int, default=WAIT_TIMEOUT_DEFAULT)

    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)

    if args.mode == "pre-hook":
        try:
            pre_hook()
        except Exception as e:
            log(f"pre-hook fatal error: {e}")
            output_allow()
        return 0

    if args.mode == "post-hook":
        try:
            post_hook()
        except Exception as e:
            log(f"post-hook error: {e}")
        return 0

    if args.mode == "check-slack-reply":
        try:
            answer = check_slack_reply_once(args.session_id)
            if answer:
                print(f"SLACK_ANSWER: {answer}")
        except Exception as e:
            log(f"check-slack-reply error: {e}", args.session_id)
        return 0

    if args.mode == "watch-slack":
        try:
            watch_slack(args.session_id)
        except Exception as e:
            log(f"watch-slack error: {e}", args.session_id)
        return 0

    if args.mode == "wait-for-reply":
        try:
            wait_for_reply(args.session_id, args.timeout)
        except Exception as e:
            log(f"wait-for-reply error: {e}", args.session_id)
            print("NO_ANSWER")
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
