# Train Ticket 混沌测试研究：阶段总结与论文准备稿

更新时间：2026-08-04

项目：`FudanSELab/train-ticket`

固定版本：`313886e99befb94be6cd45f085c98e0019f59829`

## 1. 研究目标

本项目不是简单地批量运行 Chaos Mesh YAML，而是研究一种面向真实微服务项目的、以测试节点为中心的混沌测试工程流程：

```text
真实 YAML
  -> 测试节点抽象
  -> selector/Deployment/Service/源码入口映射
  -> 测试节点局部 CFG/DFG 与调用/数据/控制关系
  -> 存在性、可达性、测试必要性判断
  -> 生成最小安全变异
  -> 业务 Oracle、日志、资源和恢复观测
  -> 防御/部分防御/未防御/测试无效分类
  -> 原因解释与知识卡更新
  -> 影响下一轮候选选择
```

论文需要回答的核心问题是：

1. 如何从大量真实 YAML 中抽象出稳定、可检索的测试节点和测试模式？
2. 如何只分析某个测试节点实际影响的代码和依赖，而不是构建一个无法用于决策的全项目大图？
3. 如何区分“响应还正确”“延迟已经恶化”“客户端超时”“服务端仍在继续执行”和“系统真正防御住了”？
4. 如何把一次实验结果转化为带适用边界的知识，并阻止 LLM 重复无效或危险注入？

## 2. 本阶段完成的工作

### 2.1 数据和项目基线

- 扫描真实 Chaos YAML 资产 1,935 个，归一化测试节点目录 77 个。
- Train Ticket 子集包含 54 个 `train-ticket` namespace 样本，其中 NetworkChaos 15 个、StressChaos 8 个、HTTPChaos 30 个、Workflow 1 个。
- 固定真实项目 commit、隔离 namespace `train-ticket-lab`、单目标 Pod、已有种子数据和自动恢复/清理规则。
- 运行环境使用 Docker Desktop Kubernetes 与 Chaos Mesh；实验没有触碰 `default` 或共享生产 namespace。

### 2.2 测试节点中心的关系网

当前图模型只保留测试节点影响半径内的节点和边：

```text
TestNode
  -> Config/Default/Validator
  -> Selector/Deployment/Service/Pod
  -> Controller
  -> Service/Repository 或下游服务调用
  -> 数据库/网络/资源边
  -> 业务响应与延迟
  -> 日志/指标/资源观测
  -> Recovery/Cleanup
```

边必须标记为 `confirmed_static`、`confirmed_runtime`、`hypothesis` 或 `not_reachable`。这使得“源码中存在函数”与“生产请求确实执行函数”不会被混为一谈。

### 2.3 候选选择和安全执行链路

已实现并实际运行：

1. 选择器根据 selector、目标存在性、源码函数候选、知识卡和运行时分类生成候选。
2. 变异器把真实 YAML 改写到隔离 namespace，并限制单目标、短 duration 和单因子变异。
3. runner 等待 `injectedCount >= 1` 后才发请求，随后等待恢复并删除资源。
4. 分类器同时读取 baseline、HTTP 响应、延迟、日志、cgroup 和清理结果。
5. 知识卡的停止条件会反向改变选择器决策。已闭环节点现在返回 `closed_runtime_boundary_no_reinjection`，可以检索但不会自动重复注入。

### 2.4 已完成的运行时实验

| 测试节点 | 关键结果 | 当前解释 |
|---|---|---|
| Basic StressChaos CPU，r2 强压力（4 worker，100%，60s） | 成功 UUID 保持 HTTP 200；r2 中位延迟 27.378ms -> 101.404ms；`nr_throttled +588` | 功能响应保留，但延迟明显恶化，不能称为完整防御 |
| Basic StressChaos CPU，r1 并发 4（12 个正式请求） | r1 中位延迟 27.378ms -> 92.826ms，p95 195.868ms；`nr_throttled +440` | 并发是独立测试维度，顺序成功不能推广到并发 SLO |
| Station StressChaos CPU | 中位延迟 30.146ms -> 43.308ms；`nr_throttled +406` | 注入位置改变影响，不能把 Basic 上游证据直接迁移到 Station |
| Station NetworkChaos 100ms | 成功 Oracle 中位延迟 30.146ms -> 216.022ms；Not Found 中位延迟 32.038ms -> 215.359ms | 双 Oracle 的延迟增量接近，说明网络边效应可复现 |
| Station NetworkChaos 500ms/2s | 中位延迟分别为 1021.227ms、4020.903ms，响应契约仍保持 | 延迟单调增长，响应正确不等于延迟 SLO 被保护 |
| Station NetworkChaos 3s 边界 | 客户端 5047.049ms 超时；Station 在 6063.895ms 写出数据库查询后的 Not Found 日志 | 客户端已超时但服务端仍继续完成，分类为 `client_timeout_server_completion_after_delay` |

### 2.5 Station NetworkChaos 闭环案例

该案例是本阶段最完整的论文样例。

```text
NetworkChaos delay, direction=to, app=ts-station-service
  -> GET /api/v1/stationservice/stations/id/{stationName}
  -> StationController.queryForStationId
  -> StationServiceImpl.queryForId
  -> StationRepository.findByName
  -> train-ticket-mysql:3306, database=ts
  -> client timeout / server-side branch completion
  -> recovery and cleanup
```

运行中的 Station Pod 已通过非敏感环境变量确认 datasource peer 为 `train-ticket-mysql:3306`。这比源码默认值更接近真实部署配置；没有读取用户名、密码或 Secret 内容。MySQL 没有输出查询日志，因此当前证据是“运行配置确认 + 服务端日志时间线”，不是数据包级 Trace。

## 3. 阶段性研究结论

### 3.1 YAML 字段本身不足以判断是否值得测试

必须同时满足：YAML 语义可解析、目标 selector 命中真实资源、业务入口可达、变异能真正注入、观测链完整。HTTPChaos 因 Docker Desktop WSL2 `ebtables` 前置条件被阻断，Order->Station 原始候选因生产调用点不可达而延期。这些不是“测试失败”，而是测试适用性判断的输出。

### 3.2 业务正确性和系统韧性必须分开

Station 在 100ms、500ms、2s 下仍返回正确响应，但延迟已经从 30.146ms 增长到 4020.903ms。3s 实验进一步显示客户端在 5s 预算内超时，而服务端之后仍完成业务分支。因此，“HTTP 200”只能证明该次扰动没有破坏响应契约，不能证明 timeout、retry、fallback、circuit breaker 或 SLO 保护存在。

### 3.3 双 Oracle 能降低业务分支混淆

成功 Oracle 和 Not Found Oracle 在 100ms 注入下分别增加 185.876ms 和 183.321ms。两种结果都保持各自响应契约，说明主要影响来自测试节点经过的网络/依赖边，而不是某一个业务分支独有的异常。

### 3.4 注入位置是因果变量

Basic 上游 CPU、Station 直连 CPU 和 Station 网络延迟虽然使用相似的业务查询，但延迟增量和观测证据不同。知识检索必须匹配 `kind + operation + selector + target service + direction + oracle`，不能只按“CPU 测试”或“网络测试”泛化。

### 3.5 知识库应保存停止规则和反例

Station NetworkChaos v4 卡片不仅保存“延迟有效”，还保存：3s 已越过实验预算、服务端晚于客户端完成、不能宣称客户端防御、生产 SLO 尚未定义、不能继续加压。选择器因此不再重复注入该节点。这是从实验结果到工程决策的闭环证据。

## 4. 可以写进论文的贡献表述

当前阶段适合使用以下保守表述：

> We propose a test-node-centered, evidence-bound workflow that maps real chaos YAMLs to local control/data-flow slices, validates runtime applicability, performs bounded single-factor injections, and feeds outcome-specific evidence back into a versioned knowledge base.

> In the Train Ticket case study, the workflow distinguished response preservation from latency-SLO preservation and identified a client-boundary gap: under a confirmed outbound delay, the Station server completed the business branch after the client had already timed out.

> The feedback policy prevented automatic reinjection after the timeout boundary was confirmed, while retaining the case as a retrievable counterexample for future test selection.

不要写成以下未经证实的结论：

- “系统具备完整超时防御”；
- “所有 HTTP 200 都表示系统防御成功”；
- “源码中的默认 MySQL 主机就是运行时实际主机”；
- “一次 10 次请求实验即可证明生产 SLO”；
- “Order->Station 候选已经被真实业务流程验证”。

## 5. 当前证据和复现入口

- 项目阶段总结：`artifacts/train-ticket/README.md`、`refined_report.md`
- 测试节点和局部图：`artifacts/train-ticket/test_node_catalog.json`、`train_ticket_test_slices_graph.json`
- 知识库索引：`artifacts/train-ticket/knowledge_base/index.json`
- Station 线路报告：`artifacts/train-ticket/runtime/station_network_delay_line_report.md`
- Station v4 知识卡：`artifacts/train-ticket/knowledge_base/KB-TT-NETWORK-STATION-DELAY-001.md`
- 3s 超时边界结果：`artifacts/train-ticket/runtime/generated_station_network_delay_r4_result.json`
- 运行依赖映射：`artifacts/train-ticket/runtime/station_network_edge_static_mapping.json`
- 候选选择结果：`artifacts/train-ticket/runtime/stress_candidate_selection.json`
- 选择器回归测试：`tools/tests/test_select_chaos_candidates.py`

## 6. 论文写作前仍需补齐的限制

1. 目前只有一个真实项目和一个固定 commit，外部有效性有限。
2. 多数正式窗口样本量较小，尚未完成置信区间、重复实验和统计显著性分析。
3. Station 的运行 datasource 已确认，但没有分布式 Trace 或数据包级证据。
4. 5s 是实验客户端预算，不是运维定义的生产 SLO。
5. HTTPChaos 仍受 Docker Desktop WSL2 `ebtables` 前置条件限制。
6. Order 真实下游业务路径尚未形成可重复 Oracle。
7. 当前 LLM 评价主要是规则和候选决策回归，还没有独立人工标注集。

## 7. 下阶段工作计划

### 阶段 A：把实验记录变成可统计数据集

目标：从“案例证据”升级为“可比较实验矩阵”。

- 为 Basic CPU、Station CPU、Basic->Station Network、Station Network 建立统一 run schema。
- 每个配置至少重复 3 次，记录 p50/p95、错误率、超时率、响应契约、恢复时间、Pod 重启、cgroup 增量和日志覆盖率。
- 固定 warm-up、正式样本、请求间隔、并发度、timeout 和停止规则。
- 输出 `experiment_matrix.csv`、重复实验汇总和置信区间。

验收：同一配置跨重复实验的主要指标可复现，异常样本有明确原因标签。

### 阶段 B：完成测试节点局部 CFG/DFG 覆盖

目标：把当前手工确认的 Station/Basic 图扩展成可导出的局部图。

- 为每个 P0 节点生成统一 JSON/GraphML：配置、selector、目标、控制流、数据流、观测、恢复。
- 给每条边绑定 source span、运行证据或 hypothesis 标签。
- 补充 Nacos、RabbitMQ、MySQL 和服务间 HTTP 调用的配置到运行映射。
- 对 Order 节点先解决业务可达性，再决定是否注入；不可达节点保留为反例。

验收：每个 P0 节点都有 `selects -> injects -> calls/controls -> observes -> recovers` 路径，且未证实边不会被标成 runtime fact。

### 阶段 C：建立 LLM 决策评测集

目标：验证知识库是否真的改善 LLM 的混沌测试工程判断。

- 从真实 YAML 中抽取候选任务，人工标注 `可测试/需运行门禁/不可达/平台阻断/已达边界`。
- 对比三种条件：只看 YAML、YAML + 项目图、YAML + 项目图 + 知识库。
- 评价候选选择准确率、不可达误报率、危险变异率、停止条件识别率、根因分类准确率和证据引用完整性。
- 把 Station v4 作为“客户端超时后服务端完成”的反例样本，把 HTTPChaos blocked 和 Order deferred 作为无效测试样本。

验收：LLM 能拒绝已闭环节点的重复注入，能区分 response preserved、latency degradation、client timeout 和 defense observed。

### 阶段 D：扩展真实业务路径和控制组

目标：验证方法不是只对 Station 查询有效。

- 找到一个真正调用 Station/其他下游服务的 Order 业务 Oracle。
- 增加同一测试节点的 `direction=to/from/both` 控制组，但保持单变量和明确预算。
- 在 HTTPChaos 平台前置条件修复后，优先测试单一只读接口的状态码或延迟变异。
- 在不同服务上重复 CPU/Network 试验，比较注入位置和依赖拓扑的影响。

验收：至少 2 个服务、2 类故障、1 个跨服务业务流程拥有同样的证据结构。

### 阶段 E：形成论文材料

目标：把工程证据组织成可审阅的论文结果。

- 图 1：整体闭环架构。
- 图 2：TestNode-centered 局部影响子图。
- 图 3：Station 延迟阶梯与客户端超时/服务端完成时间线。
- 表 1：YAML 资产与测试节点统计。
- 表 2：候选适用性分类和平台阻断原因。
- 表 3：CPU/Network 多 Oracle 实验结果。
- 表 4：LLM 选择和结果解释评测指标。
- 单独撰写威胁与限制，不把单项目案例外推为通用定律。

验收：所有论文数字都能回链到 JSON/日志/源码位置，任何 defense claim 都有对应的时间线或 SLO 证据。

## 8. 下一阶段优先级

优先顺序建议为：

1. 先做阶段 A 的重复实验和统计数据集；
2. 并行完成阶段 B 的局部图标准化；
3. 再做阶段 C 的 LLM 对照评测；
4. 最后扩展 Order 和 HTTPChaos，避免在缺乏可重复 Oracle 时扩大注入范围。

下一阶段的完成标志不是“再跑更多 YAML”，而是形成一组可重复、可比较、可回链、能证明 LLM 决策质量提升的实验数据。
