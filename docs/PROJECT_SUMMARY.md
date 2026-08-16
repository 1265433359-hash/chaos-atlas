# ChaosAtlas 项目总览

更新时间：2026-08-16（Sock Shop 三方法阶段口径复核）

本文档是仓库级总结，面向论文写作、实验复核、知识库检索和后续交接。
它描述当前工作区的事实状态，不替代任何单次实验报告、原始日志或预注册协议。

## 0. 当前论文主线

当前唯一论文主线见 `docs/CHAOSATLAS_PAPER_MAINLINE.md`，分为四个阶段：

1. 初始 TestNode、局部影响子图、适用性门禁、证据链和知识库架构；
2. Online Boutique、OpenTelemetry Demo、Train Ticket 三个真实项目的 issue 发现能力验证；
3. 方法改进后在 Sock Shop 上进行完整方法与知识库消融的真实端到端比较；
4. 官方 ChaosEater 原生流程复现，作为不同测量层的阶段参照。

same-pool、预选候选池和 `ChaosEater-adapter` 结果均为冻结历史材料，保留原路径但不进入主线统计。

## 0.1 2026-08-13 阶段归档更正

当前主线主动方法范围是 `ChaosAtlas-full` 和
`ChaosAtlas-ablation`。官方 ChaosEater 原生复现已作为不同测量层的阶段参照归档；
同层正式三方法对照仍是后续工作。

旧 Sock Shop Minikube pilot 只完成了两条 ChaosAtlas 臂，使用同一个
`front-end` PodKill mutation；该 pilot 作为冻结历史材料，不能替代当前自主
discovery/ablation 结果，也不能称为完整三方法 head-to-head。该 pilot 中的
ChaosEater 臂曾为 `environment_blocked`；后续五次官方原生复现是独立的阶段参照，
不得使用 adapter 或历史输出替代。

当前 Sock Shop 精确台账是：Full 114 个去重 family 已全部完成静态适用性处理，
其中 96 个进入 runtime cohort，88 个完成两次真实注入、8 个 route-aware
DNSChaos 在注入前被平台 gate 阻断、18 个被静态 gate 拒绝；
88 个已注入 family 中 15 个稳定、3 个不稳定、70 个未观察到业务弱点。YAML15
Ablation 从 458 个原始假设去重得到 51 个 family，46 个完成两次注入，得到 9 个
稳定弱点、0 个不稳定和 37 个 no-impact。Full 与 Ablation 分别确认 15 个和 9 个
稳定 weakness；Fisher 双侧 `p=0.8132`，不支持稳定率优越性。
详见 `docs/SOCK_SHOP_THREE_METHOD_STAGE_REVIEW_2026-08-16.md`。

P09 已完成 `ChaosAtlas-full` 与 `ChaosAtlas-ablation` 各 5 次运行，全部通过
生命周期校验，但当前 oracle 仍是 `/health`，因此只支持有界中断/恢复和连接症状
结论，不支持业务弱点、具体根因或方法优越性。P08 仍被正式运行 gate 阻断；
P03/P06 的 `r6` 静态 profile 已通过，但 server-side dry-run 尚未完成。
完整记录见 `docs/CHAOSATLAS_PROJECT_ARCHIVE_2026-08-13.md`、
`artifacts/experiments/CHAOSATLAS_ARCHIVE_INDEX_2026-08-13.json` 和
`artifacts/experiments/chaosatlas_followup_four_projects_2026-08-13/queue_manifest.json`。

## 1. 一句话定位

ChaosAtlas 是一个面向真实微服务项目的、以混沌测试节点为中心的证据闭环：

```text
真实 Chaos YAML
  -> 测试节点抽象
  -> selector/Deployment/Service/源码入口映射
  -> 测试节点局部影响子图
  -> 适用性门禁（目标、业务可达、平台前置条件）
  -> 有界单因素注入
  -> 基线/注入/恢复/清理证据
  -> 保守分类与根因解释
  -> 版本化知识卡片
  -> 下一轮候选选择与停止规则
```

核心研究对象不是“所有代码的完整 CFG/DFG”，而是某个 TestNode 实际影响的
服务、函数、调用、数据流、控制流、观测和恢复路径。

## 2. 当前工作区性质

这是一个研究工作区，不是单一业务应用仓库，也不是可直接部署到生产环境的
Helm/Compose 项目。它同时保存：

- 原始混沌 YAML 语料；
- 四个真实微服务案例的静态映射和运行时证据；
- 选择器、运行器、分类器、知识库和报告工具；
- held-out、ChaosEater 对照和知识库消融的冻结快照；
- 论文准备、问题草稿、审计修复和过程规划文件。

因此，仓库中的文件有不同证据等级。生成的候选、平台阻断、业务不可达和
运行时已验证结果必须分开解释。

## 3. 规模快照

| 区域 | 当前规模 | 说明 |
|---|---:|---|
| `raw_yaml/` | 1,935 YAML | 原始输入语料，按 Chaos Mesh 资源种类分目录 |
| `artifacts/` | 1,166 文件，约 21.76 MB | 机器产物、运行报告、知识卡片、实验协议 |
| `tools/` | 75 个顶层 Python 工具、6 个 shell 工具 | 构建、选择、注入、分类、知识库、报告 |
| `tools/tests/` | 38 个测试模块 | 选择器、门禁、运行器、分类器、知识库和审计回归 |
| `reporting/` | 13 个已登记文件 | 项目接入、问题草稿、提交追踪、证据打包 |
| `docs/` | 7 份项目级文档（含本文） | 归档、实验、知识库、工具、清理和 GitHub 说明 |
| `.planning/` | 8 个持久化计划目录 | 历史阶段、审查修复、held-out 和消融工作流 |

按 YAML 种类计数，主要分布是：NetworkChaos 428、StressChaos 352、PodChaos
341、HTTPChaos 183、IOChaos 125、TimeChaos 119、PhysicalMachineChaos 114；
其余种类包括 DNS、Workflow、Schedule、JVM、Kernel、云平台和 Block 类资源。

工作区约 7,227 个文件、335.91 MB 的总量包含嵌套源码、二进制、缓存、临时
目录和生成输出，不等于建议上传到 GitHub 的文件集合。

## 4. 项目结构与职责

| 目录 | 职责 |
|---|---|
| `raw_yaml/` | 不修改的原始混沌输入；文件路径和 SHA-256 是追溯锚点 |
| `artifacts/train-ticket/` | 第一项目的 YAML 清单、局部图、服务图、运行证据和 7 张知识卡 |
| `artifacts/online-boutique/` | Online Boutique 的构建、部署、运行重复实验和 8 张知识卡 |
| `artifacts/opentelemetry-demo/` | OTel Demo 的手工部署、观测实验和 2 张知识卡 |
| `artifacts/experiments/` | held-out、执行台账、ChaosEater、知识消融快照、候选池和提示词 |
| `artifacts/papers/` | 论文相关材料或打包输入，不替代实验原始证据 |
| `reporting/` | 人读总结、Issue 草稿、问题状态和证据包清单 |
| `tools/` | 可复用脚本；模块 docstring 和 `docs/CODE_GUIDE.md` 说明副作用 |
| `tools/tests/` | 默认本地回归测试；集成测试需显式环境 |
| `governance/` | 隔离执行、凭据、证据和发布边界 |
| `task_plan.md` / `findings.md` / `progress.md` | 计划、发现和过程日志 |

## 5. TestNode 方法与证据链

### 5.1 四层适用性

1. YAML 语义有效；
2. selector、namespace、Deployment/Pod 等目标存在；
3. 业务 workload 和 oracle 可达、可重复；
4. 变异实际注入，效果可观测，服务和资源能恢复并清理。

只有第 4 层完成后，才可以讨论防御、弱点、延迟边界或根因。平台前置条件
缺失和业务不可达本身是重要的适用性结论，但不能写成“系统防御成功”。

### 5.2 影响子图

```text
TestNode
 -> 配置/默认值/校验
 -> selector/Deployment/Service/Pod
 -> Controller/Service/Repository
 -> 下游 HTTP/gRPC/数据库/网络/资源边
 -> 业务响应与延迟
 -> 日志/指标/Trace/cgroup
 -> Recovery/Cleanup
```

每条边应标记为 `confirmed_static`、`confirmed_runtime`、`hypothesis` 或
`not_reachable`。源码里存在函数不等于实际请求执行了该函数。

### 5.3 结果分类

项目明确区分：response preserved、latency degradation、client timeout、
server completion after client timeout、graceful degradation、platform blocked、
not reachable、unknown 和 defense observed。HTTP 200 只证明该 oracle 的响应
契约在该窗口内保留，不证明生产 SLO、timeout、retry、fallback 或熔断存在。

## 6. 四个真实案例

### 6.1 Train Ticket：主线案例

- 仓库：`FudanSELab/train-ticket`。
- 固定 commit：`313886e99befb94be6cd45f085c98e0019f59829`。
- 子集：54 个 `train-ticket` namespace 样本；静态 selector 映射 53/54，源码函数候选 49/54。
- 知识库：7 张卡片，均有 `index.json` 和验证报告。
- 隔离环境：`train-ticket-lab`，单目标、自动恢复和清理。

覆盖矩阵：

| 状态 | 数量 | 解释 |
|---|---:|---|
| verified | 5 | Station 延迟、Basic/Order/Station CPU、Basic->Station 网络等运行线 |
| platform_blocked | 30 | HTTPChaos 受 WSL2 `ebtables`/tproxy 前置条件阻断 |
| not_reachable | 1 | Order->Station refresh 的生产下游调用被注释，业务路径未成立 |
| static_only | 1 | `mode: all` Workflow，爆炸半径高，只做静态展开 |
| not_run | 17 | 已有静态映射但尚未执行运行时注入 |

最完整的论文案例是 Station NetworkChaos：100 ms、500 ms、2 s 延迟阶梯下，
响应契约保持但延迟从约 30 ms 增长到约 216 ms、1,021 ms、4,021 ms；3 s 边界
下客户端约 5,047 ms 超时，而服务端约 6,064 ms 才完成业务分支。该结果支持
“响应正确不等于延迟 SLO 被保护”，也支持“客户端超时不等于服务端停止”。

CPU 线使用 cgroup-v2 观测到真实 throttling，业务响应在部分窗口仍为 HTTP 200；
正确解释是“功能响应保留但资源压力和延迟恶化”，不是“完整防御”。

### 6.2 Online Boutique：跨项目语义对照

- 仓库：`GoogleCloudPlatform/microservices-demo`。
- 固定 commit：`9a4616e77f0f9cbcbecaf27d711c38890dda1404`。
- 环境：kind `chaos-kind`、Chaos Mesh 2.8.3、Online Boutique 隔离 namespace。
- 知识库：当前 8 张运行时卡；早期报告中的 4/6 张是阶段性统计，不代表当前卡片总数。

主要结果：

- payment 2 s delay 重复实验（n=9）约 2,021.5 ± 3.1 ms，说明延迟几乎全额传导；
- payment 100% loss（n=5）稳定挂起到调用方约 10 s deadline；
- shipping 被同一 PlaceOrder 路径调用两次，2 s delay 约传导为 4,021.5 ms；
- email 丢包可通过 `Warnf` 降级，下单保持成功，但延迟仍然传导；
- product catalog 核心路径无等价 fallback，丢包可出现约 26.7 s 挂起后 500；
- liveness probe 与故障延迟竞争，重启可能暂时移除旧注入；重新注入后故障立即恢复，说明这是探针副作用而非应用自愈；
- payment+email 多故障的延迟近似按顺序相加。

该案例说明同一故障族在不同下游会产生 fatal、degraded、restart-converted 等
不同业务语义，不能只按“NetworkChaos=失败”泛化。

### 6.3 OpenTelemetry Demo：观测证据对照

- 仓库：`open-telemetry/opentelemetry-demo`。
- 固定 commit：`2e72d8bcdf754603e956406808630bc9663c992c`。
- 部署：源码以 Compose 为主，实验中手工生成 manifest，部署 10 个服务和 flagd sidecar。
- 知识库：2 张运行时卡。

主要结果：

- PlaceOrder 基线约 3.0–3.3 s，包含多语言调用链和 OTel SDK 开销；
- payment 2 s delay 增加约 1,690–2,075 ms；
- payment 100% loss 挂起约 10,007 ms 后 `DEADLINE_EXCEEDED`；
- Jaeger trace 捕获到 PaymentService/Charge span 从约 513 ms 增至约 4,462 ms，并带有 HTTP 异常事件；
- 观测链可以捕获故障，但当前没有自动告警，仍需人工查询 Jaeger；
- HTTP email 丢包的行为比 Online Boutique 的 gRPC email 更容易挂起，说明协议栈是因果变量。

该案例的价值是证明“观测完备”与“自动诊断”不是同一个命题，并提供了前两个
项目缺少的 span 级证据。

### 6.4 Sock Shop：改进方法消融与历史分层材料

Sock Shop 是阶段三的方法改进与消融项目。它检验知识视图是否改变自主假设生成和
稳定弱点发现。下面的 `6/8` 结果属于历史 HTTP-edge 分层验证，不是当前
full/ablation discovery 的统计分母。

最终 HTTP 边结果为 **6/8 weakness、2/8 defended**。`orders→payment` 和
`orders→shipping` 在真实 `POST /orders` 链路中存在 5 秒
`Future.get(timeout, SECONDS)` 防御：2 秒注入仍返回 201，6 秒注入约 5 秒返回
500 并出现 `TimeoutException`。旧报告中的 8/8 weakness 只来自直连服务级测量，
现作为修正前历史结果保存，不能作为最终论文数字。

计数口径必须写清：上述论文数字按两个 defended 服务边计数；机器台账
`sock_shop_verdicts.json` 还把 delay/loss 变体拆开，并将两个 loss 防御按共享
`Future.get` 契约推断，因此 contract-layer 汇总会显示 4/8 weakness + 4/8 defended。
loss 未单独走真实订单链路复跑，论文中不能把两种分母混用。

历史 ChaosEater 材料（commit `47c4e44`）与当前两臂运行必须分开：

- ChaosEater 的完整运行主要发现单副本、缺少 PDB/HPA、探针覆盖不足及 kill 后恢复时间等部署可用性风险；
- 本方法补充了 HTTP 调用边的 delay/loss 语义、业务响应、源码中的 timeout 契约、恢复/清理和结构化根因；
- 当前 ChaosEater 阶段摘要记录 2 个 availability/readiness 弱点，但五次复现尚缺统一机器 manifest，不能与 Full/Ablation 直接做正式统计。
- 当前材料支持**分层覆盖和可审计产出互补**，不支持未经同层公平协议验证的全面优于 ChaosEater。

这一项目给论文带来的四个具体贡献是：知识跨项目迁移、识别“loss 大于 delay”先验的边界、把调用契约层与部署可用性层统一、以及将结果输出为可复核和可复用的证据链。

## 7. 跨项目迁移证据、可复现模式与边界

论文阶段二的三个真实项目是 Online Boutique、OpenTelemetry Demo 和 Train Ticket；
Sock Shop 作为阶段三的受控方法比较项目。前三者在不同语言、协议、服务拓扑和
业务路径中复现了同一抽象问题族：同步下游
调用缺少一致的 timeout/deadline 或降级边界时，延迟、丢包或下游故障会向业务
路径传播。这里的“同一问题”指可迁移的调用契约和故障传播模式，不是三个项目
中完全相同的代码级缺陷。

- Online Boutique 中，payment 延迟几乎全量传导，丢包可持续到调用方 deadline；
  product catalog 核心路径缺少等价降级。
- OpenTelemetry Demo 中，checkout 链路的 payment/shipping 调用存在无有效
  timeout/deadline 的路径，延迟和丢包传播到业务调用方。
- Train Ticket 中，Station 延迟和客户端 timeout 边界展示了服务端晚完成与业务
  路径可达性核对的重要性。

这支持“ChaosAtlas 具备跨项目迁移能力”的克制结论：迁移的是 TestNode、调用
契约、timeout/deadline、业务 oracle 和证据链分析模式，而不是某个项目的服务名
或固定故障配置。Sock Shop 的防御边还说明，知识迁移必须允许新项目修正既有
先验，不能把所有同步调用预先判为弱点。

Sock Shop 的完整方法与 YAML15 Ablation 结果单独归入阶段三，不与阶段二的 6 个
GitHub issue 数量混合。

跨项目差异同样重要：

| 维度 | Train Ticket（阶段二项目） | Online Boutique | OTel Demo | Sock Shop |
|---|---|---|---|---|
| 观测 | 客户端/日志/cgroup 为主 | 客户端、日志、Pod/探针 | 增加 Jaeger span 证据 | 业务响应、日志、静态 manifest、Ready 曲线 |
| email/旁路语义 | 未形成同等对照 | gRPC 快速失败并降级 | HTTP 挂起到 deadline 后才降级 | 重点验证 orders 下游 timeout 防御 |
| probe/可用性 | 未形成同等案例 | 明确的重启-注入逃逸 | 当前配置未触发 | 单副本、无 PDB/HPA、部分无 readiness |
| 业务基线 | 数十毫秒级查询 | 十几毫秒级电商调用 | 三秒级多语言链 | 订单链路约 0.2 s |

## 8. 知识库与决策闭环

当前三套项目知识库共 17 张卡：Train Ticket 7、Online Boutique 8、OTel Demo 2。
Sock Shop、P02、P08、P09 的 pending 审核材料不自动进入知识库。
每张卡包含项目 commit、TestNode、局部图、四层验证、证据、状态和
`next_evidence`。`tools/validate_knowledge_base.py` 验证索引/路径、必需字段、
图结构、来源引用和敏感值 warning。

实验经验还分为三类库：

- SE：哪些测试族、业务路径和候选更值得优先测试；
- DP：哪些已验证机制提供 timeout、fallback、降级或保护；
- JE：延迟、丢包、重启、契约等症状应如何调整判断。

`decision_engine.py` 是无 LLM 的可审计规则层；LLM 只能作为候选决策增强器，
不能绕过 hard filter、冻结快照、适用性门禁和停止规则。已闭合的边界应标记
`closed_runtime_boundary_no_reinjection`，避免重复注入。

## 9. 对比实验与消融状态

### 9.1 主线对照

当前主线不是单一总分，而是比较 applicability、业务契约、延迟变化、失败语义、
防御语义、恢复和观测能力。`reporting/projects_matrix.md`、各项目实验报告和
`docs/EXPERIMENT_CATALOG.md` 是入口。

### 9.2 ChaosEater 阶段参照

官方 ChaosEater 原生流程的五次复现已归档，但其模型、oracle 和测量层与
ChaosAtlas 不同。该轨道只能作为阶段参照，不能与 Full/Ablation 的业务弱点数量
直接合并；`ChaosEater-adapter` 不能替代官方原生流程，也不能支持总体优越性结论。

### 9.3 same-pool/预选候选池冻结材料

- same-pool、预选候选池和固定 mutation 选择实验已冻结；原始 prompt、candidate
  pool、selection records、runtime reports 和 audit 文件全部保留。
- 该轨道不再作为当前论文的主线比较，也不使用 80.0%、70.6% 等命中率支持知识库
  有效性结论。
- 如未来恢复，必须另行批准 protocol amendment；恢复后的结果也不能回写覆盖当前
  主线数据。

### 9.4 当前论文冻结边界

当前论文版本优先使用：初始架构说明、三个真实项目的 issue 发现证据、Sock Shop
完整方法与知识库消融的真实 discovery/runtime 证据，以及可回链的人工审核材料。
`human_review=pending` 的运行可以作为阶段性证据保存，但不能自动进入知识库。
旧 Sock Shop pilot、same-pool/预选池结果、P02/P08/P09 等非主线 pending 材料和
ChaosEater 历史对照不得写成当前方法 superiority 结论。

## 10. 报告与对外问题

`reporting/submission_index.md` 已登记 6 个问题草稿，当前均未自动提交：

- P0：Online Boutique 核心 product catalog 无降级；Train Ticket refresh 禁用下游调用；
- P1：OTel Demo shipping/email 错误消息复制粘贴；Train Ticket Station 无 timeout/熔断防御；
- P2：Online Boutique checkout 无 timeout；payment probe 配置观察。

Docker Desktop/WSL2 `ebtables`、本地镜像构建和 manifest 适配属于环境或实验室
集成问题，不应直接作为上游项目缺陷提交。

## 11. 当前限制

1. 主案例数量仍少；阶段二结论来自 Online Boutique、OpenTelemetry Demo 和 Train Ticket
   三个特定项目，Sock Shop 的方法对比属于独立的阶段三实验。
2. 多数实验是小样本或有界窗口；5 s 是实验客户端预算，不是生产 SLO。
3. Order->Station 真实业务路径尚未形成可重复 oracle。
4. HTTPChaos 在当前 WSL2 内核上仍被 `ebtables` 前置条件阻断。
5. 一些 Online Boutique/OTel 卡片的 `source_yaml` 是 generated candidate，因此 validator 保留 warning。
6. 历史报告的卡片数量可能低于当前索引数量；以当前 `index.json` 和 validation report 为准。
7. Sock Shop Full 分母已复核为 114/96/88，YAML15 Ablation 已完成 51/46/9；ChaosEater 五次复现摘要尚缺统一机器 manifest，因此三方法同层公平比较仍未完成。
8. 工作区有大量用户生成的未跟踪/修改文件和临时目录，不是干净 release branch。

## 12. 论文材料建议

建议论文按以下顺序组织：

1. 初始方法：TestNode 抽象、局部影响子图、适用性门禁、证据链和知识库；
2. 三项目能力验证：Online Boutique、OpenTelemetry Demo、Train Ticket 的真实 issue 发现；
3. 方法改进与 Sock Shop 消融：完整方法与 YAML15 Ablation 的自主假设和真实运行结果；
4. ChaosEater 原生流程阶段参照及不同测量层的限制；
5. 评估与限制：实际注入覆盖、issue/weakness、恢复/清理、观测完整度和审核状态；
6. 后续工作：同测量层、同 oracle 的官方 ChaosEater 正式对照及新项目扩展；
7. 威胁与限制：项目数量、环境、SLO、oracle、样本量和阶段性 protocol 边界。

论文每个数字都应回链到 `.json`/`.csv`/ledger，再链接人读报告；每个 defense
claim 都应有源码合同、运行时间线或明确 SLO 证据。

## 13. 下一步优先级

### 当前四项目队列

后续只推进 `ChaosAtlas-full` 与 `ChaosAtlas-ablation`：

1. Online Boutique：重新冻结 manifest，隔离 loadgenerator，验证 PlaceOrder/frontend oracle，再做 dry-run。
2. OpenTelemetry Demo：重新冻结脱敏手工 profile，验证 PlaceOrder/trace contract，再做 dry-run。
3. Train Ticket：复用 Station 双 oracle 和 runner，但用新 namespace、manifest 和输出目录。
4. TeaStore：恢复固定源码，渲染 Helm/Ribbon profile，完成 bring-up、稳定性和两次 baseline gate。

P08/P03/P06 的历史准备材料保留在十项目 ledger 中但不进入本批矩阵；ChaosEater
不进入这四个项目的当前运行矩阵。

### P0：冻结论文数据集

- 固定四项目 commit、实验矩阵、运行环境和知识库 index；
- 清理历史报告中的“阶段性卡片数量”表述；
- 为所有论文数字建立 claim-evidence matrix。

### P1：补齐实验可比性

- 统一 Train Ticket/OB/OTel 的 run schema、warm-up、正式窗口、并发、timeout 和恢复字段；
- 记录 p50/p95、错误率、客户端/服务端完成时间、重启、清理和观测覆盖；
- 将平台 blocked、not reachable、unknown 单独作为结果类。

### P1：完成主线证据锁定

- 锁定三个项目真实 issue 证据和 Sock Shop 完整方法/消融的最终 discovery/runtime 台账；
- 分离生成假设、未注入、门禁阻断、已注入、重复完成、唯一 issue、稳定 weakness 和根因审核状态；
- 不把 same-pool/预选池文件重新引入主线统计。

### P1：准备 ChaosEater 正式对照

- 单独建立官方完整 ChaosEater 的真实部署和业务 oracle 协议；
- 完成真实注入、恢复、清理、证据审核后，再决定是否作为论文扩展实验；
- 现有历史 ChaosEater 和 adapter 材料只作为冻结背景，不替代正式第三臂。

### P2：扩展业务路径

- 找到可重复的 Order->Station 真实调用；
- 在非 WSL2 或兼容内核环境复验 HTTPChaos；
- 只扩展到有 workload、oracle 和 cleanup 证据的节点。

## 14. 发布边界

当前分支为 `remediation/2026-08-09-review`，工作区存在大量用户实验改动和
未跟踪生成物。私有 GitHub 上传前必须单独审核：纳入哪些 artifacts、是否排除
缓存/临时目录/二进制、第三方许可证、敏感值和最终分支。没有用户明确授权，
不配置 remote、不创建仓库、不 push。

项目显示名确定为 **ChaosAtlas**，仓库 slug 预留为 `chaos-atlas`。

## 15. 主要入口

- 总入口：`README.md`
- 归档规则：`docs/ARCHIVE_MAP.md`
- 实验目录：`docs/EXPERIMENT_CATALOG.md`
- 知识库：`docs/KNOWLEDGE_BASE.md`
- 工具说明：`docs/CODE_GUIDE.md`
- GitHub 交接：`docs/GITHUB_PRIVATE_HANDOFF.md`
- Train Ticket 阶段报告：`artifacts/train-ticket/paper_prep_stage_summary.md`
- Train Ticket 覆盖矩阵：`artifacts/train-ticket/runtime/coverage_matrix.md`
- 项目问题索引：`reporting/submission_index.md`
- 知识消融协议：`artifacts/experiments/llm_knowledge_ablation_protocol_v1.md`
