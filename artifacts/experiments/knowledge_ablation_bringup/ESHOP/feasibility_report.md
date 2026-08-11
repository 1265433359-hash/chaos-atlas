# ESHOP — Environment Feasibility Report (2026-08-10)

> Status: **deployment_unavailable** — ESHOP cannot be executed in this environment.
> No LLM was called; no formal candidate selection; no Chaos injection; no deployment.

## 1. Deployment manifest availability

**No runnable deployment manifest exists** at the frozen commit `9b4f9434` of
`https://github.com/dotnet/eShop` (source checkout `/root/heldout_src/eshop`):

- **Kubernetes manifests: none**
- **docker-compose: none**
- **Dockerfile: none** (`find src -name Dockerfile*` empty)
- The only YAML files are CI/lint metadata: `es-metadata.yml`, `.spectral.yml`, `ci.yml`
- Deployment form is Aspire development orchestration (`eShop.AppHost/Program.cs`,
  `AddProject`) — this is not a k8s/compose deployment entry and was not
  constructible statically (snapshot `status=blocked`, `full_pre=false`).

This matches the frozen intake report (`eshop_intake_report.json`:
`manifests.docker_compose=none`, `kubernetes=none`, `dockerfile=none`) and the
frozen snapshot (`eshop_knowledge_snapshot_pre.json`: `status=blocked`).

## 2. Classification

| check | result | classification |
|---|---|---|
| deployment manifest | **absent** | `deployment_unavailable` |
| namespace / selector | n/a (no deployment) | `deployment_unavailable` |
| minimal bring-up | not attempted (no manifest) | `deployment_unavailable` |
| baseline x2 | not available | `deployment_unavailable` |
| delay/loss injection | not performed | `injection_unavailable` |
| observation chain | not available | `observation_unavailable` |
| recovery / cleanup | not testable | `recovery_failed` (n/a) |

**`deployment_unavailable` is the root cause; all downstream checks are blocked
by it.**

## 3. Consequences (per protocol + human instructions)

- **ESHOP must NOT run Weakness@K.**
- **ESHOP must NOT run formal Chaos selection.**
- ESHOP is retained as **selection-only or environment_blocked**.
- ESHOP and SOCIALNET results **must NOT be merged** in any statistics.

## 4. Frozen artifacts — untouched

- `knowledge_ablation_candidates/ESHOP/pilot.json` SHA `41313aea…` (unchanged)
- `knowledge_ablation_candidates/ESHOP/formal.json` SHA `9a6a1e5a…` (unchanged)
- 40 mutation YAMLs under `knowledge_ablation_mutations/ESHOP/` (unchanged,
  static-only, no runtime verification)
- No LLM selection, no injection, no experiment was run during this check.

## 5. Gate 3 eligibility

**Not eligible.** ESHOP execution requires either (a) a real deployment manifest
or (b) a recorded `environment_blocked` for its execution line. Selection-only
(`LLM-partial-pre`) may proceed only after separate human approval.
