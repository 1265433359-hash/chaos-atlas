# Issue Draft - Sock Shop - single catalogue-db replica removes catalogue availability during pod replacement

> Status: DRAFT - for review before submission. Not yet posted to GitHub.
> Candidate: SS-ISSUE-002
> Classification: resilience/design concern, not a security report.
> Claim boundary: deployment and service boundary only; no source-level bug is claimed.

## Title

Sock Shop: a single catalogue-db replica removes the catalogue endpoint during pod replacement

## Summary

The `catalogue-db` Deployment is configured with one replica. When that
replica is removed, the front-end `/catalogue` business path loses its database
dependency for the replacement window. In the RCA closure run, the singleton
arm produced 54 failed oracle samples out of 65 while no pre-injection Ready
database pod was serving. A counterfactual with two self-seeding replicas kept
the same oracle available for 10 synchronized samples through a surviving Ready
pod.

This draft asks whether the deployment is intended to tolerate routine pod
replacement or node disruption. It does not assert that simply setting
`replicas: 2` is a safe production database architecture.

## Environment

- Repository: Sock Shop deployment used by the isolated ChaosAtlas lab
- Branch / commit pinned: `6e83eb6ffdf1bce43e332337a3bb0fc40327d039`
- Deployment snapshot: `artifacts/sock-shop/catalogue-db-reset.yaml`
- Runtime namespace: `chaosatlas-sock-shop`
- Oracle: front-end `GET /catalogue` via `front-end:80`
- Chaos Mesh version: not captured in the closure artifact

## Evidence

### Static evidence

`artifacts/sock-shop/catalogue-db-reset.yaml:1-9` defines a
`catalogue-db` Deployment with `spec.replicas: 1`. The frozen combined
manifest records the same singleton at
`artifacts/sock-shop/sock-shop-lab-manifest.yaml:208-215`.

### Runtime evidence

| Arm | Baseline | Injected observation | Counterfactual / recovery | Cleanup |
|---|---|---|---|---|
| Singleton (`arm_a`) | `/catalogue` available before injection | 54 failed samples / 65; no pre-injection Ready pod remained serving | Pod replacement completed and the original replica count was restored | `cleanup_errors=[]`, residual PodChaos empty |
| Two replicas (`arm_b`) | `/catalogue` available before injection | 10 defended samples / 65; HTTP 200 persisted through a non-killed Ready pod | Surviving Ready endpoint carried the business path | `cleanup_errors=[]`, restored replicas=1 |

Primary closure artifact:
`artifacts/sock-shop/rca_loop/card-closure/catalogue-db-r2/result.json`.

## Reproduction

1. Deploy the pinned Sock Shop snapshot in an isolated namespace and verify
   repeated successful `GET /catalogue` responses.
2. Confirm `catalogue-db` has one Ready replica.
3. Apply a `PodChaos` `pod-kill` targeting one `catalogue-db` pod and wait for
   `AllInjected` before sampling the business oracle.
4. Record the `/catalogue` response and Ready endpoint set until replacement
   recovery; delete the Chaos resource and verify no residual resource remains.
5. Repeat after an explicitly isolated two-replica counterfactual, retaining
   the same oracle and cleanup checks.

The exact closure manifests and timelines are under
`artifacts/sock-shop/rca_loop/card-closure/catalogue-db-r2/`.

## Impact

- Catalogue browsing can fail while the only database pod is unavailable.
- The observed impact is an availability window; no data-integrity claim is
  made.
- The result is a deployment resilience concern unless single-instance
  operation is an intentional demo/resource trade-off.

## Suggested fix

Please clarify whether the sample deployment promises catalogue availability
through routine pod replacement. If yes, document and implement an appropriate
stateful high-availability design, including replication/storage semantics,
readiness, and a disruption policy. A raw replica-count increase should not be
treated as a database failover design without those checks. If singleton
operation is intentional, document the expected outage explicitly.

## Notes

- The RCA card is `KB-RCA-sock-shop-catalogue-catalogue-db-podchaos-pod-kill`.
- The RCA status is bounded and the knowledge card is local-reusable; this is
  not evidence of a source-level timeout or fallback defect.
- Sock Shop is archived, so this draft may be better treated as a design
  clarification than as a request for active maintenance.

