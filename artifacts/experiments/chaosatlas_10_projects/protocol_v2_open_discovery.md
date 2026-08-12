# ChaosAtlas Open Discovery Protocol v2

Status: offline design freeze candidate. No DeepSeek request is authorized.

## Formal knowledge-ablation boundary

The KB/noKB contrast has two distinct phases and they must not be pooled:

1. **Source-context pilot**: both arms receive the same frozen project evidence;
   KB additionally receives a pre-runtime project card. This measures the
   value of an extra structured summary, not accumulated runtime experience.
2. **Cross-project feedback ablation**: projects run in the registered order
   `P01 -> ... -> P10`. After a project is closed, only a human-reviewed,
   abstracted feedback projection may enter a later KB. The current project's
   runtime result never enters its own input. The noKB arm never receives any
   feedback projection, and ChaosEater never receives ChaosAtlas cards.

The audit card may retain evidence, oracle labels, classification, RCA, and
mutation paths, but the prompt-facing projection may contain only provenance
and a reviewed abstraction. `tools/validate_chaosatlas_experiment.py` is a
fail-closed offline gate for these rules.

## Research question

The primary question is whether a method can read a real project and autonomously
propose bounded, reproducible fault hypotheses that reveal verified weaknesses.
The frozen candidate-pool experiment is retained as a secondary control and is
not evidence of open-ended issue discovery.

## Tracks

### Track A: open discovery (primary)

For each project, each registered seed, and each method arm, the method receives
the frozen commit, a deterministic YAML/Compose topology IR, source/deployment
evidence, workload contract, runtime safety limits, and Chaos Mesh capability
summary. The topology IR contains deployment nodes, routing/dependency edges,
and defense attributes; it is not an application call graph and does not contain
verdicts. It does **not** receive the frozen
candidate pool, candidate IDs, candidate order, oracle labels, prior selections,
runtime observations, or post-run RCA.

Each arm may return at most eight hypotheses. A hypothesis must state its target,
fault family, bounded parameters, weakness surface, topology-backed call chain,
mechanism hypothesis, expected invariant, validation plan, and recovery
expectation. An empty list is valid only when the
method explicitly reports that no safe hypothesis can be justified.

The safety compiler then validates the output against the deployment topology and
runtime contract. It rejects unknown targets, target-kind mismatches, unsupported fault families,
out-of-range parameters, duplicate actions, missing workload/recovery plans, and
any cross-namespace or shell-like action. The compiler adds the namespace and
produces a canonical mutation intent; it does not silently repair output.

After compilation, an independent evaluator compares the canonical signature to
the frozen control pool. A match is `known_candidate`; a safe non-match is
`novel_candidate`. The control pool is therefore an evaluation reference, never
an input constraint.

### Track B: candidate ranking (secondary control)

This is the existing `protocol_v1` experiment. All three arms receive the same
frozen pool and rank exactly K candidates. Its claims are limited to ranking
quality, knowledge ablation, and method comparison within a shared action space.
It must not be described as end-to-end issue discovery.

## Arms

- `ChaosAtlas-KB-open`: ChaosAtlas open-discovery prompt plus the frozen general
  and project knowledge views.
- `ChaosAtlas-noKB-open`: byte-identical project/common input and prompt skeleton,
  with all knowledge views removed.
- `ChaosEater-official`: the deployed upstream ChaosEater end-to-end cycle
  (preprocess -> hypothesis -> experiment -> analysis -> improvement), using
  its native Skaffold/Kubernetes input. This is the primary external baseline
  when the project passes the official bring-up gate.
- `ChaosEater-open`: an open prompt-level reproduction of the
  FaultScenarioAgent without the candidate-pool restriction. It is a
  supplementary diagnostic arm and must not be reported as the official
  end-to-end baseline.
- `ChaosEater-adapter-open`: supplementary adapter using the extracted
  FaultScenarioAgent prompt/parser. It is never renamed to official ChaosEater.

If `ChaosEater-official` is unavailable, the project is reported as
`environment_blocked` for the official-baseline comparison; neither open prompt
arm nor adapter may replace it. `ChaosEater-adapter-open` is a separate
supplementary result.

## Paired design

- Projects: P01-P10, fixed commit and source-tree hash.
- Seeds: 1001, 1002, 1003.
- Maximum hypotheses per call: 8.
- Pilot: P02 and P07, 18 calls for Track A and 18 calls for Track B.
- Formal: 10 projects x 3 arms x 3 seeds = 90 calls per track.
- Track A and Track B results are analyzed separately; no candidate is treated as
  an independent project sample.

## Primary metrics

- `valid_hypothesis_rate`: hypotheses accepted by the safety compiler / returned.
- `executable_rate`: accepted hypotheses with a verified target resolver and
  namespace-local mutation path.
- `unique_issue_yield`: independently confirmed weaknesses / valid hypotheses.
- `novel_issue_yield`: confirmed weaknesses whose canonical signature is not in
  the frozen control pool.
- `known_pattern_coverage`: confirmed known-pool signatures discovered by the arm.
- `protected_waste`, `method_invalid_rate`, `environment_blocked_rate`.
- `evidence_completeness`, `recovery_success`, RCA accuracy, tokens, runtime, and
  human review time.

All estimates are project-clustered. Each project has at least three registered
seeds, but seeds and hypotheses are repeated measurements, not independent
projects. Report paired KB-minus-noKB differences per project, then summarize
the distribution across projects. Keep valid-output rate, compiler rate,
confirmed-weakness yield, protected-target yield, method-invalid rate,
environment-blocked rate, call-chain coverage/depth, runtime success, and token
cost as separate endpoints.

## Result classification and feedback

Every compiled hypothesis receives an independent result class:
`confirmed_weakness`, `protected`, `latent_risk`, `unsupported`,
`environment_blocked`, or `method_invalid`. `confirmed_weakness` requires two
valid reproductions and complete baseline/injection/observation/recovery/cleanup
plus an independent oracle. `protected` is positive evidence about a defense and
is not counted as a failure. Static evidence without a valid runtime oracle is
`latent_risk`, never a confirmed issue.

After a project is closed, a human-reviewed weakness/protected card may be
abstracted into a later knowledge snapshot. The registered project order and
round id are mandatory: a card may only flow from an earlier completed project
to a later project, never into its own target project or from a future project.
The current project's input is immutable. The feedback artifact records source
commit, topology graph hash, evidence references, abstraction family, reviewer
status, round id, and the project-order allowlist.

## Claims boundary

Track A supports claims about autonomous issue discovery only when the workload,
independent oracle, two valid reproductions, recovery, and cleanup evidence are
complete. Track B supports claims about ranking in a fixed action space. A gain
only in Track B is not evidence that the method discovers new issue classes.

## Stop rules

The run stops on three consecutive transport failures, any safety-compiler defect,
or a cleanup failure. Environment and project-domain failures are recorded and
excluded from method quality metrics. Any change to prompt, model, seed, output
schema, budget, compiler, or oracle creates protocol v2.x and requires renewed
approval.
