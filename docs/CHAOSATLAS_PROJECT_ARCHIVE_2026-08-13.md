# ChaosAtlas 项目阶段归档

归档日期：2026-08-13
分支：`remediation/2026-08-09-review`
归档时 HEAD：`84a751b`（本轮 P09 运行证据生成于 2026-08-13）

本文是当前阶段的项目级归档快照。它汇总已完成运行、静态 gate、环境阻断、
待人工审核和后续排队项目，不替代单次运行报告、原始日志或冻结协议。

## 1. 当前结论

ChaosAtlas 已形成一条可复核的测试节点中心证据链：

```text
真实输入 -> TestNode/局部影响子图 -> 静态与运行 gate
-> 基线 -> 有界 Chaos Mesh 注入 -> 业务/日志/事件/Trace 观测
-> 恢复 -> 删除 -> washout -> 保守解释 -> 人工审核
```

当前主动推进的方法只有两种：

1. `ChaosAtlas-full`：完整方法，允许使用经过边界审查的项目知识视图。
2. `ChaosAtlas-ablation`：完整方法消融，使用相同项目输入和运行契约，但不提供知识视图，
   且不接收运行时反馈。

`ChaosEater-full` 暂停。它的历史材料保留为冻结审计证据，但不进入当前候选池、
统计、知识反馈或方法优势结论。

## 2. Sock Shop 当前阶段结果

### 2.1 可执行结果

目录：

`artifacts/experiments/chaosatlas_sockshop_three_method/runtime_results/sock-shop/teacher-minikube-three-method-r1/`

两条 ChaosAtlas 运行均满足：

- `status=completed`
- baseline 通过
- 实际注入已确认
- 应用恢复已确认
- Chaos 资源删除且 `absent_confirmed=true`
- washout 稳定
- 全局无残留 Chaos 资源
- mutation SHA-256 与文件一致
- `human_review=pending`
- `knowledge_base_updated=false`

两臂使用同一个 `front-end` PodKill mutation。Sock Shop 的 `front-end` 有三个副本；
注入后两臂的业务请求均保持 HTTP 200，未确认该场景下的业务弱点。

### 2.2 解释边界

本轮只证明该有界 PodKill 场景下的业务响应和恢复行为，不能证明：

- 完整方法优于消融方法；
- 任一方法发现了新的业务弱点；
- 存在 Eureka、缓存、注册机制或其他具体根因；
- Sock Shop 已完成三方法 head-to-head。

`front-end` 与 `carts` 日志为空，`catalogue` 日志主要是健康检查，原生清单没有
tracing-server，因此 Zipkin 旁证不可用。具体根因保持“不支持推断”。

### 2.3 ChaosEater 状态

官方 ChaosEater 源码导入和本地 Ollama 初始化曾通过，但本机缺少 `skaffold` 可执行文件
和 `chaos-eater/k8sapi:1.0` 镜像；其间 Minikube API 也出现 TLS 超时，最终健康检查发现
部分 Sock Shop Pod 未 Ready。不得用 adapter 或历史 ChaosEater 输出冒充第三臂。

因此 Sock Shop 当前状态是：

```text
ChaosAtlas-full       completed
ChaosAtlas-ablation   completed
ChaosEater-full       environment_blocked
三方法正式对比        incomplete
```

## 3. P09 当前阶段结果

目录：

`artifacts/experiments/chaosatlas_10_projects/runtime_results/P09/teacher-minikube-two-arm-r4/`

P09 已完成两条主动方法臂，共 10 次正式 mutation 运行，`5 + 5`：

- 两臂 gate 和 10 个 server-side dry-run 全部通过；
- 10/10 报告 `status=completed`；
- 10/10 baseline、注入、恢复、删除、washout、协议校验和比较资格通过；
- mutation 与诊断 sidecar 的 SHA-256 均与文件实际值一致；
- 全局 `podchaos,networkchaos,stresschaos -A` 无残留；
- `human_review=pending`，没有写入知识库。

两臂覆盖相同的五类语义故障：API PodKill、Redis PodKill、API 延迟、
API 丢包和 API CPU stress。API PodKill 在两臂的 `/health` 观察窗口均出现
短暂连接失败，随后替换 Pod Ready 并稳定恢复。Redis PodKill 的 `/health`
单次观察仍为 200，但 worker 日志记录了 broker 连接丢失和 Redis 连接拒绝。
延迟、丢包和 CPU stress 的单次 `/health` 观察均为 200。

P09 当前只有 `/health` 健康 oracle，不是完整业务 workflow。因而本轮只支持
“API PodKill 可造成短暂健康端点中断并恢复”和“Redis PodKill 期间出现 worker
路径连接症状”这类有界结论，不支持业务弱点、优越性或具体根因结论。缩减 profile
没有 `tracing-server` Service，Zipkin 旁证对 10 次运行均为 `unavailable`。

详细审核包：

- `artifacts/experiments/chaosatlas_10_projects/runtime_results/P09/teacher-minikube-two-arm-r4/P09_TWO_ARM_REVIEW.md`
- `artifacts/experiments/chaosatlas_10_projects/runtime_results/P09/teacher-minikube-two-arm-r4/P09_TWO_ARM_REVIEW.json`

## 4. 已归档项目和证据等级

| 项目/轨道 | 当前状态 | 可支持的结论 |
|---|---|---|
| Train Ticket | runtime evidence archived | Station 网络延迟阶梯、客户端超时与服务端晚完成、CPU throttling 和恢复边界 |
| Online Boutique | runtime/statistical evidence archived | payment/shipping/email/productcatalog 的延迟、丢包、降级和探针竞争语义 |
| OpenTelemetry Demo | runtime evidence archived | 多语言调用链、Payment 延迟/丢包和 Jaeger span 观测 |
| P02 Spring Petclinic | 15/15 R3 evidence archived | api-gateway PodKill 业务失败；discovery-server 延迟 HTTP 500；RCA 审核仍 pending |
| Sock Shop | 两臂 completed，第三臂 blocked | 当前 front-end PodKill 场景未确认业务弱点；不构成三方法完成对比 |
| P08 Appsmith | 历史双臂 runtime pilot archived | KB/noKB 两臂 PodKill 均恢复；仅是单次、健康端点级描述性结果 |
| P09 Dify | 两臂 runtime completed，pending review | `/health` 级 API PodKill 中断/恢复和 Redis worker 连接症状；不支持业务弱点或具体根因 |
| P03 Saleor | static profile passed; authorized server dry-run pending | `P03-r6` 已有静态 profile、固定镜像摘要、资源边界和 oracle 合同；尚未进入授权集群会话 |
| P06 Directus | static profile passed; authorized server dry-run pending | `P06-r6` 已有静态 profile、固定镜像摘要、资源边界和 oracle 合同；尚未进入授权集群会话 |

所有结果都必须区分 `runtime_observed`、`static_only`、`environment_blocked`、
`not_reachable` 和 `pending_human_review`。静态候选、模型输出频次和传输成功不等于
业务弱点或根因证据。

## 5. 后续四项目执行队列

Sock Shop 已完成当前阶段的两臂描述性运行并归档，不再占用下一批队列。
后续四个项目按以下顺序推进，均只运行两条 ChaosAtlas 方法臂：

| 顺序 | 项目 | 当前 gate | 下一步 |
|---:|---|---|---|
| 1 | Online Boutique | static gate passed; authorized dry-run pending | `online-boutique-r3` 已完成 namespace 隔离、loadgenerator 排除、镜像 digest 和 PlaceOrder/frontend 契约重验；下一步仅在获准 namespace 会话中做 dry-run、双 baseline 和恢复/清理 rehearsal |
| 2 | OpenTelemetry Demo | static gate blocked; immutable image provenance missing | `opentelemetry-demo-r1` 已完成脱敏 manifest、ConfigMap materialization 和 PlaceOrder/trace contract；12 个镜像缺不可变 digest，不能进入运行 |
| 3 | Train Ticket | static gate blocked; dependencies and immutable image provenance missing | `train-ticket-r2` 已完成 namespace 重写、资源去重和 Station 双 oracle 合同；缺失依赖定义及六个镜像 digest，不能进入运行 |
| 4 | TeaStore | static-ready; source snapshot missing | 当前工作区没有固定源码快照；先恢复 exact commit 并重算本地哈希，再渲染 profile 和 bring-up |

机器可读队列见
`artifacts/experiments/chaosatlas_followup_four_projects_2026-08-13/queue_manifest.json`。
P08/P03/P06 的历史准备材料继续保留在十项目 ledger 中，但不作为本批四项目
的执行队列。每个项目必须先完成 baseline、server-side dry-run、健康检查、业务
oracle 和残留审计，只有 gate 通过后才允许生成/运行两条方法臂。每轮运行必须确认
注入、恢复、删除、全局无残留和 washout；报告保持 `human_review=pending`，不得
自动更新知识库。

## 5. 方法和污染边界

- full 与 ablation 使用字节级一致的项目输入、源码/镜像/拓扑哈希和业务 oracle。
- ablation 不读取同项目运行结果、不读取未来项目结果、不接收运行时反馈。
- 同一个项目的旧实验不能直接提供新方法的候选池、统计结果或方法结论。
- 历史 ChaosEater 结果不进入当前 ChaosAtlas 知识视图。
- 已测试项目可以复用部署清单、健康检查、业务 oracle、注入恢复脚本和采集工具，
  但必须使用新输出目录并重新建立 manifest。
- 任何 pending 审核材料都不能自动写入知识库。

## 6. 当前不能写入论文的结论

以下结论目前不能作为正式 superiority claim：

1. ChaosAtlas full 优于 ablation；
2. ChaosAtlas 优于 ChaosEater；
3. 任何项目上的方法发现率或根因率具有跨项目统计显著性；
4. HTTP 200 自动等于系统有防御；
5. 没有日志/Trace 时可以猜测 Eureka、缓存、注册或服务发现机制。

当前最稳妥的项目级结论是：ChaosAtlas 已具备可审计的测试节点中心运行闭环，
并在多个项目上积累了有界业务响应、延迟、恢复、清理和观测证据；正式方法对比
仍需在统一输入、独立 oracle、项目级聚类统计和人工审核完成后再下结论。

## 7. 归档入口

- 项目总览：[docs/PROJECT_SUMMARY.md](PROJECT_SUMMARY.md)
- 实验目录：[docs/EXPERIMENT_CATALOG.md](EXPERIMENT_CATALOG.md)
- 归档规则：[docs/ARCHIVE_MAP.md](ARCHIVE_MAP.md)
- 机器索引：`artifacts/experiments/CHAOSATLAS_ARCHIVE_INDEX_2026-08-13.json`
- Sock Shop 审核：`artifacts/experiments/chaosatlas_sockshop_three_method/runtime_results/sock-shop/teacher-minikube-three-method-r1/SOCK_SHOP_THREE_METHOD_REVIEW.json`
- P09 gate：`artifacts/experiments/chaosatlas_10_projects/runtime_profiles/P09-r5/gate-summary.json`

本归档没有读取或写入任何 API key，没有执行模型调用，没有修改 Docker/Minikube/
Chaos Mesh，也没有改变知识库状态。
