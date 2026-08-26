# Issue Draft - Sock Shop - catalogue transport abort propagates to the front-end without graceful degradation

> Status: DRAFT - for review before submission. Not yet posted to GitHub.
> Candidate: SS-ISSUE-003
> Classification: resilience/design concern; source-level mechanism not established.

## Title

Sock Shop: catalogue transport abort propagates to the front-end without a graceful response contract

## Summary

When the `front-end -> catalogue` HTTP response is aborted, the front-end
business oracle returns HTTP 500 during the fault window. The RCA closure run
observed 68 failure samples, all with status code `500`, and left no residual
HTTPChaos resource after cleanup. The evidence confirms propagation at the
measured service boundary; it does not identify a missing timeout, retry, or
fallback in source code.

This draft asks whether the demo intends to expose a hard 500 when catalogue is
unavailable, or whether a documented degraded response is expected.

## Environment

- Repository: Sock Shop deployment used by the isolated ChaosAtlas lab
- Branch / commit pinned: `6e83eb6ffdf1bce43e332337a3bb0fc40327d039`
- Runtime namespace: `chaosatlas-sock-shop`
- Target edge: `front-end -> catalogue`, HTTP `/catalogue`
- Business oracle: front-end `GET /`
- Chaos Mesh version: not captured in the closure artifact

## Evidence

### Static evidence

The route-aware mutation is recorded in
`artifacts/experiments/chaosatlas_sockshop_yaml_confidence_2026-08-15-r5-r4/runtime-remaining-route-aware-2026-08-15-r1/methods/native-full/mutations/yc-sock-http-abort-catalogue-df420e4b.yaml`.
No source-level timeout or fallback mapping was archived; this draft does not
claim one.

### Runtime evidence

| Phase | Result |
|---|---|
| Baseline | Front-end business oracle available before injection |
| Injected | 68 samples observed; failure status code set was `500` |
| Recovery / cleanup | HTTPChaos deleted; residual HTTPChaos was empty; run error was null |

Primary closure artifact:
`artifacts/sock-shop/rca_loop/card-closure/http-abort-r1/result.json`.

## Reproduction

1. Deploy the pinned snapshot in an isolated namespace and verify successful
   repeated `GET /` requests.
2. Apply the route-aware HTTP abort mutation on the `front-end -> catalogue`
   edge and wait for confirmed injection before sampling.
3. Record the front-end response contract during the abort window.
4. Remove the HTTPChaos resource, verify it is absent, and confirm the
   baseline response contract returns.

The closure timeline and injection status are under
`artifacts/sock-shop/rca_loop/card-closure/http-abort-r1/`.

## Impact

- Catalogue-dependent front-end requests can return HTTP 500 while the
  downstream response is aborted.
- No data-integrity or permanent recovery failure was observed.
- The severity depends on whether the project considers a degraded catalogue
  response preferable to a hard error.

## Suggested fix

Please clarify the intended response contract for catalogue unavailability. If
the project wants graceful degradation, consider a bounded caller timeout and
an explicit fallback/error response that does not hang or surface an opaque
500. The exact implementation should be chosen from the source and project
contract; this report does not prescribe a retry or circuit-breaker mechanism.

## Notes

- RCA card: `KB-RCA-sock-shop-front-end-catalogue-httpchaos-abort`.
- The card is local-reusable but remains bounded at the service boundary.
- Hold this draft as evidence-only if the archived demo intentionally exposes
  the downstream failure and has no resilience promise.

