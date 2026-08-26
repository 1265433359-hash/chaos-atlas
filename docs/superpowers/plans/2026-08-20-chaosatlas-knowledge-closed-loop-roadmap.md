# ChaosAtlas Knowledge Closed-Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 ChaosAtlas 从项目特定的混沌实验与知识产物，逐步建设为能够接入已部署项目、主动发现故障、收集因果证据、解释防御、晋级知识并自动生成下一轮验证的受控闭环系统。

**Architecture:** 保留现有 TestNode、四层适用性门禁、业务 Oracle、运行时生命周期和知识库验证器。新增部署节点、场景节点、统一证据图和知识状态机；所有 live action 都通过显式环境门禁、隔离 namespace、清理契约和可审计 executor 执行。ChaosEater 只作为部署可用性能力的外部验证 profile，不作为 ChaosAtlas 的专用分支。

**Tech Stack:** Python 3、现有 Chaos Mesh/Kubernetes runner、JSON/JSONL artifact、PyYAML、pytest；第一阶段只要求 Kubernetes，Compose 作为静态接入输入，不同时承诺生产环境自动修改。

---

## 总体阶段

| 阶段 | 目标 | 主要产出 | 完成标准 |
|---|---|---|---|
| 0 | 冻结接入与证据契约 | project profile、Oracle taxonomy、结果状态 | 所有结果能区分 blocked、not reachable、injection unknown、preserved、defended |
| 1 | 部署与 CE 能力原生化 | deployment/scenario node、availability/recovery oracle、dry-run runner | Sock Shop fixture 能生成并校验完整部署场景 |
| 2 | 主动发现故障空间 | manifest-only discovery、统一候选池、覆盖分母 | 不依赖历史 verdict 也能产生可编译候选 |
| 3 | 主动 RCA | 证据采集器、区分性动作、live executor | 一个案例可从症状推进到 bounded/confirmed/rejected，并保留审计链 |
| 4 | 防御解释与知识反哺 | defense evidence、知识晋级、回归意图执行 | `local_reusable` 卡片能改变下一轮候选或诊断计划 |
| 5 | 改进复测 | 结构化 manifest patch、重新部署、同场景复测 | 输出 `improvement_verified` 或明确 `deployment_blocked` |
| 6 | 多项目试点 | CLI/orchestrator、权限和配额、三项目评估 | 三个项目完整跑通，指标和失败边界可比较 |

不要把阶段 5 的自动改进或阶段 6 的多项目扩展提前到阶段 0-3；没有稳定证据和清理能力时，自动动作只会放大误判和环境风险。

## Phase 0: 冻结接入与证据契约

**目标:** 让系统先知道“什么项目可以测、什么结果可以声称、什么结果必须停止”。

**Files:**
- Create: `tools/project_onboarding.py`
- Create: `tools/tests/test_project_onboarding.py`
- Modify: `tools/runtime_applicability_gate.py`
- Modify: `tools/classify_runtime_result.py`
- Modify: `tools/validate_knowledge_base.py`
- Create: `artifacts/project_profiles/sock-shop/project_profile.json`

- [x] 定义 `project_profile.json`：项目 ID、固定 commit、manifest/source roots、namespace policy、入口 Oracle、观测接口、恢复 deadline、cleanup owner、敏感字段策略。
- [x] 定义统一结果枚举：`environment_blocked`、`method_invalid`、`target_not_found`、`business_not_reachable`、`injection_not_confirmed`、`effect_unobserved`、`response_preserved`、`degraded`、`defended`、`weakness`、`recovery_timeout`。
- [x] 为每个结果附加 `claim_scope`、`evidence_refs`、`next_evidence`；禁止用 HTTP 200 或 Ready-only 直接生成 `defended`。
- [x] 用 Sock Shop 冻结输入完成静态 profile 验证；没有真实集群时只能输出 `ready_for_static_analysis`，不能伪造 runtime verdict。
- [x] 运行 focused profile/gate/classifier tests；29 tests + 5 subtests passed。

**Exit gate:** 任何后续模块都只能消费该契约；平台阻断和业务不可达不能进入 weakness 或 defense 统计。

## Phase 1: 部署与 CE 能力原生化

**目标:** 把部署可用性作为与服务调用边同级的 ChaosAtlas 能力，而不是 CE 专用适配器。

**Files:**
- Create: `tools/deployment_capability.py`
- Create: `tools/build_deployment_capability_pool.py`
- Create: `tools/compile_scenario_node.py`
- Create: `tools/availability_oracle.py`
- Create: `tools/run_deployment_scenario.py`
- Create: `tools/tests/test_deployment_capability.py`
- Create: `tools/tests/test_compile_scenario_node.py`
- Create: `tools/tests/test_availability_oracle.py`
- Create: `tools/tests/test_run_deployment_scenario.py`
- Modify: `tools/decision_engine.py`

- [x] 从 manifest 构建 `deployment_node`：Deployment、Service、Pod selector、replicas、probe、PDB、HPA、资源引用和 manifest hash。
- [x] 从 ordered/concurrent phase 构建 `scenario_node`；支持 `pod_kill`、`container_kill`、`stress_cpu`、`stress_memory`、`network_loss`、`network_partition`。
- [x] 编译器只生成 namespace-local canonical YAML 和 provenance，不调用 kubectl；未知 selector、跨 namespace target、未知参数直接 `method_invalid`。
- [x] 实现双 Oracle：CE-compatible `availableReplicas` 指标与 ChaosAtlas native recovery（replacement identity、Ready、业务 probe、cleanup）。
- [x] runner 每个 phase 记录注入确认、resource UID、观察窗口、恢复窗口、清理状态和原始 status stream；并发 phase 必须确认所有 fault 后才进入观察。
- [x] 用 Sock Shop fixture 表达 CE 四阶段，但禁止在源码中检查 `method_id == ChaosEater`。
- [x] 运行离线测试和 dry-run；没有集群时明确标记 `blocked/not_run`（46 项阶段 1/2 组合测试通过；真实集群未运行）。

**Exit gate:** deployment/scenario schema、oracle、compiler、runner 的离线测试全部通过；能生成可审计 dry-run artifact。真实能力仍需独立集群验收。

## Phase 2: 主动发现故障空间

**目标:** 从部署和源码事实生成待验证假设，而不是只从人工挑选或历史 YAML 中复用候选。

**Files:**
- Modify: `tools/run_native_full_discovery.py`
- Modify: `tools/open_discovery_compiler.py`
- Modify: `tools/candidate_registry.py`
- Modify: `tools/decision_engine.py`
- Create: `tools/tests/test_native_deployment_discovery.py`
- Create: `tools/tests/test_candidate_coverage_denominator.py`

- [x] 输入只包含 manifest、静态拓扑、源码/配置摘要、故障目录和通用 vocabulary；禁止输入历史 verdict、runtime observation 或 CE 已选 hypothesis。
- [x] 统一生成 `dependency_edge`、`deployment`、`scenario` 三类候选，并为每类记录 `applicability_plan`、`expected_steady_state`、`recovery_expectation` 和 `validation_plan`。
- [x] 生成独立 `coverage_denominator.json`；候选全集只代表可枚举空间，不代表已经发现问题。
- [x] 保留 seed、snapshot hash、候选预算和 same-input 约束，确保后续可比较不同知识条件。
- [x] 对未解析 selector、缺少业务入口、缺少恢复契约的候选 fail closed。
- [x] 运行阶段 2 focused tests；native 候选与旧 edge 候选共存，知识只改变排序/诊断。

**Exit gate:** 在没有知识视图时仍能生成合法候选；有知识视图时只能改变排序、诊断要求或停止规则，不能直接制造 runtime 结论。

## Phase 3: 主动 RCA 与因果证据

**目标:** 把“报告输出问题”推进为“自动选择下一步证据并更新根因状态”。

**Files:**
- Modify: `tools/rca_loop.py`
- Modify: `tools/rca_runtime_loop.py`
- Create: `tools/evidence_collectors.py`
- Create: `tools/tests/test_evidence_collectors.py`
- Modify: `tools/sock_shop_rca.py`
- Modify: `tools/validate_rca_loop.py`

- [ ] 实现只读证据 collector：manifest/config、源码 span、Kubernetes events、服务日志、Trace/span、业务重放和直接依赖重放。
- [ ] 每条证据记录 source ref、时间窗口、hash、claim scope、polarity、完整性和不可用原因；证据缺失不能默认为支持或反对。
- [ ] 将动作评分固定为信息增益、证据完整度、因果区分度减去成本、风险和环境不确定性；缺少 namespace、precondition、cleanup、stop condition 或 output schema 时不执行。
- [ ] 保留显式 live gate、executor 注入和 dry-run 模式；live executor 不得直接写生产 namespace。
- [ ] 让三类 Sock Shop 案例分别覆盖：部署边界 bounded、竞争假设 bounded、存在直接配置/源码证据时 confirmed；出现反证时进入 rejected 或降级。
- [ ] 运行：`python -m pytest tools/tests/test_rca_loop.py tools/tests/test_rca_runtime_loop.py tools/tests/test_sock_shop_rca.py tools/tests/test_validate_rca_loop.py -q --basetemp .pytest-tmp-rca`。

**Exit gate:** 每个案例都能生成可回链的下一动作；至少一个动作可以由 mock executor 完整执行并反馈状态；真实动作仍需要集群 gate。

## Phase 4: 防御解释与知识反哺

**目标:** 只把有证据的防御和边界知识送回下一轮选择。

**Files:**
- Modify: `tools/classify_runtime_result.py`
- Modify: `tools/compile_rca_regression.py`
- Modify: `tools/feedback_protocol.py`
- Modify: `tools/query_knowledge_base.py`
- Modify: `tools/knowledge_updater.py`
- Create: `tools/tests/test_defense_evidence.py`
- Create: `tools/tests/test_knowledge_feedback_loop.py`

- [ ] 将 response preservation、latency degradation、graceful degradation、redundancy、timeout、retry、fallback、circuit breaker、probe restart escape 分成不同 defense claims。
- [ ] 防御 claim 必须至少包含注入确认、独立业务 Oracle、观察窗口、恢复/清理和匹配的机制证据；单纯 `response_preserved` 只能是边界结论。
- [ ] `provisional` 只能生成 `reproduce/discriminate` intent；只有满足重复/反事实、生命周期、适用条件、证据和停止规则后才能晋级 `local_reusable`。
- [ ] `local_reusable` 卡片实际参与下一轮候选排序或证据计划；`contested` 卡片不得产生可执行 intent。
- [ ] 反例必须保留历史证据、旧 snapshot hash 和降级原因，不能静默覆盖卡片。
- [ ] 用一条 Sock Shop 防御边和一条 Train Ticket latency boundary 作为不同 claim scope 的回归 fixture。
- [ ] 运行：`python -m pytest tools/tests/test_defense_evidence.py tools/tests/test_knowledge_feedback_loop.py tools/tests/test_feedback_protocol.py tools/tests/test_compile_rca_regression.py -q --basetemp .pytest-tmp-feedback`。

**Exit gate:** 同一候选在“无知识”和“有 local_reusable 知识”条件下产生可审计、可解释的不同排序或诊断要求；不能只比较模型文本。

## Phase 5: 改进与复测闭环

**目标:** 验证知识是否能指导有效改进，而不是停留在报告和建议。

**Files:**
- Create: `tools/deployment_improvement.py`
- Create: `tools/tests/test_deployment_improvement.py`
- Modify: `tools/feedback_protocol.py`
- Modify: `tools/run_deployment_scenario.py`

- [ ] 只支持结构化 patch：replicas/PDB/HPA、readiness/liveness probe、resource requests/limits；每个 patch 带 source file、JSON Pointer、old/new value、reason、expected oracle change 和 rollback。
- [ ] patch 只能作用于 fresh namespace 或 immutable source copy，原始 source tree 不可变。
- [ ] patch 前运行 server-side dry-run；环境不可用时输出 `deployment_blocked`，不能输出 verified。
- [ ] 使用完全相同的 scenario、seed、业务 Oracle、观察窗口和恢复规则重新运行。
- [ ] 结果只允许 `improvement_verified`、`regression`、`deployment_blocked`、`not_run`。
- [ ] 把复测结果作为反事实证据回流 RCA 和知识卡；失败改进不能自动降级成“系统已防御”。
- [ ] 运行：`python -m pytest tools/tests/test_deployment_improvement.py -q --basetemp .pytest-tmp-improvement`。

**Exit gate:** 至少一个部署可用性问题完成“patch -> fresh deploy -> same scenario -> same oracle -> evidence review”全链路。

## Phase 6: 多项目试点与产品化边界

**目标:** 在有限项目集合中验证闭环的可重复性、成本和安全性。

**Files:**
- Create: `tools/chaosatlas_cli.py`
- Create: `tools/run_closed_loop.py`
- Create: `tools/capability_coverage_report.py`
- Create: `tools/tests/test_run_closed_loop.py`
- Create: `tools/tests/test_capability_coverage_report.py`
- Modify: `docs/PROJECT_SUMMARY.md`
- Modify: `docs/KNOWLEDGE_BASE.md`

- [ ] 提供四个明确命令：`onboard`、`discover`、`diagnose`、`learn`；每次运行生成 manifest、input hash、approval、budget、artifact index 和 cleanup report。
- [ ] 加入 namespace allow-list、最大故障半径、并发/时长预算、人工审批点、失败熔断和残留资源扫描。
- [ ] 先选择 Train Ticket、Online Boutique、Sock Shop 三个项目；每个项目使用独立 namespace、固定 commit、固定 image digest 和独立 knowledge snapshot。
- [ ] 统计 discovery precision/recall、RCA bounded-to-confirmed 比例、防御解释准确率、知识引入后的候选效率、运行成本、blocked 比例和 cleanup 成功率。
- [ ] 将 native capability coverage 与可选 CE profile validation 分开报告；不以 weakness 数量宣称能力覆盖或方法优越性。
- [ ] 运行完整离线回归、三项目 smoke、审计和敏感信息扫描。

**Exit gate:** 三个项目都能完成至少一条“发现 -> 证据 -> RCA -> 知识 -> 回归”链路；所有未完成项能被机器标记为 blocked/not_run，而不是被解释成成功。

## 不应提前做的事情

- 不先做任意项目自动修复；先做隔离副本中的结构化 patch 和复测。
- 不把 LLM 置信度当作证据真实性、RCA 状态或知识晋级裁决。
- 不把环境 blocked、目标不可达或未确认注入计入防御成功。
- 不把 CE 历史 replay 与 ChaosAtlas native capability 混入同一个统计分母。
- 不在没有统一业务 Oracle、恢复和 cleanup 证据时扩大项目数量。

## 最小可行版本

如果资源有限，先完成 Phase 0-4。此时可以诚实地声称：

> ChaosAtlas 能在一个固定 Kubernetes 项目中，从部署和服务事实生成受控故障候选，执行有边界实验，自动收集有限证据，输出 bounded/confirmed RCA，并将经过门槛的本地知识用于下一轮诊断或候选选择。

只有 Phase 5 完成后，才可以声称知识能够验证部署改进；只有 Phase 6 完成后，才适合声称具备跨项目的受控闭环能力。
