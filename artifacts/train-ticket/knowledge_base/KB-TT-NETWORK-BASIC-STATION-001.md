# Validated Knowledge Card v3: Basic-to-Station Network Delay

## Decision

This test node is valid and useful for a bounded latency experiment. The selector reached the real `ts-basic-service` Pod, the request reached `ts-station-service`, Chaos Mesh injected and recovered the delay, and the response contract stayed HTTP 200. The observed result is functional response preservation with latency degradation, not proof of complete timeout or fallback defense.

## Test-node-centered graph

```text
NetworkChaos delay (500ms, app=ts-basic-service)
  -> Basic Pod :15680
  -> BasicController.queryForStationId
  -> BasicServiceImpl.queryForStationId
  -> ts-station-service :12345
  -> StationController.queryForId
  -> HTTP 200 {status:0,msg:Not exists,data:null}
  -> latency/log observation
  -> Chaos Mesh recovery and resource cleanup
```

The graph is intentionally local to this test node. Unrelated Train Ticket modules are excluded from the card.

## Evidence

- Baseline: 3 requests returned HTTP 200 in 20-57ms.
- During the 45-second injection: 20 requests returned HTTP 200 with the same body contract; repeated delayed samples were 525-532ms.
- After recovery: repeated samples returned to 24-32ms.
- Chaos Mesh reported `selected=true`, `injectedCount=1`, `recoveredCount=1`, and `AllRecovered=true`.
- Basic and Station logs confirm the controller and downstream call path.
- The Pod remained Ready with zero restarts.

## Automated classification

The result classifier keeps three states separate:

- `response_preserved_latency_degradation`: the 100ms runner smoke preserved HTTP 200 but had a median latency of 196.611ms versus the 24ms baseline.
- `client_timeout_observed`: the confirmed 5s profile crossed the 10-second client budget.
- `platform_or_preflight_blocked`: the HTTPChaos smoke was rejected before apply because ebtables is unavailable.

These classifications are evidence states, not automatic claims that the application defended or failed. The classifier reports are `runner_network_smoke_classification.json` and `network_basic_station_5s_classification.json`.

## Selector replay

The candidate selector ranked the raw `basic-network-delay` sample first, the mutation generator rewrote it to the isolated namespace with a 100ms/20s bounded profile, and the runner confirmed injection, two requests, recovery, and cleanup. The replay was again classified as `response_preserved_latency_degradation` with a 187.527ms median versus the 24ms baseline. This validates the decision pipeline, not just a manually authored YAML.

## Timeout boundary follow-up

An atomic 5-second profile waited for `injectedCount=1` before issuing the request. With a 10-second client timeout, the client timed out at 10.041s. Basic and Station logs show that the downstream handler and normal business response occurred around 10 seconds after request start. This is classified as `client_timeout_partial_or_no_defense`: the downstream code eventually completed, but no fast timeout, retry, fallback, or circuit-breaker behavior was observed at the upstream boundary.

Static source evidence supports the hypothesis: `BasicApplication.java:32-34` creates a `RestTemplate` with `RestTemplateBuilder.build()` and `BasicServiceImpl.java:324-340` calls `exchange` without an explicit timeout or local recovery branch. Library defaults still need a dependency-level/runtime check before becoming a universal rule.

The execution gate is part of the experience: `kubectl apply` completion is not equivalent to injection. A request is valid evidence only after Chaos Mesh reports `injectedCount >= 1`, and recovery must be observed before cleanup.

## Experience for the LLM

A response that remains successful under chaos is not automatically a full defense. First prove that the selected request traversed the affected downstream edge. Then compare both functional outcome and latency against baseline. Here the delay stayed below the effective failure boundary, so the valid response propagated; timeout, retry, fallback, circuit-breaker, and SLO protection remain unproven.

## Next test

Repeat the boundary run with a client that records the eventual server response separately from the client timeout, inspect the effective RestTemplate request factory and Spring Boot defaults, and test repeated calls for connection or retry amplification. Compare `to`, `from`, and `both` directions. Keep the namespace isolated, use a single target, wait for real injection, record an abort threshold, and delete the resource after every run.
