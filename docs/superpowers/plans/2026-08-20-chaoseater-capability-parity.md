# Deployment Availability Capability Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend ChaosAtlas so deployment availability and fault recovery are native capabilities of the tool, with ChaosEater's Sock Shop cycle serving as one compatibility validation case rather than a separate implementation track.

**Architecture:** Generalize the existing TestNode/local-impact-graph/lifecycle/evidence-chain model from service edges to deployment service nodes and scenario nodes. A deployment node connects manifest facts (Deployment, ReplicaSet, Pod, Service, probes, PDB, HPA), injected faults, traffic/steady-state oracles, recovery transitions and improvement patches. ChaosEater's `availableReplicas` cycle is represented as a profile over this native layer; its replay is validation evidence, not a special code path. Capability coverage is reported per target/phase/oracle cell, never inferred from equal weakness counts.

**Tech Stack:** Python 3 standard library, Kubernetes/Chaos Mesh, existing `run_chaos_experiment.py`, `run_sock_shop_two_arm.py`, `sock_avail_sample.sh`, pytest.

---

## Native Capability Contract

ChaosEater is covered when its behavior can be expressed using the same native
interfaces as any other deployment test. No CE-specific selector, verdict or
hard-coded target is allowed in the core runner.

Every deployment or scenario TestNode must have:

`manifest_profile -> generated_fault_plan -> CE_steady_state -> runtime_observation -> recovery_oracle -> attribution -> improvement_retest`

The CE-compatible steady state must be copied from the archived CE scripts, not reconstructed from our rules. For the front-end replay it is:

```text
availability_ratio = samples(availableReplicas >= 1) / total_samples
max_zero_streak <= configured_limit
```

The `carts-db` replay keeps CE's separate 95% threshold. `desiredReplicas` is retained as
static deployment context, not substituted for CE's `>= 1` oracle.

The ChaosAtlas recovery oracle is stricter:

```text
replacement identity observed + Ready + business probe success for K consecutive samples + cleanup confirmed
```

The result must label each field as `verified`, `static_only`, `blocked`, or `not_run`.

### Task 1: Add deployment/scenario TestNodes to the native model

**Files:**
- Create: `artifacts/experiments/chaos_eater_capability_contract.json`
- Create: `tools/build_chaoseater_capability_pool.py`
- Modify: `tools/contract_inventory.py`
- Test: `tools/tests/test_chaoseater_capability_pool.py`

- [ ] Define a versioned deployment-node schema containing Deployment/ReplicaSet/Pod/Service/probe/PDB/HPA facts, selectors, traffic oracle, availability oracle, recovery deadline and cleanup contract.
- [ ] Define a scenario-node schema for ordered or concurrent fault phases; a phase may target multiple services and must retain target identity, duration and cleanup ownership.
- [ ] Extract CE's exact Sock Shop inputs from `artifacts/experiments/chaos_eater_deployed/ce_output.json` and the archived scripts as a profile conforming to these schemas: target deployments, steady states, k6 workload, fault kinds, durations, phase fan-out, sample interval, ratio threshold, zero-streak threshold and recovery window.
- [ ] Preserve CE's phase fan-out: phase 0 stresses `front-end` and `carts-db` together; phase 1 applies loss to both; phase 2 kills both; phase 3 kills the `rabbitmq-exporter` container. A one-target-per-run replay is not equivalent and must not count as parity.
- [ ] Build the general deployment candidate universe from every eligible Deployment x supported fault family; materialize CE's selected hypotheses as ordinary scenario nodes in that universe.
- [ ] Generate native hypotheses with `tools/run_native_full_discovery.py` from manifest-only frozen bundles; static Cartesian enumeration is only the coverage denominator, not evidence that the tool can perform hypothesis generation.
- [ ] Require every candidate to carry `desired_replicas`, `pdb`, probes, HPA, steady-state metric, recovery deadline, business probe and cleanup contract; missing facts become `unknown`, never a default defense.
- [ ] Store the immutable CE commit, input manifest hash, image digests and k6 profile. Test that the native model can represent CE's `front-end` and `carts-db` hypotheses with the original phase fan-out and archived steady-state scripts, without a CE-specific code branch.

### Task 2: Implement the CE-compatible availability and recovery oracle

**Files:**
- Create: `tools/availability_oracle.py`
- Modify: `tools/run_chaos_experiment.py`
- Modify: `tools/classify_runtime_result.py`
- Test: `tools/tests/test_availability_oracle.py`
- Test: `tools/tests/test_runtime_classification_consistency.py`

- [ ] Implement pure functions for `availability_ratio`, `max_zero_streak`, `replacement_identity`, `recovery_deadline`, and `business_probe_stability`.
- [ ] Execute the archived CE steady-state scripts or a differential-tested equivalent for replay; preserve CE's `availableReplicas` calculation as a separately named metric and do not replace it with Ready-only sampling.
- [ ] Execute the same k6 traffic profile used by CE for replay. A generic business probe is an additional signal, not a substitute for CE's traffic oracle.
- [ ] Classify recovery into `recovered_by_availability`, `recovered_by_business_oracle`, `probe_restart_escape`, `scheduler_or_platform_blocked`, and `recovery_timeout`.
- [ ] Add fixtures for the known failure modes: single-pod kill, no-readiness false recovery, liveness-probe restart escape, and scheduler outage.
- [ ] Ensure `recovery_timeout` cannot be downgraded to defended merely because a replacement Pod becomes `Running`.

### Task 3: Validate the native scenario runner against CE's composite attack sequence

**Files:**
- Create: `tools/run_chaoseater_capability_parity.py`
- Modify: `tools/run_sock_shop_two_arm.py`
- Modify: `tools/run_stress_with_cgroup.py`
- Test: `tools/tests/test_chaoseater_capability_parity.py`

- [ ] Compile CE's exact four phases into namespace-local resources with the original fan-out: `StressChaos(front-end,carts-db) -> NetworkChaos(50% loss on front-end,carts-db) -> PodChaos pod-kill(front-end,carts-db) -> PodChaos container-kill(rabbitmq-exporter)`.
- [ ] Start the archived CE k6 workload before injection and retain the CE-compatible sample stream plus the ChaosAtlas business-probe stream.
- [ ] Gate every phase on confirmed injection, record phase timestamps and resource UIDs, and remove each fault before the next phase.
- [ ] Use three replicates per exact CE scenario and three replicates per blind service-level candidate; retain invalid/platform-blocked runs outside weakness and capability denominators, while reporting them as missing capability cells.
- [ ] Add a dry-run mode that validates sequence ordering, selectors, duration and cleanup without touching a cluster.
- [ ] Run the same native scenario runner in blind mode for the generated hypotheses; CE replay is a compatibility fixture, not a separate execution path.
- [ ] Compare blind discovery output against the common denominator using the same hypothesis budget and compile gate; report selection coverage separately from execution coverage.

### Task 4: Add formal availability rules and attribution

**Files:**
- Modify: `tools/decision_engine.py`
- Modify: `tools/judgment_experience.py`
- Modify: `artifacts/experiments/availability_defense_design.md`
- Test: `tools/tests/test_decision_engine.py`
- Test: `tools/tests/test_judgment_experience.py`

- [ ] Promote `AD-SELFHEAL-001` into an executable rule requiring a configured recovery deadline and runtime evidence; keep environment-contaminated absolute recovery times out of generic rules.
- [ ] Promote `AD-PROBE-001` into an executable rule that distinguishes probe-induced restart from application self-healing and injection escape.
- [ ] Keep `AD-REDUNDANCY-001` as a static prior only; it predicts a single-point-of-failure but does not by itself prove recovery behavior.
- [ ] Require source/config evidence for mechanism claims such as “probe timeout caused restart”; otherwise emit a bounded runtime finding.
- [ ] Add tests proving that static-only, recovery-timeout, probe-escape and fully recovered cases receive different verdicts.

### Task 5: Close the improvement and capability coverage loop

**Files:**
- Create: `tools/chaoseater_capability_report.py`
- Modify: `tools/feedback_protocol.py`
- Modify: `docs/CHAOSATLAS_METHOD_DETAILED_FOR_SUPERVISOR_2026-08-16.md`
- Test: `tools/tests/test_chaoseater_capability_report.py`

- [ ] Generate a manifest patch proposal for each confirmed availability/recovery finding: replicas/PDB/HPA/probe changes must include an exact file, JSON/YAML diff, rationale and expected oracle change.
- [ ] Re-deploy the patched manifest in a fresh namespace, rerun the same sequence and mark improvement as `verified`, `regression`, `deployment_blocked` or `not_run`.
- [ ] Produce `capability_coverage.json` with one row per `(track, target, phase, steady_state, recovery_path, improvement_action)` cell and fields for input parity, fault parity, steady-state parity, recovery parity, attribution parity and improvement parity.
- [ ] Report two separate scores: `capability_coverage` and `weakness_surface_overlap`; do not use the latter as a proxy for the former.
- [ ] Add a regression test requiring the report to mark full parity incomplete if any required replay cell is `not_run` or `blocked`. A blocked cell may produce only a `partial_capability_coverage` report; it cannot satisfy the parity claim.

## Acceptance Evidence

The parity claim is allowed only when:

1. The native deployment/scenario model represents CE's `front-end` and `carts-db` hypotheses, with the original phase fan-out and archived steady-state scripts.
2. The archived CE k6 workload and Kubernetes API oracle both execute for every valid replay replicate.
3. All four CE fault phases execute with the original multi-target schedule. An environment block makes the replay incomplete, not complete.
4. Both `availableReplicas` and business recovery metrics are present for every valid replicate.
5. Probe escape, no-readiness false recovery and scheduler contamination are separately classified.
6. The blind track reports service-level hypothesis coverage against the full Deployment x fault-family universe.
7. At least one manifest improvement is redeployed and re-tested, or the improvement gap is explicitly reported.
8. The final report contains no raw weakness-count superiority claim.

Run the focused checks with:

```powershell
python -m pytest tools/tests/test_chaoseater_capability_pool.py tools/tests/test_availability_oracle.py tools/tests/test_chaoseater_capability_parity.py tools/tests/test_chaoseater_capability_report.py -q
python tools/chaoseater_capability_report.py --contract artifacts/experiments/chaos_eater_capability_contract.json --output artifacts/experiments/chaoseater_capability_coverage.json
```

The final report must preserve the existing confirmation-bias and environment-contamination limitations documented in `artifacts/sock-shop/sock_availability_layer_verified.md`.
