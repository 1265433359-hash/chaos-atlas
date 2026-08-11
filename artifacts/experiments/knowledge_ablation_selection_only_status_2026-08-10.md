# Selection-Only Ablation Status

Date: 2026-08-10

## Completed

- Created a separate frozen selection-only protocol.
- Derived new versioned bundles and prompts under `knowledge_ablation_selection_only/`.
- Removed `mutation_path` and all oracle/runtime evidence fields from LLM-facing inputs.
- Applied the registered candidate-order permutation independently for all 36 project/arm/phase/seed records.
- Verified 48 generated files and 12 leakage audits; all audits pass.
- Ran selection-only preflight successfully.
- No original Gate 0-2 bundle, candidate pool, snapshot, or mutation YAML was overwritten.
- No LLM call, deployment, Chaos injection, or runtime execution occurred.

## Selection execution result

The corrected run under `selections/run-20260810-r2/` completed all 36 registered selections. Every record is `valid`; the ledger has 36 unique `(project, arm, phase, seed)` keys, with no parser-invalid or transport-failure records. The earlier partial run remains under the original `selections/` directory and is excluded from analysis.

## Scientific status

Static selection metrics are complete and archived in `analysis/selection_only_analysis.md` and `.json`. On SOCIALNET, formal protected-waste is 0.433 for blind, 0.200 for generic, and 0.033 for full-pre. ESHOP has zero protected oracle candidates, so its protected-waste metric is non-informative. Runtime weakness, issue-yield, RCA, and cross-project superiority remain unmeasured because both projects failed the environment gate.

## Reproducibility command

```powershell
python tools/analyze_selection_only_ablation.py
pytest -q --basetemp .pytest-tmp-final-all
```

The selection runner accepts the project-external file `C:\APP\project\deepseek_api_key.txt`; the key is never copied into the repository or result files.
