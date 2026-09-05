# ChaosAtlas 恢复 attestation 可能受 Chaos Mesh 控制面状态延迟影响

**问题归属：** ChaosAtlas 测试框架（我们的项目）

**建议提交位置：** ChaosAtlas 项目 Issue 区

**建议标签：** `bug`, `testing`, `evidence`, `kubernetes`

## 标题

`Recovery attestation can report a timeout when the workload is healthy but Chaos Mesh status is delayed`

## 问题描述

当前恢复判断同时依赖 Chaos Mesh 注入对象的状态字段和工作负载/业务状态。本轮有一次 `stress_cpu` trial 在 180 秒恢复窗口内业务观察正常、资源删除成功，但 Chaos Mesh 对象的 `recoveredCount` 仍为 `0`，因此被判为 `recovery_timeout`。重新执行后通过。

这说明控制面状态延迟可能造成恢复误报，或者需要更清楚地区分“应用未恢复”和“Chaos Mesh 状态未收敛”。

## 实际结果

- 第一次 trial：`recovery.confirmed=false`
- Chaos Mesh 记录：`injectedCount=1`, `recoveredCount=0`
- 业务观察：HTTP `200`
- Cleanup：已确认删除
- 第二次 attempt：恢复和完整 attestation 通过

## 建议方案

- 将 Pod Ready、Deployment available replicas 和业务 oracle 作为恢复证据。
- 将 Chaos Mesh CR status 作为机制证据，而不是唯一恢复判据。
- 区分 `application_recovery_timeout` 与 `control_plane_status_timeout`。
- 在恢复窗口结束时保存最后一次资源、Pod 和业务状态快照。

## 验收标准

- 控制面状态延迟不会在应用已恢复时直接产生同一类业务恢复失败结论。
- 真正未恢复的故障仍会被可靠阻断，不能通过业务 200 单独放行。
- 最终报告明确指出恢复判定使用了哪些独立信号。

## 证据

原始失败 attempt：`.runs/dify-k8s-repeated-coverage-60hypotheses-verified-20260901/trials/003-stress_cpu-dify-k8s-agent-backend-r01/attempt-01`

补跑通过 attempt：`.runs/dify-k8s-repeated-coverage-60hypotheses-verified-20260901/trials/003-stress_cpu-dify-k8s-agent-backend-r01/attempt-02`
