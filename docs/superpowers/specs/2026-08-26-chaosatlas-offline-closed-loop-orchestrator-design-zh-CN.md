# ChaosAtlas 离线闭环编排器设计

## 状态

已获用户确认。本设计是产品主线的下一步：把现有项目接入、服务器部署检测、
经验检索、候选策略、停止策略、RCA、反馈和知识能力收束为一个可恢复、可审计的
离线编排器。第一版只验证数据流和状态边界，不宣称真实运行时漏洞或防御结论。

## 1. 目标与边界

输入项目 profile 和对应的离线项目事实，执行：

```text
onboard
  -> inventory
  -> server_deployment_detection
  -> mapping
  -> retrieval
  -> hypotheses
  -> gate
  -> baseline
  -> execute
  -> observe
  -> classify
  -> rca
  -> learn
  -> promote_defense
  -> regression
```

产出完整的阶段记录、候选选择、停止决策、证据引用、RCA、知识草稿和回归意图。

第一版明确不做：

- 真实 Kubernetes 故障注入；
- CE 服务 API 或 native executor 的实现；
- 自动修复部署或应用代码；
- 通用 CVE 扫描；
- 未审核的跨项目知识发布。

## 2. 核心原则

### 2.1 候选先于经验

候选全集必须由项目画像和服务器部署检测能力生成。经验卡只能影响候选排序、
假设表达和证据计划，不能直接制造当前项目的弱点结论。

### 2.2 LLM 只提供建议

LLM（如不可用则使用确定性 fallback）只能输出机制、预期观测、缺失证据和下一步动作。
解析器拒绝 `weakness_status`、`rca_status`、`final_verdict`、`knowledge_status`
等结论字段。最终分类、RCA 状态和知识晋级由确定性规则及证据决定。

### 2.3 合成证据不等于运行结论

dry-run 的 FakeExecutor 只返回合成生命周期和 `claim_scope=synthetic`。它可以验证
状态机、产物和清理路径，但不能产生 `confirmed_weakness`、`protected` 或 `confirmed`。

### 2.4 失败默认收紧

profile、namespace、业务 Oracle、恢复或 cleanup 契约缺失时停止当前阶段。以下状态
永远不能晋级为 weakness，也不能更新策略或知识库：

```text
environment_blocked
not_reachable
method_invalid
unsupported
```

真实运行只有同时满足证据完整、RCA confirmed、恢复成功和 cleanup verified，才可生成
反馈记录；知识卡仍需人工审核后才可影响后续项目。

## 3. 组件与职责

### 3.1 RunContext 与阶段契约

`RunContext` 固定 profile、事实、知识快照的指纹、seed、模式和输出目录。每个阶段
使用统一的 `StageResult` 写入 JSON，包含：

- 阶段名、状态和 claim scope；
- 规范化输出及 SHA-256；
- 错误列表和下一阶段；
- 写入时间。

`checkpoint.json` 记录已完成阶段和下一阶段。resume 必须验证原始输入指纹及已有产物
哈希，任何不一致都返回 `method_invalid`，不得覆盖已有结果。

### 3.2 OfflineProjectAdapter

适配现有离线 fixture，暴露 `onboard`、`inventory`、`detect_server_deployment` 和
`map_test_nodes`。检测结果只描述 Deployment、selector、副本、依赖、恢复契约和
候选故障族，不包含运行时 verdict。

### 3.3 KnowledgeProvider 与 Hypothesis Boundary

KnowledgeProvider 只读加载匹配项目身份的经验卡，并记录被拒绝卡及原因。排序器在
候选全集不变的前提下利用经验卡和策略状态改变顺序。Hypothesis Boundary 对可选 LLM
输出做 schema 校验和字段白名单过滤。

### 3.4 FakeExecutor 与后续执行器

FakeExecutor 实现统一生命周期：

```text
preflight -> baseline -> inject -> observe -> recover -> cleanup
```

后续 CEAdapter、NativeAdapter 必须实现同一生命周期和证据契约，由编排器统一分类，
不能绕过 ChaosAtlas 的 RCA 与知识门禁。

## 4. 运行与产物

产品命令为：

```powershell
python -m chaosatlas run `
  --profile projects/sock-shop/profile.json `
  --mode dry-run `
  --output <run-directory>
```

运行目录至少包含：

```text
run_context.json
onboard.json
inventory.json
server_deployment_detection.json
mapping.json
retrieval.json
hypotheses.json
gate.json
baseline.json
execute.json
observe.json
classify.json
rca.json
learn.json
promote_defense.json
regression.json
checkpoint.json
summary.json
```

每个 JSON 均带阶段状态、输出哈希和 claim scope。最终 dry-run 状态只能是
`dry_run_ready`、`method_invalid` 或 `not_run`。

## 5. 候选、预算与停止

离线编排器按单候选阶段执行策略选择，保留候选全集和选择快照。停止判断在下一次
执行前发生，至少支持：预算耗尽、候选耗尽、低期望价值、已解析和阻断。FakeExecutor
不会更新真实 policy state；只记录可供后续 live 适配器使用的反馈形状。

## 6. 错误处理与恢复

- onboard 失败：只写入 onboard 和 summary，状态为 `method_invalid`；
- 静态检测失败：停止后续候选阶段，不生成运行结论；
- advisory 失败：保留确定性假设，并记录 `advisory_unavailable`；
- fake 生命周期异常：写入失败阶段和 checkpoint，不删除已有证据；
- resume：从第一个未完成阶段继续，禁止重复写入已验证阶段；
- 非空输出目录：除显式 `--resume` 外拒绝运行，避免覆盖用户数据。

## 7. 验收标准

实现完成后必须验证：

1. 一条 dry-run 命令在 Sock Shop、Online Boutique、P02 和 Nginx fixture 上生成完整产物；
2. 相同 profile、facts 和 seed 产生相同候选顺序、停止决策和摘要哈希；
3. 中断后 resume 能复用已完成阶段，输入变化会 fail-closed；
4. dry-run 产物不包含真实 weakness、defense 或 confirmed claim；
5. 经验卡影响排序/假设/证据计划，但不改变候选全集和最终 verdict；
6. focused tests 覆盖契约、阶段顺序、产物完整性、恢复和失败收紧行为；
7. 现有 `src/chaosatlas` 入口仍保留 live 兼容路径，但本阶段明确拒绝 live 模式。

## 8. 后续接入顺序

离线编排器验收后，按以下顺序推进：

```text
真实项目 adapter
  -> native executor canary
  -> CE adapter（可选）
  -> live policy feedback
  -> 人工审核后的跨项目知识回归
```

每一步都复用本设计的阶段契约和 fail-closed 门禁，不重新实现候选、停止或 RCA 算法。
