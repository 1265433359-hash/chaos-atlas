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

## Audit corrections after Hotel intake

- Hotel Compose single-replica facts are scoped to Compose only; they must not be reused as Kubernetes replicas/PDB facts.
- Hotel source paths whose external WSL contents cannot be read are explicitly `unavailable`; no hash is guessed. The snapshot remains blocked until those files are verified.
- The current Hotel candidate map is empty. A static claim of 30+ candidates is not evidence; P3 must generate and freeze the exact pool before any selection.
- `build_hotel_knowledge_snapshot.py` now pins the three knowledge-library hashes and refuses to rebuild from drifted live files.
- Stage A2 verified 8 Kubernetes business deployments; REVIEW and ATTRACTIONS have no deployment YAML and remain unavailable for Kubernetes-specific candidates. The snapshot is valid only with that explicit scope.

2026-08-10 Hotel intake additions:
- Canonical source confirmed: delimitrou/DeathStarBench @ 6ecb0970, hotelReservation/ subproject (GPL-2.0).
- 10 business services; edges frontend->search/profile/recommendation, search->geo/rate (gRPC, no per-request timeout observed); dialer 120s dial timeout is connection-level (not a per-request contract - same class as OB productcatalog).
- compose single-replica (no PDB at compose level); kubernetes/ manifest replicas/PDB not yet verified per-file -> hotel snapshot status=blocked (provenance_completeness=partial).
- Isolation warning: DeathStarBench subprojects share dialer/registry/tracing patterns; if SE/DP/JE already encode these, SOCIALNET/MEDIA as held-out require intake-time cross-check (same posthoc lesson as Sock).

2026-08-10 (Stage B) leakage audit:
- SE/DP/JE scanned: 0 occurrences of DeathStarBench/Hotel/SOCIALNET/MEDIA/social/media across all three libraries. Knowledge base baseline is clean for DeathStarBench family.
- ESHOP leakage risk = low (different stack/repo); SOCIALNET/MEDIA = medium (structural infra sharing: dialer/registry/tracing), controlled by stripping rules (rebuild project-specific contracts from own source; re-verify shared infra; separate generic vs project-specific provenance).
- SOCIALNET and MEDIA cannot both count toward the comparable denominator (same DeathStarBench infra family) - choose one.
