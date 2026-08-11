# Issue draft - Train Ticket - possible disabled station lookup in order refresh

> Status: DRAFT - for review before submission. Not yet posted to GitHub.
> Target: https://github.com/FudanSELab/train-ticket
> Submission channel: normal issue (repository has no `SECURITY.md` / `CONTRIBUTING.md`).
> Expected outcome: low response probability (repo pushed 2025-11-21, 69 open issues with long zero-comment history). Framed as a correctness/benchmark-integrity question for maintainer confirmation.

---

## Title

Train Ticket: /order/refresh may skip the ts-order-service to ts-station-service station-name lookup

## Summary

In both `ts-order-service` and `ts-order-other-service`, the only production-path call to the station name-list endpoint appears to be commented out or absent inside `queryOrdersForRefresh`. As a result, orders are returned with raw station UUIDs (`order.from` / `order.to`) instead of station names, and any fault-injection / dependency-failure experiment targeting the `ts-order-service -> ts-station-service` call edge from the `/order/refresh` workflow does not appear to exercise the real downstream call. Could you confirm whether this is intentional?

The `queryForStationId` method itself is fully implemented and covered by unit tests, but based on the inspected paths it does not appear to be reachable from a production request.

## Environment

- Repository: `FudanSELab/train-ticket`
- Branch: `master`
- Commit inspected: `313886e99befb94be6cd45f085c98e0019f59829` (pinned during analysis)

## Evidence

### 1. `ts-order-service` - call commented out

`ts-order-service/src/main/java/order/service/OrderServiceImpl.java:192-206`:

```java
public Response queryOrdersForRefresh(OrderInfo qi, String accountId, HttpHeaders headers) {
    ArrayList<Order> orders =   queryOrders(qi, accountId, headers).getData();
    ArrayList<String> stationIds = new ArrayList<>();
    for (Order order : orders) {
        stationIds.add(order.getFrom());
        stationIds.add(order.getTo());
    }

    // List<String> names = queryForStationId(stationIds, headers);   // <-- disabled (line 200)
    for (int i = 0; i < orders.size(); i++) {
        orders.get(i).setFrom(stationIds.get(i * 2));        // stationId (UUID) is returned as-is
        orders.get(i).setTo(stationIds.get(i * 2 + 1));
    }
    return new Response<>(1, "Query Orders For Refresh Success", orders);
}
```

The method it would call is present and implemented (`OrderServiceImpl.java:208-220`):

```java
public List<String> queryForStationId(List<String> ids, HttpHeaders headers) {
    HttpEntity requestEntity = new HttpEntity(ids, null);
    String station_service_url = getServiceUrl("ts-station-service");
    ResponseEntity<Response<List<String>>> re = restTemplate.exchange(
            station_service_url + "/api/v1/stationservice/stations/namelist",
            HttpMethod.POST, requestEntity,
            new ParameterizedTypeReference<Response<List<String>>>() {});
    ...
}
```

### 2. `ts-order-other-service` - same pattern

`ts-order-other-service/src/main/java/other/service/OrderOtherServiceImpl.java:209-221`:

```java
public Response queryOrdersForRefresh(QueryInfo qi, String accountId, HttpHeaders headers) {
    ArrayList<Order> orders = queryOrders(qi, accountId, headers).getData();
    ArrayList<String> stationIds = new ArrayList<>();
    for (Order order : orders) { stationIds.add(order.getFrom()); stationIds.add(order.getTo()); }
    for (int i = 0; i < orders.size(); i++) {
        orders.get(i).setFrom(stationIds.get(i * 2));
        orders.get(i).setTo(stationIds.get(i * 2 + 1));
    }
    return new Response<>(1, success, orders);
}
```

The call to `queryForStationId` is absent here too; the method itself is implemented at `OrderOtherServiceImpl.java:223-235`.

### 3. Endpoint wiring

- `OrderController.java:65` - `@PostMapping(path = "/order/refresh")` -> `queryOrdersForRefresh`
- `OrderOtherController.java:71-74` - `/order/refresh` -> `queryOrdersForRefresh`

### 4. Unit tests cover the method, not the production path

- `ts-order-service/src/test/java/order/service/OrderServiceImplTest.java:191` - calls `queryForStationId` directly with a mocked `RestTemplate` (function-level evidence only)
- Same for `ts-order-other-service/src/test/java/other/service/OrderOtherServiceImplTest.java:192`

## Impact

1. **Benchmark integrity / fault-injection reachability.** This benchmark advertises rich service call chains for fault injection. For the `/order/refresh` workflow, the inspected production path does not execute the real `ts-order-service -> ts-station-service` dependency edge. Chaos/NetworkChaos experiments scoped to that edge from this workflow may therefore exercise no downstream call, which could be mistaken for a resilience result.
2. **Response semantics.** `order.from` / `order.to` are returned as raw station UUIDs instead of resolved names - a behavior that may differ from the method name (`Refresh`) and the preserved downstream code.
3. **Maintenance and coverage.** `queryForStationId` is maintained, logged, and unit-tested, but does not appear reachable from production, so the dependency it models (`ts-station-service /stations/namelist`) is not exercised end-to-end by this workflow.

## Reproduction

```bash
git clone https://github.com/FudanSELab/train-ticket.git
git checkout 313886e99befb94be6cd45f085c98e0019f59829
# static: grep -rn "queryForStationId" ts-order-service/src/main/java/order/service/OrderServiceImpl.java
#   -> only the commented line 200 in queryOrdersForRefresh
# runtime (isolated lab): POST /api/v1/orderservice/order/refresh with a login that owns orders
#   -> response orders contain station UUIDs in from/to, and no call to
#      /api/v1/stationservice/stations/namelist is observed from ts-order-service
```

## Possible resolution

If station-name resolution is still intended for this workflow, one possible resolution would be to restore the downstream call and handle the empty/failure case explicitly:

```java
List<String> names = queryForStationId(stationIds, headers);
// fall back to stationIds when names is null/empty/error, and log the fallback
```

Alternatively, if disabling the call is intentional, documenting it in the README/code comment and marking the dependency edge as non-executable would help prevent fault-injection studies from targeting an inactive path.

## Notes

- Reported for research purposes (fault-injection methodology validation). No credentials or secrets are disclosed.
- The repository has no `SECURITY.md`; this is filed as a normal issue.
- Additional context (same finding in the context of the project's own `fault-inject-deployment/` scripts): the injected Istio `VirtualService`/`DestinationRule` targets described for order workflows may not exercise the station dependency while this call remains disabled.
