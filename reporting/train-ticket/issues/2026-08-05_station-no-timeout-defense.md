# Issue draft — No application-level timeout/retry/fallback/circuit-breaker in `ts-station-service` under confirmed outbound latency

> Status: DRAFT — for review before submission. Not yet posted to GitHub.
> Target: https://github.com/FudanSELab/train-ticket
> Submission channel: normal issue (repository has no `SECURITY.md` / `CONTRIBUTING.md`).
> Evidence source: bounded, isolated chaos-injection experiments in namespace `train-ticket-lab` (never `default`); no credentials or secrets disclosed.

---

## Title

`ts-station-service` has no application-level timeout, retry, fallback or circuit-breaker: under a confirmed outbound network delay the client times out while the server keeps working, and latency degrades linearly with no bound

## Summary

Under controlled `NetworkChaos` outbound delay (Chaos Mesh, direction `to`, target `ts-station-service`), the station lookup endpoint kept returning correct responses but its latency grew linearly with the injected delay, with no application-level bound. At a nominal 3s outbound delay the HTTP client (5s observation budget) timed out at **5047ms**, while the server completed the repository-backed branch **~1 second later (6064ms)**. Static source review of `ts-station-service` found no `timeout`, `retry`, `fallback`, or circuit-breaker configuration on the relevant path.

The experiments were run with `mode: one` (single pod), short bounded durations, and automatic recovery/cleanup. This is a partial-resilience observation: response *correctness* survived, but *latency SLO* was not protected and the client boundary was crossed.

## Environment

- Repository: `FudanSELab/train-ticket`
- Branch: `master`, commit `313886e99befb94be6cd45f085c98e0019f59829`
- Cluster: Docker Desktop Kubernetes (WSL2), Chaos Mesh 2.8.3, isolated namespace `train-ticket-lab`
- Datasource peer (runtime-confirmed, non-credential): `train-ticket-mysql:3306`, database `ts`

## Evidence

### 1. Delay ladder — correct responses, linear latency growth, no bound

`NetworkChaos` outbound delay on `ts-station-service`, success oracle `GET /api/v1/stationservice/stations/id/shanghai` (10 formal requests each, 3 warm-ups excluded):

| Nominal delay | Median latency | vs baseline (30.1ms) | Response contract |
|---|---|---|---|
| 100ms | 216.0ms | +185.9ms | HTTP 200 + station UUID preserved |
| 500ms | 1021.2ms | +991.1ms | HTTP 200 + station UUID preserved |
| 2s | 4020.9ms | +3990.8ms | HTTP 200 + station UUID preserved |

**Statistical repetition** (each profile repeated 3×, same fixed window): the effect is highly reproducible, especially the 500ms profile where the 95% CI is only ±5ms:

| Profile | n | mean of medians | 95% CI | all 200? |
|---|---|---|---|---|
| 100ms | 3 | 224.2ms | [206.9, 241.6] | yes |
| 500ms | 3 | 1021.5ms | [1016.8, 1026.2] | yes |
| Basic CPU r1 (context) | 3 | 51.4ms | [23.1, 79.8] | yes |

### 2. Timeout boundary — client times out, server completes later

At nominal **3s** outbound delay, with an explicit **5s client observation budget**:

- HTTP client: `5047.049ms`, status `null`, error `timed out` (client-side timeout, no 5xx).
- Server logs: request entered `StationController` at `13:15:36.350Z`; the post-repository Not Found branch completed at `13:15:42.414Z` = **6063.895ms** after request start, ~1.0s *after* the client gave up.
- `NetworkChaos` reported `injectedCount=1`; recovery (`recoveredCount=1`) and resource cleanup confirmed.

### 3. Static source review — no timeout/retry/fallback/circuit-breaker on the path

- `ts-station-service/src/main/resources/application.yml` and the station code path (`StationController.queryForStationId -> StationServiceImpl.queryForId -> StationRepository.findByName`) contain no `timeout`, `retry`, `fallback` or circuit-breaker configuration.
- The observed latency equals the nominal injected delay plus the normal baseline — i.e. the HTTP client simply waits; there is no short-circuit, cancellation, or fallback.
- The same absence applies to `ts-basic-service` (the upstream caller used in the companion Basic CPU/network experiments).

## Impact

1. **Latency SLO is unprotected.** A slow or partially degraded downstream (network edge, database, upstream service) directly translates into unbounded end-to-end latency up to the client timeout; there is no per-call timeout, retry budget, or fallback to cap it.
2. **Client-boundary gap.** A client that abandons the request at 5s still leaves the server working (6064ms completion) — wasted work, potential thread-pool saturation under load, and no propagation of cancellation to the repository call.
3. **Resilience claims should not be inferred.** HTTP 200 under a single short injection must not be read as "the system is resilient": correctness was preserved, latency protection was not.

## Reproduction (isolated lab, bounded)

```bash
# Requires a Docker-Desktop Kubernetes + Chaos Mesh 2.8.3 with train-ticket services in namespace train-ticket-lab
# 1) Apply bounded NetworkChaos delay (mode: one, direction: to, 3s, duration 30s)
# 2) GET /api/v1/stationservice/stations/id/shanghai with a 5s client timeout
#    -> client times out ~5.05s; server logs completion ~6.06s
# 3) Delete the NetworkChaos resource; verify recovery (recoveredCount=1)
```

## Suggested fix (for discussion)

1. Add a per-call HTTP timeout (e.g. `RestTemplate`/client timeout or circuit-breaker) on the station read path and on the Basic->Station call.
2. Decide an explicit latency SLO and add a client-side budget; ensure server-side work is cancelled (or bounded) when the client abandons.
3. If the dependency is expected to be slow, define a fallback/error response instead of unbounded waiting.

## Notes

- Reported for research purposes (fault-injection methodology validation). No credentials, secrets, or production data involved.
- The 5s value is the *experiment's observation budget*, not an operator-defined production SLO; a production latency SLO must be defined by the project owners.
- Companion issue: `queryOrdersForRefresh` disables its only downstream call (`ts-order-service -> ts-station-service`), so that edge is currently unreachable from the production `/order/refresh` workflow (see the other draft in this folder).
