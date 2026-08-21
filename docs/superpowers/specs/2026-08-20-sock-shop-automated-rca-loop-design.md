# Sock Shop Automated RCA and Experience Iteration Loop

## Status

Design approved for specification drafting on 2026-08-20. This document
defines the first implementation scope. It does not authorize a new cluster
experiment, external model call, production change, or automatic cross-project
knowledge publication.

## 1. Problem

ChaosAtlas already has a useful runtime lifecycle and three knowledge layers:
selection experience, judgment experience, and defense patterns. It can select
bounded hypotheses, compile mutations, execute them, validate business impact,
recover the workload, and preserve evidence.

The missing part is the post-detection control loop. A runtime report currently
ends at a weakness or defense classification, while root-cause analysis is
mostly a later manual activity. The existing backfill tools match outcomes to
predefined experience entries by service and fault family; they do not maintain
a case-specific evidence graph, compare competing explanations, select a
discriminating experiment, or generate a regression test from the resulting
knowledge.

The target is a bounded, auditable loop:

```text
discover weakness
  -> create RCA case
  -> generate root-cause hypotheses
  -> collect evidence and counter-evidence
  -> select and execute a discriminating experiment
  -> confirm, bound, defer, or reject the RCA
  -> generate a provisional or reusable knowledge card
  -> compile regression and next-round tests
  -> validate whether the knowledge still holds
```

The system must not turn a business failure into an unsupported internal
mechanism. A confirmed weakness and a confirmed root cause are separate
claims.

## 2. Goals

1. Automatically create a traceable RCA case for every eligible confirmed
   runtime weakness or materially informative protected result.
2. Represent competing root-cause hypotheses with expected observations,
   falsifiers, supporting evidence, and opposing evidence.
3. Select the next evidence action or experiment using deterministic rules
   with information gain, cost, safety, and applicability as inputs.
4. Use evidence to transition each RCA hypothesis through `pending`,
   `bounded`, `confirmed`, or `rejected`.
5. Automatically create knowledge cards and regression intents without
   requiring a human to write the first draft.
6. Allow strong local evidence to produce reusable project-local knowledge,
   while keeping cross-project promotion and external issue submission
   review-gated.
7. Make an experience card operational: it must influence candidate selection,
   RCA hypothesis generation, evidence collection, or regression generation.
8. Preserve provenance, contradictions, environment blocks, and unavailable
   diagnostics instead of hiding them.

## 3. Non-goals

1. Automatically repair application code, manifests, or production systems.
2. Claim a line-level root cause when only a service-boundary symptom is
   evidenced.
3. Replace the existing four-layer runtime gate or business oracle.
4. Re-run historical Sock Shop experiments solely to retrofit this design.
5. Make pending historical reports formal knowledge cards without passing the
   new evidence and promotion gates.
6. Use an LLM as the authority for evidence truth, RCA status, or promotion.
7. Automatically publish cross-project knowledge or submit upstream issues.

## 4. Design principles

### 4.1 Three independent statuses

Every case records these independently:

```text
weakness_status   candidate | confirmed | protected | unsupported | environment_blocked
rca_status        pending | bounded | confirmed | rejected
knowledge_status  none | provisional | local_reusable | cross_project_pending | cross_project_reusable | contested
```

For example, `weakness_status=confirmed` and `rca_status=bounded` is a valid
and expected result. It means the failure is real and its affected boundary is
known, but the internal mechanism is not yet proven.

### 4.2 Evidence before explanation

An explanation is never promoted because it sounds plausible or because an LLM
is confident. Each hypothesis must declare what would support it and what would
falsify it. Missing logs, traces, source, or configuration are recorded as
unavailable evidence, not silently treated as negative evidence.

### 4.3 Boundary-first RCA

RCA proceeds from observable boundary to internal mechanism:

```text
business symptom
  -> affected request or service boundary
  -> dependency or resource behavior
  -> configuration or architectural mechanism
  -> source-level mechanism, when directly evidenced
```

The system may stop at any level and use `bounded` when deeper evidence is not
available.

### 4.4 Deterministic authority, optional LLM assistance

The deterministic engine owns lifecycle validity, evidence references, state
transitions, hard filters, safety gates, and promotion. An LLM may propose
hypotheses, summarize evidence, or suggest candidate actions, but every output
must be normalized and checked against the project snapshot and action schema.

### 4.5 Provisional learning is automatic; broad reuse is earned

The first knowledge draft is generated automatically. Project-local reuse is
allowed only after deterministic evidence gates. Cross-project exposure remains
review-gated unless the same pattern is independently reproduced in the
required number of projects.

## 5. Architecture

The first version consists of seven narrow components.

### 5.1 Case assembler

Consumes a valid runtime report, baseline, business oracle result, static
topology references, and existing classification. Produces one immutable
`WeaknessCase` snapshot per canonical weakness signature.

It deduplicates replicates by `weakness_id`, but retains every replicate and
never overwrites contradictory observations.

### 5.2 Hypothesis generator

Generates a small set of RCA hypotheses from:

- the TestNode and local impact graph;
- deployment and service configuration;
- source or contract inventory when available;
- the normalized symptom and timing;
- applicable existing knowledge cards;
- known defense patterns and their counter-conditions.

Hypotheses must be bounded to an observable mechanism. Examples include
`singleton_workload_no_redundancy`,
`synchronous_downstream_call_without_verified_timeout`, and
`transport_failure_propagates_as_business_error`. Vague hypotheses such as
`system is fragile` are invalid.

### 5.3 Evidence planner

Ranks evidence actions. Cheap read-only actions are preferred first; runtime
experiments are used when static evidence cannot distinguish the candidates.
The planner must emit an explicit reason for the selected action.

### 5.4 Diagnostic and experiment adapters

Adapters execute only declared action types. The first scope supports:

- static manifest/config/source lookup;
- bounded service logs and Kubernetes events;
- available trace/span lookup;
- real business-path replay versus direct dependency replay;
- bounded delay or loss ladder around an observed timeout boundary;
- isolated replica counterfactual where the project runner explicitly allows
  it;
- repeat-after-recovery and washout verification.

An action is rejected when its namespace, target, mutation, or cleanup contract
cannot be validated before execution.

### 5.5 RCA evaluator

Consumes the original case, hypothesis predictions, evidence results, and
counter-evidence. It applies deterministic state rules and produces an audit
record explaining the transition.

### 5.6 Knowledge projector

Projects a case into a knowledge card while retaining the full RCA case as the
audit record. Runtime-specific details remain in the audit record unless the
card's evidence schema explicitly references them.

### 5.7 Regression compiler

Converts a reusable knowledge card into one or more future test intents. A
regression intent contains applicability conditions, the business oracle,
required evidence, the expected defense or weakness boundary, and a stopping
rule. It is not an unbounded instruction to repeat the same mutation.

## 6. Data contracts

### 6.1 Weakness case

The canonical case has the following shape:

```json
{
  "schema_version": "chaosatlas-weakness-case-v1",
  "weakness_id": "WS-sock-shop-front-end-catalogue-abort",
  "project_id": "sock-shop",
  "project_commit": "<pinned-commit>",
  "round_id": "<runtime-round>",
  "test_node": {
    "family": "HTTPChaos",
    "operation": "abort",
    "target_role": "catalogue-edge",
    "source_ref": "<redacted-or-relative-reference>"
  },
  "symptom": {
    "oracle": "<business-oracle-id>",
    "baseline_contract": "<normalized-contract>",
    "injected_contract": "<normalized-contract>",
    "observed_change": "response contract changed or request budget exceeded"
  },
  "weakness_status": "confirmed",
  "rca_status": "pending",
  "knowledge_status": "none",
  "evidence_refs": [],
  "hypothesis_ids": [],
  "next_actions": [],
  "replicates": [],
  "provenance": {
    "runtime_report_sha256": "<sha256>",
    "input_snapshot_sha256": "<sha256>"
  }
}
```

The case does not store secrets, credentials, tokens, or unredacted private
endpoints. A missing or unavailable source is represented by a status and a
reference to the attempted collection, not by copying sensitive configuration.

### 6.2 RCA hypothesis

```json
{
  "hypothesis_id": "RCA-WS-sock-shop-front-end-catalogue-abort-01",
  "weakness_id": "WS-sock-shop-front-end-catalogue-abort",
  "claim": "transport abort at the catalogue boundary is propagated into the business response",
  "mechanism_class": "transport_error_propagation",
  "scope": {
    "services": ["front-end", "catalogue"],
    "edge": "front-end->catalogue"
  },
  "expected_observations": [
    "catalogue-side request failure is present in the diagnostic window",
    "front-end records or returns the corresponding downstream failure",
    "the real business path reproduces the boundary change"
  ],
  "falsifiers": [
    "direct dependency failure does not appear on the real business path",
    "a verified fallback returns the original business contract",
    "the same symptom occurs with no corresponding downstream event"
  ],
  "required_evidence": [
    "runtime_business_path",
    "downstream_diagnostic_or_source_mapping",
    "recovery_after_fault_removal"
  ],
  "evidence_for": [],
  "evidence_against": [],
  "unsupported_claims": [],
  "status": "pending",
  "confidence": 0.0,
  "next_action": null
}
```

### 6.3 Evidence record

Every evidence record identifies its source, time window, collection method,
integrity hash when applicable, and interpretation boundary:

```json
{
  "evidence_id": "EV-...",
  "kind": "runtime_log | source_span | manifest | trace | oracle | counterfactual",
  "polarity": "supports | contradicts | unavailable | neutral",
  "claim_scope": "service boundary or exact mechanism being tested",
  "source_ref": "<relative-artifact-path-or-source-span>",
  "collected_at": "<timestamp>",
  "window": {"start": "<timestamp>", "end": "<timestamp>"},
  "sha256": "<sha256-or-null>",
  "interpretation": "bounded statement supported by this record"
}
```

The evaluator may use only evidence whose source and scope match the
hypothesis. A log showing a client timeout cannot by itself prove an
application-level missing timeout.

### 6.4 Experience card

The generated card includes operational fields in addition to the existing
test-node-centered fields:

```text
id / version / status
project / project_commit / test_node
test_node_centered_graph
weakness_status / rca_status / knowledge_status
mechanism_claim / mechanism_level
applicability_conditions
exclusion_conditions
evidence_summary / counter_evidence
validation_recipe
regression_intents
stop_rule
lineage
next_evidence
```

The existing validator remains the base schema gate. The new RCA validator
adds requirements for status consistency, evidence references, explicit
counter-evidence, and a non-empty regression or next-evidence action.

## 7. State machine and promotion rules

### 7.1 Weakness state

The existing runtime lifecycle remains authoritative. A case can be created
only from a valid completed runtime result or from an explicitly marked
informative protected result.

```text
candidate -> confirmed
candidate -> unsupported
candidate -> environment_blocked
```

The transition to `confirmed` requires the existing business oracle and
runtime lifecycle evidence. A platform failure cannot become a weakness.

### 7.2 RCA state

```text
pending -> bounded
pending -> confirmed
pending -> rejected
bounded -> confirmed
bounded -> rejected
bounded -> pending       new contradictory or insufficient evidence
confirmed -> bounded     later counter-evidence limits the claim
confirmed -> rejected    reproducible contradiction invalidates the claim
```

Rules:

- `bounded` requires a stable affected boundary and at least one supporting
  evidence record, but does not require a mechanism-level proof.
- `confirmed` requires all declared required evidence, at least one
  discriminating action, and no unresolved high-severity contradiction.
- `rejected` requires a falsifier or a reproducible result that contradicts
  the claim.
- `pending` remains valid when diagnostics are unavailable or the next action
  is not safe/applicable.

### 7.3 Knowledge promotion

```text
none -> provisional
provisional -> local_reusable
local_reusable -> cross_project_pending
cross_project_pending -> cross_project_reusable
local_reusable -> provisional       meaningful counter-example
```

`provisional` is always generated automatically for a valid case. It may be
used to plan follow-up diagnostics in the same case, but it must not change
high-impact selection priorities by itself.

`local_reusable` requires:

1. two valid reproductions or one valid counterfactual plus one reproduction;
2. `weakness_status=confirmed` or `weakness_status=protected`;
3. `rca_status=confirmed` for mechanism-specific cards, or `rca_status=bounded`
   for boundary-level cards clearly labeled as bounded;
4. complete lifecycle and cleanup evidence;
5. at least one source, manifest, log, trace, or counterfactual reference;
6. explicit applicability and exclusion conditions;
7. a generated regression intent and stopping rule.

Cross-project reuse changes the state to `cross_project_pending` first and
requires either human review through the existing feedback protocol or
independent reproduction in the required project count. The card must never be
silently added to a later project's prompt snapshot. A meaningful contradiction
sets `knowledge_status=contested` and requires re-evaluation before reuse.

## 8. Active evidence and experiment selection

The planner scores an action with a deterministic tuple:

```text
priority = information_gain
         + evidence_completeness_gain
         + causal_discrimination_gain
         - execution_cost
         - risk
         - environment_uncertainty
```

Information gain is based on how many live hypotheses the action can separate.
The planner prefers actions in this order unless their applicability gate
fails:

1. existing evidence and exact source/config lookup;
2. bounded logs/events/traces in the already captured time window;
3. real business-path replay versus direct dependency replay;
4. controlled delay/loss boundary probe;
5. isolated counterfactual such as replica scaling;
6. a new fault family or broader experiment.

Every selected action contains:

- target and namespace scope;
- preconditions;
- expected evidence for each hypothesis;
- cleanup and recovery contract;
- maximum duration and retry budget;
- stop conditions;
- output evidence schema.

The system stops and records `pending` when no safe action can distinguish the
remaining hypotheses. It does not fill the gap with an LLM conclusion.

## 9. Sock Shop pilot mapping

The first pilot handles three existing result families.

### 9.1 Single-replica PodKill

The case assembler combines manifest evidence (`replicas=1`, no PDB where
verified) with the Ready transition and business impact. The expected card is
a deployment-availability card. The confirmed claim is limited to lack of
redundancy and the resulting outage window; no application-internal mechanism
is inferred.

The regression intent checks:

- singleton workload detection;
- bounded PodKill;
- business oracle failure during the replacement gap;
- recovery and cleanup;
- optional isolated scale-to-two counterfactual when the runner permits it.

### 9.2 `catalogue-db` PodKill

The initial case confirms the business impact and the database dependency
boundary. The RCA generator creates separate candidates for database
connection unavailability and catalogue-side error propagation. The case only
becomes mechanism-confirmed when the connection failure and catalogue request
failure are linked by scoped logs, source/config evidence, or a discriminating
replay. Otherwise it remains `rca_status=bounded`.

### 9.3 HTTP abort propagation

The first case records the response-contract change and distinguishes direct
dependency measurement from the real business path. It may confirm
`transport_error_propagation` at the service boundary. It must not call the
mechanism `missing_timeout` unless the real path and source/config evidence
support that claim.

## 10. Feedback into the next round

The regression compiler produces three kinds of intents:

1. `reproduce`: repeat the same boundary with a stable oracle and bounded
   budget;
2. `discriminate`: run the next experiment that separates the remaining RCA
   candidates;
3. `guard`: verify a defense boundary or ensure that a known closed boundary
   is not repeatedly reinjected.

The decision engine consumes only cards whose status and evidence gates allow
reuse. A card can influence:

- candidate family priority;
- target-edge selection;
- required business-path oracle;
- diagnostic capture requirements;
- RCA hypothesis templates;
- regression selection and stopping.

Every next-round input records the card IDs and snapshot hash. A later result
is linked back to the card that caused the action. If the result contradicts
the card, the card receives a counter-example and is demoted to `provisional`
or `contested`; it is never silently rewritten.

## 11. Failure handling and safety

The loop fails closed on:

- missing baseline or business oracle;
- unconfirmed injection;
- unconfirmed recovery or cleanup;
- namespace or selector mismatch;
- missing action preconditions;
- residual Chaos resources;
- evidence reference outside the frozen input or runtime window;
- sensitive-value detection;
- conflicting project or commit identity;
- attempted same-round or same-project cross-project feedback.

An unavailable diagnostic is a first-class result. The case remains useful and
may receive a bounded card, but the unavailable evidence is not counted as
support or contradiction.

## 12. Verification and acceptance criteria

The implementation is accepted only when focused tests demonstrate:

1. valid runtime reports create one canonical case with replicate lineage;
2. duplicate reports do not erase contradictory evidence;
3. evidence polarity and claim scope are validated;
4. each RCA state transition has a deterministic reason;
5. unsupported mechanism claims cannot reach `confirmed`;
6. environment-blocked runs cannot create a weakness card;
7. provisional cards are generated automatically;
8. local promotion requires the declared evidence gates;
9. counter-evidence demotes or contests a card without deleting history;
10. regression intents include oracle, evidence requirements, and stop rule;
11. card IDs and snapshot hashes appear in the next-round input;
12. sensitive-value and path-boundary checks remain enforced;
13. existing knowledge-base validation and runtime lifecycle tests continue to
    pass.

The Sock Shop pilot is considered closed when each of the three families has a
machine-readable case, an explicit RCA status, at least one generated next
action, and a generated knowledge/regression artifact. It is not required that
all three reach `rca_status=confirmed`; preserving `bounded` or `pending` is a
successful result when the available evidence cannot support a stronger claim.

## 13. Alternatives considered

### Post-processing only

This would add RCA fields after the current runtime reports. It is cheaper but
does not create a real active investigation loop and would leave experiment
selection mostly manual.

### Fully agentic LLM investigation

This would allow flexible multi-step investigation but makes evidence truth,
repetition, cost, and safety difficult to audit. It is unsuitable as the
authority for RCA state or knowledge promotion.

### Selected approach

Use an evidence graph, deterministic RCA state machine, and active experiment
planner. Keep the LLM as a bounded hypothesis and explanation assistant. This
reuses the existing lifecycle, business oracle, TestNode graph, decision
engine, knowledge validator, and feedback boundary while adding the missing
middle layer that turns a detected problem into an iterative learning case.
