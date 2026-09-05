# P3 首批事务 Oracle 人工审核包

日期：2026-09-06。状态：四份契约均为 `validated`，尚未 `approved`，尚未执行真实写操作。

## 共同安全边界

- 只允许契约列出的相对 API 路径与 HTTP 方法，不能跳转到其他主机，不能执行 Python/Shell；
- 只用专用测试身份、合成数据和 `run_id` 所有权标记；凭据只引用运行时 Secret，不进入契约；
- 每个写步骤都保存创建意图和精确返回 ID；响应丢失时只能按唯一所有权字段查回；
- 任意退出都清理。Immich、Rocket.Chat、ERPNext 只删除精确 ID；Medusa 先删精确 line item，再销毁
  disposable 数据库环境，不直接改数据库；
- 首次批准只冻结当前项目 revision 和当前 contract hash；任何步骤、断言、目标或 revision 变化均需重审。

## 四份具体草稿

| 项目 | 写入与读取 | 核心断言 | 清理与主要风险 |
|---|---|---|---|
| Immich v2.6.3 | 上传一张固定合成 PNG；按返回 asset ID 读元数据和下载原件 | upload=201、ID 存在、下载 SHA-256 等于独立 fixture 哈希 | DELETE 精确 asset ID；需确认重复 `deviceAssetId` 的版本语义 |
| Medusa 2.20.1 | 用合成 region/variant 建 cart、加数量 1 的 line item、读 cart | 数量、币种、unit price 等于独立 fixture | Store API 未批准 cart delete：删精确 line item 后销毁 disposable DB；不能在共享 adopted DB 上运行 |
| Rocket.Chat 8.6.1 | 建唯一 `ca-{run_id}` 公共频道、发一条合成消息、有界轮询 | room ID、消息正文、异步可见性 | POST channels.delete 精确 room ID；测试用户需具备建/删频道权限 |
| ERPNext v16.34.1 | 建 Low/Open ToDo、读取、改 Closed、再读 | 描述一致、状态确实变为 Closed | DELETE 精确 ToDo name；无财务影响，但测试用户需有 ToDo CRUD 权限 |

具体 JSON：

- `projects/chaosatlas-apps/immich/oracle-drafts/immich-asset-roundtrip-v1.json`
- `projects/chaosatlas-apps/medusa/oracle-drafts/medusa-cart-lineitem-v1.json`
- `projects/chaosatlas-apps/rocketchat/oracle-drafts/rocketchat-message-roundtrip-v1.json`
- `projects/chaosatlas-apps/erpnext/oracle-drafts/erpnext-todo-crud-v1.json`

## 已完成的非真实自检

契约 schema/hash、项目 revision、路径白名单、审批门、清理策略和敏感扫描已由自动测试覆盖。合成正常
Immich 响应通过断言器，刻意错误的下载哈希被捕获。这只验证 Oracle 逻辑，不是四个应用的真实业务证据。

## 审批后才执行

批准后写入外部人工审批记录并冻结 hash，随后按 Immich → Medusa → Rocket.Chat → ERPNext 顺序做正常
事务、刻意 Oracle 反例、每个写步骤失败补偿和响应丢失恢复。缺少测试凭据或 fixture 时精确 blocked，
不以健康检查替代事务，不自动创建高权限生产账号。
