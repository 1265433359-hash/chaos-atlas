# Knowledge Card v5: Basic CPU Stress With Downstream Call

## Decision

The selector-generated CPU test reached the real `ts-basic-service` Pod and exercised the confirmed `BasicController -> BasicServiceImpl -> ts-station-service` path. CPU pressure was measurable in cgroup-v2 for both a controlled not-found oracle and a seeded successful station lookup. The two oracles were then repeated with the same three-request warm-up and ten-request formal window.

## Runtime result

- Profile: one worker, 80 percent load, 45 seconds.
- Lifecycle: `injectedCount=1`, `recoveredCount=1`, resource absent after cleanup, zero Pod restarts.
- Resource effect: `nr_throttled +433`, `throttled_usec +8,647,513 microseconds`; post-recovery samples added zero throttling.
- Business effect: 10 requests returned HTTP 200 with the same `Not exists` envelope; median latency was 71.457ms versus 24ms baseline.
- Logs confirmed all 10 upstream Basic calls and all 10 downstream Station calls.
- Success oracle: `shanghai` returned the seeded station UUID in all 10 requests; median latency was 26.526ms versus a 27.378ms baseline.
- Not-found oracle: median latency was 71.457ms versus a 24ms baseline. The difference is an observation to reproduce, not a causal SLO conclusion.
- Controlled repeat: three warm-up requests were excluded from measurement; ten formal requests per oracle were sampled every 0.5 seconds with a five-second timeout.
- Controlled success repeat: all ten responses preserved the seeded UUID; median latency was 32.581ms versus 27.378ms baseline (+5.203ms). cgroup deltas were `nr_throttled +434`, `throttled_usec +8,107,212 microseconds`.
- Controlled not-found repeat: all ten responses preserved `status=0, msg=Not exists`; median latency was 33.864ms versus 24ms baseline (+9.864ms). cgroup deltas were `nr_throttled +423`, `throttled_usec +3,061,704 microseconds`.
- Both controlled replays recovered and cleaned up; post-recovery cgroup deltas were zero, and Basic/Station logs matched all ten formal calls per oracle.
- Strong bounded profile: four workers at 100 percent for 60 seconds, with the same three-request warm-up and ten formal requests. All ten success requests returned HTTP 200 with the seeded UUID, but median latency reached 101.404ms versus 27.378ms baseline (+74.026ms). cgroup deltas were `nr_throttled +588`, `throttled_usec +167,266,489 microseconds`; post-recovery deltas were zero.
- The strong run did not cross the five-second client timeout or produce a 5xx. Fresh application-log capture was unavailable because the read-only permission review timed out, so this run is not promoted to a new downstream-log rule.
- Concurrent profile: the r1 CPU profile was kept unchanged while 12 formal success requests were issued in batches of four concurrent callers. All responses preserved HTTP 200 and the seeded UUID; median latency was 92.826ms and p95 was 195.868ms versus 27.378ms baseline. cgroup deltas were `nr_throttled +440`, `throttled_usec +8,971,772 microseconds`; post-recovery deltas were zero.

## Test-node-centered graph

```text
StressChaos CPU
  -> ts-basic-service Pod / CPU limit
  -> BasicController.queryForStationId
  -> BasicServiceImpl.queryForStationId
  -> ts-station-service StationController.queryForId
  -> controlled not-found response
  -> cgroup + logs + latency observation
  -> recovery and cleanup
```

## New knowledge

CPU pressure can be observed directly while real downstream calls complete. Fixed warm-up removed the earlier single-run comparison bias. The stronger profile and the concurrent profile show partial resilience: response correctness remained intact, while latency degraded substantially. Concurrency is a separate test dimension and cannot be inferred from sequential requests. This does not establish stable latency SLO protection, timeout, retry, fallback or circuit-breaker behavior. The next experiment needs an explicit SLO and fresh downstream logs.

Evidence: `artifacts/train-ticket/runtime/generated_basic_stress_warmup_result.json`, `generated_basic_stress_success_strong_warmup_result.json`, `generated_basic_stress_success_concurrent_result.json`, the warm-up runner/cgroup/classification reports, the paired oracle log evidence, and `basic_stress_oracle_comparison.json`.
