# Claude Code Instructions

## Mandatory: All Questions Go Through AskUserQuestion

**ALWAYS use the `AskUserQuestion` tool for ANY question directed at the user.** Never print questions as plain text and wait for input. The slack-escalator hook intercepts `AskUserQuestion` calls and:

1. Posts the question to Slack so the user sees it on mobile
2. Displays it as plain text in the terminal
3. Accepts answers from either Slack or the terminal (whichever comes first)

If you skip `AskUserQuestion` and just print a question, the user will NOT see it on Slack and may miss it entirely.

### Setup Required

If the slack-escalator hook is not yet configured, add this to your `~/.claude/settings.json` (see README.md for full setup instructions):

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "AskUserQuestion",
        "hooks": [
          {
            "type": "command",
            "command": "<venv-python> <path-to>/escalator.py pre-hook",
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
            "command": "<venv-python> <path-to>/escalator.py post-hook",
            "timeout": 10
          }
        ]
      }
    ]
  }
}
```
