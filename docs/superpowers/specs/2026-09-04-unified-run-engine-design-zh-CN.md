# 统一 RunEngine 设计

日期：2026-09-04  
状态：已实施（HTTP live canary 已通过；Chatflow 因模型账户余额不足而阻塞）
项目：ChaosAtlas

## 1. 目的

ChaosAtlas 当前有两条编排路径。dry-run 使用
`tools/chaosatlas_orchestrator.py`，内部采用离线适配器和假执行器；live
及 live-batch 则通过兼容入口转交给 `_legacy_chaosatlas.py` 和
`_legacy_chaosatlas_batch.py`。

本次改造将用一个统一的 `RunEngine` 取代这些并行编排路径。dry-run、单候选
live 和多候选 live 将共享同一套阶段状态机、契约、策略循环、证据写入器和结果语义。
不同模式之间只通过注入的运行时能力来体现差异。

这次迁移保留现有 ChaosAtlas 方法，不为四个应用另建专用实验流水线，也不会在没有
明确契约迁移的情况下改变已经验证过的故障、分类、RCA、恢复、清理或知识提升规则。

## 2. 目标

统一引擎必须实现：

1. dry-run 与 live 使用同一个编排实现；
2. 单候选运行等价于预算为 1 的批量运行；
3. 保持候选 ID 和因果身份稳定；
4. 保留确定性的安全、注入、观测、恢复、清理、分类、复现、RCA 和知识提升门；
5. 通过统一接口支持确定性策略、LLM 策略及未来策略；
6. 通过统一注册表支持 HTTP、gRPC、Dify Chatflow 和项目工作流 Oracle；
7. 所有运行证据通过唯一的带哈希证据写入器产生；
8. 保持当前 CLI 行为以及 live 显式授权要求；
9. 在不创建项目专用编排分支的前提下，支持 Immich、ERPNext、Medusa 和
   Rocket.Chat 的能力学习阶段；
10. 完成行为等价与 live canary 验证后，移除旧编排文件。

## 3. 非目标

本次改造不包括：

- 在这四个能力学习项目上运行 Full/noKB/noLLM 消融实验；
- 重新设计现有故障目录；
- 降低 namespace、selector、授权、清理或恢复保护；
- 自动提交上游 Issue；
- 迁移或删除已有证据档案；
- 让 dry-run 的合成证据有资格支持运行时结论；
- 对保留的基线 namespace 执行高风险数据库或存储故障。

## 4. 当前状态

公共 CLI 位于 `src/chaosatlas/cli.py`。

- dry-run 调用 `tools.chaosatlas_orchestrator.run_closed_loop`；
- 单候选 live 调用 `tools._legacy_chaosatlas.run_closed_loop`；
- live batch 通过 `tools.chaosatlas_batch` 转发到
  `tools._legacy_chaosatlas_batch`；
- 新 dry-run 编排器使用 `OfflineProjectAdapter` 和 `FakeExecutor`；
- live 路径使用 `KubernetesProjectAdapter` 和
  `KubernetesLifecycleExecutor`；
- 业务探测目前通过硬编码分支选择 HTTP、gRPC 或 Dify Chatflow 行为。

这种分叉造成了阶段所有权重复，即使项目、seed、候选池和策略输入相同，dry-run 与
live 的结果也可能出现语义偏差。

## 5. 目标架构

目标调用关系如下：

```text
CLI
  -> RunRequest 校验
  -> RunEngine
       -> ProjectAdapter
       -> CandidateProvider
       -> KnowledgeProvider
       -> PolicyProvider
       -> ApplicabilityGate
       -> LifecycleExecutor
            -> FaultExecutor
            -> WorkflowOracle
            -> EvidenceCollector
            -> RecoveryManager
            -> CleanupVerifier
       -> ResultClassifier
       -> ReproductionController
       -> RCAController
       -> KnowledgePromotionGate
       -> IssueDraftGenerator
       -> ArtifactWriter
```

第一版实现将在这些接口背后复用现有函数。“搬迁代码”与“修改算法”必须是两个独立
变更。迁移期间先包装现有行为，证明等价后再进行内部重构。

## 6. 核心契约

### 6.1 RunRequest

`RunRequest` 是每次运行经过校验的输入，包含：

- profile 路径；
- 输出目录；
- 模式（`dry-run` 或 `live`）；
- seed；
- 候选数量上限或指定候选 ID；
- 知识读取与写入目录；
- 策略配置；
- Kubernetes context；
- live 显式授权状态。

所有输入在修改输出目录前完成校验。live 仍然要求显式授权、空白的新输出目录和合法的
namespace allow-list。

### 6.2 RunDependencies

`RunDependencies` 保存引擎依赖的可替换行为：

- 项目适配器；
- 策略提供器；
- 生命周期执行器；
- Oracle 注册表；
- 知识提供器；
- 证据写入器；
- 在确定性测试中可注入的时钟和进程运行器。

生产依赖由唯一的组合入口创建。测试可以传入 fake，但引擎不能通过隐藏条件自行选择
fake。

### 6.3 WorkflowOracle

所有业务 Oracle 实现同一个契约：

```text
prepare_fixture(run_context) -> FixtureResult
probe(phase, run_context) -> OracleResult
collect_evidence(run_context) -> EvidenceResult
cleanup_fixture(run_context) -> CleanupResult
```

`phase` 只能是 `baseline`、`observe` 或 `recovery`。Oracle 结果包含结构化断言、
耗时、脱敏响应摘要、已创建资源 ID、清理状态和证据引用。Oracle 只报告事实，不负责把
故障分类为 weakness 或 defense。

### 6.4 PolicyProvider

策略提供器只能接收已经通过 gate 的候选、允许访问的知识视图、当前项目反馈、剩余预算
和强制待办任务。它输出以下结构化建议：

- 下一个候选；
- 参数等级；
- 复现、升级、探索或停止；
- 竞争性 RCA 假设；
- 下一项 RCA 证据动作。

确定性 gate 可以拒绝或覆盖任何建议。所有建议、拒绝和覆盖都必须记录。

### 6.5 ArtifactWriter

唯一的证据写入器负责阶段封装、规范 JSON 序列化、哈希、别名、checkpoint 和原子写入。
任何模式专用运行器都不能写入另一套阶段格式。

## 7. 统一阶段状态机

每次运行都使用以下有序状态机：

```text
onboard
-> inventory
-> server_deployment_detection
-> mapping
-> retrieval
-> hypotheses
-> gate
-> baseline
-> select
-> execute
-> observe
-> recovery
-> cleanup
-> classify
-> reproduce
-> rca
-> learn
-> promote_defense
-> promote_weakness
-> regression
-> issue_draft
-> audit
-> complete
```

只有在写明状态和原因时才能跳过阶段。被跳过或仅计划的阶段不能表示成成功的运行时
证据。

在选择新候选前，必须按以下顺序完成强制待办：

1. 恢复并清理仍在生效的故障；
2. 完成待复现异常；
3. 完成必要的 RCA 证据动作；
4. 完成必要的参数审计；
5. 选择新的合格候选；
6. 运行停止后的遗漏异常审计。

## 8. 模式语义

### 8.1 Dry-run

dry-run 与 live 使用相同的 onboarding、inventory 规范化、候选身份、知识检索、策略、
gate 和证据规划代码。它使用 `PlanExecutor`，执行阶段输出 `not_run`，并标记
`claim_scope: planned`。

dry-run 不能输出运行时 weakness、defense、已确认 RCA、提升后的知识或 Issue 草稿。

### 8.2 Live

live 使用 Kubernetes 生命周期和故障执行器。运行时结论必须满足现有确定性契约，包括：
注入已确认、baseline 合法、业务观测有效、恢复成功且清理完成。

### 8.3 单候选与批量

系统只保留一个候选循环。单候选运行通过指定候选或将候选预算设为 1 实现；批量运行
使用同一循环和更大的预算，不再保留独立批量编排器。

## 9. 项目接入

四个能力学习项目复用 Kubernetes 通用适配器，并分别提供：

- 项目 profile；
- 依赖边；
- 确定性合成 fixture；
- 事务型 workflow oracle；
- 支持及不适用的故障声明；
- 恢复与清理契约；
- 敏感数据脱敏规则。

项目顺序固定为：

1. Immich；
2. Medusa；
3. Rocket.Chat；
4. ERPNext。

这四个项目只运行完整方法，不做消融。它们用于完善能力覆盖、发现工具问题、寻找可复现
应用异常、生成可审核 Issue 草稿，并为后续评估项目建立经过证据门控的知识。

## 10. 证据与 Issue 草稿

Issue 草稿是已确认实验结果的末端消费者，不能修改分类或知识提升决定。

生成 Issue 草稿必须满足：

- 项目 revision 和部署 manifest 已冻结；
- 干净 baseline 成功；
- 故障注入已确认；
- 确定性业务影响已确认；
- 相同因果身份完成三次独立复现；
- 每次复现都成功恢复并清理；
- RCA 至少确认到服务边界；
- 脱敏证据索引完整。

草稿包含环境、版本、最小复现、预期与实际行为、影响、复现表、RCA 范围、恢复行为和
脱敏证据引用。生成器只写 Markdown，绝不自动提交到上游服务。

## 11. 错误处理与安全

- 非法方法输入在 live 修改前以 `method_invalid` 结束；
- 缺少平台前置条件时以 `environment_blocked` 结束，不能给应用贴负面标签；
- 未确认的注入不能支持 weakness 或 defense 结论；
- 恢复或清理失败时，必须在执行下一候选前停止运行；
- live 被中断时优先清理，并写入中断证据；
- 输出目录必须原子创建；除非未来存在经过审计的 resume 契约，否则 live 拒绝非空目录；
- namespace、selector、owner label 和 secret 脱敏 gate 保持确定性并默认拒绝；
- 合成凭据和数据必须与用户数据隔离。

## 12. 迁移策略

迁移分阶段进行：

1. 为当前 dry-run、live 和 live-batch 行为增加特征测试；
2. 增加共享的 request、dependency、stage result、oracle、policy 和 artifact 契约；
3. 使用现有实现的包装器建立统一 `RunEngine`；
4. 让 dry-run 通过 `PlanExecutor` 进入 `RunEngine`；
5. 让单候选 live 进入同一引擎；
6. 让多候选 live 进入同一候选循环；
7. 用 `OracleRegistry` 取代硬编码分支，同时保持 HTTP、gRPC 和 Dify 行为；
8. 将现有 Dify 命令和 canary 切换到统一入口；
9. 添加四个项目包和 workflow oracle；
10. 运行等价性、仓库验收及 live canary；
11. 确认没有引用后，移除兼容转发和旧编排文件。

每一步都必须保持仓库可运行。最后才删除 legacy，不能先删除再重写。

## 13. 测试策略

### 13.1 契约测试

- 校验 request 和 dependency 构造；
- 校验所有阶段结果和证据封装；
- 校验 Oracle 结果、fixture、策略决策和清理 schema；
- 校验 secret 脱敏和规范哈希。

### 13.2 特征与等价测试

对于现有 fixture 和固定 seed，对比旧路径与统一路径的：

- 项目 inventory；
- 候选 ID 和因果身份；
- 候选顺序；
- gate 结果；
- 故障 manifest；
- 运行时分类；
- 恢复与清理结果；
- RCA 状态转换；
- 知识提升决定。

可以规范化时间戳、路径和进程 ID，但语义字段不能发生变化，除非存在经过审核的明确
迁移。

### 13.3 模式测试

- dry-run 不执行任何 Kubernetes 修改；
- dry-run 不产生运行时结论；
- live 必须有显式授权；
- 单候选和批量使用同一循环；
- 策略拒绝和确定性 fallback 被完整记录；
- 运行中断后先清理再结束。

### 13.4 Live canary

在四个应用产生正式证据前：

1. 通过统一引擎运行现有 Dify HTTP/Chatflow canary；
2. 验证注入、观测、恢复和清理；
3. 验证没有残留 Chaos Mesh 子资源；
4. 验证证据档案哈希；
5. 对每个新 workflow oracle 运行一次低风险 canary。

## 14. 验收标准

只有满足以下全部条件，合并才算完成：

1. dry-run、单候选 live 和批量 live 全部进入同一个 `RunEngine`；
2. 只保留一个候选循环和一个证据写入器；
3. `FakeExecutor` 不再把 dry-run 表示为合成运行时行为；
4. 所有 Oracle 类型都通过 `OracleRegistry` 解析；
5. 现有离线、Dify、故障、生命周期、RCA、知识和清理测试全部通过；
6. 固定 fixture 和 seed 的新旧语义等价测试通过；
7. Dify 统一 live canary 通过，且恢复与清理完整；
8. CLI 保持兼容，或者输出明确的迁移提示；
9. 生产代码不再导入 `_legacy_chaosatlas.py` 或
   `_legacy_chaosatlas_batch.py`；
10. 两个旧编排文件均被删除；
11. 仓库文档将统一引擎声明为唯一受支持的编排路径；
12. 四个能力学习项目能够通过项目 profile 和已注册的 workflow oracle 进入统一引擎。

## 15. 交付边界

统一引擎必须在四项目第一次正式证据运行之前完成并通过验证。共享 Oracle 和项目契约
冻结后可以开始开发项目包，但在统一引擎通过全部验收标准之前，任何四项目运行产物都
不能提升为正式证据。
