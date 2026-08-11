# Issue Submission Index

These drafts are based on pinned commits and isolated runtime evidence. They are not submitted automatically.

## Recommended order

| Priority | Project | Draft | Classification | Recommendation |
|---|---|---|---|---|
| P0 | Online Boutique | `reporting/online-boutique/issues/2026-08-10_productcatalog-core-path-no-degradation.md` | Core-path resilience observation | Ask whether the fail-closed behavior is intentional |
| P0 | Train Ticket | `reporting/train-ticket/issues/2026-08-05_disabled-downstream-call-in-refresh.md` | Potential correctness and benchmark-integrity concern | Ask for design clarification |
| P1 | OpenTelemetry Demo | `reporting/opentelemetry-demo/issues/2026-08-09_quote-shipping-error-message.md` | Confirmed error-message mismatch | Submit as a focused normal issue |
| P1 | Train Ticket | `reporting/train-ticket/issues/2026-08-05_station-no-timeout-defense.md` | Application timeout/resilience concern | Submit with explicit SLO caveat |
| P2 | Online Boutique | `reporting/online-boutique/issues/2026-08-10_checkout-downstream-no-timeout.md` | Design/resilience improvement opportunity | Ask whether behavior is intentional |
| P2 | Online Boutique | `reporting/online-boutique/issues/2026-08-10_payment-probe-too-aggressive.md` | Probe configuration observation | Optional; request owner confirmation |

## Do not submit as bugs

- Sock Shop single-replica/no-PDB findings: the repository is archived and these are largely known demo design choices.
- Docker Desktop/WSL2 `ebtables` failures: environment prerequisites, not project defects.
- Local image-build and manifest adaptation fixes: lab integration work, not upstream issues.

## Common submission rules

- Pin the repository commit and include only non-sensitive evidence.
- Keep runtime values as observed measurements, not production SLO claims.
- Label resilience findings as concerns or improvements when the project documentation does not promise stronger behavior.
- Do not combine multiple root causes into one issue unless they share one fix.
