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

### 3.1 实验目的

Online Boutique、OpenTelemetry Demo 和 Train Ticket 的作用是验证初始框架，而不是验证后续的知识增强方法。三个项目分别提供：

| 项目 | 框架验证重点 |
|---|---|
| Online Boutique | 电商 checkout 路径、同步下游故障传播、timeout/deadline 和降级边界 |
| OpenTelemetry Demo | 多语言服务、trace 证据、错误传播和错误服务标识一致性 |
| Train Ticket | 复杂业务路径、客户端 timeout、源码实现与实际可达路径的一致性 |

三个项目共同验证：ChaosAtlas 能把真实部署事实、源码/调用链和 Chaos 运行证据结合起来，形成可提交、可复现的 issue。阶段二共形成 6 个已提交 GitHub issue，分布为 Online Boutique 3 个、OpenTelemetry Demo 1 个、Train Ticket 2 个。

### 3.2 阶段二的执行步骤

1. 固定项目仓库、commit、镜像和部署清单。
2. 读取真实 YAML，提取 kind、action、selector、duration、intensity 和目标服务。
3. 建立项目服务清单、业务入口、调用关系和观测入口。
4. 为候选故障建立 TestNode 和局部影响子图。
5. 运行 baseline，确认业务路径在无故障时稳定通过。
6. 对候选 mutation 做静态检查、目标核对和平台前置条件检查。
7. 按 baseline -> 注入 -> 观测 -> 删除 -> 恢复 -> washout 执行。
8. 分析服务日志、HTTP 响应、指标、事件和 trace，区分业务现象与具体根因。
9. 对可复现、证据充分的问题形成 GitHub issue；不能充分证明的结果保留为 pending 审核材料。

阶段二的贡献是验证“框架是否能工作”，包括 TestNode、调用链位置、适用性门禁、业务 oracle 和证据链；它还为后续知识卡片、契约规则、反例边界和跨项目选择经验的迭代提供了真实证据。

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

## 8. 建议补充到论文主线的内容

当前主线已经有阶段划分、项目选择、方法演进、结果数字和边界，但建议再补充以下内容：

1. **单独的方法演进段落**：明确前三项目是初始框架验证，Sock Shop 是加入知识库迭代、经验库、契约/调用链核对和证据工程后的改进方法验证。
2. **Full/Ablation 输入差异表**：逐项列明知识卡片、选择/判定/防御经验、调用链证据、固定语法 primer、Full 生成轨迹、self-stop 和时间上限，防止读者误以为两边只差一个 prompt。
3. **统一 runtime 协议表**：列出 baseline、injection、recovery、cleanup、global residual scan、washout、diagnostics 和 replicate 规则。
4. **计数口径图**：明确 raw hypothesis -> deduplicated family -> gate-passed runtime -> completed replicate -> stable weakness 的关系。
5. **失败候选的处理**：将 static gate rejected、platform blocked、not reachable、no business impact 和 unstable 分开列出，不能把未注入候选当作负例。
6. **证据链与复现信息**：在每个 headline 数字后附 machine ledger、报告 SHA-256、日志/events/trace 入口和 `human_review=pending` 状态。
7. **公平性与限制**：说明 Full/Ablation 使用共同 runtime 协议，但不共享候选池、不使用相同 runtime 候选数量，因此当前比较是端到端描述性对照，不是严格同候选池 superiority test。
8. **结果解释层次**：主表先报告稳定 weakness 数量，问题面重合、ChaosEater coverage 和 same-pool 结果放到补充材料或历史附录。

## 9. 当前证据入口

- 论文主线：`docs/CHAOSATLAS_PAPER_MAINLINE.md`
- Sock Shop 阶段审核：`docs/SOCK_SHOP_THREE_METHOD_STAGE_REVIEW_2026-08-16.md`
- Full/Ablation runtime runner：`tools/run_sock_shop_two_arm.py`
- Ablation discovery runner：`tools/run_sock_shop_ablation_discovery.py`
- 三项目 issue 证据：`reporting/submission_index.md`、`reporting/tracking.md`
