# Knowledge Card v4: Station Network Delay Timeout Boundary

## Decision

The bounded NetworkChaos candidate selected the real `ts-station-service` Pod and exercised the direct seeded Station lookup while delaying the Station outbound dependency path.

## Runtime result

- Profile: `direction=to`, nominal latency `100ms`, duration `20s`, mode `one`.
- Controls: three warm-up requests excluded from classification, ten formal requests, 0.5s interval, 5s timeout.
- All formal requests returned HTTP 200 with the seeded station UUID.
- Median latency was 216.022ms versus 30.146ms baseline (+185.876ms); p95 was 234.324ms.
- Injection, recovery and cleanup were confirmed. A later boundary probe captured Station runtime logs, and targeted non-credential runtime configuration confirmed `train-ticket-mysql:3306`; the MySQL container emitted no query log, so packet attribution remains unobserved.
- Controlled not-found oracle: the same mutation preserved `status=0,msg=Not exists,data=stationName` for all ten formal requests; median latency was 215.359ms versus 32.038ms baseline (+183.321ms).
- The success and not-found latency deltas were close (+185.876ms and +183.321ms), indicating a reproducible network-edge effect rather than a branch-specific response failure.
- Boundary ladder on the success oracle: nominal 100ms produced 216.022ms median, 500ms produced 1021.227ms, and 2s produced 4020.903ms. All samples remained HTTP 200 with the seeded UUID; the 2s profile approached but did not cross the 5s client observation budget.
- Timeout boundary probe: nominal 3s with the controlled not-found oracle timed out at 5047.049ms. Station logged the request entry at `13:15:36.350Z` and the repository-backed `Not exists` branch at `13:15:42.414Z`, 6063.895ms after request start. The server therefore completed after the client had already timed out.

## Test-node-centered graph

```text
NetworkChaos delay
  -> ts-station-service Pod outbound edge
  -> StationController.queryForStationId
  -> StationServiceImpl.queryForId
  -> StationRepository.findByName
  -> train-ticket-mysql:3306 (runtime configuration confirmed)
  -> client timeout boundary / server-side branch completion
  -> latency + log + response observation
  -> recovery and cleanup
```

## New knowledge

The network delay was effective and substantially increased end-to-end latency. Below the boundary, both business response contracts remained correct. At the boundary, the client timed out while Station continued to the server-side Not Found branch, so this is `client_timeout_server_completion_after_delay`, not client-side defense. Source mapping identifies `StationRepository.findByName`; the running Pod configuration resolves its datasource to `train-ticket-mysql:3306`. Station logs confirm handler completion, but no packet-level Trace was collected. The 5s value is an experimental budget, not an operator-defined production SLO. Do not escalate delay further; obtain an SLO before making production-facing latency claims.

Evidence: `artifacts/train-ticket/runtime/generated_station_network_delay_boundary_comparison.json`, `generated_station_network_delay_oracle_comparison.json`, `station_network_edge_static_mapping.json`, the r1/r2/r3/r4 runner/classification reports, `generated_station_network_delay_r4_result.json`, both baselines, and the corresponding gate reports.
