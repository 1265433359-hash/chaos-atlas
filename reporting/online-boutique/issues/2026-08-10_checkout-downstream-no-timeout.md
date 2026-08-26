# Issue draft: Online Boutique - Checkout timeout behavior under downstream delay

> Status: DRAFT - review before submission.
> Target: https://github.com/GoogleCloudPlatform/microservices-demo
> Classification: resilience improvement / design clarification.

## Title

Online Boutique: Checkout waits for delayed or unavailable payment, shipping, and email services

## Summary

The checkout service forwards the request context directly to several downstream calls without an application-level timeout, retry budget or fallback on the examined path. In our test, a delayed payment request added nearly its full delay to the end-to-end order path, while a complete loss caused the order request to wait until the external client deadline. Could you confirm whether this behavior is intentional for the demo contract?

## Environment

- Repository: `GoogleCloudPlatform/microservices-demo`
- Commit: `9a4616e7`
- Deployment: isolated `online-boutique-lab` namespace
- Runtime: Kubernetes 1.36.1, Chaos Mesh 2.8.3
- Workload: `PlaceOrder`

## Evidence

Static inspection found direct context propagation in `checkoutservice/main.go` around the payment, shipping and email calls (`main.go:252`, `main.go:380`, `main.go:387`), without a per-call `WithTimeout` or `WithDeadline`.

Runtime observation:

| Fault | Baseline | Observed behavior |
|---|---:|---|
| Payment delay, 2 s | approximately 17 ms | `PlaceOrder` approximately 2019 ms; delay propagated nearly 1:1 |
| Payment loss, 100% | approximately 17-23 ms | request waited approximately 10,008 ms and ended with `DEADLINE_EXCEEDED` |
| Recovery | baseline restored | service returned to approximately 17-23 ms after cleanup |

### Additional runtime evidence: shipping double-call and delay accumulation

The `PlaceOrder` path invokes `shippingservice` twice: once for `GetQuote` and
once for `ShipOrder`. With a 2-second delay injected into `shippingservice`, the
total `PlaceOrder` latency increased to approximately 4021.5 ms from a baseline
of about 17 ms.

With simultaneous 2-second delays on `paymentservice` and `emailservice`, the
end-to-end latency was approximately 4016.2 ms, showing that synchronous
downstream delays accumulate across the checkout path.

These are controlled experiment measurements, not production SLO claims. The
main question is whether each dependency should have an explicit deadline and
whether the non-critical email operation should be asynchronous or best-effort.

## Impact

The checkout path may retain request, goroutine and connection resources while waiting for an unavailable dependency. Under concurrent failures, this could increase queueing and make unrelated orders more likely to reach their client deadlines.

## Suggested direction

It may be worth considering the following, depending on the intended demo contract:

1. Define explicit per-dependency deadlines and bounded failure handling for payment, shipping and email.
2. Use an asynchronous or best-effort path for the non-critical email side effect.
3. If the current behavior is intentional for this demo, document the absence of application-level deadlines so that the resilience contract is explicit.

## Notes

The client deadline used in this experiment is a measurement boundary, not a production SLO. The issue is the absence of an application-level bound, not a claim that the project violates a particular production latency target.
