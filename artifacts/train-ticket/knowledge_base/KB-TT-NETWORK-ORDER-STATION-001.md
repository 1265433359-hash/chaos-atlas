# Candidate Knowledge Card: Order Network Delay

## Decision

Defer this injection for the station-service downstream hypothesis. The YAML and target are real, but the current production refresh path does not call the downstream station lookup.

## Evidence chain

```text
NetworkChaos delay
  -> namespace train-ticket / app=ts-order-service
  -> ts-order-service target exists
  -> /api/v1/orderservice/order/refresh exists
  -> queryOrdersForRefresh reads orders
  -> queryForStationId -> ts-station-service exists as a source-level candidate
  -> production call is commented out at OrderServiceImpl.java:200
```

The downstream `RestTemplate.exchange` is present at `OrderServiceImpl.java:211-217`, but static source evidence alone does not prove that a selected production request reaches it.

## Test-node-centered graph

The graph contains only the order-service slice relevant to this NetworkChaos node: selector/target, controller route, service methods, repository data, candidate downstream call, logs, and recovery signals. Other Train Ticket modules are not included in the card unless they are connected by this test node.

## Current judgment

- YAML syntax: confirmed by the catalog.
- Target existence: confirmed by selector-to-Deployment/Service matching.
- Candidate downstream call: confirmed statically.
- Business reachability: not reachable in the current source through `/order/refresh`.
- Timeout/retry/fallback defense: no local implementation found; runtime behavior is unknown.
- Runtime injection: blocked until an isolated cluster and a baseline request/trace are available.

## Experience candidate

Do not count a chaos result as a defense or failure of a downstream call until the business request trace proves that the call occurred. A unit test that calls `queryForStationId` directly is useful code evidence, but it is not production path evidence.
