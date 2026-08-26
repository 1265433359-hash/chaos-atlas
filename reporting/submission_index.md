# Issue Submission Index

These drafts are based on pinned commits and isolated runtime evidence. They are not submitted automatically.

## Submitted issues

| Project | Issue | Status |
|---|---|---|
| OpenTelemetry Demo | [open-telemetry/opentelemetry-demo#3818](https://github.com/open-telemetry/opentelemetry-demo/issues/3818) `OpenTelemetry Demo: shipping quote failure reports "email service" instead of "shipping service"` | open |
| Train Ticket | [FudanSELab/train-ticket#311](https://github.com/FudanSELab/train-ticket/issues/311) `Train Ticket: station lookup exceeds the client timeout under a 3-second outbound delay` | open |
| Train Ticket | [FudanSELab/train-ticket#310](https://github.com/FudanSELab/train-ticket/issues/310) `Train Ticket: /order/refresh may skip the ts-order-service to ts-station-service station-name lookup` | open |
| Online Boutique | [GoogleCloudPlatform/microservices-demo#3475](https://github.com/GoogleCloudPlatform/microservices-demo/issues/3475) `Online Boutique: paymentservice probe restarts the container after a 2-second delay` | open |
| Online Boutique | [GoogleCloudPlatform/microservices-demo#3474](https://github.com/GoogleCloudPlatform/microservices-demo/issues/3474) `Online Boutique: Checkout waits for delayed or unavailable payment, shipping, and email services` | open |
| Online Boutique | [GoogleCloudPlatform/microservices-demo#3473](https://github.com/GoogleCloudPlatform/microservices-demo/issues/3473) `Online Boutique: home page returns HTTP 500 while productcatalogservice is unavailable` | open |

## Drafts not yet submitted

| Project | Draft | Status |
|---|---|---|
| OpenTelemetry Demo | `reporting/opentelemetry-demo/issues/2026-08-23_emailservice-blocks-placeorder.md` | draft / not-submitted |
| Sock Shop | `reporting/sock-shop/issues/2026-08-24_front-end-single-replica-availability-degradation.md` | draft / not-submitted; review pack SS-ISSUE-001 |
| Sock Shop | `reporting/sock-shop/issues/2026-08-24_catalogue-db-single-replica-catalogue-outage.md` | draft / not-submitted; review pack SS-ISSUE-002 |
| Sock Shop | `reporting/sock-shop/issues/2026-08-24_front-end-catalogue-abort-no-graceful-degradation.md` | draft / not-submitted; review pack SS-ISSUE-003 |

## Recommended order

| Priority | Project | Draft | Classification | Recommendation |
|---|---|---|---|---|
| P0 | Online Boutique | `reporting/online-boutique/issues/2026-08-10_productcatalog-core-path-no-degradation.md` | Core-path resilience observation | Ask whether the fail-closed behavior is intentional |
| P0 | Train Ticket | `reporting/train-ticket/issues/2026-08-05_disabled-downstream-call-in-refresh.md` | Potential correctness and benchmark-integrity concern | Ask for design clarification |
| P1 | OpenTelemetry Demo | `reporting/opentelemetry-demo/issues/2026-08-09_quote-shipping-error-message.md` | Confirmed error-message mismatch | Submit as a focused normal issue |
| P1 | OpenTelemetry Demo | `reporting/opentelemetry-demo/issues/2026-08-23_emailservice-blocks-placeorder.md` | Checkout resilience concern | Ask whether synchronous email behavior is intentional |
| P1 | Train Ticket | `reporting/train-ticket/issues/2026-08-05_station-no-timeout-defense.md` | Application timeout/resilience concern | Submit with explicit SLO caveat |
| P2 | Online Boutique | `reporting/online-boutique/issues/2026-08-10_checkout-downstream-no-timeout.md` | Design/resilience improvement opportunity | Ask whether behavior is intentional |
| P2 | Online Boutique | `reporting/online-boutique/issues/2026-08-10_payment-probe-too-aggressive.md` | Probe configuration observation | Optional; request owner confirmation |
| Review | Sock Shop | `reporting/sock-shop/ISSUE_REVIEW.md` | Three bounded resilience/design candidates | User must choose approve-draft, revise, hold-evidence-only, or reject-design-choice |

## Do not submit as bugs

- Sock Shop single-replica/no-PDB findings: the repository is archived and these are largely known demo design choices.
- Docker Desktop/WSL2 `ebtables` failures: environment prerequisites, not project defects.
- Local image-build and manifest adaptation fixes: lab integration work, not upstream issues.

## Common submission rules

- Pin the repository commit and include only non-sensitive evidence.
- Keep runtime values as observed measurements, not production SLO claims.
- Label resilience findings as concerns or improvements when the project documentation does not promise stronger behavior.
- Do not combine multiple root causes into one issue unless they share one fix.
