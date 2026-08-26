# ChaosAtlas Closed-Loop Integration Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate causal clustering, evidence-driven experiment selection, typed stopping, and guarded knowledge feedback into the existing ChaosAtlas discovery/runtime/RCA pipeline without allowing runtime leakage into static discovery or allowing the LLM to control execution.

**Architecture:** Keep `run_native_full_discovery.py` responsible for static candidate generation and bounded LLM advisory output. Insert a deterministic policy layer between the validated discovery handoff and `open_discovery_mutation_compiler.py`. Feed only deterministic runtime classifications into a project-local policy state; use the existing `feedback_protocol.py` and `knowledge_updater.py` for human-gated formal knowledge promotion. Keep the RCA evidence-action loop separate from the discovery fault-candidate loop, sharing only canonical causal identity and evidence-quality primitives.

**Tech Stack:** Python 3, existing JSON artifacts, pytest, current native discovery compiler, runtime applicability gates, deterministic classifiers, and knowledge snapshots.

---

## Current Integration Points

The current native path already performs these steps:

```text
run_native_full_discovery.run_matrix
  -> build_candidate_space / build_coverage_denominator
  -> build_messages / bounded LLM hypotheses
  -> build_discovery_handoff
  -> open_discovery_mutation_compiler.compile_payload
  -> runtime runner and classifier outside the discovery preflight
```

The current feedback path already provides:

```text
feedback_protocol.classify_outcome
  -> build_feedback_card
  -> human_reviewed boundary
  -> build_next_kb for later projects
knowledge_updater.backfill
  -> selection_experience / judgment_experience audit updates
decision_engine.rank
  -> frozen knowledge snapshot scoring
```

The new policy must use these boundaries rather than creating a second mutation
compiler, a second runtime classifier, or a second formal knowledge format.

## Data-Flow Contract

The implementation produces four separate artifacts:

```text
coverage_denominator/seed-*.json   static-only candidate universe
policy-state.json                   project-local mutable experiment state
policy-decisions.jsonl              every selection and stop decision
feedback-cards/*.json               evidence-backed, reviewable proposals
```

`coverage_denominator` must never contain runtime observations, classifications,
RCA results, or LLM-selected candidate IDs. `policy-state` may contain runtime
outcomes for the current project, but it must not be used to rewrite the frozen
denominator. `feedback-cards` may retain audit evidence; only reviewed
abstractions may enter a later-project knowledge snapshot.

## Rollout Modes

Add these modes to the native runner, with `legacy` as the default:

```text
legacy   preserve the current selection and four-hypothesis compilation path
observe  compute policy output but do not change the selected hypotheses
shadow   persist legacy and policy decisions side by side
guarded  execute only policy-selected candidates that pass all existing gates
default  alias for guarded after the canary gate is accepted
```

Any policy validation error, unknown candidate ID, missing state, or blocked
candidate must fail closed to legacy selection in `observe`/`shadow` and stop
before mutation in `guarded`/`default`.

### Task 1: Freeze the current baseline and policy schemas

**Files:**
- Create: `tools/experiment_policy_schema.py`
- Create: `tools/tests/test_experiment_policy_schema.py`
- Create: `artifacts/policy-rollout/sock-shop-r1/README.md`

- [ ] Define schema constants for `causal_identity`, `policy_state`, `policy_decision`, and `stop_record`.
- [ ] Require every policy artifact to include `schema_version`, `policy_version`, `project_id`, `project_commit`, `seed`, and input SHA-256 values.
- [ ] Define the candidate state fields `status`, `posterior`, `evidence_quality`, `run_count`, `observed_outcomes`, and `last_result_sha256`.
- [ ] Define the only legal stop reasons as `resolved`, `decision_irrelevant`, `blocked`, and `low_expected_value`.
- [ ] Add fixtures copied from an existing static Sock Shop denominator and one deterministic runtime classification; do not include secrets or live cluster identifiers.
- [ ] Test rejection of missing hashes, invalid statuses, probabilities outside `[0, 1]`, and unknown stop reasons.

### Task 2: Canonicalize causal identity and cluster candidates

**Files:**
- Create: `tools/causal_identity.py`
- Modify: `tools/candidate_coverage_denominator.py`
- Modify: `tools/chaosatlas_hypothesis.py`
- Test: `tools/tests/test_causal_identity.py`
- Test: `tools/tests/test_candidate_coverage_denominator.py`
- Test: `tools/tests/test_chaosatlas_hypothesis.py`

- [ ] Implement `canonical_causal_identity(candidate)` using normalized source, target, target kind, fault family, business-oracle ID, recovery-contract ID, and parameter domain; exclude prompt wording and display names.
- [ ] Implement `causal_cluster_id(candidate)` as a stable SHA-256 over the canonical identity.
- [ ] Add `causal_identity`, `causal_cluster_id`, and `parameter_domain` to native candidates produced by `build_candidate_space`.
- [ ] Attach the same identity to validated LLM hypotheses only after their target and fault family match the static candidate denominator.
- [ ] Test that renamed hypotheses with the same causal identity share a cluster, that different fault families do not, and that parameter points such as 100ms and 500ms share a domain while retaining distinct parameter values.

### Task 3: Add project-local state and deterministic outcome updates

**Files:**
- Create: `tools/experiment_policy.py`
- Test: `tools/tests/test_experiment_policy.py`

- [ ] Implement `new_policy_state(project_id, project_commit, seed, candidates)` with one state row per static candidate and no LLM-derived status.
- [ ] Implement `update_candidate_state(state, runtime_result)` using only `feedback_protocol.classify_outcome` or an already validated deterministic classification.
- [ ] Map `confirmed_weakness`, `protected`, `latent_risk`, `unsupported`, `environment_blocked`, and `method_invalid` into candidate-state updates without treating `unsupported` as `protected`.
- [ ] Implement `posterior_entropy` and `decision_confidence`; invalid or missing probabilities must return a fail-closed uncertainty state.
- [ ] Persist state atomically with input hashes and append-only decision history.
- [ ] Test that an LLM string containing a verdict cannot update state, that environment-blocked runs do not become defenses, and that repeated deterministic outcomes update run count and evidence quality.

### Task 4: Implement value-based selection and typed stopping

**Files:**
- Modify: `tools/experiment_policy.py`
- Create: `tools/stop_policy.py`
- Modify: `tools/decision_engine.py`
- Test: `tools/tests/test_experiment_policy.py`
- Test: `tools/tests/test_stop_policy.py`
- Test: `tools/tests/test_decision_engine.py`

- [ ] Implement `score_experiment(candidate, state, context)` with explicit components for uncertainty reduction, decision impact, causal coverage, boundary proximity, transfer value, execution cost, blast radius, and causal redundancy.
- [ ] Reuse `decision_engine` hard filters and frozen knowledge snapshots before applying value scoring; a value score must never revive a blocked candidate.
- [ ] Implement `select_next_experiment(candidates, states, context, budget)` with deterministic tie-breaking by `causal_cluster_id` and `candidate_id`.
- [ ] Implement `evaluate_stop(candidates, states, context)` with the four legal stop reasons and a full score breakdown in the stop record.
- [ ] Implement `plan_intensity_step` for low, medium, boundary, and binary-search parameter points, while allowing a non-monotonicity flag to disable binary search.
- [ ] Test that a high-value uncertain boundary candidate outranks a repeated candidate, that a blocked candidate is never selected, that textual novelty alone cannot stop a cluster, and that all possible outcomes being decision-equivalent produces `decision_irrelevant`.

### Task 5: Insert policy selection into native discovery

**Files:**
- Modify: `tools/run_native_full_discovery.py`
- Modify: `tools/open_discovery_compiler.py`
- Create: `tools/experiment_policy_cli.py`
- Test: `tools/tests/test_run_native_full_discovery.py`
- Test: `tools/tests/test_experiment_policy_cli.py`

- [ ] Add `--policy-mode`, `--policy-state`, `--policy-config`, and `--policy-budget` arguments while preserving the current default behavior under `legacy`.
- [ ] Keep `build_candidate_space` and `build_coverage_denominator` before the LLM call and keep their runtime-feedback rejection checks unchanged.
- [ ] After `build_discovery_handoff` validates the bounded LLM hypotheses, materialize an allow-listed candidate registry keyed by static candidate ID and causal cluster.
- [ ] In `observe` and `shadow`, compute policy selection and stop output but compile the legacy selected hypotheses; write `policy-decisions.jsonl` beside the existing `handoff.json` and `mutations.json`.
- [ ] In `guarded` and `default`, compile only policy-selected hypotheses whose IDs, signatures, selectors, parameters, and recovery contracts match the frozen registry.
- [ ] Preserve the current four-hypothesis baseline in `legacy`; policy budget changes must be recorded explicitly and must not silently alter the baseline arm.
- [ ] Test legacy output compatibility, shadow sidecar generation, unknown-ID rejection, blocked-candidate rejection, and guarded compilation with a synthetic two-candidate fixture.

### Task 6: Connect runtime classifications to policy state

**Files:**
- Create: `tools/experiment_policy_feedback.py`
- Modify: `tools/classify_runtime_result.py`
- Modify: `tools/feedback_protocol.py`
- Test: `tools/tests/test_experiment_policy_feedback.py`
- Test: `tools/tests/test_classify_runtime_result.py`
- Test: `tools/tests/test_feedback_protocol.py`

- [ ] Implement `ingest_runtime_result(policy_state, result_path)` that reads the deterministic classification artifact, verifies its input hash and candidate signature, and calls `update_candidate_state`.
- [ ] Add causal identity and policy provenance to the audit portion of a feedback card without exposing them as executable mutation fields.
- [ ] Preserve `feedback_protocol` rules: runtime evidence must be complete for `confirmed_weakness` or `protected`, and `environment_blocked`/`method_invalid` cannot promote knowledge.
- [ ] Write a policy-state update record after every valid classification and refuse same-round use of a formal cross-project knowledge update.
- [ ] Test hash mismatch, candidate-signature mismatch, incomplete defense evidence, same-round feedback, and successful weakness-state updates.

### Task 7: Reuse existing knowledge promotion without contamination

**Files:**
- Modify: `tools/knowledge_updater.py`
- Modify: `tools/decision_engine.py`
- Create: `tools/policy_calibration.py`
- Test: `tools/tests/test_knowledge_updater.py`
- Test: `tools/tests/test_policy_calibration.py`

- [ ] Keep `knowledge_updater.backfill` as the formal SE/JE/DP update path; add policy evidence references rather than duplicating those libraries.
- [ ] Record selection yield, boundary discovery, protected-waste, and invalid-run counters in a separate versioned `policy_calibration.json` artifact.
- [ ] Use `feedback_protocol.build_next_kb` and `knowledge_projection` for later-project snapshots; never add raw runtime observations or mutation paths to a knowledge prompt.
- [ ] Add confidence decay or contest handling when strong counter-examples appear, following the existing `counter_examples` and adjudication behavior.
- [ ] Make `decision_engine` consume only a frozen, validated snapshot during replay and canary selection.
- [ ] Test that accepted knowledge changes policy scores in a later project, rejected/pending cards do not, and the same project/round cannot feed itself.

### Task 8: Keep RCA action selection separate but compatible

**Files:**
- Create: `tools/rca_policy_adapter.py`
- Modify: `tools/rca_loop.py`
- Modify: `tools/rca_runtime_loop.py`
- Test: `tools/tests/test_rca_policy_adapter.py`
- Test: `tools/tests/test_rca_loop.py`

- [ ] Convert RCA evidence actions into a separate `action_kind` schema; do not treat an evidence-collection action as a new fault candidate.
- [ ] Reuse causal identity, evidence quality, cost, and stop-reason primitives from `experiment_policy.py` while preserving `rca_loop.evaluate_rca_transition` as the RCA state machine.
- [ ] Allow the policy to prioritize a discriminating evidence action when multiple RCA hypotheses remain unresolved.
- [ ] Stop RCA evidence collection when the RCA transition is resolved, evidence is decision-irrelevant, or no admissible action remains; do not infer a defense from missing evidence.
- [ ] Test that discovery candidates and RCA actions cannot share IDs or accidentally update each other’s state.

### Task 9: Offline replay, shadow comparison, and canary gate

**Files:**
- Create: `tools/evaluate_closed_loop_policy.py`
- Test: `tools/tests/test_evaluate_closed_loop_policy.py`
- Modify: `tools/open_discovery_evaluator.py`

- [ ] Replay frozen discovery and runtime artifacts without cluster access, mutation application, secrets, or model requests.
- [ ] Compare legacy versus policy arms using project-seed as the unit of analysis, not individual LLM hypotheses.
- [ ] Report experiment count, unique causal clusters, confirmed-weakness yield, protected-waste, method-invalid rate, unresolved uncertainty, boundary discoveries, and stop reasons.
- [ ] Require deterministic replay equality for identical input hashes and fail the report on blocked selections, out-of-denominator IDs, or missing provenance.
- [ ] Define the guarded canary gate as zero safety regressions, zero out-of-denominator selections, no increase in invalid runtime classifications, and a non-inferior confirmed-weakness yield at the same budget.
- [ ] Keep a held-out project/seed set that is never used to update policy calibration or formal knowledge.

### Task 10: Deployment and rollback

**Files:**
- Modify: `tools/main_experiment_orchestrator.py`
- Modify: `tools/run_native_full_discovery.py`
- Create: `docs/CHAOSATLAS_CLOSED_LOOP_RUNBOOK.md`
- Test: `tools/tests/test_main_experiment_orchestrator.py`

- [ ] Add policy mode and policy artifact paths to the main experiment ledger without changing the official ChaosEater arm or the existing no-KB arm.
- [ ] Run `legacy` and `shadow` on one frozen project first; retain all existing outputs and add policy sidecars only.
- [ ] Enable `guarded` for one project with operator approval per mutation after the canary gate passes.
- [ ] Make `default` an explicit configuration change, not an implicit fallback.
- [ ] Roll back by setting `--policy-mode legacy`; retain state, decision, and feedback artifacts for diagnosis.
- [ ] Document that a rollback does not replace existing runtime cleanup and recovery ownership.

## Verification Order

Run focused tests first:

```powershell
pytest -q tools/tests/test_experiment_policy_schema.py tools/tests/test_causal_identity.py tools/tests/test_experiment_policy.py tools/tests/test_stop_policy.py tools/tests/test_experiment_policy_feedback.py tools/tests/test_policy_calibration.py tools/tests/test_rca_policy_adapter.py
```

Then run integration tests:

```powershell
pytest -q tools/tests/test_run_native_full_discovery.py tools/tests/test_open_discovery_compiler.py tools/tests/test_feedback_protocol.py tools/tests/test_knowledge_updater.py tools/tests/test_decision_engine.py tools/tests/test_open_discovery_evaluator.py
```

Finally run the full tool suite, compile modified Python files, and run
`git diff --check`. All replay tests must remain offline. No DeepSeek request,
cluster mutation, or formal knowledge write is allowed until the shadow report
passes its gate.

## Expected Result

The integrated method should produce this behavior:

```text
LLM proposes bounded hypotheses
  -> deterministic policy chooses the next admissible experiment
  -> existing compiler/gates/runner execute it
  -> deterministic classifier updates project-local state
  -> reviewed evidence updates later-project knowledge
  -> next selection uses the new state and knowledge
  -> typed stop record ends the loop when more experiments cannot change the decision
```

The first defensible claim is therefore not “the LLM learns by itself”. It is:
“ChaosAtlas implements a human-gated, evidence-driven, knowledge-iterative
closed loop that improves experiment selection while preserving deterministic
execution and contamination controls.”
