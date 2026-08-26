# Issue draft - OpenTelemetry Demo - emailservice blocks PlaceOrder

> Status: DRAFT - for review before submission. Not yet posted to GitHub.
> Target: https://github.com/open-telemetry/opentelemetry-demo
> Submission channel: normal issue (this is a resilience/design concern, not a security report).
> Confidence: HIGH - static source inspection and repeated isolated runtime experiments.

## Title

OpenTelemetry Demo: unavailable emailservice blocks PlaceOrder until the caller deadline

## Summary

The checkout service performs the order-confirmation email request synchronously.
Although email failures are logged as warnings, the HTTP client has no explicit
request timeout. When `emailservice` was subjected to 100% packet loss,
`PlaceOrder` waited until the external 10-second deadline and failed with
`DEADLINE_EXCEEDED`.

This behavior was reproduced in all 6 formal replicates.

Could the email notification be given an explicit bounded timeout or moved to an
asynchronous/best-effort path so that an unavailable email service does not block
the primary order workflow?

## Environment

- Repository: `open-telemetry/opentelemetry-demo`
- Commit: `2e72d8bcdf754603e956406808630bc9663c992c`
- Namespace: `chaosatlas-otel`
- Kubernetes: `1.36.1`
- Chaos Mesh: `2.8.3`
- Workload: `PlaceOrder`

## Evidence

Static inspection:

- `src/checkout/main.go:212`: the checkout HTTP client is constructed without
  an explicit `Timeout`.
- `src/checkout/main.go:403-404`: email request failures are logged as a
  warning after the request returns.
- `sendOrderConfirmation` is called synchronously as part of the order flow.

Runtime observation:

- A `NetworkChaos` fault applying 100% packet loss to `emailservice` caused
  `PlaceOrder` deadline failures in all 6 formal replicates.
- The formal review classified the email fault as `weakness_observed` for 3/3
  seeds and 6/6 replicates.

## Impact

The non-critical order-confirmation email dependency can block the primary order
workflow while it is unavailable. Under concurrent failures, this may retain
request resources and cause otherwise valid orders to reach their caller
deadline.

## Suggested direction

Depending on the intended demo contract, it may be worth considering:

1. Add an explicit bounded timeout for the email request.
2. Run order confirmation asynchronously or as a best-effort side effect.
3. Document the current synchronous behavior if it is intentional.

## Notes

The 10-second value is the experimental client deadline, not a production SLO.
This report does not claim a specific retry, cache, service-discovery, or
circuit-breaker root cause. It reports the observed synchronous dependency
behavior and asks whether the resilience contract is intentional.
