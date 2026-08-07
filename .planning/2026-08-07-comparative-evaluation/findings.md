# Findings

## 已知项目能力

- 本项目已有三套真实微服务系统实验基础：Train Ticket、Online Boutique、OpenTelemetry Demo。
- 现有方法链包含真实 Chaos YAML、测试节点局部 CFG/DFG、运行时适用性门禁、注入/恢复证据、分类器、知识卡和停止规则。
- 已观察到可用于基准构造的机制：无 timeout 导致延迟传播或挂起、探针重启逃逸注入、禁用下游调用导致路径不可达、观测能够捕获但没有自动告警、多故障串行累积。
- HTTPChaos 在当前 WSL2 内核缺少所需 ebtables 路径，应从主对比矩阵排除或移到具备前置条件的原生 Linux 环境，不能计作方法失败。

## 候选比较方法

- B0：预算约束随机/模板抽样。
- B1：ChaosEater 原系统或明确标注的适配版本。
- B2：FastFI。
- B3：Cast-style selector。
- B4：YAML + global graph / graph-only。
- Ours：局部 CFG/DFG + runtime gate + evidence classification + knowledge feedback。

## 可复用实验资产

- Train Ticket 固定 commit 为 `313886e99befb94be6cd45f085c98e0019f59829`，54 个样本中 5 条已验证、30 条 HTTPChaos 平台阻断、1 条不可达、1 条高风险静态样本、17 条未运行。
- Train Ticket P0 回归集已有 7 项，可作为已知机制的正负控制：延迟退化、超时边界、CPU 节流、平台阻断和业务不可达。
- 统一 runner 已要求 baseline、注入确认、恢复和清理证据；外部方法可以只承担候选选择，避免把执行器差异算成算法差异。
- 旧报告已提出 I0/I1/I2 输入分档和六档基线，但还需要补全盲测池、预注册、样本量、随机化、删失规则和统计检验。

## 初步实验结构

- Track A（已知问题控制集）：衡量召回率、误报率、根因识别和恢复误判，不用于声称发现新问题。
- Track B（隐藏问题发现集）：对每种方法隐藏知识卡和既有结果，在相同预算内搜索；由独立评审按根因去重。
- Track C（内部消融）：隔离 local graph、runtime gate 和 knowledge feedback 的增量贡献。
- HTTPChaos 的平台阻断只作为安全门禁负控制，不进入有效故障预算或方法收益分母。

## 三项目可作为基准的机制

- 跨项目共同机制：下游调用缺少 timeout，导致延迟近似全额传播或丢包后挂起到调用方 deadline。论文统计时应按“根因机制”计算一次，同时报告跨项目复现范围，不能按 endpoint 数刷问题数。
- Online Boutique 独特机制：核心依赖故障级联、非核心广告优雅降级、探针重启逃逸注入、多下游延迟串行累加。
- OpenTelemetry Demo 独特机制：trace 完整捕获但没有自动告警、HTTP 与 gRPC 故障语义差异、误导性错误消息。
- Train Ticket 独特机制：Order->Station 生产路径被注释、HTTPChaos 平台前置阻断、Station 客户端超时与服务端晚完成。
- 统一 runner 已实现 `injected_count >= 1`、恢复确认、资源清理和 HTTP 请求测量，可作为所有方法共同执行后端；需要在协议中把方法输出统一为 candidate plan。

## 研究问题与公平性决策

- RQ1：固定预算下谁发现更多独立、确认且可行动的问题。
- RQ2：谁用更少候选、更少有效注入和更短时间找到问题。
- RQ3：谁更少产生不可达、未注入、环境阻断、重复和恢复误判。
- RQ4：谁提供更完整证据和更准确根因。
- RQ5：local graph、runtime gate、knowledge feedback 各自贡献多少。
- RQ6：结论能否迁移到未参与方法开发的项目。
- 主评价采用统一候选接口：各方法只输出排序后的 `(workload, target, fault, intensity, timing)`，由同一 runner 和 Oracle 执行。
- 原生端到端模式单独报告，不作为严格优劣排序，因为输入、fault domain 和自动修复能力不同。
- 公共故障域只含服务边延迟和不可用；CPU/Pod/HTTPChaos 等放入 K8s-native 补充轨，避免拿 FastFI 不支持的故障类型惩罚它。
- 对现有三个项目只能做已知控制、半盲未执行池和 leave-one-project-out 知识迁移；真正的自然问题发现主张需要新增一个在冻结协议前无人检查的 held-out 项目。
- 冷启动时隐藏目标项目知识卡和结果；warm-start 只允许读取本方法同一轮之前生成的标准化记录。跨项目知识迁移必须标为单独条件。

## 统计和裁决决策

- 主指标固定为 `U@10`，只计独立 actionable issue；无明确业务/SLO 边界的因果退化单列为 resilience weakness。
- 项目内重复只估计随机性；泛化推断必须先按项目聚合或使用 project 外层的 hierarchical bootstrap，禁止把 5 个 replicate 当 5 个独立项目。
- 两位盲评者独立判断，第三人裁决；去重键固定为 `(project, violated invariant, root cause, recovery mechanism)`。
- 优胜判据采用预注册的字典序：先 U@10，再 invalid/duplicate、证据和成本；不使用任意权重总分。
