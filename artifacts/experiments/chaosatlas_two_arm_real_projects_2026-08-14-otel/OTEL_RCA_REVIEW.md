# OpenTelemetry Demo Two-Arm Runtime Review

- `human_review`: `pending`
- `knowledge_base_updated`: `false`
- `project`: `opentelemetry-demo`
- `namespace`: `chaosatlas-otel`

## Execution Status

The static profile, server-side dry-run, baseline windows, recovery rehearsal,
DeepSeek discovery gate, and formal runtime verification passed. The formal
matrix contains 48/48 completed reports:

| method | reports | weakness observed | no business impact observed |
|---|---:|---:|---:|
| ChaosAtlas-full | 24 | 10 | 14 |
| ChaosAtlas-ablation | 24 | 12 | 12 |

`OTEL_RUNTIME_VERIFICATION.json` reports `passed`, with all lifecycle,
cleanup, washout, diagnostic, and SHA-256 checks passing. The discovery gate
has 6/6 valid calls, four selected hypotheses and four compiled mutations per
method/seed. The frozen OTel input has no trace backend, so trace-unavailable
artifacts are evidence of unavailable tracing, not trace results.

## Observed Behavior

The business oracle records reproducible weaknesses for selected checkout/cart
faults and no observed business impact for other selected faults. These are
observed workflow outcomes under the frozen topology and two-arm protocol.
They do not establish a specific timeout, retry, fallback, cache, Eureka,
registration, discovery, or other internal mechanism.

The full and ablation counts are descriptive only. The selected hypotheses are
not identical across the two arms, so the counts must not be interpreted as a
causal superiority claim without a matched-hypothesis analysis.

## Root-Cause Boundary

Business weakness is confirmed where the report classification is
`weakness_observed`. A specific internal root cause is not confirmed by the
available logs and traces. No trace backend was present in the frozen input,
and pending findings must remain subject to human review.

## Boundary

This report is an audit artifact only. It does not update a knowledge base or
promote a pending finding into reusable project knowledge.
