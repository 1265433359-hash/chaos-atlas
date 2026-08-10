# Stage D: Neutral Candidate Pool Freeze (P3)

> frozen_at: 2026-08-10T08:05:07.628538+00:00
> rule_version: heldout-candidate-generation-v1
> seed: heldout-stage-d-v1
> generator: tools/build_heldout_candidate_pools.py (sha256 a137e553e95a238c…)

## Status

**frozen_with_quota_shortfalls** — no experiment, selection, deployment or injection ran. Candidate pools are generated purely from the frozen knowledge snapshots with a fixed neutral parameter ladder; quota shortfalls are reported, never padded.

## Per-project pools (pilot 24 / formal 48 target)

| project | pilot | protected | unprotected | unknown | formal | protected | unprotected | unknown | status |
|---|---|---|---|---|---|---|---|---|---|
| HOTEL | 8 | 0 | 8 | 0 | 16 | 0 | 16 | 0 | blocked_for_formal |
| SOCIALNET | 24 | 8 | 8 | 8 | 44 | 16 | 12 | 16 | blocked_for_formal |
| TEASTORE | 15 | 0 | 7 | 8 | 23 | 0 | 7 | 16 | blocked_for_formal |

### Quota shortfalls (never padded)

- **HOTEL pilot**: protection-class quota shortfall: protected=0/8, unknown=0/8; pool size 8 < budget 24
- **HOTEL formal**: protection-class quota shortfall: protected=0/16, unknown=0/16; pool size 16 < budget 48
- **SOCIALNET formal**: protection-class quota shortfall: unprotected=12/16; pool size 44 < budget 48
- **TEASTORE pilot**: protection-class quota shortfall: protected=0/8, unprotected=7/8; pool size 15 < budget 24
- **TEASTORE formal**: protection-class quota shortfall: protected=0/16, unprotected=7/16; pool size 23 < budget 48

### Fault-family presence (full pools)

| project | delay | loss | kill |
|---|---|---|---|
| HOTEL | ✓ | ✓ | ✓ |
| SOCIALNET | ✓ | ✓ | ✓ |
| TEASTORE | ✓ | ✓ | ✓ |

### Exclusions

| project | reason |
|---|---|
| ESHOP | snapshot blocked (no k8s/compose deployment target); not comparable |
| SOCIALNET | 3 unverified_contract_edges excluded from the contract pool (UserTimeline->PostStorage, User->SocialGraph, SocialGraph->User) |
| HOTEL | REVIEW/ATTRACTIONS have no k8s deployment (availability unavailable) |

### Frozen hashes

| artifact | sha256 |
|---|---|
| HOTEL snapshot | `396f5e7470717b9481eab8d0621b462ac02165990dea39cad5adf6c69b0bff25` |
| HOTEL pilot pool | `e7c9f837b789a7fe7d6c629cae511a2b2ebb814e640eb3b4d4a96727a1a3d6ca` |
| HOTEL formal pool | `5ee28c27e5bd6c6492d9777573097649ff6d484d38345fa13a0df0314b2a0725` |
| SOCIALNET snapshot | `e8cf58f89dc32aa22b06b5e36e82f17e6dc82cfaba31fd6637a61893ccfa0608` |
| SOCIALNET pilot pool | `78279102b9301452064bf10d0717c8cabd3ca4736edb588dd018bcd9e2badea8` |
| SOCIALNET formal pool | `e477620e1057e0e20868bdf828f68dd84cea7a21cba1af47bb5538cec9948d68` |
| TEASTORE snapshot | `339dd2203508ba6bc40e49057febdcf3b5a2fc73bc8e3fdd536554600fd8b9d2` |
| TEASTORE pilot pool | `c2c2c7f689921af6e4267520c428d7d5d62f9d77a694a6fd0dfba2cbaa530f62` |
| TEASTORE formal pool | `5a3ee028a612d991e0af49bdf173779e574262e72dd21cf2a81813ea0cdc1143` |
| candidate_pool_registry.json | `aa4b6910e9c2b62cf2c41704bd91ffb3dcdea12502f6a1b1a97cc9e56d7feb56` |

### Declarations

- candidate_map in all three snapshots is still empty.
- blind_ranking: null (no selection executed in Stage D).
- No cluster started, no deployment, no injection, no ChaosEater/Ours/Random run, no pilot/formal run.
- SOCIALNET 3 unverified edges excluded; TeaStore retry-only edges are `unknown` (never protected); HOTEL REVIEW/ATTRACTIONS excluded (no k8s deployment).
- protocol v1.1 and the three knowledge snapshots are untouched by this stage.
- Stage E must register the HOTEL/SOCIALNET/TEASTORE prefixes in project_registry before any decision_engine selection; candidate ids use single-project-prefix syntax ('<PROJECT>-<src>-<dst>-<FAULT>-<param>', e.g. HOTEL-frontend-search-DELAY-500) so normalize_service()/fault_of() keep working.
