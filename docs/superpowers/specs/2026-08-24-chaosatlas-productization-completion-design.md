# ChaosAtlas Productization Completion Design

## Goal

Complete the current deterministic ChaosAtlas closed-loop runner before wiring in
the information-gain candidate/stop policy. The existing `chaosatlas.py run`
behavior remains the compatibility baseline; this work makes single and batch
runs auditable, resumable, and consistent for a deployed Kubernetes project.

## Scope

### In scope

- A stable single-command contract for profile, mode, kube context, candidate
  selection, approval, knowledge roots, and output directory.
- Batch-level manifest and summary over isolated candidate child runs.
- Candidate lifecycle states with fail-closed recovery and cleanup semantics.
- Resume/reconcile behavior that refuses changed inputs or already-mutated live
  runs.
- Structured aggregation of discovery, classification, RCA, knowledge, and
  cleanup outcomes.
- Regression tests for fake executor, dry-run, and context-pinned live paths.

### Out of scope

- Changing candidate ranking or stop decisions.
- Enabling information-gain policy as a default or guarded controller.
- New LLM providers or new fault families.
- Cross-project knowledge promotion without the existing validation gates.

## Architecture

The existing single-run pipeline remains authoritative:

```text
onboard -> inventory -> deployment detection -> candidate mapping
-> retrieval/advisory -> evidence plan -> preflight -> inject
-> observe -> recover -> cleanup -> classify -> RCA -> learn -> regression
```

`chaosatlas_batch.py` owns only batch coordination. Each candidate runs in an
immutable child directory and produces the same artifacts as a single run. The
parent writes a manifest before execution and a summary after every child,
including interrupted or blocked children.

## State and failure rules

Candidate states are:

```text
planned
preflight_blocked
live_completed
rca_completed
knowledge_written
cleanup_verified
failed
```

`cleanup_verified` is required for a successful live result. Recovery or cleanup
failure is never reported as a successful experiment. A batch is `completed`
only when every selected candidate reaches a terminal success state; otherwise
it is `partial`, `environment_blocked`, or `failed` according to deterministic
child results.

Resume is allowed only for dry-run or for live children that have not passed the
mutation boundary. The profile snapshot, explicit kube context, namespace,
candidate-space hash, and approval contract must match the original manifest.

## Artifacts

The batch root contains:

- `batch_manifest.json`: immutable inputs and candidate list;
- `batch_plan.json`: selected candidates and preflight planning result;
- `runs/<candidate>/...`: normal single-run artifacts;
- `batch_state.json`: append-only child state transitions;
- `batch_summary.json` and `summary.md`: deterministic aggregate result.

The summary must expose counts for planned, executed, confirmed findings,
defended outcomes, blocked outcomes, RCA confirmations, knowledge promotions,
and cleanup failures.

## Verification

The implementation is accepted when:

1. Existing focused tests remain green.
2. New tests prove batch aggregation for success, block, failure, and cleanup
   failure without performing a real mutation.
3. Resume rejects changed profile/context/candidate-space inputs.
4. Compileall and `git diff --check` pass.
5. The Sock Shop context-pinned dry-run and approved live canary preserve zero
   residue and the existing RCA/knowledge claim boundaries.

The later policy integration will consume these artifacts through an adapter;
it will not change this contract or the default deterministic path.
