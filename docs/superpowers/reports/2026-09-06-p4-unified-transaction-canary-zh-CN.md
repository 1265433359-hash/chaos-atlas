# P4 统一 RunEngine 事务 Oracle canary 报告

日期：2026-09-06。批准契约批次：`87f929e0d52510871fb19d8e8bc40a46f1002dd9ff921d5d26be0579a5648db3`。

## 1. 结论

事务 Oracle 已进入唯一的 `RunEngine` 主链，不再只存在于 H4 独立验收脚本。当前统一链路为：

`RunEngine → live batch → IsolationManager → 副本内资源重新发现 → 冻结事务 Oracle → 基线 → 故障注入与机制确认 → 业务观察 → 故障恢复 → 业务清理 → 环境释放 → 证据/RCA/学习阶段`

Immich 的 `secret_rotation` 低风险 canary 在当前代码下真实通过：隔离副本 Ready、事务上传成功、基线/注入期间/恢复后三次新鲜业务读均通过、Secret 修改被机制确认、原始 Secret 快照恢复、事务和环境清理完成、最终无测试 namespace 残留。该结果是一个 **no-impact canary**，不是应用缺陷。

P4 的核心统一引擎接入和真实生命周期 canary 已完成；真实 LLM 调用未完成。当前主机没有 `DEEPSEEK_API_KEY`/`CHAOS_EATER_API_KEY`，仓库外也没有专用 DeepSeek key 文件，因此本次运行明确记录 `advisory_status=deterministic_fallback`。不能宣称 LLM 策略已获真实证据验证。

## 2. 实现边界

1. `OracleRegistry` 正式注册 `transaction_http`。缺少明确的 `TransactionOracleDependencies` 时 fail closed，不能回退到普通健康检查。
2. `RunRequest` 新增精确 `oracle_approval_dir`；它只允许用于带隔离故障的 live run。批准目录、项目 revision、Oracle ID、契约 hash、镜像 digest 和 service 任一不一致都会阻断。
3. `run_isolated_live` 把同一个 `IsolationManager`、lease ID、namespace、context 交给内层执行，运行 profile 只保存批准件的 ID/hash，不保存凭据。
4. `LeaseTransactionDependencyFactory` 在租约内初始化最小权限身份，绑定 lease-owned Secret，生成唯一合成夹具，构造外置恢复账本和脱敏 journal。
5. 所有专用故障执行器统一由 `WorkflowBoundFaultExecutor` 包裹，必须执行 `prepare_fixture → probe → collect_evidence → cleanup_fixture`。业务清理失败会把 attestation 改为无效并禁止晋级。
6. 候选目标由临时 namespace 的只读 Kubernetes inventory 重新发现；运行中使用的 deployment ID、selector、Service UID、namespace UID 和 Secret UID 来自副本，不复用源环境 UID。
7. 批量汇总现在区分“候选已尝试”和“注入已确认”；隔离摘要只在子 fault 明确 `injection_confirmed=true` 时记录 `injection_performed=true`。
8. 恢复账本放在同一隔离运行的外层状态根，避免 Windows 长路径，同时仍保持仓库外和单 lease 边界。

## 3. 真实证据

采用的当前实现运行：`%LOCALAPPDATA%\ChaosAtlas\runs\p4-unified-immich-secret-rotation-canary-20260906-ai`。

| 证据 | 结果 |
|---|---|
| batch 状态 | `completed`，1/1 candidate `live_completed` |
| 隔离状态 | `verified`，lease `lease-528ef1b304674f70` 已 released |
| 事务契约 | `immich-asset-roundtrip-v3`，SHA-256 `30c4b6e7...a7b3328` |
| 机制证据 | `secret_value_reflected`，首次检查即确认 |
| 基线 | 资产 ID 与原件哈希断言均 pass |
| 注入期间观察 | 资产 ID 与原件哈希断言均 pass |
| 恢复 | Secret snapshot match，恢复后业务断言均 pass |
| 清理 | fault cleanup 与 business cleanup 均 confirmed；环境释放 true |
| attestation | baseline/injection/observation/recovery/cleanup/independent Oracle/comparison 全为 true，missing 为空 |
| finding | 0；分类 `response_observed`，RCA 仅 `bounded` |
| 敏感扫描 | `[]` |
| namespace 残留 | 0 |

关键文件哈希：

- `run/batch_summary.json`：`79e6370eea173530d9ea8c252c2efe997b493eccd10b196207b2f40e9281246f`
- `isolation-lifecycle.json`：`32d699c6e987bba4c152698933884cae37f20ec07dfb8790197f8d2df0979184`

## 4. 不采用的失败运行

`p4-unified-immich-secret-rotation-canary-20260906-ag` 在第一次写入账本前因 Windows 路径达到 263 字符而阻断。该运行的事务身份和隔离清理证据有效，但没有注入；旧顶层摘要又错误地把 `executed_count=1` 当作注入发生，因此不得作为 P4 通过证据。

修正账本路径后，`...-ah` 首次完成统一 canary；随后又修正顶层注入口径，并以当前代码重新运行 `...-ai`。报告只采用 `...-ai` 作为最终 P4 canary。

## 5. implemented / tested / real-evidence

| 能力 | 已实现 | 自动测试 | 真实证据 |
|---|---:|---:|---|
| 事务 Oracle 注册与显式依赖门 | 是 | 是 | Immich canary |
| 单候选经统一 RunEngine/批量路径 | 是 | 是 | Immich canary |
| 副本资源重新发现与 UID/selector 绑定 | 是 | 是 | Immich canary |
| 基线、观察、恢复使用新鲜事务读取 | 是 | 是 | 三阶段均通过 |
| 专用执行器完整事务生命周期 | 是 | 是 | Secret rotation canary |
| 故障机制确认与快照恢复 | 是 | 是 | Secret reflected/snapshot matched |
| 业务清理和环境释放 | 是 | 是 | 双清理 confirmed，零残留 |
| batch/resume 共享事务依赖透传 | 是 | 是 | batch 单候选真实；resume 仅自动测试，未跨不确定写入重放 |
| 真实 LLM 假设建议 | 接口已有 | 有模拟/结构测试 | 无；明确 deterministic fallback |
| 多项目正式实验和三次因果复现 | P5 框架已有 | 有自动测试 | 尚未由本报告证明 |

## 6. P5 准入

Immich 已满足统一引擎的低风险正式实验准入。Medusa 与 ERPNext 已有 H4 事务/恢复证据，但仍需各自运行一个统一链 canary；Rocket.Chat 继续因 `restricted-workspace` 保持 blocked。P5 必须保留 32 核心 + 9 provisional 的完整分母，并把 no-impact、blocked、unsupported、inapplicable 与 finding 分开统计。没有三次独立复现、配对对照和完整机制/清理证据时，不生成应用 Issue 草稿。
