# 结论证据矩阵（Claim Evidence Matrix）

> 日期：2026-08-09
> 状态枚举：`confirmed` / `pilot` / `supplementary` / `blocked` / `self_referential` / `future_work`
> 原则：每条结论必须可锚定到证据文件；没有独立真值的声明不标 confirmed。

## 必须单独列出的结论

### 1. 选择器未被统计证明总体优越
| Claim | Evidence | Scope | Status | Limitation |
|---|---|---|---|---|
| 在候选选择上没有任何方法被统计证明更优 | comparison_full_summary.md（B1: bootstrap CI 全含 0）；r2_head_to_head.md（U@8 6 vs 6 vs 5，样本 8，无显著）；OB 混合池（5/6 vs 5/6，88%<95%） | TT/OB/OTEL 选择实验 + OB r2 | **confirmed** | 统计功效低（20 池单轮、8 候选单轮）；结论只覆盖"选择"轴，不涉及测量/证据轴 |

### 2. 真实业务链路能看到 direct 测量看不到的代码级防御
| Claim | Evidence | Scope | Status | Limitation |
|---|---|---|---|---|
| 同一注入（Sock payment 6s delay）：direct 12s 挂死 vs real-chain 5s TimeoutException | sock_orders_future_get_verified.md（orders->payment/shipping 5s Future.get；jar javap + 运行时 TimeoutException 双证据） | SOCK 订单链路 | **confirmed** | 单一项目单一边（orders）；LOSS 两边判定为共享 Future.get 推断 + delay 实测，未单独重跑 loss |

### 3. Ours 的证据链 / RCA / 知识资产化增量
| Claim | Evidence | Scope | Status | Limitation |
|---|---|---|---|---|
| 完整流水线产出可验证、可锚定、可复用资产（83 历史注入、15 源码锚定根因、2 份可提交 bug 报告、契约清单 11 边、B3 判定一致率 0.933） | comparison_full_summary.md（被证明的产出）；contract_inventory.json；knowledge_audit_log.json | 四项目 | **confirmed** | "产出"证实；"优于其他方法"未证实 |
| 决策引擎（契约清单）在含 protected 边的池确定性跳过（OB 混合池 5/6 命中、SOCK 4/4 0 浪费 vs M0 49% 期望浪费） | mixed_pool_comparison.md；sock_three_method_predictions.json | OB/SOCK 混合池 | **confirmed** | 冻结声明经审计修正：decision_engine 知识含后验回填，非执行前冻结（见 freeze_snapshot.json note） |

### 4. ChaosEater 官方部署可用性发现
| Claim | Evidence | Scope | Status | Limitation |
|---|---|---|---|---|
| CE 官方完整 cycle 在 Sock Shop 发现 front-end 单副本可用性弱点（91.11%<99%，建议 replicas 3） | chaos_eater_deployed_vs_ours.md | SOCK（CE 官方部署，commit 47c4e44，单次运行） | **supplementary** | 单次运行；改善未闭环（skaffold 重部署失败）；部署可用性层我们未覆盖 |

### 5. CE AnalysisAgent 自证循环限制
| Claim | Evidence | Scope | Status | Limitation |
|---|---|---|---|---|
| CE AnalysisAgent 喂我们 14 候选真实数据：6/14 判"实验通过"漏判、0/14 结构化根因——但评价标准我们定义、数据我们提供 | comparison_full_summary.md（CE analysis 对照）；chaos_eater_vs_evidence_chain.md | TT/OB/OTEL | **self_referential** | 只能主张"产出形态适配我们下游"，不能主张 superiority |

### 6. r2 不是完整四项目 head-to-head
| Claim | Evidence | Scope | Status | Limitation |
|---|---|---|---|---|
| r2 实际只在 OB 执行（8 候选 24 次尝试，8/8 confirmed weakness）；OTEL 4 + TT 1 候选 environment_blocked | r2_head_to_head.md；candidate_pool_registry.json（10 env_blocked）；run_ledger_master.json（r2 24 条） | OB only | **confirmed（作为事实）；作为完整 head-to-head 则 blocked** | 不是跨项目验证；跨项目优于 CE 需 held-out 项目 |
| r2 U@8 = 6 vs 6 vs 5 不构成方法差异 | r2_head_to_head.md（结论强度定位节） | OB only, 8 候选 | **blocked（作为 superiority 证据）** | 未执行正式显著性检验；样本 8 功效不足；候选池全 weakness 存在 ceiling/saturation effect；推荐措辞"当前样本未显示明确差异，统计功效不足"，不得写三方法全面优越/超过 CE/跨项目有效 |

## 其他重要结论

| Claim | Evidence | Scope | Status | Limitation |
|---|---|---|---|---|
| 可用性层：单副本无 PDB kill 必瘫（front-end 130s / orders 56s / user 155s / carts+shipping 全瘫瞬间） | sock_availability_layer_verified.md；avail_*_kill.json | SOCK | **confirmed** | 恢复时长含环境抖动；未测多副本正例 |
| 可用性层与 CE 判定一致（front-end 单副本） | 同上 + chaos_eater_deployed_vs_ours.md | SOCK | **supplementary** | 我们的实验在 CE 结论之后设计（确认偏误已标注）；测量不对称（k6 流量 vs 无流量 Ready） |
| 盲法静态预测可用性 5/5 runtime 对齐（不看 CE 报告） | sock_blind_availability_predictions.json | SOCK | **confirmed** | 3 服务（payment/catalogue/queue-master）仅静态推断 |
| 冻结知识重放 8/8 对齐（仅凭预实验静态字节码） | sock_frozen_knowledge_predictions.json | SOCK | **confirmed** | 证明"知识资产化"而非"事后偷看"；仍是同项目 |
| C8 叠加效应（契约弱 × 可用性弱） | sock_combined_frontend_carts.json（并发注入可行，front-end 全瘫 124s） | SOCK | **pilot** | 定量延迟放大被负载污染未报告；叠加为三证据合成，非独立交互实验 |
| M1 扩展探索 5/5 验证为真实弱点 | comparison_full_summary.md（prospective r1） | TT/OB/OTEL | **confirmed** | 样本 5，执行后已知（探索成本未入对比模型） |
| M1 vs M5-select（加评分反损探索） | m1_vs_m5select_comparison.md | TT/OB/OTEL | **pilot** | 单池单轮 |
| 测试隔离修复后 artifacts 不被污染 | remediation_validation.json（hash 全 unchanged） | 工具层 | **confirmed** | 工具行为，非实验结论 |
| 统一台账口径（83 历史 + 24 r2 分开计数） | run_ledger_master.json | 全项目 | **confirmed** | 派生 67 文件不计入独立注入 |
