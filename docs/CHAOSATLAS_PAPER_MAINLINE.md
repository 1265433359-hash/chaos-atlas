# ChaosAtlas 论文主线与证据冻结

更新时间：2026-08-15

本文件是当前论文叙事的唯一主线入口。它决定哪些工作用于说明方法能力，哪些材料只保留作历史审计，哪些实验仍属于后续计划。实验原始文件不因本文件而移动、删除或改名。

## 一句话主线

ChaosAtlas 先构建了以 TestNode、局部影响子图、适用性门禁和证据约束知识库为核心的混沌测试方法；随后在三个真实微服务项目中验证其真实 issue 发现能力；在方法改进后，通过 Sock Shop 上的完整方法与知识库消融实验验证知识库对假设生成和真实问题发现的贡献；最后计划与完整官方 ChaosEater 开展真实环境对照。

## 阶段一：初始方法架构

初始架构包括：

- TestNode 作为混沌测试的基本分析单元；
- 由配置、部署、服务、源码、业务路径和观测节点组成的局部影响子图；
- YAML 语义、目标存在、业务可达、平台前置条件和注入效果等适用性门禁；
- 基线、注入、恢复、清理和 washout 的有界单因素实验；
- 将响应保持、延迟恶化、客户端超时、服务端继续执行、平台阻断和业务弱点分开记录；
- 通过知识库保存证据、适用边界、反例和下一步证据需求。

这一阶段的目标是证明方法架构能够把真实 Chaos YAML 转化为可执行、可观测、可复核的 TestNode 实验，而不是追求跨项目的单一总分。

## 阶段二：三个真实项目的能力验证

论文主线使用三个真实项目作为初始架构的能力验证：

| 项目 | 主线作用 | 代表性能力 |
|---|---|---|
| Online Boutique | 真实下游调用语义 | 延迟传导、丢包、降级和探针竞争 |
| OpenTelemetry Demo | 复杂观测条件下的真实行为 | 多语言调用链、延迟/丢包和 trace 观测 |
| Sock Shop | 新项目上的真实迁移验证 | 业务 issue、调用契约和跨项目知识边界 |

这一阶段的核心结论是：在所测试的真实项目、固定版本、业务 workload 和实验环境中，ChaosAtlas 能够提出并通过真实运行证据识别业务 issue。三个项目还复现了同一抽象问题族：同步下游调用缺少一致的 timeout/deadline 或降级边界时，延迟、丢包或下游故障会向业务路径传播。该结论不外推为所有微服务系统的普遍规律，也不把业务 issue 自动等同于内部根因。

### 跨项目迁移证据

这里的“同一问题”指可迁移的调用契约和故障传播模式，不是三个项目中完全相同的代码级缺陷：

- **Online Boutique**：payment 延迟几乎全量传导，丢包可持续到调用方 deadline；product catalog 核心路径缺少等价降级。
- **OpenTelemetry Demo**：checkout 链路中的 payment/shipping 调用存在无有效 timeout/deadline 的路径，延迟和丢包传播到业务调用方。
- **Sock Shop**：catalogue 和 orders-db 故障能够传播为真实业务失败；同时 `orders -> payment/shipping` 已观测到 `Future.get(timeout, SECONDS)` 防御，说明迁移后的方法不仅能发现弱点，也能识别保护边界和反例。

因此，这组三项目证据支持“方法具有跨项目迁移能力”的克制表述：迁移的是 TestNode、调用契约、timeout/deadline、业务 oracle 和证据链分析模式，而不是某个项目的服务名或固定故障配置。Sock Shop 的防御边还说明，知识迁移必须允许新项目修正既有先验，不能把所有同步调用预先判为弱点。

Train Ticket 保留为初始架构的历史闭环案例，主要支撑 Station 延迟边界、客户端超时与服务端晚完成、CPU throttling 和适用性分类，不与阶段二的三个项目统计混为一体。

## 阶段三：Sock Shop 方法改进与知识库消融

方法改进后，在同一个真实 Sock Shop 项目上比较：

- **完整方法**：允许使用项目知识视图和知识库，完成自主假设生成、适用性筛选和真实注入；
- **消融方法**：保持真实项目、业务 oracle、运行协议和生命周期要求一致，但移除知识库视图。

当前阶段的精确台账为：

| 指标 | 完整方法 | YAML15 消融方法 |
|---|---:|---:|
| 去重假设/fault family | 114 | 51（原始生成 458） |
| 完成静态适用性处理 | 114 | 51 |
| 进入 runtime cohort | 96 | 46 |
| 完成两次真实注入 | 88（176 reports） | 46（92 reports） |
| 注入前 platform-blocked | 8（DNSChaos） | 0 |
| 静态 gate 拒绝 | 18（12 个非 HTTP 目标 HTTPChaos + 6 个 DNS 源路由缺失） | 5 个数据库 HTTP abort |
| 稳定 weakness | 15 | 9 |
| 不稳定 | 3 | 0 |
| 两次均未观察到业务弱点 | 70 | 37 |

Full 的 15 个稳定 family 在合并直接/定时 PodKill 重复后对应 10 个问题面；不能
写成 15 个互不相同的代码级 ISSUE。YAML15 Ablation 的 9 个稳定 family 对应 9 个
问题面，与 Full 重合 8 个。Fisher 双侧精确检验 `p=0.8132`，不能写成稳定率优越性
结论。完整口径见
`docs/SOCK_SHOP_THREE_METHOD_STAGE_REVIEW_2026-08-16.md`。

当前实验报告均保持 `human_review=pending` 和
`knowledge_base_updated=false`。这一阶段支持“Full 找到的问题面更宽，YAML15
Ablation 也找到 9 个稳定问题面并包含一个 Full 稳定集合未覆盖的 user delay”；
小样本不支持任一方法的稳定率优越性。

## 阶段四：ChaosEater 正式真实对照

仓库保留了官方 ChaosEater 原生 cycle，当前阶段摘要记录五次复现、4 个场景假设、
8 个稳态假设、12 个可执行初始故障假设和 2 个可用性弱点。但五次复现尚缺统一
机器 manifest，且其稳态是 availability/readiness 层，不与 Full 的业务 mutation
15-family 清单同层。因此它作为阶段性对照保留，尚不能进入正式公平统计。

`ChaosEater-adapter` 仍然只是辅助历史材料，不能替代官方原生结果。

当前不能写成：

- 已完成同测量层、同协议的正式三方法公平对比；
- ChaosAtlas 已经全面优于 ChaosEater；
- adapter 结果等同于官方完整 ChaosEater 结果。

## 论文主线数据边界

### 纳入主线

- 初始 TestNode/局部影响子图/门禁/证据链架构；
- Online Boutique、OpenTelemetry Demo、Sock Shop 三个真实项目的能力验证；
- Sock Shop 完整方法与消融方法的自主假设生成和真实运行结果；
- 经过人工审核、可回链到机器台账的 issue/weakness 结论。

### 冻结但不纳入主线统计

- same-candidate-pool、预选候选池和固定候选集实验；
- 基于预选池的 80.0%、70.6% 等命中率；
- 历史 Sock Shop `6/8` HTTP-edge 统计及更早的 `8/8` 直连测量；
- `ChaosEater-adapter` 对照；
- 旧版单 mutation pilot、旧版 R5 分母和已经被后续实验替代的比较表。

这些材料保留原路径和原始 hash，用于审计、复现历史决策和解释研究演进，但不应被 README、论文主表或当前结论引用为主线结果。

## 统一解释规则

1. “发现 issue/weakness”指业务 oracle 层面的真实现象；具体根因需要额外日志、trace、源码或配置证据。
2. 生成假设数不等于真实注入数；未注入候选应单独报告原因和状态。
3. `platform_blocked`、`not_reachable`、`invalid_not_injected` 和业务无影响不是同一类结果。
4. pending 人工审核结果可以作为阶段性证据保存，但不能伪装成已验证知识卡。
5. 三个项目和 Sock Shop 的结论只适用于固定项目版本、workload、oracle、故障强度和实验环境。

## 证据入口

- 三项目当前阶段总结：`docs/CHAOSATLAS_REAL_PROJECT_REVIEW_2026-08-14.md`
- Sock Shop 三方法阶段复盘：`docs/SOCK_SHOP_THREE_METHOD_STAGE_REVIEW_2026-08-16.md`
- Sock Shop 消融 discovery：`artifacts/experiments/chaosatlas_sockshop_ablation_discovery_2026-08-15-r1/`
- Sock Shop 最新 runtime/review：`artifacts/experiments/chaosatlas_sockshop_r5_runtime_2026-08-15-r1/`、`artifacts/experiments/chaosatlas_sockshop_r5_review_2026-08-15-r2/`
- 历史 same-pool 归档：`artifacts/experiments/chaosatlas_same_pool_fair_2026-08-14-r3/`
- 项目归档规则：`docs/ARCHIVE_MAP.md`
