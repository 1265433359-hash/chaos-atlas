# P3 事务 Oracle v2 修订复审包

日期：2026-09-06。状态：四份 v2 均为 `validated`，未批准、未冻结、未执行真实业务写入。

## 为什么 v1 不能直接执行

用户已批准并冻结的 v1 准确描述了业务对象、断言和清理原则，但在实现确定性重放器时发现，v1 没有完整编码
删除请求的 body/path、响应丢失后的查回请求以及持续探测步骤。若执行器在代码中按项目名补这些信息，就会变成
四套隐藏适配逻辑，也会实际执行未经批准的请求。

因此 v1 继续作为原始审批审计记录保留，通用重放器明确拒绝执行 v1。v2 把这些请求全部放回契约，并因语义
发生变化重新进入 `validated → approved → frozen` 门。该修订是对证据边界的纠正，不代表 v1 已获得真实业务证据。

## v2 共同变化

- 明确 `probe_steps`，故障期间只重放只读 GET，不重复创建业务对象；
- 每个写步骤声明有界的响应丢失处理：同一幂等请求最多重试一次、按唯一 ownership 精确查回，或要求销毁
  disposable 环境；
- 清理写成完整 allow-list 请求模板，并列出可接受 HTTP 状态；
- Medusa 明确要求先删精确 line item，再由隔离管理器确认 disposable 环境已销毁；
- 重放器固定单一 HTTP origin，禁用代理和跨主机重定向；运行凭据只由仓库外 resolver 注入 header；
- journal 只记录 request ID、method、path/hash、status 和 body hash，不记录 header、凭据或完整响应；
- 最终一致性使用契约中的 30 秒上限与 2 秒间隔；断言失败立即进入补偿清理。

## 四份待批契约

| 项目 | v2 内容哈希 | 响应丢失与清理 |
|---|---|---|
| Immich | `2ffc2b950af062e407be98c2d350fd7c7e7a621bdad179da669577a3c35cfd6d` | 相同 `deviceAssetId` 只重试一次；按返回 asset ID 执行 `DELETE /api/assets`，body 为 `ids + force=true`，再 GET 确认 404 |
| Medusa | `d88dcdbd350affb5750c7b0bea7dae12dd347052c9145a99787531e616b0dd34` | cart 创建结果不确定时销毁环境；line item 通过读回 cart 查 ID；DELETE 精确 line 后仍必须销毁 disposable DB |
| Rocket.Chat | `c7f5f39c37e75d5918f502781107c6ea221eee2459df4f1a4238056c7e76e5f1` | 房间按唯一 roomName 查回，消息按 room 最新消息查回；POST delete 只携带返回 room ID |
| ERPNext | `7935aa99c15bb79c9cce9e492fa895ecbeeec61b6bd32959728b1556abc4c98f` | ToDo 按唯一 description、最多返回 2 条查回；状态 PUT 最多重试一次；DELETE 精确 name，再 GET 确认 404 |

文件位于 `projects/chaosatlas-apps/<app>/oracle-drafts/*-v2.json`。固定 API 依据包括部署镜像版本、Immich
v2 asset controller、Medusa v2 Store API、Rocket.Chat REST API 和 Frappe REST CRUD 文档。

## 已测试与尚未验证

离线测试已覆盖：冻结门、origin/path 白名单、模板变量、精确删除请求、错误业务值检测、响应丢失重试、精确
查回、异步有界轮询、disposable 环境未释放时清理不得通过、journal 不含 canary 凭据。

这些均是执行器/Oracle 自检，不是应用真实结果。当前只读探测显示四应用存活；Immich 尚未初始化，Medusa Store
API 缺 publishable key，ERPNext 有外置管理员 Secret，Rocket.Chat 仍需建立专用测试身份。批准 v2 后才会创建
合成对象；测试身份初始化是另一项明确的运行环境授权，不由本审批自动扩大。
