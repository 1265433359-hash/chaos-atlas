# Knowledge Card v1: Station CPU Stress With Direct Success Oracle

## Decision

The selector-generated Station CPU test reached the real `ts-station-service` Pod and exercised `StationController.queryForStationId -> StationServiceImpl.queryForId -> StationRepository.findByName` using the seeded `shanghai` station.

## Runtime result

- Profile: one worker, 80 percent load, 45 seconds.
- Controls: three warm-up requests excluded from classification, ten formal requests, 0.5s interval, 5s timeout, 25 cgroup samples.
- All formal requests returned HTTP 200 with the seeded station UUID.
- Median latency was 43.308ms versus 30.146ms baseline (+13.162ms).
- cgroup deltas were `nr_throttled +406`, `throttled_usec +16,272,410 microseconds`; post-recovery deltas were zero.
- Injection, recovery and cleanup were confirmed. Fresh Station log capture was unavailable because the read-only permission review timed out.

## Test-node-centered graph

```text
StressChaos CPU
  -> ts-station-service Pod
  -> StationController.queryForStationId
  -> StationServiceImpl.queryForId
  -> StationRepository.findByName
  -> seeded success response
  -> cgroup + latency + response observation
  -> recovery and cleanup
```

## New knowledge

Direct downstream injection preserved the business response with a small latency increase. This is a separate hypothesis from Basic-upstream injection: the same UUID can remain correct while the latency effect differs by injection location. The result does not establish timeout, retry, fallback, circuit-breaker or concurrent-load behavior.

Evidence: `artifacts/train-ticket/runtime/generated_station_stress_success_result.json`, `generated_station_stress_success_warmup_runner_result.json`, `generated_station_stress_success_warmup_cgroup.json`, `generated_station_stress_success_warmup_classification.json`, `baseline_station_success.json`, and `stress_station_gate.json`.
