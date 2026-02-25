#!/usr/bin/env python3
"""
Slack-to-Claude Launcher

Polls Slack #claude for messages that @mention the bot with /claude command.
When found, spins up a new tmux session running Claude Code with the user's task.

Usage in Slack:
  @biz_simulator /claude Fix the login bug in auth.py
  @biz_simulator /claude Add dark mode to the dashboard

Each task gets its own tmux session. User can:
  - Answer questions via Slack (slack-escalator hook handles this)
  - Attach to the tmux session from terminal: tmux attach -t <session-name>
  - See Claude's output summary posted back to the Slack thread

Runs as a systemd user service (slack-launcher.service).
"""

import sys
import os
import json
import time
import re
import subprocess
import hashlib
from pathlib import Path
from datetime import datetime

# ---------- Config ----------

# Path to .env file containing SLACK_BOT_TOKEN (and optionally SLACK_APP_TOKEN)
# Update this to point to YOUR .env file
ENV_FILE = Path(__file__).resolve().parent / ".env"

# Slack channel ID where the bot listens for /claude commands
# Get this from: channel details → scroll to bottom → copy ID (starts with C)
SLACK_CHANNEL_ID = "C0AGW5W7Z7X"  # UPDATE THIS to your channel

# Bot user ID — find this in your Slack app settings under "Basic Information"
BOT_USER_ID = "U0AHC57UW6M"       # UPDATE THIS to your bot's user ID

POLL_INTERVAL = 5                   # seconds between checks
STATE_FILE = Path("/tmp/claude-launcher-state.json")
LOG_DIR = Path.home() / "claude-sessions"
CLAUDE_BIN = Path.home() / ".local" / "bin" / "claude"

# ---------- Helpers ----------

def load_env():
    """Load env vars from .env file."""
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, _, value = line.partition('=')
                os.environ.setdefault(key.strip(), value.strip())


def get_slack_client():
    """Create a Slack WebClient."""
    load_env()
    # Add venv site-packages to path (look for venv next to this script, or fallback)
    script_dir = Path(__file__).resolve().parent
    for venv_root in [script_dir / "venv", Path.home() / "biz-simulator" / "venv"]:
        venv_pkgs = venv_root / "lib"
        for p in venv_pkgs.glob("python*/site-packages"):
            if str(p) not in sys.path:
                sys.path.insert(0, str(p))
    from slack_sdk import WebClient
    token = os.environ.get("SLACK_BOT_TOKEN") or os.environ.get("SIMULATOR_SLACK_TOKEN", "")
    return WebClient(token=token)


def log(msg):
    """Log with timestamp."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def load_state():
    """Load processed message timestamps."""
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {"processed": [], "sessions": {}}


def save_state(state):
    """Save state to disk."""
    STATE_FILE.write_text(json.dumps(state, indent=2))


def make_session_name(task_text):
    """Generate a short, unique tmux session name from task text."""
    # Take first few words + short hash
    words = re.sub(r'[^a-zA-Z0-9 ]', '', task_text).split()[:3]
    slug = "-".join(w.lower() for w in words) if words else "task"
    short_hash = hashlib.md5(f"{task_text}{time.time()}".encode()).hexdigest()[:4]
    return f"claude-{slug}-{short_hash}"


def parse_command(text):
    """Parse a Slack message for /claude command.

    Expected format: <@U0AHC57UW6M> /claude <task description>
    Returns task text or None.
    """
    # Remove the bot mention
    text = re.sub(r'<@[A-Z0-9]+>', '', text).strip()

    # Check for /claude prefix
    if text.startswith('/claude'):
        task = text[len('/claude'):].strip()
        if task:
            return task
    return None


def launch_claude_session(task_text, session_name, log_file):
    """Launch Claude Code in a new tmux session with the given task."""
    # Create the wrapper script that runs claude with the task
    wrapper = Path(f"/tmp/claude-launch-{session_name}.sh")
    wrapper.write_text(f"""#!/bin/bash
# Claude Code session: {session_name}
# Task: {task_text}
# Log: {log_file}

export PATH="$HOME/.local/bin:$PATH"

# Run Claude with the task in print/non-interactive mode
# Output goes to both terminal (tmux) and log file
claude --dangerously-skip-permissions -p {json.dumps(task_text)} 2>&1 | tee "{log_file}"

echo ""
echo "========================================"
echo "Claude session complete."
echo "Session: {session_name}"
echo "Log: {log_file}"
echo "========================================"
# Keep session open for 30s so user can see output if attached, then auto-close
sleep 30
""")
    wrapper.chmod(0o755)

    # Create tmux session
    result = subprocess.run(
        ["tmux", "new-session", "-d", "-s", session_name, str(wrapper)],
        capture_output=True, text=True,
    )

    if result.returncode != 0:
        log(f"Failed to create tmux session: {result.stderr}")
        return False

    log(f"Launched tmux session: {session_name}")
    return True


def post_completion_summary(client, channel, thread_ts, session_name, log_file):
    """Post a summary of Claude's output to the Slack thread."""
    try:
        if Path(log_file).exists():
            output = Path(log_file).read_text()
            # Get last ~500 chars as summary
            if len(output) > 500:
                summary = "..." + output[-500:]
            else:
                summary = output

            client.chat_postMessage(
                channel=channel,
                text=f":white_check_mark: *Session `{session_name}` completed*\n\n```\n{summary}\n```",
                thread_ts=thread_ts,
                unfurl_links=False,
                unfurl_media=False,
            )
        else:
            client.chat_postMessage(
                channel=channel,
                text=f":white_check_mark: *Session `{session_name}` completed* (no log output found)",
                thread_ts=thread_ts,
                unfurl_links=False,
                unfurl_media=False,
            )
    except Exception as e:
        log(f"Failed to post completion summary: {e}")


def check_session_status(client, state):
    """Check if any running sessions have completed and post summaries."""
    sessions = state.get("sessions", {})
    completed = []

    for session_name, info in sessions.items():
        # Check if tmux session still exists
        result = subprocess.run(
            ["tmux", "has-session", "-t", session_name],
            capture_output=True,
        )
        if result.returncode != 0:
            # Session ended
            log(f"Session {session_name} has ended")
            post_completion_summary(
                client,
                info["channel"],
                info["thread_ts"],
                session_name,
                info["log_file"],
            )
            completed.append(session_name)

    for name in completed:
        del sessions[name]


# ---------- Main loop ----------

def main():
    """Main polling loop."""
    log("Slack-to-Claude launcher starting...")
    LOG_DIR.mkdir(exist_ok=True)

    client = get_slack_client()

    # Verify connection
    try:
        auth = client.auth_test()
        log(f"Connected as {auth['user']} ({auth['user_id']})")
    except Exception as e:
        log(f"Slack auth failed: {e}")
        sys.exit(1)

    state = load_state()
    # On fresh start, set last_checked to now to avoid processing old messages
    if "last_checked" not in state:
        state["last_checked"] = str(time.time())
        save_state(state)

    log(f"Polling #{SLACK_CHANNEL_ID} every {POLL_INTERVAL}s for /claude commands...")
    log(f"Trigger: @biz_simulator /claude <task>")

    while True:
        try:
            # Fetch recent messages (don't use 'oldest' param — unreliable with precise timestamps)
            resp = client.conversations_history(
                channel=SLACK_CHANNEL_ID,
                limit=10,
            )

            last_checked_f = float(state["last_checked"])
            messages = resp.get("messages", [])
            for msg in reversed(messages):  # oldest first
                msg_ts = msg.get("ts", "")
                text = msg.get("text", "")

                # Skip messages older than our checkpoint
                if float(msg_ts) <= last_checked_f:
                    continue

                # Skip already processed
                if msg_ts in state.get("processed", []):
                    continue

                # Check for bot mention + /claude command
                if f"<@{BOT_USER_ID}>" not in text:
                    continue

                task_text = parse_command(text)
                if not task_text:
                    # Not a /claude command, might be a question reply
                    state.setdefault("processed", []).append(msg_ts)
                    continue

                log(f"New task: {task_text[:80]}...")

                # Create session
                session_name = make_session_name(task_text)
                log_file = str(LOG_DIR / f"{session_name}.log")

                # Acknowledge on Slack
                try:
                    ack_resp = client.chat_postMessage(
                        channel=SLACK_CHANNEL_ID,
                        text=(
                            f":rocket: *Launching Claude Code session*\n"
                            f"*Task:* {task_text}\n"
                            f"*Session:* `{session_name}`\n"
                            f"*Terminal:* `tmux attach -t {session_name}`\n"
                            f"*Log:* `{log_file}`"
                        ),
                        thread_ts=msg_ts,
                        unfurl_links=False,
                        unfurl_media=False,
                    )
                except Exception as e:
                    log(f"Slack ack failed: {e}")

                # Launch the session
                success = launch_claude_session(task_text, session_name, log_file)

                if success:
                    state.setdefault("sessions", {})[session_name] = {
                        "channel": SLACK_CHANNEL_ID,
                        "thread_ts": msg_ts,
                        "log_file": log_file,
                        "task": task_text,
                        "started": datetime.now().isoformat(),
                    }
                else:
                    try:
                        client.chat_postMessage(
                            channel=SLACK_CHANNEL_ID,
                            text=f":x: Failed to launch session. Check logs.",
                            thread_ts=msg_ts,
                            unfurl_links=False,
                            unfurl_media=False,
                        )
                    except Exception:
                        pass

                state.setdefault("processed", []).append(msg_ts)

            # Update last_checked to latest message ts
            if messages:
                state["last_checked"] = messages[0]["ts"]  # newest first from API

            # Trim processed list (keep last 100)
            if len(state.get("processed", [])) > 100:
                state["processed"] = state["processed"][-100:]

            # Check for completed sessions
            check_session_status(client, state)

            save_state(state)

        except Exception as e:
            log(f"Poll error: {e}")

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "test-parse":
        # Quick parse test
        tests = [
            f"<@{BOT_USER_ID}> /claude Fix the login bug",
            f"<@{BOT_USER_ID}> /claude",
            f"<@{BOT_USER_ID}> hello",
            "random message",
            f"<@{BOT_USER_ID}> /claude Add dark mode to the dashboard with a toggle switch",
        ]
        for t in tests:
            result = parse_command(t)
            print(f"  {t[:60]:60s} -> {result}")
    else:
        main()
