# 四项目 19 项 blocked 解锁推进记录

日期：2026-09-06

## 结论

本轮没有手工把能力改写为 `supported`。新增了统一的外部 runtime evidence 接口，并执行了真实 canary；`api_server_delay` 已在平台级别从 `blocked` 进入 `canary_required`。随后把可销毁环境的申请、绑定、执行和释放下沉到统一 RunEngine；Medusa 的 `secret_rotation`、`image_pull_failure`、`pod_unschedulable` 已由真实证据索引从 `blocked` 提升为 `supported/E2`。该等级表示存在有效运行生命周期证据，不表示已经得到三次稳定复现或业务缺陷结论。

## 已实现

- `probe_runtime_backends` 支持读取外部 `httpchaos-runtime-evidence.json`。
- 只有同一 Kubernetes context、生命周期 attestation 有效且故障效果被业务样本确认时，`httpchaos_runtime_verified` 才会变为 true。
- `chaosatlas capabilities` 新增 `--runtime-evidence`，可把真实 canary 证据接入统一 capability bootstrap；缺失、schema 错误或 context 不匹配均保持 false。
- 新增 `scripts/run_httpchaos_runtime_canary.py`，复用统一 `KubernetesLifecycleExecutor`，生成 namespace/selector/mode 受限的 HTTPChaos canary 和可审查证据。
- `run_api_server_delay_disposable.py` 支持本地镜像、期望响应体和容器 command/args，便于在无外网时进行真实 disposable control-plane 验收。
- RunEngine 机制证据文件使用确定性短哈希，修复 Windows 长路径导致 `method_invalid` 的问题。
- RunEngine 的候选输出目录增加确定性短路径回退，修复外置运行根较长时子阶段原子文件仍可能超过 Windows 路径预算的问题。
- `KubernetesApiFaultExecutor` 不再把 `kubectl patch` 成功直接当作注入成功：Secret 必须由 API 读回新值，镜像故障必须观察到 `ErrImagePull/ImagePullBackOff`，不可调度必须观察到 `PodScheduled=False/Unschedulable`。
- Kubernetes API 故障恢复除资源快照一致外，还必须通过恢复后的业务探针；失败时 attestation 无效。
- 新增 `scripts/run_kubernetes_api_disposable_canary.py`，通过统一的 `IsolationManager -> RunEngine -> Oracle -> attestation` 路径，在一个 L3 父集群中为每项故障创建独立的完整 Medusa L2 副本，逐项释放子租约并最终释放父集群。
- Minikube 隔离 Provider 支持经过严格校验、无凭据的容器运行时代理参数，用于可销毁节点拉取系统镜像；代理地址不会写入项目 profile。
- runtime preflight 只在所选故障确实使用 Chaos Mesh 时要求其 CRD，原生 Kubernetes API 故障不再被错误阻断。
- HTTPChaos daemon 前置探针使用实际发现的 Chaos Mesh namespace，不再硬编码 `chaos-testing`。
- `chaosatlas run` 新增显式 `--isolation-fault`、`--approve-isolation` 和隔离 TTL：RunEngine 根据项目 `fault_routes` 解析本地 blueprint，申请拥有所有权的租约，生成只绑定该租约的 runtime profile，执行一个候选，并在 `finally` 中验证释放。
- 普通 live profile 仍只暴露原有安全故障；隔离故障只有在显式双重批准后才会进入候选发现。一次租约只允许一个候选，清理失败会把整体状态降为 `partial/failed`。
- `secret_rotation` 执行器现在与镜像拉取失败、不可调度一致，强制要求 `ca-l1-*`/`ca-l2-*` 等拥有所有权的隔离命名空间。
- Medusa 增加无静态凭据的 L2 blueprint；数据库、JWT 和 cookie 值在运行时生成，数据卷为 `emptyDir`，每次运行均从合成空数据开始。

## 已测试

最终完整仓库测试：`491 passed in 14.85s`。覆盖故障效果确认、负向 fail-closed、恢复业务探针、短路径、Minikube 代理校验、preflight 路由、HTTPChaos namespace、disposable canary 汇总、blueprint 路径边界、双重批准、单候选限制和清理失败降级。

## 真实证据

### HTTPChaos（Medusa）

证据目录：`%LOCALAPPDATA%/ChaosAtlas/runs/httpchaos-medusa-canary-20260906-c`

- CRD、Chaos Mesh controller/daemon、目标 Pod、selector、端口均通过；
- 修复 namespace 探针后，Chaos Daemon 内部诊断确认 `xt_TPROXY` 和 iptables mangle 可用，但 WSL2 内核缺少 ebtables/broute；
- Chaos Daemon 的 tproxy/ebtables 正向探针失败，原因是 `http_tproxy_positive_evidence_missing`；
- 未执行 `kubectl apply` 注入，`injection_performed=false`；
- 因此 6 项 HTTPChaos 仍为 blocked。这已从“探针代码错误”收敛为当前 WSL2 内核能力不足，不能用 CRD 存在替代运行证据。

### API Server delay（disposable Minikube）

证据目录：`%LOCALAPPDATA%/ChaosAtlas/runs/api-delay-canary-20260906-i`

- disposable Minikube 启动、busybox canary 部署、基线、API 网络延迟、恢复、qdisc 清理和 profile 删除均有真实记录；
- 底层 `live-*.json` attestation 为 valid，观察到延迟样本约 309--411 ms；
- 修复路径后统一 RunEngine 状态为 `live_completed`，基线、注入、观察、恢复和清理均有效；
- 平台级证据已接入 capability bootstrap。四个项目均由 `blocked 19 / canary_required 17 / inapplicable 5` 变为 `blocked 18 / canary_required 18 / inapplicable 5`；项目级业务 canary 仍待执行。

### Kubernetes API L2 故障（disposable Medusa）

证据目录：

- `%LOCALAPPDATA%/ChaosAtlas/runs/kapi-c2`
- `%LOCALAPPDATA%/ChaosAtlas/runs/kapi-c3`

真实边界为一个 IsolationManager 所有的 disposable L3 Minikube 父集群；每项故障使用重新创建的完整 Medusa、PostgreSQL、Redis 和 migration L2 子副本。

| 故障 | 运行机制证据 | 注入 | 恢复 | 清理 |
| --- | --- | --- | --- | --- |
| `secret_rotation` | `secret_value_reflected` | 已确认 | 快照与健康探针通过 | 子租约和父租约均 released |
| `image_pull_failure` | `pod_image_pull_waiting` | 已观察 `ErrImagePull/ImagePullBackOff` | 快照与健康探针通过 | 子租约和父租约均 released |
| `pod_unschedulable` | `pod_scheduling_condition` | 已观察 `PodScheduled=False/Unschedulable` | 快照与健康探针通过 | 子租约和父租约均 released |

三项统一 RunEngine 状态均为 `live_completed`，lifecycle attestation 均为 valid，敏感信息扫描无命中。可确认的范围仅为“Medusa 可销毁副本上的故障机制、健康观察、恢复与清理”；本轮没有执行业务事务、没有三次独立复现，也没有形成应用缺陷结论。

早期真实尝试留下了两类负向诊断：Calico 镜像和 kindnet 镜像在当前网络下无法直接拉取，完整副本未 Ready；相应父子资源均已释放。后续使用受校验的无凭据节点代理后才取得上述正向证据，失败尝试不计为能力通过。

### 统一 RunEngine 自动隔离（Medusa）

证据目录：

- `%LOCALAPPDATA%/ChaosAtlas/runs/isolated-run-medusa-secret-20260906-a`
- `%LOCALAPPDATA%/ChaosAtlas/runs/isolated-run-medusa-image-20260906-a`
- `%LOCALAPPDATA%/ChaosAtlas/runs/isolated-run-medusa-unsched-20260906-a`

这三次不是专用验收脚本外层拼接，而是直接调用统一 `chaosatlas run --mode live --isolation-fault ... --approve-isolation`。每次均独立创建完整 Medusa L2，RunEngine 状态为 `completed`，隔离 lifecycle 为 `verified`，具体机制分别为 `secret_value_reflected`、`pod_image_pull_waiting`、`pod_scheduling_condition`，恢复和故障清理为 true，租约为 released，事后 Kubernetes 查询确认三个命名空间均 NotFound，且集群中无 `chaosatlas.dev/managed=true` 的残留命名空间。

只读矩阵重算目录：`%LOCALAPPDATA%/ChaosAtlas/runs/capability-medusa-isolated-20260906-a`

- Medusa 当前汇总为 `blocked 15 / canary_required 17 / inapplicable 5 / supported 4`；
- 相比上一轮 `blocked 18 / canary_required 18 / inapplicable 5 / supported 0`，三项 Kubernetes API L2 能力已由真实外部证据提升；原有 `pod_kill` 也由历史证据保持 supported；
- 三项故障的 target 级证据均为 E2，但 `stable_reproduction_count` 为 1，Secret rotation 为 2，尚未达到三次稳定复现门槛。

## 当前仍 blocked 的主要原因

1. HTTPChaos 6 项：需要同 context 的 tproxy/ebtables 正向注入证据；
2. native HTTP 2 项：四项目没有已验证的 native HTTP 控制契约；
3. native resource 3 项：没有项目级隔离资源 Agent；
4. Secret rotation、image pull failure、pod unschedulable：Medusa 已完成 RunEngine 自动申请、绑定和释放并进入 `supported/E2`；Immich、ERPNext、Rocket.Chat 仍缺少相应真实副本 blueprint 与运行证据；
5. extension time/queue/pool/runtime：缺少对应 disposable Agent 或控制契约；
6. API Server delay：平台级已解除 blocked，四个项目仍是 `canary_required`，需要各项目业务路径 canary 才能进一步提升证据等级。

## 证据边界

本报告区分“代码接口已实现”“测试通过”“真实运行证据存在”。未满足完整生命周期、事务业务效果、独立复现和清理证明的能力继续保持 blocked 或 canary_required；本轮没有使用模拟结果解锁矩阵，也没有把一次健康 canary 当作稳定业务结论。

## 下一步

1. 为 Immich、ERPNext、Rocket.Chat 生成同等真实副本 blueprint，并分别完成三项 Kubernetes API 机制 canary；
2. 在四项目已批准的事务契约上执行 baseline、注入期、恢复期 Oracle，区分“机制 supported”和“业务结论已验证”；
3. 继续为 native resource、native HTTP 和 extension Agent 建立同样的自动隔离 route；
4. HTTPChaos 改在具备 ebtables/broute 的 Linux 节点或远程测试集群验收，当前 WSL2 环境不继续做无效重试。
