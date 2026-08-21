# 人工审核材料：KB-RCA-sock-shop-front-end-podchaos-pod-kill

- 审核对象：`knowledge_drafts/KB-RCA-sock-shop-front-end-podchaos-pod-kill.json`
- 生成时间：2026-08-21（材料整理；证据采集于 2026-08-20 各轮次）
- 当前状态：`weakness_status=confirmed`、`rca_status=bounded`、`knowledge_status=local_reusable`、`human_review=pending`
- 轮次校验：`validation_report.json` 报告 `valid=True`，无 error / warning

## 一、待审结论（卡片主张）

front-end 是单副本、无 PDB 的 Deployment；任何 pod-kill 都会产生完整业务中断窗口
（机制层结论，`mechanism_level=deployment`）。适用条件：

1. 单副本且无 PodDisruptionBudget 的 Deployment；
2. kill 或 cpu 故障族。

## 二、证据链（14 条证据引用，10 支持 / 1 反对 / 1 中性 / 2 不可得）

| 轮次 | 关键证据 | 对结论的作用 |
|---|---|---|
| 静态 | `sock-shop-lab-manifest.yaml` 单副本、无 PDB | 机制前置条件（支持） |
| r1 live | PodChaos 注入确认 + Ready 1→0 + 恢复 | 弱点可复现（支持） |
| r1 live | 注入窗口内业务 HTTP 200 | **反对证据**：与中断结论表面矛盾 |
| r2 消歧 | 19 个同步样本时间轴：注入初期 200 出现时 Service 无 ready endpoint，随后业务失败、旧地址进 notReadyAddresses，约 30 秒后新 Pod Ready 恢复 | 把早期 200 解释为 `observation_window_artifact`（暂态，不计防御） |
| r4 冗余对照 | 临时扩容 2 副本后同样 pod-kill：3 个样本同时证明 HTTP 200 + 存活 Ready UID `50438b9e...` 在 Service endpoints 服务；被杀 UID `e6183197...` | 反事实闭环：冗余存在时业务确实被防御（支持） |

需要向审核人明示的细节：r4 的 15 个样本中，前 3 个为 `defended`（确定性共证），
后 12 个为 `platform_blocked`（本地 port-forward 随被杀 Pod 退出，属观测通道中断，
不是业务证据）；`defended` 判定只依赖前 3 个共证样本。

## 三、证据边界（卡片明确声明）

- 四层验证：availability 与 business_path 已验证；contract 与 recovery 未验证；
- 1 条反对证据（r1 注入窗口 HTTP 200）由 r2 消歧降级为暂态观测，未删除；
- 排除条件：未经 feedback protocol 不得跨项目迁移；不得在无源码证据时升级为
  timeout 机制结论。

## 四、下游消费现状（已实现，受审核影响）

- 该卡已投影为决策引擎快照（`retrieval-replay-r1/rca_snapshot.json`）；
- 其 kind=guard 回归意图（`closed_runtime_boundary_no_reinjection`）使决策引擎对
  匹配的 front-end pod-kill 候选禁止再注入、不加分；同项目重放
  `retrieval-replay-r1/replay_report.json` 通过；
- 正式知识库未写入（`knowledge_base_updated=false`）。

## 五、待审核人决定的事项

1. **批准/驳回 `local_reusable`**：是否同意该卡在 sock-shop 项目内作为闭合边界知识复用；
2. **是否授权跨项目投影**：若同意，下一步经 `feedback_protocol.knowledge_projection()`
   把"单副本无 PDB + kill/cpu"抽象为项目无关规则，投影到下一个目标项目 KB 快照
   （候选：Online Boutique，其亦有多个单副本服务可对照验证）；
3. **驳回时的处置**：卡片降级为 provisional 并记录驳回理由，guard 意图保留或撤销由
   审核人指定。

> 审核决定请记录于本目录 `human_review_decision.json`（字段：decision
> `approved_local_reuse` / `approved_cross_project` / `rejected`、reviewer、date、
> rationale），由后续轮次读取；在此之前一切跨项目迁移保持阻塞。
