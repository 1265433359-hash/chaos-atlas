# ChaosAtlas 统一离线闭环编排器设计

## 状态

本设计用于把现有项目接入、服务器部署检测、经验检索、RCA 和知识回归能力
收束为一条可审计的离线命令。第一版不启动 Kubernetes 实验、不调用外部模型、
不修改项目部署，也不把 CE 作为 ChaosAtlas 能力层的名称或必需依赖。

## 1. 目标

输入一个项目 profile 和项目静态/离线事实，运行：

```text
onboard
  -> inventory
  -> server deployment detection
  -> TestNode/candidate mapping
  -> experience retrieval
  -> LLM advisory hypotheses
  -> deterministic applicability gate
  -> baseline plan
  -> fake execution
  -> evidence classification
  -> RCA
  -> knowledge draft
  -> regression intent
```

第一版的价值是验证整个数据和状态链路已经闭合，而不是伪造真实运行时结论。

## 2. 术语边界

### 2.1 服务器部署检测能力

这是 ChaosAtlas 的方法层能力，负责从已部署项目或部署清单中检测和建模：

- Deployment、Service、Pod、selector、副本和端口；
- 探针、PDB、HPA、资源和隔离边界；
- 服务依赖、业务入口和可观测性出口；
- 可用性、恢复、清理和业务 Oracle 条件；
- 可测试的部署故障空间和适用性限制。

该能力不绑定某一个混沌平台，也不等同于 CE API 调用。

### 2.2 CE

CE 是可选的执行后端或外部能力参照。后续可以通过 CE adapter 调用 CE 服务，
也可以通过 native adapter 直接调用 Kubernetes/Chaos Mesh。两者都必须转换为
ChaosAtlas 统一的执行生命周期和证据契约。

### 2.3 经验卡

经验卡不是项目结论。它只用于在项目事实已经采集并映射之后：

- 排序候选；
- 提示 LLM 生成弱点和根因假设；
- 规划区分性证据动作；
- 生成下一轮回归意图。

最终弱点、防御和 RCA 结论必须由确定性规则和运行证据决定。

## 3. 正确数据流

```text
project profile + project facts
  -> project inventory
  -> server deployment detection capability
  -> project-to-TestNode mapping
  -> candidate space
  -> retrieve relevant experience cards
  -> LLM hypotheses (advisory only)
  -> applicability gate
  -> baseline and expected invariants
  -> fake executor
  -> evidence and deterministic classification
  -> RCA state transition
  -> provisional knowledge draft
  -> regression intent
```

候选全集必须先由项目事实和通用服务器部署检测规则生成。经验卡只能改变排序、
假设和证据计划，不能凭历史结果直接制造当前项目的弱点结论。

## 4. 组件和接口

### 4.1 RunContext

保存一次运行的不可变输入快照、profile hash、项目事实 hash、知识快照 hash、
随机种子、运行模式、预算、审批状态和输出目录。

### 4.2 ProjectAdapter

第一版使用离线 fixture adapter，统一暴露：

```python
onboard(profile) -> OnboardingResult
inventory(profile) -> InventoryResult
map_test_nodes(inventory, capability_rules) -> CandidateSpace
```

真实项目 adapter 后续可以替换 fixture，但不改变上层协议。

### 4.3 KnowledgeProvider

读取只读知识快照，返回与项目 TestNode、部署模式、依赖模式和证据需求匹配的经验卡。
知识状态为 `provisional` 或更高时才可以影响排序；`contested` 卡不得生成可执行意图。

### 4.4 LLMAdvisor

输入项目事实、候选、经验卡和证据要求，输出结构化假设、预期观测、否证条件和建议动作。
LLM 输出必须经过 schema 校验，不能写入最终状态字段。

第一版允许 `none` 模式，使用确定性 fixture 假设完成闭环测试。

### 4.5 Executor

第一版只实现 `FakeExecutor`：

```python
preflight(plan)
baseline(plan)
inject(plan)
observe(plan)
recover(plan)
cleanup(plan)
```

后续实现 `CEAdapter` 和 `NativeAdapter`，但它们都必须返回同一生命周期结果，
不能让底层平台状态直接绕过 ChaosAtlas 分类器和 RCA 状态机。

## 5. 统一命令

```powershell
python tools/chaosatlas.py run `
  --profile <project-profile> `
  --mode dry-run `
  --output <run-directory>
```

第一版只支持 `dry-run` 和 fake executor。`live`、CE adapter、native adapter
属于后续阶段，必须显式开启并经过 namespace、预算、恢复和清理门禁。

## 6. 状态和产物

每个阶段都写入：

- `stage.json`：阶段状态、输入 hash、输出 hash、错误和下一步；
- `checkpoint.json`：可恢复位置和已完成阶段；
- `evidence_refs.json`：证据引用和 claim scope。

运行结束至少生成：

```text
inventory.json
server_deployment_detection.json
candidate_space.json
retrieval.json
hypotheses.json
finding_report.json
rca_report.json
knowledge_draft.json
regression_intents.json
cleanup_report.json
summary.md
```

离线运行的最终状态只能是 `dry_run_ready`、`method_invalid` 或 `not_run` 等协议状态，
不得伪造 `weakness`、`defended` 或 `confirmed` 运行时结论。

## 7. 安全和失败策略

- profile 不合法时在 onboard 终止；
- namespace、业务 Oracle、恢复或 cleanup 缺失时 fail-closed；
- 经验卡缺失不阻止候选生成；
- LLM 不可用时保留确定性假设并记录 advisory unavailable；
- fake executor 的结果必须明确标记为合成证据；
- 任何未确认注入、业务不可达或平台阻断都不能进入知识晋级。

## 8. 验收标准

第一版完成必须满足：

1. 一条 dry-run 命令完成全部阶段并生成上述产物；
2. 同一输入和 seed 得到稳定的候选、检索和分类结果；
3. 中途失败后可以从 checkpoint resume；
4. 经验卡只影响排序、假设或证据计划，不直接制造弱点结论；
5. LLM 输出不能修改最终 verdict、RCA status 或 knowledge status；
6. Sock Shop、Online Boutique、P02 的离线 fixture 可以复用同一个编排器；
7. focused tests 覆盖协议、状态转移、artifact 完整性和 fail-closed 行为。

## 9. 非目标

第一版不包含：

- 真实 Kubernetes 注入；
- CE 服务 API 的实现；
- 自动修复部署或应用代码；
- 通用 CVE/安全漏洞扫描；
- 无审核的跨项目知识发布；
- 用单次 fake 结果宣称真实防御或真实弱点。
