# Train Ticket Test-Node-Centered Slice Report

## Status

This is a static source/manifests report. It does not claim runtime reachability, live traffic impact, or defense behavior.

## Coverage

- 54 Train Ticket YAML samples refined.
- 14 service modules indexed.
- 1,479 production/test function candidates collected across the selected service modules.
- 910 static function-call edges retained inside the module slices.
- 4 Workflow leaf nodes expanded from `tt-chaos`.

## Test-family slices

| Family | Samples | Slice focus |
|---|---:|---|
| HTTP | 30 | controllers, HTTP clients, exception/response handling, timeout/retry/fallback signals |
| Network | 15 | network-facing clients, exception paths, timeout/retry/circuit signals, downstream data |
| Stress | 8 | service entrypoints, database/message dependencies, timeout and transaction signals |
| Workflow | 1 | template control graph and leaf Chaos targets |

## Example: `order-network-delay`

```text
NetworkChaos delay (5s, to, app=ts-order-service)
  -> selector -> ts-order-service Deployment/Service
  -> production source candidates in ts-order-service
  -> static calls (21 retained edges)
  -> control signals: branch, try, exception, HTTP client
  -> data signals: order, ticket, price, seat, repository, response, status
  -> runtime trace and recovery: pending
```

The function list is a candidate slice, not a claim that every listed method executes for this fault. Runtime traces are required to prune it.

## Workflow: `tt-chaos`

Expanded leaves:

| Template | Type | Mode | Unique target app candidates | Risk |
|---|---|---:|---:|---|
| `network-chaos` | NetworkChaos bandwidth | all | 65 | high blast radius |
| `pod-chaos` | PodChaos pod-kill | one | 65 | wide candidate pool |
| `cpu-chaos` | StressChaos CPU | one | 65 | wide candidate pool |
| `memory-stress` | StressChaos memory | one | 65 | wide candidate pool |

The 65 count is a deduplicated static app-label candidate count across repository deployment variants, not a live Pod count.

## Next evidence required

1. Render the exact Helm/Kubernetes variant selected for the experiment.
2. Capture a no-chaos baseline request and trace for one service path.
3. Join source candidates to runtime trace spans and actual call edges.
4. Select one bounded HTTP or Network test before considering the Workflow.
