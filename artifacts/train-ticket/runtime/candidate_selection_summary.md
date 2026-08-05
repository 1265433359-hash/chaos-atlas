# Train Ticket Candidate Selection

The selector is test-node-centered. It ranks a raw YAML candidate only after joining its selector, Deployment/Service match, static function candidates, knowledge cards, and runtime classification records.

## Current top decisions

| Test node | Target app | Decision | Reason |
|---|---|---|---|
| `network_delay` | `ts-basic-service` | `ready_candidate_with_runner` | Real Basic-to-Station path, bounded delay evidence, timeout boundary card |
| `stress_cpu` | `ts-basic-service` | `ready_candidate_with_runner` | Real Basic-to-Station call, cgroup throttling, downstream logs, success/not-found oracles and recovery evidence |
| `stress_cpu` | `ts-station-service` | `ready_candidate_with_runner` | Direct seeded Station success oracle, cgroup throttling, recovery evidence; fresh log capture pending |
| `network_delay` | `ts-station-service` | `closed_runtime_boundary_no_reinjection` | 100ms/500ms/2s ladder plus 3s client-timeout/server-completion boundary; retain for retrieval, do not reinject |
| `stress_cpu` | `ts-order-service` | `ready_candidate_with_runner` | CPU injection, cgroup evidence, functional request and recovery evidence |
| `http_replace_response` | `ts-order-service` | `blocked_by_platform_prerequisite` | HTTP tproxy/ebtables is missing; do not interpret the selected Pod as an application result |
| new Network/Stress targets | other `ts-*-service` apps | `needs_runtime_gate` | Static target and code candidates exist, but no service-specific runtime evidence yet |

## Safety contract

The selector only proposes a candidate. Every generated mutation must be rewritten to `train-ticket-lab`, use a single target and bounded duration, pass `runtime_applicability_gate.py`, and execute through `run_chaos_experiment.py`. A defense conclusion requires confirmed injection, request-path evidence, outcome observation, recovery, and a baseline comparison.

Generated JSON reports:

- `network_candidate_selection.json`
- `stress_candidate_selection.json`
- `http_order_candidate_selection.json`
