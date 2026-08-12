# ChaosAtlas 10-Project Main Experiment Priority

Status: priority reset, offline planning only. No DeepSeek request or fault injection is authorized by this file.

## Priority

The primary deliverable is the 10-project open-discovery experiment. The
fixed-candidate three-arm experiment is a secondary control and must not delay
or be reported as the main result.

## Main experiment arms

1. `ChaosAtlas-KB-open`: frozen YAML/Compose topology, workload contract,
   runtime safety contract, and the pre-experiment ChaosAtlas knowledge view.
2. `ChaosAtlas-noKB-open`: the same project evidence and schema, with the
   knowledge view removed.
3. `ChaosEater-official`: the deployed upstream ChaosEater cycle, receiving
   its native Skaffold/Kubernetes input and steady-state workflow. It is not
   replaced by `ChaosEater-adapter-open`.

`ChaosEater-adapter-open` is supplementary only. The fixed-pool
`ChaosAtlas-KB`, `ChaosAtlas-noKB`, and `ChaosEater-adapter` pilot is parked
until the main track has produced its project-level results.

## Where it runs

- Frozen project evidence and run records: this repository under
  `artifacts/experiments/chaosatlas_10_projects/`.
- ChaosAtlas compiler and shared evidence runner: `tools/` in this repository.
- Official ChaosEater source: `C:/APP/tools/chaos-eater`.
- Runtime: namespace-local workloads on the WSL-native `chaos-kind` cluster;
  official ChaosEater must use a dedicated namespace and must not clean or
  modify a ChaosAtlas namespace. A separate kind context is preferred once
  more than one project is active.

## Required order for every project

1. Freeze commit, source-tree hash, deployment assets, image provenance, and
   project namespace.
2. Build and validate the YAML/Compose topology IR and a deterministic
   business oracle.
3. Deploy the project and pass health, baseline, recovery, and cleanup gates.
4. Generate three independent method outputs from the same frozen project
   snapshot. The main arms do not receive the candidate pool or oracle labels.
5. Compile ChaosAtlas hypotheses into bounded, namespace-local Chaos Mesh YAML;
   preserve ChaosEater's native Workflow output separately.
6. Execute selected hypotheses under a shared observation budget and record
   injection, observation, recovery, cleanup, and evidence hashes.
7. Evaluate all outputs with the independent oracle. Confirmed weaknesses need
   two valid reproductions; protected behavior is recorded as positive defense
   evidence.
8. Close the project, review the evidence, and only then permit reviewed
   knowledge cards to flow to a later project. No same-project feedback.

## Current gate state

- P02 is the only project with a passed runtime gate and valid baseline/oracle
  evidence. It is the first main-track pilot candidate, not a completed main
  experiment.
- P01, P03, P05, P06, P07, P08, P09, and P10 remain environment/build blocked.
- P04 remains out of domain under the current bounded runtime budget.
- No project is yet eligible for a formal cross-project superiority claim.

## Main-track metrics

Report per project and then cluster by project: valid hypotheses, executable
hypotheses, confirmed weaknesses, novel issue yield, protected defenses,
environment-blocked rate, method-invalid rate, evidence completeness, RCA
source anchoring, recovery success, tokens, wall time, and human intervention.
Do not treat hypotheses within one project as independent samples.

## Control-track boundary

The fixed candidate pool answers a narrower question: whether knowledge changes
ranking quality inside a shared action space. It cannot establish autonomous
issue discovery and must be analyzed separately after the main track.
