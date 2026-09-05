# Dify API 在 Pod 或容器重启期间出现短暂 502

**问题归属：** Dify 被测项目 / Dify Kubernetes 部署配置

**建议提交位置：** Dify 项目 Issue 区或维护该 Kubernetes 部署配置的仓库

**建议标签：** `bug`, `availability`, `kubernetes`, `needs-investigation`

## 标题

`Dify API returns transient 502 responses while an API Pod or container is restarted`

## 问题描述

在 API Pod 或容器被终止后，Dify 业务请求会出现短暂的 HTTP `502`。请求随后可以恢复，但故障窗口内用户请求失败。

## 复现环境

- Dify: `1.17.0`
- Kubernetes context: `chaosatlas-dify`
- Namespace: `dify-k8s-lab`
- 业务入口：`/v1/chat-messages`

## 复现步骤

1. 部署 Dify，并确认 Chatflow 基线请求正常。
2. 对 `dify-k8s-api` 执行 Pod kill 或 container kill。
3. 在故障注入和 Pod 重建期间持续发送 Chatflow 请求。
4. 记录 HTTP 状态码、错误类型和恢复时间。

## 实际结果

- `container_kill`：3/3 次出现业务降级，观测到 HTTP `502`，随后恢复。
- `pod_kill`：部分重复出现 HTTP `502`；其中一次记录为 `business_unreachable`，另一次为恢复后的 `degraded`。
- 所有已完成 trial 最终均通过恢复和清理门禁。

## 预期结果

在单个 API 实例被替换期间，Service 应尽快摘除不 Ready 的 Pod，并由其他 Ready 实例处理请求；用户请求不应出现未经控制的 `502`。

## 建议排查方向

- API 容器的 `terminationGracePeriodSeconds` 和优雅退出处理。
- readiness probe 是否在进程停止前及时变为失败。
- Service endpoint 更新和 kube-proxy 转发延迟。
- Gunicorn/应用进程关闭、连接复用和 keep-alive 行为。
- 多副本场景下是否仍能复现。

## 验收标准

- 单 Pod 重启时不出现持续性 `502`。
- 若无法做到零错误，应定义并满足明确的错误率和恢复时间 SLO。
- readiness、Service endpoints 和应用日志能解释每个失败请求。

## 证据

本地证据：

- `.runs/dify-k8s-repeated-coverage-60hypotheses-verified-20260901/trials/018-pod_kill-dify-k8s-api-r02` 和 `r03`
- `.runs/dify-k8s-repeated-coverage-60hypotheses-verified-20260901/trials/019-container_kill-dify-k8s-api-r01`、`r02`、`r03`
