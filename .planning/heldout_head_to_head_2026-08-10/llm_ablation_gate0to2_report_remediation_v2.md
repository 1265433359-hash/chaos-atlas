# LLM Knowledge-Base Ablation — Gate 0–2 Review Package (Remediation v2)

> Date: 2026-08-10
> Protocol: `artifacts/experiments/llm_knowledge_ablation_protocol_v1.md` (SHA-256 `9dc24410830ac894326a0fb9eff5915dbbd2a1283ef842809214b8df9a5a6344`)
> Addresses: human review findings 1–7 (Gate 0–2 暂不通过). No LLM was called, nothing was deployed, and no experiment was run.
> Status: **FROZEN, PENDING HUMAN REVIEW.**

---

## 0. Protected files — untouched (verified by SHA-256)

| file | SHA-256 | status |
|---|---|---|
| `heldout_protocol_v1_1.md` | `b23d05b4…` | IDENTICAL |
| `heldout_protocol_v1_1.json` | `6c263a7b…` | IDENTICAL |
| `hotel_knowledge_snapshot_pre.json` | `396f5e74…` | IDENTICAL |
| `socialnet_knowledge_snapshot_pre.json` | `e8cf58f8…` | IDENTICAL |
| `teastore_knowledge_snapshot_pre.json` | `339dd220…` | IDENTICAL |

The frozen candidate pools are also byte-identical to the previously frozen pools
(ESHOP pilot `41313aea…`, ESHOP formal `9a6a1e5a…`, SOCIALNET pilot `10c06fbe…`,
SOCIALNET formal `614eab5f…`): **pools were not modified**.

---

## 1. Fix 1 — LLM-generic is now generic-rules-only

New artifact: `artifacts/experiments/knowledge_ablation_generic_rules_v1.json`
(SHA-256 `5b813997e5742dc9c59938171ff53cdf1ab37a18c7f01c3530058416b745f258`, pinned).

- SE/DP/JE are distilled to **project-free rule statements** (10 SE rules, 4 DP
  patterns, 6 JE rules).
- Removed from the LLM-facing view: historical project names, service names,
  candidate IDs, `experiment_evidence`, `corpus_evidence`, `evidence_cases`,
  `evidence_files`, `evidence_count`, concrete experiment file paths, and all
  project results/severity numbers.
- `DP-DEFENSE-ABSORBED_BY_DESIGN-TT-BASIC-DELAY-500` renamed to
  `DP-DEFENSE-ABSORBED-003` (original ID embedded a candidate identifier).
- The file's top-level metadata documents what was stripped (informational only);
  the LLM-facing sections (`selection_experience`, `defense_pattern_library`,
  `judgment_experience`) are clean of all historical terms and evidence markers
  (verified by scan and by regression test).
- The builder pins this SHA and fails closed on drift.

## 2. Fix 2 — knowledge_snapshot_manifest full_pre/status

The manifest's `snapshots.original` now reads `status`, `full_pre`, and
`provenance_completeness` **from the live snapshot** (not hardcoded):

| project | live status/full_pre | manifest status/full_pre | match |
|---|---|---|---|
| ESHOP | `blocked` / `false` | `blocked` / `false` (completeness `partial`) | ✓ |
| SOCIALNET | `valid` / `true` | `valid` / `true` (completeness `complete`) | ✓ (was the bug) |

## 3. Fix 3 — regenerated artifacts

All arm views, prompt bundles, leakage audits, prompt manifests and the total
manifest were regenerated (140 files, all hashes verified on disk).

## 4. Fix 4 — full leakage scan (historical + current + evidence)

- `HISTORICAL_TERMS`: prior-project markers (`train-ticket`, `online-boutique`,
  `otel-demo`, `sock-shop`, plus candidate-ID prefixes `TT-`, `OB-`, `OTEL-`,
  `SOCK-`, `KB-`, `K7-`) and prior-service names (`paymentservice`,
  `checkoutservice`, `catalogue-db`, `ts-station`, …).
- Scanned across **every arm** (blind/generic/full-pre/partial-pre), in
  knowledge sections, intake summaries, candidate descriptors, and rendered
  prompts, plus a structural forbidden-field scan.
- Word-boundary matching prevents false positives (e.g., `otel` inside `hotel`).
- Result: **36/36 arm scans pass**; generic-rules LLM sections pass for both
  projects; pools contain no historical terms; `oracle_label` values are only
  the `stored-out-of-band` placeholder; `mutation_path` stays `null` in pools.

## 5. Fix 5 — ESHOP third arm renamed to LLM-partial-pre

| project | third arm | full_pre claimable | reason |
|---|---|---|---|
| ESHOP | `LLM-partial-pre` (dir `partial-pre`) | **no** | snapshot `blocked`, availability unavailable |
| SOCIALNET | `LLM-full-pre` (dir `full-pre`) | yes | snapshot `valid`/`full_pre=True` |

The ESHOP partial-pre bundle still carries its verified static contracts
(`no_timeout` edges) but explicitly marks availability as unavailable and does
not claim full-pre status.

## 6. Fix 6 — formal pools are NOT protocol-conformant 48

`formal_pool_conformance` in the total manifest declares:

| pool | actual | pre-registered | amendment required |
|---|---|---|---|
| ESHOP/formal | 40 | 48 | **yes** |
| SOCIALNET/formal | 30 | 48 | **yes** |
| ESHOP/pilot | 24 | 24 | no |
| SOCIALNET/pilot | 24 | 24 | no |

The 40/30 formal pools **cannot be used as the pre-registered formal-48 pools
without a protocol amendment**. No amendment is claimed in this package; formal
execution is blocked pending a human decision.

## 7. Fix 7 — independent candidate_id → mutation_path mapping

`artifacts/experiments/knowledge_ablation_mutations/<project>/mutation_map.json`
maps every candidate to a frozen NetworkChaos (delay/loss) or PodChaos (kill)
YAML under `knowledge_ablation_mutations/<project>/`. Each YAML is `mode: one`,
uses the pre-registered parameter tiers (delay 2000ms, loss 100%, kill pod-kill,
duration 30s), and carries a recorded SHA-256 (verified on disk).

- ESHOP: 40 entries; SOCIALNET: 30 entries; 70 YAMLs total, all mode=one, all
  parse, all hashes match.
- **The frozen candidate pools are NOT modified** (their `mutation_path` stays
  `null`); the mapping is a separate artifact for later execution.
- Namespace `heldout-<project>-lab` is a pre-registered placeholder and must be
  confirmed at the deployment gate.

## 8. Validation results

- `python -m json.tool` / json.load over all 34 generated JSON + generic-rules +
  total manifest: all valid.
- YAML parse (PyYAML) over all 70 mutation files: all valid, all `mode: one`.
- `pytest -q`: **225 passed, 5 subtests passed** (includes 10 new remediation-v2
  regression tests).
- `git diff --check`: clean (CRLF warnings only).
- Protected files (protocol + 3 snapshots) and frozen pools: byte-identical.

## 9. Generated artifacts (location)

```
artifacts/experiments/
  knowledge_ablation_generic_rules_v1.json        (Fix 1; pinned)
  knowledge_ablation_manifest_gate0to2.json       (schema_version 2; total manifest)
  knowledge_ablation_snapshots/<project>/{project_commit_manifest,knowledge_snapshot_manifest,leakage_audit,{blind,generic,{full,partial}_pre}_view}.json
  knowledge_ablation_candidates/<project>/{pilot,formal}.json          (unchanged bytes)
  knowledge_ablation_oracle/<project>/candidate_protection_classification.json
  knowledge_ablation_prompts/<project>/{blind,generic,{full,partial}-pre}/{pilot,formal}/...
  knowledge_ablation_mutations/<project>/{<candidate_id>.yaml, mutation_map.json}   (Fix 7)
tools/build_knowledge_ablation_gates0to2.py        (remediation v2 builder)
tools/tests/test_knowledge_ablation_remediation_v2.py
```

## 10. Still blocked / awaiting human decision

1. **Formal-48 conformance**: ESHOP 40 / SOCIALNET 30 formal pools require a
   protocol amendment (or an expanded verified universe) before formal execution.
2. **Quota deviations**: ESHOP 0 protected / SOCIALNET 0 unknown (both phases);
   formal quotas under/over-filled. Recorded, not rebalanced.
3. **B1 (from v1)**: source-checkout hashes not re-verified this session (WSL
   root access needed).
4. **Gate 3+** (LLM selection, execution, oracle) remains out of scope until
   human approval of this package.

**Waiting for human review.**
