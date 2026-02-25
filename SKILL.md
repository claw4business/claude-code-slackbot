---
name: slack-escalator
description: Slack question escalation + remote Claude Code launcher
version: 3.0.0
---

# Slack Escalator & Launcher

Two features in one package:

## 1. Question Escalation (AskUserQuestion Hook)

When Claude calls `AskUserQuestion`, the PreToolUse hook:
- Posts the question to **#claude** on Slack immediately
- Spawns a background watcher that polls Slack every 5s for replies
- **DENIES** AskUserQuestion with instructions telling Claude to:
  1. Display the question as plain text (no interactive questionnaire)
  2. Run `wait-for-reply` command (blocks up to 15 min watching for Slack answer)
  3. If Slack answer found → use it and continue
  4. If no Slack answer → wait for terminal input

### Answering

**On Slack:** Reply to the question thread with a number (`1`, `2`) or free text.
**In terminal:** Just type your answer when prompted.

## 2. Slack-to-Claude Launcher

Launch Claude Code sessions from Slack by @mentioning the bot:

```
@biz_simulator /claude <your task description>
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

- `~/skills/slack-escalator/escalator.py` — Question hook + Slack watcher + reply checker
- `~/skills/slack-escalator/launcher.py` — Slack listener/launcher service
- `~/.claude/settings.json` — Hook configuration (PreToolUse timeout: 960s)
- `~/.config/systemd/user/slack-launcher.service` — Launcher systemd service
- `~/claude-sessions/` — Session logs

## Dependencies

- `slack-sdk`, `slack-bolt` (via `~/biz-simulator/venv/`)
- Slack bot token from `~/biz-simulator/.env`
- tmux, claude CLI
