# 四项目正式实验前准入报告

日期：2026-09-06。代码基线：`87f9c812cd378c5bce4ee8829f588c69d6f56370`。

## 结论

四个项目的统一 RunEngine、真实应用 L2 副本以及三项 Kubernetes API 故障 canary 已全部通过；每次运行都实际创建应用副本、完成故障注入、业务健康观测、恢复和命名空间清理。四项目当前 32 核心 + 9 provisional 矩阵均为：

`supported 4 / canary_required 16 / blocked 16 / inapplicable 5`。

这使每个项目相对最初的 19 项 blocked 真实解除 3 项：`secret_rotation`、`image_pull_failure`、`pod_unschedulable`。原有 `pod_kill` 继续由历史 E2 canary 支持。

当前尚不能请求最终事务审批，也不能开始正式业务实验。核对最新代码发现，四份现有待审契约是 v2，而真实事务入口和恢复账本执行的是 v3。v2 缺少 v3 要求的运行目标身份、完整所有权证明、精确 Secret 身份和阶段新鲜断言，批准后仍不能执行。另一个相关边界是：v3 当前把 Secret UID 固定在契约里，但 L2 每次创建的新 Secret UID 都不同；照现状无法用一份冻结契约重复运行多个可销毁副本。

## 已实现

- Rocket.Chat：真实 Rocket.Chat 8.6.1 + MongoDB replica set L2 蓝图；MongoDB 使用运行时生成的 keyfile，并修正副本集广告地址和卷权限。
- ERPNext：真实 ERPNext v16.34.1、MariaDB、两套 Valkey、Gunicorn、Nginx、Socket.IO、scheduler 和 worker；每次从空库安装合成站点。
- Immich：真实 Immich v2.6.3、PostgreSQL 和 Valkey；依赖等待门解决了此前重复出现的启动期 DNS 失败。
- 通用 Secret 生成从 URL-safe 字符串改为 256-bit 十六进制值，避免 Rocket.Chat/MongoDB keyfile 对 `_`、`-` 的格式不兼容。
- 四个 profile 均通过统一 IsolationManager 路由三项 KAPI L2 故障，没有新增项目专用 RunEngine。

## 已测试

- 隔离 profile/蓝图/运行时 Secret 专项测试通过。
- 最新全量测试：`498 passed in 14.92s`。
- `git diff --check` 通过。
- 四份 v2 历史草稿仍能通过其原 schema/hash 校验；这只证明历史文件未损坏，不代表它们符合 v3 实际执行协议。

## 真实证据支持

外置证据根：`%LOCALAPPDATA%/ChaosAtlas/runs`。

| 项目 | Secret rotation | Image pull failure | Pod unschedulable |
|---|---|---|---|
| Medusa | `isolated-run-medusa-secret-20260906-a` | `isolated-run-medusa-image-20260906-a` | `isolated-run-medusa-unsched-20260906-a` |
| Rocket.Chat | `isolated-run-rocketchat-secret-20260906-f` | `isolated-run-rocketchat-image-20260906-b` | `isolated-run-rocketchat-unsched-20260906-a` |
| ERPNext | `isolated-run-erpnext-secret-20260906-c` | `isolated-run-erpnext-image-20260906-a` | `isolated-run-erpnext-unsched-20260906-a` |
| Immich | `isolated-run-immich-secret-20260906-d` | `isolated-run-immich-image-20260906-a` | `isolated-run-immich-unsched-20260906-a` |

上述 12 次运行均满足：外层 `status=verified`、`prepare_state=ready`、`injection_performed=true`、内层统一 RunEngine `completed`、`cleanup_state=released`，并在事后查询中没有 `chaosatlas.dev/managed=true` 命名空间残留。

统一只读矩阵位于 `four-app-formal-readiness-20260906-a`；更新后的 P5 计划位于 `p5-formal-plan-20260906-a`。P5 仍保留 164 项总分母，当前没有正式事务、三次异常复现或 Issue 草稿。正式入口前的四应用只读验收位于 `four-app-formal-preflight-20260906-a`，结果为 4/4 workload Ready、4/4 健康 Oracle 通过、4/4 RunEngine dry-run 通过。

这些证据只支持“当前应用副本上的故障机制可执行并可清理”。每项新增能力只有单次 E2 canary，不支持稳定异常、应用缺陷或论文因果结论。

## 仍阻断

四项目共同剩余的 16 项 blocked 为：

- 资源边界：`disk_pressure`、`file_descriptor_exhaustion`、`process_exhaustion`；
- HTTP/依赖代理：`http_delay`、`http_abort`、`http_status_error`、`http_response_corrupt`、`http_rate_limit`、`dependency_error`、`connection_reset`、`business_dependency_unreachable`；
- 控制面：`api_server_delay`；
- provisional：`extension.time_offset`、`extension.queue_backlog`、`extension.connection_pool_exhaustion`、`extension.runtime_pause`。

其中 HTTP 组在当前 WSL2/Minikube 节点缺少可用的 `ebtables/broute` 正向链路证据；本轮按已确认边界没有重复失败注入。其他 16 项保留真实缺失的执行器、隔离或项目机制条件，不为清零矩阵而手工提升。

正式业务实验还缺：

1. 选择 v3 凭据绑定策略；
2. 按已授权的 2A/3A 初始化专用合成身份，并把凭据只保存到精确 Kubernetes Secret；
3. 生成可执行的四份 v3 契约、固定路径/文件哈希/语义哈希清单和新的集中审核包；
4. 为外置运行证据补一项明确的敏感材料泄漏验收记录。当前隔离计划会拒绝 profile/blueprint 中的静态敏感值，运行时 Secret 也未写入 plan/lease，但没有独立的运行后扫描结论，不能声称该门已完成。

## 历史 v2 文件身份（不可作为本次最终审批对象）

| 项目 | v2 contract SHA-256 | 文件 SHA-256 |
|---|---|---|
| Immich | `2ffc2b950af062e407be98c2d350fd7c7e7a621bdad179da669577a3c35cfd6d` | `d3aeec5758724fb241184eee7e667333a1e2eec50ea2e192b35fb46c0cbe4b2a` |
| Medusa | `d88dcdbd350affb5750c7b0bea7dae12dd347052c9145a99787531e616b0dd34` | `27273bbbe247159cac78468cb40ebe5f6fc7a560d814d1ca476d10466f60493e` |
| Rocket.Chat | `c7f5f39c37e75d5918f502781107c6ea221eee2459df4f1a4238056c7e76e5f1` | `69e443870a8a73c7f748d975bd6941dad793c82261ea8e84c6d3d151438d1bd0` |
| ERPNext | `7935aa99c15bb79c9cce9e492fa895ecbeeec61b6bd32959728b1556abc4c98f` | `f556c332f3d50e1c0001cab5998bacba64a79bfcd20a1a7ac6387fc48320ee11` |

这些文件继续保留为历史设计和审计输入；不得把先前对 v1 或一般方案的同意推导为 v3 的实际批准。

