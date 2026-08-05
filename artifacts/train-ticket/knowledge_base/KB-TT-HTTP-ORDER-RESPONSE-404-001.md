# Knowledge Card: Order HTTP Response Replacement

## Decision

The raw YAML maps to a real listener, controller path, service method, and repository flow. A narrow runtime mutation was generated for one read-only order lookup. The request reached the application, but Chaos Mesh selected the Pod without injecting the HTTP rewrite.

## Runtime result

- Baseline: three requests returned HTTP 200 with `Order Not Found` and a stable application response.
- Mutation: `artifacts/train-ticket/runtime/injections/order-http-code-nonexistent.yaml`.
- Chaos status: `Selected=true`, `injectedCount=0`, `phase=Not Injected/Wait`.
- During the window: all five requests still returned HTTP 200; application logs show the controller and service handler ran.
- Root cause: Chaos Daemon tproxy reported that the Docker Desktop WSL2 kernel lacks the `ebtables` module.
- Classification: platform instrumentation prerequisite missing, not application defense and not a valid response-rewrite result.

## Test-node-centered graph

```text
HTTPChaos replace response 404
  -> app=ts-order-service
  -> listener :12031
  -> OrderController
  -> OrderServiceImpl -> OrderRepository
  -> application response
  -> (blocked) Chaos Mesh response rewrite
```

## New knowledge

`Selected` is not equivalent to `Injected`. HTTPChaos applicability must include a host-kernel/tproxy prerequisite gate. If injection count is zero, classify the run as an instrumentation failure and do not infer defended or not-defended behavior.

Evidence: `artifacts/train-ticket/runtime/http_order_404_result.json` and `artifacts/train-ticket/runtime/baseline_order_service.json`.
