---
name: slack-escalator
description: Slack question escalation + remote Claude Code launcher
version: 3.1.0
---

# Slack Escalator & Launcher

Two features in one package:

## 1. Question Escalation (AskUserQuestion Hook)

When Claude calls `AskUserQuestion`, the PreToolUse hook:
- Posts the question to the configured Slack channel immediately
- Spawns a background watcher that polls Slack every 5s for replies
- **DENIES** AskUserQuestion with instructions telling Claude to:
  1. Display the question as plain text (no interactive questionnaire)
  2. Run `wait-for-reply` in the background (watches for Slack answer up to 15 min)
  3. Race between terminal input and Slack reply — first response wins
  4. Do not call AskUserQuestion again

### Answering

**On Slack:** Reply to the question thread with a number (`1`, `2`) or free text.
**In terminal:** Just type your answer when prompted.

## 2. Slack-to-Claude Launcher

Launch Claude Code sessions from Slack by @mentioning the bot:

```
@YourBot /claude <your task description>
```

Each task gets its own tmux session. You can:
- **Answer questions via Slack** — the escalator hook handles this automatically
- **Attach from terminal** — `tmux attach -t <session-name>`
- **See results on Slack** — completion summary posted to the command thread

### Launcher Service

Runs as systemd user service `slack-launcher.service`:
```bash
systemctl --user status slack-launcher
systemctl --user restart slack-launcher
journalctl --user -u slack-launcher -f
```

## Files

- `escalator.py` — Question hook + Slack watcher + reply checker
- `launcher.py` — Slack listener/launcher service
- `CLAUDE.md` — Claude Code instructions (enforces AskUserQuestion usage)
- `~/.claude/settings.json` — Hook configuration (PreToolUse timeout: 960s)
- `~/.config/systemd/user/slack-launcher.service` — Launcher systemd service
- `~/claude-sessions/` — Session logs

## Dependencies

- `slack-sdk` (Python package, install in venv)
- Slack bot token in `.env` file
- tmux, claude CLI
