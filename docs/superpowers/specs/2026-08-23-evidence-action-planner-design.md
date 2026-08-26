# ChaosAtlas Evidence Action Planner Design

**Date:** 2026-08-23

**Status:** Proposed

## Goal

Convert bounded advisory hypotheses into a deterministic, auditable evidence plan
without granting the LLM permission to inject faults, change classifications, or
promote knowledge.

## Scope

The planner is an internal stage of `chaosatlas run`. It consumes the validated
candidate registry and optional advisory hypotheses, then emits a plan of
read-only evidence actions plus an explicit decision about whether a bounded
runtime experiment is admissible. The first implementation is offline and
dry-run compatible. Existing live executor, business Oracle, recovery, cleanup,
RCA, and promotion state machines remain authoritative.

The planner does not scan arbitrary files, execute shell commands, add new
candidates, infer a weakness, or write the formal knowledge base.

## Data Flow

```text
hypotheses.json + candidate_space.json + inventory.json
    -> validate advisory references and candidate signatures
    -> derive deterministic evidence actions
    -> apply read-only action whitelist and project scope
    -> score cost/risk/information value with deterministic tie-breaking
    -> evidence_plan.json
    -> existing gate/executor/RCA stages
```

The output is an artifact, not an execution command. A live run may consume
only actions whose `status` is `admissible`; any validation error produces
`status=blocked` and prevents executor invocation.

## Plan Contract

`evidence_plan.json` contains:

- `schema_version` and `claim_scope=advisory`;
- `project_id`, `project_commit`, `input_sha256`;
- one entry per allow-listed candidate, keyed by the existing `candidate_id`;
- `actions`, each with `action_id`, `action_kind`, `target`, `reason`,
  `read_only`, `cost`, and `required_evidence`;
- `selection`, containing the deterministic order, budget, and tie-break rule;
- `runtime_experiment`, containing `admissible`, `blocked_reasons`, and the
  existing scenario contract reference;
- `status` in `{planned, blocked, fallback}`.

Allowed read-only action kinds are limited to existing evidence concepts:
`deployment_facts`, `service_facts`, `pod_state`, `pod_events`, `pod_logs`,
`business_baseline`, and `mechanism_evidence`. No action may contain shell,
kubectl, manifest mutation, namespace creation, or delete instructions.

## Deterministic Rules

1. Candidate IDs must exist in the static candidate space and their target,
   target kind, fault family, and operation must match the candidate registry.
2. Advisory text can enrich `reason`, expected observations, and missing
   evidence only. It cannot define action kind, target scope, status, budget, or
   runtime verdict.
3. Every candidate receives the required baseline and lifecycle evidence
   actions. Advisory missing-evidence strings are mapped to known action kinds;
   unknown strings are recorded as unmapped advisory text and do not become
   executable actions.
4. Actions are sorted by `(read_only desc, cost asc, candidate_id, action_id)`.
   The plan budget is deterministic and never exceeds the configured candidate
   budget.
5. A candidate with an unknown ID, target mismatch, invalid action, or missing
   recovery contract is `blocked`; it is never silently dropped or executed.
6. Planner failure returns deterministic fallback actions and keeps the final
   runtime/RCA/knowledge statuses unchanged.

## Integration

The existing `hypotheses` stage writes `evidence_plan.json` immediately after
validated advisory output and before `gate`. The dry-run stage records the plan
without executing it. The live stage requires the plan to be `planned`, then
passes only the existing compiled scenario and evidence references to the live
preflight/executor. No new executor interface is introduced in this phase.

The plan is checkpointed and included in the artifact index and Phase 6 audit.
Resume reuses the input hash and refuses to reuse a plan generated from a
different candidate registry or project commit.

## Testing

Tests cover:

- deterministic plans from the same input;
- advisory references to unknown candidates and forbidden actions;
- target/signature mismatch and missing recovery contract fail closed;
- unmapped advisory text never becomes an executable action;
- read-only actions sort ahead of higher-cost actions;
- candidate budget and plan hashes are stable;
- dry-run writes the plan without invoking an executor;
- live preflight blocks when the plan is blocked;
- RCA, classification, knowledge status, and formal knowledge writes are not
  changed by advisory content.

## Non-goals

- automatic shell or kubectl execution;
- new fault families or scenario compilers;
- replacing the existing RCA action state machine;
- automatic knowledge promotion;
- changing the one-command user experience.
