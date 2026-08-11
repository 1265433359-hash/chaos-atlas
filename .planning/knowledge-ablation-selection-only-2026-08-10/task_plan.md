# Knowledge Ablation Selection-Only Plan

Objective: complete the knowledge-base ablation without claiming runtime fault-discovery evidence while ESHOP and SOCIALNET are environment-blocked.

| Phase | Scope | Status | Exit condition |
|---|---|---|---|
| S0 | Preserve current audit and freeze boundary | completed | Existing pools, snapshots, prompts, and mutation YAMLs are hash-verified and untouched |
| S1 | Amend protocol to selection-only | completed | Amendment explicitly excludes runtime/Weakness@K claims |
| S2 | Validate arm inputs and leakage | completed | 36 records, 12 audits, and seed permutations pass |
| S3 | Execute offline selection | completed | 36/36 selection records valid; ledger keys unique; no parser or transport failures |
| S4 | Static-oracle analysis | completed | Static protected-waste, unprotected-selection, paired deltas, tokens, and latency archived |
| S5 | Report and claim matrix | completed | Status and claim matrix state limits and no runtime discovery claim |
| S6 | Optional runnable-project feasibility | completed (blocked) | TeaStore read-only feasibility report archived; runtime entry remains blocked until Docker/Kubernetes access is available |

## Hard boundaries

- No Docker, kind, WSL, Kubernetes, Chaos Mesh, or runtime injection in S0-S5.
- No LLM API call unless the human explicitly authorizes S3.
- Frozen candidate pools and mutation YAMLs are immutable in this branch of work.
- ESHOP third arm is `LLM-partial-pre`; SOCIALNET third arm is `LLM-full-pre`.
- Results are selection-only and cannot support Weakness@K, recall, RCA, unique issue yield, or cross-project superiority.
