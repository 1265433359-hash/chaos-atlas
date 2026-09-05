# ChaosAtlas 方法补强与后三阶段执行交接方案

编写日期：2026-09-05。核对基线：`0dbd1fce8a678fb9252678dfc51cfd08b66f4da2`。

本文交付给接手实施的模型。当前回合只编写方案；本文的存在不表示其中任务已完成、Oracle 已批准或实验已执行。接手后先核对最新代码和用户授权，继承已确认的选择，按阶段推进并保存真实证据。

## 1. 目标与既定约束

目标是提升 ChaosAtlas 面对新项目时的通用适配、假设生成、实验选择、业务异常判断和证据能力，在 Immich、Medusa、Rocket.Chat、ERPNext 上验证完整方法，产出可人工审核的 Issue 草稿和可追溯的论文数据。

- 保留唯一 `RunEngine`、公共 Oracle 注册表和统一 `IsolationManager`。
- 目录口径是 32 核心能力 + 9 provisional 扩展能力；41 是故障意图数，不能称作所有项目均已验证的 41 种故障。
- 当前四项目用于方法完善与能力实验，不运行 Full/noKB/noLLM 消融。
- 项目特有 API、字段、合成数据与薄蓝图允许配置化；公共生命周期、策略和判定逻辑不可复制成四套。
- 首次事务 Oracle 审批保留：先交付可审查的具体步骤、对象范围、断言和清理，再请人工审核。现有开发授权不能代替具体 Oracle 审批。
- 只使用专用测试账号与合成数据。Issue 只生成草稿，提交上游另需用户明确授权。
- 临时文件、运行证据、凭据和租约写到外置状态根。正式方案、代码、测试和脱敏汇总才进入仓库。
- 用户曾授权该项目提交推送；保留其有效授权，提交只包含当前阶段相关变更，保护其他模型/用户的未提交修改。

## 2. 必读材料与现有接入点

先读取仓库和相关子目录 AGENTS.md，再按需读取以下材料；不可只依据本方案概述改代码。

| 材料或代码（相对仓库根） | 用途 |
|---|---|
| `docs/superpowers/specs/2026-09-05-new-project-full-capability-bootstrap-design-zh-CN.md` | 已批准的五子项目总设计 |
| `docs/superpowers/specs/2026-09-05-unified-isolation-manager-design-zh-CN.md` | 隔离契约和安全要求 |
| `docs/superpowers/reports/2026-09-05-unified-isolation-manager-report-zh-CN.md` | 历史验收及其范围，需按本方案收紧过度表述 |
| `docs/superpowers/specs/2026-09-04-continuous-learning-ablation-design.md` | 借用知识冻结、RCA、遗漏审计原则；本轮不启动消融 |
| `src/chaosatlas/capabilities/` | 能力矩阵和证据等级 |
| `src/chaosatlas/isolation/` | planner、contracts、lease store、manager、providers、blueprint |
| `src/chaosatlas/oracles/contracts.py`、`registry.py` | WorkflowOracle 及工厂注册；扩展现有接口 |
| `src/chaosatlas/orchestration/engine.py` | RunRequest、RunDependencies、RunEngine、唯一候选循环 |
| `tools/llm_policy.py`、`policy_controller.py`、`stop_policy.py` | 现有策略选择与停止逻辑 |
| `tools/rca_loop.py`、`rca_runtime_loop.py`、`reproduction_policy.py` | 现有诊断、复现与证据门 |
| `scripts/run_isolation_acceptance.py` | 现有最小工作负载生命周期验收 |
| `projects/chaosatlas-apps/*/profile.json` | 四项目版本、入口和专用 namespace 声明 |

基线状态：能力发现和隔离生命周期已有实现；历史全量测试 309 passed，须由接手者重查。临时 L1/L2 验收使用 `pause:3.10.1`，证明最小资源生命周期，不证明四项目完整应用克隆成功。L1 adopted 曾在 Immich 验证，L3 曾验证空 Minikube profile 创建与释放。OracleBuilder、隔离与 Oracle 的完整 RunEngine 集成、四项目全面实验仍待完成。

## 3. 方案选择与推进顺序

采用“先修已知边界，再逐层接入真实业务”的方案。优点是能定位问题来源并复用现有资产；代价是正式实验启动前需要补验收。直接进入四项目大批量注入会把方法问题与应用问题混在一起；重写整套系统会增加迁移成本。这两条不作为默认路线。

保留原来剩余三个主阶段，增加一个前置补强任务 P0，不重新计算成五个全新项目。

| 顺序 | 工作 | 准入/退出要求 |
|---|---|---|
| P0 | 隔离实现纠错、验收范围校准、真实应用环境准备 | 关键安全缺口关闭；生命周期和业务代表性分开报告 |
| P3 | OracleBuilder 与四项目事务契约 | 生成、校验、人工批准、确定性重放、自检、失败补偿通过 |
| P4 | RunEngine 接入与假设驱动策略 | 全程通过统一引擎，运行目标绑定租约，证据和恢复完整 |
| P5 | 四项目完整能力实验与证据输出 | 逐项目、逐能力有明确结论；符合门槛才生成 Issue 草稿 |

P0 可以准备真实镜像、依赖和合成配置；业务代表性的最终验收依赖 P3 冻结 Oracle，两者共同通过后才进入 P4 的真实注入。避免让 P0 先依赖尚不存在的 OracleBuilder。

## 4. P0：先修正隔离实现与验收口径

### 4.1 已确认问题及待验证项

以下按证据性质区分。接手者先写必要的失败测试或只读复现，再修复；静态风险不能直接当成已发生事故。

| 项目 | 当前证据 | 要求 |
|---|---|---|
| 隔离等级回退 | 已只读复现：stress_memory、required=L1、proposed=L3、目标无 memory limit，effective 变成 L2 | 使用 required、proposed、机制最低要求的最大值；将 proposed 与升级理由写入计划和摘要；覆盖三等级组合 |
| 临时验收代表性不足 | 脚本 L1 ephemeral、L2 使用 pause 镜像 | 保留为基础设施冒烟；新增真实应用/目标验收，报告不得称 pause 为完整应用副本 |
| Ready 可能漏掉 Pending | 静态代码只检查 Running 子集并排除 Failed | 构造“一 Ready + 一 Pending”“副本不足”“滚动更新未完成”等反例；校验期望工作负载和就绪副本，而非只看已运行 Pod |
| 未知错误可能被当作 L3 不存在 | 静态代码以非零 status 退出码参与缺失判定 | 区分精确 profile 缺失、Docker 不可达、命令缺失、超时、JSON 损坏；保存 profile 清单与容器身份的正向缺失证明 |
| 清理恢复位置 | Provider runtime root 由调用端配置，验收脚本和 CLI 构造路径不同 | lease 固定运行根、context/cluster 身份；换进程使用公共 CLI recover 仍命中同一环境；不可因换 root 检查了另一个空目录而成功 |
| 敏感材料仍可能进入 blocked plan | planner 标记敏感路径后仍携带原 blueprint/target；CLI 会输出计划 | 凭据拒绝或在序列化前移除；测试 plan、stdout、lease、异常和审计均不出现 canary secret 值 |
| 并发与生命周期竞争 | 现有创建锁位于单 store；未证明跨 store 全机 L3 限制和 prepare/recover 竞争安全 | 验证进程锁、过期回收和中断语义；锁域与声明一致，运行中的 prepare 不得被并行清理 |
| 网络和资源隔离的真实效果 | 创建 NetworkPolicy、Quota 不等于数据面已实施约束 | 检验 CNI 策略实际生效和资源上限；防止蓝图放宽守卫，验证租约外探针不受影响 |

L3 Docker profile 仍共享 Docker Desktop/宿主机内核与资源，不应视作物理隔离。任何可能影响宿主节点、磁盘或其他 profile 的实验应要求相应隔离 Provider 或保持 blocked；不可仅凭 L3 标签放行。

补充检查创建失败窗口：资源创建成功但 UID 尚未写回时如何恢复、同名异 UID 如何拒绝删除、context 指向另一集群时如何阻断。未知身份保留人工恢复说明，不按前缀猜测删除。

### 4.2 支持真实应用启动所需的安全配置

当前编译器广泛禁止 Secret 引用、ConfigMap 引用和 PVC，而真实应用往往需要这些配置。新增来源可验证的引用规则：允许引用本次 lease 新建的测试配置、运行时生成凭据和新建空卷；继续拒绝源 namespace 数据复制、宿主挂载与未知外部数据依赖。不要通过关闭安全编译器来让应用启动。

记录 `environment_fidelity`：真实镜像/摘要、保留组件、替换依赖、缺失组件、测试数据类型、可检验机制与结论范围。默认复用已有 L1 专用测试副本；额外完成至少一个真实应用克隆和一个真实目标 L2 验收。P5 中每个使用 L2 的目标都需单独通过代表性门，不能把这两个样例推及所有应用。

P0 交付：修复代码、针对性反例测试、修订后的中文报告、公共 CLI 跨进程恢复证据、真实环境差异清单。P0 不运行资源耗尽或控制面故障。

## 5. P3：OracleBuilder 与业务判断能力

### 5.1 扩展现有 WorkflowOracle

沿用 prepare_fixture、probe、collect_evidence、cleanup_fixture 接口和 OracleRegistry。增加事务契约、生成接口、验证器、批准记录和通用重放器；文件可置于 `src/chaosatlas/oracles/`，避免再建独立主循环。

契约至少包含：schema、project/revision、Oracle ID/摘要、证据来源、允许 endpoint/方法、运行步骤、输入输出变量、断言、超时/轮询预算、对象所有权、失败补偿、凭据引用和批准状态。

LLM 输出结构化草稿，禁止直接执行自由 Python、Shell 或任意网络请求。状态流为 draft → validated → approved → frozen；内容/版本/目标作用域变化使旧批准失效。批准依据必须来自真实人工动作，模型不得自动填写 approved。

### 5.2 首批四个事务

| 项目 | 首批流程 | 关键检查 |
|---|---|---|
| Immich | 上传合成小图、查元数据、下载、删除 | 原始文件哈希/明确的转换契约、删除结果；重试去重按实际 API 约定判断 |
| Medusa | 建测试购物车、加入合成商品、读取价格、清理 | 价格计算、数量、货币与重复请求语义；商品/地区等依赖必须为测试夹具 |
| Rocket.Chat | 建测试房间、发消息、查询、删除 | 消息内容、房间归属、身份权限及异步可见性 |
| ERPNext | 建 ToDo 或无财务影响草稿、读、改、删 | 字段一致、更新生效、对象清理 |

执行前依据部署固定版本的源码/OpenAPI/官方文档确认 API。Medusa 若没有允许的购物车删除/失效接口，先提出准确补偿方案（例如 disposable 环境销毁）供审核，不能虚构接口、直接删数据库或悄悄放宽清理要求。

每项目一个事务是首批门槛。P5 再根据候选影响的业务路径增加必要断言，不无限扩展成通用全功能 UI 测试工具。

### 5.3 验证 Oracle 自身

- 正常业务样例通过，人工构造的错误哈希、错误金额、遗漏更新、重复对象等适用反例被捕获。
- 反例是测试 Oracle 的夹具，标记为合成，不进入应用缺陷或故障验证统计。
- 在每个写步骤失败、响应丢失、连接超时、进程中断时验证恢复清理。
- 对“写入已成功但响应丢失”保存创建意图，并通过幂等键/精确 run ownership 查回对象。不能只清理成功响应返回的 ID，也不能宽泛删除同名前缀对象。
- 最终一致性使用有界轮询；预期值来自独立业务契约/计算规则，不能把应用返回值原样当作正确答案。
- 记录服务存活、事务正确、机制生效三个独立结果。无机制证据不能把 no-impact 归因为应用防御。

P3 交付：四个可审核草稿、真实批准后冻结契约、自动自检、正常和失败补偿证据、对缺失凭据/权限的精确说明。未批准的部分保持未运行，不伪造通过。

## 6. P4：统一引擎与 LLM 的实质作用

### 6.1 接入顺序

在现有 RunDependencies 注入能力发现、隔离管理和 Oracle 工厂。候选计划引用 capability matrix、lease、frozen Oracle；运行时重新发现租约内资源并绑定其 UID/context/selector，保留源目标到隔离目标的映射。防止把源项目 selector 直接用于临时环境。

统一流程：能力发现 → 候选/假设 → 适用性与预算门 → 隔离环境 → 冻结 Oracle 夹具 → 基线 → 注入确认 → 机制与事务观察 → 恢复 → 数据清理 → 环境释放 → 证据判定 → RCA/学习。

顺序细化应兼容现有阶段协议。恢复和清理在异常路径仍尝试，业务数据应在销毁环境前完成核验；resume 不重复未确定结果的写操作或故障。旧入口只转发。

### 6.2 假设驱动策略

LLM 应提出可被推翻的实验假设，至少包含：

```text
hypothesis_id / source_evidence_refs / target_role / dependency_edge
fault_intent / approved_oracle_id / expected_mechanism / business_invariant
predicted_observation / alternative_explanations / falsifying_observation
parameter_tier / discriminating_next_action / knowledge_snapshot_id
```

例如：代码与契约提示某写接口可能缺少幂等处理，提出“响应超时后的重试可能造成重复对象”，通过适用故障、已有 Oracle 和重复对象断言验证。找不到证据则注明未知，不能虚构代码位置。

允许在 32+9 的可执行原语内组合新的“目标—业务路径—断言”候选；新增候选经过相同 schema、适用性、预算和审批门。LLM 建议新 Oracle 进入草稿队列，不能在运行中改写冻结断言。

先复用现有策略接口，不另造复杂优化器。保留探索预算、已批准参数层级和确定性 fallback；LLM 不可用时明确记录降级，不宣称本轮验证了 LLM 策略。

每次记录候选摘要、可见证据/知识快照、模型配置、结构化输出、采纳/拒绝及理由、实际结果、成本和停止原因。无需采集隐藏推理链。以这些记录检查 LLM 是否实际改变选择，并衡量预测、诊断、停止表现；当前无消融不能宣称 LLM 优于其他策略。

P4 交付：单候选和批量同一路径，错误注入/越界/中断测试，至少一次真实 LLM 建议被门禁处理的证据，以及低风险完整生命周期 canary。高风险实验以 P0 的实际隔离能力为前置。

## 7. P5：四项目实验、因果验证与 Issue 草稿

按 Immich → Medusa → Rocket.Chat → ERPNext 顺序。每项记录故障意图、目标、业务路径、Oracle、参数、隔离等级、执行器与机制证据，避免仅按项目汇总一个 supported 布尔值。

### 7.1 运行规则

1. 固定源码/镜像摘要、部署配置、依赖、测试数据、Oracle、模型与知识快照，建立稳定基线。
2. 全量静态评估 41 项。缺少资源语义为 inapplicable，环境缺前置为 blocked，执行器不支持为 unsupported；不得删除这些分母。
3. 在预先确定预算内先做低强度 canary，再根据机制与业务观察选择重复、升级、判别实验或停止。
4. 异常冻结因果身份与关键参数，在独立重置状态下完成至少三次有效复现；预注入失败不计入复现次数。
5. 配对无故障对照；必要时增加经过相同编排但不注入的对照，以及修改单个解释因素的判别实验。记录运行顺序和环境漂移，避免把后台负载趋势当成故障效果。
6. 恢复/清理失败停止当前项目注入，先处理残留。环境容量不足或机制不可验证时给出阻断证据。

三次复现是项目门槛，不是统计显著性。报告每次结果、波动、尝试总数和失效次数；样本不足不作总体概率结论。E3 的复现强度与 RCA 根因层级分开存储。

### 7.2 RCA 与草稿门

区分现象确认、服务边界确认、机制范围缩小和源码根因确认。对每个根因假设列出支持证据、反证与未排除解释。注入导致预期服务中断本身不足以形成上游缺陷。

只有异常复现、相关行为契约、对照、机制证据、恢复清理和敏感审查通过，才生成 Issue 草稿。归类为应用缺陷、部署配置问题、平台问题、方法问题或待判定；草稿投递对象随归因确定。

草稿包含固定版本、最小部署、合成数据步骤、期望与实际、三次运行引用、影响范围、替代解释、复现命令、恢复方法和限制。未得到上游确认只能称候选 finding。没有合格异常时明确报告零草稿，不为凑数量降低门槛。

## 8. 通用性、成本与持续学习记录

输出以下独立统计，不把一张 41 项覆盖表称作全面业务覆盖：

- 能力目录覆盖、适用目标覆盖、业务路径覆盖、真实注入完成率和机制验证率；所有分母可追溯。
- 接入时人工修改的 profile/蓝图/Oracle 量、必须修改公共代码的原因、人工审核次数；只记录可观测耗时。
- 每个独立因果问题的实验数、LLM/运行成本、首次确认成本；按根因和因果身份去重，不能把参数变体算成多个 Issue。
- 全部异常草稿的人工审核结果；未审核项保持 pending，不计为真阳性。
- 停止后从未执行候选中按风险/因果簇抽样作遗漏审计，默认约 15%，单独预算和报告。其结果不回灌同一轮策略；有限抽样不等于总体召回率。

知识按“项目 revision + 因果身份 + 适用范围”保存，保留反证、失败建议、no-impact 与 confirmed finding。每轮开始冻结只可见的历史快照；当前运行结束后才发布可复用记录，禁止未来项目证据提前进入检索。区分本项目即时观测反馈与跨项目知识晋级。

这四项目经过方法调试，属于开发/能力验证集。完成后给出独立的新项目迁移评估方案；当前不选定或执行新的第五项目，也不声称已经证明未知项目泛化。

建议外置产物：`capability_matrix.json`、`environment_fidelity.json`、`environment_lease.json`、`oracle_contract_ref.json`、`hypotheses.jsonl`、`decisions.jsonl`、`runtime_results.jsonl`、`reproduction_ledger.json`、`rca.json`、`knowledge_snapshot_manifest.json`、`coverage_summary.json`、`cost_summary.json`、`issue-drafts/`。优先复用现有 schema/证据 writer，新增字段必须有版本与哈希策略。

## 9. 验收、提交与维护边界

每阶段执行与风险相称的测试，保存外置原始结果；提交前运行仓库已有测试、架构、产品边界及卫生检查。使用实际运行输出报告通过数量，不复制历史 309 数字。

```powershell
& scripts/invoke_python.ps1 -m pytest -q
& scripts/invoke_python.ps1 scripts/check_workspace_hygiene.py --root .
git diff --check
```

仓库综合验收可复用 `scripts/run_repository_acceptance.py`，传入唯一外置 evidence-root/report。运行真实隔离前重查当前 profile、容量、工具版本和已有租约；命令成功不自动等于实验成功。

历史 `environment-reports/dify-1.17.0-docker` 曾被活跃 Dify bind mount 使用。先只读核对，若仍在使用，保持不动并记录卫生阻断。停止 Dify、迁移数据、改变 Compose 挂载属于独立维护任务；不能为获得 clean 输出直接移动数据库或修改 hygiene 规则忽略它。

建议逐阶段小提交，注明真实验证范围和剩余事项，不把 P3、P4、P5 全打包为一个不可审阅提交。已有报告纠错以新增范围说明和真实证据引用为主，保留历史原始实验。

## 10. 接手模型的执行纪律与最终汇报

- 开始先给简短当前状态和下一步，然后实施；上下文已确定的接口和偏好不再反复征求确认。
- 默认先单模型顺序执行阶段。若用户选择多个模型并行，应划分文件所有权、独立工作树和集成责任，公共契约先冻结，不能并行覆盖同一引擎。
- 凭据、Oracle 首次审核、超出当前边界的维护或外部副作用需要人工输入时，先完成可独立推进的实现、测试和具体审核材料，再集中提出问题。
- 不因困难把已批准目标换成演示；确有阻断时提交已完成部分和复现证据，清楚标注 partial/blocked，不使用 mock 冒充真实业务或真实 LLM。
- 完成汇报必须分开列出：实现状态、离线测试、真实生命周期、真实业务、真实故障、Issue/论文可用性、已知阻断、提交与远端状态。
- 遵守 AGENTS.md 的通知要求，邮件仅外置本地入队，内容不含凭据或原始业务数据。

最终完成标准：统一引擎能消费能力矩阵，在已验证的隔离环境中使用人工批准的事务 Oracle，通过受控 LLM 假设与策略选择完成实验、观察、恢复、清理、诊断和学习；四项目的全部 32+9 意图都有范围明确的结论，任何 Issue 草稿与论文数字都能追溯到对应证据。
