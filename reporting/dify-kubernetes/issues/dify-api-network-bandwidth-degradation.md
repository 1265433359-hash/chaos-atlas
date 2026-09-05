# Dify API 在网络带宽受限时返回 500 且延迟显著升高

**问题归属：** Dify 被测项目

**建议提交位置：** Dify 项目 Issue 区

**建议标签：** `bug`, `performance`, `availability`, `networking`

## 标题

`Dify API returns HTTP 500 and incurs multi-second latency under bandwidth degradation`

## 问题描述

当 API 所在工作负载遭遇网络带宽限制时，Chatflow 请求会返回 HTTP `500`，且请求延迟显著升高。当前行为没有表现为清晰的超时、重试或受控降级。

## 复现环境

- Dify: `1.17.0`
- Kubernetes context: `chaosatlas-dify`
- Namespace: `dify-k8s-lab`
- 业务入口：`/v1/chat-messages`

## 复现步骤

1. 确认 Chatflow 基线请求返回 HTTP `200`。
2. 对 `dify-k8s-api` 注入网络带宽限制。
3. 在限制期间发送相同的 Chatflow 请求。
4. 记录状态码、延迟和应用日志。

## 实际结果

`network_bandwidth` 共执行 3 次，3 次均出现业务降级：

- HTTP 状态码：`500`
- transport error：`true`
- 观测延迟：约 `7.9` 秒
- 故障清除后业务恢复

## 预期结果

网络变慢时，系统应通过明确的超时、重试、熔断或降级机制处理请求，不应将网络资源耗尽统一表现为未解释的 HTTP `500`。

## 建议排查方向

- API 到 Redis、数据库、Worker 和模型供应商的调用超时。
- 上游连接池、keep-alive 和请求体读取超时。
- Worker/API 间异步任务等待是否阻塞 HTTP 请求。
- 500 响应对应的 API、Nginx 和 Worker 日志。
- 网络受限时的客户端重试是否会放大请求压力。

## 验收标准

- 为关键下游调用定义可审计的 timeout 和 retry budget。
- 带宽受限时返回稳定、可识别的错误或降级响应。
- 不出现无界等待或未分类的 HTTP `500`。
- 在相同网络故障下，记录并满足目标 P95 延迟和错误率。

## 证据

本地证据目录：`.runs/dify-k8s-repeated-coverage-60hypotheses-verified-20260901/trials/025-network_bandwidth-dify-k8s-api-r01`、`r02`、`r03`
