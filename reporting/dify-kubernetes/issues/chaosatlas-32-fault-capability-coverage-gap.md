# ChaosAtlas 当前 Dify Kubernetes 环境无法覆盖全部 32 个具体故障能力

**问题归属：** ChaosAtlas 测试框架（我们的项目）

**建议提交位置：** ChaosAtlas 项目 Issue 区

**建议标签：** `enhancement`, `testing`, `fault-coverage`, `kubernetes`

## 标题

`Expand Dify Kubernetes fault capability matrix beyond the current 17 live-testable families`

## 问题描述

ChaosAtlas 的故障目录分为 8 个故障大类，共包含 32 个具体故障能力。当前 Dify Kubernetes profile 的 live 测试覆盖了 17 个具体故障能力，分布在 6 个大类中；另外 15 个具体故障能力在当前环境被标记为 `inapplicable`。因此当前结果可以声称“17 个具体故障能力已完成 live 验证”，不能声称“32 个具体故障能力全部完成真实运行验证”。

## 当前结果

- 唯一假设：`60`
- 每个假设重复：`3`
- 实际 trial：`180`
- 故障大类总数：`8`
- 具体故障能力总数：`32`
- 已覆盖具体故障能力：`17`
- 当前不可适用具体故障能力：`15`
- 自动化回归测试：`165 passed`

## 问题影响

缺少统一的适用性、阻断原因和后续启用条件时，用户容易把“候选已生成”误解为“故障已真实注入并验证”。这也会影响不同项目之间的覆盖率比较。

## 建议方案

- 为 8 个故障大类、32 个具体故障能力建立机器可读 capability matrix。
- 每个 `inapplicable` 项记录明确原因，例如内核能力、Chaos Mesh CRD、权限、网络插件或目标组件不存在。
- 为可补齐的故障增加隔离环境和最小复现 fixture。
- 在最终报告中分开统计 `live_completed`、`inapplicable`、`blocked_by_platform_prerequisite` 和 `not_reachable`。
- 只有完整生命周期 attestation 通过后，才将故障计入真实运行覆盖率。

## 验收标准

- 32 个具体故障能力均有明确状态和证据引用。
- 新增故障在至少一个可复现 Kubernetes fixture 中完成注入、观察、恢复和清理验证。
- 报告同时展示候选覆盖率、可执行覆盖率和完整生命周期覆盖率。

## 证据

运行摘要：`.runs/dify-k8s-repeated-coverage-60hypotheses-verified-20260901/repeat_summary.json`

Profile：`projects/dify-kubernetes/profile.json`
