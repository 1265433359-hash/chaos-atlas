# ChaosAtlas 方法详细说明（论文写作准备稿）

更新时间：2026-08-16
用途：向老师说明 ChaosAtlas 的方法演进、Sock Shop 完整实验流程、消融实验流程和当前论文口径。
审核状态：`human_review=pending`
知识库更新：`knowledge_base_updated=false`

## 1. 论文主线中的方法定位

ChaosAtlas 的实验不是从一开始就使用最终版本的方法，而是分为两个方法阶段：

1. **前三个真实项目阶段**：验证初始框架能否把真实 Chaos YAML、项目部署、源码/调用链、业务路径和运行时证据连接起来，并发现可以提交、可以复现的真实 issue。
2. **Sock Shop 改进方法阶段**：在前三个项目积累的经验基础上，将知识卡片、选择经验、判定经验、防御模式、调用链位置、故障适用条件和历史证据组合成可审计的知识视图，形成 `ChaosAtlas-full`；再去掉知识库相关输入，构造 `ChaosAtlas-ablation`，比较知识增强对假设生成和稳定弱点发现的影响。

因此，论文不应把前三个项目写成最终 Full 方法已经完成的全部能力，也不应把 Sock Shop 写成单纯重复前三个项目。更准确的叙述是：

> 前三项目验证 ChaosAtlas 初始架构的真实 issue 发现能力；Sock Shop 在相同的真实微服务场景中，进一步验证改进后的知识增强方法和知识库消融方法，并观察知识视图对假设空间和稳定弱点发现的影响。

## 2. ChaosAtlas 初始框架

### 2.1 TestNode：统一的测试单元

ChaosAtlas 不把一个 YAML 文件直接当成“已验证故障”。它先把一个潜在故障整理成 TestNode。一个 TestNode 至少包含：

- 目标服务、Pod 或容器；
- 故障动作，例如 PodKill、delay、loss、partition、CPU 或 memory pressure；
- 调用链位置，即目标位于入口、业务服务、数据依赖或支撑服务的哪一层；
- 业务路径和业务 oracle；
- 适用条件，包括目标是否存在、端口/路径是否可信、源端和下游是否可达、Chaos Mesh 是否支持该动作；
- 预期现象和实际观测证据；
- 恢复、清理和 washout 状态；
- 来源 YAML、固定版本、文件 SHA-256 和人工审核状态。

这样做的意义是把“故障配置”“实验执行”和“业务结论”分开。YAML 只能说明一个故障意图，不能单独证明系统存在弱点。

### 2.2 局部影响子图

对每个项目，ChaosAtlas 建立与当前测试节点有关的局部影响子图。图中连接：

- Kubernetes Deployment、Service、Pod 和 Chaos 资源；
- 服务之间的请求调用关系；
- 数据库、消息队列等数据依赖；
- 业务入口和业务路径；
- 日志、HTTP 响应、指标和 trace 等观测节点；
- 故障目标到业务 oracle 的可能传播路径。

局部影响子图的作用不是声称完整还原整个系统，而是回答三个实验问题：

1. 故障目标是否位于当前业务路径上；
2. 目标故障是否可能传播到可观察的业务结果；
3. 实验结果出现后，应该从哪些服务、日志和 trace 中寻找证据。

### 2.3 适用性门禁

在注入前，ChaosAtlas 按 fail-closed 原则检查：

1. YAML 是否能够解析，kind 和 action 是否受支持；
2. namespace 是否是实验 namespace；
3. selector 是否只指向允许的 workload；
4. 目标服务、Pod、端口、HTTP path、源端和下游是否真实存在；
5. 故障类型是否与目标协议匹配；
6. 当前 Kubernetes、Chaos Mesh 和内核环境是否满足前置条件；
7. 服务是否位于业务路径中，且业务 oracle 可观察；
8. server-side dry-run 和运行前静态检查是否通过。

门禁失败不等于系统防御成功，也不等于业务弱点。它表示当前假设没有足够证据安全、有效地进入 runtime，应单独记录为 `invalid_not_injected`、`not_reachable` 或 `platform_blocked`。

### 2.4 统一生命周期

每个通过门禁的 mutation 都执行同一条生命周期：

```mermaid
flowchart LR
    A[固定项目版本和输入] --> B[静态解析与适用性门禁]
    B --> C[server-side dry-run]
    C --> D[故障前 baseline]
    D --> E[apply Chaos 资源]
    E --> F[确认 injected]
    F --> G[业务 oracle 观测]
    G --> H[删除父子 Chaos 资源]
    H --> I[全局残留扫描]
    I --> J[资源恢复与业务恢复]
    J --> K[washout 稳定窗口]
    K --> L[日志、事件、trace 和报告]
```

当前 Sock Shop runner 的具体规则是：注入前 5 次业务 journey 必须全部通过；故障期间重复执行相同 journey；删除故障后验证资源和业务恢复；再进行至少 60 秒且连续 10 次成功的 washout。每次报告记录 mutation SHA-256、baseline、injected、observation、recovered、cleanup、washout、诊断文件和人工审核状态。

### 2.5 证据解释规则

ChaosAtlas 将以下概念严格区分：

- **业务弱点**：业务 oracle 在故障期间稳定失败，并且两次 replicate 都复现；
- **不稳定结果**：两次中只有一次失败，不能作为稳定真实弱点；
- **无业务影响**：故障注入成功，但业务 oracle 两次都保持通过；
- **平台阻断**：故障无法在当前平台真正注入；
- **具体根因**：需要日志、trace、源码或配置证据支持，不能仅凭业务失败猜测 Eureka、缓存、重试或注册机制。

知识库只保存经过人工审核、可回链到证据的经验。当前阶段所有报告保持 `human_review=pending`，不自动写入知识库。

## 3. 前三个真实项目：框架验证阶段

### 3.1 为什么选择这三个项目

前三个项目不是为了堆叠项目数量，也不是按照某个单一故障动作挑选，而是用于验证初始框架能否迁移到结构、调用关系和观测条件不同的真实微服务系统。选择依据有四个：

1. 项目必须有真实的多服务依赖和可执行的端到端业务路径；
2. 项目必须能够在固定版本和本地 Kubernetes 环境中重复部署；
3. 业务结果必须能够通过页面、API、响应码、延迟或 trace 观察；
4. 三个项目之间要有足够的结构差异，避免 TestNode 和证据链只适用于某一个项目的服务命名。

| 项目 | 选择原因 | 主要验证重点 |
|---|---|---|
| Online Boutique | Google 的云原生电商演示系统，部署资料完整，首页、购物车和 checkout 路径清晰，并且包含多个同步下游服务。 | 下游不可用、延迟和丢包如何传播到核心业务，以及调用方的 timeout、deadline 和降级边界。 |
| OpenTelemetry Demo | 多语言微服务组成，带有丰富的日志、指标和 trace 观测，适合检验复杂观测条件下的错误传播和错误标识。 | 跨服务调用、trace 证据、错误传播，以及报告的错误服务是否与实际故障服务一致。 |
| Train Ticket | 业务服务数量多、业务流程真实，既能部署和重复运行，又能检验源码实现与实际生产可达路径是否一致。 | 调用契约、客户端 timeout、下游路径可达性，以及“代码中存在但业务路径未必经过”的情况。 |

三个项目共同形成互补验证面：Online Boutique 强调业务下游传播，OpenTelemetry Demo 强调多语言调用链和观测证据，Train Ticket 强调复杂业务路径和可达性核对。这个选择支持方法迁移性的工程验证，但不宣称三个项目构成所有微服务系统的统计代表样本。

### 3.2 三项目实验的实际执行步骤

阶段二使用的是 ChaosAtlas 初始框架，核心目标是证明“从真实 YAML 到可复核 issue”的闭环能够工作。每个项目按以下步骤执行：

1. **冻结项目事实**：固定仓库 commit、镜像、部署清单、命名空间、服务清单和业务入口，记录部署输入及相关文件 hash。
2. **建立项目地图**：整理 Deployment、Service、Pod、端口、业务入口、下游依赖、源码候选调用和日志/指标/trace 入口，形成项目级服务事实表。
3. **把 YAML 转成 TestNode**：读取真实 Chaos YAML 的 kind、action、selector、duration、intensity 和目标服务；再绑定业务路径、调用链位置、适用条件、预期现象和证据入口。YAML 只是故障意图，不直接等同于问题。
4. **建立局部影响子图**：连接故障目标、调用方、下游服务、数据库/消息队列、业务 oracle 和观测节点，先判断目标是否位于当前业务路径上。
5. **执行 baseline 和 gate**：确认无故障业务路径稳定通过，再检查目标存在性、selector、真实端口/路径、协议匹配、平台支持和 server-side dry-run；gate 失败单独记录，不伪造 runtime 结果。
6. **执行有界故障生命周期**：按 baseline -> 注入 -> 确认 injected -> 业务观测 -> 删除 Chaos 资源 -> 恢复 -> washout 执行，并记录资源状态、业务响应、事件和诊断日志。
7. **结合静态与运行时证据分析**：将源码/配置中的 timeout、fallback、错误处理和路径实现，与注入期间的 HTTP 响应、延迟、服务日志、trace 和 Kubernetes 事件对应起来。
8. **形成 issue 或保留 pending**：只有现象能够复现、业务影响明确、证据可以回链且没有把未经证明的内部机制写成事实时，才形成 GitHub issue；证据不足的结果保留为 pending 审核材料。

### 3.3 三项目的实际发现和外部结果

阶段二共形成 6 个已提交 GitHub issue。它们不是模型生成的“可能问题”清单，而是经过部署事实、业务 oracle、运行时故障和源码/日志分析后的外部报告：

| 项目 | 实际发现 | GitHub issue | 证据含义 |
|---|---|---|---|
| Online Boutique | `productcatalogservice` 不可用时首页返回 HTTP 500 | [`microservices-demo#3473`](https://github.com/GoogleCloudPlatform/microservices-demo/issues/3473) | 核心首页路径缺少等价降级，属于业务路径上的可复现故障传播。 |
| Online Boutique | checkout 在 payment、shipping 或 email 延迟/不可用时持续等待 | [`microservices-demo#3474`](https://github.com/GoogleCloudPlatform/microservices-demo/issues/3474) | 多个同步下游的等待和错误边界未形成一致的业务级保护。 |
| Online Boutique | paymentservice 延迟 2 秒后触发 probe，容器被重启 | [`microservices-demo#3475`](https://github.com/GoogleCloudPlatform/microservices-demo/issues/3475) | 探针阈值与服务实际处理/等待行为之间存在可观测的重启风险。 |
| OpenTelemetry Demo | shipping quote 失败时，错误报告错误地指向 email service | [`opentelemetry-demo#3818`](https://github.com/open-telemetry/opentelemetry-demo/issues/3818) | 故障传播后的错误服务标识与真实失败服务不一致，影响诊断和用户反馈。 |
| Train Ticket | 出站延迟 3 秒时，station lookup 超过客户端 timeout | [`train-ticket#311`](https://github.com/FudanSELab/train-ticket/issues/311) | 客户端 timeout 与下游调用延迟边界不协调，业务请求被截断或失败。 |
| Train Ticket | `/order/refresh` 可能跳过 `ts-order-service` 到 `ts-station-service` 的 station-name 查询 | [`train-ticket#310`](https://github.com/FudanSELab/train-ticket/issues/310) | 源码中存在的调用并不必然经过当前业务路径，暴露了调用路径可达性与预期不一致。 |

这 6 个 issue 的具体提交状态和链接由 `reporting/submission_index.md`、`reporting/tracking.md` 维护。issue 是否已经被上游修复或回复，不是 ChaosAtlas 发现能力成立的必要条件；论文应区分“我们发现并提交了问题”和“上游是否接受或修复问题”。

### 3.4 三项目共性结论与边界

三个项目虽然不是同一段代码，也不是同一个可直接合并的 bug，但在抽象层面暴露出同一个问题族：**跨服务同步调用的 timeout/deadline、降级和错误传播边界不完整或不一致**。当下游延迟、丢包、不可用或返回异常时，调用方可能等待过久、把故障继续传播到业务路径，或者报告错误的服务/错误类型。

跨项目证据表现为：

- **Online Boutique**：payment 延迟几乎全量传导到 checkout，丢包可持续到调用方 deadline；product catalog 不可用时核心首页没有等价降级。
- **OpenTelemetry Demo**：checkout 链路中的 payment/shipping 调用在特定路径上缺少有效的 timeout/deadline 保护，故障能够传播到业务调用方；shipping 失败还会产生错误服务标识。
- **Train Ticket**：station 查询延迟直接暴露客户端 timeout 边界；`/order/refresh` 的可达性分析则证明“有实现”不等于“生产路径一定经过”。

因此，三项目阶段支持的克制结论是：ChaosAtlas 能把 TestNode、调用契约、timeout/deadline、降级/错误边界、业务 oracle、源码核对和证据链分析模式迁移到不同真实项目，并发现可以提交、可以复现、可以回链的 issue。它是初始框架有效性验证，不是最终 Full 方法的完整性能对比；后续 Sock Shop 才加入知识闭环、项目知识视图和更严格的路径/契约约束。

## 4. Sock Shop 上的改进后 ChaosAtlas-full

### 4.1 为什么选择 Sock Shop

Sock Shop 是一个真实的微服务电商系统，包含 front-end、业务服务、数据库、消息队列和多条端到端业务路径。它同时满足：

- 有足够复杂的服务依赖，能够检验调用链和故障传播；
- 有明确的 front-end、catalogue、login、orders 等业务 oracle；
- 能在本地 Kubernetes/Chaos Mesh 中重复部署和恢复；
- 可以让 Full 和 Ablation 使用同一个项目版本、同一个 workload、同一个 runtime runner 和同一套生命周期规则。

因此，Sock Shop 是改进方法的受控真实项目验证场景。它不是为了代表所有生产系统，而是为了在真实微服务依赖中尽量隔离“知识库是否参与假设生成”这一方法变量。

### 4.2 改进内容：知识库和证据工程

Sock Shop 阶段真正增加的是知识和证据的可复用性，以及面向真实项目的决策约束：

1. **知识卡片版本化**：每张卡记录项目 commit、TestNode、局部影响子图、四层适用性、
   运行结果、反例、边界和 `next_evidence`，旧卡不被静默覆盖。
2. **知识回流和审计**：已验证实验可以把明确匹配的证据回填到选择经验、判定经验和防御
   模式，并在 audit log 中记录来源、原因和变更；冲突证据进入 `contested`，由人工裁决。
3. **可审计决策层**：selection experience 负责优先测试路径，defense pattern 负责降级或
   跳过有源码/运行证据支持的防御边，judgment experience 负责解释业务症状和契约边界。
   源码确认的 timeout、deadline、fallback 和业务 contract 可以作为硬过滤条件。
4. **项目知识投影**：Full 的上下文同时包含 Sock Shop 的部署/服务/业务 profile、项目调用
   链和真实路由、知识卡片、历史经验、适用条件和反例；每个输入都有来源路径和 hash。
5. **候选规范化**：模型输出先经过结构化解析、合法目标校验、故障协议匹配和 family 去重，
   保留原始成员、代表 mutation 和选择理由，不把模型提出的数量直接当成问题数量。

### 4.3 Full discovery 的详细步骤

1. **冻结项目输入**：固定 Sock Shop 部署、镜像/拓扑、服务清单、业务 oracle、源码和调用
   链证据；固定知识快照并记录每个来源文件的 SHA-256。
2. **建立项目影响子图**：将 TestNode 连接到真实 Deployment、Service、Pod、业务入口、
   下游依赖、实际端口和可观测节点；源码中存在但业务路径未经过的调用标记为未证实。
3. **检索知识视图**：按故障目标、调用方向、业务路径和协议读取知识卡片、选择经验、防御
   模式、判定经验、契约清单和历史反例。
4. **生成结构化假设**：模型每次输出目标服务、故障动作/目标、调用链位置、理由和预期
   观测；输出只作为候选，不直接执行。
5. **应用硬过滤**：检查目标是否存在、调用方向是否真实、端口/path 是否可信、协议是否
   匹配、是否有已知防御边界，以及当前平台是否具备注入前置条件。
6. **规范化和去重**：按目标、动作、调用位置、参数语义和时间/调度关系合并重复 family，
   保留原始成员列表、代表选择理由和未解决证据需求。
7. **编译并运行 gate**：将代表假设编译为 Chaos YAML，执行 namespace、selector、协议、
   server-side dry-run 和 platform gate；失败候选单独记录，不进入 runtime 分母。
8. **真实 runtime**：每个可执行 family 执行两次统一生命周期，确认 baseline、injected、
   observation、recovery、cleanup、washout 和诊断证据。
9. **人工复核和回流**：复核日志、事件、trace 状态、源码和报告 hash；只有人工审核后的
   经验才允许进入知识库，当前 Sock Shop 结果保持 pending。

### 4.4 Full 的当前结果

| 阶段 | 数量 |
|---|---:|
| 去重 fault family | 114 |
| 进入 runtime cohort | 96 |
| 完成两次真实注入 | 88 |
| 注入前 DNSChaos platform-blocked | 8 |
| 静态 gate 拒绝 | 18 |
| 稳定 weakness family | 15 |
| 不稳定 family | 3 |
| 两次均无业务影响 | 70 |

稳定弱点定义为两次 replicate 都是 `weakness_observed`。所以当前 Full 的主线结论是：在 88 个完成完整生命周期的 family 中，确认 15 个稳定 weakness；这不是 114/114 都完成了注入，也不是生成 114 个假设就等于发现 114 个问题。

## 5. Sock Shop 上的 ChaosAtlas-ablation（知识视图消融）

### 5.1 消融变量

最终 Ablation 保留与 Full 相同的 Sock Shop 项目 profile、业务 oracle、mutation 编译器、runtime runner、baseline、恢复、cleanup、washout 和两次 replicate 规则；只在 discovery 阶段移除 Full 的知识增强输入：

- 不提供知识库；
- 不提供选择经验、判定经验和防御模式；
- 不提供项目调用链证据；
- 不提供 Full 的候选假设；
- 不提供 Full 的生成轨迹或候选列表。

最终运行使用的固定语法示例 primer 只用于让模型理解合法 Chaos YAML 的基本结构，不提供 Sock Shop 的知识卡片、历史结果、调用链证据、弱点答案或 Full 的候选轨迹；该 primer 不作为本文的方法贡献。

### 5.2 Ablation discovery 的详细步骤

1. 固定与 Full 相同的 Sock Shop 项目 profile、业务 oracle、seed 和输入边界。
2. 读取固定语法 primer，记录 primer 与 manifest SHA-256；不读取任何知识库或项目历史结果。
3. 首轮向模型提供项目的公开运行边界和 primer，不提供知识卡片、选择经验、判定经验、
   防御模式、项目调用链或 Full 轨迹。
4. 模型自主生成结构化假设，输出目标服务、故障动作/目标、可推断的调用链位置和理由；
   调用链位置必须标注为模型推断或 unknown，不能伪装成项目证据。
5. 模型自主决定是否继续生成；同时记录 self-stop、time-cap、调用数、token 数和输入 hash。
6. 对 Ablation 自己生成的假设独立归一化和去重，形成 51 个 fault family；不使用 Full 的
   family 列表帮助去重。
7. 逐个执行同一套静态 gate 和 mutation 编译；不能执行的候选单独记录，不补造业务结果。
8. 每个 gate 通过的 family 执行两次完整 runtime，并使用与 Full 相同的稳定弱点判定。

### 5.3 Ablation 的当前结果

| 阶段 | 数量 |
|---|---:|
| 原始生成假设 | 458 |
| Ablation 独立去重 family | 51 |
| 完成两次真实注入 | 46 |
| 静态 gate 拒绝 | 5 |
| 稳定 weakness family | 9 |
| 不稳定 family | 0 |
| 两次均无业务影响 | 37 |

当前最终 Ablation 在 1419.047 秒 Full wall-clock 上限内运行了 734.188 秒后自然停止；这一记录说明它是 `self_stop`，而不是因为达到时间上限被截断。最终结果为 458 个原始假设、51 个 family、46 个完成 runtime family 和 9 个稳定 weakness。旧版 12 个假设、2 个弱点属于已替代历史，不能与当前结果相加。

## 6. 两种方法的共同 runtime 步骤

为了让差异集中在 discovery 输入，而不是执行器，Full 和 Ablation 的每个 mutation 都遵守同一条规则：

1. 读取并记录 YAML SHA-256。
2. 检查 namespace、kind、selector、目标 workload、mode 和动作。
3. 检查服务状态和业务 oracle。
4. 执行 5 次无故障 baseline journey，任何 baseline 失败都使该 mutation 无效。
5. apply Chaos 资源并确认真实进入 `injected` 生命周期。
6. 在注入期间执行业务 journey，按业务 contract 判断是否失败。
7. 删除 Chaos 资源；Schedule 还要删除其生成的子 PodChaos。
8. 检查资源 `absent_confirmed=true`，并做全局 Chaos 资源残留扫描。
9. 等待目标 Pod/资源恢复，并重新验证业务 journey。
10. 执行至少 60 秒、连续 10 次成功的 washout，排除残留故障和 stale port-forward 影响。
11. 捕获关键服务日志、events 和可用的 trace/Zipkin 证据。
12. 完成第二次 replicate；只有两次都确认业务弱点，才计入稳定 weakness。

共同 runtime 使两种方法在“如何执行一个已选假设”上保持一致；但它们不是同候选池实验，因为 Full 和 Ablation 的 discovery 输入、生成轨迹、候选数量和 family 集合不同。因此，15 和 9 是真实端到端能力的描述性结果，不是严格控制候选集合后的选择命中率。

## 7. 结果应如何理解

当前最稳妥的论文表述是：

> 在 Sock Shop 上，改进后的 ChaosAtlas-full 从项目知识视图、真实调用链、契约边界和历史证据出发，经过结构化假设生成、硬过滤、规范化去重和真实 runtime 验证，最终确认 15 个稳定 weakness family。移除知识卡片、经验库、调用链证据和 Full 生成轨迹，只保留公开项目边界与固定语法 primer 的 Ablation 仍生成并验证了 9 个稳定 weakness family。该结果说明知识增强方法能够支持更宽的候选探索和问题发现，但由于两边候选空间不同、样本规模较小且存在 gate/platform block，当前结果不能单独证明 Full 具有统计显著的稳定率优越性。

当前可以强调的贡献：

- 把单次实验结果提升为带来源、反例、适用边界和下一步证据需求的可迭代知识；
- 将选择经验、判定经验、防御模式和项目知识卡片组合成可审计的知识视图；
- 通过调用链、契约和真实路由核对，减少无效或不适用 mutation；
- 将调用链位置、适用条件和历史证据纳入可审计的假设生成上下文；
- 把生成、编译、gate、注入、恢复、清理和 washout 形成一条闭环；
- 用双 replicate 和业务 oracle 区分一次性现象、平台阻断、无影响和稳定真实弱点；
- 在真实项目中展示从框架验证到改进方法能力验证的阶段性演进。

当前不能写成：

- Full 找到 15 个问题，所以普遍优于 Ablation 的 9 个；
- 业务失败自动证明了某个具体内部根因；
- ChaosEater 的 2 个 availability/readiness 结果可以和 Full/Ablation 的业务 weakness 直接排名；
- pending 审核结果已经自动写入知识库。

## 8. ChaosEater 官方原生流程对比实验

### 8.1 对比实验的定位

ChaosEater 是论文中的外部方法参照。它与 ChaosAtlas 都在真实 Kubernetes 微服务系统上使用 LLM 生成故障假设并执行 Chaos Mesh，但两者的核心输入和测量层不同：ChaosEater 以稳态、故障生成、实验分析和 manifest 重配置为主；ChaosAtlas 以 TestNode、局部影响子图、适用性 gate、业务 oracle、证据链和知识闭环为主。

因此，本实验的目的不是把两个方法强行压成一个分数，而是回答两个问题：

1. 官方 ChaosEater 原生流程能否在当前真实 Sock Shop 环境中复现并产生可验证结果；
2. ChaosAtlas 的业务路径/调用契约测量层与 ChaosEater 的 availability/readiness 测量层分别能看到什么问题，二者是互补还是重复。

### 8.2 实验条件和公平性边界

| 维度 | 论文中的 ChaosEater 条件 | 当前原生复现条件 |
|---|---|---|
| 实现 | 官方 ChaosEater | 官方 ChaosEater，commit `47c4e44` |
| Sock Shop 入口 | 官方 `examples/sock-shop-2` | 相同入口 |
| 执行次数 | 5 次 | 5 次 |
| 集群/故障执行 | Kubernetes + Chaos Mesh | 真实 Kind/Kubernetes + Chaos Mesh |
| 模型 | `gpt-4o-2024-08-06` | DeepSeek |
| 参数 | `temperature=0`、`seed=42` | `temperature=0`、`seed=42` |
| LLM-as-a-judge | 论文脚本包含评审阶段 | `num_review_samples=0`，未运行评审阶段 |
| 输入边界 | ChaosEater 官方 manifest、prompt 和原生流程 | 只提供 ChaosEater 官方流程所需输入，不注入 ChaosAtlas 知识库 |

这意味着当前结果是**官方流程的真实原生复现**，但不是 GPT-4o 条件下的逐字逐结果复现。即使温度和 seed 相同，不同模型仍会改变假设内容、排序、停止轨迹和重配置建议；没有运行 judge 阶段也会改变最终评价报告。因此论文应把模型、judge、集群版本、镜像和网络条件作为复现差异明确报告。

### 8.3 ChaosEater 原生流程步骤

1. 固定官方 ChaosEater 仓库 commit、Sock Shop 示例入口、Kubernetes manifest 和运行环境。
2. 部署 Sock Shop，建立官方流程使用的 steady state，并确认服务能够正常运行。
3. 按官方流程让模型生成 steady-state hypotheses、场景假设和初始故障假设，记录原始响应和调用轨迹。
4. 将可执行故障假设转成 Chaos Mesh 实验，执行故障注入、系统观测和结果分析。
5. 让官方流程根据分析结果尝试提出 Kubernetes manifest 重配置建议；原始输出与实际运行结果分开保存。
6. 重复 5 次，汇总场景假设、steady-state 假设、可执行初始故障假设和实际可验证的弱点。
7. 由于当前没有运行 LLM-as-a-judge，只将原生执行输出和机器证据作为阶段性结果，不把它写成论文 judge 后的等价评分。

### 8.4 ChaosEater 当前复现结果

5 次原生运行得到：

| 结果层 | 数量 | 解释 |
|---|---:|---|
| 场景假设 | 4 | 官方流程生成的实验场景层候选。 |
| steady-state 假设 | 8 | 官方流程用于描述系统正常状态和可用性条件的候选。 |
| 可执行初始故障假设 | 12 | 经过原生流程后进入实际故障实验的初始假设。 |
| 实际确认的弱点类型 | 2 | 在当前环境和当前测量层下得到稳定、可验证的可用性/恢复现象。 |

这 2 类实际确认的弱点是：

1. **front-end 单副本导致单点故障**：杀掉唯一实例后，系统出现可观测的可用性下降；
2. **readiness/recovery 延迟过长**：故障后实例恢复和重新可用的时间过长，影响业务可用性窗口。

### 8.5 与 ChaosAtlas 结果的理解

ChaosEater 当前测量的是 availability/readiness 层，重点是“服务实例是否还在、是否达到 Ready、恢复是否及时”；ChaosAtlas Full/Ablation 主线测量的是业务 oracle 层，重点是“调用是否成功、请求是否超时、错误是否传播、业务 journey 是否失败”。因此：

- ChaosEater 的 front-end 单副本和 readiness/recovery 问题属于部署可用性/恢复层；
- ChaosAtlas 的 15 个 Full 稳定 weakness 和 9 个 Ablation 稳定 weakness 属于业务 mutation family 层；
- 两组数字不能直接相加、计算覆盖率或排序谁发现得更多；
- 当前实验更适合表述为两种测量层的分层参照：ChaosEater 能发现部署可用性弱点，ChaosAtlas 能沿业务路径验证调用契约和故障传播。

当前允许写成：ChaosAtlas 工作区完成了官方 ChaosEater 原生流程的真实复现；在当前 DeepSeek、Kind、Chaos Mesh 和未启用 judge 的条件下，ChaosEater 发现了 front-end 单副本和恢复/readiness 相关可用性弱点；该结果为 ChaosAtlas 的业务 oracle 和证据链方法提供了外部参照。

当前不能写成：已经完成 GPT-4o、同集群、同 judge、同测量层的严格三方法公平比较；ChaosAtlas 已经全面优于 ChaosEater；15、9、2 可以作为三种方法的统一弱点排名；或 `ChaosEater-adapter` 等同于官方完整 ChaosEater。`ChaosEater-adapter` 仍属于辅助历史材料，不能替代本节的官方原生结果。

## 9. 建议补充到论文主线的内容

当前主线已经有阶段划分、项目选择、方法演进、结果数字和边界，但建议再补充以下内容：

1. **单独的方法演进段落**：明确前三项目是初始框架验证，Sock Shop 是加入知识库迭代、经验库、契约/调用链核对和证据工程后的改进方法验证。
2. **Full/Ablation 输入差异表**：逐项列明知识卡片、选择/判定/防御经验、调用链证据、固定语法 primer、Full 生成轨迹、self-stop 和时间上限，防止读者误以为两边只差一个 prompt。
3. **统一 runtime 协议表**：列出 baseline、injection、recovery、cleanup、global residual scan、washout、diagnostics 和 replicate 规则。
4. **计数口径图**：明确 raw hypothesis -> deduplicated family -> gate-passed runtime -> completed replicate -> stable weakness 的关系。
5. **失败候选的处理**：将 static gate rejected、platform blocked、not reachable、no business impact 和 unstable 分开列出，不能把未注入候选当作负例。
6. **证据链与复现信息**：在每个 headline 数字后附 machine ledger、报告 SHA-256、日志/events/trace 入口和 `human_review=pending` 状态。
7. **公平性与限制**：说明 Full/Ablation 使用共同 runtime 协议，但不共享候选池、不使用相同 runtime 候选数量，因此当前比较是端到端描述性对照，不是严格同候选池 superiority test。
8. **结果解释层次**：主表先报告稳定 weakness 数量，问题面重合、ChaosEater 分层参照和 same-pool 结果放到补充材料或历史附录。

## 10. 当前证据入口

- 论文主线：`docs/CHAOSATLAS_PAPER_MAINLINE.md`
- Sock Shop 阶段审核：`docs/SOCK_SHOP_THREE_METHOD_STAGE_REVIEW_2026-08-16.md`
- Full/Ablation runtime runner：`tools/run_sock_shop_two_arm.py`
- Ablation discovery runner：`tools/run_sock_shop_ablation_discovery.py`
- 三项目 issue 证据：`reporting/submission_index.md`、`reporting/tracking.md`
