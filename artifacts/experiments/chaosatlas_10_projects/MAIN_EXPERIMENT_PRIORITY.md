# ChaosAtlas 10-Project Main Experiment Priority

Status: frozen ten-project protocol; immediate execution is governed by the
four-project follow-up queue. Offline planning only. No DeepSeek request or
fault injection is authorized by this file.

## Priority

The immediate deliverable is our complete method plus its complete-method
ablation across the four-project follow-up queue: Online Boutique,
OpenTelemetry Demo, Train Ticket, and TeaStore. The fixed-candidate experiment
and ChaosEater comparison are deferred and must not delay or enter the active
results.

## Main experiment arms

1. `ChaosAtlas-KB-open`: our complete method with frozen project evidence,
   runtime safety contract, and the permitted pre-experiment knowledge view.
2. `ChaosAtlas-noKB-open`: the complete-method ablation with byte-identical
   project evidence and no knowledge view or runtime feedback.

`ChaosEater-official`, `ChaosEater-open`, and `ChaosEater-adapter-open` are
deferred. Their existing artifacts remain immutable historical evidence, but
they are excluded from active runs, active statistics, method-result
eligibility, and knowledge feedback until a separate unified comparison is
approved.

## Where it runs

- Frozen project evidence and run records: this repository under
  `artifacts/experiments/chaosatlas_10_projects/`.
- Immediate follow-up queue and new method-owned outputs:
  `artifacts/experiments/chaosatlas_followup_four_projects_2026-08-13/`.
- ChaosAtlas compiler and shared evidence runner: `tools/` in this repository.
- Runtime: namespace-local workloads on the WSL-native `chaos-kind` cluster;
  each active method run must use an isolated namespace and a clean
  project/runtime snapshot. A separate kind context is preferred once more
  than one project is active.

## Required order for every project

1. Freeze commit, source-tree hash, deployment assets, image provenance, and
   project namespace.
2. Build and validate the YAML/Compose topology IR and a deterministic
   business oracle.
3. Deploy the project and pass health, baseline, recovery, and cleanup gates.
4. Generate the complete-method and ablation outputs from the same frozen
   project snapshot. The ablation differs only by the declared knowledge
   removal.
5. Compile each ChaosAtlas output into bounded, namespace-local Chaos Mesh YAML.
6. Before every method run, verify no residual Chaos resources, clean output
   directory, matching source/image/topology hashes, and a stable oracle.
7. Execute selected hypotheses under a shared observation budget and record
   injection, observation, recovery, cleanup, and evidence hashes.
8. After every method run, require recovery, cleanup, washout, residual-Chaos
   scan, and namespace stability before the next method starts.
9. Evaluate both outputs with the independent oracle. Confirmed weaknesses need
   two valid reproductions; protected behavior is recorded as positive defense
   evidence.
10. Close the project, review the evidence, and only then permit a reviewed
    static abstraction to flow to a later complete-method KB. No same-project
    feedback; no feedback enters the ablation.

## Ten-project ledger state

- P02 is the only project with a passed runtime gate and valid baseline/oracle
  evidence. It is the first main-track pilot candidate, not a completed main
  experiment.
- P01, P03, P05, P06, P07, P08, P09, and P10 remain environment/build blocked.
- P04 remains out of domain under the current bounded runtime budget.
- No project is yet eligible for a formal cross-project superiority claim.

The ten-project ledger remains a frozen planning and audit record. It does not
override the immediate four-project execution queue.

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

## Deferred comparison boundary

ChaosEater is not deleted or reinterpreted. Its prior reports, audits, and
comparison notes remain under their existing paths with their original method
ownership. They must not be copied into the active candidate pool, used as
runtime labels, used to select current mutations, included in current
project-clustered statistics, or projected into the ChaosAtlas knowledge base.
A future unified comparison must start from a newly frozen protocol, shared
inputs, explicit namespace/snapshot isolation, and a fresh contamination audit.
