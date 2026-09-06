# P3 H4 四项目真实事务基线验收报告

日期：2026-09-06。批准批次：`87f929e0d52510871fb19d8e8bc40a46f1002dd9ff921d5d26be0579a5648db3`。

## 1. 结论

本轮在 `chaosatlas-apps` Kind 集群中使用统一 `IsolationManager`、真实固定版本镜像、每次新建的 L2 可销毁副本和用户批准的冻结 v3.1 契约执行了正常事务基线。没有执行故障注入。

| 项目 | 正常事务基线 | 环境释放 | 真实证据结论 |
|---|---|---|---|
| Immich | 通过 | 已确认 | 上传唯一合法 PNG，独立哈希与新鲜下载哈希一致 |
| Medusa | 通过 | 已确认 | 建购物车、加入合成商品，新鲜读取的商品、数量、价格、币种均通过 |
| ERPNext | 通过 | 已确认 | 创建并更新合成 ToDo，新鲜读取的描述和状态均通过 |
| Rocket.Chat | 阻断 | 已确认 | 房间创建成功，发消息被固定版本返回 `restricted-workspace`；未完成正常事务 |

因此当前是 **H4 正常基线部分完成（3/4）**，不是 H4 全部退出，更不是四项目正式故障实验已完成。Rocket.Chat 的结果是外部 workspace/许可门阻断，不满足应用缺陷 Issue 的证据门。

## 2. 精确契约与真实运行

| 项目 | 冻结契约 SHA-256 | 运行 ID | 事务汇总 SHA-256 |
|---|---|---|---|
| Immich | `30c4b6e7ec2b3f845668cc98f7778479654616740c30a7978b398cd10a7b3328` | `h4-immich-e50d6f4706a74a1d` | `72dd7293f73669b6f331d6d01d9118b98430c1f579a3781dfffb4d2d92724952` |
| Medusa | `64e93fce8679d9f957080919c95ed43bd95003b54c784c75a7f97a686345224c` | `h4-medusa-3f43fe0a119c4fa1` | `e6a1b878c904123d061ba062753e30c04d3b0310b6da095ca32705be8a8dad3e` |
| Rocket.Chat | `ea606c9724f8decd8b0be8b532a71f610f111f9d28d3bc758f2eead3ead12c55` | `h4-rocketchat-5358f5ba1a1a4dd1` | `99c2eb3cfe55ff436d427c54b6acc05dcc8c3c842797ec932a2865c415bad202` |
| ERPNext | `20eb561ff282f3fcdec352b56cd45885cccef0af2f094b6f0e383e910a5f9f84` | `h4-erpnext-16de30fff4004417` | `84f85df38950a4160bd71e61bb5fa5cf463672664886f7dd0785c605b944ec4c` |

外置证据根位于 `%LOCALAPPDATA%\Packages\OpenAI.Codex_2p2nqsd0c76g0\LocalCache\Local\ChaosAtlas\runs`：

- Immich：`p3-h4-immich-baseline-20260906-b`
- Medusa：`p3-h4-four-project-baseline-20260906-a\medusa`
- Rocket.Chat：`p3-h4-rocketchat-baseline-20260906-c`
- ERPNext：`p3-h4-erpnext-diagnostic-20260906-g`

四次选定运行的租约均有 `cleanup_confirmed=true`、`environment_released=true` 或等价的隔离审计，且运行汇总的持久化敏感值扫描未命中。凭据值、管理员会话和 API secret 未进入仓库或报告。

## 3. 本轮发现并修正的方法问题

1. 原 NetworkPolicy 依赖 `kube-system` namespace selector 放行 DNS，在当前 Kindnet 上出现间歇性解析失败。修订为只放行 TCP/UDP 53，其余跨命名空间和非 DNS 出站仍禁止。修订后 Immich 与 ERPNext 的全新副本均成功启动；这支持这两次运行，不应外推为所有 CNI 已验证。
2. 事务入口在 `prepare` 已经完成清理时会再次调用 cleanup，可能把首次正确清理覆盖成失败。入口现在复用已完成清理结果。
3. 事务 journal 现在只提取满足严格字符白名单的应用错误码，不持久化响应正文。Rocket.Chat 因而留下了可审计的 `restricted-workspace`，同时避免泄露响应内容。
4. ERPNext 身份引导增加 `token`/`Basic` 两种官方 API 认证探测、只读重试、租约 Secret 写后精确回读以及再次认证。失败诊断只记录用户存在、启用、类型和 key 是否匹配等布尔量，不记录凭据。

ERPNext 曾在两个独立、已正常启动的副本中对新 API credential 返回 401，第三个独立副本完整通过。该现象目前只能记为间歇性环境/身份初始化证据，尚无三次同向复现、服务端根因或配对对照，不能生成上游 Issue 草稿。

## 4. implemented / tested / real-evidence 边界

| 能力 | 已实现 | 自动测试 | 真实证据 |
|---|---:|---:|---|
| 四项目批准契约基线编排 | 是 | 是 | 三项目通过，Rocket.Chat 阻断 |
| L2 真实应用副本与整租约清理 | 是 | 是 | 四项目运行均最终释放 |
| DNS 端口边界规则 | 是 | 是 | Immich、ERPNext 本轮启动成功；未覆盖其他 CNI |
| Secret 写后精确回读 | 是 | 是 | ERPNext 通过运行支持 |
| 正常业务事务 Oracle | 是 | 是 | Immich、Medusa、ERPNext 支持；Rocket.Chat 无通过证据 |
| 应用错误码脱敏 journal | 是 | 是 | Rocket.Chat `restricted-workspace` 支持 |
| Oracle 真实响应反例自检 | 组件逻辑已有 | 有合成测试 | 本轮未执行真实响应副本自检 |
| 响应丢失、重复 cleanup、跨进程恢复 | 组件逻辑已有 | 有合成测试 | 本轮未完成四项目真实验收 |
| 正式故障注入与因果实验 | P4/P5 框架已有 | 有自动测试 | 本轮未运行 |

## 5. 后续准入

H4 仍需补齐真实响应副本 Oracle 自检、客户端响应丢失、重复 cleanup、跨进程账本恢复和关键窗口进程终止验收。完成这些组件验收后，才能用统一 RunEngine 进入低风险正式故障 canary。

Rocket.Chat 若不改变当前固定版本与外部注册状态，只能保持 `blocked`，其他三个项目可继续完成独立 H4 验收与后续正式实验。任何注册 workspace、接受条款/许可或更换测试版本的方案都需要用户另行选择，不能由当前契约批准推导。
