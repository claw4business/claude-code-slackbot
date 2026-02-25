# Claude Code Instructions

## Mandatory: All Questions Go Through AskUserQuestion

**ALWAYS use the `AskUserQuestion` tool for ANY question directed at the user.** Never print questions as plain text and wait for input. The slack-escalator hook intercepts `AskUserQuestion` calls and:

1. Posts the question to Slack so the user sees it on mobile
2. Displays it as plain text in the terminal
3. Accepts answers from either Slack or the terminal (whichever comes first)

If you skip `AskUserQuestion` and just print a question, the user will NOT see it on Slack and may miss it entirely.

## Never End a Session Without Asking What's Next

**When you finish a task, DO NOT just stop.** Instead, always use `AskUserQuestion` to nudge the user with a "what should I do next?" prompt. This keeps the session alive and the user engaged from Slack/mobile.

Include relevant context and links in your question. For example, if you just finished work involving data, spreadsheets, or lead-hunter:

> "Done! Here's the test spreadsheet: https://docs.google.com/spreadsheets/d/1zb0cl7IkEBMMSsu0E6IB9DmQa6QdRvnrfDVwlyvbkXA
>
> What should I do next?"

### Guidelines for the "what's next" nudge:
- **Always include links** to any artifacts you created or worked on (spreadsheets, repos, dashboards, files)
- **Summarize what was accomplished** in 1-2 lines before asking
- **Suggest 2-3 concrete next steps** as options when applicable (e.g., "Run more tests?", "Deploy to production?", "Set up the next integration?")
- **This applies to ALL sessions** — whether launched from Slack, terminal, or anywhere else
- The only exception is if the user explicitly says "that's all" or "done" — then you can end cleanly

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
