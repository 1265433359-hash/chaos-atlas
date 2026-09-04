# Unified RunEngine Design

Date: 2026-09-04  
Status: proposed for implementation  
Project: ChaosAtlas

## 1. Purpose

ChaosAtlas currently has two orchestration paths. Dry-run uses
`tools/chaosatlas_orchestrator.py` with an offline adapter and a fake executor,
while live and live-batch execution are delegated through compatibility entry
points to `_legacy_chaosatlas.py` and `_legacy_chaosatlas_batch.py`.

This change will replace those parallel orchestration paths with one
`RunEngine`. Dry-run, single-candidate live execution, and multi-candidate live
execution will use the same stage machine, contracts, policy loop, artifact
writer, and result semantics. Modes will differ only through injected runtime
capabilities.

The migration preserves the existing ChaosAtlas method. It does not introduce
a separate four-application experiment runner and does not change verified
fault, classification, RCA, recovery, cleanup, or knowledge-promotion rules
without an explicit contract migration.

## 2. Goals

The unified engine must:

1. provide one orchestration implementation for dry-run and live modes;
2. treat a single-candidate run as a batch run with a budget of one;
3. retain stable candidate and causal identities;
4. retain deterministic safety, injection, observation, recovery, cleanup,
   classification, reproduction, RCA, and promotion gates;
5. support deterministic, LLM-backed, and future policy providers through one
   interface;
6. support HTTP, gRPC, Dify chatflow, and project workflow oracles through one
   registry;
7. write all run artifacts through one hashed artifact writer;
8. preserve current CLI behavior and explicit live approval;
9. support the Immich, ERPNext, Medusa, and Rocket.Chat capability-learning
   stage without project-specific orchestration forks; and
10. remove the legacy orchestration files after behavior and live-canary parity
    are verified.

## 3. Non-goals

This change does not:

- run Full/noKB/noLLM ablations on the four capability-learning projects;
- redesign the existing fault catalog;
- weaken namespace, selector, approval, cleanup, or recovery protections;
- automatically submit upstream issues;
- migrate or delete existing evidence archives;
- make synthetic dry-run evidence eligible for runtime claims; or
- execute high-risk database or storage faults against the preserved baseline
  namespaces.

## 4. Current State

The public CLI is `src/chaosatlas/cli.py`.

- Dry-run calls `tools.chaosatlas_orchestrator.run_closed_loop`.
- Live single-candidate execution calls
  `tools._legacy_chaosatlas.run_closed_loop`.
- Live batch execution is exposed through `tools.chaosatlas_batch`, which
  forwards to `tools._legacy_chaosatlas_batch`.
- The new dry-run orchestrator uses `OfflineProjectAdapter` and `FakeExecutor`.
- The live path uses `KubernetesProjectAdapter` and
  `KubernetesLifecycleExecutor`.
- Business probing is selected through hard-coded branching for HTTP, gRPC,
  and Dify chatflow behavior.

This split creates duplicate stage ownership and makes it possible for dry-run
and live results to diverge even when their project, seed, candidate pool, and
policy inputs are identical.

## 5. Target Architecture

The target call graph is:

```text
CLI
  -> RunRequest validation
  -> RunEngine
       -> ProjectAdapter
       -> CandidateProvider
       -> KnowledgeProvider
       -> PolicyProvider
       -> ApplicabilityGate
       -> LifecycleExecutor
            -> FaultExecutor
            -> WorkflowOracle
            -> EvidenceCollector
            -> RecoveryManager
            -> CleanupVerifier
       -> ResultClassifier
       -> ReproductionController
       -> RCAController
       -> KnowledgePromotionGate
       -> IssueDraftGenerator
       -> ArtifactWriter
```

The initial implementation will reuse existing functions behind these
interfaces. Moving code and changing algorithms are separate changes. During
the migration, existing behavior is wrapped first and refactored only after
parity is demonstrated.

## 6. Core Contracts

### 6.1 RunRequest

`RunRequest` is the validated input to every run. It contains:

- profile path;
- output root;
- mode (`dry-run` or `live`);
- seed;
- candidate limit or explicit candidate ID;
- knowledge read and write roots;
- policy configuration;
- Kubernetes context; and
- explicit live approval state.

Validation occurs before an output directory is mutated. Live execution
continues to require explicit approval, a fresh output directory, and a valid
namespace allow-list.

### 6.2 RunDependencies

`RunDependencies` contains the replaceable behavior used by the engine:

- project adapter;
- policy provider;
- lifecycle executor;
- oracle registry;
- knowledge provider;
- artifact writer; and
- clock and process runner where deterministic tests require injection.

Production dependencies are created by a composition root. Tests may provide
fakes, but the engine never selects a fake based on hidden conditions.

### 6.3 WorkflowOracle

Every business oracle implements one contract:

```text
prepare_fixture(run_context) -> FixtureResult
probe(phase, run_context) -> OracleResult
collect_evidence(run_context) -> EvidenceResult
cleanup_fixture(run_context) -> CleanupResult
```

`phase` is one of `baseline`, `observe`, or `recovery`. Oracle results contain
structured assertions, timings, redacted response summaries, created resource
identifiers, cleanup state, and evidence references. An oracle reports facts;
it does not classify a fault as a weakness or defense.

### 6.4 PolicyProvider

The policy provider receives only gate-eligible candidates, the allowed
knowledge view, project-local feedback, remaining budget, and mandatory work.
It returns structured recommendations for:

- next candidate;
- parameter level;
- reproduction, escalation, exploration, or stop;
- competing RCA hypotheses; and
- the next RCA evidence action.

The deterministic gate may reject or override any recommendation. Every
recommendation and override is recorded.

### 6.5 ArtifactWriter

One artifact writer owns stage envelopes, canonical JSON serialization,
hashes, aliases, checkpoints, and atomic writes. No mode-specific runner may
write a competing stage format.

## 7. Unified Stage Machine

Every run uses this ordered state machine:

```text
onboard
-> inventory
-> server_deployment_detection
-> mapping
-> retrieval
-> hypotheses
-> gate
-> baseline
-> select
-> execute
-> observe
-> recovery
-> cleanup
-> classify
-> reproduce
-> rca
-> learn
-> promote_defense
-> promote_weakness
-> regression
-> issue_draft
-> audit
-> complete
```

Stages may be skipped only with an explicit status and reason. A skipped or
planned stage is never represented as successful runtime evidence.

Mandatory pending work takes precedence over selecting a new candidate:

1. recover and clean up an active mutation;
2. complete pending anomaly reproductions;
3. complete required RCA evidence actions;
4. complete required parameter audits;
5. select a new eligible candidate; and
6. run the post-stop missed-anomaly audit.

## 8. Mode Semantics

### 8.1 Dry-run

Dry-run uses the same onboarding, inventory normalization, candidate identity,
knowledge retrieval, policy, gate, and evidence-plan code as live mode. It
uses a `PlanExecutor` that produces `not_run` execution stages with
`claim_scope: planned`.

Dry-run cannot emit a runtime weakness, defense, confirmed RCA, promoted
knowledge, or issue draft.

### 8.2 Live

Live uses the Kubernetes lifecycle and fault executors. Runtime claims require
confirmed injection, a valid baseline, business observations, recovery, and
cleanup evidence according to the existing deterministic contracts.

### 8.3 Single and batch

There is one candidate loop. A single-candidate run is configured with an
explicit candidate or a candidate budget of one. Batch execution uses the same
loop with a larger budget. There is no separate batch orchestrator.

## 9. Project Integration

The four capability-learning projects use the generic Kubernetes adapter and
project packages containing:

- one project profile;
- dependency edges;
- a deterministic synthetic fixture;
- a transactional workflow oracle;
- supported and inapplicable fault declarations;
- recovery and cleanup contracts; and
- sensitive-data redaction rules.

Their frozen order is:

1. Immich;
2. Medusa;
3. Rocket.Chat; and
4. ERPNext.

Only the complete method is run on these projects. Their purpose is to improve
capability coverage, discover tool failures, find reproducible application
anomalies, produce reviewable issue drafts, and build evidence-gated knowledge
for later evaluation projects.

## 10. Evidence and Issue Drafts

An issue draft is a terminal consumer of confirmed evidence. It cannot alter a
classification or promotion decision.

An issue draft requires:

- a frozen project revision and deployment manifest;
- a successful clean baseline;
- confirmed fault injection;
- deterministic business impact;
- three independent reproductions with the same causal identity;
- successful recovery and cleanup for every included reproduction;
- at least service-boundary RCA; and
- a complete redacted evidence index.

Drafts contain environment, version, minimal reproduction, expected and actual
behavior, impact, reproduction table, RCA scope, recovery behavior, and
redacted evidence references. The generator writes Markdown only and never
submits to an upstream service.

## 11. Error Handling and Safety

- Invalid method inputs terminate as `method_invalid` before live mutation.
- Missing platform prerequisites terminate as `environment_blocked` and do not
  label the application.
- Unconfirmed injection cannot support a weakness or defense result.
- Failed recovery or cleanup stops the run before another candidate executes.
- An interrupted live run prioritizes cleanup and writes an interruption
  artifact.
- Output directories are created atomically and live runs refuse non-empty
  targets unless a future audited resume contract explicitly allows them.
- Namespace, selector, owner-label, and secret-redaction gates remain
  deterministic and fail closed.
- Synthetic credentials and data are isolated from user data.

## 12. Migration Strategy

The migration is incremental:

1. Add characterization tests around current dry-run, live, and live-batch
   behavior.
2. Add shared request, dependency, stage-result, oracle, policy, and artifact
   contracts.
3. Add the unified `RunEngine` using wrappers around existing implementations.
4. Route dry-run through `RunEngine` with `PlanExecutor`.
5. Route single-candidate live execution through the same engine.
6. Route multi-candidate live execution through the same candidate loop.
7. Replace hard-coded oracle branching with `OracleRegistry` while preserving
   HTTP, gRPC, and Dify behavior.
8. Route existing Dify commands and canaries through the unified entry point.
9. Add the four project packages and workflow oracles.
10. Run parity, repository acceptance, and live canary verification.
11. Remove compatibility forwarding and legacy orchestration files only after
    no references remain.

Each step must leave the repository runnable. Legacy removal is the last step,
not the first.

## 13. Testing Strategy

### 13.1 Contract tests

- Validate request and dependency construction.
- Validate every stage result and artifact envelope.
- Validate oracle result, fixture, policy decision, and cleanup schemas.
- Validate secret redaction and canonical hashing.

### 13.2 Characterization and parity tests

For existing fixtures and fixed seeds, compare old and unified paths for:

- project inventory;
- candidate IDs and causal identities;
- candidate ordering;
- gate outcomes;
- fault manifests;
- runtime classifications;
- recovery and cleanup outcomes;
- RCA transitions; and
- knowledge promotion decisions.

Timestamp, path, and process-ID fields may be normalized. Semantic fields may
not differ without an explicit reviewed migration.

### 13.3 Mode tests

- Dry-run performs no Kubernetes mutation.
- Dry-run emits no runtime claim.
- Live mode requires explicit approval.
- Single and batch modes use the same loop.
- Policy rejection and deterministic fallback are recorded.
- Interruption triggers cleanup before completion.

### 13.4 Live canaries

Before the four applications produce formal evidence:

1. run the existing Dify HTTP/chatflow canary through the unified engine;
2. verify injection, observation, recovery, and cleanup;
3. verify no Chaos Mesh child resources remain;
4. verify the evidence archive hashes; and
5. run one low-risk canary for each new workflow oracle.

## 14. Acceptance Criteria

The merge is complete only when:

1. dry-run, single live, and batch live enter one `RunEngine`;
2. there is one candidate loop and one artifact writer;
3. `FakeExecutor` no longer represents dry-run execution as synthetic runtime
   behavior;
4. all oracle types resolve through `OracleRegistry`;
5. existing offline, Dify, fault, lifecycle, RCA, knowledge, and cleanup tests
   pass;
6. old/new semantic parity passes for fixed fixtures and seeds;
7. the Dify unified live canary passes with complete recovery and cleanup;
8. CLI compatibility is preserved or an explicit migration message is emitted;
9. no production code imports `_legacy_chaosatlas.py` or
   `_legacy_chaosatlas_batch.py`;
10. both legacy orchestration files are deleted;
11. repository documentation names the unified engine as the only supported
    orchestration path; and
12. the four capability-learning projects can enter the unified engine through
    project profiles and registered workflow oracles.

## 15. Delivery Boundary

The unified engine merge is completed and verified before the first formal
four-project evidence run. Project package development may begin after the
shared oracle and project contracts are frozen, but no four-project runtime
artifact is promoted as formal evidence until the unified engine acceptance
criteria pass.
