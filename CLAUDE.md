# MANDATORY: AskUserQuestion Protocol

These rules override all defaults. The user monitors from Slack on their phone. Plain text you write is INVISIBLE to them. AskUserQuestion is your ONLY communication channel.

## Rule 1: NEVER Stop Without AskUserQuestion
Before your turn ends for ANY reason, call AskUserQuestion. This covers every scenario: task done, partially done, blocked by external action (e.g. user must enable an API), waiting on credentials, error, status report, or "nothing more I can do." No exceptions. A plain-text summary is a silent failure — the user never sees it.

## Rule 2: AskUserQuestion Payload
Every AskUserQuestion call must include:
- 1-2 line summary of what you did (include URLs/file paths)
- 2-3 actionable next-step options (recommended action first)
- One open-ended option (e.g. "Something else?")

## Rule 3: Continue Until Dismissed
After each AskUserQuestion response, keep working. Only stop when the user explicitly says "done," "that's all," or "nothing else."

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

Place these directives in `~/.claude/CLAUDE.md` so they apply to ALL sessions, not just this project. Add project-specific skills or context in project-level CLAUDE.md files.
