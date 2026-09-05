# Unified RunEngine Implementation Report

Date: 2026-09-05

Project: ChaosAtlas

Result: implementation verified; Chatflow canary externally blocked

## Delivered architecture

- `src/chaosatlas/orchestration/engine.py` is the single composition boundary for dry-run and live requests.
- Every public live request enters the shared bounded candidate loop in `src/chaosatlas/orchestration/batch.py`; a single-candidate request uses a budget of one.
- Dry-run uses `PlanExecutor` and emits `not_run` observations with `claim_scope: planned`; it cannot create runtime claims.
- `RunRequest` and `RunDependencies` centralize validated inputs and replaceable runtime capabilities.
- HTTP, gRPC, and Dify Chatflow resolve through `OracleRegistry` and implement the shared `WorkflowOracle` contract.
- The old `_legacy_chaosatlas.py` and `_legacy_chaosatlas_batch.py` implementations were removed. Compatibility commands delegate to the packaged CLI.
- Resume now rejects modified stage artifacts by verifying canonical payload hashes.
- Candidate selection, stop decisions, evidence plans, cleanup, summaries, and stage hashes are persisted without promoting plans to runtime evidence.
- All Oracle kinds now receive an owner-scoped Chaos Mesh cleanup sweep after an applied mutation.

## Verification

- Full regression suite: `230 passed`.
- Repository acceptance: `success` (compileall, architecture contracts, two dry-runs, product boundary).
- Product snapshot: packaged CLI opened successfully and imported `RunEngine`, `RunDependencies`, and the default Oracle registry.
- Production Python search found no imports of either removed legacy orchestrator.

## Live canary

Operational canary profile:
`projects/dify-kubernetes/profile-http-canary.json`.

Verified run:
`.runs/unified-engine-http-canary-20260905-002`.

The candidate killed one `dify-k8s-api` Pod through the unified engine. The run recorded:

- batch status: `completed`;
- child status: `live_completed`;
- cleanup status: `verified`;
- API Deployment after recovery: `1/1` Ready;
- owner-scoped Chaos Mesh scan: 22 resource types;
- residual resources: `0`;
- independently verified remaining Chaos Mesh resources: none.

The HTTP health canary validates orchestration, mutation, observation, recovery,
artifact, and cleanup behavior. It is not accepted as a substitute for the
Chatflow business oracle and does not create a confirmed application issue.

## External blocker

The Chatflow canary reached the unified engine but stopped before injection.
The Dify workflow's configured DeepSeek provider returned HTTP 402 for
insufficient account balance. ChaosAtlas correctly refused to inject when the
business baseline was invalid. That run is retained at
`.runs/unified-engine-canary-20260905-001`; it has no residual Chaos Mesh
resources and supports only an environment-blocked conclusion.

Chatflow live acceptance can be repeated after the model provider is funded or
the test workflow is switched to an available model. No code change is needed
to bypass the gate, and bypassing it would invalidate the evidence contract.
