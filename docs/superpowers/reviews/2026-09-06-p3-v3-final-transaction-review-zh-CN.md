# P3 v3 四项目最终事务契约复审包

日期：2026-09-06。状态：H3 实现、离线测试和真实身份验收已完成；四份契约均为 `validated`，尚未批准或冻结。H4 真实业务事务和故障注入均未开始。

## 1. 结论边界

| 层次 | 当前结论 |
|---|---|
| 已实现 | 统一 `RunEngine / WorkflowOracle / IsolationManager` 路径、v3.1 受限解释器、lease-owned Secret 绑定、四项目可销毁身份初始化、整租约清理 |
| 已测试 | v3 验证、运行绑定、响应丢失恢复、精确数组匹配、隔离蓝图与身份初始化均有自动化测试；最终全量结果为 `561 passed` |
| 有真实证据 | 四个固定版本应用都创建过完整 L2 副本，初始化合成身份、绑定最小权限凭据，并释放 namespace；证据未持久化凭据值 |
| 尚无真实证据 | 上传图片、创建购物车、发消息、创建/更新 ToDo；任何故障注入、因果结论、应用缺陷或 Issue 候选 |

本次批准若通过，只授权按下列精确契约在新的 disposable lease 中先做正常事务与失败补偿验收；不等于批准扩大故障强度、共享环境写入或自动提交上游 Issue。

## 2. 精确待审清单

机器可读审批输入：`docs/superpowers/reviews/2026-09-06-p3-v3-contract-review-manifest.json`。

| 项目 | Oracle | 文件 SHA-256 | 契约 SHA-256 |
|---|---|---|---|
| Immich | `immich-asset-roundtrip-v3` | `024c76e7f2f47b6b5aa4cf53bce23ace81cdcecd61b9abfd734763bc548b9c6f` | `88c816fcce546977b31b8fe8d5f283a0c5aa84a978731dc4956c9bb4fddb9af6` |
| Medusa | `medusa-cart-lineitem-v3` | `dbe620eaf1ce76ac654771959cda81d3905ee6b3b7165eb6b0a59529ddf94f13` | `351eafb1e36dcf5c42579739827b3cb9da10a2f5ff0f422ed83aa8f2bf0bfa9c` |
| Rocket.Chat | `rocketchat-message-roundtrip-v3` | `7f25b406369b47b3e59dd536ba19d452bad06e0afaa1d106cc5901dae0257e9f` | `efa397746958f885f8ddba776b6d41a93af6736a501d2959aac72d72f6497582` |
| ERPNext | `erpnext-todo-crud-v3` | `15bc10d43ce197a03116d2a9235a4a8062ce78321ff04455eac0026eebbdffd1` | `e02fb15d85588b7f72d709b11538c822917ab808ce72194c29b77fa49d28a60b` |

四份契约都使用 `transaction-http-3.1`。任何文件内容、契约哈希、解释器版本或请求白名单变化都会使本次审批失效并重新进入审核。

## 3. 大白话版事务内容

### Immich

在全新副本里用普通测试用户上传一张每次都不同的合成 PNG；读回资产元数据，并下载原文件。Oracle 检查返回的资产 ID 与本轮一致，下载字节的 SHA-256 与独立生成的夹具哈希一致。任何写响应丢失都不猜测是否成功，直接以销毁整套副本收敛。

### Medusa

在全新数据库预置一个合成销售渠道、region、商品和 variant。事务创建 cart，加入唯一 variant，再读回 cart；检查 cart ID、只有一条 line、variant、数量、币种和单价全部正确。Store API 没有获批的 cart 删除路径，所以唯一补偿方式是销毁整个数据库租约。

### Rocket.Chat

在全新副本公开注册一个合成普通用户，不使用管理员执行日常事务。事务创建本轮唯一频道、发送带 run ID 的消息，再读取消息列表。v3.1 不再假定 `messages[0]` 是目标，而要求在有界列表中恰好一条消息同时匹配 room ID、发送者 ID 和正文；重复或归属不符都失败。频道、消息和账号随整个租约销毁。

### ERPNext

管理员只负责创建普通合成用户并调用固定版本官方 `generate_keys`。普通用户事务创建一个带 run ID 的 ToDo，读回确认描述和 `Open`，更新为 `Closed`，再用新响应确认描述和状态。ToDo、用户、site 和数据库都随租约销毁。

## 4. v2 到 v3.1 的关键语义变化

- 凭据由“契约固定某个 Secret UID”改成“契约批准逻辑凭据槽，运行时只绑定当前 lease 创建并拥有的 Secret”；namespace UID、Secret UID、principal ID 都写入运行证据，调用者不能伪造。
- 每个请求明确 `read/write`、成功状态和必要字段；prepare 与 probe 使用分开的新鲜观察。
- 写操作使用持久恢复账本；发送前记录意图，响应丢失、坏 JSON、缺 ID、日志失败或进程重启都不会被误报成清理成功。
- 四项目都采用 lease-exclusive ownership：只允许在全新、合成、可销毁副本写入，补偿由 `IsolationManager` 的真实释放审计证明，而不是任意 callback 返回值。
- Rocket.Chat 从“取最新消息”升级为按 room、sender、正文三条件恰好一条匹配；解释器因此从 3.0 升为 3.1，旧审批不能复用。
- Medusa 不再声称可以精确删除 Store cart；Immich、Rocket.Chat、ERPNext 也不在共享实例中逐对象冒险清理，统一用已验证的整租约销毁边界。

## 5. 固定版本 API 与运行身份证据

`docs/superpowers/reviews/2026-09-06-p3-v3-api-evidence-manifest.json` 记录了实际部署 image digest，以及部署镜像内控制器、路由或源码文件的 SHA-256。版本为 Immich 2.6.3、Medusa 2.20.1、Rocket.Chat 8.6.1、ERPNext 16.34.1 + Frappe 16.33.0。

真实身份验收文件如下；四份项目结果均为 `verified`、`cleanup_state=released`，对应验收汇总明确声明 `business_transaction_executed=false`、`fault_injection_performed=false`。文件只保存 Secret 名称、UID、key 名和 principal role，不保存凭据值。

| 项目 | 外置证据 | 文件 SHA-256 |
|---|---|---|
| Immich | `%LOCALAPPDATA%\ChaosAtlas\runs\p3-v3-identity-final-20260906-a\immich\identity-acceptance.json` | `7f815bbd59577644a4924f01e7e8e55b9a4f593f3f5112a8d54e28fc185433ae` |
| Medusa | `%LOCALAPPDATA%\ChaosAtlas\runs\p3-v3-identity-final-20260906-a\medusa\identity-acceptance.json` | `be445533c1c03ae9037d6324908fe23bf69c6c3ace1787a3ba8a8531fcd1b52d` |
| Rocket.Chat | `%LOCALAPPDATA%\ChaosAtlas\runs\p3-v3-identity-final-20260906-a\rocketchat\identity-acceptance.json` | `c2b309f0ba6424655016b93448edea7d01d8ff614abc3ce4935642450bbab34c` |
| ERPNext | `%LOCALAPPDATA%\ChaosAtlas\runs\p3-v3-identity-final-20260906-erpnext-b\erpnext\identity-acceptance.json` | `ca2ef902972197fddfcd085d87abd33fdbef9811e4f13f93dbdb7caaf13643db` |

一次 ERPNext 验收曾在生成 key 后立即读取时返回 401；该失败报告为 `partial`，但租约仍为 `released`。修复只对无副作用的鉴权 GET 最多重试三次，不重试用户创建或 key 生成；新 lease 的重跑已通过。它属于方法初始化鲁棒性问题，不是 ERPNext 应用 Issue。

## 6. 权限、通知与清理

| 项目 | 日常身份 | 凭据槽 | 外部通知 | 最终清理 |
|---|---|---|---|---|
| Immich | `transaction-test-user` | `immich-transaction-auth/x-api-key` | 关闭 | namespace 删除审计 |
| Medusa | `transaction-sales-channel` | `medusa-transaction-auth/x-publishable-api-key` | 无 | namespace 与合成数据库删除审计 |
| Rocket.Chat | `transaction-test-user` | `rocketchat-transaction-auth/x-auth-token,x-user-id` | 邮箱验证/欢迎流程关闭 | namespace 删除审计 |
| ERPNext | `transaction-todo-user` | `erpnext-transaction-auth/authorization` | 不使用用户真实邮箱 | namespace、site 与数据库删除审计 |

运行完成后的只读检查未发现 `chaosatlas.dev/managed=true` 的残留 namespace。长期运行的四个基线 namespace 未被修改或销毁。

仓库级综合验收报告位于 `%LOCALAPPDATA%\ChaosAtlas\runs\p3-v3-repository-acceptance-20260906-a\repository-acceptance.json`，SHA-256 为 `28d4ac1fd42d799d610c449861b8491e1af90d596d71715319cefa6cc537fb82`。其中 compileall、12 项架构门、两个统一引擎 dry-run 和产品边界均通过；总状态为 `partial`，唯一失败是仓库中保留的历史 `environment-reports` 目录。该目录可能仍被 Dify 挂载，本阶段不把删除或迁移活跃数据推导为已授权操作，因此卫生门保持显式未通过。

## 7. 获批后的执行顺序

1. 用机器清单再次校验四份文件哈希和 `validated` 状态，原子记录本次人工批准并冻结四份契约。
2. 按 Immich → Medusa → Rocket.Chat → ERPNext 创建全新 lease，执行无故障正常事务、业务断言、整租约清理。
3. 对真实响应的脱敏副本做 Oracle 反例自检；这些只标为 `synthetic_oracle_self_check`，不算应用故障。
4. 做响应丢失、清理重放、跨进程恢复等 P3 失败补偿验收；客户端丢响应不会冒充服务端网络故障。
5. 四项目 H4 通过后，才由统一 RunEngine 进入 P4/P5 低强度正式故障实验与 Issue 草稿证据门。

唯一阻断决定：是否批准第 2 节列出的四份精确 v3.1 契约。方案 A 是四份全部批准；方案 B 是只批准指定项目；方案 C 是退回修改。未明确批准时保持 `validated`，不执行真实业务写入。
