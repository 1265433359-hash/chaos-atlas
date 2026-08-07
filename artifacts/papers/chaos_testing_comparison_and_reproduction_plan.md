# 混沌测试相近方法、对比基线与复现路线

更新日期：2026-08-06

## 1. 先说结论

你记得没错，[ChaosEater](https://arxiv.org/abs/2501.11107) 是目前与你们方法最接近的公开工作之一，而且应该作为论文中的首要对比对象。但两者并不等价：ChaosEater 的核心是用多 LLM agent 自动走完 `假设 -> 实验 -> 分析 -> 修改 K8s manifest` 的单轮 CE cycle；你们现在真正有区分度的部分，是从真实 Chaos YAML 出发，用测试节点局部 CFG/DFG、运行时适用性门禁、证据绑定判定和跨轮知识库去发现隐藏问题并避免无效/重复实验。

ChaosEater 官方项目页明确把以下内容列为局限或未来方向：

- 对已有一定韧性的系统，隐藏问题发现能力有限；
- 目前只修改 K8s manifest；
- 未来需要 `LLMs x Graphs` 来处理跨代码依赖；
- 未来需要长期多轮 CE cycle 和历史管理；
- 目前缺少系统化 CE 数据集、benchmark 和量化指标。

这几条与本项目的局部图、代码/运行时证据、知识卡、停止规则、三个真实项目案例高度对应。论文定位应避免写成“我们也做了自动化混沌工程”，而应写成：

> 面向隐藏韧性问题发现的、测试节点中心且证据绑定的混沌测试方法；它在执行前验证业务可达性，在执行后区分响应保持、性能退化、客户端超时、服务端晚完成、偶然恢复和测试无效，并把限定条件反馈到下一轮选择。

## 2. 用户给定 PDF 的身份

用户文件虽然命名为 `ChaosEater_Extended_arXiv2501.11107`，但 PDF 元数据和正文实际对应 6 页短版：

- 标题：*LLM-Powered Fully Automated Chaos Engineering: Towards Enabling Anyone to Build Resilient Software Systems at Low Cost*
- arXiv：[`2511.07865`](https://arxiv.org/abs/2511.07865)
- 会议：ASE 2025 NIER
- 短版在参考文献中把 [`2501.11107`](https://arxiv.org/abs/2501.11107) 作为 114 页扩展版引用。

本项目已保存官方扩展版 v2：`artifacts/papers/ChaosEater_arXiv2501.11107v2.pdf`，并提取了同名文本文件，后续复现应以扩展版和作者项目页为准。

## 3. 相近方法分层

### 3.1 第一层：直接竞争方法

| 方法 | 核心方法 | 与本项目重叠 | 关键差异 | 可复现性 |
|---|---|---|---|---|
| [ChaosEater](https://arxiv.org/abs/2501.11107) | 多 LLM agent 自动定义 steady state、生成 Chaos Mesh Workflow、分析并修改 K8s manifest；用 Validation as Code 判定 | LLM、Chaos Mesh、自动计划/执行/分析、反馈循环 | 没有测试节点局部 CFG/DFG 和证据知识库；官方承认隐藏问题发现较弱 | **高**：作者代码、项目页、完整 prompt 和案例公开 |
| [Cast](https://arxiv.org/abs/2602.00972) | 生产流量重放；按 trace 长度、组件多样性、时延做复杂度排序；细粒度 endpoint 注入；数据流依赖优先；多维 Oracle | 调用图/数据流、候选选择、三阶段执行、结果判定 | Java agent + 生产流量；主要是 application-level faults，不是 Chaos YAML/CRD；没有知识库反馈 | **低到中**：论文很完整，但未发现公开实现，只能做 Cast-style 重实现 |
| [FastFI](https://arxiv.org/abs/2601.14800) | trace 转 monotone CNF；DFS 枚举最小组合故障；用运行反馈动态扩展故障大小；Max-SAT 选择关键 API | 依赖路径、组合故障、候选剪枝、用更少实验发现高价值问题 | 侧重请求级 API 组合故障和调用点加固；不处理 YAML 语义/控制器/恢复证据 | **高**：论文声明代码和 benchmark 公开，[仓库](https://github.com/TanYuzhen/TOSEM-FastFI-Code) 包含同类微服务基准 |
| [SequenceFI](https://arxiv.org/abs/2607.20050) | 从消息 send/receive trace 合成 occurrence-sensitive temporal guard，在准确执行时序下注入 | 局部执行路径、时序、状态改变后的隐藏问题 | 重点是“何时注入”，不做全 CE cycle、知识反馈或 K8s manifest 诊断 | **中低**：论文清楚，但截至检索时未发现公开代码 |

Cast 是最强概念近邻；FastFI 是最重要的可执行问题发现效率基线；ChaosEater 是最重要的 LLM 自动 CE 基线。

### 3.2 第二层：结构、观测和恢复对照

| 方法 | 用途 | 适合作为什么对照 |
|---|---|---|
| [Model Discovery and Graph Simulation](https://arxiv.org/abs/2506.11176) | 从 Jaeger/配置发现服务依赖图，以 replica + fail-stop Monte Carlo 估计可用性并减少 live chaos 范围 | `全局服务图/模拟` 对 `测试节点局部 CFG/DFG + live evidence`；有 [Zenodo artifact](https://doi.org/10.5281/zenodo.15396047) |
| [OXN](https://arxiv.org/abs/2407.09644) | 同时改变故障和 observability 配置，系统评估观测设计 | OTel Demo 中“trace 能捕获但没有自动告警”的观测性对照 |
| [CHESS](https://arxiv.org/abs/2303.07283) | 用混沌工程系统化评价 self-adaptive/self-healing 系统 | “是否真正恢复”与“只是重启/逃逸注入”的恢复判定对照 |
| [MicroRes](https://doi.org/10.1145/3650212.3652131) | 通过 degradation dissemination indexing 做微服务韧性画像 | 故障传播范围、关键服务/调用选择对照 |
| [Filibuster](https://doi.org/10.1145/3472883.3487005) | 请求级 service fault injection，系统探索 RPC 失败 | FastFI/LDFI 路线的基础基线；适合解释组合故障搜索脉络 |

### 3.3 第三层：更低层故障模型

- [ChaosOrca](https://arxiv.org/abs/1907.13039)：不改应用，在容器系统调用层注入错误并多层监控。
- [Phoebe](https://arxiv.org/abs/2006.04444)：从生产中的系统调用错误生成现实错误模型，再自动实验。
- [ChaosMachine](https://arxiv.org/abs/1805.05246)：在 JVM try-catch 粒度分析和证伪异常处理能力。

这些方法可以证明“细粒度注入能找到普通 Pod/Network chaos 找不到的问题”，但它们与本项目的故障层不同，不建议作为主排名对手。

### 3.4 相关但不适合作为当前主基线

- [Scaling Mobile Chaos Testing with AI-Driven Test Execution](https://arxiv.org/abs/2602.06223)：LLM 移动端探索 + 服务级故障注入，工业规模很强，但依赖移动 App、DragonCrawl、uHavoc 和 Uber 内部基础设施，与当前后端 K8s 项目不公平。
- AIOpsLab/ITBench：重点是故障后的定位和修复 agent 评测，不是混沌实验选择本身。
- 各类 Chaos Mesh、Litmus、Gremlin、Chaos Monkey：主要是注入平台，不是“如何选测试并发现更好问题”的方法基线。

## 4. 最推荐的对比组合

不要一次复现十个系统。论文主实验建议采用下面六档：

| 编号 | 条件 | 目的 |
|---|---|---|
| B0 | Random/Template：从同一可用故障集合随机或按 YAML 频率选择 | 最低基线，证明提升不是因为多跑实验 |
| B1 | ChaosEater | 对比 LLM 全自动 CE cycle 和隐藏问题发现能力 |
| B2 | FastFI | 对比组合故障搜索效率、独立问题收益和关键 API 定位 |
| B3 | Cast-style selector | 对比 trace complexity + 数据流优先的候选选择；必须标注为论文规则重实现 |
| B4 | Graph-only | 全局服务依赖图 + replica/fail-stop 或 YAML + service graph，不进入局部 CFG/DFG |
| Ours | 完整方法 | YAML + 局部图 + runtime gate + evidence oracle + KB feedback |

再做四个内部消融：

1. `YAML only`；
2. `YAML + global service graph`；
3. `YAML + test-node local graph`；
4. `YAML + local graph + runtime gate + knowledge base`。

这组实验能直接回答：提升来自 LLM、图、运行时门禁，还是知识反馈？

## 5. 公平实验协议

### 5.1 固定实验对象

优先选择当前已经有运行证据的两个共同基准：

- Train Ticket：固定 commit `313886e99befb94be6cd45f085c98e0019f59829`；
- Online Boutique：固定当前已使用 commit `9a4616e7`；
- OpenTelemetry Demo 作为外部泛化项目，主要验证观测和根因证据，不要求所有外部方法都原生支持。

FastFI 原论文也使用 Train Ticket 和 Online Boutique，因此这两个项目最适合做同项目 head-to-head。

### 5.2 固定可用信息

为了不让某个方法吃到更多信息，定义三档输入：

- I0：YAML/manifests + API/workload；
- I1：I0 + 静态服务图/调用候选；
- I2：I1 + runtime trace/log/metrics + 历史知识卡。

每个方法只在自己声明的输入档运行；结果表必须标注输入档，不能把使用生产 trace 的 Cast/FastFI 与只看 YAML 的基线当作同等信息条件。

### 5.3 固定故障和预算

- 单项目同一 wall-clock budget，例如 6 小时；
- 同一最大实验次数，例如 40 次有效注入；
- 同一 fault family 交集：network delay/loss、CPU stress、Pod failure；
- 同一单目标、duration、warm-up、请求数、并发、timeout 和恢复窗口；
- 同一安全门禁、namespace、kill switch、cleanup 和 `injectedCount >= 1` 规则；
- 每个方法 5 个随机种子；确定性方法也重复 5 次验证环境噪声。

外部方法只负责“选哪个节点/何种故障/何时注入”，统一由本项目 runner 执行 baseline -> injection -> recovery。这样不会把执行器可靠性误计为选择算法收益。

### 5.4 什么算一个新问题

一个问题必须同时满足：

1. **Reachable**：业务入口、目标和路径真实可达；
2. **Injected**：运行时确认注入生效，而不是仅 apply/selected；
3. **Causal**：基线、注入、恢复或反事实重放支持因果关系；
4. **Reproducible**：独立窗口重复出现，或满足预注册的确定性时序；
5. **Impactful**：违反响应契约、SLO、恢复目标、数据一致性或观测要求；
6. **Distinct**：按根因机制去重，而不是把同一 timeout 缺口在五个 endpoint 上算五个 bug；
7. **Evidence-bound**：有配置、代码/trace、运行时间线和 cleanup 证据。

问题类别建议固定为：

- `confirmed_unique_issue`
- `confirmed_duplicate_mechanism`
- `invalid_unreachable`
- `invalid_not_injected`
- `environment_blocked`
- `insufficient_evidence`

### 5.5 主要指标

| 指标 | 定义 |
|---|---|
| Unique Confirmed Issues | 去重后的独立确认问题数 |
| Severity-weighted Yield | `sum(severity weight)` / 有效实验数或小时 |
| Issue Precision | `confirmed_unique / reported_candidates` |
| Time to First Confirmed Issue | 从开始到第一个确认问题的时间 |
| Experiments per Unique Issue | 有效注入数 / 独立问题数 |
| Invalid Injection Rate | 不可达、未注入、平台阻断占比 |
| Duplicate Experiment Rate | 重复已知机制或已闭环节点占比 |
| Evidence Completeness | 配置/路径/注入/Oracle/恢复五类证据覆盖率 |
| RCA Accuracy | 盲评下根因标签 Top-1/Top-3 准确率 |
| Recovery Misclassification | 把逃逸注入、重启副作用或无观测误判为恢复的比例 |
| Safety Gate Utility | 执行前正确拦截危险或无效计划的比例 |

“找到更多问题”只作为结果之一，论文主张最好写成“在固定预算下提高独立确认问题收益并降低无效/重复实验”，更难被审稿人质疑刷数量。

## 6. ChaosEater 复现路线

### 6.1 先做原论文复现，不要直接改到 Train Ticket

原论文环境和参数：

- 单机 kind 开发集群；
- ChaosEater Web 应用是 Docker 中的 Streamlit；
- 通过 Kubernetes API 部署、监控和注入；
- 输入是 zip 后的 Skaffold project，根目录必须有 `skaffold.yaml`；
- Nginx 与 Sock Shop 两个案例；
- `gpt-4o-2024-08-06`，temperature `0`，seed `42`；
- chaos experiment 不超过 1 分钟；
- 每个系统 5 次单 CE cycle。

复现验收：

- Nginx 中识别 `restartPolicy: Never`，并将 Pod 改为多副本 Deployment；
- Sock Shop 中识别 front-end 单副本问题并增加副本；
- 每轮保存 hypothesis、VaC、Chaos Workflow、实验日志、修改 diff、token、cost、time；
- 报告 5 次中的完成率和正确重配置率，不只展示最佳一次。

模型版本若已不可用，必须分成两组：`exact-model replication` 和 `current-model reproduction`。不能用新模型结果直接宣称复现了论文数值。

### 6.2 再做同项目适配

为 Train Ticket、Online Boutique、OTel Demo 分别补最小 `skaffold.yaml`，把当前固定 manifest 和 workload 放入 zip 输入。对 ChaosEater 只提供它原生允许的信息，不提供本项目知识卡。

建议每项目限定：

- 最多 3 个 steady states；
- 只允许 PodChaos/NetworkChaos/StressChaos 的交集；
- 单目标、短 duration、隔离 namespace；
- 禁止自动修改业务代码；
- 每项目 5 次、相同时间和实验预算。

重点观察 ChaosEater 是否会：

- 把 `HTTP 200` 误当完整防御；
- 对不可达 Order->Station 路径继续注入；
- 把 `Selected=true, injectedCount=0` 当有效实验；
- 把探针重启后的注入逃逸当自愈；
- 发现 missing-timeout、observability-no-alert 等代码/运行时问题。

这些不是故意设陷阱，而是本项目已经闭环的真实反例。

## 7. FastFI 复现路线

FastFI 是最值得先跑的外部问题发现基线，因为：

- 作者提供代码和 benchmark；
- 原论文包含 Online Boutique、Train Ticket、Sock Shop、Hotel Reservation；
- 评价目标直接是组合故障发现效率和关键 API 定位；
- 与本项目“局部路径 + 反馈剪枝”的研究问题足够接近。

建议步骤：

1. 在独立分支/环境运行作者仓库的最小 Online Boutique 请求；
2. 验证 trace 收集、CNF 构造、DFS 解、故障注入和恢复能完整闭环；
3. 再复现 Train Ticket 的单请求场景；
4. 将 FastFI 输出的 API 组合转换为统一的实验计划 schema；
5. 用本项目同一个 runner/Oracle 执行，比较有效注入、独立问题、实验数和时间；
6. 最后才扩展到本项目现有三个完整业务路径。

不要一开始就重实现 LDFI/IntelliFI/MicroFI。FastFI 论文说明这些基线缺少完整实现，作者也是按论文重实现；如果论文需要它们，先把重实现标为 secondary evaluation。

## 8. Cast-style 与 Graph-only 复现

### 8.1 Cast-style selector

Cast 没有可确认的公开完整实现，因此命名必须是 `Cast-style` 或 `Cast-inspired`。只复现可验证规则：

```text
trace_score = w1 * span_count
            + w2 * component_diversity
            + w3 * normalized_duration
```

然后：

- 每个接口选择最高复杂度 trace；
- 同一 endpoint 重复出现时优先最后一次；
- producer-consumer 链优先 producer；
- dual-write 优先第二/异步写；
- 用相同 fault budget 选 top-K。

这可以直接与本项目的 `reachability x impact x uncertainty x evidence` 排序比较。

### 8.2 Graph-only

利用 OTel/Jaeger 已有 trace 导出全局服务依赖图，或读取静态 service graph；只保留服务拓扑和副本数，做 fail-stop 可用性估计或关键节点排序。然后在相同 K 下运行 live chaos。

它回答一个关键消融问题：局部 CFG/DFG 和控制/数据/恢复边，是否真的比全局服务图多发现问题，还是仅增加了复杂度？

## 9. 当前环境的复现前置项

本次受限会话只确认到：

- `kubectl` client v1.36.1 可见；
- Docker client 29.6.1 可见，但沙箱不能读取用户 Docker 配置或连接引擎；
- kubeconfig 同样被沙箱拒绝读取，不能据此判断真实集群状态；
- `kind`、`helm`、`skaffold` 当前不在 PATH。

实际复现前先做一次主机侧前置检查，并记录版本：Docker、kind、kubectl、helm、skaffold、Chaos Mesh、Python、LLM API。Windows/WSL2 可先复现 PodChaos/NetworkChaos；涉及 HTTPChaos 时，当前项目已经证明 WSL2 缺少所需 ebtables 路径，应改用原生 Linux/具备相应内核模块的 VM，而不是继续换 kind 集群。

## 10. 推荐执行顺序

1. **第 1 周**：原样复现 ChaosEater 的 Nginx/Sock Shop；跑通 FastFI 的 Online Boutique 最小案例。
2. **第 2 周**：统一实验计划 schema 和 runner；将 ChaosEater/FastFI 接到 Train Ticket、Online Boutique。
3. **第 3 周**：跑 B0/B1/B2/B3/B4/Ours 六档和四个消融，完成盲标与问题去重。
4. **第 4 周**：统计 unique issue yield、Precision、time-to-first、invalid/duplicate rate、RCA 和 evidence completeness。
5. **第二阶段**：若主实验已经稳定，再加入 SequenceFI 时序故障和 OXN observability 对照。

最先做 ChaosEater + FastFI，不建议先投入 SequenceFI 或 Cast 全量重实现。前两者已经足够支撑一篇论文中“LLM 自动 CE”和“高效组合故障发现”两条主对比线。

## 11. 可写入论文的差异化表述

保守而有力的版本：

> Unlike end-to-end LLM-based chaos engineering systems that primarily automate a single hypothesis-experiment-improvement cycle over Kubernetes manifests, our method centers each candidate fault as a test node, constructs an evidence-annotated local control/data-flow slice, validates runtime applicability before execution, and feeds both positive and negative evidence into subsequent test selection.

结果型主张应等实验完成后再写成：

> Under an equal experiment budget, the full method found more independently confirmed resilience issues while reducing unreachable, non-injected, and duplicate experiments compared with YAML-only, graph-only, ChaosEater, and FastFI baselines.

在数据出来之前，不要提前写“比 ChaosEater 找到更多 bug”。当前证据足以说明方法差异和可检验假设，尚不足以说明外部基线上的统计优势。

