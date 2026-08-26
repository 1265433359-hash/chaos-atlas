# 真实 YAML 测试节点知识库与项目影响子图计划

## 2026-08-24 Phase 16 第二项目接入复核

- [complete] 使用 Online Boutique 离线 profile 运行统一 `chaosatlas run --mode dry-run`。
- [complete] 验证项目 profile、inventory、服务器部署检测、候选映射、知识检索和 evidence plan 的跨项目契约。
- [complete] 验证第二项目知识 root 隔离：Sock Shop 知识不参与检索、排序或晋级。
- [complete] 验证 synthetic/not_run 边界：dry-run 不产生漏洞、RCA 或正式知识声明。
- [complete] 在独立 Online Boutique namespace 执行真实只读 evidence smoke，并冻结 runtime-backed shadow 的输入分母。
- [complete] 在第二项目完成受控 runtime shadow 和知识晋级；guarded policy 扩大范围仍保持 pending。

## 2026-08-24 Phase 17 第二项目真实只读 evidence smoke

- [complete] 使用显式 `minikube` context 对 `chaosatlas-online-boutique` 做真实只读 inventory。
- [complete] 复用服务器部署检测、候选映射、单候选 evidence plan 和 planned collector。
- [complete] 记录 Deployment/Service/Pod/Events/Logs 的 supports/unavailable 证据及 `planned_action_id` provenance。
- [complete] 完成副作用审计：无 mutation、无模型调用、无正式知识写入、无 Chaos 残留。
- [complete] 恢复 Online Boutique 独立 namespace 的可用副本并验证业务 Oracle 基线。
- [complete] 经显式批准执行单候选 runtime-backed shadow，并完成两次独立有效重复；policy guarded 扩大范围仍保持 pending。

## 2026-08-24 Phase 18 第二项目 runtime 闭环与知识晋级

- [complete] 恢复 Online Boutique 独立 namespace 副本并通过业务 HTTP 基线。
- [complete] 完成首个单候选 `frontend/pod_kill` runtime shadow，输出 availability、RCA、recovery 和 cleanup 证据。
- [complete] 使用不同 seed 完成第二个独立有效重复，拒绝相同 seed 仅凭相同 run_id 直接晋级。
- [complete] 通过 weakness promotion stage 将两次重复发布为 `local_reusable` weakness card，并生成 reproduce/guard intents。
- [complete] 用正式 Online Boutique knowledge root 回放 dry-run，验证知识检索和候选首选回流。
- [pending] 在第三个项目完成同样的 runtime evidence/shadow 对照，评估跨项目知识迁移边界。
- [pending] 修复或统一旧版 knowledge validator 与新版 weakness card schema 的验证入口，避免工具名相同但契约不一致。

## 2026-08-24 Shadow rollout and evidence-planner checkpoint

- 静态服务候选映射：complete。
- Online Boutique frozen Legacy/Shadow replay：complete（离线、无模型、无 runtime 注入）。
- replay comparison gate：`complete`；已获得第二项目 runtime-backed Shadow 与 Guarded r2 证据，默认仍保持 `legacy`，不自动扩大 guarded 范围。
- 只读证据规划器接入 `chaosatlas run`：complete；live blocked plan 在 executor 前 fail closed。
- 归档换行/hash 漂移与旧防御夹具：complete；当前全量测试无失败。
- Shadow replay：`complete`；Online Boutique offline/runtime Shadow 输入和 guarded r2 已有独立 artifact，跨项目 superiority 与默认 rollout 仍未宣称。

## 2026-08-23 Phase 4 防御知识晋级接入
- 目标：将显式历史防御运行的晋级、冲突降级和 advisory 边界接入统一 `chaosatlas run`。
- 阶段 1：防御历史选择器和结构化拒绝产物。状态：complete。
- 阶段 2：两次独立运行晋级、显式知识写入和冲突保留。状态：complete。
- 阶段 3：`promote_defense` checkpoint stage、CLI 参数和只读 knowledge root。状态：complete。
- 阶段 4：advisory provider 白名单解析和确定性 fallback。状态：complete。
- 阶段 5：focused regression、compile、diff check 和 CLI 帮助验证。状态：complete（73 passed）。
- 后续：补 Train Ticket latency boundary fixture；再进入 Phase 5 的结构化部署 patch、fresh deploy、同场景复测。

## 2026-08-23 Phase 4 exit gate
- Train Ticket latency boundary fixture：complete。
- Sock Shop redundancy promotion fixture：complete。
- 无知识/local_reusable 知识排序差异：已由现有 knowledge feedback tests 覆盖。
- Phase 4 状态：complete（76 focused tests passed）。
- 下一阶段：Phase 5 只支持结构化部署 patch，执行 fresh deploy、同场景同 Oracle 复测并输出 improvement_verified/regression/deployment_blocked/not_run。

## 2026-08-23 Phase 5 离线改进复测门
- 结构化 patch allow-list（replicas/PDB/HPA/probes/resources）：complete。
- immutable source copy 与非法 pointer fail-closed：complete。
- 可注入 server-side dry-run validator，阻断时不调用 executor：complete。
- 四态 retest result 与 improvement evidence/feedback validation：complete（85 focused tests）。
- fresh namespace/deployment adapter 和真实同场景复测：pending；必须另设 live approval、namespace allow-list、rollback 和残留扫描，不在离线阶段伪造完成。

## 2026-08-23 Phase 5 fresh-deploy adapter
- namespace-scoped immutable manifest validator：complete。
- server-side dry-run / explicit apply / cleanup adapter：complete（默认禁止 live mutation）。
- patched copy 在复测前执行 server-side dry-run：complete。
- 真实 Sock Shop fresh namespace 同场景复测：pending，等待显式 live 环境批准和 deployment source 选择。

## 当前执行：真实 Kubernetes inventory 与自动候选（2026-08-21）
- 目标：让 live CLI 从 namespace 内只读发现 Deployment/Service/Pod，构建统一部署节点和可验证故障候选；不在发现阶段注入、不把候选当漏洞。
- 阶段 1：实现 KubernetesProjectAdapter，完成 namespace allow-list、只读 inventory、失败关闭和结构化 hash。状态：complete。
- 阶段 2：从 live inventory 生成 Deployment/TestNode/故障候选，复用现有 scenario compiler 和 gate。状态：complete。
- 阶段 3：接入 `chaosatlas.py --mode live`，保留 executor 注入测试和显式 live approval。状态：complete。
- 阶段 4：focused tests、compile、diff check、集群只读残留检查。状态：complete（54 passed；真实 sock-shop-lab 只读发现 14 deployments/14 services/14 pods、84 candidates；未执行注入）。
- 后续：接入日志/events/业务证据到 RCA，再实现知识卡验证和下一轮候选变化；本阶段不自动晋级知识。
- 安全边界：只读 inventory 不执行 kubectl apply/delete/patch；真实注入仍由现有 KubernetesLifecycleExecutor 管理。

## 当前执行：运行证据与 RCA 交接（2026-08-21）
- 目标：把 live executor 的 lifecycle 结果与 Kubernetes events/logs 证据写入统一运行目录，生成有证据边界的 RCA pending 报告。
- 阶段 1：接入 KubernetesEvidenceCollector 和 evidence_refs.json。状态：complete。
- 阶段 2：分类结果引用 evidence refs，RCA 明确待补证据和禁止晋级条件。状态：complete（live 结果保持 `pending`，不可自动晋级）。
- 阶段 3：focused tests、真实只读 evidence smoke、compile、diff check。状态：complete（63 passed；events/logs smoke 均返回 supports evidence；未执行注入）。
- 后续：将 RCA confirmed/provisional 结果接入知识卡验证和下一轮候选重排；本阶段不自动更新知识库。

## 当前执行：live preflight 安全门（2026-08-21）
- 目标：在 live executor 前强制运行只读 KubernetesPreflight，残留 Chaos、kubeconfig、namespace、资源或 events 不可用时 fail closed。
- 阶段 1：接入 preflight artifact 和 executor 前阻断。状态：complete。
- 阶段 2：focused tests、真实 preflight smoke、compile、diff check、残留扫描。状态：complete（67 passed；真实 preflight ready_for_injection，residual clean；未执行注入）。
- 后续：RCA confirmed/provisional 状态转移、知识卡验证和下一轮候选改变。

## 当前执行：业务 Oracle 证据闭合约束（2026-08-21）
- 目标：把业务路径回放摘要作为 `business_path_replay` evidence，并要求 live PodKill 目标与 Oracle service 对齐。
- 阶段 1：写入去敏 business observation evidence。状态：complete。
- 阶段 2：Oracle service/候选目标不匹配时 fail closed。状态：complete。
- 阶段 3：最终 focused tests、compile、真实只读 inventory/preflight/residual 验证。状态：complete（67 passed；14/14/14、84 candidates、preflight ready、residual clean）。
- 下一阶段：把 evidence contract 映射到确定性 RCA 状态转移；只有达到 confirmed 条件才生成 provisional knowledge draft。

## 当前任务：按论文主线完成全项目整理归档（2026-08-16）
- 目标：统一 README、项目总览、归档地图和实验目录的当前口径；明确主线、冻结历史材料、未来工作与证据入口；为主线关键工具补充模块职责和副作用注释。
- 阶段 1：核对当前主线、历史边界、文档矛盾和关键工具入口。状态：complete。
- 阶段 2：更新项目总览、README、归档地图和实验目录。状态：complete。
- 阶段 3：为主线关键工具补充模块级和关键门禁注释。状态：complete。
- 阶段 4：运行文档一致性、代码语法/测试和敏感信息检查。状态：complete（focused 66 passed + 5 subtests；全量 643 passed、2 个已知历史 pinned-hash drift；Python 编译、diff check、归档入口断言和敏感模式扫描通过）。
- 阶段 5：审查差异并汇报整理结果；不擅自提交、推送或上传。状态：complete。
- 边界：不移动、删除或覆盖实验产物；不重跑 Kubernetes 实验；不调用模型、不读取密钥；不把 pending 审核写入知识库；不将无关未跟踪文件加入提交。

## GitHub 上传前保守清理（2026-08-21）
- 目标：停止跟踪本地工具分发物和 pytest 临时缓存，保持实验主线与历史证据完整。
- 阶段 1：确认 `tools/bin/` 跟踪范围、远端分支和临时目录边界。状态：complete。
- 阶段 2：加入忽略规则，索引中移除 `tools/bin/`，清理根目录 `.pytest-tmp/`。状态：complete。
- 阶段 3：运行主线验证并检查本地文件仍存在；形成本地清理提交。状态：complete（commit `b879feb`；1036 passed，2 个既有 pinned-hash drift）。
- 阶段 4：等待用户明确授权后再决定是否推送；不做历史重写或 force-push。状态：pending。
- 边界：不删除 `artifacts/`、`raw_yaml/`、知识库、实验台账或失败证据；不把未筛选的大型目录加入提交。

## 下一阶段：主线固化与远端发布准备（2026-08-21）
- 阶段 1：盘点当前未提交的 Phase 0/2 主线代码、测试和产物，按“主线 / 证据 / 临时 / 无关改动”分组；不使用 `git add .`。状态：pending。
- 阶段 2：对准备提交的主线代码运行 focused tests、全量 tests、编译、敏感信息和路径引用检查；保留两个既有 hash 漂移为显式问题，必要时单独修复。状态：pending。
- 阶段 3：选择性提交 Phase 0/2 主线代码和必要文档，确保清理提交与功能提交边界清楚。状态：pending。
- 阶段 4：生成 GitHub 出境清单，确认 13 个本地领先提交和提交内容；默认只做普通 push，不做历史重写。状态：pending。
- 阶段 5：远端同步后，回到知识闭环消费端，执行已验证先验的回归重放和决策命中审计；不自动晋级新知识。状态：pending。
- 决策点：若要清除远端历史中的 Helm 二进制，必须另行批准 `git filter-repo` + force-push；这不属于默认发布路径。

## 当前主线：闭环方法完善与实验项目扩展（2026-08-21）
- 总目标：把“项目接入 → TestNode/影响子图 → 适用性门禁 → CE 注入 → 证据采集 → RCA → 防御/伪防御判定 → 知识升级 → 回归选择”固化为可重复工具方法，再扩展到更多技术栈和项目。
- 阶段 1：闭环协议硬化。统一 project profile、运行状态机、证据 contract、RCA 状态转移、知识 promotion、retrieval/guard 和 replay 的接口与失败状态。状态：pending。
- 阶段 2：方法验收。对 Sock Shop、Online Boutique 和 P02 现有证据做离线重放；要求不依赖 LLM 最终裁决，能区分 weakness、defended、observation artifact、platform blocked 和 not reachable。状态：pending。
- 阶段 3：单项目扩展。每个已接入项目至少覆盖一个 PodChaos、一个网络/协议故障和一个业务 oracle；统一记录基线、注入、恢复、清理、UID/endpoint 共证和知识回归。状态：pending。
- 阶段 4：跨项目扩展。优先选择技术栈、协议和部署形态不同的项目；先静态接入和 dry-run，再小规模真实双臂实验，最后才扩大候选量。状态：pending。
- 阶段 5：规模化评估。比较知识启用/禁用、候选命中率、有效注入率、真实弱点发现、误判率、RCA 边界和回归收益；所有结论按项目、协议和 oracle 分层。状态：pending。
- 发布支线：GitHub 普通 push 和历史清理暂不阻塞方法闭环；只有在主线代码和验证稳定后执行。

## 统一离线闭环编排器（2026-08-21）
- 目标：将项目事实、服务器部署检测、经验检索、advisory 假设、门禁、RCA、知识草稿和回归意图收束为一条可恢复的 dry-run 命令。
- 状态：complete（`tools/chaosatlas.py`、协议/adapter/假设模块及 focused tests 已完成；Sock Shop、Online Boutique、P02 离线回放通过）。
- 术语边界：使用“服务器部署检测能力”描述平台无关的部署检测和可测试空间建模；CE 仅保留为后续可选执行 adapter，不作为能力层名称。
- 验收：离线命令输出 `dry_run_ready`，生成阶段 artifact、checkpoint、RCA/知识/回归草稿；fake evidence 明确为 synthetic，不生成 runtime weakness/defended 结论。

## Sock Shop Ablation YAML15 重做（2026-08-16）
- 目标：按五类明确标注各 3 个真实 YAML，作为新版 Ablation 的唯一新增前置知识；保持无知识库、无项目调用链证据、无置信度、LLM 自停和 Full discovery wall-clock 硬上限，重做 discovery 与 runtime。
- 阶段 1：冻结设计、选择规则和实现计划。状态：complete。
- 阶段 2：实现 YAML15 确定性选择、结构化去敏、双 hash 和输入审计。状态：complete（r1 审计发现嵌套 URL 泄漏并保留为失败证据；r2 修复后 15/15 hash 一致、敏感扫描 0 命中、确定性复跑一致）。
- 阶段 3：扩展独立 `chaosatlas-ablation-yaml15` discovery 协议并完成离线回归。状态：complete（14 个 focused tests 通过；fake discovery 自停并由公共编译器生成 4/4 候选）。
- 阶段 4：运行 DeepSeek discovery、自去重、公共编译器和静态 gate。状态：in_progress（模型调用前全量相关回归与输入审计中）。
- 阶段 5：对所有 gate 通过的唯一 family 各运行两次，逐轮确认恢复、cleanup、washout 和全局无残留。状态：pending。
- 阶段 6：替换旧 Ablation 正式分栏，与 Full 冻结口径比较，生成 pending 审核并选择性提交。状态：pending。
- 边界：不重跑 Full discovery 或既有 Full mutation；YAML15 选择不使用 runtime outcome；旧 Ablation 保留但不叠加；不更新知识库；不覆盖已有实验目录。

## Sock Shop 三方法阶段结果归档（2026-08-16）
- 目标：按当前证据整理 `ChaosAtlas-full`、最终版 `ChaosAtlas-ablation` 和 ChaosEater 原生结果，冻结统计口径、问题覆盖关系与证据边界，为后续重做 Ablation 保留可替换入口。
- 阶段 1：复核 Full 全部 completed runtime 报告，按 `mutation_id + replicate` 取最新完成记录并统计稳定/不稳定/无影响。状态：complete（114 个冻结 family 均有静态适用性处置；96 个进入 runtime cohort，其中 88 个完成 176 个注入重复槽位、8 个 DNSChaos 被平台 gate 阻断；15 个稳定、3 个不稳定、70 个未观察到弱点；另 18 个被静态 gate 拒绝）。
- 阶段 2：复核当前最终 Ablation 与 ChaosEater 证据，区分正式结果、exploratory 结果和仅有会话摘要但尚缺统一机器台账的结果。状态：complete。
- 阶段 3：生成阶段对比报告和机器可读摘要，更新论文主线、项目总览及归档索引。状态：complete。
- 阶段 4：执行 JSON/Markdown 引用、数字一致性和敏感信息检查；审核 diff。状态：complete（JSON 算术一致、6/6 证据路径存在、敏感模式 0 命中；未提交）。
- 冻结边界：same-pool、预选池和早期 pilot 不进入本轮统计；Ablation 标记为待重做；`human_review=pending`、`knowledge_base_updated=false`；不重跑实验、不调用外部模型、不读取密钥。

## Git 上传前整理归档（2026-08-14）
- 目标：把当前 ChaosAtlas 阶段成果整理为可上传前复核的仓库状态，明确提交范围、排除临时目录、保留证据边界，并形成上传准备清单。
- 阶段 1：核对本地分支、领先提交、tracked/untracked 状态，区分已提交证据、未提交归档文件、临时验证目录和大体量 runtime 目录。状态：complete。
- 阶段 2：整理三项目汇报文档，生成并排版 `docs/ChaosAtlas_three_project_experiment_report_2026-08-14.docx`，保留 UTF-8 Markdown 源稿。状态：complete。
- 阶段 3：更新归档地图和上传准备清单，新增 `.tmp-*` 忽略规则，禁止 `git add .`。状态：complete。
- 阶段 4：对最终提交集合执行敏感信息扫描和 focused regression。状态：complete（118 passed；严格敏感扫描 0 命中）。
- 阶段 5：选择性暂存必要文件、提交本次归档整理 commit；不推送，等待用户确认。状态：complete（当前 HEAD）。
- 阶段 6：等待用户确认后推送当前分支；推送前再次确认出境边界。状态：pending。
- 边界：不删除用户实验产物；不提交未筛选临时目录；不把 pending 审核写入知识库；不声称 Word PNG 视觉渲染已通过。

## Sock Shop YAML 置信停止两臂实验（2026-08-14）
- 目标：基于 1,935 个真实 YAML 的五大类统计与 Beta 置信停止规则，完成 Sock Shop `native-full` 与 `ChaosAtlas-ablation` 的独立候选生成、运行时验证和人工待审比较。
- 阶段 1：离线 YAML 分类、特征统计、置信停止、输入构建与 DeepSeek 发现。状态：complete（两臂各 25 个假设、19 个 runtime 候选、6 个显式 gate_failed）。
- 阶段 2：运行时批次。状态：complete（`runtime-exec-r2/r3` 保留原 failed 证据；`runtime-exec-r4` 形成 76/76 个 completed 报告）。
- 阶段 3：修复 Sock Shop session-db 与只读根文件系统不兼容的 Redis RDB 写入。状态：complete（准备器已覆盖该配置；当前 live Pod 已临时设置 `stop-writes-on-bgsave-error=no`，正式 cookie oracle 5/5 通过）。
- 阶段 4：续跑与恢复预算修订。状态：complete（r3 的 fail-fast 计划摘要只记录已处理的 10 个 ablation 候选；r4 使用冻结 discovery 输入和 completed-only 复用，补齐 18 个未执行槽位并重测失败单元；唯一协议改动为 recovery timeout 180 -> 240 秒）。
- 阶段 5：验收 76 个 runtime 报告、复核 mutation/diagnostic SHA-256、分析日志/events，生成 `human_review=pending` 的比较审核。状态：complete（所有生命周期、cleanup、washout 和 SHA-256 验收通过；全局 Chaos 资源为空）。
- 阶段 6：focused regression、敏感信息扫描、选择性暂存本次代码/测试/报告/必要证据并本地提交。状态：in_progress（focused regression 已通过；敏感扫描、diff 审核和选择性提交待执行）。
- 边界：仅操作 `chaosatlas-sock-shop`；不修复 Docker、Minikube 或 Chaos Mesh；不把 pending 审核写入知识库；不提交密钥或未筛选的大型 runtime 目录；默认不 push。

## 三项目两臂正式实验续跑（2026-08-14 当前会话）
- 目标：不重跑已完成单元，完成 OpenTelemetry Demo 剩余正式单元和新 Sock Shop 的 ChaosAtlas-full/ChaosAtlas-ablation 正式实验，并对 Online Boutique、OpenTelemetry Demo、Sock Shop 形成可复核结果与问题清单。
- 阶段 1：等待 OTel `runtime_results-r3` 串行批次自然完成，核验 48 个去重单元、生命周期、diagnostic/mutation SHA-256、pending human review 与全局无残留。状态：complete（48/48，验收 passed）。
- 阶段 2：仅在 OTel 完成且平台稳定后部署 `chaosatlas-sock-shop`，完成健康、双基线、cleanup rehearsal 和稳定 washout gate。状态：in_progress。
- 阶段 3：使用已授权 DeepSeek 出境范围生成新的 Sock Shop 两臂候选并执行静态/运行时适用性 gate。状态：pending。
- 阶段 4：串行执行 Sock Shop 48 单元正式批次；每轮确认恢复、删除 Chaos 资源并全局扫描。状态：pending。
- 阶段 5：验收三项目证据，区分已观测业务弱点与有直接证据支持的具体根因，保持 `human_review=pending`、`knowledge_base_updated=false`。状态：pending。
- 阶段 6：测试、敏感信息扫描、选择性暂存本次必要代码与正式证据、提交并推送当前分支。状态：pending。
- 禁止事项：不修复/安装 Docker、Minikube、Chaos Mesh；不重跑已完成 Online Boutique 或 OTel H3；不使用历史 Sock Shop 结果作为新实验正式证据；不自动更新知识库；不暴露 API key/token。
- 本轮错误：沙箱 PowerShell 未解析到 `python`，但现有本机实验终端可用；后续改用本机授权执行环境或显式解析已有 Python 路径，不安装新运行时。
- 本轮错误：新 Sock Shop deployment gate 首次组合测试因包式/脚本式导入差异失败两次；先补双模式导入，再按既有 runner 模式把 `tools/` 加入 `sys.path`，第三次 `13 passed`。未触发集群操作。
- 本轮错误：Sock Shop runtime gate 在注入前因双基线失败而 blocked；两个复杂 PowerShell 诊断命令分别因空管道和缺失花括号在解析阶段失败，均未触发 kubectl。改为拆分简单 JSON 输出与独立日志查询，禁止第三次拼接复杂循环。

## 三项目两臂正式实验续跑（2026-08-14）
- 目标：完成 Online Boutique、OpenTelemetry Demo、Sock Shop 上 ChaosAtlas-full 与 ChaosAtlas-ablation 的真实运行时实验，汇总可复核问题证据。
- 当前阶段：修复 Online Boutique 清理后业务恢复判定；从新目录重跑完整可比批次。
- 后续 gate：OTel 与 Sock Shop 先证明镜像/源码 provenance、严格 dry-run、双基线、rehearsal、清理和 washout，再允许模型调用与正式注入。
- 状态：in_progress。

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
| 2026-08-16 首次枚举规划文件的 PowerShell `foreach` 后直接接管道，触发 `EmptyPipeElement` 解析错误 | 改用 `Get-ChildItem | Where-Object` 的简单管道，未重复原失败命令；未修改任何文件或集群状态 |
| 2026-08-16 首次敏感信息扫描的 PowerShell 正则引号转义失败，命令在解析阶段退出 | 改用 `Select-String` 的模式数组逐项扫描；最终 0 命中，未执行任何写入或外部调用 |
| 2026-08-16 首次完整验证被 Git 的 LF/CRLF stderr 提示打断；第二次 `diff --check` 把 CR 误报为行尾空格 | 使用只影响本次只读校验的 `core.whitespace=cr-at-eol`，最终完整校验 11/11 通过；未改 Git 配置 |
| 2026-08-16 首次生成 18-family 明细时再次在 PowerShell `foreach` 后直接接管道，触发 `EmptyPipeElement` | 改为先收集 `$result` 数组再管道格式化，成功确认 18 个均为静态 gate 拒绝；未触发实验 |
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
# Open-discovery mutation compiler implementation (2026-08-11)

Status: complete

Goal: convert accepted ChaosAtlas open-discovery hypotheses into deterministic,
namespace-local Chaos Mesh YAML without allowing model output to execute shell
commands or bypass the existing runtime applicability gate.

Steps:

1. Inspect the topology IR, compiler contract, applicability gate, runner, and existing tests. (complete)
2. Add deterministic target resolution and YAML generation for PodChaos, NetworkChaos, and StressChaos. (complete)
3. Add fail-closed tests for valid mutations, configuration targets, empty selectors, namespace mismatch, unresolved targets, edge handling, and signature provenance. (complete)
4. Run focused tests and the full repository test suite; record residual runtime gates. (complete: 278 passed, 5 subtests passed)

Constraints:

- Do not read or use the DeepSeek key.
- Do not apply mutations to the kind cluster in this implementation turn.
- Do not touch Docker Desktop.
- The compiler emits files and provenance only; the existing gate and runner remain responsible for execution.

## Main experiment priority (2026-08-12)

- `in_progress`: 10-project open-discovery main experiment.
- `parked`: fixed candidate-pool three-arm control; do not invoke its runner.
- `complete`: offline main ledger, P02 dry-run compiler/mutation path, selector map, Kubernetes server-side dry-run, and deployment remediation queue.
- `blocked_pending_consent`: DeepSeek calls and real fault injection. The key has not been read and no request has been sent.
- GitHub source restoration (2026-08-12): complete for P09; P03/P06 commit/tree verified but full restoration blocked by partial-clone missing blobs and archive download timeout. Manifest: `artifacts/experiments/chaosatlas_10_projects/sources_restored/RESTORATION_MANIFEST.md`. No deployment or DeepSeek calls.

## Active method scope reset (2026-08-13)

- `in_progress`: run the complete ChaosAtlas method and the complete-method
  `noKB` ablation on the next eligible projects.
- `deferred`: all ChaosEater execution and unified comparison work. Existing
  ChaosEater artifacts remain frozen historical evidence only.
- `required`: enforce contamination gates before every method run: identical
  project inputs, separate method-owned outputs, no runtime feedback into the
  ablation, no same-project feedback into the complete method, residual-Chaos
  and cleanup checks, washout, and independent oracle evaluation.
- `blocked_pending_consent`: model calls and real fault injection remain
  separately gated; no credentials or requests are authorized by this scope
  change.

## Project summary and archive (2026-08-13)

- [complete] Verify the current Sock Shop two-arm reports and ChaosEater block.
- [complete] Create the dated project summary and machine-readable archive index.
- [complete] Record the active method boundary and next four-project queue:
  Online Boutique, OpenTelemetry Demo, Train Ticket, and TeaStore.
- [complete] Create a separate two-method follow-up queue manifest with fresh-output
  and contamination boundaries.
- [complete] Run archive consistency, JSON, link, sensitive-information, and
  repository regression checks.
- [complete] Correct P03/P06 archive status and make source completeness include
  required application files.
- [complete] Begin offline preparation for the four-project queue with
  Online Boutique, OpenTelemetry Demo, and Train Ticket fresh profiles.
- [complete] Verify the Online Boutique `r3` digest-pinned manifest and record
  its namespace-first dry-run as the next authorized runtime gate.
- [complete] Keep OpenTelemetry Demo blocked on immutable image provenance,
  Train Ticket blocked on missing dependency definitions plus immutable image
  provenance, and TeaStore blocked on missing source restoration.
- [pending] Obtain explicit `chaosatlas-online-boutique` authorization before
  namespace-first dry-run, baseline windows, and the two active method runs.

## Regression boundary (2026-08-13)

- [complete] Update the two P03 tests to match the current fail-closed
  `application_service_missing` and preparation-gate contract.
- [pending] Historical knowledge-ablation hash drift remains outside this archive
  change: the generic-rules and ESHOP mutation files are not tracked in the
  current branch history and must not be overwritten by this task.
- [pending] Default pytest temp-root access remains blocked by Windows ACLs;
  use a repository-local `--basetemp` for verification.

## Archive verification result (2026-08-13)

- Focused archive/gate regression: 18 passed.
- Contamination audit: 120 bundles and 30 KB/noKB pairs valid.
- JSON/archive/queue parse and status consistency checks passed.
- Full repository regression: 397 passed, 2 failed.
- The two failures are pre-existing pinned-hash drift in historical knowledge
  ablation artifacts; those files remain untouched and are excluded from this
  archive repair.

## Repository handoff (2026-08-12)

- `complete`: classify the current ChaosAtlas implementation, protocols, tests, and experiment evidence for commit.
- `complete`: exclude local Docker state, kubeconfig, proxy bridge files, planning sessions, environment files, and full upstream source snapshots.
- `complete`: scan the exact candidate set for credential values and sensitive filenames; no candidate secret was found.
- `complete`: run the complete tool test suite with an isolated basetemp (`290 passed`, `5 subtests passed`) and the offline ablation/profile validators.
- `complete`: stage and inspect the curated repository snapshot.
- `in_progress`: commit and push `remediation/2026-08-09-review`.
# P02 teacher-minikube formal runtime batch (2026-08-12)

- Goal: harden the one-mutation runner and add a fail-closed orchestrator for the teacher Minikube environment.
- [complete] Add cluster identity, arm/mutation/replicate metadata, global residual-Chaos preflight, and stable recovery checks.
- [complete] Add a 15-run formal batch plan (5 method outputs x 3 replicates), per-run read-only gate, no-overwrite output handling, and stop-on-failure behavior.
- [complete] Add focused unit tests and run the full regression suite.
- [complete] Commit and push only the intended code/tests/docs; preserve the existing timestamp-only manifest change.
- Runtime boundary: this workstation will not mutate the teacher cluster; teacher-generated reports use a new `teacher-minikube-formal` path.
- LLM boundary: no DeepSeek credential access or API call is needed for this work.

# P02 teacher result analysis (2026-08-13)

- Goal: validate the 15 teacher-Minukube reports and produce reproducible arm/mutation statistics plus a bounded issue ledger.
- [complete] Audit report completeness, identities, gates, cleanup, warnings, request outcomes, and target equivalence.
- [complete] Add a deterministic offline summarizer and focused tests.
- [complete] Generate JSON/Markdown summaries and distinguish project findings from method-comparison claims.
- [complete] Run regression tests, commit, and push without including the pre-existing manifest timestamp change.
- Interpretation boundary: identical faults across arms are execution replications, not independent discovery advantages; `ChaosEater-adapter-open` is supplementary, not official ChaosEater.

# P02 R3 evidence completion and review (2026-08-13)

- Goal: run one clean P02 batch with sustained washout plus logs/traces/events, then build a human review pack before any knowledge feedback or next-project work.
- [complete] Capture per-run api-gateway/discovery/customers logs, namespace events, and Zipkin traces with hashes and explicit unavailable states.
- [complete] Extend the offline summary to consume washout/diagnostic evidence without cross-run attribution.
- [complete] Add focused tests and run the full suite (`309 passed`, `5 subtests passed`).
- [complete] Commit and push the teacher R3 runner (`727c9a5`).
- [pending] Execute R3 on teacher Minikube, ingest results, produce pending human-review cards, and obtain explicit review decisions.
- [pending] Only after review, project approved abstractions into the later-project KB and proceed to the next deployable project.

## Sock Shop YAML confidence native-vs-ablation pipeline (2026-08-14)
- Goal: build the offline Sock Shop pipeline that classifies the 1,935 real YAMLs into five big categories, generates confidence-stopped hypotheses for native-full vs ChaosAtlas-ablation, and prepares a static runtime plan without touching Kubernetes yet.
- [complete] Add the YAML five-category classifier and inventory/statistics writer.
- [complete] Add the Beta confidence stop engine with novelty tracking and coverage-aware stopping.
- [complete] Add the frozen-input builder separating native-full and ablation method boundaries.
- [complete] Add the offline discovery runner with fake-model and DeepSeek-ready entry points.
- [complete] Add the runtime planner that compiles namespace-local mutations and marks unsupported categories as gate_failed.
- [complete] Add the review summarizer that distinguishes stable weaknesses from unstable and no-impact candidates.
- [complete] Generate the first offline artifact directory `artifacts/experiments/chaosatlas_sockshop_yaml_confidence_2026-08-15-r1/`.
- [in_progress] Run focused regression over the new modules, scan for sensitive data, validate diffs, and decide whether to proceed to authorized DeepSeek-backed discovery/runtime.
- Boundary: do not touch Sock Shop Kubernetes until the offline pipeline and verification finish; keep `human_review=pending` and `knowledge_base_updated=false`.

## ChaosAtlas Phase 0 project onboarding (2026-08-20)
- [complete] Freeze the versioned project profile schema, namespace isolation, Oracle, observability, recovery, cleanup and redaction requirements.
- [complete] Add the unified result contract and prevent response preservation/HTTP 200 from becoming an automatic defense claim.
- [complete] Integrate the contract into the runtime applicability gate, runtime classifier and knowledge-base validator.
- [complete] Add Sock Shop static profile and onboarding CLI; static readiness is reported separately from runtime readiness.
- [complete] Run focused regression, profile validation, Python compilation and diff hygiene checks.
- Boundary: no cluster access, no deployment, no live injection, no secret reads, and no automatic knowledge promotion.

## ChaosAtlas live RCA handoff (2026-08-21)
- [complete] Normalize live executor lifecycle attestations into baseline, injection, observation, recovery and cleanup evidence.
- [complete] Project live action results through the shared RCA state machine instead of hand-written `pending/none` output.
- [complete] Keep business-unreachable and injection-unconfirmed outcomes at `pending/none`; do not treat them as findings.
- [complete] Generate provisional knowledge drafts only when the live action is executed with valid attestation and bounded evidence.
- [complete] Generate a `discriminate` regression intent for provisional knowledge; no formal knowledge-base write occurs.
- [complete] Verify focused live/RCA regression (`68 passed`), compileall and diff hygiene.
- Boundary: mechanism evidence and a discriminating action are still required before `confirmed` RCA or reusable knowledge.

## ChaosAtlas bounded live batch (2026-08-22)
- [complete] Complete the Sock Shop HTTP Oracle with `service=front-end` and `remote_port=80`.
- [complete] Extend live scenario compilation across `pod_kill`, `container_kill`, `stress_cpu`, `stress_memory`, `network_loss` and `network_partition`.
- [complete] Add `run_live_batch` and `--max-candidates/--all-candidates`; each candidate gets an isolated output directory and independent RCA/knowledge artifacts.
- [complete] Fix live inventory Deployment lookup for Kubernetes `metadata.name` and nested selector/replica facts.
- [complete] Verify focused live batch regression (`63 passed`), compileall, diff hygiene, and real no-approval batch smoke.
- [complete] Preserve executor-declared mechanism evidence only after safe file collection; require `mechanism_evidence` and a discriminating action before RCA can become `confirmed`.
- Boundary: the batch is still limited to candidates covered by the configured business Oracle; explicit `--approve-live` remains required before any mutation.
# 2026-08-16 Sock Shop YAML15 Ablation closure

- [x] Freeze and audit five labeled YAML categories with three examples each.
- [x] Run independent DeepSeek discovery under the Full discovery time cap.
- [x] Deduplicate 458 hypotheses into 51 families and gate 46 runtime-ready families.
- [x] Fix the post-washout target readiness gap with a RED/GREEN regression test.
- [x] Complete 92 runtime report slots without rerunning 53 completed slots.
- [x] Verify lifecycle fields, mutation hashes, diagnostic hashes and empty Chaos residue.
- [x] Publish pending machine/Chinese review and replace the superseded Ablation headline.

## 2026-08-16 YAML15 review hardening

- [x] Reproduce and fix gate exclusion status, discovery hard-deadline, and DeepSeek retry-deadline findings with RED/GREEN tests.
- [x] Add `target_ready=false` regression coverage and preserve the 53 legacy / 39 current-schema evidence boundary.
- [x] Freeze the Full canonical 38-family batch with 76 report SHA-256 entries and combine it with the audited route-aware 50-family batch.
- [x] Correct protocol metadata, source hashes, sensitive-scan status, and Chinese review wording while keeping human review pending.
- [x] Verify affected tests, full-suite residual failures, cluster readiness, empty Chaos residue, JSON/SHA consistency, and Git diff hygiene.
- [complete] Selectively stage and commit only the YAML15 closure and necessary review fixes; push follows in the final repository handoff.

## ChaosAtlas Phase 5.2 live improvement closure (2026-08-23)
- [complete] Add the unified `chaosatlas improve` orchestration path for patch, fresh deployment, live retest, cleanup, evidence comparison and promotion.
- [complete] Validate the patched manifest with namespace-scoped server-side dry-run before live apply.
- [complete] Run two independent real Sock Shop front-end pod-kill after-runs on the `chaosatlas-improvement` profile.
- [complete] Promote only the verified deployment-boundary redundancy defense to `local_reusable` knowledge and compile regression intents.
- [complete] Remove the superseded `runtime-unknown` duplicate from the formal live-improvement knowledge directory while retaining historical run artifacts.
- [complete] Run focused regression and final static/lifecycle checks.

## ChaosAtlas Phase 6 productized live closed loop (2026-08-23)
- [complete] Add execution contract with explicit live approval, namespace allow-list, one-candidate budget and recovery deadline.
- [complete] Add content-addressed artifact index and phase6 audit for success, blocked and invalid exits.
- [complete] Preserve existing RCA/promotion boundaries; a single live run remains provisional and does not write formal knowledge.
- [complete] Verify Sock Shop, Online Boutique and P02 through one dry-run orchestrator path.
- [complete] Run one real isolated Sock Shop live canary through discovery, injection, observation, RCA, knowledge draft, regression intent and cleanup.
- [complete] Verify the isolated namespace is gone, global Chaos residue is zero and the original `minikube/sock-shop-lab` still has 14 Pods.

## ChaosAtlas Phase 7 DeepSeek advisory integration (2026-08-23)
- [complete] Add an explicit DeepSeek advisory provider with key-file/environment loading and no secret persistence.
- [complete] Keep the deterministic candidate set, gate, RCA, classification and knowledge promotion authoritative; advisory output is allow-listed and candidate-bounded.
- [complete] Add CLI provider selection and model/endpoint/key-file options while preserving deterministic fallback by default.
- [complete] Handle fenced/preamble JSON and length-truncated responses fail-closed; constrain output to at most 8 compact hypotheses.
- [complete] Verify one real Sock Shop dry-run with `deepseek-v4-flash`: advisory completed, no mutation, no formal knowledge write.
- [complete] Run Phase 7 focused suite (`41 passed`), compileall and diff hygiene checks.
- Boundary: DeepSeek is advisory-only; live execution and knowledge promotion remain deterministic, explicitly gated stages.

## ChaosAtlas Phase 8 Evidence action planner (2026-08-24)
- [complete] Add deterministic `tools/evidence_action_planner.py` with candidate/signature/recovery validation and read-only action allow-list.
- [complete] Convert advisory missing-evidence text into bounded action context without copying arbitrary model fields or executable commands.
- [complete] Write `evidence_plan.json` after hypotheses and before gate; include it in the existing artifact index and resume hash boundary.
- [complete] Require live Oracle candidate membership in the evidence plan before executor invocation; blocked plans return `environment_blocked` without executor calls.
- [complete] Preserve one-command CLI behavior, existing STAGES/RCA/classification/promotion contracts, and formal knowledge write boundaries.
- [complete] Verify actual Sock Shop dry-run and focused suite (`49 passed`), compileall, and diff hygiene.
- Boundary: evidence actions are planned and gated but not yet automatically replayed through the live Kubernetes evidence collector for every candidate.

## ChaosAtlas Phase 9 Planned evidence collection (2026-08-24)
- [complete] Add `tools/planned_evidence.py` to dispatch only validated read-only plan actions.
- [complete] Add namespace-safe Kubernetes collector methods for Deployment, Service, and Pod facts.
- [complete] Attach `planned_action_id` provenance to evidence records and `evidence_plan_ref` to `evidence_refs.json`.
- [complete] Preserve existing lifecycle, business Oracle, mechanism evidence, RCA, classification, cleanup, and promotion authority.
- [complete] Verify focused suite (`53 passed`), Sock Shop dry-run, compileall, and diff hygiene.
- Boundary: real-cluster evidence-plan smoke and automatic multi-candidate evidence iteration remain pending explicit runtime execution.

## ChaosAtlas Phase 10 Real read-only evidence smoke (2026-08-24)
- [complete] Run a real read-only planned evidence smoke against the available `chaos-testing` namespace.
- [complete] Verify Deployment, Service, Pod, Events, and Logs actions produce hashed evidence with plan provenance.
- [complete] Add field-level Kubernetes resource projection before sensitive scanning and persistence.
- [complete] Separate deployment target and Service target in candidate/plan/dispatcher contracts.
- [complete] Confirm no cluster mutation and no Chaos resource changes during smoke.
- [complete] Verify focused suite (`54 passed`), compileall, and diff hygiene.
- Boundary: Sock Shop business smoke requires an independently deployed allowed namespace; multi-candidate live iteration remains next.

### Phase 10 follow-up audit
- [complete] 使用独立输出 `artifacts/phase9-readonly-smoke-20260824/run-r2/` 重放只读采集，确认 `evidence_refs.json` 的 5/5 records 均有 `planned_action_id`。
- [complete] 计划中的 Service target `chaos-mesh-dns-server` 与实际 `kubectl get service` 命令一致；禁止操作命令为 0，`runtime_executed=false`、`model_called=false`、`formal_knowledge_written=false`。
- [complete] 当前工作区全量 `tools/tests` 为 `1206 passed, 1 warning, 5 subtests passed`；相关 Phase 9/10 suite 为 `56 passed`。
- Boundary: 本次 follow-up 仍只验证 `chaos-testing` 控制面资源，不改变 Sock Shop Shadow gate，也不构成业务 runtime 对照证据。

## ChaosAtlas Phase 10.1 Sock Shop read-only smoke on the correct Minikube context (2026-08-24)
- [complete] 识别本机多个 context/profile，确认 8G Sock Shop 位于 `minikube` context 的 `sock-shop-lab` namespace；不切换全局当前 context，所有命令显式带 `--context=minikube`。
- [complete] 真实只读 inventory 返回 14 Deployments、14 Services、14 Pods，生成 84 个候选并选择 `front-end` PodKill 证据计划。
- [complete] 生成 7 个计划动作并执行 Deployment、Service、Pod、Events、Logs 五类只读采集；5/5 records 均为 `supports` 且带 `planned_action_id`。
- [complete] 通过命令、敏感信息、context 前缀和 Chaos 资源残留审计；无 mutation、无模型调用、无正式知识写入。
- Boundary: 这仍是 evidence-plan smoke，不执行 PodKill；正式 runtime、RCA、Shadow 对照和 `guarded` 默认化仍需单独批准和生命周期实验。

## ChaosAtlas Phase 11 Guarded Sock Shop canary (2026-08-24)
- [complete] 在用户明确批准后，仅执行 `minikube/sock-shop-lab` 的单候选 `front-end` PodKill；预算为 1，未启动多候选批次。
- [complete] 修复并测试 Deployment-to-Service target 泄漏：候选从每个 deployment node 读取对应 Service，避免所有候选误用最后一个 Service。
- [complete] 使用工作区临时 kubeconfig 副本运行 live CLI，原 kubeconfig 未被改写；canary 输出为 `artifacts/phase10-guarded-canary-20260824-front-end-podkill-r2/`。
- [complete] lifecycle 验收：preflight ready、baseline 200、注入确认、观察期间短暂业务不可达后恢复、replacement Pod UID 变化、cleanup verified、全局 Chaos 残留 0。
- [complete] 结果保持边界：classification=`availability_degraded`；RCA=`confirmed` 但 weakness=`candidate`；knowledge=`provisional` 草稿和 1 个 regression intent；`knowledge_base_updated=false`、未写正式知识库。
- [complete] 直接相关 focused suite `26 passed`；compileall 和 diff check 通过。
- [complete] 修复 runtime gate 的空 `kube_context` 兼容调用、fail-closed 异常结果字段和 batch adapter 的 profile-aware inventory 兼容；全量 `tools/tests` 为 `1213 passed, 1 warning, 5 subtests passed`。
- [complete] 执行第二次独立 `front-end` PodKill canary，输出为 `artifacts/phase10-guarded-canary-20260824-front-end-podkill-r3/`；未复用 r2 runtime 结果，显式使用 `minikube` context。
- [complete] r2/r3 均完成 baseline、注入、短暂业务降级、replacement UID、恢复、cleanup；两次分类均为 `availability_degraded`，RCA=`confirmed`，weakness=`candidate`，knowledge=`provisional`。
- Boundary: 双重复支持该单候选的稳定受控观察，但仍不自动开启项目级 `guarded` 默认或写入正式知识库；正式晋级仍需显式 promotion policy/knowledge root 和更广泛候选验证。

## ChaosAtlas Phase 11 context-pinned live closure (2026-08-24)
- [complete] Add explicit `--kube-context` to the unified `chaosatlas run` entry point.
- [complete] Pin inventory, preflight, evidence, gate, mutation lifecycle, recovery polling and business port-forward to the selected context.
- [complete] Add regression coverage for context propagation and requested-context audit reporting.
- [complete] Execute one real `front-end pod_kill` against `minikube/sock-shop-lab` with explicit live approval.
- [complete] Verify `live_completed`, `availability_degraded`, RCA `confirmed`, provisional knowledge draft, regression intent and verified cleanup.
- [pending] Add explicit knowledge write/promotion-root handling to the one-command live path and verify a controlled formal knowledge update.
- [pending] Add multi-candidate information-gain iteration after the single-candidate contract remains stable.
- Boundary: `--kube-context minikube` is required for this machine because the process default is `chaosatlas-improvement`; no kubeconfig current-context mutation is performed.

## ChaosAtlas Phase 12 formal knowledge write and batch context (2026-08-24)
- [complete] Verify the unified dry-run path promotes two complete independent defense runs only with an explicit history root.
- [complete] Verify publication occurs only under an explicit knowledge write root and produces a reusable defense card plus regression intents.
- [complete] Forward `--kube-context` through batch planning and every isolated child `run_closed_loop`.
- [complete] Run a real no-approval batch smoke against `minikube/sock-shop-lab`; both children stop before mutation with context-pinned preflight evidence.
- [pending] Add information-gain policy state and typed multi-candidate stopping to the batch path; keep legacy deterministic ranking as rollback.
- Boundary: formal promotion is available but still requires prevalidated repeated history; a single provisional live run cannot directly become reusable knowledge.

## ChaosAtlas Phase 13 information-value replay closure (2026-08-24)
- [complete] Confirm existing deterministic policy primitives and rollout modes remain green (`35 passed` focused policy suite).
- [complete] Add `tools/evaluate_experiment_value_policy.py` for offline replay of legacy runtime order against policy recommendations, deterministic state updates, input hashes and stop records.
- [complete] Add list/object JSON input compatibility and regression tests; replay evaluator has no cluster, model or mutation side effects.
- [complete] Generate `artifacts/policy-rollout/online-boutique-r4-shadow-20260823/information-value-replay.json` from the frozen denominator; it correctly records `recorded_result_count=0`, `stop_reason=replay_exhausted`, and no runtime evidence.
- [complete] Obtain a frozen Sock Shop runtime-result set from two independent deterministic classifications and run the replay comparison; the report records 84 candidates, two results, zero decision changes and deterministic replay hashes.
- [complete] Run one policy-selected guarded canary with the replay-selected `front-end/pod_kill` candidate under explicit `minikube` context, one-candidate budget and operator approval; lifecycle and cleanup gates passed.
- [complete] Add policy mode wiring to the live batch path; second-project runtime evidence and default rollout remain intentionally pending.
- Boundary: the旁路候选 method now has runtime-backed shadow and one guarded canary acceptance for the Sock Shop candidate, but this is not a project-wide superiority claim, default rollout, or formal knowledge promotion.

## ChaosAtlas Phase 14 policy-selected guarded canary (2026-08-24)
- [complete] Make replay CLI accept nested stage envelopes and a read-only policy context; preserve legacy metadata compatibility and add `next_candidate_id` to the stop record.
- [complete] Freeze `artifacts/policy-rollout/sock-shop-front-end-r2-r3-denominator.json` from the 84-candidate Sock Shop static space and replay the two real r2/r3 runtime classifications.
- [complete] Verify policy version `ig-stop-v1`, both replay decisions select `server:deployment:827339c6afd397a13efb276a:pod_kill`, `decision_changed=0`, and primary/repeat replay SHA-256 equality.
- [complete] Execute `artifacts/phase14-policy-selected-guarded-canary-20260824-front-end-podkill-r1/` with explicit `minikube` context; preflight, gate, injection, observation, recovery, cleanup and residual scan passed.
- [complete] Write `policy_selected_canary.json` binding replay/denominator/context hashes to the live execution contract; `candidate_in_frozen_denominator=true` and `contract_matches_policy_selection=true`.
- [complete] Run the full verification suite (`1228 passed, 1 warning, 5 subtests passed`), compileall, diff check and runtime artifact assertions; send the required completion notification; default mode remains disabled and formal knowledge remains untouched.

## ChaosAtlas Phase 15 policy selection gate integration readiness (2026-08-24)
- [complete] Integrate `policy_selection_gate` into live batch orchestration while preserving `legacy` as the default; persist policy state, selection, and manifest input hashes.
- [complete] Add `--policy-mode`, `--policy-state`, `--policy-context`, and `--policy-budget` to the unified CLI; non-legacy policy is restricted to batch entry points and single-candidate use fails closed.
- [complete] Keep mode boundaries explicit: `shadow` records policy choices without changing execution; `guarded/default` execute only frozen-denominator policy choices; invalid state or policy errors fall back to the bounded legacy prefix.
- [complete] Pass focused acceptance (`52 passed`) and full `tools/tests` (`1235 passed, 1 warning, 5 subtests passed`).
- [complete] Pass compileall, diff hygiene, and offline smoke checks for shadow, guarded, and fallback paths.
- [complete] No Kubernetes mutation, model call, or formal knowledge write was performed; the project is at the pre-experiment integration acceptance point.
- Boundary: default remains `legacy`; before the formal experiment, run a runtime-backed shadow comparison on a second project and only then enable guarded multi-candidate execution under explicit approval.

## ChaosAtlas Phase 16 Online Boutique offline Shadow replay (2026-08-24)
- [complete] Add the deterministic `project_runtime_projection` bridge with lifecycle, project, candidate, replicate, and classification fail-closed checks.
- [complete] Freeze the 55-candidate Online Boutique same-pool input and project four candidates from eight complete historical reports; preserve source paths and raw report SHA-256 values.
- [complete] Run the existing policy replay twice with the actual candidate-file snapshot hash; both reports have identical input hash, decisions, and full-file SHA-256.
- [complete] Verify four non-empty runtime feedback records and four policy/legacy decision changes; replay metadata confirms no cluster access, model call, mutation, or formal knowledge write.
- [complete] Run projection tests (`4 passed`) and artifact assertions (`9/9` checks passed).
- Boundary: this is an offline historical Shadow comparison, not a new runtime experiment and not proof of cross-project superiority; guarded live rollout remains disabled.

## ChaosAtlas Phase 19 Guarded container-kill contract (2026-08-24)
- [complete] 核对 Guarded r1 证据，确认容器在同一 Pod 内重启并恢复，旧 `replacement_identity_required=true` 是契约不匹配而非真实恢复失败。
- [complete] 新增 fault-specific recovery contract：`pod_kill` 继续要求 replacement Pod UID，`container_kill` 改为 `container_restart`，要求目标容器 restartCount 增长、Pod Ready 稳定和业务 Oracle 恢复。
- [complete] 接入 live/offline adapter、manifest capability pool、evidence planner、统一 lifecycle executor 和通用 Chaos runner；机制证据按 recovery mode 描述。
- [complete] TDD 与回归：契约/恢复/证据/adapter/lifecycle focused suites 全部通过，先 RED 后 GREEN。
- [complete] 执行新的单候选 Guarded r2，输出 `artifacts/phase17-online-boutique-guarded-live-20260824-r2/`；policy 仍从 Legacy `pod_kill` 切换到 `container_kill`，实际执行与 selection 一致。
- [complete] r2 通过 baseline、injection、container restart recovery、业务观察、cleanup 和 residual 检查；attestation `valid=true`、`comparison_eligible=true`，正式知识库未更新，knowledge 保持 `provisional`。
- Boundary: r2 证明的是容器重启恢复契约和单候选服务边界观察，不增加项目级发现率结论，不将 provisional case 晋级为正式知识。

## ChaosAtlas Phase 20 P02 productized runtime closure (2026-08-24)
- [complete] Restore the parked `minikube/chaosatlas-p02` namespace to its recorded one-replica runtime shape.
- [complete] Verify all P02 Deployments/Pods Ready and validate the warm-up-aware `/api/gateway/owners/1` business baseline.
- [complete] Run namespace-pinned read-only inventory, server deployment detection and planned evidence collection.
- [complete] Execute bounded live `api-gateway/pod_kill` runs through the unified closed-loop path, with RCA, recovery and cleanup evidence.
- [complete] Repeat the same candidate with an independent seed and promote only the two complete runs (`r1` and `r4`) to a P02-local reusable weakness card.
- [complete] Harden the executor boundary: preserve errors/action identity, scope live event evidence to the current mutation, and retry transient baseline HTTP protocol failures.
- Boundary: P02 historical prior-validation evidence is retained but is not reused as a new runtime replicate. `r2` was rejected because its event artifact contained stale `r1` events and no lifecycle attestation; `r3` was rejected because baseline failed on a transient `BadStatusLine` before injection. No cross-project transfer is implied.

## Phase 20 follow-up: P02 offline identity and knowledge replay (2026-08-24)
- [complete] Reproduce the offline P02 fixture failure and keep strict profile/facts identity validation.
- [complete] Separate lowercase synthetic `p02` facts from the uppercase formal `P02` profile with an explicit runtime facts variant; do not weaken identity checks for case-insensitive Windows paths.
- [complete] Add regression coverage for the formal P02 profile and the three-project offline orchestrator path.
- [complete] Verify full `tools/tests`: `1261 passed, 5 subtests passed`; compileall passed.
- [complete] Stabilize completed ablation checkpoint resume by returning the exact payload written to the checkpoint; final full suite is `1262 passed, 5 subtests passed`.
- [complete] Run paired P02 dry-runs with the same formal profile and seed: no-knowledge and P02 knowledge root both `dry_run_ready`; retrieval changed from 0 cards to `KB-WEAK-172535b133dde433` and the first candidate changed from `admin-server/container_kill` to `api-gateway/pod_kill`.
- Boundary: the replay validates knowledge-directed prioritization only; both runs remain `static/synthetic`, no mutation, no model call, no formal knowledge write, and no new runtime weakness claim.

## ChaosAtlas Phase 21 OTel Demo preflight (2026-08-24)
- [complete] Run a read-only `minikube/chaosatlas-otel` status check; namespace is Active and all 11 Deployments/Pods are Ready/Running.
- [complete] Run the unified live batch without approval; inventory, server deployment detection, candidate planning and runtime preflight completed for one bounded candidate.
- [complete] Verify gRPC PlaceOrder Oracle is configured, preflight is `ready_for_injection`, and all Chaos residual resource classes are clean.
- [complete] Execute one explicitly approved OTel Demo `checkout/pod_kill` Shadow candidate through the unified live path.
- [complete] Verify gRPC baseline, transient business unreachability, recovery, RCA, cleanup, replacement Pod readiness and independent residual scan.
- [complete] Preserve the result as `availability_degraded`, RCA `confirmed`, knowledge `provisional`, and formal knowledge unchanged.
- Boundary: one runtime replicate is not enough for reusable knowledge; a distinct second replicate remains approval-gated before promotion.

## ChaosAtlas Phase 22 OTel Demo deterministic feedback reflow (2026-08-24)
- [complete] Aggregate r2/r3 complete runtime attestations into `artifacts/opentelemetry-demo/chaosatlas-guarded-feedback-20260824/feedback-input.json` with `valid_reproductions=2`.
- [complete] Ingest the aggregate through `experiment_policy_feedback`; `container_kill` becomes project-local `weakness` with normalized `confirmed_weakness` evidence.
- [complete] Retain r1 `response_observed/bounded` as non-confirming audit evidence; no formal knowledge write, denominator change, policy-mode change, or mutation occurred.
- [complete] Run offline guarded selection replay; candidate value drops from `3.58496` to `2.24758`, next candidate moves to `network_loss`, and stop remains open for unresolved candidates.
- [complete] Validate policy state, focused tests (`15 passed` with plugin autoload disabled), compileall, diff check, explicit `minikube/chaosatlas-otel` health, zero Chaos resources, and no guarded runtime temp directory.
- Boundary: this is project-local policy feedback, not formal knowledge promotion or a default switch to guarded.

## ChaosAtlas Phase 23 OTel Demo network-loss guarded preflight (2026-08-24)
- [complete] Run a new guarded batch with the feedback-updated policy state and one-candidate budget, without live approval.
- [complete] Confirm policy selected `server:deployment:e6b73b454a44174b26e2ceb6:network_loss` inside the frozen candidate denominator; no fallback was used.
- [complete] Confirm explicit `minikube/chaosatlas-otel` preflight is `ready_for_injection`: 11 Deployments/Pods ready, gRPC Oracle configured, and all Chaos residual classes clean.
- [complete] Confirm the approval gate stopped before mutation: `injection_performed=false`, batch status `environment_blocked` only because `approve-live` was absent.
- Boundary: live `network_loss` execution is still approval-gated; no runtime weakness or RCA claim is made from this preflight.

## ChaosAtlas Phase 24 OTel Demo network-loss execution gate (2026-08-24)
- [complete] Use the approved guarded command with one-candidate budget and updated policy state.
- [complete] Diagnose the first blocked attempt: NetworkChaos compiler omitted `spec.mode`; no mutation occurred.
- [complete] Add a regression assertion and fix all live StressChaos/NetworkChaos branches to emit `mode: one`; focused gate/compiler suite passes (`26 passed`, `5 subtests passed`).
- [complete] Retry after the fix; preflight became `ready_for_injection`, but baseline stopped before mutation because `.venv` lacks `google.protobuf`.
- [complete] Confirm both attempts left the cluster clean and all 11 OTel workloads Ready; no runtime result was accepted and no knowledge write occurred.
- Boundary: the canary remains pending local installation of `grpcio` and compatible `protobuf`; do not bypass the business baseline or infer a network-loss finding.

## ChaosAtlas Phase 25 OTel Demo dependency unblock attempt (2026-08-24)
- [complete] Retry the approved local `.venv` installation of `grpcio` and compatible `protobuf`.
- [complete] Installation was rejected again by the external approval service after the allowed retry window; no package or cluster state was changed.
- [complete] Check for offline wheels and alternative `grpcurl`/`protoc` executables; none are available.
- Boundary: the approved `network_loss` canary is blocked on external dependency installation; do not bypass the gRPC business baseline.

## ChaosAtlas Phase 26 OTel Demo dependency permission check (2026-08-25)
- [complete] Recheck the project `.venv` after the user requested another inspection.
- [complete] Confirm `grpcio`/`protobuf` package directories and dist-info exist, but are unreadable to the current user; normal imports still fail.
- [complete] Confirm no `grpcurl`/`protoc` alternative and no active Chaos resources; all 11 OTel Pods remain Running.
- Boundary: runtime execution is blocked by local package-directory permissions and failed elevated read approval, not by candidate policy or Kubernetes readiness.

## ChaosAtlas Phase 27 OTel Demo network-loss canary recovery (2026-08-25)
- [complete] Use the project-local `.venv-otel-runtime` fallback because the existing `.venv` dependency directories remain ACL-blocked; verify `google.protobuf` and `grpc` imports.
- [complete] Run a fresh read-only preflight on `minikube/chaosatlas-otel`: 11/11 workloads Ready, gRPC Oracle configured, and all Chaos residual classes clean.
- [complete] Execute the explicitly approved guarded single-candidate `network_loss` canary with `max_candidates=1`.
- [complete] Verify baseline 10/10, confirmed Chaos Mesh Apply/Recover for one target, transient business degradation followed by recovery, cleanup verified, and zero residual Chaos resources.
- [complete] Preserve the result as one independent `availability_degraded` replicate with RCA `confirmed` and knowledge `provisional`; policy feedback and formal knowledge promotion remain closed until a distinct second replicate.
- [complete] After explicit administrator authorization, grant the actual Codex sandbox user access to the four gRPC/protobuf targets plus the observed `typing_extensions` dependency, without deleting or rebuilding `.venv`.
- [complete] Re-verify the original `.venv`: protobuf/grpc imports and package metadata work for the active user.
- Boundary: the operational fallback remains valid evidence for this canary, while future runs may use the repaired original `.venv`.

## ChaosAtlas Phase 23 OTel Demo weakness promotion (2026-08-24)
- [complete] Exclude r6 because the pre-fix batch path did not propagate its requested seed and reused the r5 run identity.
- [complete] Select only independent r5 (`seed=1001`) and r7 (`seed=1002`) complete runs into an explicit weakness history root.
- [complete] Run `weakness_promotion_stage.py` with lifecycle, RCA, evidence-reference, project-identity, causal-identity, cleanup and distinct-artifact gates.
- [complete] Promote `KB-WEAK-fd0bcc9a763e4bdf` to `local_reusable` with two valid reproductions and generate `reproduce`/`guard` regression intents.
- [complete] Write the card only to the isolated OTel runtime knowledge root; existing OTel cards were not overwritten.
- [complete] Replay dry-run with and without the new root: retrieval changed from 0 to 1 card and loaded the new card; both runs remained synthetic `dry_run_ready` with no mutation or formal write.
- [complete] Full `tools/tests` passed (`1263 passed`); compileall and diff hygiene are final checks.
- Boundary: the card is limited to the OTel Demo checkout deployment/service boundary at the recorded commit; it does not claim source-level root cause, timeout semantics, cross-project reuse or automatic guarded rollout.

## ChaosAtlas Phase 24 Sock Shop third-project runtime closure (2026-08-24)
- [complete] Pin the live run to `minikube/sock-shop-lab` and verify 14/14 workloads, the front-end HTTP Oracle and zero Chaos residuals before mutation.
- [complete] Execute one bounded `front-end/pod_kill` Shadow run with seed `3001`; verify availability degradation, confirmed RCA, recovery, cleanup and full lifecycle attestation.
- [complete] Execute an independent second run with seed `3002`; verify a distinct run identity, the same bounded runtime classification, recovery and cleanup.
- [complete] Exclude the no-approval preflight artifact from runtime evidence because it stopped at the explicit approval gate before mutation.
- [complete] Promote the two valid runs to `KB-WEAK-452bd9a809fa41f2` (`local_reusable`) and generate `reproduce`/`guard` regression intents.
- [complete] Replay dry-run with and without the Sock Shop card: retrieval changed from 0 to 1 card; both runs stayed synthetic `dry_run_ready` with RCA `not_run` and no mutation.
- Boundary: this validates a Sock Shop front-end deployment/service boundary at the recorded runtime commit; it does not establish cross-project transfer, source-level root cause or default guarded rollout.
-
## ChaosAtlas Phase 26 Knowledge consumption contract (2026-08-24)
- [complete] Emit `knowledge_consumption.json` from the unified run with accepted and rejected card IDs, project/commit identity and rejection reasons.
- [complete] Keep foreign-project and foreign-commit cards out of candidate ranking; retain them as `cross_project_pending` audit entries.
- [complete] Add flat weakness-card validation and four-project migration audit.
- [complete] Run focused contract/orchestrator tests (`47 passed`), full `tools/tests` (`1268 passed`), compileall, diff hygiene and four-project flat-card validation.
- Boundary: this phase is read-only knowledge consumption auditing; it does not promote cross-project cards, execute mutation or enable guarded by default.

## ChaosAtlas Phase 27 Structured improvement retest acceptance (2026-08-24)
- [complete] Reuse the existing isolated Sock Shop `chaosatlas-improvement` fresh-namespace runs; the verified after-run changed the same `front-end/pod_kill` scenario from `availability_degraded` to `availability_defended`.
- [complete] Verify same scenario/oracle/recovery/cleanup contract, server-side dry-run, live apply, recovery and cleanup evidence; `improvement_evidence.json` is `improvement_verified` and validation is true.
- [complete] Confirm the resulting defense card is deployment-boundary redundancy only, with two independent evidence runs and no source-level timeout/retry claim.
- Boundary: no new live mutation was required in this phase; historical artifacts are immutable evidence and the original default policy remains unchanged.

## ChaosAtlas Phase 28 Final multi-project one-command acceptance (2026-08-24)
- [complete] Validate four project-local weakness roots: Sock Shop, Online Boutique, P02 and OpenTelemetry Demo; each has a matching project commit and `local_reusable` card.
- [complete] Validate three independent dry-run records remain `dry_run_ready`, `finding=not_run` and `rca=not_run`.
- [complete] Generate `.tmp-phase28-final-acceptance-r1/final_acceptance.json` with status `passed`, four accepted projects, one verified improvement record and no Kubernetes/LLM/formal-write side effects.
- [complete] Make the explicit policy decision `retain_legacy`; `guarded/default` is not enabled automatically.
- Boundary: ChaosAtlas now has an accepted controlled closed-loop product path; broad autonomous live scanning and automatic guarded rollout remain explicit future policy decisions.

## ChaosAtlas Phase 29 OTel Demo network-loss dual-replicate feedback (2026-08-25)
- [complete] Re-run the read-only preflight with the repaired original `.venv` and `seed=1002`: 11/11 workloads ready, gRPC Oracle configured, and all Chaos residual classes clean.
- [complete] Execute the second explicitly approved guarded single-candidate `network_loss` replicate; obtain a distinct run identity `live-aa28cef942de`.
- [complete] Verify the second lifecycle: baseline, confirmed injection/recovery, transient `availability_degraded`, RCA `confirmed`, cleanup `verified`, and no residual Chaos resources.
- [complete] Aggregate the two independent complete runs with source hashes and attestation into `artifacts/opentelemetry-demo/chaosatlas-guarded-feedback-20260825-network-loss/`.
- [complete] Ingest through `experiment_policy_feedback`; only the project-local policy state changes `network_loss` to `weakness`, while formal knowledge and default policy remain unchanged.
- [complete] Generate an offline selection replay showing the next candidate moves to `network_partition` and the stop condition remains open.
- Boundary: this is a project-local two-replicate policy result; it does not establish a source-level RCA, cross-project rule, formal KB promotion or automatic guarded default.

## ChaosAtlas Phase 30 NGINX Kubernetes Ingress deployment preparation (2026-08-25)
- [complete] Define the deployment-only boundary for `nginx/kubernetes-ingress`; no fault injection, knowledge promotion or upstream claim is in scope.
- [complete] Reuse the existing ChaosAtlas namespace allow-list, read-only preflight, server-side dry-run, evidence collector and project-profile contracts.
- [complete] Write the staged deployment plan and progress table in `docs/superpowers/plans/2026-08-25-nginx-kubernetes-ingress-deployment.md`.
- [pending] Run read-only cluster preflight and record existing ingress-controller, IngressClass, CRD, exposure and residual state.
- [pending] Freeze the controller release, chart, values, image digests, rendered manifests and SHA-256 provenance bundle.
- [pending] Obtain explicit live approval, then deploy only into an isolated namespace and verify controller readiness.
- [pending] Deploy a namespace-local fixture backend, verify one deterministic ingress route, and complete two failure-free baseline windows.
- [pending] Create and validate the NGINX Ingress project profile; keep future fault families marked `pending` until the method is frozen.
- Boundary: deployment readiness is not a chaos result; no mutation experiment may start from this plan without a separate approval and passed preflight.

# 2026-08-25 Legacy/Shadow/Guarded cross-project comparison

- 目标：在 Sock Shop 与 Online Boutique 各执行最多 5 轮 legacy、shadow、guarded，比较候选质量、停止效率、RCA 准确性和 cleanup 安全性；不做独立候选池排序对比。
- Sock Shop：三模式均完成 5/5，2 个 confirmed finding、2 个 RCA confirmed、cleanup 全部 verified；无退化证据。
- Online Boutique：legacy/shadow 完成 5/5 且 cleanup 全 verified；guarded 首轮含 2 个 preflight blocked，guarded-r2 暴露 network_loss cleanup attestation 缺失，当前结论不能通过。
- 当前阶段：root-cause investigation。证据指向 `delete_resource` 删除后单次立即验证的异步删除竞态；先添加失败回归测试，再修复并重新运行 guarded。
- 通过门槛：两个项目三模式的有效运行均不得出现 cleanup 未验证；environment_blocked 不得计为弱点；RCA 只能在完整 attestation 下计入。

- [complete] 修复 `delete_resource` 删除后异步传播造成的单次验证竞态；新增回归测试并通过相关执行器/编排器测试。
- [complete] Online Boutique guarded-r3/r4 在修复后完成有效轮次补足；r4 为 5/5 completed、0 blocked、0 cleanup failure，停止原因为 `budget_exhausted`。
- [complete] 与 Sock Shop 三模式结果合并复核：候选质量、停止效率、RCA 确认和 cleanup 安全均未出现 post-fix 退化；r2 的 cleanup block 保留为已修复历史证据。
- [complete] 生成对比报告 `reporting/policy_rollout_comparison_2026-08-25.md`。
# 当前新增阶段：项目全量画像与假设注册表（2026-08-25）

- [complete] 设计并实现 `project_portrait.json` 与 `hypothesis_registry.json` 的 advisory 契约。
- [complete] 用 TDD 覆盖五类假设、证据前置条件、稳定排序和去重。
- [complete] 将两个 artifact 接入离线闭环，不改变现有 live 注入和 policy 安全门。
- [complete] 完成 focused tests、compileall、fresh dry-run，并记录“候选总量”和“执行预算”分离。

边界：本阶段不扩大真实 live 批次，不把画像或假设注册表内容直接判定为漏洞、RCA 或正式知识；DeepSeek advisory 仍是可选增强，不作为确定性裁决。

验证：注册表与闭环回归 `60 passed`；`compileall` 通过；fresh dry-run `dry_run_ready`，生成 23 条假设（12 条 runtime、11 条静态/防御），预算仍为 1，正式知识目录未写入。

下一阶段：先在离线回放中评估注册表覆盖和假设质量，再设计 registry-to-policy 的只读 shadow 接口；在质量门通过前，不允许静态假设进入 live mutation。

# 当前阶段：Registry Shadow 质量评估（2026-08-25）

- [complete] 新增纯函数质量评估器和 registry shadow 排序报告。
- [complete] 接入 `chaosatlas run --registry-shadow`，默认路径保持不变。
- [complete] Sock Shop 与 Online Boutique fresh dry-run 均通过，报告稳定且无副作用。

验证：相关测试 `61 passed`；两项目质量状态均为 `passed`；重复运行的输入 hash、候选选择和副作用标志一致；未执行 live mutation、未更新 policy state、未写入正式知识库。

边界：registry shadow 目前是策略接入前的验收层，仍不驱动 guarded/live 选择；下一阶段才评估是否把 registry runtime 优先级接入 policy 的 shadow/guarded 流程。

# 当前阶段：Registry Policy Signal 接入（2026-08-26）

- [complete] 新增 registry runtime priority signal，固定 bonus 上限并排除静态假设。
- [complete] 接入现有 policy scoring、PolicyController 和 live batch 的 shadow/guarded context。
- [complete] 写入 `registry-policy-input.json` 与 `registry-policy-decisions.jsonl`，legacy 默认路径保持不变。
- [complete] 完成 82 个相关测试、fixture 级 Sock Shop/Online Boutique 离线检查和 compileall。

边界：registry signal 只影响通过质量门的 runtime candidate 排序；真实 guarded canary 仍需显式批准，guarded 仍不是默认模式。

# 当前阶段：方法身份、覆盖统计与执行器边界固化（2026-08-26）

- [complete] 新增 `problem_identity.py`，区分 `weakness_id`、`causal_cluster_id` 与跨故障方法的 `issue_id`，并要求完整 runtime lifecycle 才能计入有效问题。
- [complete] 新增只读 `coverage_report.py`，按项目、故障族、独立弱点和独立问题统计现有 RCA artifacts；平台阻断、证据不完整和无项目归属历史 artifact 不进入确认问题统计。
- [complete] 新增 `fault_executor_registry.py`，为 6 个 ready 方法和 4 个 pending 方法提供显式 executor/evidence 状态；NGINX candidate catalog 校验执行器状态一致性。
- [complete] TDD focused tests、当前 `artifacts/` 覆盖报告和 compile 检查已完成。
- [pending] 将 coverage report 接入主批次汇总，并在第二轮项目扩展前冻结跨项目验收阈值。
- [pending] 为 `network_delay`、`backend_pod_kill`、`config_reload`、`replica_reduction` 分别实现真实 executor、恢复与证据契约，再进行 live canary。

## 当前阶段：仓库结构整理与 GitHub 发布准备（2026-08-26）

- [complete] 盘点当前仓库并按主线源代码、实验输入、生成证据、外部源码、本机状态和审阅文档分类。
- [complete] 写入 `docs/REPOSITORY_MAP.md` 和 `docs/REPOSITORY_CLEANUP_POLICY.md`，冻结不删除、不移动原始证据的边界。
- [complete] 新增只读 `tools/repository_inventory.py` 及回归测试，当前 inventory 零未分类。
- [complete] 补充本机临时目录、通知队列、虚拟环境和 inventory 输出的 `.gitignore` 规则。
- [in_progress] 运行全量验证并审查选择性暂存清单。
- [pending] 创建本地整理提交并尝试推送当前分支；凭据失败时保留本地提交并报告阻塞。
