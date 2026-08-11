# Protocol Amendment — LLM Knowledge-Base Ablation (DRAFT for human approval)

> Date: 2026-08-10
> Protocol amended: `artifacts/experiments/llm_knowledge_ablation_protocol_v1.md`
> (SHA `9dc24410830ac894…`, header status **DRAFT**)
> Status: **DRAFT — requires human approval. No LLM selection, deployment, or
> injection may start until this amendment AND the protocol freeze are approved.**

---

## 1. Plan B — descriptive comparison on the actual candidate universe

Chosen option: **B** (per reviewer recommendation). Formal pools are smaller than
the pre-registered 48, and expansion (Plan A) is not adopted because no new
verifiable, method-neutral candidates exist beyond the statically-verified
universe and a third independent project family is required for cross-project
claims regardless of pool size.

| project | frozen formal pool | pre-registered | treatment |
|---|---|---|---|
| ESHOP | 40 | 48 | **descriptive, not preregistered formal-48** |
| SOCIALNET | 30 | 48 | **descriptive, not preregistered formal-48** |
| pilot | 24 / 24 | 24 / 24 | unchanged (conforms) |

Rules:
1. **K fixed at 10** for formal; K=8 for pilot. No change.
2. Results are labeled **"descriptive comparison on the actual frozen candidate
   universe"** — never "preregistered formal-48".
3. **No candidate is added, duplicated, or borrowed across projects.** Frozen
   pools are NOT modified (SHA-pinned).
4. Statistics use **project-level paired analysis** (candidates are nested in
   projects, not independent samples); with <3 independent project families only
   descriptive conclusions are permitted.
5. **No weighted composite score.**

## 2. Arm knowledge states (as frozen in Gate 0–2 remediation v2)

| arm | ESHOP | SOCIALNET |
|---|---|---|
| `LLM-blind` | ✓ | ✓ |
| `LLM-generic` (generic-rules-only) | ✓ | ✓ |
| `LLM-partial-pre` | ✓ (full_pre NOT claimable; snapshot blocked) | — |
| `LLM-full-pre` | — | ✓ (snapshot valid/full_pre=True) |

- ESHOP and SOCIALNET **must not be merged into one full-pre knowledge state**;
  partial-pre results are reported separately and never equated with full-pre.

## 3. Environment-feasibility findings (this date) — recorded, not fixed here

| project | finding | classification |
|---|---|---|
| ESHOP | no deployment manifest at frozen commit | `deployment_unavailable` |
| SOCIALNET | bring-up blocked: cluster Service-DNS broken (CoreDNS crash-loop), app listener never opens (Jaeger unresolved); baseline x2 failed | `environment_blocked` |
| SOCIALNET | **18/30 frozen delay/loss mutation YAMLs have selector mismatch** (`app: <short>` vs actual `app=<name>-service`); 12 kill YAMLs match | `selector_mismatch` |
| Chaos Mesh | installed (23 CRDs); controller-manager + daemon Running; dashboard CrashLoopBackOff; dns-server not Ready | partial |

Consequences:
- **ESHOP**: no Weakness@K, no formal Chaos selection. Selection-only or
  `environment_blocked`. Not merged with SOCIALNET.
- **SOCIALNET**: execution line `environment_blocked` until (a) Service-DNS is
  repaired and CoreDNS Ready, (b) two consecutive baselines pass, (c) the 18
  selectors are fixed, (d) observation chain verified.
- **environment_blocked is never a method win/loss** (protocol §14).
- The **selector_mismatch defect belongs to the frozen mutation mapping** and
  requires a regenerated mapping (or label alignment) — a separate fix with its
  own audit trail; the frozen candidate pools/YAMLs are NOT edited in place.

## 4. Gate state after this amendment

- Gate 0–2: frozen (pools, prompts, snapshots, oracle isolated) — unchanged.
- Gate 2 formal-pool conformance: **amended** (this document).
- Gate 3 (pilot LLM selection): **not approved** — environment feasibility failed;
  and protocol still DRAFT.
- Gate 4 (bring-up/baseline): **not passed** (this feasibility report).

## 5. What is explicitly NOT changed

- Frozen candidate pools (SHA `41313aea…`/`9a6a1e5a…` ESHOP; `10c06fbe…`/`614eab5f…`
  SOCIALNET), seeds, K, temperature, max tokens, timeout, output schema, prompts.
- `heldout_protocol_v1_1.md/json` and the three knowledge snapshots (Hotel /
  SOCIALNET / TeaStore) — untouched (verified byte-identical).
- The `llm_knowledge_ablation_protocol_v1.md` text itself remains unchanged; this
  amendment is a separate, dated, versioned document.

## 6. Approval items

1. Approve Plan B (descriptive comparison on actual universe; K=10; no formal-48 claim).
2. Freeze `llm_knowledge_ablation_protocol_v1.md` (currently DRAFT).
3. Accept ESHOP as **selection-only or environment_blocked** (not executable).
4. Accept SOCIALNET as **environment_blocked** pending DNS/baseline repair + the
   selector-mismatch fix (separate tracked item).
5. Decide whether to proceed at all with only 2 projects (descriptive) or add a
   third independent project family.

> This document is a DRAFT. Nothing in it authorizes LLM calls, deployment, or
> Chaos injection.
