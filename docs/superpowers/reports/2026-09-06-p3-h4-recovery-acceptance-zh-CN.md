# P3 H4 事务 Oracle 与恢复真实验收报告

日期：2026-09-06。批准批次：`87f929e0d52510871fb19d8e8bc40a46f1002dd9ff921d5d26be0579a5648db3`。

## 1. 结论

本轮使用统一 `IsolationManager`、真实固定版本应用镜像、每次新建的 L2 可销毁副本，以及用户批准的四份 v3.1 冻结契约，完成了 H4 的正常事务、真实响应反事实自检、客户端响应丢失和跨进程恢复验收。

Immich、Medusa、ERPNext 三个项目的 H4 支持分支均有真实证据通过；Rocket.Chat 按用户确认的方案 A 保持阻断，不注册外部 workspace、不接受许可条款，也不更换固定版本。因此四项目总体 H4 状态是 **部分完成（3/4）**，而不是 4/4 通过。

| 项目 | 正常事务与自检 | 客户端响应丢失 | 跨进程恢复 | 环境释放 | H4 结论 |
|---|---|---|---|---|---|
| Immich | verified | verified | verified | verified | 支持分支完成 |
| Medusa | verified | verified | verified | verified | 支持分支完成 |
| ERPNext | verified | verified | verified | verified | 支持分支完成 |
| Rocket.Chat | blocked | 未运行 | 未运行 | 已释放既有验收副本 | `restricted-workspace` 外部门阻断 |

这些运行没有执行服务端故障、Chaos Mesh 注入或应用缺陷复现；所有相应摘要均明确记录 `server_fault_injection_performed=false`。本报告证明的是 P3 组件及恢复边界，不是 P4/P5 正式故障实验结论。

## 2. 精确真实证据

外置证据根为 `%LOCALAPPDATA%\ChaosAtlas\runs`。原始证据不进入 Git，以下 SHA-256 用于核对相应 `acceptance-summary.json` 或项目汇总。

| 项目/场景 | 外置运行目录 | 状态 | 汇总 SHA-256 |
|---|---|---|---|
| Immich 正常事务与自检 | `p3-h4-immich-selfcheck-20260906-i` | verified | `4f877fc7b9690ac06fc9ddce00b6c321d77258d5a79b90e3752747877db1b0f0` |
| Immich 响应丢失 | `p3-h4-immich-response-loss-20260906-j` | verified | `5302a01a4ba4493d902938664030e1d754a877e28e7b8b93e30ae494b4b297a2` |
| Immich 跨进程恢复 | `p3-h4-immich-process-recovery-20260906-m` | verified | `0fc19e5b2387ce9438c953caf42e2442a9e96c298e51a7773bb43a8cd2f12b92` |
| Medusa 正常事务与自检 | `p3-h4-medusa-erpnext-selfcheck-20260906-n\medusa` | verified | `c85a046739877f0286f390ad66bf57803e6fd8924bc8db6be3a5f5de40516be5` |
| Medusa 响应丢失 | `p3-h4-medusa-response-loss-20260906-u` | verified | `d61cbf808fdd1adccbcb9fc68941bb20995db56a217a69252476dfe5b131c9a5` |
| Medusa 跨进程恢复 | `p3-h4-medusa-process-recovery-20260906-w` | verified | `4dadb74bfb6fdf5fc86185639f3d405bf19c17b84da2a504d04adebdbebd75a2` |
| ERPNext 正常事务与自检 | `p3-h4-erpnext-verified-baseline-20260906-ad` | verified | `f6e89805e339148c3f64c7d159855a0dfef2fa5c5169c84771820c13c50def3d` |
| ERPNext 响应丢失 | `p3-h4-erpnext-preweb-response-loss-20260906-ae` | verified | `4d3793b703905ad923b952017978ffec5d14ee5e3c7914613a48e66e051366af` |
| ERPNext 跨进程恢复 | `p3-h4-erpnext-preweb-process-recovery-20260906-af` | verified | `9ae8d24ca161f20781ffb186642edb2a981e9b092cff306f9f9956155458118f` |

Medusa 基线与 ERPNext 的一次失败尝试位于同一个批次目录，因此批次顶层状态为 `partial`；表中引用的是其中独立为 `verified` 的 Medusa 项目汇总，不能把失败的 ERPNext 条目算作通过。

## 3. 证据支持的行为

### 3.1 正常事务与 Oracle 自检

- Immich：真实上传唯一合法 PNG，新鲜下载结果与独立计算的哈希一致。
- Medusa：真实创建购物车并加入合成商品，新鲜读取验证商品、数量、价格和币种。
- ERPNext：使用最小权限合成身份真实创建、读取、更新和再次读取 ToDo；12 次连续授权读取均为 200。
- 三个项目均从真实响应的内存副本构造反事实，已批准契约中的四项业务断言均能识别对应错误。反事实结果标记为 `synthetic_oracle_self_check`，不计为应用异常。

### 3.2 客户端响应丢失

三个项目均在服务端完成第一次真实写入后丢弃客户端响应，账本把结果保留为未知并通过契约批准的查回/归属规则收敛。该流程没有为了“确保成功”而重发不确定写入，最终完成精确业务清理和租约释放。

这只证明客户端未知提交结果的处理能力，不证明网络代理、服务端丢包或应用在真实网络故障下的表现。

### 3.3 跨进程恢复

三个项目均由外部控制器在写入意图已经持久化、操作处于 `outcome_unknown` 时终止工作进程，再由独立进程读取恢复账本。每次运行均确认：终止前写请求数为 1、恢复期间写请求数为 0、恢复进程退出码为 0、清理完成且环境释放。

## 4. 本轮修正的方法问题

1. `ReplaySession` 增加基于真实响应内存观察的反事实自检，持久化内容只包含断言 ID 与布尔结果，不保存响应正文。
2. 四项目验收入口增加 `baseline`、`response-loss`、`process-recovery` 三种明确场景，并将外部终止、恢复写次数、重复清理和释放结果写入结构化摘要。
3. `IsolationManager` 的 Kubernetes Ready 验证现在重新读取所有已注册资源，核对 UID 与租约 owner label，避免名称复用或资源被替换后仍误判 Ready。
4. ERPNext 身份改为在 Web 工作负载启动前由建站 Job 创建固定最小权限角色、用户和 API key；运行期只从租约所属 Secret 绑定认证并做 12 次连续只读稳定性检查。这样消除了不同 Gunicorn worker 读取运行期新 key 时出现的间歇性 401。
5. 敏感值扫描器允许蓝图中的未解析 `${...}` 模板，但仍拒绝任何已经物化的 token。旧运行 `p3-h4-erpnext-preweb-baseline-20260906-ac` 的业务核心已通过，却因模板误报成为 `partial`；修正后重新执行的 `...-ad` 才是本报告采用的完整通过证据。

以上是方法/适配和环境问题，不是上游应用缺陷。

## 5. 无效或失败运行不得作为通过证据

- `p3-h4-immich-selfcheck-20260906-h`：运行后发现 NetworkPolicy 被手工删除，已有 `EVIDENCE-INVALIDATED.json`，不得引用。
- Immich `k/l`：进程包装与终止控制失败，不是应用或恢复机制通过证据。
- ERPNext `n/o/r/s/t/y/z/aa/ab`：分别暴露身份类型、路径编码、权限稳定性、运行期 key 和重启可用性问题；均未通过最终证据门。
- ERPNext `ac`：真实事务、自检、清理均通过，但证据封套受旧扫描器模板误报影响，只能作为修复诊断材料；正式结论引用重新运行的 `ad`。
- 先前 ERPNext `v/x` 虽真实通过响应丢失与恢复，但使用的是被后续替换的运行期身份方案；本报告改用最新预 Web 身份实现下的 `ae/af`。

## 6. implemented / tested / real-evidence 边界

| 能力 | 已实现 | 自动测试 | 真实证据 |
|---|---:|---:|---|
| 真实响应反事实自检 | 是 | 是 | Immich、Medusa、ERPNext |
| 客户端响应丢失后查回与精确清理 | 是 | 是 | Immich、Medusa、ERPNext |
| 外部终止与独立进程恢复 | 是 | 是 | Immich、Medusa、ERPNext |
| 恢复期间不重发未知写入 | 是 | 是 | 三项目均为 0 次恢复写入 |
| 租约资源 UID/owner 重验 | 是 | 是 | 本轮所有选定 L2 运行正常释放；不外推到未测 CNI/集群 |
| Rocket.Chat 完整事务 | 代码与契约已有 | 有离线测试 | 无；workspace 门阻断 |
| 服务端故障注入 | 执行能力另有实现 | 有自动测试 | 本轮未运行 |
| RunEngine 统一事务工厂接入 | 尚待 P4 | 现有普通 Oracle 有测试 | 无 |
| P5 三次复现、配对对照、RCA 与 Issue 门 | 初版框架已有 | 有自动测试 | 无正式实验结论 |

## 7. H4 退出与下一步

Immich、Medusa、ERPNext 已满足进入 P4 低风险完整生命周期 canary 的 H4 前置；Rocket.Chat 仍保留明确阻断，不降低证据门。P4 必须把通用事务工厂真正注册到 `OracleRegistry`，由唯一 `RunEngine` 注入租约目标、凭据、journal 和恢复账本，并让单候选、批量与 resume 共用同一路径。P4 canary 通过后才进入 P5 的 32 核心 + 9 provisional 静态评估与低强度正式实验。
