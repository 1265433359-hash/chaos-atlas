# ChaosAtlas 论文主线与证据冻结

更新时间：2026-08-16

本文件是当前论文叙事的唯一主线入口。它决定哪些工作用于说明方法能力，哪些材料只保留作历史审计，哪些实验仍属于后续计划。实验原始文件不因本文件而移动、删除或改名。

## 一句话主线

ChaosAtlas 先构建了以 TestNode、局部影响子图、适用性门禁和证据约束知识库为核心的混沌测试方法；随后在三个真实微服务项目中验证其真实 issue 发现能力；在方法改进后，通过 Sock Shop 上的完整方法与知识库消融实验验证知识库对假设生成和真实问题发现的贡献；最后复现官方 ChaosEater 原生流程，作为不同模型和测量层下的独立参照。

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

论文主线使用三个真实项目作为初始架构的能力验证，并已经向对应 GitHub
仓库提交 6 个可回链 issue：

### 为什么选择这三个项目

这三个项目不是按照服务名称或单一故障类型挑选的，而是按照“真实微服务结构、可部署
性、业务可观测性和调用模式差异”共同确定。它们能够在相对可控的实验环境中提供不同
的业务路径、服务依赖和观测条件，使 ChaosAtlas 的 TestNode、调用链分析、适用性门禁
和证据链不依赖某一个项目的固定服务名。

| 项目 | 选择原因 | 主要验证重点 |
|---|---|---|
| Online Boutique | 具有清晰的电商端到端路径和多个同步下游服务，部署资料完整，业务结果容易通过首页、购物车和结算流程观察。 | 下游不可用、延迟和丢包如何传播到核心业务路径，以及调用方的超时和降级边界。 |
| OpenTelemetry Demo | 由多语言服务组成，调用链和遥测信息丰富，适合检验方法在复杂观测条件下能否把运行现象与服务路径、错误语义对应起来。 | 跨服务调用、trace 证据、错误传播和错误服务标识之间的一致性。 |
| Train Ticket | 是具有较多业务服务和真实业务流程的微服务基准系统，既能部署和重复运行，又能检验源码实现与实际生产可达路径是否一致。 | 调用契约、客户端 timeout、路径可达性，以及“代码中存在但业务路径未必经过”的情况。 |

因此，三个项目共同形成了互补的验证面：Online Boutique 强调业务下游传播，
OpenTelemetry Demo 强调多语言调用链和观测证据，Train Ticket 强调复杂业务路径与
可达性核对。这里的“选择”服务于方法能力的代表性验证，不宣称三个项目构成所有微服务
系统的统计代表样本。

| 项目 | 主线作用 | 代表性能力 |
|---|---|---|
| Online Boutique | 真实下游调用语义 | 3 个已提交 issue：product catalog 不可用导致首页 500、checkout 等待下游、payment probe 延迟重启 |
| OpenTelemetry Demo | 复杂观测条件下的真实行为 | 1 个已提交 issue：shipping 失败时错误消息错误指向 email service |
| Train Ticket | 真实基准系统中的调用契约与可达性 | 2 个已提交 issue：station 查询超出客户端超时、`/order/refresh` 可能跳过 station-name 查询 |

这一阶段的核心结论是：在固定版本、业务 workload 和实验环境下，ChaosAtlas 能够把
真实 YAML、部署事实、源码/调用路径和运行时证据连接起来，识别真实 issue，并形成
可提交、可复现和可回链的 GitHub 报告。6 个 issue 的性质并不完全相同，既包括
运行时延迟/故障传播，也包括错误处理语义和生产路径可达性；因此论文不把它们强行
合并成一个代码级问题族，也不把业务 issue 自动等同于内部根因。

但在可泛化的抽象层面，三个项目确实暴露出同一个共性问题族：**跨服务同步调用的
timeout/deadline、降级和错误传播边界不完整或不一致**。当下游服务延迟、丢包、不可用
或返回异常时，调用方可能等待过久、把故障继续传播到业务路径，或者报告错误的服务/
错误类型。这个共性结论描述的是调用契约和故障传播模式，不表示三个项目存在同一段
代码或同一个可直接合并的 GitHub bug。

### 跨项目迁移证据

这里的“迁移能力”指方法和证据链可以迁移到不同项目，不是三个项目中存在完全相同
的代码级缺陷：

- **Online Boutique**：payment 延迟几乎全量传导，丢包可持续到调用方 deadline；product catalog 核心路径缺少等价降级。
- **OpenTelemetry Demo**：checkout 链路中的 payment/shipping 调用存在无有效 timeout/deadline 的路径，延迟和丢包传播到业务调用方。
- **Train Ticket**：station 查询延迟暴露了客户端超时边界，`/order/refresh` 的下游调用可达性分析则展示了“有实现但生产路径可能不经过”的反例。

因此，这组三项目证据支持“方法具有跨项目迁移能力”的克制表述：迁移的是
TestNode、调用契约、timeout/deadline、降级/错误边界、业务 oracle、源码核对和证据链
分析模式，而不是某个项目的服务名或固定故障配置。

6 个 issue 的提交状态和链接记录在 `reporting/submission_index.md` 与
`reporting/tracking.md`；提交事实属于论文的外部影响证据，issue 是否被上游修复或
回复不作为 ChaosAtlas 发现能力的必要条件。

## 阶段三：Sock Shop 方法改进与知识库消融

方法改进后，在同一个真实 Sock Shop 项目上比较：

- **完整方法**：允许使用项目知识视图和知识库，完成自主假设生成、适用性筛选和真实注入；
- **消融方法**：保持真实项目、业务 oracle、运行协议和生命周期要求一致，但移除知识库视图。

### 为什么选择 Sock Shop

Sock Shop 是一个真实的微服务电商系统，而不是只包含单一服务的玩具应用。它同时包含
前端、业务服务、数据库、消息队列和下游依赖，具有适中的服务规模、可分析的调用关系
和明确的端到端业务路径。因而，在本地 Kubernetes/Chaos Mesh 环境中，它既能够呈现
故障从服务实例、网络和资源层向业务层传播的过程，又能够通过稳定的业务 oracle 区分
真实业务弱点、无影响结果和恢复保护边界。

Sock Shop 还适合进行方法学上的公平比较：两个方法可以使用同一项目版本、同一业务
workload、同一故障生命周期和同一证据采集协议，实验差异主要集中在知识库是否参与
假设生成与筛选。选择 Sock Shop 的目的，是在一个具有真实微服务依赖的可控基准上
隔离方法变量，不宣称该项目能够代表所有生产系统。

### 五类故障范围与实验成本控制

五类范围按照故障机制归并，而不是只选择五个具体动作：

| 类别 | 主要考察的故障机制 | YAML 数量 | 占全部语料 |
|---|---|---:|---:|
| Pod disruption | 实例或容器不可用 | 341 | 17.6% |
| Network degradation | 延迟、丢包、分区和带宽退化 | 428 | 22.1% |
| Resource pressure | CPU、内存等资源压力 | 352 | 18.2% |
| Protocol/HTTP fault | HTTP、DNS 和请求层异常 | 263 | 13.6% |
| Composite/scheduled fault | Workflow、Schedule 和复合故障 | 122 | 6.3% |
| **合计** | **主要故障传播机制** | **1506** | **77.8%** |

该范围来自约 1935 条真实 YAML 的分类结果，覆盖 1506 条，占全部语料的 77.8%。
五类覆盖了实例可用性、通信退化、资源耗尽、协议层异常以及复合编排等主要实验轴，
并且都能够在 Sock Shop 中映射到可执行的 mutation、可达的服务路径和可观察的业务
oracle。因此，它在语料覆盖率、故障机制代表性和运行可行性之间取得了平衡。

五类范围也用于控制实验成本。若直接覆盖全部 YAML，需要分别处理不同 Chaos 资源
的部署依赖、参数约束、代理配置、权限要求和环境兼容性，并为每个候选重复执行
baseline、注入、恢复、cleanup 和 washout。IOChaos、TimeChaos、PhysicalMachineChaos、
JVMChaos、KernelChaos 及云平台相关类型等剩余 429 条 YAML，部分还需要额外的平台或
内核支持，容易把实验时间消耗在环境适配和排障上，而不是方法能力评估上。

因此，五类范围能够在保留主要故障机制的同时，减少故障语义、环境配置、重复注入和
人工证据审查的组合数量，使有限资源更多用于验证结果是否稳定、证据是否充分以及
两种方法是否能够公平比较。这里的“成本控制”是实验设计层面的综合成本控制，不能
将 77.8% 的语料覆盖率直接解释为 77.8% 的时间或资源节省。剩余 429 条 YAML 并非被
判定为无价值，而是作为后续扩展范围保留。

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

本阶段主线首先比较可复现稳定弱点的数量：Full 确认 15 个稳定 weakness family，
YAML15 Ablation 确认 9 个。该数量差异只能作为当前实验范围内的描述性结果，因为两种
方法生成并进入 runtime 的候选数量不同，不能直接解释为总体发现能力的固定比例。
Fisher 双侧精确检验 `p=0.8132`，也不支持把 Full 写成具有统计显著的稳定率优越性。
其他候选归并和重合分析保留在补充台账中，不作为本阶段主线结论。完整口径见
`docs/SOCK_SHOP_THREE_METHOD_STAGE_REVIEW_2026-08-16.md`。

当前实验报告均保持 `human_review=pending` 和
`knowledge_base_updated=false`。这一阶段支持“Full 确认 15 个稳定 weakness，YAML15
Ablation 确认 9 个稳定 weakness”；小样本和不同候选规模不支持任一方法的稳定率优越性。
本阶段以稳定弱点数量为主线指标，不把补充归并结果与稳定弱点数量混用。

## 阶段四：ChaosEater 官方原生流程复现

当前已完成官方 ChaosEater 原生端到端流程的五次真实运行。使用官方
`commit 47c4e44`、官方 `examples/sock-shop-2` 入口、真实 Kubernetes/Chaos Mesh
环境和原生执行流程，得到 4 个场景假设、8 个稳态假设、12 个可执行初始故障假设，
并观察到 2 类 availability/readiness 弱点：

1. front-end 单副本导致单点故障；
2. readiness/recovery 延迟过长，导致故障恢复慢。

这是一项**官方流程复现**，不是论文结果的逐字逐值复现。论文使用 GPT-4o
`gpt-4o-2024-08-06`，当前运行使用 DeepSeek；即使两边都设置
`temperature=0`、`seed=42`，不同模型仍会产生不同的假设、排序、停止轨迹和重配置
结果。当前运行也没有启用论文脚本中的 LLM-as-a-judge
（`num_review_samples=0`），因此只把原生执行和机器证据作为阶段性结果，不把它
当作论文 judge 后的完全等价结论。Kind 集群资源、Kubernetes/Chaos Mesh 版本、
镜像和网络条件也不应默认视为与论文环境完全一致。

ChaosEater 与 ChaosAtlas 的测量层不同：ChaosEater 当前稳态主要是
availability/readiness，ChaosAtlas Full/Ablation 主要使用业务 oracle。因此，
ChaosEater 的 2 类弱点不能与 Full 的 15 个稳定业务 mutation family 或
Ablation 的 9 个稳定 family 直接相加、计算覆盖率或比较发现率。

本阶段允许写成：

- ChaosAtlas 工作区完成了官方 ChaosEater 原生流程的真实复现；
- ChaosEater 在当前环境中发现了 front-end 单副本和恢复/readiness 相关可用性弱点；
- 该结果可作为方法能力的分层参照，说明两种方法都能在真实 Sock Shop 上产生可验证
  的故障发现结果。

本阶段不允许写成：

- 已完成 GPT-4o 条件、同集群、同 judge、同测量层的正式三方法公平对比；
- ChaosAtlas 已经全面优于 ChaosEater；
- 当前 15、9、2 三个数字可以直接作为三种方法的统一弱点排名；
- `ChaosEater-adapter` 结果等同于官方完整 ChaosEater 结果。

`ChaosEater-adapter` 仍然只是辅助历史材料，不能替代官方原生结果。

## 论文主线数据边界

### 纳入主线

- 初始 TestNode/局部影响子图/门禁/证据链架构；
- Online Boutique、OpenTelemetry Demo、Train Ticket 三个真实项目的能力验证及 6 个已提交 issue；
- Sock Shop 完整方法与消融方法的自主假设生成和真实运行结果；
- 官方 ChaosEater 原生流程复现及其 availability/readiness 层参照结果；
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

- 三项目 issue/能力证据：`artifacts/report_for_supervisor.md`
- 已提交 issue 台账：`reporting/submission_index.md`、`reporting/tracking.md`
- Sock Shop 三方法阶段复盘：`docs/SOCK_SHOP_THREE_METHOD_STAGE_REVIEW_2026-08-16.md`
- Sock Shop 消融 discovery：`artifacts/experiments/chaosatlas_sockshop_ablation_discovery_2026-08-15-r1/`
- Sock Shop 最新 runtime/review：`artifacts/experiments/chaosatlas_sockshop_r5_runtime_2026-08-15-r1/`、`artifacts/experiments/chaosatlas_sockshop_r5_review_2026-08-15-r2/`
- 历史 same-pool 归档：`artifacts/experiments/chaosatlas_same_pool_fair_2026-08-14-r3/`
- 项目归档规则：`docs/ARCHIVE_MAP.md`
