# LLM Knowledge Ablation — Current-State Audit (2026-08-10)

> Phase 1 read-only audit. No experiment, no deployment, no LLM call was performed
> in producing this report. All numbers below were re-verified directly from disk in
> this session (not copied from other agent reports).

---

## 1. Repository state

| item | value |
|---|---|
| branch | `remediation/2026-08-09-review` |
| HEAD | `09f2c23` — "fix(heldout): make Stage D freeze checks fail-closed" (2026-08-10) |
| recent commits | `09f2c23` Stage D fail-closed; `b1ffaef` Stage D freeze (Hotel/SOCIALNET/TeaStore); `8209ee9` Stage C3 TeaStore; `a263942` Stage C2 SOCIALNET; `5786a07` Stage C |
| ablation artifacts tracked in git | **0** (all `knowledge_ablation_*` are untracked working-tree files) |
| working tree | modified heldout intake/snapshots/builders from the parallel Stage A–D process; ablation artifacts untracked |

## 2. Protocol SHA-256

- `artifacts/experiments/llm_knowledge_ablation_protocol_v1.md` → **`9dc24410830ac894…`**
- **Status in header: `DRAFT`** — "not frozen until the human reviewer approves the
  pre-registration checklist". This is a blocking fact: no arm selection may start
  while the protocol itself is still DRAFT.

## 3. Gate 0–Gate 2 status

| gate | status | evidence |
|---|---|---|
| Gate 0 (commits/source hashes/snapshots) | **partial — see B3** | commit manifests + snapshot refs hashed; source checkout NOT re-verifiable this session |
| Gate 1 (leakage audit + frozen arm views) | **pass (36/36)** | `leakage_audit.json` per project; generic-rules LLM sections clean |
| Gate 2 (candidate pools frozen, oracle isolated) | **pass with amendments required** | pools byte-identical to remediation-v2 freeze; formal pools ≠ 48 (B1); quota deviations (B2) |

## 4. Candidate counts (frozen pools on disk)

| project | pilot | formal | target (pilot/formal) |
|---|---|---|---|
| ESHOP | 24 | **40** | 24/48 |
| SOCIALNET | 24 | **30** | 24/48 |

- `knowledge_ablation_manifest_gate0to2.json` (`d469a0cf…`) declares
  `requires_protocol_amendment: true` for both formal pools.
- Pilot pools match the pre-registered 24 in both projects.

## 5. Protection-class distribution (from the out-of-band oracle, frozen)

| project/phase | protected | unprotected | unknown |
|---|---|---|---|
| ESHOP/pilot | 0 | 4 | 20 |
| ESHOP/formal | 0 | 4 | 36 |
| SOCIALNET/pilot | 8 | 16 | 0 |
| SOCIALNET/formal | 9 | 21 | 0 |

- Quota targets are 8/8/8 (pilot) and 16/16/16 (formal).
- **ESHOP has 0 protected candidates** (no verified timeout/fallback evidence; only
  2 contract edges are `no_timeout` → unprotected, the rest unknown).
- **SOCIALNET has 0 unknown candidates** (all edges statically classified).
- Both are recorded as deviations in `candidate_protection_classification.json`; no
  silent rebalancing was performed.

## 6. Fault-family distribution

| project/phase | delay | loss | kill |
|---|---|---|---|
| ESHOP/pilot | 12 | 12 | 0 (family `unavailable`) |
| ESHOP/formal | 20 | 20 | 0 (family `unavailable`) |
| SOCIALNET/pilot | 8 | 8 | 8 |
| SOCIALNET/formal | 9 | 9 | 12 |

- ESHOP kill is `unavailable` (no deployment manifest at the frozen commit). No
  kill candidates are borrowed from any other project.
- All three families appear in SOCIALNET; ESHOP supports only delay/loss.

## 7. LLM arm input differences (verified from bundles)

| arm | ESHOP | SOCIALNET | knowledge |
|---|---|---|---|
| `LLM-blind` | ✓ | ✓ | `null`; neutral intake summary; neutral descriptors |
| `LLM-generic` | ✓ | ✓ | `generic_rules` only (project-free) |
| `LLM-full-pre` | — | ✓ | `generic_rules` + project_specific (contracts, availability_scope, provenance) |
| `LLM-partial-pre` | ✓ | — | `generic_rules` + project_specific (contracts only; availability unavailable; full_pre not claimable) |

- Model/endpoint/temp/max_tokens/timeout identical across arms: `deepseek-v4-flash`,
  `https://api.deepseek.com/v1`, 0.2, 2048, 180 s.
- Seeds identical across arms: pilot `[1001,1002,1003]`, formal `[2001,2002,2003]`.
- Candidate-order permutation for a given (phase, seed) is byte-identical across
  arms (paired design; verified for pilot/1001 in both projects).
- Budget: K=8 pilot, K=10 formal. Output schema identical.
- ESHOP has NO `LLM-full-pre` arm — it uses `LLM-partial-pre` and must never be
  reported as full-pre (protocol §2/§5; remediation Fix 5).

## 8. Generic knowledge base — leakage check (fresh scan this session)

- LLM-facing sections of `knowledge_ablation_generic_rules_v1.json`
  (SHA `5b813997…`):
  - substring scan for historical project names, service names, candidate-ID
    prefixes (`TT-`, `OB-`, `OTEL-`, `SOCK-`, `KB-`, `K7-`), file paths
    (`mutations/`, `*.yaml`, `main.go`, `application.yml`), evidence markers
    (`experiment_evidence`, `corpus_evidence`, `evidence_cases`, `evidence_files`,
    `evidence_count`), and verdict markers (`weakness@k`, `protected-waste`,
    `environment_blocked`, `root_cause`): **0 hits**.
  - The file's top-level metadata block documents what was stripped (sanitization
    log) and is informational only — never sent to any LLM.
- Rendered prompts / intake summaries / descriptors / arm views contain no
  historical project terms (word-boundary scan; all 36 arm scans pass).

## 9. Snapshot pre-experiment status

| project | snapshot status | full_pre | source_provenance (all five fields) |
|---|---|---|---|
| ESHOP | `blocked` | `false` | contract=static_reconstructed_pre_experiment; availability=unavailable; SE/DP/JE=pre_experiment_commit |
| SOCIALNET | `valid` | `true` | contract/availability=static_reconstructed_pre_experiment; SE/DP/JE=pre_experiment_commit |

- ESHOP cannot claim full-pre (availability unavailable). `LLM-partial-pre` is the
  correct arm; this is recorded in the arm view and the manifest.
- The three main-protocol snapshots (Hotel/SOCIALNET/TeaStore) are untouched
  (SHA-256 unchanged from baseline).

## 10. Source-hash re-verification

- **NOT possible in this session**: the WSL checkout `/root/heldout_src` is
  root-owned and not readable without interactive sudo (`Permission denied`).
- Commit manifests record `hash_verification.status =
  recorded_2026-08-10_intake_not_reverified_this_session`. All source hashes are
  frozen intake values awaiting an independent human re-verification with WSL root
  access (blocker B3).

## 11. Mutation YAML executability

- 70 static YAML files under `knowledge_ablation_mutations/{ESHOP,SOCIALNET}/`,
  one per candidate, plus a `mutation_map.json` (candidate_id → mutation_path,
  yaml_sha256, fault_parameters, pool_eligibility).
- All YAMLs: `mode: one`; NetworkChaos for delay/loss (latency 2000ms / loss 100%,
  duration 30s, direction to) and PodChaos for kill.
- **They are STATIC-ONLY**: grep for `observed|runtime|verified|baseline` in the
  mutation tree returns 0 matches; there are no `.log`/`.jsonl` execution files
  anywhere under `knowledge_ablation_*`.
- **Not runtime-validated**: the namespace `heldout-<project>-lab` is a
  pre-registered placeholder and the `selector.labelSelectors.app` values have not
  been verified against any live deployment (no bring-up has occurred). They are
  NOT executable as-is until the deployment gate confirms namespace and labels.

## 12. pytest output (fresh, this session)

```
236 passed, 5 subtests passed in 3.84s
```

(Includes `test_knowledge_ablation_remediation_v2.py` — 10 tests covering
generic-rules cleanliness, leakage-audit pass, formal-48 non-conformance, and
mutation-map hash integrity.)

## 13. Selection / execution / oracle artifacts

| artifact | exists? |
|---|---|
| `knowledge_ablation_selections/` | **no** |
| `knowledge_ablation_execution/` | **no** |
| `knowledge_ablation_analysis/` | **no** |
| `knowledge_ablation_claim_evidence_matrix.md` | **no** |
| `knowledge_ablation_run_ledger.jsonl` | **no** |

No LLM selection, no Chaos execution, and no independent oracle pass has been run.
The only oracle file is the static pre-selection classification
(`knowledge_ablation_oracle/<project>/candidate_protection_classification.json`),
which is out-of-band and never enters any LLM bundle.

---

## 14. Blockers — Gate 3 is NOT permitted yet

| id | blocker | severity |
|---|---|---|
| B1 | Formal pools ESHOP=40, SOCIALNET=30 ≠ pre-registered 48. No amendment approved. | blocking |
| B2 | Quota deviations: ESHOP 0 protected; SOCIALNET 0 unknown (pilot+formal). Weakness@K and Protected-waste@K interpretability affected. | blocking |
| B3 | Source hashes not re-verifiable this session (WSL root access needed). | blocking |
| B4 | Protocol `llm_knowledge_ablation_protocol_v1.md` is **DRAFT** (header), not frozen. | blocking |
| B5 | Only ESHOP + SOCIALNET (2 projects). SOCIALNET is DeathStarBench-family; Hotel (main track) shares the same DeathStarBench repo. Per protocol §10 and heldout v1.1 §6, fewer than 3 independent project families → descriptive results only, no cross-project generalization claim. | claim-limiting |
| B6 | Mutation YAMLs not runtime-validated (placeholder namespace/selectors); bring-up/baseline gates not_run. | blocking for execution (Gate 4) |
| B7 | ESHOP `LLM-partial-pre` must never be merged/equated with `LLM-full-pre` results. | claim-limiting |

## 15. Formal-pool amendment — options for human decision (do not self-select)

| option | description | cost | consequence |
|---|---|---|---|
| **A. Expand pools** | add only real, verifiable, method-neutral candidates to reach 48 | new static source work (expanded edge/contract verification) + full regeneration | keeps pre-registered formal-48 design |
| **B. Amend protocol → descriptive on actual universe** | record ESHOP=40, SOCIALNET=30; keep K=10; label results "descriptive comparison on the actual full universe", never "preregistered formal-48"; project-level paired analysis only | small (amendment doc + manifest update) | weaker claim, honest; aligns with protocol §10 / heldout v1.1 §6 |
| **C. No formal experiment** | treat current data as pilot/descriptive; no formal LLM selection + Chaos | none | no strict KB-benefit claim possible |

**Recommendation**: Option B is the most defensible given the verified universe is
finite and the protocol demands 3 project families for cross-project claims (which
2 projects cannot satisfy regardless of pool size). Option A only helps if a third
independent project family (non-DeathStarBench) is added. Option C is the fallback
if no amendment can be approved.

## 16. Actions required before Gate 3

1. Human approval of an amendment (A/B/C) for the formal pool.
2. Human freeze of the protocol (currently DRAFT).
3. Human decision on whether to proceed with only 2 projects (descriptive) or add a
   third independent family.
4. Independent re-verification of source hashes (WSL root) OR recorded waiver.
5. Confirmation that ESHOP `LLM-partial-pre` is acceptable as a non-full-pre arm.

Until then, **no LLM selection, no deployment, no Chaos injection, no oracle pass**.

---

*Audit generated 2026-08-10 in this session; all hashes and counts read directly
from disk.*
