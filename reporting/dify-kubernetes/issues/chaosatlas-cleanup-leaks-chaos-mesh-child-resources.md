# ChaosAtlas 清理阶段未覆盖 Chaos Mesh 子资源

**问题归属：** ChaosAtlas 测试框架（我们的项目）

**建议提交位置：** ChaosAtlas 项目 Issue 区

**建议标签：** `bug`, `testing`, `cleanup`, `kubernetes`

## 标题

`Live cleanup can leave orphaned Chaos Mesh child resources in the test namespace`

## 问题描述

ChaosAtlas 的 trial 主资源删除和清理报告可以显示成功，但 namespace 中仍可能残留由 Chaos Mesh 生成或关联的子资源。本轮测试结束后发现一个 `PodNetworkChaos` 残留资源，必须手动删除。

## 实际结果

测试主资源的 cleanup report 为 `verified`，但额外扫描发现：

- Resource: `podnetworkchaos`
- Namespace: `dify-k8s-lab`
- Target Pod: `dify-k8s-local-sandbox-7bb545c9b8-wglpr`
- `spec` 为空，带有 Pod owner reference

该资源已手动删除，删除后 namespace 中 Chaos Mesh 资源数量为 `0`。

## 影响

残留资源可能影响后续 trial 的基线、故障注入结果和环境隔离，并使“cleanup verified”与 namespace 实际洁净状态不一致。

## 建议方案

- 清理阶段按 namespace 扫描所有 Chaos Mesh resource kinds，而不只删除 action 记录中的主资源。
- 使用统一的 owner、run ID 和 trial ID 标签识别本次运行创建的资源。
- 对 owner reference 指向已不存在 Pod 的资源执行 orphan cleanup。
- 将 namespace 级零残留检查写入最终汇总门禁。

## 验收标准

- 每个 live run 结束后，目标 namespace 不存在本次 run 创建的任何 Chaos Mesh 资源。
- cleanup report 明确记录扫描过的 resource kinds 和发现数量。
- 模拟主资源删除失败、子资源残留和 Pod 提前删除时，测试能失败并保留诊断证据。

## 证据

运行目录：`.runs/dify-k8s-repeated-coverage-60hypotheses-verified-20260901`

残留资源已在最终环境审计阶段删除；该 Issue 记录的是清理门禁覆盖不足。
