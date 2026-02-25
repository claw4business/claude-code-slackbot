# Claude Code Slackbot

Slack integration for [Claude Code](https://claude.ai/claude-code) that lets you answer Claude's questions from your phone via Slack — or from the terminal. Whichever you answer first wins.

**Two features:**
1. **Question Escalation** — Claude Code's `AskUserQuestion` calls get posted to Slack automatically
2. **Slack Launcher** — Start Claude Code sessions from Slack with `@yourbot /claude <task>`

## How It Works

When Claude calls `AskUserQuestion`, a [PreToolUse hook](https://docs.anthropic.com/en/docs/claude-code/hooks) intercepts it:

1. Posts the question to your Slack channel immediately
2. Spawns a background watcher polling for Slack replies
3. **Denies** the interactive questionnaire — instead tells Claude to display the question as plain text
4. Claude runs a background `wait-for-reply` command watching for Slack answers
5. You answer in **Slack** (reply to the thread) or **terminal** (just type) — first response wins

This means you can walk away from your computer and still answer Claude's questions from your phone.

---

## Prerequisites

- Python 3.10+
- [Claude Code CLI](https://claude.ai/claude-code) installed
- A Slack workspace you can create apps in
- `tmux` (for the launcher feature)

---

## Setup

### Step 1: Create a Slack App

1. Go to [api.slack.com/apps](https://api.slack.com/apps) and click **Create New App** → **From scratch**
2. Name it whatever you want (e.g. `Claude Bot`) and select your workspace
3. Go to **OAuth & Permissions** and add these **Bot Token Scopes**:
   - `channels:history` — read messages in public channels
   - `channels:read` — view basic channel info
   - `chat:write` — post messages
   - `users:read` — resolve user names
4. Go to **Event Subscriptions** → Enable Events, and subscribe to these **bot events**:
   - `app_mention` — for the launcher feature (optional)
   - `message.channels` — to read replies
5. Click **Install to Workspace** and authorize
6. Copy the **Bot User OAuth Token** (starts with `xoxb-`)

### Step 2: Configure Your Channel

1. Create a Slack channel for Claude (e.g. `#claude`)
2. Invite your bot to the channel: `/invite @YourBotName`
3. Get the channel ID: right-click the channel name → **View channel details** → scroll to the bottom, copy the ID (starts with `C`)

### Step 3: Clone and Configure

```bash
git clone https://github.com/claw4business/claude-code-slackbot.git
cd claude-code-slackbot
```

Create a `.env` file in the repo directory with your Slack credentials:

```bash
SLACK_BOT_TOKEN=xoxb-your-bot-token-here
```

Set up a Python virtual environment with dependencies:

```bash
python3 -m venv venv
source venv/bin/activate
pip install slack-sdk slack-bolt
```

Edit the config constants at the top of `escalator.py`:

```python
# Point these to YOUR .env file and venv
BIZ_SIM_ENV = Path("/path/to/your/.env")
VENV_LIB_ROOT = Path("/path/to/your/venv/lib")
VENV_PYTHON = "/path/to/your/venv/bin/python3"

# Your Slack channel ID
SLACK_CHANNEL_ID = "C0YOUR_CHANNEL_ID"
```

### Step 4: Configure Claude Code Hooks

Add this to your `~/.claude/settings.json` (create the file if it doesn't exist):

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "AskUserQuestion",
        "hooks": [
          {
            "type": "command",
            "command": "/path/to/your/venv/bin/python3 /path/to/claude-code-slackbot/escalator.py pre-hook",
            "timeout": 960
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "AskUserQuestion",
        "hooks": [
          {
            "type": "command",
            "command": "/path/to/your/venv/bin/python3 /path/to/claude-code-slackbot/escalator.py post-hook",
            "timeout": 10
          }
        ]
      }
    ]
  }
}
```

Replace the paths with your actual venv python and escalator.py locations.

### Step 5: Register as a Claude Code Skill (Optional)

To make Claude aware of this skill's capabilities:

```bash
mkdir -p ~/.claude/skills
ln -s /path/to/claude-code-slackbot ~/.claude/skills/slack-escalator
```

### Step 6: Force Claude to Always Use AskUserQuestion

**This is critical.** Without this, Claude may print questions as plain text instead of using `AskUserQuestion`, which means they won't reach Slack.

Add this line to your project's `CLAUDE.md` file (or `~/.claude/CLAUDE.md` for global, or your memory file):

```
**All questions MUST go through `AskUserQuestion`** — never print questions as plain text. The slack-escalator hook pushes them to Slack so the user sees them on mobile even when away from terminal.
```

---

## Answering Questions

**From Slack:** Reply to the question's thread with your answer. Use a number (`1`, `2`, `3`) to pick an option, or type free text.

**From terminal:** Just type your answer in the Claude Code terminal as you normally would.

Whichever arrives first wins. The other path is automatically cleaned up.

---

## Slack Launcher

Launch Claude Code sessions remotely from Slack — no terminal required:

```
@YourBotName /claude Fix the login bug in auth.py
```

What happens:
1. The launcher picks up your message in the Slack channel
2. Spins up a new **tmux session** running Claude Code with your task
3. Posts an acknowledgement to the Slack thread with session details
4. Claude works autonomously — if it has questions, the **escalator hook** posts them back to Slack
5. You answer questions by replying to threads on your phone
6. When Claude finishes, a completion summary is posted to the thread

This means you can kick off coding tasks from your couch and monitor progress entirely from Slack.

### Launcher Config

Edit the config constants at the top of `launcher.py`:

```python
# Your Slack channel ID
SLACK_CHANNEL_ID = "C0YOUR_CHANNEL_ID"

# Your bot's user ID (find in Slack app settings → Basic Information)
BOT_USER_ID = "U0YOUR_BOT_ID"
```

### Systemd Service Setup

The launcher runs as a background service that polls Slack for `/claude` commands.

Create `~/.config/systemd/user/slack-launcher.service`:

```ini
[Unit]
Description=Slack-to-Claude Code Launcher
After=network-online.target

[Service]
Type=simple
ExecStart=/path/to/your/venv/bin/python3 /path/to/claude-code-slackbot/launcher.py
Restart=always
RestartSec=10
Environment=HOME=%h
Environment=PATH=%h/.local/bin:/usr/local/bin:/usr/bin:/bin
WorkingDirectory=%h

[Install]
WantedBy=default.target
```

Enable and start:

```bash
systemctl --user daemon-reload
systemctl --user enable --now slack-launcher.service
```

Manage:

```bash
systemctl --user status slack-launcher    # check status
systemctl --user restart slack-launcher   # restart after config changes
journalctl --user -u slack-launcher -f    # watch logs live
```

### Finding Your Bot User ID

You need the bot's Slack user ID (starts with `U`) for the launcher config:

1. In Slack, go to your bot's profile (click its name in any message)
2. Click the **...** menu → **Copy member ID**
3. Or check your app settings at [api.slack.com/apps](https://api.slack.com/apps) → **Basic Information**

### Attaching to Sessions

Each launched task runs in its own tmux session. You can attach from any terminal:

```bash
tmux list-sessions              # see all running sessions
tmux attach -t claude-fix-bug-a1b2   # attach to a specific session
```

Session logs are saved to `~/claude-sessions/`.

### How Escalator + Launcher Work Together

When the launcher starts a Claude session with `--dangerously-skip-permissions`, the escalator hook is still active. So when Claude needs to ask a question during a launched task:

1. Claude calls `AskUserQuestion`
2. The escalator hook posts the question to Slack
3. You reply to the thread on Slack
4. Claude gets the answer and continues working

This creates a fully remote workflow — launch from Slack, answer questions on Slack, get results on Slack.

---

## Files

| File | Description |
|------|-------------|
| `escalator.py` | Question hook + Slack watcher + reply checker |
| `launcher.py` | Slack listener/launcher service |
| `SKILL.md` | Skill description (read by Claude Code at runtime) |
| `CLAUDE.md` | Claude Code instructions (enforces AskUserQuestion usage) |

---

## How the Race Works

```
User runs Claude Code
        │
Claude calls AskUserQuestion
        │
   PreToolUse hook fires
        │
   ┌────┴────┐
   │  Posts   │
   │ to Slack │
   └────┬────┘
        │
   Hook DENIES the interactive questionnaire
        │
   Claude displays question as plain text
        │
   Starts background wait-for-reply
        │
   ┌────────────────┬────────────────┐
   │   Terminal      │     Slack      │
   │   (user types)  │  (user replies │
   │                 │   to thread)   │
   └───────┬────────┘───────┬────────┘
           │                │
     First response wins ───┘
           │
   Claude continues with the answer
```

---

## Troubleshooting

**Question doesn't appear on Slack:**
- Check that your `SLACK_BOT_TOKEN` is correct in `.env`
- Verify the bot is invited to the channel
- Check the channel ID matches `SLACK_CHANNEL_ID` in `escalator.py`

**Slack reply not detected:**
- Make sure you're replying **in the thread**, not as a new message
- Bot messages are filtered out — reply from your own Slack account, not another bot

**Terminal is blocked / can't type:**
- The `wait-for-reply` command should run with `run_in_background=true`. If Claude isn't doing this, check that the deny reason in `build_deny_reason()` includes the background instruction.

**Hook not firing:**
- Verify `~/.claude/settings.json` has the correct paths
- Test manually: `python3 escalator.py pre-hook < test-input.json`

---

## License

MIT
