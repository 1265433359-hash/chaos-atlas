# 统一 RunEngine 实施报告

日期：2026-09-05

项目：ChaosAtlas

结果：代码与 HTTP live canary 验证通过；Chatflow canary 被外部账户状态阻塞

## 已完成

- `src/chaosatlas/orchestration/engine.py` 成为 dry-run 和 live 的唯一组合入口。
- 所有公开 live 请求都进入 `src/chaosatlas/orchestration/batch.py` 的同一候选循环；单候选就是预算为 1。
- dry-run 改用 `PlanExecutor`，执行和观测均为 `not_run`、`claim_scope: planned`，不能产生运行时结论。
- `RunRequest` 统一运行输入，`RunDependencies` 统一可替换运行能力。
- HTTP、gRPC、Dify Chatflow 全部通过 `OracleRegistry` 解析，并使用同一 `WorkflowOracle` 契约。
- 删除 `_legacy_chaosatlas.py` 和 `_legacy_chaosatlas_batch.py`；旧命令只保留转发兼容。
- resume 会重新计算阶段产物哈希，任何已完成阶段被修改都会以 `method_invalid` 拒绝继续。
- 候选选择、停止决策、证据计划、清理报告和摘要均正式落盘；计划证据不会被提升为运行时证据。
- 所有 Oracle 在故障执行后都会进行带 owner 与目标范围的 Chaos Mesh 清理扫描。

## 自动化验收

- 全量回归：`230 passed`。
- 仓库验收：`success`，包括编译、架构契约、两个 dry-run 和产品边界。
- 产品快照中的 CLI 能正常启动，并能导入 `RunEngine`、`RunDependencies` 和默认 Oracle 注册表。
- 生产 Python 代码不再导入两个旧编排器。

## Live canary

运维 canary profile：
`projects/dify-kubernetes/profile-http-canary.json`。

通过的证据目录：
`.runs/unified-engine-http-canary-20260905-002`。

统一引擎对 `dify-k8s-api` 执行了一次 `pod_kill`，结果为：

- 批次状态 `completed`；
- 子运行状态 `live_completed`；
- 清理状态 `verified`；
- 恢复后 API Deployment 为 `1/1 Ready`；
- 清理扫描覆盖 22 类 Chaos Mesh 资源；
- 报告残留数为 `0`，独立 kubectl 检查同样没有残留资源。

这个 HTTP canary 只证明统一引擎的注入、观测、恢复、清理和证据链，不替代 Chatflow 业务证据，也不能据此生成应用 Issue。

## 当前外部阻塞

Chatflow canary 已进入统一引擎，但在注入前停止。Dify 工作流使用的 DeepSeek
模型提供方返回 HTTP 402，原因是账户余额不足。ChaosAtlas 因业务 baseline 无效而拒绝
注入，这是预期的安全行为。证据保存在
`.runs/unified-engine-canary-20260905-001`，该运行没有 Chaos Mesh 残留，只能支持
“环境阻塞”结论。

充值模型账户或把测试工作流切换到可用模型后即可重跑 Chatflow canary。不能绕过
baseline gate，否则后续证据不具备论文与 Issue 审核资格。
