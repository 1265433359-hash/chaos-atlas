# Sock Shop 三方法阶段结果复盘

更新时间：2026-08-16

状态：YAML15 Ablation 已完成，人工审核 pending

人工审核：`pending`

知识库更新：`false`

本文只整理当前可回链证据，不重跑实验。预选池、same-pool、早期 pilot 和
`ChaosEater-adapter` 不进入本次结果。

## 1. 当前结论

当前可以确认三件事：

1. ChaosAtlas-full 的 114 个去重 fault family 已全部经过静态适用性处理。96 个
   进入 runtime cohort，其中 88 个完成两次真实注入，得到 15 个稳定弱点
   family、3 个不稳定 family 和 70 个未观察到业务弱点的 family；8 个 DNSChaos
   在注入前被平台 gate 阻断。其余 18 个被静态 gate 拒绝，不是漏评估。
2. 当前最终版 YAML15 ChaosAtlas-ablation 生成 458 个原始假设，独立去重为 51 个
   family；46 个通过 gate 并完成两次注入，确认 9 个稳定弱点、0 个不稳定结果和
   37 个未观察到业务影响的 family。旧版 `12 个假设/2 个弱点` 仅作 superseded
   历史记录，不进入当前统计。
3. ChaosEater 当前阶段摘要记录 2 类可用性弱点：front-end 单副本单点故障，
   以及 readiness/recovery 过慢。它们与 Full 的 15 个业务 mutation family
   不在同一测量层，不能直接相加或硬算覆盖率。

因此，`15 vs 9 vs 2` 是当前不同测量层的问题集合盘点，不是公平的胜负统计。
YAML15 Ablation 已完成并替换旧版 Ablation 一栏；Full 原始证据没有重跑。

## 2. 统一计数口径

| 名称 | 定义 |
|---|---|
| fault family | 由冻结归一化规则得到的假设族；Full 共 114 个 |
| runtime cohort | 通过静态编译/适用性筛选，进入既有完成证据或后续 runtime 计划 |
| 已注入 | 两个 replicate 都完成 baseline、注入、恢复、cleanup 和 washout |
| 稳定弱点 | gate 通过且两个 replicate 都是 `weakness_observed` |
| 不稳定 | 两个 replicate 只有一次是 `weakness_observed` |
| 未观察到弱点 | 两个 replicate 都是 `no_business_impact_observed` |
| 问题面 | 合并同一目标与故障作用的直接、定时或误命名重复 family 后的现象集合 |

稳定弱点率以“gate 通过且完成完整生命周期的 mutation”为分母。platform-blocked
不放入弱点率分母，也不算系统防御成功。

## 3. ChaosAtlas-full 结果

### 3.1 总体结果

| 指标 | 数量 | 占比 |
|---|---:|---:|
| 去重 fault family | 114 | 100.00% |
| 已完成静态适用性处理 | 114 | 100.00% |
| 进入 runtime cohort | 96 | 84.21% |
| 完成两次真实注入 | 88 | 77.19% |
| platform-blocked DNSChaos | 8 | 7.02% |
| 静态 gate 拒绝 | 18 | 15.79% |
| 稳定弱点 | 15 | 17.05%（15/88） |
| 不稳定 | 3 | 3.41%（3/88） |
| 两次均未观察到弱点 | 70 | 79.55%（70/88） |

88 个已注入 family 对应 176 份 completed replicate。结构化复核确认这些报告的
baseline、injected、recovered、cleanup absent 和 washout stable 字段全部通过。

### 3.2 为什么 18 个没有注入

这 18 个不是因为时间不够而遗漏，而是在 route-aware runtime plan 中明确
`gate.status=failed`：

| 类型 | 数量 | 目标 | 不注入原因 |
|---|---:|---|---|
| HTTPChaos abort | 6 | carts-db、catalogue-db、orders-db、rabbitmq、session-db、user-db | 目标是 MySQL/MongoDB/RabbitMQ/Redis 等非 HTTP 接口，没有可信 HTTP port/path |
| HTTPChaos delay | 6 | 同上 | 同上；强行使用 port 80 会形成无效注入 |
| DNSChaos error | 6 | 同上 | 原假设把下游数据库/中间件写成 selector 目标，缺少“发起查询的源 Pod -> 下游域名”的正确调用链映射 |

其中 12 个 HTTPChaos 不应该补跑原 YAML；合理替代是按真实协议使用
NetworkChaos delay/loss/partition。6 个 DNSChaos 可以重建为 source-aware mutation，
例如 `catalogue -> catalogue-db`、`orders -> orders-db`、`user -> user-db`，但当前
Minikube 的 DNSChaos canary 已因 Chaos Daemon 无法备份只读 `/etc/resolv.conf`
而 platform-blocked。在平台条件改变前重复运行仍会得到同一个环境阻断，不会产生
业务结论。

### 3.3 按故障大类

| 大类 | 已注入 family | 稳定 | 不稳定 | 未观察到弱点 | 稳定率 |
|---|---:|---:|---:|---:|---:|
| Pod disruption | 17 | 5 | 0 | 12 | 29.41% |
| Network degradation | 13 | 2 | 2 | 9 | 15.38% |
| Resource pressure | 28 | 1 | 0 | 27 | 3.57% |
| Protocol/HTTP fault | 16 | 3 | 0 | 13 | 18.75% |
| Composite/scheduled fault | 14 | 4 | 1 | 9 | 28.57% |

### 3.4 15 个稳定 family

| # | family | 实际故障 | 首要业务现象 |
|---:|---|---|---|
| 1 | `net-loss-frontend-catalogue-002` | catalogue 网络丢包 | catalogue timeout |
| 2 | `net-partition-frontend-catalogue-003` | catalogue 网络分区 | catalogue timeout |
| 3 | `sock-http-abort-catalogue` | catalogue HTTP response abort | `/catalogue` HTTP 500 |
| 4 | `sock-http-abort-orders` | orders HTTP response abort | `/orders` HTTP 500 |
| 5 | `sock-http-abort-user` | user/login HTTP response abort | login HTTP 401 |
| 6 | `sock-mem-orders-007` | orders memory stress | `/orders` HTTP 500 |
| 7 | `sock-pod-failure-catalogue-002` | 实际 YAML 为 catalogue PodKill | catalogue 500/timeout |
| 8 | `sock-pod-kill-catalogue-024` | catalogue PodKill | catalogue timeout |
| 9 | `sock-pod-kill-catalogue-db-011` | catalogue-db PodKill | catalogue body contract 失败 |
| 10 | `sock-pod-kill-orders-db-012` | orders-db PodKill | orders 连接被关闭 |
| 11 | `sock-pod-kill-user-008` | user PodKill | login 401/timeout |
| 12 | `sock-sched-delay-catalogue-db-catalogue` | 定时触发 catalogue-db PodKill | catalogue body contract 失败 |
| 13 | `sock-sched-delay-catalogue-frontend` | 定时触发 catalogue PodKill | `/catalogue` HTTP 500 |
| 14 | `sock-sched-delay-orders-db-orders` | 定时触发 orders-db PodKill | orders 连接被关闭 |
| 15 | `sock-sched-delay-user-frontend` | 定时触发 user PodKill | login 401/timeout |

四个 `sock-sched-delay-*` 名称中的 `delay` 是历史 family 标签；YAML 的真实嵌套
action 是 `PodChaos/pod-kill`。`sock-pod-failure-catalogue-002` 也实际编译为
`pod-kill`。按“目标 + 故障作用”合并直接/定时重复后，15 个 family 对应 10 个
问题面：catalogue 丢包、catalogue 分区、catalogue/orders/user HTTP abort、orders
内存压力，以及 catalogue、catalogue-db、orders-db、user 的 PodKill 敏感性。

### 3.5 三个不稳定 family

- `net-delay-frontend-catalogue-001`
- `net-loss-frontend-orders-013`
- `sock-sched-delay-user-db-frontend`

它们只在一个 replicate 中出现业务失败，不算稳定真实弱点。

## 4. 当前 ChaosAtlas-ablation 结果

旧版 2/11 结果已被 YAML15 协议替换，不与新分母叠加。新版向 Ablation 提供五类
明确标注的真实 YAML，每类 3 份；不提供知识库、Full 假设、置信度、Full 停止轨迹
或 Sock Shop 调用链证据。模型在 1419.047 秒硬上限内于 734.188 秒自然停止。

458 个原始假设独立去重为 51 个 family，46 个通过 gate 并各执行两次。92 份报告
全部 completed，得到 9 个稳定弱点、0 个不稳定和 37 个 no-impact：

| 假设 | 故障 | 结果 | Full 稳定问题面覆盖 |
|---|---|---|---|
| `hyp-003` | user PodKill | 2/2 | 是 |
| `hyp-006` | orders-db PodKill | 2/2 | 是 |
| `hyp-008` | catalogue-db PodKill | 2/2 | 是 |
| `hyp-014` | catalogue HTTP abort | 2/2 | 是 |
| `hyp-018` | user 500ms delay | 2/2 | 否 |
| `hyp-020` | orders HTTP abort | 2/2 | 是 |
| `hyp-021` | user HTTP abort | 2/2 | 是 |
| `hyp-030` | catalogue PodKill | 2/2 | 是 |
| `hyp-065` | orders memory pressure | 2/2 | 是 |

稳定率为 19.57%（9/46）。5 个数据库 HTTP abort 因目标没有可信 HTTP 接口而被
编译 gate 阻断，没有注入。正式审核保持 `human_review=pending`，没有更新知识库。

## 5. ChaosEater 阶段结果

当前讨论采用的五次原生复现摘要为：4 个场景假设、8 个稳态假设、12 个可执行
初始故障假设、2 个唯一弱点：

1. front-end 单副本导致单点故障；
2. readiness/recovery 延迟过长，导致故障恢复慢。

仓库现有原生 cycle 文件可直接回链到 front-end 可用率 91.11%（低于 99%）和
单副本配置；ChaosAtlas 的 availability 轨道也记录了 front-end PodKill 后
Ready 1 -> 0 及约 130 秒恢复。但五次复现的统一机器 manifest 尚未在当前仓库中
找到，因此 `2` 暂作为阶段摘要，不进入与 Full/Ablation 的正式统计检验。

## 6. 覆盖关系

| 比较 | 当前能说的结论 |
|---|---|
| Full vs Ablation | 按问题面比较重合 8 个；Full 覆盖 Ablation 8/9，Ablation 覆盖 Full 8/10 |
| Full 15-family vs ChaosEater | 不能直接声称覆盖；Full 15 个是业务 oracle mutation，ChaosEater 2 个是 availability/readiness 层 |
| ChaosAtlas 整体能力 vs ChaosEater | ChaosAtlas 的独立 availability 轨道有对应现象，但实验在已知 ChaosEater 结果后设计，存在确认偏误，不能写成双盲独立发现 |

## 7. 结果说明

当前结果说明 Full 的知识增强方法能够提出并验证更广的故障类型，尤其覆盖网络、
HTTP、资源、Pod 和定时复合故障。新版 Ablation 也发现了 9 个稳定问题面，其中
8 个与 Full 重合，并发现 Full 稳定集合未覆盖的 user 500ms delay。但这不能证明
任一方法在一般条件下必然优于另一方法，因为：

- Full 与当前 Ablation 的候选数和生成轨迹不同；
- ChaosEater 使用不同稳态和测量层；
- 15 个稳定 family 中存在同一问题面的直接/定时重复；
- 18 个 Full family 被静态适用性 gate 拒绝，另有 8 个 route-aware DNS family
  被当前平台阻断；
- 新版 Ablation 的 5 个数据库 HTTP abort 也被静态 gate 阻断。

Full `15/88` 与 Ablation `9/46` 的 Fisher 双侧精确检验 `p=0.8132`，95% 置信区间
高度重叠。最稳妥的阶段结论是：**Full 找到的问题面更宽，但新版 Ablation 找到一个
Full 稳定集合未覆盖的问题面；当前小样本不支持稳定率优越性结论。**

## 8. 证据入口

- Full 114-family 台账：`artifacts/experiments/chaosatlas_sockshop_r5_dedup_2026-08-15-r5/audit_summary.json`
- Full 前 38-family 结果：`artifacts/experiments/chaosatlas_sockshop_yaml_confidence_2026-08-15-r5-r4/runtime-canonical-plan-r2/final-review.json`（8 稳定、2 不稳定、28 no-impact）
- Full 前 38-family 完整性：`artifacts/experiments/chaosatlas_sockshop_yaml_confidence_2026-08-15-r5-r4/runtime-canonical-plan-r2/final-verification.json`（76 份报告逐文件 SHA）
- Full 后续选择与 gate：`artifacts/experiments/chaosatlas_sockshop_yaml_confidence_2026-08-15-r5-r4/runtime-remaining-route-aware-2026-08-15-r1/selection_manifest.json`
- Full 静态 gate 明细：`artifacts/experiments/chaosatlas_sockshop_yaml_confidence_2026-08-15-r5-r4/runtime-http-routes-2026-08-15-r1/runtime_plan.json`
- route-aware 最终审核：`artifacts/experiments/chaosatlas_sockshop_yaml_confidence_2026-08-15-r5-r4/runtime-remaining-route-aware-2026-08-15-r3/final-audit.json`
- DNS 平台阻断：`artifacts/experiments/chaosatlas_sockshop_yaml_confidence_2026-08-15-r5-r4/runtime-remaining-route-aware-2026-08-15-r3/dns-runtime-blocked.json`
- 旧版 Ablation 审核（superseded）：`artifacts/experiments/chaosatlas_sockshop_r5_review_2026-08-15-r2/FINAL_REVIEW.zh-CN.md`
- YAML15 Ablation 机器审核：`artifacts/experiments/chaosatlas_sockshop_ablation_yaml15_2026-08-16-r2/final-audit.json`
- YAML15 Ablation 中文审核：`artifacts/experiments/chaosatlas_sockshop_ablation_yaml15_2026-08-16-r2/FINAL_REVIEW.zh-CN.md`
- ChaosEater 原生 cycle：`artifacts/experiments/chaos_eater_deployed/ce_output.json`
- ChaosAtlas availability 旁证：`artifacts/sock-shop/sock_availability_layer_verified.md`
- 本报告机器摘要：`analysis_outputs/sock_shop_three_method_stage_2026-08-16.json`

## 9. 冻结边界

- `human_review=pending`
- `knowledge_base_updated=false`
- 敏感信息扫描已完成：5 类模式命中 0 个文件
- 不把业务弱点写成未经证据支持的缓存、注册、重试或服务发现根因
- 不使用预选池、same-pool、早期 pilot 或 adapter 结果补强当前结论
- Ablation 重做后更新本报告，不把新旧分母相加
