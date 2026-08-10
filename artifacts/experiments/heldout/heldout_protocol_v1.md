# Confirmatory Held-out Protocol v1 — Hotel (第一确认项目)

> 状态：**FROZEN**（2026-08-10，commit 冻结于本文 + heldout_protocol_v1.json）
> 目的：为第一个真正 held-out 项目（Hotel Reservation）建立可审计的 confirmatory 对比协议。
> 约束：本文在任何 Hotel 实验前冻结；协议内容在实验后不可修改（候选池/指标/胜出条件均已预注册）。
> 禁止：本协议只允许协议冻结、Hotel 可行性预检、静态知识快照构造；不得运行 pilot/正式实验/任何注入。

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

## 2. 两条主比较线

| 线 | 输入信息 | 目的 |
|---|---|---|
| **Equal-information** | 所有方法获得相同候选元数据（edge/fault/静态契约提示，无执行历史） | 比选择器本身（纯选择能力） |
| **Realistic end-to-end** | Ours 使用冻结知识资产（full-pre 与 generic 分开）；CE 使用其标准流程 | 比完整工具链（证据链/根因/漏检/成本） |

## 3. 候选预算与运行器

- 每方法固定选择 `K=8`（pilot）/ `K=10`（正式）个候选，等预算，不临时补位。
- 所有方法用**同一个 runner**、同一环境、同一 recovery/cleanup 规则。
- 随机种子：每方法预注册 seed（decision_engine 确定性 1 生成；LLM 3 seed；Random 10-20 廉价抽样 seed）。
- 执行盲化：方法选择过程盲化，执行者看不到其他方法结果。

## 4. 主指标（提前锁定）

**主指标：`Weakness@K`** = 预算 K 内确认的真实 weakness 数（≥2 次一致 valid run 确认）。

## 5. 辅助指标（分别预注册，不允许事后等权合成总分）

| 维度 | 指标 | 定义 |
|---|---|---|
| 覆盖 | `Protected-waste@K` | 选中 protected 候选数 / K |
| 覆盖 | 漏检估计 | oracle pass 后：未选候选中的真实 weakness / 总未选 weakness |
| 证据 | lifecycle 完整率 | baseline→inject→recover→cleanup 全完整 run 占比 |
| 证据 | RCA 锚定率 | 根因锚定到源码行/服务的 confirmed issue 占比 |
| 证据 | 证据可追溯率 | 每条结论有 source_file + 运行时证据 |
| 成本 | 单位有效发现成本 | 注入次数 / Weakness@K |
| 成本 | 分析时间 / 人工介入 / 失败恢复成本 | 记录，不合成 |

> **禁止**：将不同量纲指标等权相加成综合总分（量纲不同，等权即人为调分）。

## 6. CE official bring-up 预算与失败策略

- CE official bring-up 预算：`X 小时`（预注册时定值，建议 4h）。
- 超时或稳态无法建立 → 标记 `environment_blocked`，**不得算作我们的算法胜利**。
- failure policy：CE blocked 时，该线该候选记 `environment_blocked`，不进主指标分母。

## 7. Hotel 闸门（预注册，禁用改规则过闸门）

| 闸门 | 值 |
|---|---|
| bring-up 最长 | 2 小时 |
| 观测链路稳定窗口 | ≥ 30 分钟 |
| 连续两次 baseline 窗口无法复现 | 标记 `environment_blocked` |
| 禁止 | 为通过闸门修改业务代码或方法规则 |

## 8. 规模与通过/终止条件

- **pilot**：24-32 候选。
  - 通过条件：CE official 部署成功 + baseline 稳定 + 协议跑通。
  - 终止条件：CE official blocked / baseline 不稳定 / 协议缺陷暴露。
- **正式确认**：48-64 候选，≥2 个 held-out 项目（Hotel 为第一个）。

## 9. 选中/未选/ oracle pass 关系

- 选中候选：按预注册方法选择执行（budget K）。
- 未选候选：抽取独立 audit set，估计漏检。
- oracle pass：选择实验结束后，对整个候选池执行一次完整独立真值建立；**结果不回流到方法选择阶段**。

## 10. 结果不可回填

实验结果、CE 输出、人工 runtime verdict **均不得回填**到本轮 selection snapshot。

## 11. 结论边界

- 单 Hotel 项目最多写：**"在 Hotel 项目和本协议下，Ours-full-pre 优于/不劣于 ChaosEater"**。
- 至少 3 个 held-out 项目才允许写跨项目结论。

## 12. 预注册胜出条件

> **Ours-full-pre 在至少两个 held-out 项目上，Weakness@K 不降低（≥ CE-official），且在预注册的证据终点（RCA 锚定率 / 证据可追溯率 / 单位有效发现成本）之一优于 CE-official；同时 Protected-waste@K 不更高。**
>
> 附加规则：
> - 差值的 bootstrap 95% CI 不跨 0（在单个 held-out 项目上）；
> - CE `environment_blocked` 不得当作算法胜利；
> - 若 Ours 只在 Realistic 线胜出，主张写"知识资产化流水线优势"，不写"选择算法全面优于"。

## 13. 统计规则

- 候选**嵌套在项目内**：置信区间按**项目聚类**，不能把同一项目的所有候选当作独立样本。
- 两三个项目只能作为最小复现，不足以支撑强跨项目显著性结论。
- 跨项目结论需 ≥3 held-out 项目 + 聚类 CI。

## 14. 防污染流水线（顺序固定）

```
Hotel 源码/manifest 静态 intake
        ↓
contract/availability inventory 构造（静态）
        ↓
knowledge snapshot 冻结（validate_knowledge_snapshot 兼容）
        ↓
candidate pool 冻结（中性规则生成，非结果反向挑选）
        ↓
blind method selection（五组，K 预算）
        ↓
common execution（同一 runner）
        ↓
independent truth evaluation（oracle pass，不回填）
```

> Hotel snapshot 的 `source_provenance` 五字段须全为 `static_reconstructed_pre_experiment` 或 `pre_experiment_commit` 才允许 `Ours-full-pre` 的 frozen replay 标 `valid`；否则 blocked。

## 15. 本阶段（当前）只允许

- 协议冻结（本文）
- Hotel 可行性预检（intake report，只读）
- 静态知识快照构造（若 intake 找到可靠源码/manifest）

**禁止**：启动集群、跑 pilot、跑 head-to-head、任何注入。
