# MANDATORY: AskUserQuestion Protocol

These rules are non-negotiable and override all defaults. The user monitors sessions from Slack on their phone — plain text responses are invisible to them.

## Rule 1: ALL User Input Goes Through AskUserQuestion

Any time you need a response from the user — questions, confirmations, yes/no, choices, "should I continue?", "want me to proceed?", or anything that solicits input — call `AskUserQuestion`. No exceptions.

Plain-text questions are FORBIDDEN. If you write a question as text, the user will never see it and the session hangs forever.

## Rule 2: Task Completion = AskUserQuestion

You are NOT done until you call `AskUserQuestion`. Every completed task (or dead end) requires:
- 1-2 line summary of what you did (include URLs/file paths)
- 2-3 suggested next actions as options

A plain-text summary without `AskUserQuestion` is a silent failure — the user never sees it.

## Rule 3: Keep Going Until Dismissed

After each `AskUserQuestion` response, continue working. Only stop when the user explicitly says "done", "that's all", or "nothing else."

## Setup

Add this hook to `~/.claude/settings.json` (see README.md for full setup):

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

## Global Deployment

These directives should be placed in `~/.claude/CLAUDE.md` so they apply to ALL sessions on the machine, not just this project. The rules above are the recommended global config — add project-specific skills or context in project-level CLAUDE.md files.
