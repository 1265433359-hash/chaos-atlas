# 论文书写主归档（Paper Writing Archive）

> 最后更新：2026-08-09
> 用途：从本项目的全部实验、证据、结论、资产中，为论文写作提供**结构化索引**——每条论文主张都能锚定到证据文件与原始数据，每个资产文件都知道自己在论文里的角色。
> 本文是"导览"，不是"论文"。所有主张的原始证据在引用的文件中。

---

## 一、论文定位与叙事主线（怎么讲这个故事）

### 研究问题
微服务混沌工程中，**如何评估一个系统对故障的防御能力**（而非"能否注入故障"）？

### 核心命题（一句话）
> **防御能力评估是"测量方法 × 证据链"问题，不是"注入强度"或"候选选择算法"问题。**

### 叙事弧线（论文章节骨架，每个节点都有证据）

| 论文环节 | 故事 | 证据文件 |
|---|---|---|
| 动机 | 混沌工程工具（ChaosEater 等）判定"弱点"时看不见调用契约层防御 | `chaos_eater_deployed_vs_ours.md` |
| 方法 | 测试节点中心 + 通用判定模板 + 双证据链 + 知识资产化 | `availability_defense_design.md` |
| 实验1 | 9 方法对比：选择方法无统计差异（B1） | `comparison_full_summary.md` |
| 实验2 | 混合池：protected 边太明显则打平 | `mixed_pool_comparison.md` |
| 实验3 | **真实业务链路 vs 直连：同一注入两种结论（12s vs 5s）** | `sock_orders_future_get_verified.md` |
| 实验4 | **可用性层第二应用：单副本 kill 必瘫（追平 CE + 叠加增量）** | `sock_availability_layer_verified.md` |
| 结论 | 选择方法无差异；测量方法与知识资产产生差异；与 CE 从互补到追平+增量 | `unified_experiments_summary.md` |

### 论文独有贡献（审稿人视角）
1. **测量位置决定防御可见性**：同一故障、同一服务，直连 12s 挂死 vs 真实链路 5s TimeoutException——防御的"存在性"依赖测量位置。
2. **通用判定模板第二应用**：同一框架覆盖契约层 + 可用性层（不是套用 ChaosEater 的 availableReplicas）。
3. **叠加效应**：契约弱 × 可用性弱的复合弱点，单一稳态检查器结构上测不出。
4. **知识资产化确定性收益**：契约清单硬过滤 4/4 命中 0 浪费 vs M0 随机 49% 期望浪费。

---

## 二、方法论文档地图（论文每章 ← 资产文件）

### 方法章节素材
| 论文章 | 素材文件 | 内容要点 |
|---|---|---|
| 方法论核心 | `artifacts/experiments/availability_defense_design.md` | 通用判定模板、双轨设计、叠加效应定义 |
| 证据链纪律 | `artifacts/experiments/methodology_audit.md` | A2 审计：runner timeout ≠ 系统契约 |
| 知识闭环 | `artifacts/experiments/knowledge_closed_loop.md` | 三层提炼、全部可检索 |
| 三阶段测量 | `artifacts/experiments/defense_pattern_methodology.md` | baseline→inject→recover→cleanup |
| 跨项目迁移 | `artifacts/cross_project_summary.md` | 三项目复现"无 timeout"模式 |

### 实验章节素材（核心证据）
| 论文实验 | 素材文件 | 关键数据 |
|---|---|---|
| 选择方法对比 | `experiments/comparison_full_summary.md` | B1 bootstrap CI 全含 0 |
| 混合池 | `online-boutique/mixed_pool_comparison.md` | 5/6 vs 5/6 打平 |
| **真实链路 vs 直连** | `sock-shop/sock_orders_future_get_verified.md` | 2s 吸收/6s 超时/12s 直连盲区 |
| **可用性层** | `sock-shop/sock_availability_layer_verified.md` | front-end 130s、orders 56s 全瘫 |
| **统一结论** | `experiments/unified_experiments_summary.md` | C1-C8 全部结论 |

---

## 三、证据链总索引（结论 → 证据 → 原始数据）

### 契约层证据（orders→payment/shipping 5s 防御）
| 主张 | 静态证据 | 运行时证据 | 原始数据 |
|---|---|---|---|
| Future.get(5s) 存在 | `OrdersController.java:139/160`（源码）+ jar javap（字节码） | 2s 注入 → 201@4.15s；6s 注入 → 500@5.10s TimeoutException | `sock_orders_future_get_verified.md` |

### 可用性层证据（单副本无 PDB）
| 主张 | 静态证据 | 运行时证据 | 原始数据 |
|---|---|---|---|
| 8/8 服务单副本无 PDB | manifest（`contract_inventory.json` availability 段） | front-end kill → 全瘫 130s；orders kill → 全瘫 56s | `avail_frontend_kill.json` / `avail_orders_kill.json` |

### 对比方法证据（三方法）
| 主张 | 证据 | 原始数据 |
|---|---|---|
| decision_engine 4/4 命中 0 浪费 | 冻结预测 + 契约清单硬过滤 | `sock_three_method_predictions.json` |
| M0 随机 49% 期望浪费 | 100 trials 分布 | 同上 |
| CE 结构失明（可用性稳态） | 真实部署观察 | `chaos_eater_deployed_vs_ours.md` |

---

## 四、可引用数据速查表（论文正文/表格用）

### 契约层（Sock Shop orders 链路）
| 指标 | 值 |
|---|---|
| 基线下单 | 201 @ 0.19s |
| payment 2s 注入 | 201 @ 4.15s（吸收，往返 4.0s） |
| payment 6s 注入 | 500 @ 5.10s（TimeoutException） |
| shipping 2s 注入 | 500 @ 5.07s（TimeoutException） |
| 直连 payment 6s 对照 | 200 @ 12.0s（挂死感） |

### 可用性层（Sock Shop）
| 服务 | 静态 | kill 实测 | 恢复 |
|---|---|---|---|
| front-end | replicas=1, 无 PDB | 全瘫 130s | ~131s |
| orders | replicas=1, 无 PDB | 全瘫 56s | ~57s |
| user | replicas=1, 无 PDB | 全瘫 155s | 未捕获（scheduler 抖动） |
| carts | replicas=1, 无 PDB | 全瘫瞬间（无 readiness 门控） | 4s（假恢复） |
| shipping | replicas=1, 无 PDB | 全瘫瞬间（无 readiness 门控） | 3s（假恢复） |
| payment/catalogue/queue-master | replicas=1, 无 PDB | 静态推断同形态（AD-REDUNDANCY-001） | — |

### 三方法对比（Sock 池，预算 4）
| 方法 | protected 浪费 | 弱点命中 |
|---|---|---|
| decision_engine | 0/4 | 4/4 |
| M0 随机（100 trials） | 1.95/4（49%） | 2.05/4 |
| M1 盲选（单次采样） | 0/4（运气） | 4/4（运气） |

### 三方法对比（OB 混合池，预算 6）
| 方法 | 命中 | severity | protected 误选 |
|---|---|---|---|
| decision_engine | 5/6 | 12 | 1 |
| M1 盲选 | 5/6 | 12 | 1 |
| M0 随机 | 3.72 | ~8 | 2.28 |

### ChaosEater 对照
| 项 | 值 |
|---|---|
| CE 真实部署判定 | front-end 单副本 91.11%<99% → 弱点 |
| CE 契约层能力 | 稳态=availableReplicas，不测 HTTP 语义 |
| 同数据喂 CE analysis | 6/14 漏判（延迟放大但返回 OK 的 case） |

---

## 五、术语表（论文定义）

| 术语 | 定义 | 出处 |
|---|---|---|
| 测试节点中心 | 不建全项目图，从业务语义选注入点 | `report_for_supervisor.md` §2.1 |
| 证据链 | 静态（源码/配置/manifest）+ 运行时（注入实测）双证据，缺一不判定 | `methodology_audit.md` |
| 契约层 | 服务间调用契约（超时/重试/熔断）防御维度 | `contract_inventory.py` docstring |
| 可用性层 | 部署可用性（replicas/PDB/探针/自愈）防御维度 | `availability_defense_design.md` |
| 通用判定模板 | 选节点→注入→测防御响应→证据链判定（两层共用） | `availability_defense_design.md` |
| explicit_timeout | 源码/配置声明的超时契约（系统承诺，非测试参数） | `contract_inventory.py` |
| loss_bounded | Future.get 类异步防御对 LOSS 也有界（非无限挂起） | `contract_inventory.py` |
| AD-REDUNDANCY-001 | 单副本无 PDB → kill 必瘫（静态先验已知） | `decision_engine.py` |
| 叠加效应 | 契约弱 × 可用性弱 = 复合弱点（单层方法测不出） | `availability_defense_design.md` |
| floor effect | 全弱/全强系统上方法无差异 | `unified_experiments_summary.md` |
| 信息不对称 | 池子含"关键路径×隐蔽防御×直连盲区"候选时的可区分度 | `unified_experiments_summary.md` |

---

## 六、诚实边界与 limitation（审稿人会问，提前备好答案）

| 边界 | 影响 | 应对/答复 |
|---|---|---|
| B1 统计功效不足（20 池单轮） | "选择方法更优"无背书 | 论文只主张"选择方法无差异"，不主张"我们选得更准" |
| M1 盲选单次 4/4 | 不能证明 M1 差 | 论文用 OB 池 M1 误选 protected 作对照，强调"确定性 vs 运气" |
| Sock LOSS 判定为推断 | orders LOSS 未单独重跑 | 基于共享 Future.get + delay 实测推断，代码逻辑确定（connection-refused 路径） |
| 可用性层追平非超越 | 不能说"可用性测得更准" | 主张"统一框架覆盖两层 + 叠加效应"，非单层超越 |
| CE 对 Future.get 边行为为推断 | 未让 CE 实测该边 | 基于其稳态定义（availableReplicas）逻辑推导，报告已标注 |
| 恢复时长含环境因素 | 130s/56s 绝对值不通用 | 相对结论（单副本 kill 必瘫）成立；绝对值仅作展示 |
| 未测多副本正例 | AD-REDUNDANCY 只有单侧证据 | 集群无 replicas>1 服务，留作 future work |
| 外部真值缺失 | 2 份 issue 未提交 | `reporting/issue_template.md` 已备好模板，提交后闭环 |
| 评价标准自证循环 | CE 对照用我们定义的 severity | 只主张"产出形态适配"，不主张"更优" |

---

## 七、可复用工具链索引（代码论文用途，注释说明）

### 工具模块 → 论文角色
| 工具 | 角色 | 论文用途 |
|---|---|---|
| `tools/contract_inventory.py` | 契约清单（边级 contract + 服务级 availability） | 方法核心资产，论文方法章 |
| `tools/decision_engine.py` | 无 LLM 判定引擎（双硬过滤） | 知识资产化主张的可复现代码 |
| `tools/sock_three_method_select.py` | 三方法冻结对比 | 实验章对比数据生成器 |
| `tools/mixed_pool_prospective_select.py` | OB 混合池对比 | 实验章（打平案例） |
| `tools/sock_avail_sample.sh` | 可用性采样器（500ms Ready 曲线） | 可用性层实验工具 |
| `tools/chaos_eater_analysis_adapter.py` | CE analysis 适配 | CE 对照实验 |
| `tools/knowledge_updater.py` | 知识库闭环 | 知识资产化 |
| `tools/project_registry.py` | 服务归一化（单点加项目） | 方法可迁移性 |

### 复现所需环境（论文附录）
- WSL2 自定义内核（ebtables broute/nat）解锁 HTTPChaos——`tools/wsl_chaos_env_up.sh`
- kind + Chaos Mesh 2.8.3 + 独立集群（chaos-eater-cluster）
- mongo 4.0 降级（旧驱动 OP_QUERY 兼容）、探针放宽（防误杀污染实验）
- 详细环境指纹：`artifacts/experiments/environment_fingerprint.json`

---

## 八、论文写作 checklist（从本归档出发）

- [ ] 方法章：通用判定模板 + 双轨设计（§1、§2 素材）
- [ ] 实验章-契约层：真实链路 vs 直连（§4 数据表）
- [ ] 实验章-可用性层：单副本 kill 实证（§4 数据表）
- [ ] 对比章：三方法冻结预测 + M0 分布（§4 数据表）
- [ ] 与 CE 对比：真实部署 + 结构失明分析（§3、`chaos_eater_deployed_vs_ours.md`）
- [ ] limitation 节：§6 表格直接改写
- [ ] 复现附录：§7 工具链 + 环境
- [ ] 外部真值：提交 2 份 issue（`reporting/issue_template.md`）→ 补 strong evidence

---

## 附：完整资产文件索引（论文引用备查）

### 顶层报告
- `artifacts/report_for_supervisor.md` — 导师汇报（含方法论全貌）
- `artifacts/cross_project_summary.md` — 三项目跨项目对照

### 对比实验
- `artifacts/experiments/comparison_full_summary.md` — 9 方法全历程总结
- `artifacts/experiments/comparison_experiment_summary.md` — 早期对比总结
- `artifacts/experiments/m1_vs_m5select_comparison.md` — 知识层加持对照
- `artifacts/experiments/prospective_round1_result.md` — 前瞻 r1
- `artifacts/experiments/method_comparison_verdict.md` — 方法对比裁定
- `artifacts/experiments/p4_closed_loop_validation.md` — 闭环验证

### 本轮核心（2026-08-09）
- `artifacts/experiments/unified_experiments_summary.md` — 统一结论（C1-C8）+ 经验缺口审计（§3.5）
- `artifacts/experiments/availability_defense_design.md` — 可用性层设计
- `artifacts/sock-shop/sock_orders_future_get_verified.md` — 契约层实证
- `artifacts/sock-shop/sock_availability_layer_verified.md` — 可用性层实证（4 服务 kill + gate-lack 发现）
- `artifacts/sock-shop/sock_shop_verdicts.json` — 判定数据 v3（可用性 5 服务实测）
- `artifacts/sock-shop/sock_dual_track_pool.json` — 双轨统一池（16/16 对齐，引擎级端到端）
- `artifacts/experiments/chaos_eater_deployed_vs_ours.md` — CE 真实部署对比
- `tools/sock_dual_track_pool.py` — 双轨统一池生成器（论文实验章可复现）
- `tools/backfill_experience_gaps.py` — 知识库缺口回填（审计→补全可复现）
- `tools/sock_frozen_knowledge_rerun.py` + `sock_frozen_knowledge_predictions.json` — **重验证1**：仅凭预实验静态字节码预测 8 边 → 8/8 对齐（堵自证循环）
- `tools/sock_blind_availability_predict.py` + `sock_blind_availability_predictions.json` — **重验证3**：不看 CE 报告、仅凭 manifest 预测可用性 → 5/5 runtime 对齐（堵确认偏误）
- `tools/sock_combined_inject.sh` + `sock_combined_frontend_carts.json` — **重验证4**：delay+kill 并发注入 → front-end 全瘫 124s（C8 并发可行性实证）

### 知识库（JSON 资产）
- `contract_inventory.json` / `defense_pattern_library.json` / `judgment_experience.json` / `selection_experience.json` / `knowledge_audit_log.json` / `our_evidence_chain_root_causes.json` / `environment_fingerprint.json` / `issue_tracker.json`

### 论文素材
- `artifacts/papers/ChaosEater_arXiv2501.11107v2.txt` — 对照方法原文
- `artifacts/papers/chaos_testing_comparison_and_reproduction_plan.md` — 复现计划
