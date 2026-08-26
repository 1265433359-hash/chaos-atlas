---
project_name: ChaosAtlas
---

# Completion Notification

## Mandatory Completion Gate

Before sending any final response for a task, determine exactly one final result:
`success`, `failed`, `partial`, or `blocked`.

Immediately before the final response, invoke the `email-notify` skill exactly once with that result. The skill must enqueue the notification locally; do not connect to SMTP from the Codex command environment. Do not send notifications for intermediate progress updates, clarification questions, or ongoing work.

- If local enqueue fails, state that the notification was not queued and include the error; do not silently skip it.
- If the user interrupts or cancels the task before the final response, no completion email is expected.

- Use status `success` only when verification passed; otherwise use `failed`, `partial`, or `blocked`.
- The email subject must be generated as `[<project_name>] <session name>` by the skill.
- Include the project name, session name, result status, and a concise summary of the changes and verification.
- Never include passwords, email authorization codes, API keys, tokens, private keys, or full file contents.
