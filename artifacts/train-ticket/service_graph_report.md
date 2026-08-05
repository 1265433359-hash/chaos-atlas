# Train Ticket Static Service-Call Graph

## Scope

This graph is derived from service `application.yml` files and production source references. It is a candidate graph, not a runtime trace.

- 46 Train Ticket service modules indexed.
- 172 source-level candidate service-call edges.
- 26 services have at least one outgoing candidate edge.
- Database/service-discovery dependencies are recorded from configuration where present.

## Test-node use

For a test node targeting `app=ts-order-service`, the slice now has this shape:

```text
TestNode: NetworkChaos delay
  -> selector: app=ts-order-service
  -> target: ts-order-service Pod/Service
  -> source call: ts-order-service -> ts-station-service
  -> function evidence: OrderServiceImpl.java:211
  -> control/data slice: timeout/exception/response/order/repository candidates
  -> runtime trace: pending
```

The edge is based on `getServiceUrl("ts-station-service")` and a `RestTemplate` exchange in the production source. It is a strong static candidate for the NetworkChaos slice, but not proof that the selected user request executes that call.

## Important distinction

- Deployment/Service matching answers: “Can this YAML selector find a target?”
- Source graph answers: “Which downstream services could this target call?”
- Runtime trace must answer: “Which call actually occurred for the chosen business request?”
- Only after all three are joined can the LLM claim a tested code/data/control path.
