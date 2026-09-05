# 四项目 32+9 能力启动器只读验收报告

日期：2026-09-05

范围：Immich、ERPNext、Medusa、Rocket.Chat

结论：通过

## 结论摘要

统一 `CapabilityBootstrapper` 已在 `chaosatlas-apps` Kubernetes context 上完成真实只读验收。
四个项目均生成且只生成 32 个核心能力和 9 个 provisional 扩展能力的项目级聚合项；没有执行
故障注入，也没有创建、修改或删除 Kubernetes 资源。

“完成 41 项评估”不等于“41 项都可直接执行”。四项目当前相同的项目级结果为：

- `supported/E2`：1 项（`pod_kill`，来自既有外置 live 生命周期证据）；
- `canary_required/E1`：16 项（只读前置条件成立，但尚无本项目有效 live 证据）；
- `blocked/E0`：19 项（缺少隔离目标、控制契约、Agent 或 HTTPChaos 正向运行证据）；
- `inapplicable/E0`：5 项（当前没有适用的依赖边、安全 IO 路径或 JVM 目标）。

现有 `pod_kill` 仅达到 E2，即至少有一次有效生命周期证据；它还没有达到三次同参数独立复现所需的
E3，因此不能据此声称稳定复现了应用缺陷，也不能直接生成应用 Issue。

## 实际发现范围

| 项目 | 发现目标数 | 目标级能力记录数 | 项目级目录项 | 错误/警告 |
|---|---:|---:|---:|---:|
| Immich | 3 | 117 | 41 | 0/0 |
| ERPNext | 10 | 383 | 41 | 0/0 |
| Medusa | 4 | 155 | 41 | 0/0 |
| Rocket.Chat | 4 | 155 | 41 | 0/0 |

目标清单：

- Immich：`immich-server`、`immich-postgres`、`immich-valkey`；
- ERPNext：`erpnext-socketio`、`erpnext-nginx`、`erpnext-mariadb-sts`、`erpnext-gunicorn`、
  `erpnext-valkey-cache`、`erpnext-scheduler`、`erpnext-worker-l`、`erpnext-worker-d`、
  `erpnext-valkey-queue`、`erpnext-worker-s`；
- Medusa：`medusa-postgres`、`medusa-worker`、`medusa-backend`、`medusa-redis`；
- Rocket.Chat：`rocketchat-mongodb`、`rocketchat-nats`、`rocketchat-rocketchat`、
  `rocketchat-nats-box`。

## 41 项分类结果

### 已有 E2 证据

`pod_kill`

### 可进入后续小流量验证（E1）

`config_drift`、`config_reload`、`container_kill`、`dns_delay`、`dns_failure`、
`env_misconfiguration`、`network_bandwidth`、`network_corrupt`、`network_delay`、
`network_duplicate`、`network_loss`、`network_partition`、`replica_reduction`、
`rollout_pause`、`stress_cpu`、`stress_memory`。

这里的 E1 只表示“结构、目标和只读运行时前置已发现”，不代表已经授权执行，更不代表存在应用缺陷。

### 当前阻塞

`api_server_delay`、`business_dependency_unreachable`、`connection_reset`、`dependency_error`、
`disk_pressure`、`extension.connection_pool_exhaustion`、`extension.queue_backlog`、
`extension.runtime_pause`、`extension.time_offset`、`file_descriptor_exhaustion`、`http_abort`、
`http_delay`、`http_rate_limit`、`http_response_corrupt`、`http_status_error`、
`image_pull_failure`、`pod_unschedulable`、`process_exhaustion`、`secret_rotation`。

主要阻塞原因：

- HTTPChaos 类故障缺少 tproxy/ebtables 的正向运行证据；仅发现 CRD 不能证明实际注入链可用；
- 磁盘、文件描述符、进程、时间、队列和连接池类故障缺少显式 disposable target 或专用 Agent；
- Secret、镜像拉取和调度类故障需要 L2 一次性目标；
- API Server 延迟需要 L3 一次性集群；
- 原生 HTTP 控制故障缺少可验证、可清理的控制契约。

### 当前不适用

`extension.dependency_delay`、`extension.dependency_unreachable`、`extension.io_delay`、
`extension.io_error`、`extension.jvm_gc_pause`。

原因分别为：profile 尚未声明可解析到双方 Service selector 的业务依赖边；没有专用安全 IO 测试路径；
没有发现 JVM 目标。此状态是当前部署事实，不是永久不支持。

## 只读与数据安全证据

验收命令使用公共 `chaosatlas capabilities` CLI，输出到仓库外：

`C:\Users\12654\AppData\Local\ChaosAtlas\runs\four-app-capability-bootstrap-final-20260905-160337`

运行前后验证结果：

- CLI 退出码为 0，summary 状态为 `verified`；
- Chaos Mesh 八类故障资源均为 0，运行前后资源身份集合相同；
- 四个 namespace 的 Deployment、StatefulSet、DaemonSet、Pod UID 与容器重启次数相同；
- 输出中 `read_only=true`、`injection_performed=false`；
- 对输出 JSON 的密码、Token、Cookie、Authorization 与 Kubernetes Secret data 模式扫描命中 0；
- 仓库内没有生成本次运行产物。

运行时发现 Chaos Mesh 位于 `chaos-mesh` namespace，controller/daemon Ready；PodChaos、StressChaos、
NetworkChaos、DNSChaos、HTTPChaos、IOChaos、TimeChaos、JVMChaos CRD 均存在。HTTPChaos 仍按
fail-closed 原则保持阻塞，因为本子项目不执行会深入 daemon 的运行验证。

## 方法边界与下一阶段

本报告只完成子项目一“41 项能力自动发现”。它没有提前实施混合隔离环境、OracleBuilder、live
候选执行或全面故障测试。建议下一阶段优先建设 L1/L2 disposable target 与通用 Oracle 合成，然后从
16 个 E1 项中选择风险较低、因果边界清楚的 canary，按统一 RunEngine 的 baseline、inject、observe、
recover、cleanup、attestation 生命周期逐项把证据提升到 E2/E3。

本次只读验收没有发现可归因于四个上游应用的异常，因此没有形成可提交的上游 Issue 草稿。
