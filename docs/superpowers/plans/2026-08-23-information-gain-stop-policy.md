# Information-Gain Stop Policy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace novelty/repetition-only stopping with a deterministic, evidence-driven selector that chooses the next chaos experiment by expected decision value and stops when further experiments cannot change the conclusion.

**Architecture:** Keep static candidate enumeration and runtime classification as the authoritative layers. Add a small policy module that canonicalizes causal identity, tracks candidate state/posteriors, computes expected information gain per cost, and emits `next_experiment` or a typed `stop_reason`. The LLM remains advisory: it may propose competing hypotheses and discriminating observations only for allow-listed candidate IDs.

**Tech Stack:** Python 3, existing JSON schemas, pytest, current `decision_engine.py` and native discovery artifacts.

---

## Deployment Model

This feature is deployed as an offline-first policy layer inside the existing
ChaosAtlas runner. It does not become an autonomous LLM agent and it does not
apply Kubernetes mutations by itself.

```text
static topology/profile
        |
        v
candidate_coverage_denominator.py
        |
        v
causal clusters + candidate registry
        |
        +--> optional LLM advisory: competing hypotheses only
        |
        v
experiment_value.py
        |
        +--> decision_engine.py: hard filters and ranking
        +--> stop_policy.py: next experiment or stop reason
        |
        v
existing compiler/runner/classifier
        |
        v
state artifact + replay report
```

The policy is introduced in four rollout modes:

1. **Observe:** calculate policy decisions but continue using the existing selector.
2. **Shadow:** record both decisions and compare them without changing execution.
3. **Guarded:** allow the new selector only for candidates that pass all existing applicability, recovery, and business-oracle gates.
4. **Default:** make the new selector the normal path after replay and canary thresholds pass.

Every policy output must include `policy_version`, input hashes, selected
candidate IDs, score components, and a typed `stop_reason`. A policy failure
falls back to the existing deterministic ranking; it never falls back to an
unconstrained LLM choice.

## State and Configuration

The implementation uses a versioned JSON state artifact per project and seed:

```json
{
  "schema_version": "chaosatlas-experiment-policy-state-v1",
  "policy_version": "ig-stop-v1",
  "project_id": "P02",
  "seed": 1001,
  "candidate_states": {
    "candidate-id": {
      "causal_cluster_id": "sha256:...",
      "status": "unknown",
      "posterior": {"weakness": 0.33, "defended": 0.33, "below_threshold": 0.34},
      "run_count": 0,
      "observed_outcomes": []
    }
  },
  "history": [],
  "stop_reason": null
}
```

Thresholds are explicit CLI/config values, not hidden prompt instructions:

```text
resolved_confidence = 0.90
minimum_value_per_cost = 0.05
maximum_blast_radius = existing runtime gate limit
boundary_search = enabled
llm_advisory = optional
```

## Deployment Phases

### Phase 0: Freeze and baseline

Freeze the candidate denominator, knowledge snapshot, runner version, and
classification schema for one project/seed. Run the current repetition rule
against the same frozen inputs and save its selected IDs and stop behavior.
This is the comparison baseline and must not include runtime mutation.

### Phase 1: Offline policy implementation

Implement Tasks 1-4 below. Run unit tests with synthetic candidates and known
classification outcomes. Then replay frozen artifacts using the new policy.
No Kubernetes access, model request, or mutation compiler invocation is allowed
in this phase.

### Phase 2: Shadow deployment

Add a `--policy-mode shadow` path to the existing orchestration entry point.
The runner still executes the legacy selection, while the policy writes a
shadow decision beside each run. Compare:

- number of experiments selected;
- unique causal clusters covered;
- blocked candidates incorrectly proposed;
- unresolved candidate uncertainty;
- decisions changed by the new policy;
- policy computation failures.

Shadow mode is accepted only when there are zero blocked-candidate proposals,
zero schema violations, and all policy outputs are reproducible for the same
input hashes.

### Phase 3: One-project guarded canary

Enable `--policy-mode guarded` for one already-qualified project such as the
existing Sock Shop or Train Ticket path. The new selector may choose only
`eligible` candidates with a verified selector, business oracle, recovery
contract, and cleanup plan. Keep an operator approval before each mutation.

Stop the canary and revert to shadow mode if any of these occur:

- a policy-selected candidate is not compilable;
- cleanup or recovery evidence is missing;
- the selector proposes a candidate outside the frozen denominator;
- the new policy increases failed/invalid runs compared with baseline;
- a policy error requires LLM output to make an execution decision.

### Phase 4: Default rollout and maintenance

After the canary passes, make guarded mode the default for the qualified
project family. Keep legacy ranking behind `--policy-mode legacy` for rollback.
Whenever the candidate schema, knowledge snapshot schema, runtime classifier,
or policy weights change, increment `policy_version` and repeat Phase 0-2.

## Rollback

Rollback is configuration-only: set `--policy-mode legacy`, retain the policy
state and shadow artifacts for diagnosis, and do not delete them. A rollback
does not undo an already completed mutation; runtime cleanup remains owned by
the existing runner and recovery contract.

### Task 1: Canonical causal identity and experiment clusters

**Files:**
- Modify: `tools/candidate_coverage_denominator.py`
- Modify: `tools/chaosatlas_hypothesis.py`
- Test: `tools/tests/test_candidate_coverage_denominator.py`
- Test: `tools/tests/test_chaosatlas_hypothesis.py`

- [ ] Add `causal_identity` to every native candidate with `source`, `target`, `fault_family`, `oracle`, `recovery_contract`, and normalized `parameter_bucket`.
- [ ] Add `causal_cluster_id`, derived from the identity fields above and independent of prompt wording or candidate display name.
- [ ] Add `parameter_domain` for intensity-bearing faults so 100ms and 500ms are represented as points on one experiment line, not unrelated discoveries.
- [ ] Test that renamed/textually different candidates with the same causal identity share a cluster, while different fault families do not.

### Task 2: Candidate state and posterior update

**Files:**
- Create: `tools/experiment_value.py`
- Test: `tools/tests/test_experiment_value.py`

- [ ] Define `CandidateState` fields: `status`, `posterior`, `evidence_quality`, `observed_outcomes`, `last_run_sha256`, and `run_count`.
- [ ] Implement `update_candidate_state(state, classification, evidence_quality)` using deterministic runtime classifications only.
- [ ] Implement `posterior_entropy(posterior)` and `decision_confidence(posterior)` with fail-closed handling for missing or invalid probabilities.
- [ ] Test transitions for `unknown -> below_threshold`, `unknown -> weakness`, repeated same outcomes, and invalid evidence.

### Task 3: Expected-value next-experiment selector

**Files:**
- Modify: `tools/decision_engine.py`
- Modify: `tools/experiment_value.py`
- Test: `tools/tests/test_decision_engine.py`
- Test: `tools/tests/test_experiment_value.py`

- [ ] Implement `score_experiment(candidate, state, context)` with these auditable components: uncertainty reduction, decision impact, graph/coverage gain, transfer value, boundary proximity, execution cost, blast radius, and causal redundancy.
- [ ] Implement `select_next_experiment(candidates, states, context)` returning the highest `value_per_cost`, deterministic tie-breaking by `candidate_id`.
- [ ] Ensure blocked candidates are never selected and the LLM cannot introduce an ID outside the static candidate set.
- [ ] Test that an uncertain boundary candidate outranks a repeated low-information candidate, and that a high-risk candidate is downgraded when an equivalent lower-risk candidate exists.

### Task 4: Typed stopping policy and intensity ladder

**Files:**
- Create: `tools/stop_policy.py`
- Modify: `tools/experiment_value.py`
- Test: `tools/tests/test_stop_policy.py`

- [ ] Implement `evaluate_stop(candidates, states, budget, thresholds)` with only four terminal reasons: `resolved`, `decision_irrelevant`, `blocked`, and `low_expected_value`.
- [ ] Add an intensity-ladder planner that proposes low, medium, boundary, then binary-search points for the same causal cluster.
- [ ] Stop a cluster when confidence is at least `0.90`, the operational decision is invariant across possible outcomes, or the best remaining value-per-cost is below the configured threshold.
- [ ] Test that textual repetition alone never stops a cluster and that a new intensity near a decision boundary remains selectable.

### Task 5: Offline replay evaluation and documentation

**Files:**
- Create: `tools/evaluate_experiment_value_policy.py`
- Test: `tools/tests/test_evaluate_experiment_value_policy.py`
- Modify: `docs/CHAOSATLAS_METHOD_DETAILED_FOR_SUPERVISOR_2026-08-16.md`

- [ ] Replay frozen experiment records without cluster access or model calls.
- [ ] Compare the current repetition rule with the new policy on experiments used, unique causal clusters covered, unresolved uncertainty, and decision changes discovered.
- [ ] Require the replay report to record `policy_version`, input hashes, selected candidate IDs, and `stop_reason`.
- [ ] Document that LLM output is advisory and that runtime classification, posterior updates, selection, and stopping are deterministic.

### Task 6: Verification

- [ ] Run focused tests:

```powershell
pytest -q tools/tests/test_candidate_coverage_denominator.py tools/tests/test_chaosatlas_hypothesis.py tools/tests/test_experiment_value.py tools/tests/test_stop_policy.py tools/tests/test_decision_engine.py
```

- [ ] Run the full test suite:

```powershell
pytest -q tools/tests
```

- [ ] Run `python -m py_compile` on all modified Python files and `git diff --check`.
- [ ] Confirm no cluster, mutation, external model request, or secret access occurs during replay verification.

### Task 7: Orchestration integration and deployment modes

**Files:**
- Modify: `tools/run_native_full_discovery.py`
- Modify: `tools/main_experiment_orchestrator.py`
- Create: `tools/experiment_policy_cli.py`
- Test: `tools/tests/test_experiment_policy_cli.py`

- [ ] Add `--policy-mode legacy|observe|shadow|guarded|default`, defaulting to `legacy` until the canary is approved.
- [ ] Add `--policy-state PATH` and `--policy-config PATH`; reject missing or hash-mismatched frozen inputs before selection.
- [ ] In `observe` mode, calculate and print the decision but do not alter the selected candidate.
- [ ] In `shadow` mode, write a sidecar JSON decision next to the legacy run record.
- [ ] In `guarded` and `default` modes, pass only the policy-selected allow-listed candidate into the existing compiler/runner after all existing gates pass.
- [ ] Test that malformed policy output, unknown candidate IDs, and blocked candidates fall back to legacy ranking without invoking an LLM.

### Task 8: Shadow report and canary gate

**Files:**
- Create: `tools/evaluate_policy_rollout.py`
- Test: `tools/tests/test_evaluate_policy_rollout.py`
- Modify: `docs/CHAOSATLAS_METHOD_DETAILED_FOR_SUPERVISOR_2026-08-16.md`

- [ ] Generate a report comparing legacy and policy decisions from identical frozen inputs.
- [ ] Fail the report when reproducibility hashes differ, blocked candidates are selected, or any policy output lacks a typed stop reason.
- [ ] Add canary acceptance thresholds: zero safety-gate regressions, zero out-of-denominator selections, deterministic replay equality, and no increase in invalid runtime classifications.
- [ ] Document deployment modes, rollback, artifact locations, and the separation between LLM advisory output and deterministic execution control.

## Operational Runbook

Before a real run:

```powershell
python tools/project_onboarding.py --profile artifacts/project_profiles/sock-shop/project_profile.json
python tools/experiment_policy_cli.py --mode shadow --candidates artifacts/policy-rollout/sock-shop-r1/candidate-denominator.json --state artifacts/policy-rollout/sock-shop-r1/policy-state-r1.json
```

Review the shadow report. If it passes, run the guarded canary with the same
frozen candidate denominator and seed. After each run, update the state only
from the deterministic runtime classifier, then ask the policy for the next
candidate. Never update posterior state from an LLM verdict alone.

At completion, the run directory must contain:

```text
candidate-denominator.json
policy-state.json
policy-decisions.jsonl
shadow-or-canary-report.json
runtime-classifications/
stop-record.json
```

The deployment is considered complete only when the policy replay is
deterministic, the canary passes all safety gates, and the final stop record
explains why no remaining candidate could change the decision.
