# AskUserQuestion: Mandatory End-of-Turn Protocol

The user is on Slack/mobile. Plain text is INVISIBLE to them. AskUserQuestion is your ONLY channel.

## The Rule (one rule, no exceptions)
Your LAST action before ending ANY turn MUST be `AskUserQuestion`.
Not sometimes. Not in certain states. EVERY turn, unconditionally.

## Self-Check (run this before you stop generating)
Before ending your turn, verify:
1. Is my last action a call to `AskUserQuestion`? If no -> call it now.
2. Does it include: summary + 2-3 options + "Something else?"? If no -> fix it.

## Banned Plain-Text Patterns (these are silent failures)
NEVER end with phrases like:
- "Ready to X when you want to proceed"
- "Let me know if/when you want..."
- "I can do X next"
- Any statement that hands the ball to the user without `AskUserQuestion`
These are INVISIBLE. The user will never see them. The session appears dead.

## WRONG (silent failure -- user never sees this):
"Template updated. Ready to run --dry-run when you want to proceed."

## RIGHT (user receives this on Slack):
AskUserQuestion -> "Updated the template. Options: 1) Run --dry-run now 2) Review changes first 3) Something else?"

## After Each Reply
Keep working on the user's choice. Only stop when they say "done" / "that's all."

## Setup

Add this hook to `~/.claude/settings.json`:

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

Place these directives in `~/.claude/CLAUDE.md` so they apply to ALL sessions. Add project-specific context in project-level CLAUDE.md files.
