# P0 回归集定义（Train Ticket 第一轮收尾）

> 目的：当被测项目 commit、Chaos Mesh 版本、部署清单或工具链发生变化时，用最小实验集重放，验证知识库结论是否仍然成立（阶段 10 回归治理的入口）。
> 依据：`paper_prep_stage_summary.md` 阶段 A 验收标准与运行时分类索引。

## 回归原则

- 每个 P0 实验必须使用隔离 namespace `train-ticket-lab`、单目标（`mode: one`）、固定 commit。
- 每个实验必须产出：runner report（含 preflight 决策、注入/恢复/清理证据）+ 分类结果。
- 通过条件：响应契约保持 + 分类标签与基线一致（允许延迟量级变化，不允许分类语义翻转）。
- 禁止项：`mode: all`、跨 namespace selector、未过 `runtime_applicability_gate` 的注入。

## P0 实验清单

| ID | 测试节点 | 目标 | 变异（mutation 文件） | 请求 | 观测 | 基线期望（首轮实测） | 分类期望 | 触发条件 |
|---|---|---|---|---|---|---|---|---|
| P0-01 | Station NetworkChaos delay 100ms | ts-station-service | `generated_mutations/network-station/station-network-delay-candidate-r1.yaml` | GET `/api/v1/stationservice/stations/id/shanghai`（10 请求，3 warm-up，5s 超时） | 延迟、cgroup、注入/恢复/清理 | 中位 ≈216ms（基线 30.1ms，+186ms） | `response_observed` / `response_preserved_latency_degradation` | 项目 commit 或 Chaos Mesh 版本变化 |
| P0-02 | Station NetworkChaos delay 500ms | ts-station-service | 由 r1 改 500ms（`latency: 500ms`） | 同上 | 同上 | 中位 ≈1021ms | `response_preserved_latency_degradation` | 同上 |
| P0-03 | Station NetworkChaos 3s 边界 | ts-station-service | `network-station` 系 3s 变体 | 1 请求 + 明确 5s 观测预算 | 客户端超时、服务端日志时间线 | 客户端 5047ms 超时；服务端 6064ms 完成 | `client_timeout_observed` | 同上（回归重点是"超时边界仍成立"，不是重复加压） |
| P0-04 | Basic StressChaos CPU r1 | ts-basic-service | `generated_mutations/stress-basic/basic-stress-cpu-candidate-r1.yaml` | GET `/api/v1/basicservice/basic/shanghai` | cgroup、延迟、恢复 | 中位 ≈27-33ms；`nr_throttled +400` 量级 | `response_observed` | 同上 |
| P0-05 | Order StressChaos CPU | ts-order-service | `generated_mutations/stress/order-stress-cpu-*` | GET 只读订单（Order Not Found） | cgroup、延迟、恢复 | HTTP 200 + 契约保持 | `response_observed` | 同上 |
| P0-06 | HTTPChaos 平台阻断 | ts-order-service | 任一 HTTPChaos 变异 | 不注入（gate 层验证） | gate 决策 | `blocked`（ebtables） | `platform_or_preflight_blocked` | 平台升级或 ebtables 就绪后改为注入验证 |
| P0-07 | Order->Station 可达性 | ts-order-service | 无（静态） | 无 | 源码 grep + 可选运行 trace | `queryForStationId` 生产调用被注释 | `not_reachable`（保留反例） | 项目源码变化（如恢复该调用） |

## 回归执行命令（示例）

```bash
# P0-01 重复一次
python tools/run_chaos_experiment.py \
  artifacts/train-ticket/runtime/generated_mutations/network-station/station-network-delay-candidate-r1.yaml \
  --report artifacts/train-ticket/runtime/regression_P0-01.json \
  --service ts-station-service --remote-port 12345 --local-port 18096 \
  --request-path /api/v1/stationservice/stations/id/shanghai \
  --request-count 10 --warmup-count 3 --request-interval 0.5

# 分类
python tools/classify_runtime_result.py \
  --run artifacts/train-ticket/runtime/regression_P0-01.json \
  --baseline artifacts/train-ticket/runtime/baseline_station_success.json \
  --output artifacts/train-ticket/runtime/regression_P0-01_classification.json
```

## 变更检测规则

- 若 P0-01/02/04 的分类翻转（如 `response_observed` -> `client_timeout_observed` 且无环境变化），视为"回归失败"，记录到 `progress.md` 并重新评估知识卡。
- 若 P0-03 边界不再成立（客户端不超时），说明项目/环境引入了防御或超时配置——更新对应知识卡。
- 若 P0-06 从 `blocked` 变为可注入（ebtables 就绪），执行一次只读 HTTP 变异并新建知识卡。

## 状态

- 定义时间：2026-08-05（第一轮收尾）
- 当前基线：commit `313886e99befb94be6cd45f085c98e0019f59829`；Chaos Mesh 2.8.3；Docker Desktop WSL2
- 首次回归执行：待项目/工具版本变化时触发，或用户明确要求时执行
