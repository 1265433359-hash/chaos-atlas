# Issue draft: Online Boutique - home page behavior when `productcatalogservice` is unavailable

> Status: DRAFT - review before submission.
> Target: https://github.com/GoogleCloudPlatform/microservices-demo
> Classification: core-path resilience observation / design clarification.

## Title

Online Boutique: home page returns HTTP 500 while productcatalogservice is unavailable

## Summary

The frontend currently treats the product catalog as a hard dependency for rendering the home page. When `productcatalogservice` is unavailable, the request returns HTTP 500 rather than a bounded degraded response or an explicit retryable error. Could you please confirm whether the documented core home journey becoming unavailable during the pod-recreation window is intentional, or whether a more limited degradation is preferred?

## Environment

- Repository: `GoogleCloudPlatform/microservices-demo`
- Commit: `9a4616e7`
- Deployment: isolated `online-boutique-lab` namespace
- Runtime: Kubernetes 1.36.1, Chaos Mesh 2.8.3
- Fault: one `productcatalogservice` pod killed with `PodChaos`

## Evidence

Static inspection identified the product, currency and cart RPCs in the frontend home handler (`frontend/handlers.go:62-90`). RPC failures are routed to the generic HTTP error path (`frontend/rpc.go:30-57`) without a product-catalog fallback or cached response.

Runtime observation:

| Phase | Result |
|---|---|
| Baseline | `GET /` returned HTTP 200 in approximately 25 ms |
| During product catalog pod failure | `GET /` returned HTTP 500 in approximately 9 ms |
| Pod recreation window | HTTP 500 persisted for approximately 1.5-2 minutes |
| After recovery | HTTP 200 and baseline latency returned |

### Additional runtime evidence: packet loss

In a separate controlled experiment on the same pinned commit, 100% packet loss
was applied to `productcatalogservice`. The first `GET /` request remained
pending for approximately 26.7 seconds and then returned HTTP 500. After fault
removal and service recovery, the home page returned to its baseline behavior.

This strengthens the existing observation: the frontend-to-product-catalog path
is fail-closed and does not impose a bounded request deadline on this failure
mode. The 26.7-second value is an experimental observation boundary, not a
production SLO claim.

## Impact

A single dependency failure currently affects the entire home page, including content that might otherwise be served from a cache or rendered with a bounded degraded state. The observed unavailability lasts for the full pod-recreation window rather than being limited to the catalog portion of the response.

## Suggested direction

Depending on the intended demo contract, it may be worth considering one of the following:

1. Return a bounded, explicit degraded response for catalog failures.
2. Serve a small cached product set when the catalog service is unavailable.
3. Add a per-request deadline and document the fail-closed behavior if that is the desired contract.

## Notes

This report does not claim that every frontend component must degrade independently. It reports the current behavior of the documented core home journey and asks whether the fail-closed policy is intentional.
