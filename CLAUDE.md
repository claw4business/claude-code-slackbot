# Claude Code Instructions

## Mandatory: All Questions Go Through AskUserQuestion

**ALWAYS use the `AskUserQuestion` tool for ANY question directed at the user.** Never print questions as plain text and wait for input. The slack-escalator hook intercepts `AskUserQuestion` calls and:

1. Posts the question to Slack so the user sees it on mobile
2. Displays it as plain text in the terminal
3. Accepts answers from either Slack or the terminal (whichever comes first)

If you skip `AskUserQuestion` and just print a question, the user will NOT see it on Slack and may miss it entirely.

## Never End a Session Without Asking What's Next

**Never end a session silently.** When you complete a task (or hit a dead end), ALWAYS use `AskUserQuestion` to ask the user what to do next. This ensures the user gets a Slack notification and can respond from their phone.

- Summarize what you accomplished in 1-2 lines
- Include links to any artifacts you created or used (spreadsheets, repos, deployed URLs)
- Suggest 2-3 concrete next steps as options when applicable
- Only stop if the user explicitly says "that's all", "done", or "nothing else"

## Global CLAUDE.md

This skill's directives should be included in a global `~/.claude/CLAUDE.md` so they apply to all sessions on the machine, not just this project. See the README for the recommended global config.

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
