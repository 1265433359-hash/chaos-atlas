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
- SE/DP/JE scanned at pinned file versions: 0 direct-text occurrences of DeathStarBench/Hotel/SOCIALNET/MEDIA/social/media. This is a clean direct-evidence scan, not proof that every abstract rule is implementation-independent.
- ESHOP leakage risk = low (different stack/repo); SOCIALNET/MEDIA = medium (structural infra sharing: dialer/registry/tracing), controlled by stripping rules (rebuild project-specific contracts from own source; re-verify shared infra; separate generic vs project-specific provenance).
- Current protocol conservatively chooses one of SOCIALNET and MEDIA for the comparable denominator because they share DeathStarBench infrastructure; including both would require a pre-registered project-cluster analysis.

2026-08-10 (Stage C audit correction):
- ESHOP and SOCIALNET source commits are fixed, but both pre-snapshots remain blocked because the deployment availability evidence is incomplete. ESHOP has no compose/Kubernetes manifest; SOCIALNET Compose is known but Helm availability is not yet verified per file.
- ESHOP currently has two source-verified contract edges; SOCIALNET has seven ComposePost edges. Candidate capacity remains unknown until the edge inventories and deployment targets are expanded and verified.
- Snapshot builder now locks SE/DP/JE with full SHA-256 values and records a separate availability scope; no runtime or experiment result was added.

2026-08-10 (Stage C2 audit correction):
- SOCIALNET Helm availability is verified for the recorded service targets. The valid snapshot contains 9 contract edges with complete source SHA; 3 discovered edges remain explicitly excluded in `unverified_contract_edges` until their individual source files are hashed.
- `full_pre=true` is therefore scoped to the verified 9-edge contract, not a claim that all discovered SOCIALNET edges are frozen.

2026-08-10 (new candidate search):
- `DescartesResearch/TeaStore` is the leading replacement for blocked ESHOP: independent Apache-2.0 repository, fixed candidate commit `34b37f7e7be433ce72d5f9455e66922a13116749`, explicit Helm/Kubernetes/Compose assets, five services plus registry, and zero direct hits in pinned SE/DP/JE files.
- TeaStore remains conditional until approved static intake confirms service graph, timeout semantics, probes/PDB/HPA, images, observability, and pilot/formal candidate capacity.

2026-08-10 (TeaStore C3 audit correction):
- TeaStore snapshot provenance paths were corrected from `utilities/...` placeholders to exact repository paths.
- Ribbon retry count is verified, but timeout milliseconds are unknown; retries alone do not establish `loss_bounded`. TeaStore contract edges retain `loss_bounded=false` and protected status unknown.

2026-08-10 (Stage D candidate-pool freeze):
- Neutral generation from frozen snapshots only; protection class is a pure static, project-agnostic function of the contract edge (explicit_timeout+delay=protected; loss on explicit_timeout=unknown; retry_policy_timeout_unknown=unknown; no_timeout=unprotected; kill on single-replica no-PDB=unprotected).
- Quota arithmetic is decisive: 3 comparable snapshots do NOT imply 24/48 legal candidates per project. HOTEL has no protected/unknown static evidence (5 no_timeout edges + 8 no-PDB deployments); TEASTORE has no protected evidence (4 retry-only edges + 7 deployments); SOCIALNET has 9 protected-able edges + 9 unknown-able edges but only 12 kill targets -> formal unprotected quota (16) is unsatisfiable. Pools freeze at the legally reachable size; shortfalls are reported, not padded.
- SOCIALNET pilot (8/8/8 = 24) is the only full-quota pool; its kill targets reuse the committed knowledge-ablation template labels (verified selector evidence). HOTEL/TEASTORE app labels are convention-based and are pre-registered for confirmation at the Stage F deployment gate.
- 135 YAMLs, registry and freeze artifacts are hash-locked; candidate_map remains empty; blind ranking is null (Stage D runs no selection). ESHOP stays excluded (blocked, no k8s target).
- Risk for P4: formal pools 16/44/23 are not comparable in size; any cross-method Weakness@K comparison must be per-selection-budget (K), not per-pool-size, and the shortfalls must be adjudicated before P5 pilot.

## Parallel v1.2 decision

- v1.1 remains the strict protocol and is not edited or reinterpreted.
- v1.2 changes only the eligibility estimand: pooled class quotas with project as the inference cluster and equal project weight.
- Existing formal pool counts recompute to 16 protected, 35 unprotected, 32 unknown, and 83 legal candidates across Hotel, SOCIALNET, and TeaStore.
- Protected candidates occur in SOCIALNET only; protected-specific claims are descriptive_only until a second project contributes that class.
- A fresh v1.2 registry must still be frozen after amendment approval. The current feasibility report is not an execution authorization.
