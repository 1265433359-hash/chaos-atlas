# Sock Shop Two-Arm Runtime Review

- `human_review`: `pending`
- `knowledge_base_updated`: `false`
- `project`: `sock-shop`
- `namespace`: `chaosatlas-sock-shop`
- `reports`: 48/48
- `verification`: passed

## Observed Results

| method | reports | weakness observed | no business impact observed |
|---|---:|---:|---:|
| ChaosAtlas-full | 24 | 11 | 13 |
| ChaosAtlas-ablation | 24 | 14 | 10 |

The business oracle exercised front-end, catalogue, login, and orders. Across
the 240 injected journey samples, the observed response evidence included 43
catalogue HTTP 500 responses, 37 orders HTTP 500 responses, 27 login HTTP 401
responses, and additional timeout or connection-failure samples. These counts
describe observed oracle outcomes; they are not a claim that every sample
failed for the same reason.

The diagnostic events include readiness-probe connection-refused messages for
affected Pods, and service logs were captured with SHA-256 values verified
against the reports. Sock Shop has no trace backend in the frozen topology;
`zipkin-unavailable.json` records that limitation.

## Root-Cause Boundary

The business weakness is confirmed for reports classified
`weakness_observed`. The available evidence supports affected service/workload
and fault-family associations, plus readiness and service-log symptoms. It
does not support guessing Eureka, cache, registration, discovery, retry,
timeout, or another specific internal mechanism.

The first r3 attempt at seed-1003/full/hyp-001 exposed a runner failure:
NetworkChaos recovered and was deleted, but a restarted local port-forward
later exited and recovery requests received `WinError 10061`. This was
diagnosed as an observation-channel defect, fixed with recovery/washout
port-forward liveness rebinding, covered by regression tests, and excluded
from final statistics. The affected unit completed successfully in r4.

## Evidence

- `SOCK_RUNTIME_VERIFICATION.json`
- `SOCK_RUNTIME_SUMMARY.json`
- `batch-progress.json`
- `runtime_results-r3` prior completed reports
- `runtime_results-r4` rerun reports and diagnostics

This report is an audit artifact only. It does not update a knowledge base or
promote a pending finding into reusable project knowledge.
