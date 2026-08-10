# Confirmatory Held-out Protocol v1.1 — Hotel (第一确认项目)

> 状态：**FROZEN**（2026-08-10）
> supersedes: `heldout_protocol_v1`
> amendment_reason: budget/statistics/replicate semantics correction
>
> 变更说明：v1.1 修正 v1 中 CE 官方预算占位符、统计结论层级（删除"单 held-out 项目 CI 不跨 0"）、seed/replicate/K 语义、候选池规模、CE blocked 分母规则，并澄清 Equal-information 与 Ours-generic。CE official bring-up 预算固定为 **4h**（见 §2a）。
> **v1 原文件保留为历史冻结版本，未被修改。**

---

## 1. 方法定义（五组，严格分开）

| method_id | 定义 | 输入信息层 | 测量/证据轴 |
|---|---|---|---|
| `Ours-full-pre` | Hotel 源码/manifest 静态 intake 后冻结的项目特定 contract/availability inventory + 通用 SE/DP/JE；decision_engine 在注入的 knowledge snapshot 下运行（零 live 读取） | 项目特定静态契约 + 通用知识资产 | selection + evidence |
| `Ours-generic` | **消融组**：空项目特定 contract（无 Hotel contract/availability），仅通用 SE/DP/JE | 仅通用知识资产 | selection + evidence |
| `ChaosEater-official` | 官方 ChaosEater 完整 pipeline（hypothesis→experiment→analysis→improvement），独立部署 | 官方 manifests + steady states | availability（其稳态定义） |
| `ChaosEater-adapter` | 项目已有 adapter（LLM 盲排序，经我们 OpenAI-compat 封装）。**≠ ChaosEater-official**，严格分开 | 架构描述（盲） | selection |
| `Random` | 同预算随机基线（固定 seed） | 无 | selection |

> 空 contract 不得称为 `Ours-full`；只有 `Ours-full-pre`（有项目特定静态契约）才是完整方法。

## 2. CE official 预算与 Hotel 环境闸门（两个独立规则）

### 2a. CE official bring-up 预算

**CE official bring-up budget = 4h**（固定值，非占位符）。

- 超时或稳态无法建立 → 该项目 CE 对比线标记 `environment_blocked`。
- **不得把 blocked 当作算法 superiority**。
- 详见 §7 CE blocked 分母规则。

### 2b. Hotel 环境闸门（与 CE 预算无关的独立规则）

| 闸门 | 值 |
|---|---|
| bring-up 最长 | 2 小时 |
| 观测链路稳定窗口 | ≥ 30 分钟 |
| 连续两次 baseline 窗口无法复现 | 标记 `environment_blocked` |
| 禁止 | 为通过闸门修改业务代码或方法规则 |

> CE 预算（4h，针对 CE official 部署）与 Hotel 环境闸门（2h/30min/2-baseline，针对实验环境本身）是**两个不同规则**，不得混为一谈。

## 3. 两条主比较线

| 线 | 输入信息 | 目的 |
|---|---|---|
| **Equal-information** | 所有方法获得**同一候选元数据**（edge/fault/静态契约提示，无执行历史） | 比选择器本身（纯选择能力） |
| **Realistic end-to-end** | 各方法使用其标准输入（Ours 用冻结知识资产，full-pre 与 generic 分开；CE 用其标准流程） | 比完整工具链（证据链/根因/漏检/成本） |

> **Equal-information 与 Ours-generic 的关系（澄清）**：
> - Equal-information 线中**所有**方法（含 Ours-generic）获得同一候选元数据。
> - `Ours-generic` 是消融组：即使获得候选元数据，也**禁用**项目特定 contract/availability（空契约）。
> - `Ours-full-pre` 才使用 Hotel 静态 intake 后冻结的项目 contract/availability。
> - Realistic end-to-end 线允许方法使用各自标准输入，但**结果不能写成纯选择算法 superiority**（只能写"完整工具链/知识资产化流水线"层面的结论）。

## 4. seed / replicate / K 语义（明确）

- **一个 method-seed = 一次独立候选选择**。
- **每次选择预算固定为 `K`**。
- **每个选中候选最多进行 2 次确认运行**（1 首跑 + 1 确认）。
- **Weakness@K 按候选计数，不按确认运行次数计数**。

### 4a. 各方法 seed 规定

| 方法 | 选择 replicate | 说明 |
|---|---|---|
| `decision_engine`（Ours 确定性） | **1 个 selection replicate** | 确定性选择，无 LLM 随机性；执行重复（每候选 ≤2 次确认）用于验证，不增加选择样本量 |
| LLM 方法（Ours 若含 LLM / ChaosEater-adapter） | **3 个预注册 seed** | 每个 seed 独立消耗 K（3 次独立选择） |
| `Random` | **20 个 seed**（固定数） | 每个 seed 独立消耗 K |

### 4b. 聚合规则

- 报告 **seed-level 分布**：每个 method-seed 的 Weakness@K / Protected-waste@K。
- 报告 **均值、中位数** 及预注册的聚合规则（如"以 median 为主，mean 为辅"——预注册时固定）。
- **不得把 LLM 的 3 个 seed 与 Ours 的一次确定性选择直接当作相同样本量**（样本量不同，比较须按 seed 聚类/加权说明）。

## 5. 主指标与辅助指标

**主指标：`Weakness@K`** = 预算 K 内确认的真实 weakness 候选数（按候选计数，≥2 次一致 valid run 确认）。

辅助指标（分别预注册，**不允许事后等权合成总分**）：

| 维度 | 指标 | 定义 |
|---|---|---|
| 覆盖 | `Protected-waste@K` | 选中 protected 候选数 / K |
| 覆盖 | 漏检估计 | oracle pass 后：未选候选中的真实 weakness / 总未选 weakness |
| 证据 | lifecycle 完整率 | baseline→inject→recover→cleanup 全完整 run 占比 |
| 证据 | RCA 锚定率 | 根因锚定到源码行/服务的 confirmed issue 占比 |
| 证据 | 证据可追溯率 | 每条结论有 source_file + 运行时证据 |
| 成本 | 单位有效发现成本 | 注入次数 / Weakness@K |
| 成本 | 分析时间 / 人工介入 / 失败恢复成本 | 记录，不合成 |

> **禁止**：将不同量纲指标等权相加成综合总分。

## 6. 统计结论层级（修正 v1 的"单 held-out CI 不跨 0"）

| 层级 | 可写结论 |
|---|---|
| **单个 Hotel** | 只能报告**描述性结果**，**不能声称 superiority**（即使 CI 显示差异） |
| **两个 held-out 项目** | 只能作为**最小复现**，不支持强跨项目显著性 |
| **≥3 个 held-out 项目** | 才允许作**跨项目结论** |

### 6a. CI 与聚类规则（修正）

- **CI 针对项目级配对差值做 clustered bootstrap 或 permutation**（以项目为聚类单位）。
- **不能要求每个项目自己的 CI 都不跨 0**（项目内 CI 不跨 0 不是必要条件）。
- **同一项目中的候选不能被当作独立项目样本**（候选嵌套于项目，样本单位是项目，不是候选）。
- 正式跨项目结论的写法：

> **至少 3 个 held-out 项目的项目级配对差值，clustered bootstrap/permutation 95% CI 不跨 0。**

> v1 中"差值的 bootstrap 95% CI 不跨 0（在单个 held-out 项目上）"规则已删除/改写。

## 7. CE blocked 分母规则（修正 v1 的"候选不进入分母"）

CE official 在某项目无法完成 bring-up 或稳态建立时：

1. 该项目 CE 对比线标记为 `environment_blocked`。
2. **不得从剩余候选中删除后继续声称 Ours 胜出**（禁止选择性分母）。
3. **不得把 blocked 当作算法 superiority**。
4. 该项目比较结果只能报告为 **blocked / 不可比较**（不进入胜出判定，也不进失败判定）。

> v1 只写"CE blocked 候选不进入主指标分母"——**已修正**：整个项目的 CE 线为不可比较，避免选择性分母偏差。

## 8. 候选池规模

| 阶段 | 每个 held-out 项目候选数 |
|---|---|
| **pilot** | 24–32 |
| **formal** | 48–64 |

候选池**必须包含**：

- `protected` / `unprotected` / `unknown`（三类保护状态）
- `delay` / `loss` / `kill`（至少三类故障族）

若项目不支持某类注入（如某项目无 kill 能力），**明确标记 `unavailable`**，不强制补齐。

候选生成规则：**中性规则生成 + 静态证据分层**，不得用结果反向挑选候选。

## 9. 选中/未选/ oracle pass 关系

- 选中候选：按预注册方法选择执行（budget K）。
- 未选候选：抽取独立 audit set，估计漏检。
- oracle pass：选择实验结束后，对整个候选池执行一次完整独立真值建立；**结果不回流到方法选择阶段**。

## 10. 结果不可回填

实验结果、CE 输出、人工 runtime verdict **均不得回填**到本轮 selection snapshot。

## 11. 预注册胜出条件（修正后）

> **Ours-full-pre 在至少 3 个 held-out 项目上，Weakness@K 不降低（≥ CE-official 的项目级配对差值），且项目级配对差值的 clustered bootstrap/permutation 95% CI 不跨 0；并在预注册的证据终点（RCA 锚定率 / 证据可追溯率 / 单位有效发现成本）之一优于 CE-official；同时 Protected-waste@K 不更高。**

附加规则：
- CE `environment_blocked` 的项目不得计入胜出（也不计失败），该项目报告 blocked/不可比较。
- 若 Ours 只在 Realistic 线胜出，主张写"知识资产化流水线优势"，不写"选择算法全面优于"。
- 单个 Hotel 或两个项目不满足胜出条件（统计层级 §6）。

## 12. 统计规则（汇总）

- 候选嵌套在项目内；CI 按项目聚类（clustered bootstrap / permutation）。
- 项目内 CI 不跨 0 不是必要条件。
- ≥3 held-out 项目 + 聚类 CI 才允许跨项目结论。

## 13. 防污染流水线（顺序固定）

```
Hotel 源码/manifest 静态 intake
        ↓
contract/availability inventory 构造（静态）
        ↓
knowledge snapshot 冻结（validate_knowledge_snapshot 兼容）
        ↓
candidate pool 冻结（中性规则生成，非结果反向挑选）
        ↓
blind method selection（五组，K 预算，seed 规定见 §4）
        ↓
common execution（同一 runner，每选中候选 ≤2 确认）
        ↓
independent truth evaluation（oracle pass，不回填）
```

> Hotel snapshot 的 `source_provenance` 五字段须全为 `static_reconstructed_pre_experiment` 或 `pre_experiment_commit` 才允许 `Ours-full-pre` 的 frozen replay 标 `valid`；否则 blocked。

## 14. 当前阶段状态（Hotel intake）

- **go_no_go = blocked**（见 `hotel_intake_report.md`）：仓库内无 Hotel 源码/manifest，禁止下载。
- 本协议冻结于此；**Hotel intake 从 blocked 改为 ready 需要人工决策**（提供仓库路径或批准受限下载）。
- 未进入 P2（快照）、pilot 或正式实验。
