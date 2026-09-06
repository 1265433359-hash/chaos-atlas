# v3 运行身份绑定方案决策单

日期：2026-09-06。状态：阻断最终事务契约生成；没有业务事务写入。

## 新发现的问题

最新事务入口使用 `ReplaySession + LeaseRuntime + SecretHeaders`。它要求冻结契约同时包含 Secret 名称、Secret UID、principal ID 和请求头到 Secret key 的精确映射。这个设计适用于长期不变的专用 namespace，但与 L2 可销毁副本冲突：每个新 lease 都会创建不同 UID 的 Secret 和不同实例身份，旧冻结契约不能重用。

继续批准现有 v2 没有意义：v2 步骤不含 v3 的 `effect`、结构化 `success`、完整 ownership lookup/selection 和 fresh `probe_assertions`，当前真实入口不能执行。

## 方案 A：审批逻辑凭据槽，运行时绑定 lease 所有 Secret（推荐）

冻结契约声明 Secret 的逻辑名称、允许的 header key、最小权限角色和身份匹配规则；实际 Secret UID、namespace UID、principal ID 在每个 lease 创建后由 IsolationManager 生成并写入不可变运行绑定证据。执行前验证 Secret 是本 lease 创建/拥有、key 集完全一致、身份权限符合契约；UID 不能由调用者任意传入。

优点：同一份人工批准语义可以安全复用于多个全新 L2 副本；与“混合隔离 + 可销毁真实应用”一致；能迁移到以后接入的新项目。缺点：需要升级 v3 schema、SecretHeaders、lease 绑定和反例测试，并为四个蓝图补身份初始化。风险：若 lease ownership 校验写错，可能绑定错误 Secret，因此必须加入跨 namespace、替换 UID、额外 key、错误 principal 的失败测试。

下游影响：完成后生成四份新的 v3 草稿和精确审核 manifest；你只需再审批一次事务语义，然后可做 H4 正常事务/失败补偿和 P5 正式实验。

## 方案 B：正式事务固定在现有 L1 专用 namespace

先在四个长期运行的测试 namespace 创建最小权限身份，冻结其稳定 Secret UID；故障副本 canary 仍使用 L2，但事务 Oracle 与故障不在同一个可销毁副本。

优点：改动较少，能较快满足当前 SecretHeaders。缺点：事务和 L2 故障机制的因果链分离；账号/Secret 与这套集群长期耦合；Secret 轮换后所有契约都要重新审批。风险：涉及已有专用环境的持久业务对象和身份，清理失败的影响比 L2 大。

下游影响：适合临时演示，不适合作为方法通用性和论文主证据。

## 方案 C：继续使用 v2/旧重放器

优点：表面上最快。缺点：绕过已实现的 durable recovery、lease identity 和 exact ownership 安全门；批准件与真实执行器不一致。风险：响应丢失时可能无法证明对象归属和清理，证据不能进入正式结论。

下游影响：不接受为正式实验路径，仅保留历史审计。

## 默认与审批边界

推荐选择 A。由于这会改变事务凭据的审批语义和运行时信任边界，不能从先前的方案 A 或 `1C/2A/3A` 自动推导；如果没有明确选择，本阶段停在这里，不生成或冻结伪可执行契约。

