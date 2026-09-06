# P3 重放器补强、测试身份与后续阶段实施交接

日期：2026-09-06。只读核对基线：`6e81cd6`，工作区核对时无未提交变更。

本轮只编写交接计划，未修改执行代码、未批准新版事务契约、未创建应用账号、未执行真实业务写入或故障。
接手模型需先核对最新 HEAD 和工作区；本文不是能力完成证明。

## 1. 目标、授权和顺序

沿用 `2026-09-05-method-improvement-handoff-zh-CN.md` 的 P0 → P3 → P4 → P5 总方案。
本文件细化当前 P3 补强任务；对本文件未涉及的隔离、LLM、因果验证和论文要求，继续执行原交接方案。

用户已接受 `1C 2A 3A`：

- 1C：先修完重放器与契约，再交付完整新版复审材料。现有 v2 没有获批，不能自动填写批准记录。
- 2A：允许在四个专用测试环境中自动初始化合成测试身份；关闭欢迎邮件、外部通知等副作用。
- 3A：管理员只用于必要的初始化；日常事务使用最小权限身份，凭据通过测试 namespace 内 Secret 引用读取。

以上授权可用于接手实施，不应重新询问同一选择。本轮用户要求由其它模型执行，所以编写者在计划交付后停止实施。
首次正式事务执行仍等待用户审核最终版本的具体步骤、范围、断言、补偿与哈希；这道门来自已确认总方案第 5 节。
在等待最终审批之前，先完成能独立推进的代码、反例测试、固定版本 API 核对、身份初始化及审核材料。
身份权限测试仅限已授权初始化所需的身份/权限查询；不能以权限自检名义提前执行未批业务事务。

已经授权提交推送本项目相关变更。保留唯一 RunEngine、OracleRegistry、IsolationManager；允许配置化薄蓝图、API 契约和初始化配方。
本轮四项目不做消融，能力目录仍是 32 核心 + 9 provisional。上游 Issue 只生成草稿，提交另需明确授权。

## 2. 现状与证据口径

| 内容 | 已有状态 | 接手时如何处理 |
|---|---|---|
| P0 隔离补强 | 先前已提交，真实范围见 P0 报告 | 重查关键前提和租约，避免重复创建无用环境 |
| 四份 v1 | `6a659b7` 已记录人工批准并冻结 | 保留历史原件；当前执行器拒绝 v1 |
| 四份 v2 | `6e81cd6` 仅 validated | 有下述缺口，不直接批准或真实执行 |
| 通用重放器 | 已有初始代码与合成测试 | 补强现有接口，不能另起四套主链 |
| OracleBuilder | 当前按项目选静态模板 | 不能宣称已验证 LLM 生成能力；后续补结构化生成接口 |
| WorkflowOracle 集成 | engine 调用了 probe，未完整调用 prepare/collect/cleanup | P4 必须补全生命周期；导出类不等于集成完成 |
| 历史测试 | 上一轮 347 passed | 历史数字，仅供对照；不是本轮重跑结果或真实验收 |
| 真实事务 | 这批新事务尚无成功证据 | 健康检查不能替代上传、购物车、发消息、ToDo 验收 |
| 卫生门 | 上轮仅剩 environment-reports | 重查 Dify 挂载，禁止直接搬走活跃数据或修改规则掩盖 |

先前只读探测：Immich `isInitialized=false`；Medusa 无凭据 Store 请求被要求提供 publishable key；ERPNext 存在管理员 Secret；Rocket.Chat 在线但未验证专用身份。
这些不是当前实时状态。缺 key 的 400 只能证明该请求未带有效 key，不能证明应用内没有任何 key。
测试 namespace 声明也不能替代当前数据/身份边界检查。

## 3. 必读代码与报告

读取仓库及目标子目录 AGENTS.md，然后阅读：

- `docs/superpowers/plans/2026-09-05-method-improvement-handoff-zh-CN.md`
- `docs/superpowers/specs/2026-09-05-new-project-full-capability-bootstrap-design-zh-CN.md`
- `docs/superpowers/specs/2026-09-05-unified-isolation-manager-design-zh-CN.md`
- `docs/superpowers/reports/2026-09-06-p0-isolation-hardening-report-zh-CN.md`
- 两份 `docs/superpowers/reviews/2026-09-06-p3-oracle*-zh-CN.md`
- `src/chaosatlas/oracles/{transaction_contracts,builder,replay,registry,contracts}.py`
- `scripts/{approve_oracle_contracts,build_oracle_drafts,run_transaction_oracle_acceptance}.py`
- `tests/test_transaction_oracle_contracts.py`、`tests/test_transaction_oracle_replay.py`
- `src/chaosatlas/orchestration/engine.py`、`batch.py`，以及实际执行器中调用 probe 的路径
- `src/chaosatlas/isolation/`、四项目 profile、现有环境恢复 CLI 与证据 writer。

以下实施文件名为建议；优先复用已有公共组件。不要仅按文件名清单机械新增模块。

## 4. 先固定失败证据：H1

以下三项在 `6e81cd6` 用内存假 transport 只读复现，未访问应用、未落盘审批、未创建业务对象：

| 反例 | 实际输出 | 必须达到的结果 |
|---|---|---|
| Immich 上传和恢复重试均抛 ResponseLost | prepare_failed，但 cleanup_confirmed=true、executed_steps=[] | 不确定写入保留待恢复，清理不得成功 |
| fixtures 包含不同 run_id | prepare 的 run_id 被 fixtures 覆盖 | 运行身份受保护，在任何请求前拒绝冲突 |
| json_path_exists 的路径为 not-a-json-path | 对无关 JSON 返回 pass | 契约验证拒绝非法路径，运行求值也拒绝 |

新增能在当前代码失败的回归测试，记录修复前后结果。假 transport 的人工审批样例必须标为 synthetic-test-only，永不作为真实批准或应用证据。

同时为下述静态缺口写必要反例再修；它们在本文编写时是代码风险，不代表发生过真实事故：

- exact_lookup 直接 capture `[0]`，未证明唯一性、归属、分页完整性；Rocket.Chat 最新消息可能是系统消息或别人的消息。
- `_uncertain_write` 只在部分恢复分支设置；返回畸形 JSON、缺 ID、第二次超时、日志写入失败等均可能丢掉未决写入。
- 构造器保存外部 contract 引用、fixtures 可注入捕获 ID；已校验内容可能被调用者修改，后续删除可能使用伪造 ID。
- 默认 journal 是空回调，日志只含摘要；没有可靠的跨进程对象恢复账本、目标身份、持久化捕获映射。
- 大部分步骤缺成功状态/成功字段门；最终 probe 复用 prepare 的旧观察，可能把早先正确当成本轮正确。
- 未严格验证变量来源、重复 ID、JSON 路径完整语法、轮询正数/上限、请求/响应大小、模板可执行字段和未知字段。
- URL 校验不足以证明目标属于租约；替换路径变量未作路径段约束，header resolver 可能覆盖 Host 等路由字段。
- 清理只凭 HTTP 成功：Rocket.Chat 未确认房间消失，202/异步删除不能作为最终缺失证明。
- 独立验收脚本写死真实证据标记，且未接 Medusa 的环境释放；不能在缺释放器时先创建购物车再报告失败。
- `except Exception` 不覆盖 KeyboardInterrupt/SystemExit；脚本 finally 与重放器内清理可能重复，崩溃时可能完全未完成。
- 全部写事务发生在 prepare，故障期间只读；只能证明已创建对象的读取行为，不能据此宣称故障期间写入/重试行为已验证。

H1 退出：新增关键失败测试、问题到代码位置的映射、当前能力与风险列表。提交建议：`test: reproduce transaction recovery and ownership gaps`。

## 5. 契约和执行器补强：H2

### 5.1 冻结与验证

在现有 DSL 上增加需要的受限字段。建议保留 v1/v2 文件作为历史审计，生成 v3 schema/Oracle ID 和草稿，避免现有复审包哈希与新版内容混淆。
更新版本选择工具，不能仅生成新文件却仍只允许 v1/v2。

必须校验：唯一 request/step/assertion ID；请求白名单；输入类型及上限；变量定义和先后依赖；捕获字段的类型/来源；完整 JSON 路径语法；断言依赖；每步成功条件；阶段观察新鲜度；清理/恢复的完备性。
未知可执行字段拒绝，不静默忽略；缺 expected_from、非法路径或解析失败均不能与 null 恰好相等而通过。
拒绝 NaN、Infinity、非正间隔、无上限列表/轮询。deadline 覆盖请求与 sleep，不能靠 attempt 数伪装为时间上限。

冻结件须防外部别名修改，并在执行入口核对语义 hash、revision、环境作用域、解释器兼容版本；解释器语义改变必须经过版本兼容判定，不能沿用旧批准默默改变语义。
审批工具输入精确待审文件/哈希清单，先校验全部文件，再落盘；支持安全重试，不因第四份失败悄悄留下未报告的前三份批准。
批准引用真实用户动作；区分用户审批时间与程序记录时间，不把读取系统时间伪装为精确用户消息时间。

### 5.2 对象状态与所有权

用逐写操作账本代替 `_uncertain_write` 单布尔。至少表达：not_sent、intent_persisted、outcome_unknown、owned_confirmed、cleanup_pending、absent_confirmed、cleanup_blocked。
发请求前持久化意图；任何可能已到达服务端但尚未证明结果的异常都保留 outcome_unknown。仅有明确未发出证明时才可返回 not_required。
缺 ID、空响应、坏 JSON、capture 失败、超时、断连、进程退出、journal 失败均覆盖；未决写入不能被下一轮 prepare 清空。

运行生成的 run_id、lease_id、principal ID、captured IDs 不能来自普通 fixture 覆盖。普通夹具和响应捕获变量分命名空间或采用等效的强类型来源校验。
恢复必须同时验证对象类别、唯一标记、创建身份/所属父对象等固定版本可获取的证据；“返回了一个 ID”本身不证明为本次创建。
查回 0 条且可能最终一致时有界等待；查回多条、分页不完整、归属不符保留 ambiguity 并停止删除；不能随意选第一条。
精确删除账本中已证明本次拥有的对象。父对象已确定且契约批准级联删除时，可清掉未捕获子对象，但未能核实子对象行为的事务结果仍为 inconclusive。

### 5.3 可靠恢复、传输和清理

账本位于外置状态根，复用现有原子持久化/锁机制。保存 run/attempt/lease、契约 hash、目标身份、步骤、合成对象精确 ID、ownership 证据摘要和状态转换；不能保存密码、cookie、token 或真实业务正文。
故障前后的证据 journal 与恢复账本可以分开；仅有 body hash 不能支持跨进程查回。写前持久化失败必须阻断发送。
进程重启只做 reconcile/recover，不无条件重发未决写入；加入重复清理、并行恢复、账本损坏和同名新对象测试。
普通退出尝试补偿；外部强杀用独立恢复进程验证，不能声称 finally 可以处理强杀。

HTTP origin 由环境租约绑定，检查 scheme/authority/port、拒绝 userinfo/query/fragment、代理/重定向和保留 header 覆盖。路径变量只允许被编码的单一路径段，防止跨端点、查询注入、点路径和未解析占位符。
关闭响应对象并统一限制成功/错误响应大小；控制 multipart 字段/体积。只有固定版本证据支持幂等时才允许重试写操作。
身份凭据只注入合法认证 header，来自明确引用的 Secret；错误摘要必须可排查且脱敏，不能只有异常类名或写出原始敏感响应。

cleanup 成功要求：所有可能写入的对象都有明确归宿且缺失/环境销毁证明成立。删除成功响应不能代替缺失验证；401/403 或未知 404 也不能自动证明缺失。
释放失败或异常保持 cleanup_failed，保留重试材料，停止该项目下一次注入。业务清理、环境释放各保存结果，不能互相覆盖。
Medusa 在发送请求前必须有可验证的 disposable lease 和公共环境释放能力；环境最终销毁只能由 IsolationManager 负责，不能把任意 callback 返回 True 当真实审计。
保留“业务清理完成后才销毁环境”的顺序；避免清理失败过早销毁唯一诊断信息，先收集脱敏证据。

H2 退出：全部 H1 反例变绿、协议/账本/传输/恢复测试通过、无新真实业务写入。按验证器、恢复账本、执行器分小提交。

## 6. 四项目契约和身份：H3

### 6.1 先核实固定版本 API

从部署镜像内代码、对应源码 tag/commit、该版本 OpenAPI 验证路径、HTTP 方法、请求和响应字段、权限、去重、异步删除及错误语义。
文档链接只能作为证据入口；当前 main/latest 不能直接替代固定版本。profile 的 project_commit 如是配置指纹，应另列真实 source revision，不要误称为上游 commit。
每份草稿 evidence_sources 含实际来源、版本、路径/操作、内容 hash 与推导结论。无法确认项保持 unknown，不能先编接口通过模拟测试。

| 项目 | 必须解决的事务细节 |
|---|---|
| Immich | 原始 PNG 必须由独立解码器确认合法，独立计算哈希；每运行生成唯一合成内容，防固定图片命中旧资产。核实去重到底按 checksum 还是 deviceAssetId，以及 200 duplicate 的含义。重复结果不自动取得删除权；先校验归属。删除 force=true 仅限本次合成资产，并核实异步删除和原件缺失。 |
| Medusa | 在本次 disposable 数据库创建合成 region/currency/product/variant/sales channel/key；所有初始化对象随租约销毁。价格预期由 fixture 清单独立计算，数量/币种/关联 variant/价格项全部核实。查 line 不靠 items[0]；cart 响应丢失且没有精确查询接口时停止业务判定，通过租约销毁收尾。 |
| Rocket.Chat | 查 roomName 要核对创建者与精确 room ID。消息按唯一标记、发送者、room ID 精确匹配，排除系统消息，结果不确定时不能把最新消息当目标。删除检查 success 字段，并通过正确查询证明房间消失；明确权限不足与不存在的区别。 |
| ERPNext | ToDo 查询核实精确 description、owner、name 和数量；保留“创建前不存在”的证据。确认 PUT 重试语义、描述字段是否转换、成功状态和 DELETE 最终缺失条件。只读阶段检查更新后状态及内容均为本轮新响应。 |

新增响应丢失查回/校验端点须编码进草稿并展示 diff；不在 Python 中隐藏额外项目请求。
H3 首批可保留故障期间只读探测，但明确其验证范围。若 P4/P5 要测试写入受扰，新增受控阶段写步骤并纳入同一审批；不得在运行中绕过冻结契约扩写。

### 6.2 按已授权 2A/3A 初始化身份

先检查目标 context/cluster UID、namespace、dedicated 声明与现有账号状态；不导出所有 Secret 值或扫描无关私人凭据目录。
允许对已声明的四个测试环境创建合成身份；新建受 IsolationManager 管理的 disposable 测试环境沿用同一合成/最小权限要求。
用户名可采用 `chaosatlas-oracle` 加受控唯一后缀，邮箱使用 `.invalid` 合成地址，禁止使用用户 QQ 邮箱作为测试联系人。

- 已有管理员：仅通过已配置的合法管理员凭据调用官方初始化接口；不重置现有密码。
- 全新未初始化实例：允许创建必要的 bootstrap 管理员，随后创建普通测试身份；管理员凭据与实验凭据隔离，保留可恢复的初始化记录。
- 存量实例缺管理员凭据：先完成其余代码/其它项目，记录精确缺失引用；不能通过数据库直接改权限、破解或接管账号。
- Rocket.Chat 若初始化要求云注册、许可证或真实邮箱，先形成具体阻断材料；现有授权不包含代用户接受条款或注册外部服务。
- 最小权限按实际版本权限模型确认；若某项操作必须 admin 或需扩大到共享全局角色，记录原因和可选方案，不自动回退为全程管理员。
- ERPNext 仅 ToDo 所需权限；Rocket.Chat 仅测试频道创建/消息读写/本次频道删除；Immich 仅测试用户资产操作；Medusa Store key 限测试 sales channel。
- 关闭欢迎邮件、邀请和外部通知；不能全局修改无关用户设置。初始化也要有对象意图、重试查回和撤销规则。

凭据随机生成且仅在内存与精确 Secret 间传递，禁止出现在 argv、stdout、日志、临时明文文件、plan、lease、Git。
Secret 的 base64 不是加密；限制 namespace/RBAC、仅记录 Secret 名称/UID/key 名和身份范围，勿宣称其具有未验证的加密保障。
持久测试账号按项目保留复用，并记录轮换/撤销；事务合成对象按 run 清理；disposable 身份随 lease 销毁。

### 6.3 最终复审包

一次性交付：四份最终 validated 草稿及哈希清单、相对 v1/v2 的语义 diff、固定版本 API 证据、权限与初始化报告、恢复/清理规则、反例测试输出、遗留阻断及真实验收步骤。
报告必须纠正旧 v2 复审包中把“存在测试样例”泛化成全部边界已覆盖的措辞；保留历史材料。
只请求批准最终内容，不重新问 2A/3A。此时才是人工确认的正常暂停点。
审批前代码可以支持 frozen 执行并用合成审批测试，但四份实际待审件必须保持 validated。

H3 退出：复审材料完整、已授权初始化有明确结果、待批准 hash 锁定并提交。未获最终批准时停在此处，不进入 H4 的真实业务写入。

## 7. 获批后的真实验收：H4

实际用户批准后记录精确 hash/版本清单，再核对部署身份，冻结并按 Immich → Medusa → Rocket.Chat → ERPNext 执行。
审批记录不能自动从“方案同意”“默认 A”推导；不同草稿或解释器语义不能偷用本次批准。

每项目验收至少包含：

1. 正常事务：真实创建、独立预期检查、新鲜读回、精确删除、缺失确认、租约释放/保留审计。
2. Oracle 自检：对真实响应的脱敏副本构造错哈希/错价格/错状态/重复对象等反例，标记 synthetic_oracle_self_check，不计应用故障。
3. 每写步骤前失败、服务已写入但响应被丢弃、连接超时、畸形/不完整响应；确认方法能收敛或准确报告未决。
4. 清理响应丢失、暂时不可达、重复 cleanup、跨进程恢复；保护与本次 run 无关的合成对照对象。
5. 在关键窗口外部终止测试进程，独立进程读取账本恢复；损坏账本或身份不匹配必须拒绝删除。

明确标记故障位置：在客户端丢弃一次真实服务响应，可以验证未知提交结果处理，但不是服务端网络故障、Chaos Mesh 注入或应用缺陷。
本地 HTTP 测试服务只能证明传输协议逻辑；真实应用验收必须调用上述固定版本应用。
缺失证据时结果为 blocked/failed/inconclusive，不仅保存一个 passed 布尔。

修订 `run_transaction_oracle_acceptance.py` 为薄测试入口：复用 WorkflowOracle 与 IsolationManager；负责选择无故障验收用例和记录结果，不负责候选循环/故障策略/RCA/学习。
先完成 P3 组件真实验收，再在 P4 用 RunEngine 重做集成 canary，避免组件验收与完整方法混淆。
机制、生存、事务正确、清理、环境释放分别记录；P3 无真实故障时 mechanism=not_run，不能填 pass。

H4 退出：四项目正常事务与失败补偿有真实证据，所有残留有确定归宿；逐项目报告 implemented/tested/real-evidence。
缺少账号/权限或实际 API 不符时提交已完成部分，集中提供具体材料；不能换为健康检查来宣布 P3 完成。

## 8. 承接 P4、P5

P3 完整验收后继续原交接方案，重点处理下列已知接入点：

- OracleRegistry 注册通用事务工厂，运行依赖提供凭据、journal、租约目标绑定；不能仅在 `__init__.py` 导出就称接入完成。
- RunEngine 统一调用 prepare_fixture → baseline → 注入确认 → observe → recovery → collect_evidence → cleanup_fixture → release，并处理任一阶段异常；现有 stage 协议必要时版本化扩展。
- 单候选、批量、resume 共用同一路径；只在尚未产生不确定副作用时允许重试。对象/故障恢复均依赖持久账本。
- 隔离环境内重新发现目标并绑定 context/UID/selector，不能复用源环境 selector；移交前先核实 P0 的数据面隔离证据。
- 实现 OracleBuilder 结构化生成入口与假设驱动策略；LLM 输出只进草稿/门禁，不能执行自由代码或更改冻结断言。
- 真正调用一次可用 LLM，记录输入证据、结构化输出、采纳/拒绝理由、成本及模型；不可用则标记 fallback，不能用静态模板称 LLM 已验证。
- 完整 canary 通过后才做四项目 32+9 静态全量评估和可执行候选低强度实验。主集群 kindnet 的历史跨 namespace 隔离失败仍需正向复核；不要把 Calico 一次通过推广到所有环境。
- P5 保留 blocked/inapplicable/unsupported 分母；三次独立复现、配对对照、机制证据、恢复清理、因果范围及敏感审查全部满足才生成候选 Issue 草稿。
- 保存知识快照、反证、no-impact、人工审核、成本、遗漏审计数据。本轮属于开发/能力验证集，不声称未知项目泛化或 LLM 相对优势。

## 9. 验证、提交和外置材料

从现在运行 Python 都使用公共 wrapper，避免重新生成仓库内 __pycache__：

```powershell
& scripts/invoke_python.ps1 -m pytest tests/test_transaction_oracle_contracts.py tests/test_transaction_oracle_replay.py -q
& scripts/invoke_python.ps1 -m pytest -q
& scripts/invoke_python.ps1 scripts/check_workspace_hygiene.py --root .
git diff --check
```

新测试文件加入专项命令；源码/事务变更后运行适当回归，提交前按仓库要求执行综合验收和架构门。先查看 `scripts/run_repository_acceptance.py --help` 再按当前接口传外置路径，不虚构参数。
每条失败命令必须处理并报告，不能靠最后一条成功的 shell 命令掩盖先前失败。

运行证据统一放 `%LOCALAPPDATA%\ChaosAtlas\runs\<唯一运行名>`，状态账本放相应外置状态根。建议材料：

- implementation-gap-report.json、test-results、contract-review-manifest.json；
- api-evidence-manifest.json、identity-bootstrap-report.json、runtime-binding.json；
- transaction-journal.jsonl、transaction-recovery-ledger.json、ownership-audit.json；
- environment_fidelity.json、environment_lease.json、cleanup-audit.json、acceptance-summary.json；
- 原总方案 P4/P5 要求的 hypotheses/decisions/coverage/reproduction/RCA/knowledge/cost/Issue 草稿。

实际 runtime claim 必须有固定版本应用、目标身份、已批准契约和原始运行引用。不要硬编码 claim_scope=real_business_transaction，让空跑或假 transport 获得同样标签。
敏感扫描在持久化前做白名单脱敏，并在落盘后核查；命中时阻断证据晋级，安全处理命中文件，不只是改 summary 状态后继续暴露。
仅正式代码、测试、契约、计划和脱敏汇总进入 Git。

建议提交批次：H1 失败反例；H2 验证/账本/执行器；H3 初始化与最终复审；真实批准件；H4 真实验收；P4 集成；P5 实验汇总。
提交前检查工作区，保护用户及其它模型变更；不批量 stage 无关文件。推送后核对远端实际 SHA，报告是否同步。
历史 environment-reports 若仍被 Dify 挂载，保持不动并报告卫生门 blocked；停止/迁移 Dify 是独立维护授权，不能从本计划推导。

## 10. 给接手模型的启动指令

> 请先读取本文件和原 2026-09-05 方法补强交接方案，核对最新 HEAD、AGENTS.md、当前实现与环境。沿用用户已接受的 1C 2A 3A，从 H1 关键失败反例开始，依次完成 H2/H3 的代码、测试、固定版本证据与已授权测试身份初始化。所有临时文件、运行证据和秘密保持外置；提交推送仅包含本阶段改动。先交付四份最终可审查草稿、语义 diff、精确哈希、权限/清理/恢复和验证结果，再集中请求首次真实事务审批，不重复询问已定选择。获得实际批准后按 H4 做真实应用正常事务与失败补偿，再继续原方案 P4/P5。严格区分静态、合成自检、真实组件验收和统一引擎真实故障证据；遇到阻断先完成独立可推进事项并提供具体材料，不能模拟通过或降低证据门槛。

本计划验收标准：接手者能明确先改哪里、如何证明修复、哪些工作已授权、唯一正常审批暂停点在哪里，以及获批后如何继续到统一方法正式实验。
