# Train Ticket 54 样本验证状态矩阵（第一轮收尾）

> 生成时间：2026-08-05；数据源：`train_ticket_test_slices_graph.json` + `runtime/classification_index.json`（19 条运行时记录）

## 总览

| 验证状态 | 数量 | 说明 |
|---|---|---|
| verified | 5 | 有真实注入+观测证据（分类索引匹配） |
| platform_blocked | 30 | HTTPChaos：WSL2 ebtables 前置缺失，平台阻断（非防御结论） |
| not_reachable | 1 | Order->Station 生产调用被注释，静态不可达 |
| static_only | 1 | Workflow 高爆炸半径（mode:all 叶子），仅静态展开，不注入 |
| not_run | 17 | 有静态映射但第一轮未做运行时注入 |

## 逐样本明细

| test_id | kind | app | test_nodes | 验证状态 |
|---|---|---|---|---|
| basic-http-code | HTTPChaos | ts-basic-service | http_replace_response|selector | platform_blocked |
| basic-http-outbound | HTTPChaos | ts-basic-service | http_delay|selector | platform_blocked |
| config-http-code | HTTPChaos | ts-config-service | http_replace_response|selector | platform_blocked |
| config-http-outbound | HTTPChaos | ts-config-service | http_delay|selector | platform_blocked |
| consign-http-code | HTTPChaos | ts-consign-service | http_replace_response|selector | platform_blocked |
| consign-http-outbound | HTTPChaos | ts-consign-service | http_delay|selector | platform_blocked |
| order-http-code | HTTPChaos | ts-order-service | http_replace_response|selector | platform_blocked |
| order-http-outbound | HTTPChaos | ts-order-service | http_delay|selector | platform_blocked |
| order-other-http-code | HTTPChaos | ts-order-other-service | http_replace_response|selector | platform_blocked |
| order-other-http-outbound | HTTPChaos | ts-order-other-service | http_delay|selector | platform_blocked |
| price-http-code | HTTPChaos | ts-price-service | http_replace_response|selector | platform_blocked |
| price-http-outbound | HTTPChaos | ts-price-service | http_delay|selector | platform_blocked |
| rebook-http-code | HTTPChaos | ts-rebook-service | http_replace_response|selector | platform_blocked |
| rebook-http-outbound | HTTPChaos | ts-rebook-service | http_delay|selector | platform_blocked |
| route-http-code | HTTPChaos | ts-route-service | http_replace_response|selector | platform_blocked |
| route-http-outbound | HTTPChaos | ts-route-service | http_delay|selector | platform_blocked |
| seat-http-code | HTTPChaos | ts-seat-service | http_replace_response|selector | platform_blocked |
| seat-http-outbound | HTTPChaos | ts-seat-service | http_delay|selector | platform_blocked |
| station-http-code | HTTPChaos | ts-station-service | http_replace_response|selector | platform_blocked |
| station-http-outbound | HTTPChaos | ts-station-service | http_delay|selector | platform_blocked |
| ticketinfo-http-code | HTTPChaos | ts-ticketinfo-service | http_replace_response|selector | platform_blocked |
| ticketinfo-http-outbound | HTTPChaos | ts-ticketinfo-service | http_delay|selector | platform_blocked |
| train-http-code | HTTPChaos | ts-train-service | http_replace_response|selector | platform_blocked |
| train-http-outbound | HTTPChaos | ts-train-service | http_delay|selector | platform_blocked |
| travel-http-code | HTTPChaos | ts-travel-service | http_replace_response|selector | platform_blocked |
| travel-http-outbound | HTTPChaos | ts-travel-service | http_delay|selector | platform_blocked |
| travel-plan-http-code | HTTPChaos | ts-travel-plan-service | http_replace_response|selector | platform_blocked |
| travel-plan-http-outbound | HTTPChaos | ts-travel-plan-service | http_abort|selector | platform_blocked |
| user-http-code | HTTPChaos | ts-user-service | http_replace_response|selector | platform_blocked |
| user-http-outbound | HTTPChaos | ts-user-service | http_delay|selector | platform_blocked |
| basic-network-delay | NetworkChaos | ts-basic-service | network_delay|selector | verified |
| config-network-delay | NetworkChaos | ts-config-service | network_delay|selector | not_run |
| consign-network-delay | NetworkChaos | ts-consign-service | network_delay|selector | not_run |
| order-network-delay | NetworkChaos | ts-order-service | network_delay|selector | not_reachable |
| order-other-network-delay | NetworkChaos | ts-order-other-service | network_delay|selector | not_run |
| price-network-delay | NetworkChaos | ts-price-service | network_delay|selector | not_run |
| rebook-network-delay | NetworkChaos | ts-rebook-service | network_delay|selector | not_run |
| route-network-delay | NetworkChaos | ts-route-service | network_delay|selector | not_run |
| seat-network-delay | NetworkChaos | ts-seat-service | network_delay|selector | not_run |
| station-network-delay | NetworkChaos | ts-station-service | network_delay|selector | verified |
| ticketinfo-network-delay | NetworkChaos | ts-ticketinfo-service | network_delay|selector | not_run |
| train-network-delay | NetworkChaos | ts-train-service | network_delay|selector | not_run |
| travel-network-delay | NetworkChaos | ts-travel-service | network_delay|selector | not_run |
| travel-plan-network-delay | NetworkChaos | ts-travel-plan-service | network_delay|selector | not_run |
| user-network-delay | NetworkChaos | ts-user-service | network_delay|selector | not_run |
| basic-stress-cpu | StressChaos | ts-basic-service | selector|stress_cpu | verified |
| order-stress-cpu | StressChaos | ts-order-service | selector|stress_cpu | verified |
| route-stress-cpu | StressChaos | ts-route-service | selector|stress_cpu | not_run |
| station-stress-cpu | StressChaos | ts-station-service | selector|stress_cpu | verified |
| ticketinfo-stress-cpu | StressChaos | ts-ticketinfo-service | selector|stress_cpu | not_run |
| travel-plan-stress-cpu | StressChaos | ts-travel-plan-service | selector|stress_cpu | not_run |
| travel-stress-cpu | StressChaos | ts-travel-service | selector|stress_cpu | not_run |
| user-stress-cpu | StressChaos | ts-user-service | selector|stress_cpu | not_run |
| tt-chaos | Workflow | - | workflow_schedule|workflow_serial | static_only |

## 第一轮结论

- 已验证 5 条实验线：Station 延迟（100ms/500ms/2s/3s 边界）、Basic/Order/Station CPU、Basic->Station 网络。
- 30 个 HTTPChaos 全部平台阻断，不是防御结果。
- 17 个未运行样本（12 network_delay + 5 stress_cpu）是跨服务扩展空间：方法已验证，只需对每个目标服务重复相同的注入-观测-恢复流程。
- Order 的 network_delay 不可达是真实项目缺陷（见薄弱点报告）。
- 新服务目标都需要先过 `runtime_applicability_gate.py` 的命名空间/模式/前置检查。
