# LLM Knowledge-Base Ablation — Gate 0–2 Review Package

> Date: 2026-08-10
> Protocol: `artifacts/experiments/llm_knowledge_ablation_protocol_v1.md` (SHA-256 `9dc24410830ac894326a0fb9eff5915dbbd2a1283ef842809214b8df9a5a6344`)
> Scope: Gate 0 (commits/source hashes/snapshots), Gate 1 (leakage audit + frozen arm views), Gate 2 (frozen pools, out-of-band classification), prompt pre-registration (model/endpoint/seeds/permutations/prompts).
> Status: **FROZEN, PENDING HUMAN REVIEW**. No deployment, no Chaos, no LLM selection, no execution has occurred.

---

## 1. Concurrency note (mandatory read)

At session start the ESHOP/SOCIALNET snapshots were the committed `blocked` versions. During this session a
parallel Stage C2 process (helm availability audit) **regenerated the snapshots and intake reports mid-run**.
Per human decision, I waited until the files settled (stable for 10+ minutes) before freezing. The frozen
state used for all Gate 0–2 artifacts is the **settled Stage C2 state**:

| project | settled snapshot status | full_pre | provenance_completeness | contract edges | availability |
|---|---|---|---|---|---|
| ESHOP | `blocked` | `false` | `partial` | 2 (`no_timeout`) | unavailable (no manifest) |
| SOCIALNET | `valid` | `true` | `complete` | 9 verified (`explicit_timeout` 10s) + 3 excluded `unverified_contract_edges` | verified (helm: replicas=1, no PDB/HPA/probes) |

Snapshot drift guard: the builder fail-closes if the snapshot status/full_pre diverge from the values recorded
in this report, and refuses to overwrite any existing artifact.

---

## 2. Generated file list and SHA-256

Complete listing with hashes is in
`artifacts/experiments/knowledge_ablation_manifest_gate0to2.json` (68 files; the manifest itself is the 69th).
All 68 were independently re-verified on disk after generation. Layout (protocol §12):

```
artifacts/experiments/
  knowledge_ablation_manifest_gate0to2.json
  knowledge_ablation_snapshots/<project>/{project_commit_manifest,knowledge_snapshot_manifest,leakage_audit,{blind,generic,full_pre}_view}.json
  knowledge_ablation_candidates/<project>/{pilot,formal}.json
  knowledge_ablation_oracle/<project>/candidate_protection_classification.json
  knowledge_ablation_prompts/<project>/prompt_manifest.json
  knowledge_ablation_prompts/<project>/{blind,generic,full-pre}/{pilot,formal}/{bundle.json, seed-{1001,1002,1003|2001,2002,2003}.prompt.txt}
```

Per-file SHA-256 (full 64-hex values are in the manifest; key files):

| file | SHA-256 |
|---|---|
| `knowledge_ablation_manifest_gate0to2.json` | `a5f585fe243a921f8c853691a7adaab73cc31ba7d3961304e813824aa1118a89` |
| `.../ESHOP/pilot.json` (pool) | `41313aeab7bd97773bdfc4b0efae18575cf425b34529bfbc9cf59108bc0cfc4a` |
| `.../ESHOP/formal.json` (pool) | `9a6a1e5a2e1759faf526f3b0da43781375850b01825b28d9347f61393d39ebc6` |
| `.../SOCIALNET/pilot.json` (pool) | `10c06fbece09c44d9ae30da3a5e88352f9d154d0333bcb41bf8739545bd8dc97` |
| `.../SOCIALNET/formal.json` (pool) | `614eab5fbc7a5a056d820bb8d99eee783831222f050f3a27ff8866a5579332eb` |
| `.../ESHOP/prompt_manifest.json` | `b0a412759dce71a054874e3d195b644b0bbaac985fdfc28f814bde93ab19c3d5` |
| `.../SOCIALNET/prompt_manifest.json` | `e85f4cfd6082288973cf5a07a8733745c3289e976bbaa70206a3ef4de75e5543` |
| `.../ESHOP/leakage_audit.json` | `c121767c7eb68bd9fd9249b6e8e24df4c384db0aaf53a437df9128bc2eefd54d` |
| `.../SOCIALNET/leakage_audit.json` | `15a6ad97013ed60ebef154d022c28864988d1e805bb94ff2c8e92c62b6d429e1` |
| `.../ESHOP/candidate_protection_classification.json` | `81573dcfee091559ec1ae338813de1d6cd181aba2ebd2bb0503d150063ac5ff2` |
| `.../SOCIALNET/candidate_protection_classification.json` | `468e2451ab14c75fa810b1aa7b553d0b8087bcbb44c54822ed490466b59cc4ff` |

Underlying frozen sources (pre-existing, unmodified by this work):
- `heldout/eshop_knowledge_snapshot_pre.json` `de6c1239d6b2a762…`
- `heldout/socialnet_knowledge_snapshot_pre.json` `e8cf58f89dc32aa2…`
- SE/DP/JE pinned hashes: `f7280be…`, `afffb6a…`, `7756d8d…` (unchanged; embedded in snapshots and re-verified).

---

## 3. Gate 0 — commits, source hashes, snapshots

- Commit manifest per project: `knowledge_ablation_snapshots/<project>/project_commit_manifest.json`
  - ESHOP `9b4f9434…` (`dotnet/eShop`, MIT), 7 source-file hashes from frozen intake.
  - SOCIALNET `6ecb0970…` (`DeathStarBench socialNetwork/`, GPL-2.0), 7 intake hashes + 20 snapshot provenance hashes (incl. helm values.yaml per service, Stage C2).
- Source-path hash re-verification: **NOT re-run this session** — the WSL checkout `/root/heldout_src/*` is root-owned and unreadable without interactive sudo. Recorded hashes are the frozen 2026-08-10 intake values; a human with WSL root access should independently re-verify (blocker B1).
- Snapshots validate against `decision_engine.validate_knowledge_snapshot`; embedded SE/DP/JE match pinned live hashes byte-for-byte.

## 4. Gate 1 — leakage audit results

Per-arm views frozen in `knowledge_ablation_snapshots/<project>/*_view.json`; full scan results in `leakage_audit.json`.

| arm | knowledge supplied | project-specific contract/availability | verdict/oracle data |
|---|---|---|---|
| `LLM-blind` | none (`knowledge: null`) | **no** | none |
| `LLM-generic` | SE/DP/JE only (pinned) | **no** | none |
| `LLM-full-pre` | SE/DP/JE + project-specific snapshot (contracts, availability scope, provenance; `status/status_reason/candidate_map/full_pre` redacted) | yes (redacted view) | none |

Audit method: term scans (project markers, contract/availability markers, knowledge markers, narrow
verdict markers) + structural forbidden-field scan on the full bundle JSON + rendered prompt. **36/36 arm
scans PASS; 0 forbidden fields; 0 project-term hits in knowledge sections; no oracle labels reach any
LLM input.** Known limitation: ESHOP/SOCIALNET are descriptively referenced in task/intake text by
candidate IDs and service names (this is intended I0 information); the audit proves the *knowledge* and
*verdict* channels are clean.

## 5. Gate 2 — candidate pool composition and deviations

Pre-registered rules: pool from statically-documented call edges (intake dependency graph) + helm-verified
kill targets; per-family rotation (pilot 8/family, formal 16/family); kill family `unavailable` only where
no deployment target exists; no borrowing, no result-derived filtering.

| project/phase | size | target | protected | unprotected | unknown | delay | loss | kill |
|---|---|---|---|---|---|---|---|---|
| ESHOP/pilot | 24 | 24 | 0 | 4 | 20 | 12 | 12 | – |
| ESHOP/formal | **40** | 48 | 0 | 4 | 36 | 20 | 20 | – |
| SOCIALNET/pilot | 24 | 24 | 8 | 16 | 0 | 8 | 8 | 8 |
| SOCIALNET/formal | **30** | 48 | 9 | 21 | 0 | 9 | 9 | 12 |

- Quota targets are 8/8/8 (pilot) and 16/16/16 (formal); **deviations are recorded, not silently rebalanced**.
- **Blockers B2/B3**: both formal pools fall short of 48 because the verified candidate universe is finite
  (ESHOP: 40 = 20 documented edges × 2 families; SOCIALNET: 30 = 9 verified edges × 2 families + 12 kill
  targets). The protocol requires formal K=10 selections from a frozen 48-pool; a 40/30 pool makes
  `Weakness@10` well-defined but the pool is smaller than pre-registered, and the protected/unknown quotas
  are under-filled (ESHOP formal: 0 protected/36 unknown; SOCIALNET formal: 9 protected/0 unknown).
- Classification is **out-of-band** (`candidate_protection_classification.json`, rule CLS-001..005);
  `oracle_label` in pool files is the placeholder `stored-out-of-band` only. No truth label enters any LLM bundle.

## 6. Prompt pre-registration

`prompt_manifest.json` per project: model `deepseek-v4-flash`, endpoint `https://api.deepseek.com/v1`
(OpenAI-compatible), temperature 0.2, max_output_tokens 2048, timeout 180 s, json_mode true; K = 8 (pilot) /
10 (formal); seeds pilot [1001,1002,1003], formal [2001,2002,2003]; candidate-order permutation per
(phase, seed) recorded and **identical across the three arms** (paired design verified by spot check).
12 rendered prompts per project are frozen with hashes; **no LLM call was made.**

## 7. Blockers for human review

- **B1 (Gate 0 verification gap):** Source-checkout hashes not re-verified this session (WSL root access
  needed). Frozen intake hashes used; independent re-verification recommended before Gate 3.
- **B2 (pool size):** ESHOP/formal = 40, SOCIALNET/formal = 30, below the pre-registered 48. Requires a
  decision: (a) amend protocol to allow 40/30 formal pools (documenting the shortfall), (b) expand the
  verified universe (more edge/SHA work), or (c) downgrade the formal phase. Cannot proceed to formal
  execution unchanged.
- **B3 (quota shortfall):** protection quotas under/over-filled (ESHOP 0 protected; SOCIALNET 0 unknown in
  both phases; formal deviations -16/+20 and -7/-16). Recorded as deviations per protocol §5; reviewer must
  confirm the pool still satisfies the ablation's research questions or approve an amendment.
- **B4 (unverified SOCIALNET edges):** 3 contract edges (`usertimeline->poststorage`, `user->socialgraph`,
  `socialgraph->user`) are explicitly excluded from the pool until source SHA is computed (snapshot marks
  them `unverified_contract_edges`). Their later inclusion would change the pool → requires an amendment if
  added after this freeze.
- **B5 (compare-ability):** ESHOP kill family `unavailable` and SOCIALNET `unknown` class = 0 mean the two
  projects differ structurally; ≥3 comparable projects are still required for any cross-project claim (no
  such claim is made here).

## 8. Reviewer checklist (protocol §15 status)

- [x] Three arms differ only in knowledge visibility.
- [x] All snapshots and prompts have hashes and provenance.
- [x] Candidate truth labels out-of-band during selection.
- [x] Seeds and candidate-order permutations pre-registered and identical across arms.
- [ ] Candidate pools of 24/48 and quotas **NOT** met for formal phase (B2/B3).
- [ ] Full-pool oracle before recall/missed-weakness claims (future gate; not this package).
- [x] No weighted-total score; no cross-project claim made.
- [ ] Human approval of B1–B5 before Gate 3.

**Waiting for human review.**
