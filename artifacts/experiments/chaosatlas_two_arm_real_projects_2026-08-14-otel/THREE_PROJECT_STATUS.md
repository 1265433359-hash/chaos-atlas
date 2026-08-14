# Three-Project Two-Arm Status

- `human_review`: `pending`
- `knowledge_base_updated`: `false`

## Online Boutique

Formal comparison complete: 16/16 reports completed. Full had 8 reports with
no observed business impact; ablation had 6 weakness reports and 2 reports
with no observed business impact. All formal reports passed baseline,
injection, recovery, cleanup, and washout checks.

## OpenTelemetry Demo

Formal comparison complete: 48/48 reports completed and strict verification
passed. Full: 10/24 weakness reports and 14/24 no-impact reports. Ablation:
12/24 weakness reports and 12/24 no-impact reports. Discovery completed with
6/6 valid calls. No specific internal mechanism is inferred from these
business-oracle outcomes.

## Sock Shop

Formal comparison complete: 48/48 reports completed after a runner-only
port-forward rebind fix. Full: 11/24 weakness reports and 13/24 no-impact
reports. Ablation: 14/24 weakness reports and 10/24 no-impact reports.
Combined verification passed with 48 reports, including lifecycle, cleanup,
washout, diagnostics, and SHA-256 checks. Global Chaos resource scan was
clear after completion.

The Sock Shop diagnostics provide direct readiness-probe and service-log
evidence for affected runs. The frozen input has no trace backend, so
`zipkin-unavailable.json` is not trace evidence. The observed 500/401,
timeout, and connection-failure outcomes support business-weakness findings,
but do not prove Eureka, cache, registration, discovery, retry, or timeout
mechanisms.

## Overall Issues

1. Business weaknesses are observable in all three real projects under some
   fault hypotheses; the exact internal mechanisms remain pending human review.
2. Sock Shop required a test-harness fix for port-forward rebinding after
   cleanup. The failed pre-fix unit was excluded from final statistics and
   rerun successfully in a new runtime directory.
3. OTel and Sock Shop have no usable trace backend in their frozen inputs, which
   limits mechanism-level root-cause claims.

These documents are audit artifacts only. No pending finding was written to the
knowledge base.
