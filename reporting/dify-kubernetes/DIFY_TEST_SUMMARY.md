# Dify Kubernetes Chaos Testing Summary

**Date:** 2026-09-04

**Tested project:** Dify `1.17.0`

**Test project:** ChaosAtlas

**Deployment:** Self-hosted Dify on Kubernetes

**Kubernetes context:** `chaosatlas-dify`

**Namespace:** `dify-k8s-lab`

**Business Oracle:** `POST /v1/chat-messages` with a published Chatflow

## Purpose

This document records the Dify tests performed by ChaosAtlas. It separates:

- behavior that is reproducible in Dify at runtime;
- deployment or Helm configuration observations;
- duplicate or already-submitted GitHub issues; and
- failures in ChaosAtlas or the Chaos Mesh test environment.

ChaosAtlas is the testing tool. Dify is the system under test.

## Test Scope

The adaptive Dify profile generated:

- 10 target workloads;
- 17 concrete fault capabilities from the canonical 32-capability catalog;
- 170 baseline candidates;
- 160 parameterized variants; and
- 330 total parameterized candidates.

The canonical ChaosAtlas catalog has two levels: 8 fault categories containing
32 concrete fault capabilities. This Dify profile exercised 17 concrete
capabilities across 6 categories. The remaining 15 concrete capabilities were
recorded as `inapplicable` for this environment; they are not counted as live
successes.

ChaosAtlas now has 40 method-level capability definitions: the 32 formal
capabilities plus 8 validated extension capabilities. Extensions remain in a
separate namespace until promotion, so the historical 32-capability Dify
coverage denominator is unchanged.

### Adapter Expansion Validation

The Dify adapter was expanded and revalidated on 2026-09-03. The live
inventory now includes 14 workloads: the original 10 Deployments plus the
PostgreSQL, Redis, and Weaviate StatefulSets, as well as the dedicated
`dify-extension-canary` Deployment. It also records 5 PVCs, 14 ConfigMap
metadata records, 12 Secret metadata records, and 19 dependency edges. Secret
values are never included in the inventory. The resulting space contains 462
core candidates and 11 supported extension candidates.

Final adapter matrix evidence: `.runs/dify-extension-probe-20260903-adapted-r2/project_matrix.json`.

Service-to-workload matching now accepts selector subsets, so headless and
component-labeled services are not dropped merely because their selectors are
less specific than the workload selector. HPA and PDB facts are attached when
present; this Dify installation currently exposes none in the tested namespace.

### Target Workloads

The candidate space covered these workloads:

- `agent-backend`
- `api`
- `beat`
- `local-sandbox`
- `plugin-daemon`
- `proxy`
- `sandbox`
- `ssrf-proxy`
- `web`
- `worker`

### Fault Capabilities

The profile included:

`config_drift`, `config_reload`, `container_kill`, `dns_delay`,
`dns_failure`, `env_misconfiguration`, `network_bandwidth`,
`network_corrupt`, `network_delay`, `network_duplicate`, `network_loss`,
`network_partition`, `pod_kill`, `replica_reduction`, `rollout_pause`,
`stress_cpu`, and `stress_memory`.

## Test Method

The run used the guarded LLM policy mode with the Chatflow business Oracle.
The policy loop was:

1. inventory Dify workloads and create baseline candidates;
2. run the lowest-cost baseline fault first;
3. observe the business response, Kubernetes state, logs, recovery, and cleanup;
4. expand to parameter variants only when the evidence justified it;
5. require three valid reproductions before declaring a stable anomaly; and
6. perform RCA and knowledge promotion after the evidence gates passed.

The Dify profile also enabled a configurable parameter-audit floor:
after a baseline is valid, each causal cluster with a parameter ladder must
exercise at least one untested parameter level, starting with the lowest-cost
preferred level. This floor is project-profile configuration and does not
replace the anomaly confirmation gate.

The LLM provided candidate prioritization and policy advice under the guarded
controller. Evidence validity, cleanup, and the `3/3` anomaly gate remained
deterministic safety conditions. When the LLM advisory was unavailable, the
controller used its deterministic fallback without bypassing those gates.

## Execution Results

The final consolidated run was:

`.runs/dify-parameter-round-20260904/live`

Recorded results:

| Metric | Result |
|---|---:|
| Parameter-audit actions in second round | 78 |
| Consolidated unique hypotheses seen | 250 |
| Consolidated trial records | 457 |
| Consolidated valid trial records | 428 |
| Baseline coverage | 167/170 (98.24%) |
| Parameter coverage | 82/160 (51.25%) |
| Stable anomaly candidates | 16/330 (4.85%) |
| Stable confirmation among anomaly candidates | 16/16 (100%) |
| Environment-blocked candidates | 3 |
| Promoted knowledge-base records | 11 |

The first run established the baseline and anomaly evidence. The second
history-aware run then executed the 78 remaining mandatory parameter-audit
actions. All 78 completed with verified cleanup and no retry exhaustion.
Three DNS-failure candidates remain blocked by the environment gate. They are
reported as environment limitations, not as Dify defects.

The second round used DeepSeek `deepseek-v4-flash` in guarded mode. All 79
policy decisions, including the terminal stop decision, were accepted by the
deterministic safety guard; no policy fallback was needed. The terminal stop
condition was that all mandatory baseline and parameter-audit work was
complete, with no pending confirmation.

The stable anomaly count is not the number of Dify bugs. It includes deployment
availability observations and behaviors that were not appropriate to submit as
Dify application issues.

## Submitted Dify Issues

### 1. Plugin daemon restart returns `400 invalid_param`

**Status:** Submitted by the user. The public URL was not recorded in this
archive.

Failure chain observed:

```text
plugin daemon restart
    -> plugin runtime is not registered or restored yet
    -> Redis has no state for the plugin runtime
    -> plugin daemon reports no available node and returns 404
    -> Chatflow API returns 400 invalid_param
```

The plugin-daemon logs repeatedly contained `no plugin states found in redis`,
`no plugin available nodes found`, and `no available node, plugin runtime not
found`. The unchanged valid Chatflow request returned HTTP `200` after recovery.
The behavior was reproduced in three independent restart trials.

This is a Dify runtime error-classification and dependency-recovery issue. The
test does not claim that the exact source-level registration or exception
mapping code has been isolated.

### 2. Single API replica exposes transient HTTP 502 responses during restart

**Status:** Submitted by the user.

Issue: [#41624](https://github.com/langgenius/dify/issues/41624)

This reports the externally visible restart behavior of a single API replica.
It should be understood as a deployment availability observation, rather than a
claim that the Dify application code alone provides high availability when
deployed with one replica.

### 3. API network degradation and PostgreSQL timeout

**Status:** Already reported; do not create a duplicate.

Issue: [#41626](https://github.com/langgenius/dify/issues/41626)

Under an API network bandwidth limit, the API log showed a PostgreSQL receive
timeout:

```text
psycopg2.OperationalError:
could not receive data from server: Connection timed out
```

The exception reached the HTTP handler and produced HTTP `500` after about
`7.9` seconds. Later successful requests took about `18.0-20.6` seconds,
compared with a baseline of about `1.3-1.7` seconds. The pattern was observed
across six valid low/high bandwidth trials.

## Findings Not Submitted to Dify

### Helm and deployment configuration observations

The following were intentionally not submitted, according to the project
scope decision:

- Helm chart `appVersion` metadata differing from the deployed image version;
- Helm or deployment defaults that leave API or Plugin daemon at one replica;
- Plugin daemon single-replica outage behavior as a high-availability claim;
- a separate API single-replica single-point-of-failure issue, because it
  overlaps with #41624 and the deployment topology rather than a distinct
  application defect.

These observations may be useful for deployment documentation or a separate
deployment-configuration repository, but they are outside the current Dify
application issue submission scope.

### Related but non-duplicative reports

The Dify repository already contains older reports about plugin-daemon errors
and `no available node, plugin runtime not found`. Those reports do not cover
the exact restart-triggered Chatflow sequence above. They were treated as
related context, not as a reason to suppress the new runtime issue.

## ChaosAtlas and Environment Findings

These findings belong to ChaosAtlas or the test environment and must not be
filed as Dify defects:

- 10 attempts where fault injection could not be confirmed;
- 1 early `apply_failed` attempt;
- 3 candidates permanently classified as `environment_blocked` after retry
  exhaustion;
- cleanup, recovery-attestation, and observation-state issues recorded in the
  ChaosAtlas issue drafts; and
- gaps between the abstract fault capability registry and executable Dify
  adapters.

The final environment was recovered: Dify workloads were Ready and no owned
Chaos Mesh resources remained.

## Extension Capability Probe

ChaosAtlas now supports a separate provisional extension namespace for
`extension.io_delay`, `extension.io_error`, `extension.time_offset`,
`extension.jvm_gc_pause`, `extension.dependency_delay`, and
`extension.dependency_unreachable`, `extension.queue_backlog`, and
`extension.connection_pool_exhaustion`. These bring the method-level count to
40 without changing the formal 8-category, 32-capability Dify catalog.

The read-only probe against Dify Kubernetes on 2026-09-03 found:

| Extension | Status | Reason |
| --- | --- | --- |
| `extension.io_delay` | `supported` | Dedicated disposable Dify extension target exposes `/data` |
| `extension.io_error` | `supported` | Dedicated disposable Dify extension target exposes `/data` |
| `extension.time_offset` | `supported` | Dedicated disposable Dify extension target is declared |
| `extension.jvm_gc_pause` | `inapplicable` | No JVM image was discovered in the Dify workloads |
| `extension.queue_backlog` | `supported` | Dedicated disposable Dify extension target declares a queue agent |
| `extension.connection_pool_exhaustion` | `supported` | Dedicated disposable Dify extension target declares a connection-pool agent |
| `extension.queue_backlog` | `blocked` | No explicit workload-local queue agent is declared |
| `extension.connection_pool_exhaustion` | `blocked` | No explicit workload-local connection-pool agent is declared |

The IOChaos, TimeChaos, and JVMChaos CRDs and the Chaos Mesh controller/daemon
were available and Ready. This probe performed no injection. The resulting
read-only evidence is stored in
`.runs/dify-extension-probe-20260903/project_matrix.json`.

## Extension Canary Results

Because the Dify workloads do not expose a disposable IO path or a JVM
runtime, the extension capabilities were validated in a temporary isolated
canary namespace rather than by mutating Dify's PVCs or containers. The canary
used a Python HTTP service with an `emptyDir` volume at `/data`; the namespace
was deleted after the run.

Evidence: `.runs/extension-canary-40-20260903-r2/summary.json`

| Extension | Target | Result | Evidence |
| --- | --- | --- | --- |
| `extension.io_delay` | Python canary `/data` | Executed, observed, pass | IOChaos injected and recovered; HTTP 200 with 1066.656 ms latency (baseline 1093.151 ms) |
| `extension.io_error` | Python canary `/data` | Executed, observed, pass | IOChaos injected and recovered, but the canary still returned HTTP 200; no business-level IO error was observed |
| `extension.time_offset` | Python canary `/clock` | Executed, degraded | TimeChaos injected and recovered; independent oracle measured `+0.4972 s` |
| `extension.jvm_gc_pause` | Dify target | Inapplicable | No JVM runtime in Dify; JVM canary was intentionally excluded from this three-capability run |
| `extension.queue_backlog` | Python canary `/queue` | Executed, degraded | Native queue agent observed depth `100`, then recovered to `0`; valid attestation |
| `extension.connection_pool_exhaustion` | Python canary `/pool` | Executed, degraded | Native pool agent observed `20/20` and `100%` utilization, then recovered to `0/20`; valid attestation |

All five applicable canaries had valid runtime attestations, including
baseline, injection, observation, recovery, cleanup, and independent-oracle
evidence. The results prove that ChaosAtlas can compile, scope, inject, observe,
recover, and clean up five extension types in an isolated Kubernetes target.
They do not mean that every extension produces a user-visible failure:
`io_error` was confirmed at the injection layer but did not cause an HTTP error
in this canary, and the single IO latency sample is not a reliable quantitative
latency benchmark because it includes local port-forward overhead.

The canary run also exposed and fixed two ChaosAtlas runner defects:
the fixture apply namespace was omitted, and the HTTP probe passed arguments
in the wrong order. Compiler-only CRD metadata is now removed at the
Kubernetes apply boundary so strict Chaos Mesh decoding succeeds.

The disposable target manifest is
`projects/dify-kubernetes/disposable-extension-target.yaml`. It uses only an
`emptyDir` volume and the ChaosAtlas extension image. The existing
`/app/api/storage` PVC is not treated as a safe test target merely because it
is writable.

The Dify namespace disposable extension canary completed with valid lifecycle
attestations:

Evidence: `.runs/dify-disposable-extension-canary-20260903/summary.json`

| Extension | Observation | Recovery | Cleanup |
| --- | --- | --- | --- |
| `extension.queue_backlog` | Queue depth `100` | Queue depth `0` | Confirmed |
| `extension.connection_pool_exhaustion` | `20/20`, utilization `100%` | `0/20`, utilization `0%` | Confirmed |

These results validate the adapter and disposable-agent path in the Dify
namespace. They are not claims about the internal Redis or PostgreSQL pools.

## Dependency-Edge Extension Experiment

The method layer was extended with a generic dependency-edge contract. A
project profile declares a logical edge by source and target Service name; the
Kubernetes adapter resolves both selectors from live inventory, creates a
stable dependency candidate, and the compiler emits a scoped NetworkChaos
manifest. This keeps the dependency model project-agnostic while allowing a
project adapter to provide its own topology facts.

Dify was used for the first live validation with the edge
`dify-k8s-api -> dify-k8s-plugin-daemon`:

Evidence: `.runs/dify-dependency-canary-20260903-api-plugin-r2/summary.json`

| Field | Result |
| --- | --- |
| Fault | `extension.dependency_delay` |
| Parameters | `100ms`, `0ms` jitter, `10s` |
| Injection | Confirmed; source and target PodNetworkChaos children were created |
| Business observation | Chatflow returned HTTP 200; baseline `1349.235 ms`, observe `1420.009 ms` |
| Recovery | Confirmed; Chatflow returned HTTP 200 in `1477.140 ms` |
| Cleanup | Verified; 2 child resources removed, residual count `0` |
| Final verdict | `pass`; lifecycle attestation valid |

The first run was not promoted because cleanup discovered an unowned target
PodNetworkChaos child. ChaosAtlas was corrected to derive cleanup ownership
from the dependency target selector, and the rerun passed. This is a
ChaosAtlas cleanup defect caught by the safety gate, not a Dify issue.

### Next-round dependency and StatefulSet validation

After the initial dependency runs, the lifecycle executor found one cleanup
defect: it resolved only `spec.target.selector`, while IOChaos and some other
Chaos Mesh resources use the top-level `spec.selector`. The executor now
resolves and unions both selector locations, while accepting only selectors
that are exactly scoped to the executor namespace. Regression coverage includes
top-level selector discovery, selector union, and cross-namespace rejection.

The known residual `PodIOChaos` was deleted only after its owner reference was
verified to point to the ChaosAtlas disposable target. A namespace-wide sweep
then returned `confirmed=true`, `status=verified`, and `residual_count=0`.

The corrected dependency runs were:

| Fault | Edges | Result |
| --- | --- | --- |
| `extension.dependency_delay` | API -> Plugin daemon, PostgreSQL, Redis | 3/3 executed with valid attestation and cleanup |
| `extension.dependency_unreachable` | API -> Plugin daemon, PostgreSQL, Redis | 3/3 executed with valid attestation and cleanup; no business anomaly observed |

The dependency-unreachable tests therefore demonstrate that the selected
Chatflow request path remained healthy during this short, scoped disruption.
They do not prove that every Dify operation is independent of those services.

The StatefulSet service canary then tested the three stateful services with
`PodChaos` `pod-kill` and service-specific independent oracles:

| Target | Repetitions | Observation | Recovery | Cleanup |
| --- | ---: | --- | --- | --- |
| PostgreSQL | 3/3 | transient `degraded` | 3/3 confirmed | 3/3 confirmed |
| Redis | 3/3 | transient `degraded` | 3/3 confirmed | 3/3 confirmed |
| Weaviate | 3/3 | transient `degraded` | 3/3 confirmed | 3/3 confirmed |

Evidence roots:

- `.runs/dify-dependency-delay-20260903-fixed-api-plugin-daemon/`
- `.runs/dify-dependency-delay-20260903-fixed-api-postgresql/`
- `.runs/dify-dependency-delay-20260903-fixed-api-redis/`
- `.runs/dify-dependency-unreachable-20260903-fixed-api-plugin-daemon/`
- `.runs/dify-dependency-unreachable-20260903-fixed-api-postgresql/`
- `.runs/dify-dependency-unreachable-20260903-fixed-api-redis/`
- `.runs/dify-statefulset-pod-kill-20260903-r1/`
- `.runs/dify-statefulset-pod-kill-20260903-r2/`
- `.runs/dify-statefulset-pod-kill-20260903-r3/`

The final environment check found 14/14 Pods Ready and no remaining
ChaosAtlas-owned or target-owned Chaos Mesh resource.

## RCA and Experience Library

RCA was run for candidates that passed the evidence contract. The promotion
stage retained 11 `local_reusable` knowledge cards and updated the Dify
Kubernetes knowledge index. Each card has confirmed RCA, three independent
valid reproductions, promotion audit evidence, and regression intents. The
second parameter round produced no additional card because it found no new
stable RCA-confirmed weakness.

The coverage report now counts the same 11 cards as reusable experience. The
policy layer canonicalizes the profile's human-readable revision identifier
before retrieval, so the selector can actually consume the experience cards
that the promotion stage writes.

## Overall Conclusion

ChaosAtlas successfully exercised Dify through a broad Kubernetes fault space
and connected business behavior with workload, log, recovery, and cleanup
evidence. Three Dify-facing runtime observations are now accounted for:

- Plugin daemon restart exposes a dependency failure as `400 invalid_param`;
- single API replica restart behavior is tracked by #41624; and
- API network degradation and PostgreSQL timeout behavior is tracked by #41626.
- PostgreSQL, Redis, and Weaviate each recovered from a single-Pod disruption
  in all three repetitions; no new Dify application issue is claimed from
  these expected recovery observations.

Helm Chart metadata and default replica configuration remain intentionally
excluded from the submitted Dify application issues. The next Dify activity
should focus on maintainer feedback, source-level confirmation of the two
runtime error paths, and targeted regression tests rather than duplicate issue
creation.

## Evidence Index

- Initial run: `.runs/dify-k8s-final-20260903`
- Parameter-audit run: `.runs/dify-parameter-round-20260904/live`
- Issue drafts: `reporting/dify-kubernetes/issues/`
- Knowledge artifacts: `artifacts/dify-kubernetes/knowledge_base/`
