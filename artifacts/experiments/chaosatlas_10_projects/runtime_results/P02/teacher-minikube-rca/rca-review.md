# P02 Discovery-Server RCA Review

- Status: `pending_human_review`
- Knowledge update applied: `false`
- Scope: two bounded `discovery-server` PodKill replays in `chaosatlas-p02`
- Cluster context: `minikube`
- Mutation: `discovery-server-pod-kill`
- Protocol: 60-second washout, 10 consecutive HTTP 200 successes, scoped logs/events/Zipkin capture

## Repository Redaction

Customer response-body PII was redacted in the committed JSON reports (name, address, city, telephone, pet name, and birth date). Status codes, timings, error bodies, lifecycle fields, logs, events, Zipkin sidecars, and sidecar hashes were preserved.

## Runtime Gates

| Report | Status | Baseline failures | Injected | Recovered | Chaos absent | Washout stable | Washout HTTP 500 |
|---|---|---:|---|---|---|---|---:|
| `rep-1.json` | `completed` | 0 | true | true | true | true | 2 |
| `rep-2.json` | `completed` | 0 | true | true | true | true | 2 |

Both reports recorded a replacement discovery-server Pod UID, successful cleanup with `NotFound`, and no global `PodChaos`, `NetworkChaos`, or `StressChaos` remaining after cleanup.

Report SHA-256:

- `rep-1.json`: `aab75053116c08b299a087d692d0ea1d467a6ca89a3105b4e111a68b78770982`
- `rep-2.json`: `6631cfbab97ae860403b3b4d470d7ada004d1e19c63fd4b105dae081aa4bc92c`

## Business Weakness

**Confirmed, pending human acceptance.** Both discovery-server kills produced two delayed HTTP 500 observations during the same run's post-cleanup washout, even though the replacement Pod was Ready and the immediate post-recovery oracle had returned HTTP 200.

This confirms a business-path availability gap that is not captured by Pod readiness alone. It does not by itself identify the internal mechanism.

## Directly Supported Mechanism

The logs support the following bounded statement:

> After discovery-server was killed and replaced, the `api-gateway` request path temporarily had no usable `customers-service` instance. The gateway logged `No servers available for service: customers-service`, then a downstream `503 SERVICE_UNAVAILABLE` for `GET http://customers-service/owners/1`, and exposed HTTP 500 on the business endpoint. In the same evidence window, `discovery-server` logged a missing customers-service lease followed by registration, while `customers-service` logged re-registration with status 204.

This is evidence of a **transient service-discovery visibility gap** associated with the discovery-server restart and recovery window. It is the strongest mechanism statement supported by the captured evidence.

## Not Established

The evidence does not establish:

- Eureka cache as the root cause.
- A specific cache invalidation or registration-propagation defect.
- A network fault.
- A customers-service process failure or Pod kill.

The discovery-server log contains a default-cache warning, but there is no cache-state evidence or trace correlation proving that warning caused the 500s. Zipkin was captured in both runs but contained no traces, so it cannot strengthen or weaken the mechanism attribution.

## Evidence Index

Key sidecars are present for both replicates:

- `rep-1.api-gateway.log`
- `rep-1.discovery-server.log`
- `rep-1.customers-service.log`
- `rep-1.events.json`
- `rep-1.zipkin.json`
- `rep-2.api-gateway.log`
- `rep-2.discovery-server.log`
- `rep-2.customers-service.log`
- `rep-2.events.json`
- `rep-2.zipkin.json`

The JSON reports contain the complete sidecar manifest, byte sizes, and SHA-256 values. The sidecar files were independently hashed after each run and matched the report metadata.

## Human Review

- Human decision: `pending`
- Knowledge update applied: `false`
- Review rule: do not write this result into the knowledge base until a human accepts the abstraction.
- Review note: keep the concrete root cause bounded to the observed service-discovery visibility gap; do not promote Eureka, cache, registration, or network hypotheses without additional direct evidence.
