# Online Boutique Runtime Policy Projection Design

## Goal

Create a deterministic, offline-only bridge from frozen historical runtime reports to the existing experiment-policy replay evaluator, so a second project can provide non-empty Shadow evidence without re-running Kubernetes mutations.

## Scope and boundaries

- Input is a frozen candidate pool and historical `unified-lifecycle-v1` runtime reports for one project.
- The bridge must reject project, candidate, replicate, lifecycle, or classification inconsistencies instead of guessing.
- A candidate is projected as `confirmed_weakness` only when at least two distinct completed reports have `weakness_observed` and every report passes baseline, injection, recovery, cleanup, and washout checks.
- The projection keeps source paths, raw report SHA-256 values, original classifications, and the deterministic reason for the normalized classification.
- The bridge has no Kubernetes, model, or knowledge-write access. It does not change the frozen denominator or the default `legacy` rollout.

## Architecture

`project_runtime_projection.py` exposes a pure `project_runtime_results(...)` function and a CLI. It loads the candidate pool, indexes reports by `mutation_id`, validates that every report belongs to the selected project and candidate pool, groups replicate evidence, and emits the canonical `runtime_results` list consumed by `evaluate_experiment_value_policy.py`. It also emits an audit record containing input hashes and lifecycle checks.

The existing replay evaluator remains the only policy-state updater. The projection layer supplies deterministic classifications; it never scores candidates, selects experiments, or promotes knowledge.

## Failure handling

The projection fails closed on unknown candidate IDs, duplicate replicate numbers, missing required lifecycle evidence, incomplete stable pairs, unsupported report schema, or non-`weakness_observed` reports. Partial evidence is not silently converted to `confirmed_weakness`.

## Verification

Unit tests cover a valid two-replicate projection, unknown candidate rejection, incomplete lifecycle rejection, and mixed classification rejection. The Online Boutique artifact run must produce four projected candidates and eight source reports, then pass two identical replay runs with equal report hashes. The run must record `cluster_access=false`, `model_called=false`, and `mutation_executed=false`.
