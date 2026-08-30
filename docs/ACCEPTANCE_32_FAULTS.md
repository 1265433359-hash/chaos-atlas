# 32 类故障能力验收状态

更新时间：2026-08-28

## 当前结论

32 个产品级故障 ID 已冻结，三个项目的离线矩阵均可生成。当前 32 类均有显式编译器/执行器契约；新增 8 类已在 disposable resource-canary 项目完成一次项目级真实 live canary。7 类满足完整生命周期并返回 `live_completed`，1 类因共享控制面缺少 disposable-cluster mutator 返回 `environment_blocked`。未将缺少环境前置条件误报为 live 成功。

## 项目状态

| 项目 | 离线矩阵 | Live 状态 | 证据 |
| --- | --- | --- | --- |
| Nginx Kubernetes Ingress | 32 类 | `live_completed`（原有 16 类及 `disk_pressure`、`file_descriptor_exhaustion`、`process_exhaustion`） | 既有证据加 `.runs/resource-canary/disk-pressure-run-r3`、`.runs/resource-canary/file_descriptor_exhaustion-run-r3`、`.runs/resource-canary/process_exhaustion-run-r6` |
| Sock Shop | 32 类 | `live_completed`（network_delay、network_loss、stress_cpu、stress_memory、network_bandwidth、network_duplicate、network_corrupt、http_delay、http_abort、http_status_error） | 既有证据加 `.runs/acceptance-network-expansion-sock-bandwidth-20260827`、`.runs/acceptance-network-expansion-sock-duplicate-20260827`、`.runs/acceptance-network-expansion-sock-corrupt-20260827`、`.runs/acceptance-http-sock-delay-20260827-r2`、`.runs/acceptance-http-abort-sock-20260827/run-r2`、`.runs/acceptance-http-status-sock-20260827/run` |
| Online Boutique | 32 类 | `live_completed`（network_delay、container_kill、network_partition、stress_memory、network_bandwidth、network_duplicate、network_corrupt、http_delay、http_abort、http_status_error） | 既有证据加 `.runs/acceptance-network-expansion-online-bandwidth-20260827`、`.runs/acceptance-network-expansion-online-duplicate-20260827`、`.runs/acceptance-network-expansion-online-corrupt-20260827`、`.runs/acceptance-http-online-delay-20260827-r1`、`.runs/acceptance-http-abort-online-20260827/run`、`.runs/acceptance-http-status-online-20260827/run` |

## 能力口径

- 目录中的 `planned` 不进入 live 候选；只有具备执行器、业务 Oracle、恢复和清理契约的类型才可升级为 `implemented`。
- Nginx `pod_kill` 和 `network_loss` 已产生 `confirmed` RCA；`network_delay` 在 Nginx、Sock Shop 上保持 `bounded`，说明业务仍成功但延迟发生变化。
- Sock Shop `network_loss` 和 `network_delay`、Online Boutique `network_delay` 均完成恢复和清理；业务未退化的结果不得升级为 confirmed weakness。
- Nginx `container_kill`、Sock Shop `stress_cpu`/`stress_memory`、Online Boutique `container_kill`/`network_partition`/`stress_memory` 均完成真实注入、恢复和清理；未观察到业务退化的结果保持 `bounded`。
- 对 Nginx 请求 `network_partition` 时，候选生成阶段返回 `method_invalid` 且未注入，证明 profile 能力边界门禁生效；该类型尚未纳入 Nginx live 支持矩阵。
- 早期 Online Boutique 的 `environment_blocked` 运行是 PyYAML 加载错误（`yaml.safe_dump` 缺失），不是 Kubernetes 基线失败；后续运行已使用固定依赖路径并通过。
- `http_delay` 已在三个项目各完成一次真实 canary，均为 `response_observed`、RCA=`bounded`、清理=`verified`；结果说明 HTTP 延迟注入链路可用，但没有证据证明业务漏洞，因此知识状态保持 `provisional`。
- `http_abort` 和 `http_status_error` 已分别在 Sock Shop、Nginx 和 Online Boutique 完成真实 canary，均满足注入、观测、恢复和清理门槛，业务结果为 `response_observed`、RCA=`bounded`；因此两类故障升级为全局 `implemented`，三个项目 profile 均登记为 `supported`。
- 当前三个产品项目的 live 全量矩阵仍不能宣称通过；本次新增 8 类是在隔离的 `remaining-eight-canary` fixture 上完成项目级 live 验证，不能直接把结果外推到 Sock Shop、Online Boutique 或 Nginx。`replica_reduction` 的单副本缩容到 0 复现了业务不可达，属于 `availability_degraded`；资源 canary 在本次参数域下保持业务成功，属于 `response_observed` 防御结果。

## 新增 8 类项目级 live canary（2026-08-28）

测试项目为 `remaining-eight-canary`，工作负载为 `resource-canary`（2 副本），一次性 namespace 为 `chaosatlas-run-remaining08`，Kubernetes context 为 `chaosatlas-improvement`。每条运行均通过 profile onboarding、inventory、服务器部署检测、候选门禁和证据链编排；结果按真实执行状态登记：

| 故障 | Live 结果 | 业务/RCA 结论 | 清理/晋级 | 证据目录 |
| --- | --- | --- | --- | --- |
| `env_misconfiguration` | `live_completed` | `response_observed` / `bounded` | `verified` / 可生成运行证据 | `.runs/remaining-eight-live/env-misconfiguration` |
| `secret_rotation` | `live_completed` | `response_observed` / `bounded` | `verified` / 可生成运行证据 | `.runs/remaining-eight-live/secret-rotation` |
| `rollout_pause` | `live_completed` | `response_observed` / `bounded` | `verified` / 可生成运行证据 | `.runs/remaining-eight-live/rollout-pause` |
| `image_pull_failure` | `live_completed` | `response_observed` / `bounded` | `verified` / 可生成运行证据 | `.runs/remaining-eight-live/image-pull-failure` |
| `pod_unschedulable` | `live_completed` | `response_observed` / `bounded` | `verified` / 可生成运行证据 | `.runs/remaining-eight-live/pod-unschedulable` |
| `dns_failure` | `live_completed` | NetworkChaos fallback 注入确认，DNS 依赖探针连续超时，RCA=`bounded` / `availability_degraded` | attestation valid；清理 `verified`；知识 `provisional` | `.runs/remaining-eight-live-r8/dns-failure-live` |
| `dns_delay` | `live_completed` | NetworkChaos fallback 注入确认，DNS 延迟被机制证据观测，RCA=`bounded` / `response_observed` | attestation valid；清理 `verified`；知识 `provisional` | `.runs/remaining-eight-live-r8/dns-delay-live` |
| `api_server_delay` | `environment_blocked` | 共享 Minikube 没有 disposable control-plane mutator；未触碰控制面 | `promotion_allowed=false`；无控制面动作 | `.runs/remaining-eight-live/api-server-delay-live` |

DNS 两次运行均完成 capability probe，检查到两个目标 Pod 的 resolver 状态为只读，因此在 apply 前停止；`api_server_delay` 在执行器边界直接 fail-closed。上述三类不是漏洞成立、也不是业务防御成功，只是本环境的适用性/隔离能力结论。要把 DNS 登记为项目 `supported`，需要可写 resolver 或替代 DNS 注入器；要把 `api_server_delay` 登记为 `supported`，需要一次性控制面和专用 mutator。

补充验收：在恢复 Docker 权限并使用本机可读 Python 依赖后，DNS fallback 已完成真实 live 重跑。`dns_failure` 观察到 DNS 依赖业务不可达，`dns_delay` 观察到服务边界延迟；两次均满足 `attestation.valid=true`、`comparison_eligible=true`、RCA=`bounded`、清理 `verified`。证据目录为 `.runs/remaining-eight-live-r8/dns-failure-live` 和 `.runs/remaining-eight-live-r8/dns-delay-live`。

## 第一批矩阵检查点（2026-08-27）

- `scripts/run_network_dns_http_matrix.py` 已提供静态矩阵和显式审批的 live 批量入口。
- 静态运行 `.runs/network-dns-http-static-matrix` 产出 `batch_manifest.json`、`runtime_results.jsonl`、`rca_summary.json`、`cleanup_audit.json` 和 `batch_summary.json`。
- 最新矩阵产物为 `.runs/acceptance/32-fault-matrix-20260828.json`，三个项目共 96 条记录：Nginx 为 `19 supported / 0 planned / 13 inapplicable`，Sock Shop 和 Online Boutique 均为 `9 supported / 0 planned / 23 inapplicable`。`inapplicable` 表示全局执行器已存在但该项目尚未声明或缺少安全前置条件，不等于已完成 live 验收。
- 只有 `live_completed` 且 `cleanup=verified` 的子运行才会进入矩阵的策略反馈资格；`environment_blocked`、`method_invalid` 和未验证清理的结果保留在报告中但不会晋级。

## 矩阵接入 live canary（2026-08-27）

本轮在已授权 namespace 使用现有真实 executor 完成 3 条 canary，均满足 `live_completed`、attestation 有效、`phase6_audit=live_completed` 和清理 `verified`：

| 项目 | 故障 | 结果 | RCA | 证据 |
| --- | --- | --- | --- | --- |
| Nginx Kubernetes Ingress | `pod_kill` | `availability_degraded` | `confirmed` | `.runs/acceptance-matrix-live-nginx-20260827/projects/profile/runs/server-deployment-46f154f24e1db2da85adebbf-pod_kill` |
| Sock Shop | `network_delay` | `response_observed` | `bounded` | `.runs/acceptance-network-matrix-sock-network-delay-20260827` |
| Online Boutique | `network_delay` | `availability_degraded` | `confirmed` | `.runs/acceptance-network-matrix-online-network-delay-20260827` |

三个 namespace 的 `podchaos,networkchaos,dnschaos,httpchaos` 查询均无残留资源。DNS 故障及其余新增类型已具备 guarded executor；在缺少可写 resolver、disposable workload 或控制面 mutator 时按项目矩阵记录为 `inapplicable`，不会伪造 live 结论。

## 网络故障扩展验收（2026-08-27）

本轮在 Nginx Kubernetes Ingress、Sock Shop、Online Boutique 各执行 `network_bandwidth`、`network_duplicate`、`network_corrupt` 1 次，共 9 次。每次均满足：`summary.status=live_completed`、`finding_report.payload.attestation.valid=true`、`rca_report.payload.rca_status=bounded`、`cleanup_report.status=verified`、`phase6_audit.status=live_completed`。`bounded` 表示在本次强度和业务 Oracle 下证据边界稳定，不宣称已确认业务漏洞；9 次结果的 knowledge 状态均为 `provisional`，待跨版本重复后再晋级。

对应证据目录：

- Nginx：`.runs/acceptance-network-expansion-nginx-bandwidth-20260827`、`.runs/acceptance-network-expansion-nginx-duplicate-20260827`、`.runs/acceptance-network-expansion-nginx-corrupt-20260827`
- Sock Shop：`.runs/acceptance-network-expansion-sock-bandwidth-20260827`、`.runs/acceptance-network-expansion-sock-duplicate-20260827`、`.runs/acceptance-network-expansion-sock-corrupt-20260827`
- Online Boutique：`.runs/acceptance-network-expansion-online-bandwidth-20260827`、`.runs/acceptance-network-expansion-online-duplicate-20260827`、`.runs/acceptance-network-expansion-online-corrupt-20260827`

## 隔离 DNS canary（2026-08-27）

在一次性 namespace `chaosatlas-run-8e673b8e1705` 中完成了 Sock Shop fixture 的部署、server-side dry-run、业务基线和 `dns_failure` 注入尝试。Chaos Mesh CRD 创建成功，但 Chaos Daemon 在目标 Pod 内执行 DNS 修改时无法写入 `/etc/resolv.conf.chaos.bak`（`Read-only file system`），所以结果为 `injection_not_confirmed`，不是业务漏洞结论。系统随后删除 DNSChaos 和整个一次性 namespace，清理报告为 `verified`，全局无残留资源。证据目录：`.runs/acceptance-dns-isolated-sock-20260827/run`。

因此 `dns_failure`、`dns_delay` 虽已具备 guarded executor，但在当前只读 resolver 集群上记录为 `inapplicable`；要登记为项目 `supported`，需要在支持可写 DNS 配置或替代 DNS 注入机制的集群上重新完成同一生命周期验收。

## HTTP 延迟扩展验收（2026-08-27）

在 Nginx Kubernetes Ingress、Sock Shop、Online Boutique 各执行 `http_delay` 1 次，共 3 次。编译器生成的 `HTTPChaos` manifest 使用 CRD 支持的 `delay` 字段，不再写入非法的 `spec.action`。三次运行均满足：`summary.status=live_completed`、`finding_report.payload.attestation.valid=true`、`classify.payload.result=response_observed`、`rca_report.payload.rca_status=bounded`、`cleanup_report.status=verified`，且两个集群无 HTTPChaos 或临时 namespace 残留。知识状态均为 `provisional`，待不同强度或版本重复后再晋级。

对应证据目录：

- Nginx：`.runs/acceptance-http-nginx-delay-20260827-r1`
- Sock Shop：`.runs/acceptance-http-sock-delay-20260827-r2`
- Online Boutique：`.runs/acceptance-http-online-delay-20260827-r1`

## HTTP 中断与状态替换 canary（2026-08-27）

`http_abort` 和 `http_status_error` 均已在 Sock Shop 授权 namespace 以及 Nginx、Online Boutique 的一次性隔离 namespace 完成真实验证。6 次运行全部满足 `summary.status=live_completed`、attestation 有效、`cleanup_report.status=verified`，并在运行结束后确认无 HTTPChaos 残留。所有业务 Oracle 均保持成功，分类为 `response_observed`、RCA=`bounded`，不是业务漏洞结论；这些结果证明执行链路可复用，但不证明所有应用都具备同等防御能力。

对应证据目录：

- Sock Shop：`.runs/acceptance-http-abort-sock-20260827/run-r2`、`.runs/acceptance-http-status-sock-20260827/run`
- Nginx：`.runs/acceptance-http-abort-nginx-20260827/run-r2`、`.runs/acceptance-http-status-nginx-20260827/run`
- Online Boutique：`.runs/acceptance-http-abort-online-20260827/run`、`.runs/acceptance-http-status-online-20260827/run`

## HTTP 业务扩展 canary（2026-08-27）

本轮在 Sock Shop 和 Online Boutique 各执行 `http_response_corrupt`、`dependency_error`、`connection_reset` 1 次，共 6 条成功运行；另有 1 条 Sock Shop 首次明文 body 尝试因 admission webhook 要求 base64 而 `apply_failed`，未进入注入阶段。修复编译器后重跑成功，失败尝试保留为方法边界证据。

| 项目 | 故障 | 结果 | RCA | attestation | 清理 |
| --- | --- | --- | --- | --- | --- |
| Sock Shop | `http_response_corrupt` | `response_observed` | `bounded` | `valid` | `verified` |
| Sock Shop | `dependency_error` | `response_observed` | `bounded` | `valid` | `verified` |
| Sock Shop | `connection_reset` | `response_observed` | `bounded` | `valid` | `verified` |
| Online Boutique | `http_response_corrupt` | `response_observed` | `bounded` | `valid` | `verified` |
| Online Boutique | `dependency_error` | `response_observed` | `bounded` | `valid` | `verified` |
| Online Boutique | `connection_reset` | `response_observed` | `bounded` | `valid` | `verified` |

Nginx Kubernetes Ingress 在第二个 Minikube profile `chaosatlas-improvement`（context 同名）上完成同样三条 canary，证据目录为 `.runs/next-http-canary-20260827/nginx-http-response-corrupt`、`.runs/next-http-canary-20260827/nginx-dependency-error`、`.runs/next-http-canary-20260827/nginx-connection-reset`，结果均为 `live_completed`、`response_observed`、RCA=`bounded`、清理=`verified`。

证据目录：`.runs/next-http-canary-20260827/`。`http_response_corrupt` 的 body 已按 HTTPChaos admission 要求进行 base64 编码；`dependency_error` 当前表示 HTTP 服务边界的错误码替换，不等价于已定位到内部下游调用；`connection_reset` 当前表示 HTTP session abort 语义，不宣称内核 TCP RST。三类结果均未观察到业务退化，因此知识不得晋级为 confirmed weakness。

## 本批实施记录与下一批队列

本批已完成资源扩缩容和配置故障的三类 Kubernetes API executor 验收：

1. `replica_reduction`：Deployment 原始副本快照、受控缩容、业务观测和精确恢复均已验证。
2. `config_reload`：Deployment 模板 reload 标记、业务观测、原注解恢复均已验证。
3. `config_drift`：Deployment 模板 drift 标记、业务观测、原注解恢复均已验证。

三类资源故障已标记为全局 `implemented`，并在 Nginx profile 登记为 `supported`。它们均通过 resource-canary 隔离环境的真实注入、观测、恢复、清理和 attestation 验收；高风险项继续要求隔离环境和独立恢复证明。

资源故障的 native 协议、参数校验和 live executor 已完成：`disk_pressure` 只允许 `/tmp`、`/var/tmp` 或 `/dev/shm` 下的受控路径，文件描述符和进程数量均有上限；live executor 在没有 disposable namespace、容器能力探测和显式隔离批准时返回 `environment_blocked`，不会在共享 Minikube 上执行耗尽动作。

本轮补齐了资源故障接入底座：编译 manifest 现在携带 `targetSelector`，live 场景提供三类故障的受控默认参数，主 live 分派已识别 `ChaosAtlasNativeFault`。native executor 在注入前执行只读能力探测（`sh`、`sleep`、临时目录写入、文件创建工具及资源上限），清理后还会验证 marker 文件已删除；任一检查失败都停在 `environment_blocked` 或 `cleanup_unverified`，不会进入知识晋级。

同时加入 `DisposableNamespaceManager`，对高风险资源故障生成确定性的 `chaosatlas-run-<hash>` lease，创建时写入 owner/project/fault/seed 标签，销毁后必须确认 namespace 返回 `NotFound`。resource-canary 使用完整 shell/资源工具验证了三类故障：文件描述符和进程耗尽均保持业务 HTTP 200，说明该 canary 在当前边界下防御成功；三次运行的 cleanup 和 attestation 均通过。process canary 首次因 Debian `dash` 不支持 `ulimit -u` 被正确阻断，切换为 `bash` 并接受 `unlimited` 的受控上限语义后重新验收通过。

## 重新执行命令

```powershell
$repo = (Get-Location).Path
$archivedDeps = Join-Path (Split-Path $repo -Parent) 'ChaosAtlas-local-archive-20260826\.tmp-test-deps3'
$env:PYTHONPATH = ".;src;$archivedDeps"
python tools/chaosatlas.py run --profile projects/sock-shop/profile.json --mode live --approve-live --kube-context minikube --candidate-id server:deployment:sock-shop:front-end:network_loss --output .runs/acceptance-sock-live --seed 3206
python tools/chaosatlas.py run --profile projects/online-boutique/profile.json --mode live --approve-live --kube-context minikube --candidate-id server:deployment:online-boutique:frontend:network_delay --output .runs/acceptance-online-live --seed 3207
```

本地测试依赖统一放在 `ChaosAtlas-local-archive-20260826\.tmp-test-deps3`，不要在产品仓库根目录创建新的 `.tmp-*` 目录；运行证据仍写入被忽略的 `.runs/`。

两个项目都必须先确认节点 Ready、业务 Oracle 可访问、Chaos Mesh 组件就绪，再逐类执行 canary。

## HTTP 原生边界执行器实现（2026-08-27）

新增 `ChaosAtlasNativeHttpFault` 协议和 `NativeHttpFaultExecutor`，覆盖
`http_rate_limit` 与 `business_dependency_unreachable`。执行器要求目标
workload 提供 `/opt/chaosatlas/http-boundary-capability` 能力标记，并在
隔离 namespace 中通过 `/tmp/chaosatlas-http-control.json` 写入短生命周期
控制指令；观测结束后删除并验证控制文件，完整生命周期才可生成有效
attestation。

本阶段已完成编译器、live scenario defaults、能力注册、隔离门禁和
`workloads/http-boundary-canary` fixture。限流和依赖不可达 canary 已在
隔离 namespace 完成真实验证：分别产生 `rate_limit_observed` 与
`dependency_unreachable_observed`，两次均满足基线、注入、专属观测契约、
恢复探针、清理验证和有效 attestation；RCA 均为 `confirmed`，知识卡进入
`provisional`，并生成下一轮复现意图。因此这两个故障已从 `planned` 提升
为全局 `implemented`。这不等同于所有业务项目都支持，项目级支持仍需在
各自 workload 上完成同样的 live 生命周期验收。

部署 canary 前需在具备 Docker Desktop 权限的用户 PowerShell 中执行：

```powershell
docker --context desktop-linux build -t chaosatlas/http-boundary-canary:20260827 workloads/http-boundary-canary
minikube -p chaosatlas-improvement image load chaosatlas/http-boundary-canary:20260827
kubectl --context chaosatlas-improvement apply -f workloads/http-boundary-canary/k8s.yaml
kubectl --context chaosatlas-improvement -n chaosatlas-http-canary rollout status deployment/http-boundary-canary
```

## 剩余八类 guarded executor（2026-08-28）

本轮已将 `dns_failure`、`dns_delay`、`env_misconfiguration`、`secret_rotation`、`rollout_pause`、`image_pull_failure`、`pod_unschedulable` 和 `api_server_delay` 接入统一编排器。编译器会生成显式的 DNSChaos、Deployment/Secret 可逆补丁或控制面故障意图；Kubernetes API 执行器保存不可变快照并在 finally 路径执行精确恢复，Secret 证据只保留占位值摘要。DNS 在注入前探测 resolver 可写性，失败返回 `inapplicable`；调度故障要求 `chaosatlas-run-*` disposable namespace，API server delay 还要求 disposable cluster mutator，二者在共享 Minikube 上 fail-closed。本次 resource-canary live canary 已覆盖 8/8 类型，结果详见上表。

新增契约测试覆盖参数边界、Secret 脱敏、快照恢复、DNS 只读能力和控制面隔离门禁。当前这些类型已达到产品级 `implemented`（有 guarded executor）。resource-canary fixture 的 5 类已完成完整 live 生命周期；DNS 两类和 API server delay 的结果受环境前置条件限制，仍不得在三个产品 profile 中升级为 `supported`。

## 剩余三类 live 收尾状态（2026-08-28）

`dns_failure` 的 `r6` 运行已在隔离 namespace 内确认 NetworkChaos fallback 生效：DNS 依赖探针连续超时，随后 NetworkChaos 删除、Pod 恢复和清理均成功。该运行是在 attestation eligibility 修正前生成的旧产物，不能直接作为最终验收结论；必须用当前代码重新运行并确认 `attestation.valid=true` 后才可登记为 `live_completed`。

`dns_delay` 仍需要在同一隔离 workload 上用真实 DNS 依赖探针重跑。旧运行因 resolver 能力探测结果为不可适用而停止，不能生成漏洞或防御结论。

`api_server_delay` 已具备 fail-closed 控制面 mutator，并新增 `scripts/run_api_server_delay_disposable.py`：脚本会创建带 `chaosatlas-` 前缀的一次性 Minikube profile、加载 canary 镜像、部署隔离 namespace、让主编排器从唯一的 `api_server_delay` 候选自动选择并执行、保存 `.runs/` 审计，最后在 finally 路径销毁 profile。候选不再由脚本预计算，避免与真实 inventory node hash 不一致。
