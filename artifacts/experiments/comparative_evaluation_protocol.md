# 混沌测试方法公平对比实验协议

版本：v1.0  
日期：2026-08-07

## 1. 最终要回答的问题

本实验不比较“谁生成的 YAML 多”，而比较：

> 在相同候选预算、执行环境和最终判定标准下，哪种方法能发现更多独立、可复现、有业务影响且证据完整的韧性问题，同时产生更少无效、重复和误判实验？

预注册六个研究问题：

| RQ | 问题 | 主要结果 |
|---|---|---|
| RQ1 Effectiveness | 固定预算下谁发现的问题更多、机制更丰富？ | `Unique Confirmed Issues @ K`、机制家族数 |
| RQ2 Efficiency | 谁更快、用更少实验找到问题？ | discovery curve、首个问题时间、每问题实验数 |
| RQ3 Validity/Safety | 谁更少生成不可达、未注入、环境阻断或重复实验？ | invalid/duplicate rate、gate precision/recall |
| RQ4 Diagnosis | 谁能正确解释根因和恢复行为？ | RCA Top-1、恢复误判率、证据完整度 |
| RQ5 Components | 局部图、门禁、运行证据、知识反馈分别贡献多少？ | 四级消融的增量差异 |
| RQ6 Generalization | 结果能否迁移到未参与方法开发的项目？ | held-out 项目上的 RQ1-RQ4 |

主要假设只有一个：完整方法在 `K=10` 个提交候选内得到更高的独立确认问题数，并降低无效与重复比例。其他指标作为解释性或次要结果，避免事后挑选有利指标。

## 2. 不能直接混在一起比较的内容

ChaosEater、FastFI、Cast 和本项目原生故障层不同：

- ChaosEater 是端到端 LLM CE cycle，还会修改 K8s manifest；
- FastFI 主要在请求/API 调用点搜索组合故障；
- Cast 使用生产 trace 和 endpoint/data-flow 选择；
- 本项目从 Chaos YAML、局部 CFG/DFG 和运行证据选择 K8s/服务级故障。

因此必须分成三个评价轨道：

| 轨道 | 目的 | 能否用于主排名 |
|---|---|---|
| T1 原生端到端复现 | 按作者原设置运行，回答实际部署时各系统能完成什么 | 只做描述性比较，不直接宣称算法优劣 |
| T2 统一候选接口 | 各方法输出同一格式的排序候选，由同一 runner 和 Oracle 执行 | **论文主排名** |
| T3 本方法消融 | 在同一输入和实现中逐步增加局部图、门禁、知识反馈 | **用于解释提升来源** |

T1 和 T2 的名称必须分开。例如，经过统一接口适配的结果写 `ChaosEater-adapter`、`FastFI-adapter`、`Cast-style`，不能写成原作者系统的原样结果。

## 3. 参与方法

### 3.1 核心组

| ID | 方法 | 允许输入 | 在统一轨道中的职责 |
|---|---|---|---|
| M0 | Random/Template | I0 | 从相同候选宇宙随机或按真实 YAML 频率选择 |
| M1 | ChaosEater-adapter | I0 | 用其假设/实验 agent 产生候选，再映射到公共故障域 |
| M2 | FastFI-adapter | I0+I2 | 根据 trace/CNF 搜索关键 API 或组合，再映射到公共故障域 |
| M3 | Graph-only | I0+I1-global | 按全局服务图中心性、调用频率或模拟风险排序 |
| M4 | Ours-full | I0+I1-local+I2；历史条件另列 | 局部 CFG/DFG、runtime gate、证据分类和反馈选择 |

### 3.2 可选组

| ID | 方法 | 用途 |
|---|---|---|
| M5 | Cast-style | 若时间允许，比较 trace complexity + data-flow 排序 |
| A0 | YAML-only | 本方法内部消融起点 |
| A1 | YAML + global graph | 判断全局图是否已经足够 |
| A2 | YAML + local graph | 隔离测试节点局部 CFG/DFG 的贡献 |
| A3 | A2 + runtime gate | 隔离执行前可达性/注入器门禁的贡献 |
| A4 | A3 + evidence + KB | 完整方法；比较跨轮重复率和边际收益 |

时间有限时，先完成 M0/M1/M2/M3/M4。Cast-style 不应挤占 ChaosEater 和 FastFI 的复现时间。

## 4. 输入权限分档

| 档位 | 内容 |
|---|---|
| I0 | 固定 commit、部署 manifest、真实 YAML、工作负载接口、公共故障候选目录 |
| I1-global | 静态或 trace 聚合后的服务级调用图，不含函数/分支 |
| I1-local | 目标测试节点周围的函数、调用、控制、数据、恢复和观测切片 |
| I2 | 当前目标的运行 trace、日志、指标和基线，不含既有结论 |
| I3 | 之前实验的标准化结果或知识卡 |

规则：

- 每张结果表必须显示方法实际使用的输入档；
- 冷启动条件禁止目标项目 I3；
- 跨项目知识迁移只允许读取其他项目的卡片，并单独标为 `cross-project warm start`；
- 同一方法不能在看到其他方法结果后重新生成候选；
- LLM 的模型 ID、temperature、seed、system prompt、token 和费用全部保存。

输入信息不同是方法能力的一部分，但不能隐藏。因此主结果同时报告效果和输入/运行成本，而不是只给一个不透明综合分数。

## 5. 被测项目和数据切分

### 5.1 现有项目的角色

| 项目 | 固定版本 | 用途 |
|---|---|---|
| Train Ticket | `313886e99befb94be6cd45f085c98e0019f59829` | 已知控制、17 个未运行样本的半盲池、LOPO 知识迁移 |
| Online Boutique | `9a4616e7` | 已知控制、真实 checkout 故障、探针/降级/多故障机制 |
| OpenTelemetry Demo | `2e72d8bc` | 已知控制、trace 证据、观测性和协议差异 |

这三个项目已经被本项目研究过，不能再称为真正的 blind discovery。可以做：

- 已知问题召回和误判测试；
- 把目标项目知识卡全部隐藏后的 leave-one-project-out 迁移；
- Train Ticket 17 个未执行样本的 `semi-blind execution`。

### 5.2 必须增加 held-out 项目

要写“发现新问题能力更好”，至少增加一个在协议冻结前无人查看源码、trace 和 issue 的项目；推荐两个：

1. Hotel Reservation：FastFI 有同类 benchmark 经验，适合作为 API FI 对照；
2. Sock Shop：ChaosEater 原论文使用过，适合作为 LLM CE 对照，但必须披露它对该项目已有先验优势。

若资源只允许一个，优先部署成功率更高的那个，并在打开源码前完成：commit 固定、实验预算、工作负载、候选 fault family、随机种子和评审规则注册。

项目级泛化的统计单位是“项目”，不是同一项目重复运行次数。只有一个 held-out 项目时，应写 case-study evidence，不能写广泛统计泛化结论。

## 6. 两套测试集

### 6.1 Track K：已知控制集

用于检查方法是否能找对问题、识别非问题和避免错误恢复结论，不计入“新发现”数量。

| ID | 场景 | 预期标签 |
|---|---|---|
| K1 | Train Ticket Station 延迟阶梯和 3s 边界 | 延迟退化；边界处客户端超时、服务端晚完成 |
| K2 | Train Ticket Order->Station 被注释的调用 | 不可达，不应执行或宣称防御 |
| K3 | WSL2 HTTPChaos/ebtables 前置缺失 | 环境阻断，不应算应用问题或防御 |
| K4 | Online Boutique payment 延迟/丢包 | 缺少 timeout，延迟传播/挂起 |
| K5 | Online Boutique productcatalog pod failure | 核心路径级联失败 |
| K6 | Online Boutique adservice 缺失 | 非核心路径正确降级，负控制 |
| K7 | Online Boutique probe restart escape | 注入逃逸，不是真正自愈 |
| K8 | OpenTelemetry Demo payment/email 故障 | HTTP/gRPC 故障语义差异，延迟或挂起传播 |
| K9 | OpenTelemetry Demo Jaeger 捕获故障但无自动告警 | 可观测但运营闭环缺失 |

Track K 报告 `Recall@K`、错误问题率、恢复误判率和 RCA 准确率。

### 6.2 Track H：隐藏问题发现集

包含：

- held-out 项目的自然问题；
- Train Ticket 尚未执行的 17 个样本，但标为 semi-blind；
- 可选的人工植入 vulnerability/defense 成对变体。

推荐的成对变体是：无 timeout vs 有界 timeout/fallback、单副本 vs 多副本、核心路径无降级 vs 有界降级、过激探针 vs 合理探针、无告警 vs 有告警、不可达调用 vs 可达调用。变体只用于已知 ground truth 的召回/误报实验，必须和自然问题分开统计。

## 7. 公共候选接口

所有 T2 方法必须输出排序后的候选计划；方法不能直接控制集群。最小字段如下：

```json
{
  "plan_id": "M4-HR-seed42-001",
  "method": "ours-full",
  "project_id": "hotel-reservation",
  "replicate": 1,
  "rank": 1,
  "workload_id": "reserve-hotel",
  "target": {
    "service": "reservation",
    "endpoint_or_edge": "frontend->reservation",
    "direction": "to"
  },
  "fault": {
    "family": "latency",
    "intensity": "500ms",
    "duration": "45s",
    "mode": "one"
  },
  "trigger": "during_workload",
  "predicted_invariant": "p95 latency remains below the registered deadline",
  "predicted_root_cause": "missing bounded downstream timeout",
  "information_tier": ["I0", "I1-local", "I2"],
  "evidence_refs": [],
  "generation_time_ms": 0,
  "model_tokens": 0
}
```

Runner 负责：schema 校验、runtime gate、baseline、等待 `injectedCount >= 1`、业务请求、恢复、资源删除和标准化分类。方法只能接收预先允许的标准化反馈，不能读取其他方法的目录。

## 8. 公共故障域

### 8.1 主排名故障域

只使用所有核心方法都能合理表达的服务边故障：

- latency：`100ms`、`500ms`、`2000ms`；
- unavailable：100% loss、连接拒绝或等价 API failure，适配器必须记录具体映射；
- 可选 abort/error：只有所有方法和环境都支持时加入。

目标单位固定为业务工作负载中的服务或调用边。组合故障最多两个目标，且只有单故障阶段稳定后才开放。

### 8.2 K8s-native 补充故障域

Pod kill、CPU stress、单副本、探针和 manifest 改进单独比较 Random、ChaosEater、Graph-only 和 Ours。FastFI/Cast 不支持这些类型时记 `out_of_domain`，不能记失败。

HTTPChaos 在当前 WSL2 平台不进入主排名。它只作为门禁负控制；迁移到具备 ebtables 前置条件的原生 Linux 后，才作为正式故障重新注册。

## 9. 预算和实验矩阵

### 9.1 预算单位

每个 `方法 x 项目 x replicate` 使用：

- 候选预算：最多 `K=10` 个提交计划；
- 时间预算：最多 3 小时 discovery wall clock；
- 每个候选最多一次 discovery 注入；
- blocked、不可达、schema 错误和未注入都占一个候选名额，不允许免费补位；
- 发现疑似问题后，另用确认预算独立重复 3 次；确认运行不占 discovery K，但单独报告成本；
- 任一预算先耗尽即停止。

这种双记录方式同时保留“选择质量”和“真实验证成本”：不会因为一个方法发现的问题多、需要重复确认，就反而在 discovery 排名中受罚。

### 9.2 最小可行实验

| 项目 | 方法 | replicate | K | 最多候选数 |
|---|---:|---:|---:|---:|
| Train Ticket + Online Boutique | M0/M1/M2/M3/M4 | 3 | 6 | 180 |

先用这个 pilot 校验 adapter、预算、记录格式和 Oracle；不得把 pilot 用来改完方法后又当最终测试数据。

### 9.3 论文主实验

建议至少三个项目，其中一个必须 held-out：

| 维度 | 设置 |
|---|---|
| 核心方法 | M0/M1/M2/M3/M4；M5 可选 |
| 项目 | 2 个现有项目 + 1 个 held-out；资源允许时加入第二个 held-out |
| replicate | 5 个独立块；LLM/random 使用预注册 seeds，确定性方法仍在干净环境重放 |
| discovery budget | 每块 K=10，最多 3 小时 |
| issue confirmation | 3 个独立窗口；时序/竞态问题建议 5 次 |
| 最大规模 | 5 方法 x 3 项目 x 5 块 x 10 = 750 个 discovery 候选 |

若 750 次过大，优先减少 replicate 到 3 并扩大项目数，而不是在一个项目上大量重复；跨项目证据比同项目伪重复更重要。

## 10. 单次实验标准流程

1. 从干净 snapshot/namespace 恢复固定版本；确认没有残留 Chaos CR。
2. 运行 5 次 warm-up，再运行 3 个基线窗口，每窗至少 20 个请求；保存响应、p50/p95、错误、Pod/restart、trace/log/metric。
3. 方法根据允许输入产生下一个候选；记录生成时间、模型参数和成本。
4. 公共 schema 检查和 runtime gate；blocked/invalid 直接记录，不执行。
5. 随机抖动等待后执行候选，直到运行时确认注入；仅 apply 或 selected 不算生效。
6. 在固定负载窗口测量业务不变量、延迟、错误、状态、日志、trace 和恢复行为。
7. 删除故障资源，确认 recovered、资源不存在、Pod/业务回到基线容差。
8. 统一分类器输出证据状态；方法输出自己的根因预测，但不能决定最终问题标签。
9. 疑似问题进入确认队列，使用相同配置独立重复 3 次；竞态问题 5 次并报告成功比例。
10. 方法收到允许的标准化反馈后选择下一候选，直到 K 或时间用完。

方法执行顺序按 `project x replicate` 分块随机化。每个方法使用独立 namespace 或重建 snapshot，防止上一个方法的缓存、重启次数、故障 CR 和知识记录污染下一个方法。

## 11. 什么算一个问题

### 11.1 七个必要条件

一个自然问题只有同时满足以下条件才计入主指标：

1. Reachable：目标和业务路径真实可达；
2. Injected：运行时确认故障生效；
3. Causal：baseline/injection/recovery 或反事实重放支持因果关系；
4. Reproducible：3 次至少 2 次复现；确定性失败应 3/3；
5. Impactful：违反预注册的响应契约、deadline/SLO、数据、恢复或告警要求；
6. Distinct：不是已计数根因在另一个 endpoint 上的重复表现；
7. Evidence-bound：配置、路径、注入、影响、恢复/清理证据齐全。

仅观察到延迟上升但没有业务/SLO 边界时，标为 `confirmed_resilience_weakness`，不能与 `confirmed_actionable_issue` 合并。

### 11.2 去重键

项目内使用：

```text
(project, violated_invariant, root_cause_mechanism, recovery_mechanism)
```

同一 timeout 缺口影响五个 endpoint，只算一个项目级问题实例；同一机制在三个项目各出现一次，报告为 3 个项目实例和 1 个跨项目机制家族，两个数字不能相加。

标准标签：

- `confirmed_actionable_issue`
- `confirmed_resilience_weakness`
- `confirmed_duplicate_mechanism`
- `defended_or_expected_behavior`
- `invalid_unreachable`
- `invalid_not_injected`
- `environment_blocked`
- `out_of_domain`
- `insufficient_evidence`

## 12. Oracle 和影响标准

每个 workload 在实验前注册：

- 正常响应状态、schema/body 不变量；
- 客户端 deadline；
- 明确的业务状态/数据不变量；
- 恢复目标和允许重启行为；
- 是否要求自动告警或仅要求可追踪；
- 不存在业务 SLO 时，只报告延迟效应和弱点，不事后创造阈值。

当前分类器中的 `delta >= 50ms` 或 `ratio >= 1.5` 只能作为“检测到退化”的筛选阈值，不能自动升级成应用 bug。最终问题判定仍需要业务边界和人工评审。

影响分级只做次要分析：

| 等级 | 定义 |
|---|---|
| S1 | 无明确 SLO 的局部弱点、人工才能发现的观测缺口 |
| S2 | 单个关键工作流违反 deadline/契约，或恢复超过注册目标 |
| S3 | 多工作流级联、长时间不可用、数据/状态错误或危险恢复 |

主结果使用未加权独立问题数；若计算加权收益，固定使用 S1/S2/S3 = 1/2/3，并同时展示原始分布。

## 13. 指标

### 13.1 主指标

```text
U@10 = 在前 10 个提交候选内确认的独立 actionable issue 数
```

### 13.2 次要指标

| 指标 | 公式/说明 |
|---|---|
| Discovery AUC | 横轴为提交候选数，纵轴为累计独立问题数的曲线面积 |
| Precision | 独立确认问题 / 方法报告的问题候选 |
| Experiments per Issue | 已提交候选数 / 独立确认问题数；无问题时记删失而非除零 |
| Time to First Issue | 从该块开始到首个后来被确认的问题首次出现 |
| Invalid Rate | unreachable + not-injected + blocked + schema-invalid / submitted |
| Duplicate Rate | duplicate mechanism / submitted |
| Evidence Completeness | path、reachability、injection、impact、recovery、causality 六项覆盖率 |
| RCA Top-1 | 方法预测根因与盲评根因一致比例 |
| Recovery Misclassification | 把注入逃逸、重启副作用、未观测误判为自愈的比例 |
| Gate Precision/Recall | 对预注册危险/无效计划的正确拦截能力 |
| Cost | wall time、CPU/GPU、LLM token/API cost、人工分钟数 |

不要把所有指标加成一个任意权重的“总分”。预注册决策规则是：先比较 U@10；效果没有明确差异时，再比较 invalid rate、Discovery AUC、证据和成本。

## 14. 盲评和根因去重

1. 所有 finding 删除方法名，替换为随机 ID；
2. 两位评审独立判断必要条件、影响等级、根因和重复组；
3. 分歧由第三位评审裁决；
4. 报告 Cohen's kappa 或 Krippendorff's alpha；
5. 评审前冻结 dedup taxonomy，不能因为某方法结果多就临时拆细根因；
6. 方法作者不能单独担任最终裁决者；
7. 评审只看统一证据包，不看候选排序来源和 LLM 解释风格。

证据包至少包含：版本、workload、candidate plan、baseline、注入生命周期、请求/trace/log/metric、恢复/cleanup、重复运行和源码/配置引用。

## 15. 统计分析

- 在执行层以 `project x replicate` 为配对块；同一块对所有方法使用相同 workload、候选宇宙和环境快照；
- 在泛化推断层先把 replicate 在项目内聚合，再对方法做项目级配对比较。replicate 只量化 LLM/环境随机性，不能当成新的独立项目；
- U@10 和 Discovery AUC 报告逐项目配对差值及以 project 为外层、replicate 为内层的 hierarchical bootstrap 95% CI；项目达到 5 个后，才把项目级 paired permutation 或 Wilcoxon 作为正式检验；
- 首个问题时间使用 Kaplan-Meier 曲线；没有发现问题的块按预算终点右删失，置信区间按项目聚类；
- invalid/duplicate 等比例使用 hierarchical bootstrap；数据量足够时再用带 project random effect 的 logistic model；
- Ours 分别与 M0-M3 比较，使用 Holm 校正；M5 为预注册的次要比较；
- 效果量优先报告项目级平均/中位配对差值和 paired rank-biserial correlation，不用同项目重复扩大显著性；
- 项目少于 5 个时，以逐项目结果、效果量和区间为主，不把 `p < 0.05` 当主要结论。

“Ours 更好”的判据：Ours 的 U@10 配对差值 95% CI 下界大于 0，并且平均每项目至少多发现 1 个独立 actionable issue；否则写“未观察到明确优势”。若 U@10 相当但 invalid rate/成本显著更低，应写“效果相当、效率或有效性更好”，不能写全面胜出。

## 16. 必须保存的数据

| 表/目录 | 一行或一文件代表什么 |
|---|---|
| `project_registry` | 固定 commit、镜像、环境、workload、SLO |
| `method_registry` | 版本、repo、prompt/model、adapter diff、输入档 |
| `candidate_plans` | 每个提交候选及其 rank、理由、成本 |
| `run_records` | gate、baseline、injection、requests、recovery、cleanup |
| `method_predictions` | 方法自己的 outcome/root-cause/recovery 判断 |
| `confirmation_runs` | 每个疑似问题的 3/5 次独立重放 |
| `adjudication` | 两位评审标签、分歧、最终标签、dedup key |
| `analysis` | 冻结脚本、原始表、图、CI 和统计输出 |

所有文件带 `project_commit + method_version + config_hash + seed + timestamp`。原始证据只追加不覆盖；人工修订用新版本和变更理由。

## 17. 推荐实施顺序

### 第 0 阶段：冻结协议

- 确定核心五种方法、输入档、公共候选 schema、K、seeds 和 Oracle；
- 固定所有项目版本和容器 digest；
- 选择 held-out 项目后，在查看源码前登记。

### 第 1 阶段：打通 adapter

- 先对每种方法只生成一个候选；
- 用同一 runner 完成 baseline -> injection -> recovery；
- 验证 invalid 不补位、out-of-domain 不算失败、方法目录隔离。

### 第 2 阶段：Track K

- 跑 K1-K9；
- 若某方法/adapter 连已知正负控制都无法正确表达，先修 adapter，不进入主实验；
- 修完后重跑 Track K，保留失败版本记录。

### 第 3 阶段：pilot

- 两项目、五方法、3 replicate、K=6；
- 冻结数据清洗、去重和统计脚本；
- pilot 后不得再根据最终指标调方法超参数。

### 第 4 阶段：held-out 主实验

- 干净环境运行 T2；
- 完成盲评后一次性解盲；
- 再运行 T3 消融和 leave-one-project-out 知识迁移。

### 第 5 阶段：原生系统复现

- 单独报告 ChaosEater 原论文 Nginx/Sock Shop 复现、FastFI 原 benchmark 和本方法原生流程；
- 只用于外部有效性和工程成本说明，不覆盖 T2 的主统计结论。

## 18. 最小结论表

最终论文至少给出：

| Method | Input | U@10 | Weaknesses | AUC | Invalid % | Duplicate % | RCA Top-1 | Evidence % | Time/Issue | Cost |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Random | I0 | | | | | | | | | |
| ChaosEater-adapter | I0 | | | | | | | | | |
| FastFI-adapter | I0+I2 | | | | | | | | | |
| Graph-only | I0+I1-global | | | | | | | | | |
| Ours-full | I0+I1-local+I2(+I3) | | | | | | | | | |

另给一张消融表和一张逐项目表。总体平均数不能替代逐项目结果，因为某方法可能只在一种系统或 fault family 上占优。

## 19. 当前项目可立即复用的入口

- 统一执行器：`tools/run_chaos_experiment.py`
- 运行时适用性门禁：`tools/runtime_applicability_gate.py`
- 统一分类器：`tools/classify_runtime_result.py`
- 统计重复器：`tools/run_stat_repeats.py`
- Train Ticket 已知控制：`artifacts/train-ticket/runtime/p0_regression_set.md`
- Train Ticket 半盲池：`artifacts/train-ticket/runtime/coverage_matrix.csv`
- 三项目机制汇总：`artifacts/cross_project_summary.md`
- 证据打包：`tools/package_report_evidence.py`

下一项工程工作不是继续注入，而是实现公共 `candidate_plan` adapter/registry 和盲评表，然后先跑 Track K 与 180 候选 pilot。
