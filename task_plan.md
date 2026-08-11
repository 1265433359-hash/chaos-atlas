# 真实 YAML 测试节点知识库与项目影响子图计划

## 本轮项目归档任务（2026-08-10）
- 目标：为论文写作、对比实验复核和知识库复用补齐项目级文档、目录说明、证据索引、复现实验入口和代码注释。
- 项目名称确定为：**ChaosAtlas**（TestNode-Centered Chaos Analysis and Knowledge Base）。名称用于文档与本地 Git 元数据，不执行远程上传。
- 范围：保留用户现有未提交实验产物；只新增/修改归档说明、README、实验/知识库索引和必要的高风险工具注释。
- 上传门槛：完成本地清单、敏感信息扫描、测试和 Git diff 审核后，等待用户明确同意再执行 `git remote add`、`git push` 或 GitHub CLI 操作。
- 状态：complete（本地归档文档与验证完成；GitHub 上传仍需用户明确授权）。

## 归档清理补充（2026-08-11）
- 保留所有原始 YAML、运行证据、JSON/CSV 台账、知识卡、正式消融 prompt、报告和历史规划摘要。
- 删除 9 个 `.planning/**/DEEPSEEK_*_PROMPT.md` 临时工作指令和 `.pytest-tmp-final-all/` 测试缓存；清单见 `docs/ARCHIVE_CLEANUP.md`。
- 未删除 `.pytest_cache/`，原因是当前 Windows 权限无法读取；未配置 remote、未上传 GitHub。
- 状态：complete。

## 论文准备复盘（2026-08-11）
- 重新核对四个案例、TestNode 证据链、知识卡、跨项目报告和主实验归档索引。
- 形成 `analysis_outputs/SUMMARY.md`、`analysis_outputs/RISKS.md`、`analysis_outputs/status.json`。
- 明确知识库消融与最终方法 head-to-head 对比尚未完成，状态统一为 `parked_future_work`，不纳入当前论文正式结论。
- 状态：complete；后续恢复实验前需要人工确认协议、候选池、oracle 和统计方案。

## 本轮错误记录
| 错误 | 处理 |
|---|---|
| 全量 pytest 首次运行时 2 个使用 `tmp_path` 的测试因 Windows `AppData\\Local\\Temp\\pytest-of-*` 权限拒绝而在 setup 阶段失败 | 使用仓库内隔离 `--basetemp .pytest-tmp-archive-run` 重跑，2/2 通过；其余 247 个测试通过 |
| 知识库校验对 Online Boutique 8 张卡、OpenTelemetry Demo 2 张卡给出 `source_yaml` 不存在 warning | 这些卡明确使用 generated candidate；保留 warning，不把它升级为错误 |

## 项目总览阶段（2026-08-10）
- 目标：逐目录核对项目资产、案例、工具、实验状态和论文证据，生成一份不依赖会话上下文的总览。
- 产出：`docs/PROJECT_SUMMARY.md`，并在 `findings.md` / `progress.md` 记录数量与发现。
- 约束：只读核对现有资产；不重新运行注入、不重写用户实验结果、不上传 GitHub。
- 状态：complete。

## Latest execution status
- 2026-08-05 收尾：第一项目（train-ticket）运行时循环已全部关闭；阶段 4/7/8/9 标记 complete，阶段 10 进入 in_progress（P0 回归集已定义）。统计重复实验（Station 延迟、Basic CPU 各 2-3 次）已补跑并输出置信区间。薄弱点报告（Order refresh 禁用下游调用 + Station 无超时/熔断防御）已整理。
- Paper-preparation checkpoint completed: `artifacts/train-ticket/paper_prep_stage_summary.md` records the current method, evidence, claims, limitations, and next-stage acceptance criteria.
- Current phase conclusion: the first runtime case-study loop is complete for Station NetworkChaos; the next phase is statistical repetition, local CFG/DFG standardization, and an LLM decision benchmark.
- Completed fixed-warmup repetition for the Basic CPU success and not-found oracles; both formal ten-request windows preserved their response contracts under measurable CPU throttling.
- Upgraded the Basic CPU card to v3, added the unified warmup result, paired log/cgroup/classification evidence, and re-ranked the selector with the new runtime record.
- Next runtime action: increase CPU pressure in one bounded step on the seeded success oracle using the same warm-up/sample/recovery controls, then identify the first HTTP error or timeout boundary.
- Completed the bounded r2 strong profile (4 workers, 100%, 60s) on the seeded success oracle: HTTP 200/UUID preserved, median latency 101.404ms (+74.026ms), no timeout/5xx, cgroup throttling confirmed, and runner cleanup confirmed. This is partial resilience, not full defense.
- Fresh application-log capture for r2 was not obtained because the read-only permission review timed out; that limitation is recorded in the result and knowledge card.
- Completed the r1 concurrent replay (four concurrent callers, twelve formal success requests): all responses remained HTTP 200/UUID, median 92.826ms and p95 195.868ms, with cgroup throttling and successful recovery. This confirms concurrency-amplified latency degradation.
- Completed a direct Station CPU replay with the same r1 profile and fixed window: all ten seeded Station responses remained HTTP 200/UUID, median 43.308ms versus 30.146ms baseline (+13.162ms), cgroup throttling and recovery confirmed. Added a separate Station test-node card.
- Completed a bounded Station NetworkChaos replay (100ms outbound delay, 20s): all ten seeded Station responses remained HTTP 200/UUID, median 216.022ms versus 30.146ms baseline (+185.876ms), with injection/recovery/cleanup confirmed. Added a separate NetworkChaos Station card.
- Repeated the same Station NetworkChaos mutation against a direct not-found oracle: all ten responses preserved `status=0,msg=Not exists`, median 215.359ms versus 32.038ms baseline (+183.321ms). The near-equal deltas across outcomes make the network-edge effect reproducible.
- Repeated Station log capture was blocked by permission-review timeout; added a redacted static Station-to-MySQL edge mapping without accessing credentials.
- Completed a bounded Station delay ladder: 100ms -> 216.022ms median, 500ms -> 1021.227ms, 2s -> 4020.903ms; all success responses preserved and all runs recovered. Stopped before crossing the 5s observation budget.
- Static source review found no Basic application-level timeout/retry/fallback/circuit-breaker configuration; the runner's 5s timeout is an observation budget, not a system defense.
- Completed a 3s Station NetworkChaos timeout-boundary probe under the explicit 5s lab observation budget: the client timed out at 5047.049ms, while Station logged completion of the repository-backed Not Found branch at 6063.895ms.
- The Station NetworkChaos runtime loop is closed: dual oracles, 100ms/500ms/2s ladder, client-timeout boundary, server-side completion log, injection/recovery/cleanup proof, stopping rule, line classification, and v4 knowledge-card update are recorded for LLM retrieval.
- No further delay injection is required. Runtime configuration confirms the datasource peer as `train-ticket-mysql:3306`; an operator-defined SLO is needed only for a production-facing latency judgment, and Trace/network evidence is needed only for packet-level attribution.
- Cleanup verification from both runner reports is complete (`recoveredCount=1`, resource absent, post-recovery cgroup deltas zero). A final read-only kubectl health query was attempted twice but the external permission review timed out; no new injection will be started until health is rechecked.
- Completed the selector-generated Network candidate replay and upgraded the Basic->Station card to v3.
- Completed the selector-generated CPU candidate replay with an injection gate and cgroup-v2 sampling; upgraded the Order CPU card to v4.
- Completed a selector-generated Basic CPU replay over the real Basic-to-Station call path; added a new Basic CPU card and promoted that candidate to `ready_candidate_with_runner`.
- Completed a second Basic CPU replay using the existing seeded `shanghai` success oracle; the Basic CPU card now compares successful and not-found outcomes under one TestNode.
- Current runtime conclusion: the CPU tests produced measurable throttling while exercised responses stayed HTTP 200 and Pods recovered. The next required evidence is controlled repetition with fixed warm-up/sample windows, followed by a reachable order workflow with a real downstream call.
- Remaining gates: collect version-pinned external semantics, expand test-node-centered slices, and run regression/replay across service boundaries. HTTPChaos remains blocked by the Docker Desktop WSL2 `ebtables` prerequisite.

## 目标
以 Train Ticket 为第一个真实项目，让 LLM 从真实 YAML 中学习“测试节点 -> 影响代码路径 -> 防御结果”的混沌工程思维。核心不是构建整个项目的无差别 CFG/DFG，而是以每一个测试节点为中心，提取它实际涉及的服务、函数、调用、数据流、控制流、观测和恢复路径，形成可验证的测试影响子图，并通过注入结果持续更新知识库。

## 范围边界
- 首轮只覆盖仓库中已存在且可定位入口的 YAML；不直接修改生产环境。
- 注入采用隔离副本、沙箱或显式 dry-run，任何真实环境执行需人工批准。
- 结论必须绑定证据：配置片段、代码位置、运行日志、指标、回滚结果。
- 外部资料只作方法参考，不替代项目自身行为证据。

## 核心闭环
```text
真实 YAML 语料
  -> 测试节点抽象/频率/共现模式
  -> YAML 测试知识库
  -> Train Ticket 真实资源和代码映射
  -> 以测试节点为根的 CFG/DFG 影响子图
  -> 存在性/可达性/测试必要性判断
  -> 外部资料与项目资料补充
  -> LLM 生成并安全注入 YAML
  -> 观测防御住/部分防御/未防御/测试无效
  -> 根因解释与经验卡片
  -> 知识库更新和下一轮测试
```

## 阶段
| 阶段 | 状态 | 产出 | 完成判据 |
|---|---|---|---|
| -1. 真实项目选择 | complete | 候选评分表、选定项目与版本 | 已选 `FudanSELab/train-ticket`；版本与隔离环境待阶段 0/1 固定 |
| 0. 项目与环境基线 | complete | 固定 commit、部署入口、隔离边界、观测方案 | 已固定 commit；建立 `train-ticket-lab` 隔离 namespace；完成真实服务启动和只读基线；未触碰 `default`/`chaos-testing` |
| 1. 真实 YAML 语料抽取 | complete | YAML 清单、AST/IR、有效性分层 | 已生成逐文件清单、hash、字段、风险和 34 个语义形状问题记录 |
| 2. 测试节点知识库 | complete | 测试节点词典、频率、共现图、测试模式卡片 | 已生成候选节点频率和共现目录；外部语义验证和人工审核仍属于后续增强 |
| 3. Train Ticket 项目映射 | complete | 服务/配置/调用/观测资源图 | 已完成 selector -> Deployment/Service 和 source module/function 候选；运行 Trace 可达性作为阶段 4 输入 |
| 4. 测试节点中心影响子图 | complete | 每类测试的局部 CFG/DFG/调用/数据/控制关系 | 已补 Basic->Station 的运行时可达子图；Station 网络延迟子图（含超时边界）已运行时闭环；Order->Station 原始候选明确标记不可达并保留为反例 |
| 5. 存在性与测试必要性 | complete | 节点存在/可达/重要性/覆盖矩阵 | 已实现 `runtime_applicability_gate.py`；HTTP 节点被阻断、CPU/Network 节点可注入的结论均有真实运行证据；54 样本验证状态矩阵见收尾产物 |
| 6. 相关资料采集 | in_progress | 官方语义、源码规则、故障模式、版本差异 | 已完成 GitHub 候选调研快照；Chaos Mesh/项目源码规则按需采集；官方语义与版本差异卡片仍未系统化 |
| 7. LLM 注入与观测 | complete | 变异 YAML、实验记录、基线和结果时间线 | 第一轮闭环：Station 延迟阶梯与超时边界、Basic/Order/Station CPU、Basic->Station 网络均已注入并观测；HTTPChaos 被 ebtables 平台阻断（非防御结论）；所有运行自动恢复/清理 |
| 8. 防御解释与根因 | complete | 防御/未防御/无效分类、影响子图证据、根因树 | 分类器区分平台阻断、未注入、响应保持/延迟退化和客户端超时；Station 超时边界根因（无应用级 timeout/retry/fallback/熔断配置）已记录；分类索引 0 mismatch |
| 9. 知识库闭环 | complete | 经验/反例/测试配方、置信度和检索索引 | 7 张卡片（4 张 runtime_observed），停止规则反向影响选择器（closed_runtime_boundary_no_reinjection）；验证 0 error；选择器回归测试通过 |
| 10. 回归与评估 | in_progress | P0 回归集、LLM 决策评估、漂移和治理报告 | P0 回归集已定义（见收尾产物）；统计重复实验与置信区间已补跑；LLM 决策基准与独立标注集待后续 |

## 关键问题
1. 配置项是否真实存在、是否被加载、是否影响行为？
2. 是否已有校验/默认值/熔断/限流/回滚等防御？
3. 测试该配置的收益是否高于风险和成本？
4. 注入后结果是“被防御”“未防御”“不可判定”还是“测试本身无效”？
5. 如何把一次结果提炼成可迁移但不过度泛化的经验？

## 详细项目计划
| 阶段 | 主要任务 | 输入与方法 | 产出物 | 验收指标 | 主要风险/控制 |
|---|---|---|---|---|---|
| 0. 项目与环境基线 | 固定 Train Ticket commit；确认 Kubernetes/Helm/Chaos Mesh；建立隔离 namespace/集群；选择 Prometheus/Grafana + Jaeger/SkyWalking | README、Makefile、部署脚本、镜像和 CRD 版本核对；先 dry-run，不执行 `make deploy` | `project_manifest`、环境清单、权限边界、回滚方案 | 版本和镜像可复现；不触碰 `default`/生产；观测出口可访问 | 默认部署包含集群范围监控和硬编码凭据，必须隔离和脱敏 |
| 1. 真实 YAML 语料抽取 | 对 1,935 个 YAML 做规范化、解析和四层有效性标注 | AST、CRD/OpenAPI、模板展开、server-side dry-run；保留 source span 和原文 hash | `yaml_inventory`、`yaml_ir`、异常队列、字段词典 | 每个样本可追溯；异常不静默修复；模板与真实资源分开 | Helm 模板不能直接按 YAML 解析；敏感值只保存引用/哈希 |
| 2. 测试节点知识库 | 把字段组合抽象成测试节点和测试模式，统计频率与共现 | 规范化 `selector/action/target/delay/stress/schedule`；构建节点共现图；区分频率与风险价值 | `test_node_catalog`、`motif_graph`、测试卡片、P0/P1/P2 候选 | 能回答常见测试节点、组合、参数边界和测试目的 | 高频不等于重要；保留反例和低频高风险节点 |
| 3. Train Ticket 项目映射 | 建立服务、Pod、Deployment、Service、配置、调用、观测资源关系 | 解析 Helm 渲染结果、Deployment labels、服务端口、源码入口、配置和运行 trace | `service_graph`、资源/代码映射表、版本绑定 | 54 个 `train-ticket` YAML 的 selector 能映射到真实目标或被标为不可达 | 动态服务发现和版本漂移：边必须有静态或运行证据 |
| 4. 测试节点中心影响子图 | 对每个测试节点提取局部代码和行为网络，不分析无关代码 | 以测试节点为根，向前找注入目标/调用/控制流/数据流/观测/恢复，向后找配置/校验/默认值；合并静态 CFG/DFG 与运行 trace | `test_slice/<node>.graphml`、影响函数表、分支表、数据流表、观测路径 | 每个 P0 节点有 `selects -> injects -> calls -> controls -> observes -> recovers` 路径 | 只声明存在但没有代码/运行证据的边标 `hypothesis` |
| 5. 存在性与测试必要性 | 判断节点是否存在、是否可达、是否已覆盖、是否值得测试 | 三层判定：声明存在、运行可达、程序语义存在；用影响面、业务关键性、不确定性、现有证据和成本排序 | `test_point_matrix`、可达性矩阵、测试假设、停止条件 | 每个节点有明确结论和理由；P0 覆盖关键可达路径 | selector 空命中、没有观测或环境不匹配只能标测试无效 |
| 6. 相关资料采集 | 补齐 Chaos Mesh/CRD 语义、控制器行为、项目测试和已知故障 | 官方文档、CRD schema、源码、Issue/CVE、论文/项目文档；按版本、来源和置信度记录 | `source_catalog`、规则卡片、版本差异、项目映射 | 每条规则可回源并有项目内证据；外部内容不直接作为执行指令 | 外部资料可能过时或含恶意指令，必须二次验证 |
| 7. LLM 注入与观测 | LLM 根据测试子图选择最小变异并执行 | 先生成假设和预期不变量；单因素/边界优先；dry-run、快照、TTL、kill switch、隔离执行 | 变异 YAML、实验 manifest、基线/注入时间线、日志/指标/trace | 每次运行可复现、可停止、可清理；观测证据完整 | 高爆炸半径 Workflow、`mode: all`、真实凭据默认禁止 |
| 8. 防御解释与根因 | 判断防御住、部分防御、未防御、测试无效，并定位到子图 | 对比基线；关联 admission/controller/runtime/业务 SLO；使用反事实重放和影响子图定位 | 结果报告、根因树、证据链、修复建议、复现命令 | 能解释防御层、缺口节点和业务后果，而非只报成功/失败 | 不把未命中、无观测、环境偶然恢复误判为防御 |
| 9. 知识库闭环 | 将结果转成经验、反例和下一轮测试配方 | 卡片包含测试节点、影响子图、前置条件、注入、结果、根因、防御、证据、版本、边界、置信度 | `knowledge_base/`、索引、变更日志、候选下一轮测试 | 可按 kind/节点/图模式/根因检索；经验有审核和反例 | 候选 -> 审核 -> 验证 -> 弃用；禁止无证据泛化 |
| 10. 回归与评估 | 验证知识库和 LLM 决策是否有效 | 版本变化重放 P0；比较节点选择准确率、可达性判断、根因解释、重复实验一致性 | P0 回归集、LLM 评估报告、漂移/覆盖/风险看板 | 能发现项目/控制器变化；失败可复现；经验迁移边界明确 | 不只看测试通过率，要看解释正确性和证据完整性 |

## 原子步骤执行清单
| 步骤 | 要做什么 | 怎么做 | 达成目的 | 进入下一步的条件 |
|---|---|---|---|---|
| 1. 选择真实项目 | 从候选中确定主项目、版本、部署方式 | 对比 stars、维护状态、微服务数量、K8s/Compose、观测、负载、许可证；优先使用固定 release/commit | 保证实验对象是真实、可复现、可对照的系统 | 用户确认项目、版本和实验环境 |
| 2. 建立可复现环境 | 不改变业务代码地部署基线 | 固定 OS/K8s/Helm/Chaos Mesh 版本；记录镜像 digest、namespace、资源配额；执行健康检查 | 把后续结果绑定到明确环境，避免“环境偶然性” | 所有服务 Ready，健康请求和基线指标稳定 |
| 3. 建立资产清单 | 逐文件登记 YAML 与外部依赖 | 计算 SHA-256；记录 kind、namespace、name、apiVersion、占位符、secret/endpoint/path；保留原始行号 | 知道每个 YAML 是什么、属于谁、能否安全使用 | 100% 文件有唯一 ID 和风险标签 |
| 4. 四层有效性检查 | 分离语法、schema、语义、运行时可达性 | 先 YAML AST，再 Kubernetes server-side dry-run，再 CRD/控制器校验，最后最小 apply；异常不得静默修复 | 避免把“能解析”误判成“可运行” | 每个样本有四层状态 |
| 5. 建立 YAML IR | 抽取统一字段和来源位置 | 规范 action/mode/selector/duration/scheduler；解析单位、默认值、模板变量、引用；保留 source span | 给 LLM 和图分析提供稳定输入 | IR 可由原文往返定位，未知字段不丢失 |
| 6. 反查真实加载入口 | 找到 YAML 到控制器/应用行为的路径 | 在项目源码、Helm、CRD、controller、CI/CD、运行日志中检索 kind/字段；绑定版本/镜像 | 证明字段是否真正被使用 | 高风险字段至少有加载证据 |
| 7. 构建测试节点关系网 | 以单个 TestNode 为中心建配置、目标、注入、调用、观测、恢复局部图 | 只保留从测试节点可达或反向依赖的节点；边记录 selects/injects/calls/controls/flows_to/observes/restores | 看清该测试真正影响的爆炸半径，排除无关代码 | 每个节点子图可导出 GraphML/JSON，边可回溯证据 |
| 8. 构建局部 CFG/DFG | 在测试节点影响子图内追踪控制流和数据流 | backward slice：配置/校验/目标；forward slice：注入/调用/异常分支/业务状态/指标；合并静态分析和 trace | 找到“该测试会触发哪些函数/分支”和防御缺口 | 每个 P0 测试节点有影响函数、数据流和控制流，未知边标 hypothesis |
| 9. 生成测试点 | 判断存在性、必要性和优先级 | 使用 reachability × impact × uncertainty × change-frequency / cost；生成单因素、边界、pairwise、时序、恢复测试 | 控制测试规模，先覆盖高价值路径 | P0 测试点有前置条件、假设、停止条件 |
| 10. 建立基线观测 | 定义注入前的正常状态 | 记录请求成功率、延迟、错误率、资源、事件、日志、trace、业务 SLO；固定窗口与负载 | 后续能区分故障影响与自然波动 | 基线重复运行结果在容差内 |
| 11. 生成安全变异 | 对 YAML 做可审计注入 | 一次只改一个因素；覆盖空值、越界、selector 扩大、duration 延长、调度重入、依赖失效；脱敏并生成 diff | 系统化探索防御边界而非随机改配置 | 每个变异有 parent hash、mutation、风险等级 |
| 12. 预演与审批 | 注入前验证风险和回滚 | schema/dry-run、目标快照、权限检查、资源配额、TTL、自动清理、kill switch；生产环境禁止默认执行 | 把高风险实验挡在执行前 | 预演通过且获得人工批准 |
| 13. 隔离执行 | 在受控环境运行注入 | 隔离 namespace/集群；先小流量、短 duration、单目标；实时监测并满足停止条件 | 获得真实行为证据而不扩大事故 | 运行可复现、清理成功、审计完整 |
| 14. 结果判定 | 解释防御住、未防御、部分防御或无效 | 对比基线与注入时间线；检查 admission、controller、runtime、业务 SLO、cleanup；做反事实复现 | 不把静默、未命中、偶然恢复误判为防御 | 每个结论至少有直接证据和反事实检查 |
| 15. 根因归纳 | 找到防御层缺口 | 按 missing validation、selector overmatch、race、cleanup leak、RBAC gap、observability gap 等标签归因 | 将结果转成可修复工程问题 | 根因能映射回 CFG/DFG 节点和代码/配置位置 |
| 16. 更新知识库 | 沉淀经验与反例 | 生成经验卡片、反例卡片、测试配方；附 run_id、版本、证据、适用边界、置信度；人工审核 | 让 LLM 学到可迁移但有限定条件的工程思维 | 卡片可检索、可复现、可回归 |
| 17. 回归治理 | 让经验持续有效 | 控制器/CRD/应用版本变化时重放 P0；监控覆盖率、漂移、失败率、恢复时间 | 防止知识库和真实系统脱节 | 失败有责任人、重现命令和修复闭环 |

## YAML 测试点矩阵
| 维度 | 典型检查 | 适用资源 | “存在”与“需要测试”判定 | 预期证据 |
|---|---|---|---|---|
| 资源身份 | `apiVersion`、`kind`、metadata name/namespace | 全部 | 文件有字段不等于集群支持；版本/CRD 可达才测试 | server-side dry-run、CRD schema、事件 |
| 选择范围 | namespaces、labelSelectors、mode、containerNames | 全部 | selector 能解析且命中目标才测；空命中是“无效测试”而非防御 | 命中对象快照、selector 评估日志 |
| 故障动作 | action、target、direction、operation | Pod/Network/HTTP/IO/云类 | 枚举受支持且执行路径可达；未支持值先做拒绝测试 | admission/controller 错误、执行事件 |
| 强度/边界 | percent、delay、loss、bandwidth、errno、timeOffset、code | Network/HTTP/IO/Time 等 | 有数值且影响 SLO；测 0、最小、典型、最大、越界、负数/超大 | 参数校验、实际注入值、SLO 变化 |
| 时间与调度 | duration、scheduler、schedule、startingDeadlineSeconds | 全部含 Schedule/Workflow | 调度器启用且时间窗口可控才测；测过期、重入、并发、取消 | Cron/Workflow 状态、重入次数、清理时间 |
| 组合关系 | action+mode+selector、target+direction、replace+path、duration+scheduler | 组合资源及高频字段 | CFG 中存在交汇节点且单因素不足以覆盖时做 pairwise | 组合覆盖矩阵、路径/分支命中 |
| 依赖与秘密 | secretName、endpoint、region、instance、volumePath | AWS/GCP/Azure/IO/Block/Physical | 引用可解析、权限最小、目标非生产才允许运行 | RBAC 审计、引用解析、资源标签 |
| 组合编排 | Workflow templates/entry/parallel；Schedule concurrencyPolicy | Workflow/Schedule | 入口可达、模板引用闭合、并发策略明确才测 | 模板展开图、执行 DAG、并发事件 |
| 防御与恢复 | schema/admission、限流、熔断、自动清理、TTL、回滚 | 全部 | 只要节点可达且影响面非零就必须有至少一个恢复测试 | 拒绝原因、cleanup、恢复时间、孤儿资源扫描 |
| 观测与判定 | status、events、logs、metrics、traces、业务 SLO | 全部 | 没有可观测信号时先测“可观测性缺口”，不要宣称防御成功 | 证据时间线、指标基线/偏差、告警 |
| 变体与兼容 | 旧 apiVersion、模板变量、空值/错类型/未知字段 | 全部 | 版本或模板实际存在才测；保留“解析失败”和“运行拒绝”两类 | parser/schema 差异、兼容矩阵 |

## 测试节点中心的 CFG/DFG 影响子图规范
全局项目图只作为索引；真正用于测试决策的是以一个 `TestNode` 为根的局部切片。切片向后追踪配置、默认值、校验和目标选择，向前追踪注入点、调用、异常控制流、数据流、观测和恢复。每条边必须绑定静态位置、运行 trace、日志/指标或明确的 `hypothesis` 证据。

| 节点类型 | 示例 | 关键边 | 是否进入局部切片 |
|---|---|---|---|
| TestNode | `NetworkChaos.delay(app=ts-order-service, 5s)` | root -> Select/Inject | 必须，图的中心 |
| Config | `spec.delay.latency`, `spec.selector` | defines -> Default/Validator | 必须，解释测试参数 |
| Validator/Default | CRD、admission、controller 默认值 | guards/flows_to -> TestNode | 必须，判断是否被拦截或改写 |
| Selector/Target | namespace、label、Pod、Service、端口 | selects/scopes -> RuntimeTarget | 必须，判断真实命中范围 |
| Injector | tc/netem、HTTP proxy、cgroup、pod delete | injects -> RuntimeEffect | 必须，确认故障实际落点 |
| Call/Function | HTTP client、RPC、数据库访问、业务函数 | calls/data_depends -> Downstream | 只保留从测试节点可达的函数 |
| ControlFlow | timeout、retry、catch、fallback、熔断、幂等分支 | controls -> Outcome | 必须，解释防御行为 |
| DataFlow | latency/error/status -> exception、订单状态、消息 | flows_to -> Control/BusinessState | 必须，解释数据影响 |
| Observer | log、metric、trace、event、SLO、告警 | observes -> Outcome | 必须，形成判定证据 |
| Recovery | cleanup、TTL、reconcile、重试成功、回滚 | restores -> Service/Target | 必须，判断恢复是否完整 |
| Unrelated | 与测试节点无调用/数据/控制/观测关系的代码 | none | 排除，避免构建无意义全图 |

### Train Ticket 首轮测试子图
| 测试节点 | 局部 CFG/DFG 范围 | 首要判断 |
|---|---|---|
| HTTPChaos response 404 | 目标服务 HTTP 入口/客户端解码、异常映射、调用方 fallback、Trace | 404 是否进入预期降级分支，是否出现错误状态扩散 |
| HTTPChaos delay/abort | HTTP client timeout、重试、线程池、下游调用、业务请求结果 | 延迟/中止是否被限制，是否导致重试放大 |
| NetworkChaos delay | 目标 Pod 出站调用、网络错误、超时/熔断、下游服务和观测 | 5 秒网络延迟实际影响哪些调用和业务路径 |
| StressChaos CPU | 目标服务线程池、队列、健康探针、响应时间、资源指标 | CPU 压力是否导致排队、超时、探针重启或 SLO 越界 |
| Workflow | 子测试节点的顺序、并发、namespace 级命中和恢复依赖 | `mode: all` 是否扩大爆炸半径，串行/调度是否按预期执行 |

### 测试节点存在性判定
```text
声明存在：YAML/CRD 中存在节点
    -> 目标存在：selector 命中真实 Pod/Service
    -> 执行存在：Chaos Mesh/controller 能执行该故障
    -> 代码存在：存在受影响的调用/函数/分支
    -> 观测存在：能观察结果和恢复
    -> 测试必要：影响重要、证据不足、成本可接受
```

## 注入结果分类与根因标签
| 结果 | 判定条件 | 常见根因标签 |
|---|---|---|
| 防御住 | 在 schema/admission 阶段拒绝，或运行时有边界、告警、自动清理且 SLO 在目标内 | `schema_guard`、`admission_guard`、`scope_guard`、`rate_limit`、`auto_recovery` |
| 部分防御 | 接受注入但强度被限制，或短暂越界后恢复；证据链完整 | `default_clamp`、`partial_selector`、`delayed_reconcile`、`observability_lag` |
| 未防御 | 注入可达且超出安全不变量，无有效限制/清理/告警，或静默失败 | `missing_validation`、`selector_overmatch`、`cleanup_leak`、`race_condition`、`rbac_gap` |
| 测试无效 | 未命中目标、入口不可达、依赖缺失、观测不足以判定 | `unreachable_path`、`empty_selector`、`environment_mismatch`、`no_observability` |

## 知识库卡片最小字段
```yaml
id: KB-<kind>-<field>-<sequence>
kind: NetworkChaos
pattern: selector -> target -> delay -> recovery
hypothesis: "selector 命中范围扩大时，blast radius 增大"
test_recipe: {mutation: label-selector-expansion, preconditions: [...], stop_conditions: [...]}
outcome: defended|partial|not_defended|invalid
root_cause: selector_overmatch
evidence: [{artifact: ..., source_span: ..., run_id: ..., timestamp: ...}]
confidence: A|B|C|D
scope: {versions: [...], environments: [...], exclusions: [...]}
counterexamples: [KB-...]
status: candidate|reviewed|validated|deprecated
```

## 里程碑与建议顺序
1. M1（资产基线）：完成清单、解析分层、敏感值隔离；不执行注入。
2. M2（可达性）：拿到真实项目源码/镜像/CRD，产出 CFG/DFG 和字段可达性；没有这些证据的样本不进入运行队列。
3. M3（最小测试集）：每类资源选代表样本，先做身份、selector、边界、恢复和观测测试。
4. M4（受控注入）：隔离环境跑单因素，再跑必要的 pairwise/时序组合；每次自动清理。
5. M5（经验闭环）：完成防御/未防御根因归因，生成并审核知识卡片，重放验证。
6. M6（持续治理）：将 P0 用例接入版本变更门禁，建立漂移检测、回归和责任人机制。

## 错误记录
| 错误 | 尝试 | 处理 |
|---|---|---|
| 上一轮执行被用户中断 | 1 | 本轮从只读基线和持久化计划恢复 |
## Audit remediation checkpoint (2026-08-05)

The first implementation audit is closed for the current Train Ticket scope. Runtime injection is namespace- and mode-scoped, HTTP prerequisites fail closed, runner and parent cleanup are bounded and verified, classification/exit codes are shared, candidate selection is deterministic, slices carry blast-radius flags, and the evidence validator reports per-card detail. Regression tests cover these boundaries; future changes must update the root Git history and rerun the test and knowledge-base validation commands.
