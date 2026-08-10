# v1.2 Method and Execution Freeze

Status: `dry_run_runner_implemented_adapters_pending`
Freeze date: 2026-08-10

The v1.2 method IDs, K budgets, numeric seeds, comparison lines, blindness fields, lifecycle, cleanup contract, and environment gates are now frozen. The candidate registry and freeze snapshot are the input references.

## Methods

| Method | Selection replicates | Seeds |
|---|---:|---|
| Ours-full-pre | 1 | deterministic seed `0` |
| Ours-generic | 1 | deterministic seed `0` |
| ChaosEater-official | 3 | pilot `1001-1003`, formal `2001-2003` |
| ChaosEater-adapter | 3 | pilot `1001-1003`, formal `2001-2003` |
| Random | 20 | pilot `3001-3020`, formal `4001-4020` |

Pilot uses `K=8`; formal uses `K=10`; each selected candidate has at most two confirmation runs. `Weakness@K` counts candidate IDs, not confirmations.

## Blinding

Equal-information views share candidate ID, project, edge, target, fault family, and fault parameters. Protection class, availability evidence, contract hashes, and snapshot provenance are redacted from that shared view. The same candidate order permutation is used for paired method-seed comparisons. Realistic end-to-end views use each method's declared knowledge tier.

## Runner gate

The repository now has a common read-only dry-run entrypoint at `tools/heldout_v12_runner.py`. It accepts project, method, phase, seed, candidate, and output directory; validates the frozen registry/YAML/SHA; and emits the frozen lifecycle schema without calling `kubectl` or Chaos Mesh. A project adapter is still required before execution. The eventual adapter-backed runner must execute preflight, baseline, one fault, observation, recovery, deletion, cleanup assertion, and ledger writing. Network faults are `NetworkChaos mode=one`; kills are `PodChaos mode=one`.

No run may start until this runner contract is implemented and validated. Cleanup failure invalidates a run; changing business code, changing frozen YAML, reselection from results, or selective cleanup is forbidden.

Environment gates remain project bring-up <=2h, stable observation 30min, two consecutive baseline failures => `environment_blocked`, and CE official bring-up <=4h. CE blocked is never superiority.

No cluster, deployment, selection, injection, pilot, or formal execution has started.
