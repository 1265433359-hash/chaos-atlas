# Held-out Head-to-Head Plan

Objective: test whether the complete Ours pipeline beats ChaosEater on held-out projects without contaminating selection with post-experiment knowledge.

## Gates

| Phase | Scope | Status | Exit condition |
|---|---|---|---|
| P0 | preregister claims, metrics, budgets, failure policy | pending | protocol frozen before Hotel intake results are used |
| P1 | Hotel bring-up and static intake | pending | 2h bring-up, 30min stable observation, two baseline failures => blocked |
| P2 | build and freeze Hotel snapshot | pending | contract/availability/SE/DP/JE provenance and hashes recorded |
| P3 | neutral candidate pool | pending | 30+ candidates, mixed protected/unprotected/unknown, no result-derived filtering |
| P4 | method setup | pending | Ours-full-pre, Ours-generic, CE official, CE adapter, Random definitions frozen |
| P5 | pilot | pending | 24-32 candidates; CE official and baseline gates pass; otherwise blocked |
| P6 | confirmatory comparison | pending | 48-64 candidates across at least 3 held-out projects |
| P7 | analysis and archive | pending | project-clustered CIs, separate coverage/evidence/cost outcomes |

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
