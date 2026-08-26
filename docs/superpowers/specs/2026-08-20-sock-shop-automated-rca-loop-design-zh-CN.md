# Sock Shop 自动根因分析与经验迭代闭环

## 状态

本设计于 2026-08-20 获准进入规格编写阶段。本文定义第一阶段的实现范围，
不授权启动新的集群实验、调用外部模型、修改生产系统或自动发布跨项目知识。

## 1. 问题

ChaosAtlas 已经具备可用的运行时生命周期和三类知识层：选择经验、判定经验
和防御模式。它能够选择有边界的假设、编译故障注入、执行实验、验证业务影响、
恢复工作负载并保存证据。

目前缺少的是问题发现之后的控制闭环。运行报告通常在输出“弱点”或“有防御”
分类后结束，而根因分析大多仍是后续人工工作。现有回填工具主要按照服务名和
故障类型，把结果匹配到预先定义的经验条目；它们还不能维护针对具体案例的证据图、
比较多个竞争性解释、选择区分性实验，或者根据结果生成回归测试。

目标是建立一个有边界、可审计的闭环：

```text
发现弱点
  -> 创建 RCA 案例
  -> 生成根因假设
  -> 收集支持证据和反证
  -> 选择并执行区分性实验
  -> 确认、限定、延期或否定 RCA
  -> 生成临时知识卡或可复用知识卡
  -> 编译回归测试和下一轮测试
  -> 验证知识是否仍然成立
```

系统不能把业务失败直接转换成没有证据支持的内部机制。已确认的业务弱点和
已确认的根因是两个独立的结论。

## 2. 目标

1. 对每个符合条件的已确认运行时弱点，或具有重要信息价值的防御结果，自动创建
   可追溯的 RCA 案例。
2. 用预期观测、否证条件、支持证据和反对证据表示竞争性的根因假设。
3. 使用包含信息增益、成本、安全性和适用性的确定性规则，选择下一步证据动作或实验。
4. 根据证据，让每个 RCA 假设在 `pending`、`bounded`、`confirmed` 和 `rejected` 之间转换。
5. 自动创建知识卡和回归意图，不要求人工先写出第一版。
6. 允许强本地证据形成项目内可复用知识，同时保持跨项目推广和外部 issue 提交的审核门槛。
7. 让经验卡真正参与工作：它必须影响候选选择、RCA 假设生成、证据收集或回归测试生成。
8. 保留来源、矛盾、环境阻断和不可用诊断，不得隐藏这些信息。

## 3. 非目标

1. 自动修复应用代码、配置文件或生产系统。
2. 当只有服务边界症状时，声称已经定位到代码行级根因。
3. 替换现有的四层运行时门禁或业务 oracle。
4. 仅为了补录本设计而重新运行历史 Sock Shop 实验。
5. 未通过新的证据门槛前，不把历史 pending 报告作为正式知识卡。
6. 让 LLM 成为证据真实性、RCA 状态或知识晋级的最终裁决者。
7. 自动发布跨项目知识或提交上游 issue。

## 4. 设计原则

### 4.1 三种独立状态

每个案例分别记录以下三个状态：

```text
weakness_status   candidate | confirmed | protected | unsupported | environment_blocked
rca_status        pending | bounded | confirmed | rejected
knowledge_status  none | provisional | local_reusable | cross_project_pending | cross_project_reusable | contested
```

例如，`weakness_status=confirmed` 和 `rca_status=bounded` 是合法且预期的结果。
它表示业务失败是真实的，受影响的边界也已知，但内部机制尚未被证明。

### 4.2 证据优先于解释

不能因为一个解释听起来合理，或者 LLM 的置信度很高，就晋级该解释。每个假设都必须声明
哪些现象支持它、哪些现象可以否定它。日志、trace、源码或配置缺失时，应记录为“证据不可用”，
不能默认为反证。

### 4.3 先定位边界，再分析根因

RCA 按以下层次推进：

```text
业务症状
  -> 受影响的请求或服务边界
  -> 依赖或资源行为
  -> 配置或架构机制
  -> 有直接证据支持时再到源码级机制
```

当更深层证据不可用时，系统可以停在当前层，并将状态记为 `bounded`。

### 4.4 确定性规则负责裁决，LLM 只提供辅助

确定性引擎负责生命周期有效性、证据引用、状态转换、硬过滤、安全门禁和知识晋级。
LLM 可以提出假设、总结证据或建议候选动作，但所有输出都必须根据项目快照和动作模式
规范化、校验。

### 4.5 临时学习自动产生，广泛复用必须积累证据

第一版知识草稿自动生成。只有通过确定性证据门槛后，才允许项目内复用。跨项目暴露仍然需要
审核，除非同一模式已经在规定数量的项目中独立复现。

## 5. 架构

第一版由七个职责明确的组件组成。

### 5.1 案例组装器

输入有效运行报告、基线、业务 oracle 结果、静态拓扑引用和现有分类，针对每个规范化弱点签名
生成一个不可变的 `WeaknessCase` 快照。

它按照 `weakness_id` 对重复实验去重，但保留每次重复的记录，绝不覆盖相互矛盾的观测。

### 5.2 假设生成器

根据以下信息生成少量 RCA 假设：

- TestNode 和局部影响图；
- 部署配置和服务配置；
- 可用时的源码或契约清单；
- 规范化后的症状和时间特征；
- 适用的现有知识卡；
- 已知防御模式及其反条件。

假设必须限定到可观测机制。示例包括
`singleton_workload_no_redundancy`、
`synchronous_downstream_call_without_verified_timeout` 和
`transport_failure_propagates_as_business_error`。类似 `system is fragile` 的
模糊假设无效。

### 5.3 证据规划器

对证据动作排序。优先使用低成本只读动作；只有静态证据无法区分候选假设时，才使用运行时实验。
规划器必须输出选择该动作的明确理由。

### 5.4 诊断和实验适配器

适配器只能执行已经声明的动作类型。第一阶段支持：

- 静态 manifest、配置和源码查询；
- 有边界的服务日志和 Kubernetes events；
- 可用的 trace/span 查询；
- 真实业务链路重放与直接依赖重放的对比；
- 围绕已观察到的超时边界执行有边界的延迟或丢包阶梯；
- 在项目运行器明确允许时，执行隔离的副本数反事实实验；
- 故障移除后的重复测试和 washout 验证。

当动作的命名空间、目标、注入方式或清理契约无法在执行前校验时，应拒绝该动作。

### 5.5 RCA 评估器

输入原始案例、假设预测、证据结果和反证，应用确定性状态规则，并生成解释状态转换原因的审计记录。

### 5.6 知识投影器

将案例投影为知识卡，同时保留完整 RCA 案例作为审计记录。运行时细节留在审计记录中，除非知识卡
的证据结构明确允许引用这些细节。

### 5.7 回归编译器

把可复用知识卡转换成未来的测试意图。回归意图包含适用条件、业务 oracle、所需证据、预期的防御或
弱点边界以及停止规则。它不是一条无边界地重复同一注入的指令。

## 6. 数据契约

### 6.1 Weakness Case

规范化案例的结构如下：

```json
{
  "schema_version": "chaosatlas-weakness-case-v1",
  "weakness_id": "WS-sock-shop-front-end-catalogue-abort",
  "project_id": "sock-shop",
  "project_commit": "<pinned-commit>",
  "round_id": "<runtime-round>",
  "test_node": {
    "family": "HTTPChaos",
    "operation": "abort",
    "target_role": "catalogue-edge",
    "source_ref": "<redacted-or-relative-reference>"
  },
  "symptom": {
    "oracle": "<business-oracle-id>",
    "baseline_contract": "<normalized-contract>",
    "injected_contract": "<normalized-contract>",
    "observed_change": "response contract changed or request budget exceeded"
  },
  "weakness_status": "confirmed",
  "rca_status": "pending",
  "knowledge_status": "none",
  "evidence_refs": [],
  "hypothesis_ids": [],
  "next_actions": [],
  "replicates": [],
  "provenance": {
    "runtime_report_sha256": "<sha256>",
    "input_snapshot_sha256": "<sha256>"
  }
}
```

案例不能保存 secret、凭据、token 或未脱敏的私有 endpoint。源码缺失或不可用时，应记录收集尝试的
状态和引用，不能复制敏感配置。

### 6.2 RCA 假设

```json
{
  "hypothesis_id": "RCA-WS-sock-shop-front-end-catalogue-abort-01",
  "weakness_id": "WS-sock-shop-front-end-catalogue-abort",
  "claim": "transport abort at the catalogue boundary is propagated into the business response",
  "mechanism_class": "transport_error_propagation",
  "scope": {
    "services": ["front-end", "catalogue"],
    "edge": "front-end->catalogue"
  },
  "expected_observations": [
    "catalogue-side request failure is present in the diagnostic window",
    "front-end records or returns the corresponding downstream failure",
    "the real business path reproduces the boundary change"
  ],
  "falsifiers": [
    "direct dependency failure does not appear on the real business path",
    "a verified fallback returns the original business contract",
    "the same symptom occurs with no corresponding downstream event"
  ],
  "required_evidence": [
    "runtime_business_path",
    "downstream_diagnostic_or_source_mapping",
    "recovery_after_fault_removal"
  ],
  "evidence_for": [],
  "evidence_against": [],
  "unsupported_claims": [],
  "status": "pending",
  "confidence": 0.0,
  "next_action": null
}
```

### 6.3 证据记录

每条证据都必须记录来源、时间窗口、收集方法，以及适用时的完整性哈希和解释边界：

```json
{
  "evidence_id": "EV-...",
  "kind": "runtime_log | source_span | manifest | trace | oracle | counterfactual",
  "polarity": "supports | contradicts | unavailable | neutral",
  "claim_scope": "service boundary or exact mechanism being tested",
  "source_ref": "<relative-artifact-path-or-source-span>",
  "collected_at": "<timestamp>",
  "window": {"start": "<timestamp>", "end": "<timestamp>"},
  "sha256": "<sha256-or-null>",
  "interpretation": "bounded statement supported by this record"
}
```

评估器只能使用来源和范围与假设匹配的证据。一条显示客户端超时的日志，不能单独证明应用层缺少 timeout。

### 6.4 经验卡

在现有以测试节点为中心的字段之外，生成的卡片还要包含以下运行字段：

```text
id / version / status
project / project_commit / test_node
test_node_centered_graph
weakness_status / rca_status / knowledge_status
mechanism_claim / mechanism_level
applicability_conditions
exclusion_conditions
evidence_summary / counter_evidence
validation_recipe
regression_intents
stop_rule
lineage
next_evidence
```

现有验证器继续作为基础 schema 门禁。新增的 RCA 验证器还要检查状态一致性、证据引用、明确的反证，
以及非空的回归动作或下一步证据动作。

## 7. 状态机和晋级规则

### 7.1 弱点状态

现有运行时生命周期仍然是权威来源。只有有效完成的运行结果，或明确标记为有信息价值的防御结果，
才能创建案例。

```text
candidate -> confirmed
candidate -> unsupported
candidate -> environment_blocked
```

进入 `confirmed` 必须具备现有业务 oracle 和运行时生命周期证据。平台失败不能变成业务弱点。

### 7.2 RCA 状态

```text
pending -> bounded
pending -> confirmed
pending -> rejected
bounded -> confirmed
bounded -> rejected
bounded -> pending       出现新矛盾或证据不足
confirmed -> bounded     后续反证限制了原结论范围
confirmed -> rejected    可复现的矛盾否定了原结论
```

规则如下：

- `bounded` 需要稳定的受影响边界和至少一条支持证据，但不要求已经证明内部机制。
- `confirmed` 需要所有声明的必要证据、至少一个区分性动作，且不能存在未解决的高严重性矛盾。
- `rejected` 需要否证条件成立，或需要出现可复现且与该主张矛盾的结果。
- 当诊断不可用，或下一步动作不安全、不适用时，保持 `pending` 是合法结果。

### 7.3 知识晋级

```text
none -> provisional
provisional -> local_reusable
local_reusable -> cross_project_pending
cross_project_pending -> cross_project_reusable
local_reusable -> provisional       出现有意义的反例
```

`provisional` 对每个有效案例自动生成。它可以用于同一案例的后续诊断规划，但不能单独改变高影响候选的优先级。

进入 `local_reusable` 必须满足：

1. 两次有效复现，或一次有效反事实实验加一次有效复现；
2. `weakness_status=confirmed` 或 `weakness_status=protected`；
3. 机制型卡片要求 `rca_status=confirmed`；边界型卡片可以使用 `rca_status=bounded`，但必须明确标记为有边界的结论；
4. 生命周期和清理证据完整；
5. 至少有一个源码、manifest、日志、trace 或反事实证据引用；
6. 明确的适用条件和排除条件；
7. 已生成回归意图和停止规则。

跨项目复用首先进入 `cross_project_pending`，然后必须通过现有反馈协议中的人工审核，或在规定数量的项目中
独立复现。知识卡不能被静默加入后续项目的 prompt 快照。有意义的矛盾会将状态设为 `contested`，在重新评估前不能继续复用。

## 8. 主动证据和实验选择

规划器使用以下确定性元组为动作评分：

```text
priority = information_gain
         + evidence_completeness_gain
         + causal_discrimination_gain
         - execution_cost
         - risk
         - environment_uncertainty
```

信息增益取决于一个动作能区分多少个仍然存活的假设。除非适用性门禁失败，否则规划器按以下顺序优先选择：

1. 已有证据和精确的源码/配置查询；
2. 在已捕获时间窗口内收集有边界的日志、events 和 trace；
3. 真实业务链路重放与直接依赖重放的对比；
4. 受控的延迟/丢包边界探测；
5. 隔离的反事实实验，例如扩容副本数；
6. 新故障类型或更大范围的实验。

每个被选中的动作必须包含：

- 目标和命名空间范围；
- 前置条件；
- 对每个假设的预期证据；
- 清理和恢复契约；
- 最大执行时间和重试预算；
- 停止条件；
- 输出证据 schema。

当没有安全动作能够区分剩余假设时，系统停止并记录 `pending`，不能用 LLM 结论填补证据空白。

## 9. Sock Shop 试点映射

第一阶段处理三类已有结果。

### 9.1 单副本 PodKill

案例组装器将 manifest 证据（已验证的 `replicas=1`、无 PDB）与 Ready 状态变化和业务影响合并。预期生成的是
部署可用性知识卡。可确认的结论限定为“缺少冗余以及由此产生的中断窗口”，不能推断应用内部机制。

回归意图检查：

- 是否识别出单例工作负载；
- 是否执行有边界的 PodKill；
- 替换窗口期间业务 oracle 是否失败；
- 恢复和清理是否完成；
- 在运行器允许时，是否执行隔离的扩容到两副本反事实实验。

### 9.2 `catalogue-db` PodKill

初始案例确认业务影响和数据库依赖边界。RCA 生成器分别生成“数据库连接不可用”和“catalogue 侧错误传播”两个候选。
只有当有边界的日志、源码/配置证据，或区分性重放把连接失败与 catalogue 请求失败关联起来时，案例才可以将机制标记为确认；
否则保持 `rca_status=bounded`。

### 9.3 HTTP abort 传播

第一版案例记录响应契约变化，并区分直接依赖测量和真实业务链路测量。它可以在服务边界确认
`transport_error_propagation`，但除非真实链路和源码/配置证据支持，不能把机制命名为 `missing_timeout`。

## 10. 反馈到下一轮

回归编译器生成三类意图：

1. `reproduce`：使用稳定 oracle 和有边界预算，复现同一边界；
2. `discriminate`：执行可以区分剩余 RCA 候选的下一步实验；
3. `guard`：验证防御边界，或确保已经关闭的边界不被反复注入。

决策引擎只消费满足状态和证据门槛的卡片。知识卡可以影响：

- 候选故障类型的优先级；
- 目标调用边的选择；
- 所需的业务链路 oracle；
- 诊断采集要求；
- RCA 假设模板；
- 回归测试选择和停止规则。

每个下一轮输入都要记录卡片 ID 和快照哈希。后续结果必须回链到触发该动作的卡片。如果结果与卡片矛盾，
卡片增加反例，并降级为 `provisional` 或标记为 `contested`；历史记录不能被静默改写或删除。

## 11. 失败处理和安全性

出现以下情况时，闭环必须 fail closed：

- 缺少基线或业务 oracle；
- 没有确认故障已经注入；
- 没有确认恢复或清理完成；
- 命名空间或 selector 不匹配；
- 动作前置条件缺失；
- 存在残留 Chaos 资源；
- 证据引用超出冻结输入或运行时间窗口；
- 检测到敏感值；
- 项目身份或 commit 身份冲突；
- 尝试进行同轮或同项目的跨项目反馈。

诊断不可用是一个一等结果。案例仍然有价值，也可以生成有边界的知识卡，但不可用证据不能被计为支持或反对。

## 12. 验证和验收标准

只有当 focused tests 证明以下内容时，才算实现通过：

1. 有效运行报告能创建带重复实验血缘的一条规范化案例；
2. 重复报告不会删除或覆盖相互矛盾的证据；
3. 证据的极性和声明范围会被校验；
4. 每个 RCA 状态转换都有确定性的原因；
5. 没有证据支持的机制主张不能进入 `confirmed`；
6. 环境阻断运行不能创建弱点卡；
7. 临时知识卡能自动生成；
8. 本地晋级必须满足声明的证据门槛；
9. 反证会使卡片降级或进入争议状态，但不会删除历史；
10. 回归意图包含 oracle、证据要求和停止规则；
11. 下一轮输入包含卡片 ID 和快照哈希；
12. 敏感值检查和路径边界检查仍然生效；
13. 现有知识库验证和运行时生命周期测试继续通过。

当三类 Sock Shop 案例都具备机器可读案例、明确 RCA 状态、至少一个自动生成的下一步动作，以及生成的知识/回归产物时，
试点即视为完成。三类案例不必全部达到 `rca_status=confirmed`；当现有证据不足以支持更强结论时，保留 `bounded` 或 `pending` 也是成功结果。

## 13. 已考虑的替代方案

### 只做后处理

这种方式只在当前运行报告之后增加 RCA 字段，成本较低，但无法形成真正的主动调查闭环，实验选择仍然主要依赖人工。

### 完全由 LLM 代理调查

这种方式可以支持灵活的多步调查，但证据真实性、重复执行、成本和安全性难以审计。因此不适合让 LLM 负责 RCA 状态或知识晋级。

### 选定方案

采用证据图、确定性 RCA 状态机和主动实验规划器。LLM 保留为受约束的假设生成器和解释助手。
这样既复用现有生命周期、业务 oracle、TestNode 图、决策引擎、知识验证器和反馈边界，又补上了从问题发现到迭代学习之间缺失的中间层。
