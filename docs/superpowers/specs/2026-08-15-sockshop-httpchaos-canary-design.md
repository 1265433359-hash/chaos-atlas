# Sock Shop HTTPChaos Canary 设计

## 目标

判断当前 Minikube/WSL2 内核是否已经具备 Chaos Mesh HTTPChaos 的完整透明代理能力，并据此重新分类尚未验证的 28 个 HTTP fault family。

## 证据边界

- 历史失败证明旧 WSL2 内核缺少 ebtables broute/nat 能力，但不能直接代表当前内核。
- CRD Established、组件 Ready 和 server-side dry-run 只证明资源可被 Kubernetes 接受，不证明故障已经注入。
- 当前只读探针必须确认 ebtables broute/nat、xt_TPROXY 和 iptables mangle 可访问。
- 最终平台可用结论必须来自一次真实 canary：基线通过、HTTPChaos 实际注入、业务影响被 oracle 观察、资源恢复和删除、washout 稳定、全局无残留。

## Canary

- namespace：`chaosatlas-sock-shop`
- target：`catalogue` Pod，标签 `name=catalogue`
- protocol：HTTP，端口 `80`，路径 `/catalogue`
- action：Response abort
- mode：`one`
- duration：`30s`
- replicate：先执行 1 次平台 canary；成功后才允许正式 family 批次按每个 mutation 两次执行。

## 失败处理

- 如果资源未进入实际 injected 状态、oracle 无变化或出现 tproxy/ebtables 错误，平台保持 blocked。
- 无论成功失败都删除 HTTPChaos，并检查 namespace 与全局 Chaos 资源为空。
- cleanup 或 washout 失败时停止，不执行第二个 HTTPChaos。
- 不通过删除 finalizer 掩盖正常清理失败；只有资源已无法由控制器回收且完成证据保全后，才单独审计人工恢复。

## 剩余 28 个 family 的后续分类

- 端口 80 的 HTTP 服务候选继续做服务路径语义 gate。
- `front-end` 使用真实端口 8079，并绑定实际 HTTP 路径。
- MongoDB、MySQL、Redis 和 RabbitMQ 业务协议不是 HTTP；对应候选标记 `not_applicable`，不计入 runtime 分母。
- 不再使用统一硬编码的 `port: 80`、`path: /catalogue` 代表所有服务。

## 审核状态

`human_review=pending`，`knowledge_base_updated=false`。
