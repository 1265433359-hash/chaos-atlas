# ChaosAtlas Repository Map

This repository contains both the ChaosAtlas product and the evidence produced while validating it. The distinction below is intentional: product files are maintained as source, while runtime output is retained only when it has clear provenance and review value.

## Target Logical Tree

```text
tools/          implementation, adapters, orchestration, policy, RCA, knowledge, tests
projects/       project profiles, business oracles, onboarding metadata
experiments/    authored scenarios, manifests, and experiment protocols
artifacts/      generated runtime evidence, RCA, acceptance, and replay output
knowledge/      reusable schemas, cards, promotion history, regression intents
reporting/      human-review reports and issue drafts
docs/           architecture, operations, methods, research, and plans
raw_yaml/       read-only source snapshots with provenance
governance/     repository and data handling rules
vendor/         external source copies, never product source
```

## Current Directory Map

| Current path | Lifecycle class | GitHub policy |
| --- | --- | --- |
| `tools/` | Compatibility modules and implementation helpers | Track |
| `tests/` | Product contract and regression tests | Track |
| `docs/` | Product and research documentation | Track when reviewed |
| `reporting/` | Human-review material and issue drafts | Track selected reviewed reports |
| `governance/` | Repository and data policy | Track |
| `artifacts/project_profiles/` | Project onboarding inputs | Track sanitized profiles |
| `artifacts/` runtime directories | Generated evidence | Track selected acceptance/RCA evidence only |
| `raw_yaml/` | Experiment input snapshots | Track only with source, license, and hash metadata |
| `artifacts/experiments/*/sources/` | External upstream source | Keep local or archive externally |
| `.tmp-*`, `.pytest-tmp-*`, `.venv-*` | Local execution state | Ignore |
| `.email-notify-outbox/`, `.planning/`, `.secrets/` | Local state or credentials | Ignore |
| `%LOCALAPPDATA%/ChaosAtlas/runs/` | Default unreviewed runtime output | Keep outside the repository |
| `%LOCALAPPDATA%/ChaosAtlas/archive/` | Local cleanup archives with manifests | Keep outside the repository |

## Mainline Entry Points

- `src/chaosatlas/cli.py`: the supported dry-run and live CLI.
- `src/chaosatlas/orchestration/engine.py`: the single `RunEngine` composition boundary and candidate lifecycle.
- `src/chaosatlas/orchestration/batch.py`: the shared bounded candidate loop used by both single-candidate and batch live requests.
- `src/chaosatlas/oracles/`: the `WorkflowOracle` contract and registry for HTTP, gRPC, Dify, and project extensions.
- `tools/chaosatlas.py`, `tools/run_closed_loop.py`, and `tools/chaosatlas_batch.py`: compatibility CLI wrappers only; they delegate to the packaged CLI.
- `tools/kubernetes_project_adapter.py`: read-only project inventory and dependency portrait.
- `tools/experiment_policy.py` and `tools/stop_policy.py`: candidate selection and stopping.
- `tools/knowledge_updater.py` and `tools/weakness_promotion_stage.py`: knowledge feedback and promotion gates.
- `tests/`: deterministic contract and regression coverage.

## Evidence Rule

Every retained runtime result should have a project, run identity, source/provenance hash, lifecycle status, cleanup status, and review status. A file that is merely a local rehearsal, cache, duplicate, or failed temporary attempt belongs outside the mainline snapshot even when it remains on disk.

New commands obtain external defaults from `src/chaosatlas/workspace.py`.
`CHAOSATLAS_STATE_ROOT` is the only supported override for the state root.
Run `scripts/check_workspace_hygiene.py` to detect local-state regressions.

## Migration Rule

This map is a logical classification, not a bulk move. Existing paths remain stable in this phase because reports and scripts reference them. Any later move must update references, preserve hashes, and pass the full regression suite.

