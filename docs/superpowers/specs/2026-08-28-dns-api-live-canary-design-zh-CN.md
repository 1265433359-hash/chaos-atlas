# DNS 与 API Server Delay 真实 Live Canary 设计

日期：2026-08-28

## 目标

为 `dns_failure`、`dns_delay` 和 `api_server_delay` 补齐项目级真实 live canary，同时保持现有 fail-closed 安全边界：不修改共享控制面，不把环境阻断误报为业务漏洞，不在缺少恢复证据时晋级知识。

## 方案一：DNS 网络级回退

现有 DNSChaos 继续作为首选执行器。若目标 Pod 的 `/etc/resolv.conf` 不可写，执行器在同一隔离 namespace 内回退到 NetworkChaos：

- 解析 `kube-dns`/CoreDNS Service 及其端点；
- 仅允许目标 Pod 到 DNS Service 的 UDP/TCP 53 流量；
- `dns_failure` 使用丢弃/拒绝语义；
- `dns_delay` 使用受控延迟语义；
- mutation 必须带 namespace、selector、owner 和有限时长；
- 观测前确认目标应用确实发起 DNS 查询，观测后删除 mutation 并验证 DNS 恢复。

`resource-canary` 增加 DNS 依赖业务探针，避免仅访问本地 HTTP 接口导致 DNS 故障不可观测。只有基线、注入确认、DNS 结果、业务观测、恢复、清理和 attestation 全部满足时，结果才允许为 `live_completed`；否则保留 `inapplicable` 或 `environment_blocked`。

## 方案二：Disposable API Server Delay

`api_server_delay` 仅允许在一次性 Minikube 集群执行。新增控制面 mutator，实现 `ControlPlaneDelayExecutor` 的回调契约：

1. 创建唯一的 disposable Minikube profile 和 kubeconfig/context；
2. 保存控制面容器身份、网络接口和原始 qdisc 状态；
3. 只对 API Server 流量施加限定时长的 `tc netem delay`；
4. 通过 API 请求和控制器状态确认延迟生效；
5. 在 `finally` 路径恢复原始 qdisc，并验证 API Server 健康；
6. 销毁一次性集群，保存控制面快照、变更和恢复审计包。

共享 Minikube、没有 disposable cluster 标记、没有 mutator、恢复校验失败或集群销毁失败时，结果必须为 `environment_blocked`，不得执行下一步注入或知识晋级。

## 统一接口与证据

两种执行器都通过现有 live 编排器返回统一字段：`status`、`injection_confirmed`、`observation`、`recovery_confirmed`、`cleanup_confirmed`、`attestation` 和 `promotion_allowed`。DNS 结果属于业务数据面证据；API Server 结果属于 Kubernetes 控制面证据，两者分别生成 RCA 和清理审计，不互相替代。

## 测试与验收

- 单元测试：DNS fallback 选择、CoreDNS 端点校验、参数上限、API mutator fail-closed 和恢复失败处理；
- 离线测试：两类 DNS 和 API Server manifest、候选门禁和证据 schema；
- live 测试：隔离 resource-canary 完成 DNS 两类；一次性 Minikube 完成 API Server Delay；
- 每类至少保存一条完整运行证据；未满足完整生命周期的运行只记录阻断原因；
- 现有 32 类测试和全部回归测试必须继续通过。
