# Dify API 单副本导致 Kubernetes 环境存在单点故障

**问题归属：** Dify 被测项目 / Dify Kubernetes 部署配置

**建议提交位置：** Dify 项目 Issue 区或维护该 Kubernetes 部署配置的仓库

**建议标签：** `bug`, `availability`, `kubernetes`, `high-priority`

## 标题

`Dify API runs as a single replica and becomes unavailable during replica loss`

## 问题描述

当前 Kubernetes 部署中的 `dify-k8s-api` 只有一个可用副本。对 API 执行副本缩减故障时，业务 Chatflow 请求直接返回 `502`，说明 API 没有可用的服务实例承接请求。

如果单副本是测试环境的明确选择，请将本 Issue 视为生产部署配置改进，而不是 Dify 应用逻辑缺陷。

## 复现环境

- Dify: `1.17.0`
- Kubernetes context: `chaosatlas-dify`
- Namespace: `dify-k8s-lab`
- 业务入口：`/v1/chat-messages`
- 业务预期：HTTP `200`

## 复现步骤

1. 部署 Dify Kubernetes 环境，并确认 `dify-k8s-api` 只有一个副本。
2. 对 `dify-k8s-api` 执行 `replica_reduction` 故障。
3. 通过 Dify Chatflow 连续发送业务请求。
4. 观察请求状态码和恢复时间。

## 实际结果

`replica_reduction` 共执行 3 次，3 次业务观察均为 `business_unreachable`，返回 HTTP `502`。

## 预期结果

在单个 API Pod 丢失或滚动更新期间，仍应由其他 API Pod 承接请求，或返回明确且受控的降级结果，而不是直接出现网关 `502`。

## 建议方案

- 将 API 副本数设置为至少 `2`。
- 为 API 配置 `PodDisruptionBudget`。
- 为多个副本配置跨节点或跨故障域反亲和性。
- 检查 Service、readiness probe 和滚动更新策略是否允许无中断切换。

## 验收标准

- API 至少运行两个 Ready 副本。
- 删除任意一个 API Pod 后，Chatflow 请求仍能返回 HTTP `200`。
- 滚动更新期间无持续性 `502`。
- 提供副本数、PDB、Service 和故障测试结果作为证据。

## 证据

运行摘要：`60` 个唯一假设，`180` 次 trial。

本地证据目录：`.runs/dify-k8s-repeated-coverage-60hypotheses-verified-20260901/trials/030-replica_reduction-dify-k8s-api-r01`、`r02`、`r03`
