# ChaosAtlas 执行结果在观察完成后仍保留 observation_pending

**问题归属：** ChaosAtlas 测试框架（我们的项目）

**建议提交位置：** ChaosAtlas 项目 Issue 区

**建议标签：** `bug`, `reporting`, `data-contract`, `testing`

## 标题

`Runtime fault verdict remains observation_pending after observation has completed`

## 问题描述

在本轮已完成的 180 个 trial 中，故障记录的执行状态为 `executed`，观察阶段已经写入结果，但 fault-level `verdict` 仍为 `observation_pending`。这会使下游 RCA、统计和人工报告无法直接使用 verdict 字段判断真实业务结果。

## 实际结果

180/180 条记录出现以下状态组合：

- `fault_status=executed`
- `observation.status` 已完成，结果包括 `pass`、`degraded` 和 `business_unreachable`
- `verdict=observation_pending`

业务观察实际统计为：`pass=169`、`degraded=7`、`business_unreachable=4`。

## 预期结果

观察阶段结束后，fault-level verdict 应与业务 oracle 的最终结果一致，例如：

- `pass`
- `degraded`
- `business_unreachable`
- `observation_inconclusive`

`observation_pending` 只能出现在观察尚未执行或证据尚未写完的中间状态。

## 建议方案

- 在 observe stage 完成时统一计算并写入 verdict。
- 为 stage status、fault status、business outcome 和 lifecycle attestation 明确定义字段边界。
- 在汇总和 RCA 前增加一致性校验，拒绝“观察已完成但 verdict 仍 pending”的记录。
- 为每种最终 verdict 增加 schema 测试。

## 验收标准

- 已完成观察的 trial 不再保留 `observation_pending`。
- 汇总中的 verdict 分布与 observation 状态分布一致。
- 无效或缺失观察证据只能进入 `observation_inconclusive` 或失败状态。

## 证据

运行摘要：`.runs/dify-k8s-repeated-coverage-60hypotheses-verified-20260901/repeat_summary.json`
