# ChaosAtlas Continuous-Learning Ablation Study Design

Date: 2026-09-04
Status: proposed and approved in discussion; implementation and experiment execution not started

## 1. Purpose

This study evaluates the central ChaosAtlas claim:

> With evidence-gated cross-project knowledge, ChaosAtlas can find stable,
> real anomalies earlier and at lower aggregate cost, without increasing
> false conclusions or missed-anomaly risk, and its efficiency improves as it
> is used on more projects.

The study separates two stages:

1. a capability-and-learning stage that builds the knowledge base on roughly
   nine or ten projects; and
2. a five-project continuous-learning ablation stage that compares the full
   method with an otherwise identical method that has no cross-project memory.

This is an online continual-learning comparison, not a frozen-knowledge
retrieval benchmark. The method, metrics, and safety contracts are frozen for
the ablation stage, while the Full arm's knowledge state is intentionally
allowed to evolve between projects.

## 2. Current Evidence Boundary

The current capability evidence includes five primary projects:

- Train Ticket;
- Online Boutique;
- OpenTelemetry Demo;
- Sock Shop; and
- Dify.

The next capability-and-learning projects are:

- Immich;
- ERPNext;
- Medusa; and
- Rocket.Chat.

An optional fifth learning project may be added before the ablation stage. It
must be selected before its results are observed and must satisfy the same
deployment, oracle, provenance, and safety gates.

Historical P02, NGINX Ingress, pilot, same-pool, and other engineering evidence
may be used to validate tooling, but it is not silently added to the formal
project denominator. Every included project must be listed in the
preregistered cohort manifest.

Existing knowledge artifacts are preserved. They are validated, normalized,
and migrated into the current state model; they are not regenerated merely to
make the archive look uniform. Any artifact that cannot satisfy the new
evidence contract remains provisional or excluded.

## 3. Research Questions

### RQ1: Cost efficiency

Does cross-project knowledge reduce aggregate cost to the first stable anomaly
and aggregate cost per independently confirmed issue surface?

### RQ2: Selection quality

Does cross-project knowledge increase anomaly yield among executed candidates
and reduce spending on inapplicable, already-defended, or repeatedly
no-impact regions?

### RQ3: Continual improvement

As evidence accumulates across the five evaluation projects, does the Full
arm's paired cost advantage increase without a corresponding increase in
missed anomalies or incorrect knowledge guidance?

### RQ4: RCA efficiency

Does knowledge reduce the number and cost of evidence actions required to move
an anomaly from symptom confirmation to bounded or confirmed RCA?

### RQ5: Knowledge safety

How often does reused knowledge transfer correctly, remain merely pending, or
become contested because its applicability assumptions fail?

## 4. Experimental Arms

### 4.1 Full

The Full arm uses:

- the shared project portrait and canonical candidate pool;
- the same configured LLM used by the control arm;
- cross-project knowledge available before the current project;
- project-local feedback during the current run;
- knowledge-conditioned ranking, parameter selection, evidence planning, and
  stopping advice; and
- automatic evidence-gated knowledge generation and promotion after both arms
  have completed the project.

### 4.2 noKB

The noKB arm retains:

- the same project portrait;
- the same canonical candidate pool;
- the same LLM, prompt structure, model parameters, and output schema;
- the same within-project runtime feedback;
- the same parameter escalation, reproduction, RCA, and stop controller; and
- the same deterministic execution and classification gates.

It receives no cross-project cards, selection experience, defense patterns,
judgment experience, or prior-project result summaries. Its project-local
state is archived for audit and reset before the next project.

The primary causal contrast is therefore cross-project persistent knowledge,
not LLM versus no LLM and not adaptive versus non-adaptive execution.

## 5. Sequential Knowledge Protocol

Let `K0` be the knowledge snapshot produced by the capability-and-learning
stage. For evaluation project `Ei`:

1. freeze and hash `K(i-1)`;
2. run Full with `K(i-1)` and run noKB with an empty cross-project view;
3. keep the two arms isolated and restore the environment between arms;
4. complete result classification, RCA, and evaluation audit for both arms;
5. only after both arms close, promote eligible evidence discovered by Full;
6. write the next immutable snapshot `Ki`; and
7. use `Ki` on `E(i+1)`.

The noKB arm never contributes evidence to a later noKB run. Its results also
must not be copied into the Full knowledge base, because Full did not acquire
that evidence through its own policy. Unique noKB findings remain part of the
evaluation ledger and missed-opportunity analysis.

The project order is preregistered and is not changed in response to interim
results. Snapshot lineage records source card IDs, source projects, evidence
hashes, accepted promotions, rejected promotions, demotions, and conflicts.

## 6. LLM Responsibility Boundary

The LLM may:

- propose supplemental hypotheses from the project portrait;
- retrieve and explain potentially applicable knowledge;
- score or rank eligible candidates;
- recommend parameter escalation or budget reduction;
- recommend the next evidence action for RCA; and
- recommend `screen`, `confirm`, `escalate`, `explore`, or `stop`.

The LLM may not determine:

- whether a target, selector, protocol, or executor is valid;
- whether a live mutation is authorized;
- whether injection actually occurred;
- whether the business oracle failed;
- whether recovery or cleanup passed;
- whether an RCA claim is confirmed;
- whether evidence is eligible for formal promotion; or
- whether a safety or minimum-exploration requirement can be bypassed.

Those decisions remain deterministic and fail closed. Every LLM decision
records its input snapshot hash, retrieved card IDs, structured output,
acceptance or override result, token use, latency, and fallback status.

## 7. Candidate Construction and Identity

Each project begins with a canonical pool generated deterministically from:

```text
workload and service inventory
x executable fault capabilities
x verified dependency edges
x allowed parameter levels
```

Every candidate has a stable candidate ID, causal-cluster ID, fault family,
target role, parameter level, expected cost, provenance, and applicability
requirements.

LLM-proposed candidates enter a separate supplemental pool. They must pass the
same schema, target, protocol, executor, risk, and server-side validation gates
before execution. Supplemental candidates are reported separately and cannot
silently change the canonical denominator.

For the primary Full/noKB comparison, both arms receive byte-identical
canonical candidate pools. If supplemental candidates are enabled, both arms
receive the same opportunity and budget for proposing them, and results are
reported both with and without the supplemental stratum.

## 8. Runtime and Isolation Contract

Both arms use the same:

- isolated namespace and pinned project revision;
- immutable images and rendered deployment inputs;
- business oracle and observation window;
- mutation compiler and executor;
- baseline requirements;
- anomaly reproduction threshold;
- recovery, cleanup, residual scan, and washout rules;
- evidence collectors and RCA state machine; and
- aggregate budget ceiling.

Arm order is randomized or counterbalanced by project. When parallel isolated
environments are unavailable, the second arm starts only after the first arm's
fault resources are absent, workloads are restored, the business baseline is
stable, and washout passes. Environment drift and operator interventions are
recorded explicitly.

An environment or method failure is never classified as a defense or
no-impact application result.

## 9. Aggregate Cost

The primary cost is an auditable aggregate derived from separately retained
components:

```text
C_total = C_llm + C_gate + C_runtime + C_observation + C_recovery + C_rca
```

The ledger retains raw units before normalization:

- model calls, input/output tokens, latency, and monetary cost when available;
- gate and compilation wall-clock time;
- live injection count and active fault duration;
- business-oracle and evidence-collection time;
- recovery, cleanup, and washout time;
- RCA evidence-action count and duration; and
- exceptional operator-intervention time.

Normal execution excludes human review. Exceptional manual recovery is
reported as a separate operational-cost component and cannot be hidden.

The scalar normalization and weights are preregistered using only the learning
cohort. All component metrics are reported alongside the scalar result, and a
weight sensitivity analysis is required so that the headline cannot depend on
one arbitrary weighting choice.

## 10. Selection, Exploration, and Stop Policy

The deterministic controller enforces this priority order:

1. finish pending anomaly confirmations;
2. complete required baseline coverage;
3. execute mandatory parameter audits;
4. allocate budget to high-value candidates;
5. satisfy the low-priority exploration floor;
6. execute required RCA evidence actions; and
7. allow stopping only when no mandatory work remains and expected marginal
   information gain is below the frozen threshold, or the aggregate budget is
   exhausted.

The default exploration floor is 15 percent, with at least one lowest-cost
representative from each eligible causal cluster. Sensitivity analysis uses 5,
15, and 25 percent. First-transfer knowledge may recommend a higher 25 percent
audit rate, while mature cross-project knowledge may recommend a lower rate;
the controller still enforces the preregistered floor for the primary study.

Knowledge can reduce priority or budget for verified defense and no-impact
regions. Only an inapplicability rule whose target, protocol, platform, and
executor conditions all match may hard-filter a candidate.

## 11. RCA Contract

Stable anomalies enter a competing-hypothesis RCA process:

```text
symptom confirmed
-> competing mechanism hypotheses
-> evidence for and against each hypothesis
-> lowest-risk discriminating evidence action
-> confirmed, bounded, rejected, or contested
```

RCA claims are labeled by evidence level:

- `symptom_confirmed`;
- `service_boundary_confirmed`;
- `mechanism_bounded`; or
- `source_root_cause_confirmed`.

A service-boundary observation must not be presented as a source-level root
cause. Knowledge may recommend evidence actions, but deterministic evidence
requirements control the transition between RCA states.

## 12. Knowledge Contents and Promotion

The knowledge base stores four result classes:

- `confirmed_weakness`;
- `verified_defense`;
- `no_impact`; and
- `inapplicable`.

Each record includes source project and revision, causal identity, target role,
fault and parameter scope, applicability and exclusion conditions, evidence
references, reproduction count, RCA level, counter-evidence, next evidence,
and promotion audit.

The automatic lifecycle is:

```text
provisional
-> local_reusable
-> cross_project_pending
-> cross_project_reusable
```

Contradictory evidence moves a record to `contested`, reduces its influence,
and creates a discriminating evidence request. Current-project evidence may
become `local_reusable` after all deterministic gates pass. It becomes
`cross_project_reusable` only after independent validation on a later project
with matching applicability semantics.

Same-project same-round feedback is forbidden. No-impact and defense knowledge
may reduce budget but cannot eliminate the exploration floor.

## 13. Evaluation Audit for Missed Anomalies

Policy stopping alone cannot demonstrate accuracy because the unexecuted
candidates have unknown outcomes. After each arm stops, an evaluation-only
audit samples approximately 15 percent of its unexecuted candidate space,
stratified across high, medium, and low predicted value and across causal
clusters.

Audit execution:

- is excluded from the arm's policy budget and reported separately;
- cannot change the arm's decisions for the current project;
- cannot enter the next knowledge snapshot until the entire study closes; and
- estimates missed-anomaly rate, stop regret, and calibration.

Where safe and practical, the union of candidates selected by either arm can
also provide common outcome labels for paired ranking analysis. Reusing a
runtime label requires matching project revision, causal identity, parameter,
oracle, and environment contract.

## 14. Primary Outcomes

Primary outcomes are calculated within each project before cross-project
aggregation:

- aggregate cost to first stable anomaly;
- aggregate cost to first independent issue surface;
- aggregate cost per stable anomaly;
- aggregate cost per independent issue surface;
- issue surfaces found under the common budget;
- anomaly yield among executed candidates;
- cost spent on inapplicable, defended, and no-impact candidates;
- RCA evidence-action cost;
- audit-estimated missed-anomaly rate; and
- knowledge-guidance correctness and contradiction rates.

The continual-learning curve records, for `E1` through `E5`:

- knowledge snapshot size and provenance mix;
- retrieved and influential card counts;
- paired cost difference `C_noKB - C_Full`;
- time and cost to first stable anomaly;
- unique issue surfaces;
- knowledge savings and knowledge-caused waste; and
- promotion, rejection, and contested counts.

## 15. Analysis and Interpretation

The project is the primary statistical cluster. Report paired per-project
effects, cumulative cost-discovery curves, effect sizes, and project-level
bootstrap confidence intervals. With five evaluation projects, statistical
power is limited; practical effect and consistency are more important than a
single significance threshold.

The preregistered practical success criteria are:

- at least 20 percent lower aggregate cost per independent issue surface;
- no reduction in issue surfaces found under the common budget;
- lower cost in at least four of five evaluation projects;
- no material increase in audit-estimated missed anomalies; and
- a positive continual-learning trend without increasing knowledge-caused
  waste.

Interpretation levels are:

- **strong support**: lower cost, equal or better issue coverage, acceptable
  miss risk, and an improving learning curve;
- **partial support**: similar coverage with materially lower invalid,
  no-impact, or RCA cost, but no clear learning slope;
- **no support**: no cost reduction, reduced coverage, or savings explained by
  premature stopping and missed anomalies.

## 16. Secondary Component Ablations

The live primary experiment remains Full versus noKB. Component attribution is
performed primarily through offline replay or shadow evaluation using frozen
runtime labels:

- remove confirmed-weakness knowledge;
- remove verified-defense and no-impact knowledge;
- remove inapplicability knowledge;
- disable knowledge-conditioned stop advice;
- disable RCA knowledge; and
- replace the LLM advisor with deterministic ranking.

These analyses separate anomaly-prior value, negative-knowledge savings,
stopping value, RCA value, and the LLM's incremental contribution without
repeating every destructive runtime experiment.

## 17. Required Artifacts

Before the first evaluation run, produce:

- a learning-cohort and evaluation-cohort manifest;
- frozen method, prompt, model, cost, and metric specifications;
- project-order manifest;
- `K0` snapshot and validation report;
- canonical candidate-pool schema;
- arm isolation and reset checklist;
- aggregate-cost ledger schema;
- stop-decision schema;
- RCA evidence-level schema;
- knowledge promotion and conflict schema;
- audit-sampling manifest; and
- preregistered analysis script or calculation specification.

Each project then produces arm manifests, decision ledgers, runtime evidence,
cost ledgers, stop audits, RCA reports, knowledge-consumption reports, and an
immutable next-snapshot transition report.

## 18. Safety and Leakage Rules

- Runtime findings from the current project cannot appear in either arm's
  initial prompt or knowledge input.
- Full learns only from evidence it acquired through its own prior runs.
- noKB state is reset between projects.
- Evaluation-audit findings remain quarantined until the primary experiment
  closes.
- Platform blocks, invalid injection, incomplete cleanup, and missing oracle
  evidence are never negative application labels.
- Secrets, raw credentials, and unredacted sensitive logs never enter prompts
  or knowledge cards.
- A failed cleanup or recovery attestation stops the affected arm until the
  environment is repaired and re-baselined.

## 19. Scope Boundary

This design does not authorize deployment, model calls, fault injection,
knowledge mutation, or code changes. Implementation begins only after this
written design is reviewed and an implementation plan is approved.
