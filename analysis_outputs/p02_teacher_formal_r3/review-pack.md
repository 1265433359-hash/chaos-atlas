# P02 Pending Human Review

No knowledge update has been applied. Review the immutable R3 reports and diagnostic sidecars first.

## P02-ISSUE-001

- Proposed classification: `confirmed_weakness`
- Evidence: Every sole api-gateway Pod kill produced at least one non-200 business observation before replacement recovery.
- Human decision: `pending`
- Note: pending

## P02-ISSUE-002

- Proposed classification: `confirmed_weakness`
- Evidence: Discovery-server kills produced delayed non-200 responses inside the same run's post-cleanup washout. Logs, events, and traces must be reviewed before assigning a causal mechanism.
- Human decision: `pending`
- Note: Do not name a cache, registration, or Eureka mechanism unless scoped logs or traces support it.
