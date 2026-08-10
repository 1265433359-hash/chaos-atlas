# Held-out Head-to-Head Plan

Objective: test whether the complete Ours pipeline beats ChaosEater on held-out projects without contaminating selection with post-experiment knowledge.

## Gates

| Phase | Scope | Status | Exit condition |
|---|---|---|---|
| P0 | v1.1 claims, metrics, budgets, failure policy | complete | v1.1 corrected; K, seeds, aggregation and blocked denominator fixed |
| P1 | Hotel read-only intake | complete | canonical source/commit fixed; static intake recorded; runtime gates remain not_run |
| P1b | held-out project set | complete (conditional) | ESHOP+SOCIALNET selected; comparable count remains conditional on intake/deployment gates |
| P2 | static intake and frozen snapshots | in_progress | Hotel valid; ESHOP/SOCIALNET intake recorded but snapshots blocked until deployment availability and contract coverage are complete |
| P3 | neutral candidate pools | pending | pilot=24 and formal=48 per project; fixed quotas; no result-derived filtering |
| P4 | method setup | pending | five method IDs, seed mapping, runner, cleanup and blindness frozen |
| P5 | pilot | pending | each project passes bring-up/baseline gates with K=8; otherwise that project is blocked |
| P6 | confirmatory comparison | pending | at least 3 comparable projects, 48 candidates/project, K=10 |
| P7 | analysis and archive | pending | project-clustered CIs, separate coverage/evidence/cost outcomes, claim matrix updated |

## Immediate decision gate

Do not start P3, P5 or P6 until ESHOP/SOCIALNET snapshots are valid and their verified contract edge inventories can support the registered candidate quotas. Hotel REVIEW/ATTRACTIONS Kubernetes-specific candidates remain unavailable. A blocked CE line cannot be replaced by deleting its candidates and cannot count as a win.

## Required method lines

1. Equal-information: all methods receive the same candidate metadata.
2. Realistic end-to-end: Ours-full-pre uses its frozen intake and knowledge assets; ChaosEater uses its standard pipeline.
3. Ours-generic ablation: empty project-specific contract, generic SE/DP/JE only.
4. CE official and CE adapter remain separate; Random is a baseline only.

## Hard rules

- Freeze code, candidate IDs, inputs, budgets, seeds, runner, cleanup and analysis before selection.
- Project-specific static contract/availability analysis is allowed before freeze; experiment results are not.
- Never call an empty-contract run Ours-full; label it Ours-generic.
- Equal-weight composite scores are prohibited unless justified and frozen before data collection.
- Environment-blocked CE is not an algorithm win; report it separately.
- No superiority claim from a single Hotel project.

## Parallel v1.1 / v1.2 track (2026-08-10)

| Phase | Scope | Status | Exit condition |
|---|---|---|---|
| V12-0 | Define pooled estimand without changing v1.1 | complete | v1.2 MD/JSON records coexistence and separate denominators |
| V12-1 | Read-only pooled feasibility check | complete | Hotel/SOCIALNET/TeaStore recompute to 16/35/32/83 |
| V12-2 | Amendment review and approval | complete | user approved v1.2 on 2026-08-10 |
| V12-3 | Fresh v1.2 candidate registry freeze | complete | 83 unique candidates; source/protocol hashes locked |
| V12-4 | v1.2 method/runner configuration freeze | in_progress | method IDs, seeds, redaction and lifecycle frozen; common runner still required |
| V12-5 | v1.2 pilot/formal execution | pending | only after common runner and CE gates pass |

v1.1 remains frozen and may proceed only with its per-project quotas. v1.2 uses pooled quotas and project-equal inference; neither protocol may relabel the other's results.
