# Hotel Reservation 只读预检报告（intake report）

> 日期：2026-08-10
> 状态：**go_no_go = blocked**（仓库内无 Hotel 源码/manifest，无法确认来源；按协议禁止下载）
> 本阶段禁止启动集群/部署，bring-up 与稳定性闸门一律 `not_run`（不伪造 `passed`）。

---

## 1. 项目来源

- **project / repository**：Hotel Reservation（DeathStarBench / delimitrou 的子项目，见 findings.md:84 推荐）
- **version / commit**：`unknown`（仓库内无实际源码，无法确认版本或 commit）
- **仓库内源码存在性**：**不存在**——全仓库搜索 `*hotel*` 无源码/manifest 目录；仅以下引用：

| 位置 | 内容 | 性质 |
|---|---|---|
| `findings.md:84` | 推荐 DeathStarBench（含 Hotel Reservation） | 文档建议，非项目本体 |
| `artifacts/experiments/comparative_evaluation_protocol.md:109,154` | 计划用 hotel-reservation 作 FastFI 对照；含一个样例 M4 plan JSON（`reserve-hotel` 工作负载） | 计划草案 + 样例 plan，非部署产物 |
| `raw_yaml/NetworkChaos/089f360e346cb3e041d5e690.yaml` | `hotel-booking-f06-db-slow` NetworkChaos 模板（namespace `vibe-coding`） | chaos-mesh 模板，**非 Hotel 部署 manifest** |
| `raw_yaml/TimeChaos/f2042a14bb08d7f908ff01ca.yaml` | `hotel-booking-f13-time-skew` TimeChaos 模板 | 同上 |

> 结论：raw_yaml 两个 `hotel-booking-*` 是 chaos-mesh 注入模板，不是 Hotel 应用的 manifest/源码；它们不能支撑 contract/availability 静态 intake。

## 2. 服务数 / 工作流数 / 可观测入口

- 服务数：`unknown`（无 manifest 可数）
- 工作流数：`unknown`（仅协议草案提过 `reserve-hotel` 一个样例工作负载名，非确认）
- 可观测入口：`unknown`（无部署配置）

## 3. 可用 manifest / 源码 / 镜像路径

| 类型 | 路径 | 状态 |
|---|---|---|
| Hotel 部署 manifest | 无 | `unavailable`（仓库内不存在） |
| Hotel 源码 | 无 | `unavailable` |
| Hotel 镜像引用 | 无 | `unavailable` |
| raw_yaml chaos 模板 | `raw_yaml/NetworkChaos/089f...yaml`、`raw_yaml/TimeChaos/f204...yaml` | 存在但**非部署 manifest**，不可用于 intake |

## 4. 可构造的 contract/availability 事实

- **无**。缺少源码与 manifest，无法从静态证据构造任何 Hotel 特定 contract 或 availability 事实。

## 5. 不能确认的字段和原因

| 字段 | 原因 |
|---|---|
| repository/version/commit | 仓库内无源码，未下载（禁止） |
| 服务数/工作流/观测入口 | 无 manifest |
| contract/availability | 无静态证据源 |
| bring-up 2h / 稳定 30min / 2 baseline | **not_run**（本阶段禁止启动集群） |

## 6. ≥30 中性候选生成条件

- **不满足**：候选生成依赖中性规则 + 静态分层，需要服务图/manifest；当前无 Hotel 拓扑。

## 7. 可覆盖 fault families

- **不可确认**（无服务可注入）；协议设计上目标是 delay/loss/kill 三族，但 Hotel 侧无目标可列。

## 8. 闸门状态

| 闸门 | 值 | 阶段状态 |
|---|---|---|
| bring-up 最长 2h | 协议值 | `not_run` |
| 稳定观测 ≥30min | 协议值 | `not_run` |
| 连续 2 baseline 失败 → blocked | 协议规则 | `not_run` |

> 按提示词要求，本阶段禁止运行集群，闸门必须 `not_run`，不能填 `passed`。

## 9. go_no_go

**`blocked`**

原因（可追溯）：
1. 仓库内无 Hotel Reservation 源码/manifest（全仓库 `*hotel*` 搜索无源码目录）；
2. 仅有的 `hotel-booking-*` raw_yaml 是 chaos-mesh 注入模板，非部署 manifest；
3. 协议禁止下载/部署，无法在当前阶段取得项目本体；
4. 因此 P2（静态知识快照）**不创建**（避免空壳文件），需人工提供 Hotel 仓库路径/批准下载后才可重做 intake。

> 若主代理决定提供 Hotel 仓库路径或批准受限下载，可将 go_no_go 重新评估为 `needs_human_decision` → `ready_for_snapshot`。本报告不自行更改。
