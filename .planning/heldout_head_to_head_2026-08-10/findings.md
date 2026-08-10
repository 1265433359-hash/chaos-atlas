# Findings

## Current evidence

- Existing TT/OB/OTEL/Sock results do not establish overall superiority over ChaosEater.
- OB r2 has a saturated weakness pool and no useful selector separation.
- Sock frozen engine replay is correctly blocked because SE/DP/JE lack a clean pre-Sock snapshot.
- The strongest current differentiator is evidence quality: measurement position, lifecycle evidence, RCA anchoring and auditability.

## Risks to prevent

- A held-out project is not knowledge-free: source and manifest intake must happen before snapshot freeze.
- An empty contract is an ablation, not the complete method.
- Weakness@K, evidence completeness and cost measure different things and must be reported as separate endpoints.
- Candidate-level confidence intervals must account for project clustering; two projects are replication evidence, not strong generalization proof.

## Current execution gate

- Protocol v1.1 fixes `pilot K=8`, `formal K=10`, exact candidate pools of 24/48 per project, method-to-seed mapping, deterministic within-project aggregation, and a minimum of 3 comparable projects.
- Hotel is still `go_no_go=blocked`; no P2 snapshot should be created until a real source/manifest path is supplied or restricted download is approved.
- A cross-project superiority claim requires 3 comparable projects after excluding CE `environment_blocked` projects from the comparison denominator. One Hotel project can only produce descriptive evidence.

2026-08-10 Hotel intake additions:
- Canonical source confirmed: delimitrou/DeathStarBench @ 6ecb0970, hotelReservation/ subproject (GPL-2.0).
- 10 business services; edges frontend->search/profile/recommendation, search->geo/rate (gRPC, no per-request timeout observed); dialer 120s dial timeout is connection-level (not a per-request contract - same class as OB productcatalog).
- compose single-replica (no PDB at compose level); kubernetes/ manifest replicas/PDB not yet verified per-file -> hotel snapshot status=blocked (provenance_completeness=partial).
- Isolation warning: DeathStarBench subprojects share dialer/registry/tracing patterns; if SE/DP/JE already encode these, SOCIALNET/MEDIA as held-out require intake-time cross-check (same posthoc lesson as Sock).
