# Unified Chaos Experiment Protocol

## Goal

Make every ChaosAtlas project comparable by using the same experiment lifecycle,
evidence contract, mutation gate, cleanup policy, and review state. P02 is the
reference implementation. Existing completed experiments remain immutable and
are not rerun only to retrofit this protocol.

## Scope

This change standardizes the runtime lifecycle for project experiments:

1. project/static gate
2. namespace-local deployment and server-side dry-run
3. deterministic baseline and workload oracle
4. autonomous discovery or frozen candidate selection
5. deterministic mutation compilation with provenance
6. mutation execution gate
7. one-fault injection
8. injected-state confirmation
9. observation and oracle collection
10. fault removal
11. namespace recovery and washout
12. explicit Chaos resource cleanup confirmation
13. residual-resource audit
14. report hashing, sensitive-data scan, and human review

The protocol does not authorize deployment of a project whose static gate is
blocked. It does not authorize automatic knowledge-base updates. It does not
change the namespace boundary for a project.

## Architecture

The implementation has three layers:

- `open_discovery_compiler.py` and
  `open_discovery_mutation_compiler.py` remain deterministic, side-effect-free
  compilers. Model output may propose hypotheses, but it never calls
  `kubectl`.
- A shared lifecycle contract validates reports from project runners. Each
  runner supplies project-specific namespace, selector, workload, oracle, and
  diagnostics, while the lifecycle fields and failure semantics remain shared.
- Project adapters provide the narrow runtime details. P02 remains the
  reference adapter. P09 is upgraded to use the same mutation compilation,
  execution gate, and lifecycle report shape. P08 remains blocked until its
  static gate passes.

The shared layer must fail closed: an invalid namespace, selector, mutation
kind, missing injection confirmation, missing recovery, unconfirmed cleanup,
or residual Chaos resource makes the run ineligible for comparison.

## Lifecycle Contract

Every formal run report must contain:

- `schema_version`
- `project_id`
- `namespace`
- `arm`
- `mutation_id`
- `replicate`
- `mutation.path`
- `mutation.sha256`
- `baseline`
- `injection`
- `observation`
- `recovery`
- `cleanup`
- `washout`
- `diagnostics`
- `human_review`
- `status`

The lifecycle booleans have one meaning across projects:

- `baseline.pass=true`: the required baseline oracle successes were observed
  before applying the mutation.
- `injection.applied=true`: the apply command succeeded and the named Chaos
  object was observed with an injected count of at least one.
- `recovery.recovered=true`: the target workload and project namespace returned
  to the required ready state.
- `cleanup.absent_confirmed=true`: deletion was issued and a subsequent
  NotFound check confirmed the named Chaos object is absent.
- `washout.stable=true`: the configured stable-success count was reached after
  cleanup.
- `cleanup.residual_resources=[]`: the allowed residual audit found no
  `PodChaos`, `NetworkChaos`, or `StressChaos` resource in the permitted scope.

`status=completed` is valid only when the run passed the required lifecycle
checks. A failed apply remains a reportable failed run and must still attempt
cleanup if the apply result is ambiguous.

## Autonomous Discovery Contract

Autonomous discovery is a hypothesis-generation phase, not an execution phase.
Its output must include project identity, bounded fault family, target intent,
parameters, expected invariant, recovery expectation, and evidence references.
The compiler resolves targets against the frozen topology and runtime mapping,
generates a Chaos Mesh mutation, and records provenance and SHA-256.

No discovery output may directly contain or execute shell commands. No accepted
hypothesis is execution-ready until deterministic compilation and the runtime
execution gate both pass.

For P09, the existing 12-call discovery evidence remains frozen. The upgrade
must consume that evidence without issuing an additional DeepSeek call merely to
retrofit the execution path.

## Candidate Selection Contract

Candidate selection is separate from autonomous discovery but uses the same
runtime lifecycle after selection. The selection stage freezes:

- candidate pool hash
- arm and seed
- knowledge view hash, if applicable
- selected candidate IDs and ranks
- prompt and response hashes

Only selected candidates with a deterministic mutation mapping may enter runtime
execution. Selection output alone is not runtime evidence.

## Project Adapters

Each adapter must expose:

- `validate_static_gate()`
- `validate_mutation(document)`
- `collect_baseline()`
- `wait_injected(name)`
- `collect_observation()`
- `wait_recovery()`
- `delete_and_confirm_absent(name)`
- `collect_washout()`
- `collect_diagnostics()`
- `residual_chaos()`

The adapter may use project-specific ports, URLs, labels, and diagnostics, but
must not alter the shared lifecycle meanings or silently omit required evidence.

## Error Handling and Safety

- Only the explicitly authorized project namespace may be operated.
- Every run operates on one mutation at a time.
- Existing non-empty evidence directories are never overwritten; a new `rN`
  directory is required.
- Cleanup runs in `finally`-equivalent logic after any apply attempt.
- Ambiguous apply failures are recorded as failed runs and followed by cleanup
  and residual checks.
- API keys are read only by the model-call adapter when explicitly authorized;
  they are never printed, committed, or written into evidence.
- Reports retain `human_review=pending` and do not update the knowledge base.

## Comparison Rules

The comparison denominator is formal lifecycle-complete runs only. A run with
`baseline.pass=false`, `injection.applied=false`, `recovery.recovered=false`,
`cleanup.absent_confirmed=false`, `washout.stable=false`, or non-empty residual
Chaos resources is excluded from weakness-yield comparison and retained as an
explicit invalid or failed run.

Model hypotheses, static candidates, pilot plans, and preflight records are
reported separately from runtime-confirmed outcomes.

## Testing

The implementation must add tests for:

- shared lifecycle validation and fail-closed status derivation
- mutation provenance and SHA-256 consistency
- namespace and selector rejection
- cleanup confirmation and residual-resource rejection
- P09 discovery-to-mutation compilation without a model call
- P09 runner report compatibility with the shared lifecycle contract
- unchanged P02 gate and formal-batch behavior
- P08 static gate remaining deployment-blocked when its gate is incomplete

Tests must run offline. No test may read or print an API key or contact an
external model.

## Rollout

1. Add the shared lifecycle contract and tests.
2. Adapt P09 compilation and runtime reports.
3. Run focused tests, then the relevant full test subset.
4. Run P09 static/deployment gate and server-side dry-run before any new
   namespace mutation.
5. Execute only newly authorized P09 formal runs in a new evidence directory.
6. Verify reports, hashes, diagnostics, cleanup, residual resources, and
   sensitive-data scan.
7. Commit only protocol, necessary code, tests, and P09 evidence generated by
   this change. Leave unrelated worktree changes untouched.
