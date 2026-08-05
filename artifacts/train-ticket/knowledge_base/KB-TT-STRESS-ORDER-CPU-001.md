# Knowledge Card v4: Order CPU Stress

## Decision

The raw YAML targets a real order-service Pod with a declared CPU request/limit and a TCP readiness probe. A selector-generated bounded mutation was injected only after the runtime gate passed, then recovered and cleaned up cleanly.

## Runtime result

- Generated mutation: `artifacts/train-ticket/runtime/generated_mutations/stress/order-stress-cpu-candidate-r1.yaml`.
- Profile: one worker, 80 percent load, 45 seconds; the cgroup sampler started only after `injectedCount=1`.
- Chaos status: `injectedCount=1`, then `recoveredCount=1`; the resource was absent after cleanup.
- cgroup evidence: `nr_throttled` increased by 432 and `throttled_usec` by 15,496,840 microseconds during the active window; both counters were stable after recovery.
- During injection: eight read-only requests returned HTTP 200 with the same response envelope; the Pod had zero restarts.
- Strong short profile: four workers, 100 percent load, 60 seconds; `injectedCount=1`, `recoveredCount=1`, `nr_throttled` increased by 593 and `throttled_usec` increased by 183615850.
- The strong profile still returned HTTP 200 for all 25 sampled requests, with latency 17-228 ms, and the Pod had zero restarts.
- Classification: bounded response resilience with measurable CPU throttling. The evidence is not an unconditional claim for the original five-minute duration or for downstream business paths not exercised by this request.

## Test-node-centered graph

```text
Candidate selector
  -> StressChaos CPU
  -> app=ts-order-service Pod
  -> CPU request/limit
  -> listener :12031 -> OrderController -> OrderServiceImpl
  -> readiness + latency/error observation
  -> automatic recovery
```

## New knowledge

A successful StressChaos record proves that the test node reached the intended container. The selector-generated replay additionally proves the candidate-to-runner pipeline: the sampler waited for injection, cgroup counters proved measurable throttling, and functional HTTP success plus zero restarts showed bounded resilience for the exercised path. The next test must exercise a real downstream call before generalizing to the complete service.

Evidence: `artifacts/train-ticket/runtime/generated_stress_result.json`, `artifacts/train-ticket/runtime/generated_stress_orchestration.json`, `artifacts/train-ticket/runtime/generated_stress_cgroup.json`, `artifacts/train-ticket/runtime/stress_order_cpu_result.json`, `artifacts/train-ticket/runtime/stress_order_cpu_strong_result.json`, and `artifacts/train-ticket/runtime/cgroup_cpu_strong.json`.
