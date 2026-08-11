# LLM Knowledge-Base Selection-Only Ablation Protocol v1

Status: FROZEN for offline selection analysis on 2026-08-10.

## Scope

This protocol isolates the effect of knowledge visibility on LLM candidate selection. ESHOP and SOCIALNET are currently not runtime-executable, so this protocol does not authorize deployment, Chaos injection, or runtime weakness claims.

Arms are paired within the same frozen candidate pool and seed permutation:

- ESHOP: `LLM-blind`, `LLM-generic`, `LLM-partial-pre`.
- SOCIALNET: `LLM-blind`, `LLM-generic`, `LLM-full-pre`.

The ESHOP partial-pre arm must never be merged with SOCIALNET full-pre. Formal pools are the actual frozen universes (ESHOP 40, SOCIALNET 30) and are descriptive rather than preregistered formal-48; pilot pools remain 24 candidates with K=8. Formal selection uses K=10.

## Allowed outcomes

- selected candidate IDs and rank;
- schema validity, duplicate IDs, unknown IDs, and missing selections;
- static protection-oracle class counts and protected-waste;
- static-oracle hit rate and selected-class composition;
- input/output token counts, call count, transport retries, latency, and cost.

## Prohibited claims

No `confirmed_weakness`, Weakness@K, runtime recall, execution invalid-rate, evidence completeness, RCA accuracy, unique issue yield, or end-to-end superiority claim may be produced by this protocol. Runtime results require a separate approved protocol and a passing environment gate.

## Input boundary

LLM bundles contain no `mutation_path`, oracle label, static evidence reference, runtime result, verdict, root cause, or post-hoc experiment field. The original Gate 0-2 artifacts remain immutable; all clean selection-only inputs are written under `knowledge_ablation_selection_only/`.

## Reproducibility

Every selection result must include protocol, bundle, prompt, and candidate-pool SHA-256 values, project, arm, phase, seed, model, endpoint, and status. No API call is run in this repository session until a valid API credential is explicitly available.
