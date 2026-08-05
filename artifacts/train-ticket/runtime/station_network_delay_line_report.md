# Station NetworkChaos Line Report

Status: closed at a runtime-confirmed client timeout boundary.

## Scope

This line isolates the `ts-station-service` NetworkChaos `direction=to` node and exercises the real Station lookup path with both a seeded success oracle and a controlled not-found oracle.

## Evidence

The seeded success oracle stayed HTTP 200 with the real UUID at all three delay levels:

| Nominal delay | Median latency | Outcome |
|---|---:|---|
| 100ms | 216.022ms | response preserved |
| 500ms | 1021.227ms | response preserved |
| 2s | 4020.903ms | response preserved, 5s budget approached |

The not-found oracle at 100ms stayed HTTP 200 with `status=0,msg=Not exists,data=stationName`; median latency was 215.359ms versus 32.038ms baseline. Its +183.321ms increase matched the success oracle's +185.876ms increase.

The 3s boundary probe crossed the 5s client observation budget: the client timed out at 5047.049ms. Station logs show the request entered `StationController.queryForStationId` at `13:15:36.350Z`, then logged the repository-backed Not Found branch at `13:15:42.414Z` (6063.895ms after request start). The server therefore completed after the client had already timed out.

## Final conclusion

Network delay is effective on the selected Station dependency path and causes monotonic end-to-end latency growth. The response contract remains correct below the boundary, but baseline latency behavior is not preserved. At the boundary, the client timed out while the server continued to completion. No client-side retry, fallback or circuit-breaker defense was established.

The dependency mapping is now runtime-configured: `ts-station-service -> train-ticket-mysql:3306` (database `ts`), confirmed by targeted non-credential environment inspection. Station logs confirm server-side completion; MySQL emitted no query line, so packet-level attribution remains unobserved. Further delay escalation is stopped because the 3s profile crossed the runner's 5s client observation budget. The 5s value is an experimental boundary, not an operator-defined production SLO.

## Reuse rule for the LLM

Match the exact test node, target service, network direction and business oracle. Treat response preservation, client-timeout behavior, server completion and latency-SLO preservation as separate outcomes. A server-side business response after a client timeout is partial or missing client-boundary defense, not full resilience. Distinguish runtime-configured peer identity from packet-level attribution; the former does not substitute for Trace.

The candidate selector now returns `closed_runtime_boundary_no_reinjection` for this exact node. The experience remains retrievable, but automatic mutation generation must not repeat it unless the knowledge card is deliberately reopened with new evidence requirements.
