# H2 重放器补强进度（非完成报告）

承接 `2026-09-06-p3-replay-hardening-handoff-zh-CN.md`。沿用 1C / 2A / 3A。
H1 已完成；H2 仍在实施，H3 最终契约尚未形成，不应请求真实事务审批。

## 当前实现及测试

- H1 三项红测试修复后转绿：二次响应丢失不得宣称清理成功、普通 fixture 不得覆盖运行身份、非法 JSON path 拒绝。
- v2 真实 HTTP 入口已关闭。历史 v1/v2 文件未修改、未增加实际批准记录。
- v3 校验器加入变量先后依赖、输入/超时边界、唯一 ID、阶段观察约束，以及嵌套所有权、分页完整性、清理关联校验。
- 外置逐写操作账本使用原子写入和操作锁。独立 Python 进程已验证读取未决状态和并发锁拒绝；这不是独立进程真实应用恢复验收。
- 目标绑定核对集群/namespace/Service UID、Service spec、租约 revision、应用镜像摘要；只允许重启时改变已核验的本地转发端口。
- Secret 解析只读取精确 namespace/name/UID/key，并限制认证 header。测试仅使用合成 Secret；没有读取实际应用凭据或创建应用账号。
- 公共 TransactionReplayer 按版本进入 v3 会话解释器。其合成测试覆盖新鲜 probe、查回清理、响应丢失、日志失败、写前持久化失败、重复 cleanup、对象替换和实际剩余 deadline。
- 审批工具改为 `--manifest` 精确路径/文件哈希/语义哈希清单。全量验证后通过目录重命名发布整批冻结件；程序记录时间与显式用户决定时间分开。中断落盘不会发布半批；暂存文件留在外置根供诊断。

全量实跑：**448 passed**。原始 JUnit：
`%LOCALAPPDATA%/ChaosAtlas/runs/h2-replay-core-20260906/full-tests-v3-session.xml`。

综合验收：编译、12 项架构检查、两个 dry-run、产品边界通过；卫生门仍只报告 `environment-reports`。
该目录已核对仍被 Dify 数据库挂载，本轮没有移动、删除或通过修改规则掩盖。
综合报告：`%LOCALAPPDATA%/ChaosAtlas/runs/h2-replay-core-20260906/repository-acceptance-v3-session.json`。

## 必须继续的 H2 工作

1. v3 **真实执行仍有明确代码门禁**；Secret/LeaseRuntime 尚未接成可执行的真实依赖链。不能把 helper 存在称为完整接入。
2. disposable 响应所有权、Medusa 未知 cart 提交的公共 IsolationManager 释放、业务清理与环境释放分别落证、释放重试尚未完成。当前要求释放的会话会明确返回 cleanup_failed。
3. 补齐跨进程完整 reconcile、强杀窗口、传输 deadline/大小/重定向实测，以及未决写入的跨会话项目门禁。
4. 校验器与解释器继续对齐：固定版本幂等写重试目前不支持；只读 capture 明确拒绝；不能写入 DSL 中尚无解释器语义的字段。
5. 薄验收入口及 OracleRegistry/RunEngine 全生命周期接入尚未完成；后者属于后续 P4，不能称当前方法已跑通。

## 真实环境只读观察

实际 namespace 为 `chaosatlas-immich`、`chaosatlas-medusa`、`chaosatlas-rocketchat`、`chaosatlas-erpnext`。
曾以未加前缀的简称读取，返回空资源；随后按 profile 核实完整名称，没有对错误 namespace 执行任何变更。

本轮读到 Immich v2.6.3、Medusa 2.20.1、Rocket.Chat 8.6.1、ERPNext v16.34.1 的 Pod。
Medusa backend/worker 的 imageID 为 `sha256:1bf4cc153e58a99cf34d92ee970d5494bf0d599899ee2481d691a849cba53464`，
旧 migrate Job 同标签但 imageID 为 `sha256:6bcf762e3a16ff82788a29f67dbcbb67b20badcca728ec759df80d4916bb1dd6`。
这只是只读部署观察，不是 API 语义核实、业务事务成功或应用缺陷证据；H3 必须以实际运行镜像继续采集固定版本源码。

## 后续顺序与授权边界

继续完成 H2，再落实 H3 固定版本 API、2A/3A 身份初始化和四份最终 validated 契约/哈希/语义 diff。
所有这些独立工作完成后才集中请求最终事务审批。批准后再进入 H4 真实业务验收、P4 统一引擎 canary、P5 正式实验。
本轮尚无新真实业务写入、故障注入、应用缺陷、Issue 候选或论文统计结论；合成结果不计入真实证据。
