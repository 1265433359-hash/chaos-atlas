# P02 Teacher Minikube Formal Audit: teacher-minikube-formal-r3

- Batch: `completed`, 15/15 completed.
- Reports: 15; all technically valid: `true`.
- Clean execution sequence: `true`.
- Runtime head-to-head eligible: `false`.

## Arm Coverage

| Arm | Accepted | Rejected | Executable | Executions | Valid | Baseline contaminated | Targets |
|---|---:|---:|---:|---:|---:|---:|---|
| ChaosAtlas-KB-open | 2 | 0 | 2 | 6 | 6 | 0 | api-gateway, discovery-server |
| ChaosAtlas-noKB-open | 2 | 0 | 2 | 6 | 6 | 0 | api-gateway, discovery-server |
| ChaosEater-adapter-open | 1 | 1 | 1 | 3 | 3 | 0 | api-gateway |

## Confirmed Project Findings

- `P02-ISSUE-001` (api-gateway): Every sole api-gateway Pod kill produced at least one non-200 business observation before replacement recovery.
- `P02-ISSUE-002` (discovery-server): Discovery-server kills produced delayed non-200 responses inside the same run's post-cleanup washout. Logs, events, and traces must be reviewed before assigning a causal mechanism.

## Interpretation

- P02 seed-1001 is a null selection result: KB and noKB produced the same two executable candidates. It neither demonstrates a KB benefit nor disproves one across projects.
- The adapter produced one executable api-gateway mutation; its config-server latency proposal was rejected by the compiler parameter contract. This is a tool-chain compatibility result, not an official ChaosEater score.
- R2 remains valuable execution and issue-discovery evidence, but a clean comparison requires a sustained post-recovery observation and washout window before the next mutation.
