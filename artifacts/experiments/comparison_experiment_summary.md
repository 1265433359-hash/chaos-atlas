# 对比试验总结：候选选择方法 × 统一候选池 × 可审计证据

> 日期：2026-08-09
> 范围：train-ticket / Online Boutique / OpenTelemetry Demo 三个微服务系统，kind + Chaos Mesh 隔离环境
> 提交链：fdfbd3f（adapter 提取）→ 8227565（真实 LLM）→ 1fc2cae（证据骨架+诚实指标）→ 896eadc（M1 探索批次）→ 2788247（GT 完整+加权+稀疏池）→ 4cdf3f6（扩展探索 5/5）

## 一、试验目标

在**同一候选池、同一预算、同一注入门禁、同一证据判定规则**下，公平对比候选选择方法——包括我们自己的方法（M3/M4/A0-A4）、外部 LLM 方法（M1, ChaosEater adapter + deepseek-v4-flash）、随机基线（M0），并验证外部方法能否被提取为可审计的 adapter。

## 二、参与方法（9 个）

| 方法 | 定义 | 信息层 |
|---|---|---|
| M0 | 随机模板选择（基线） | I0 |
| M1 | ChaosEater-adapter（LLM 领域先验选择，deepseek-v4-flash） | I0 |
| M2 | FastFI-adapter | **blocked：任务不对齐**（故障定位 vs 候选选择，Istio 依赖） |
| M3 | 全局图评分 | I0+I1-global |
| M4 | 我们的完整方法（局部图+运行时证据） | I0+I1-local+I2 |
| A0-A4 | 消融：yaml-only / global-graph / local-graph / +runtime-gate / +evidence-feedback | 逐层 |

## 三、候选池与证据骨架演进

| 阶段 | 池 | 有执行结论 | 关键动作 |
|---|---|---|---|
| 初版 | 12 核心 | 6 | 6 场景 r1-r4（24 次受控注入） |
| 探索批次 | 12 | 11 | 执行 M1 独有的 5 候选（email/catalog/station 等） |
| GT 完整 | 12 | 12 | 补 TT-BASIC-DELAY-100 |
| 重复覆盖 | 12 | 12 | 5 新场景补 r2/r3（三次一致） |
| 稀疏池 | 20 | 12→17 | 加 8 个 score-0 扩展候选；执行 M1 选的 5 个（15 次注入） |

合计 **约 55 次受控注入**（全部 baseline→inject→recover→cleanup 完整生命周期，三 namespace 无遗留注入）。

## 四、指标体系（为什么不用裸 U@10）

- **known-positive recall@10**：|选中 ∩ 已知弱点| / |已知弱点|——用于 ground truth 不完整期。
- **severity-weighted recall**：severity 3=超时/挂死/级联（grpc_error、client_timeout、full cascade）、2=延迟放大（response 保留但显著劣化）、1=弱影响（接近基线）。**这是唯一有区分度的指标**。
- 禁用裸 U@10：12/12 与 17/20 密度下随机期望逼近上限，recall 饱和、无统计意义。

## 五、各阶段结果

### 阶段 1：12 池、6 已知（recall 饱和，无结论可下）
M3/M4=1.000、M0/M1=0.833；6/12 密度下 M0 期望命中恰为 5 → **指标失效，差异只能看"漏了谁"**。

### 阶段 2：M1 探索 5 候选 → 4/5 证实弱点（email 阻塞、延迟放大）
`OTEL-EMAIL-LOSS-100`（email 不可用 → PlaceOrder 10s 挂死）为全新强发现，此前只有静态分析。**M1 无执行历史、纯 I0 先验命中**。

### 阶段 3：12/12 GT + severity 加权（区分度出现）
M1 = **0.920**（三次稳定，只漏弱候选）；M3/M4/A1-A4 = 0.840（稳定漏 severity-3 的 OTEL-EMAIL-LOSS）；A0 = 0.880（漏两个 TT 延迟，不同盲区）。

### 阶段 4：20 候选稀疏池（随机基线压到天花板以下）
随机 M0 掉到 0.333-0.583。**结构性发现**：score-0 的扩展候选永远排不进评分方法 top10 → M3/M4 保持 0.833（盲区），M1 把 ~50% 预算用于探索未知（0.417-0.583）。

### 阶段 5：执行 M1 扩展选择（探索→发现，最强结论）
M1 选的 5 个未知候选**全部证实弱点**：

| 候选 | 结果（×3 重复） | severity |
|---|---|---|
| OB-CHECKOUT-DELAY-2000 | 10s DEADLINE_EXCEEDED | 3 |
| OB-CART-DELAY-2000 | 12s client timeout | 3 |
| OTEL-CHECKOUT-DELAY-2000 | 10s DEADLINE_EXCEEDED | 3 |
| OTEL-CURRENCY-DELAY-2000 | 2s 注入 → ~7s | 2 |
| TT-ORDER-DELAY-2000 | 2s 注入 → ~4s | 2 |

稀疏池最终（severity 加权，r1/r2/r3）：

| 方法 | 加权 recall | 稳定遗漏 |
|---|---|---|
| **M1 ChaosEater** | **0.658 / 0.658 / 0.658** | 全部轻候选 |
| M3/M4/A1-A4 | 0.553 | 全是 M1 探索出的 severity-3/2 弱点 |
| M0 随机 | 0.526 / 0.474 / 0.605 | 飘忽 |

## 六、核心结论

1. **框架可行且可审计**：9 个方法在同池/同预算/同 gate/同证据规则下完成对比，外部方法（LLM adapter）能公平接入，M2 因任务不对齐被诚实拒绝而非硬塞。
2. **M1 探索有效性实证**：LLM 在无执行历史、无静态评分（I0 输入）下选中的未知候选，执行后 5/5 命中（3×severity 3 + 2×severity 2）——**LLM 领域先验能发现评分方法结构性看不见的真实弱点**。
3. **结构性盲区实证**：M3/M4 漏的恰是 M1 探索出的最严重弱点（score-0 候选对评分方法是天然盲区），且 OTEL-EMAIL-LOSS 在最严苛的 12 池阶段也被它们三次漏掉。
4. **severity 加权是唯一有区分度的指标**：裸 recall 在 6/12、12/12、17/20 各阶段都饱和，加权才把方法分开。
5. **方法互补而非竞争**：M1 补盲（未知路径、非关键边），M3/M4 在已知高价值路径稳定，A0 漏 TT 系候选——组合优于单一。

## 七、诚实边界与局限（论文必须声明）

- **不能宣称任何方法"更好"**：recall 饱和、选择-执行循环偏置（原 6 已知按我们方法选出）、M1 优势部分是后验增益（选择被我们执行后才成为已知）。
- **单模型单 prompt**：deepseek-v4-flash 一套配置，推广性未知。
- **新场景仅 3 重复**：统计权重低于原 6 场景的 r4。
- **缺陷候选池同质**：全部为延迟/丢包/pod 故障，未覆盖 CPU 边界（TT-CPU-80 弱影响仅单档）。
- **M1 的"发现"依赖我们执行**：无我们的注入验证链，LLM 选择只是假设。

## 八、对论文的含义（可直接引用的论证链）

1. 我们的方法论能把**外部方法的探索**转成**可审计的发现证据**（adapter + 受控注入框架）。
2. 对比须用**发现质量分级**（severity 加权），不能用裸 recall/U@10。
3. LLM 选择与图/评分方法**互补**：前者补盲未知路径，后者在已知路径稳定。
4. FastFI 定位为"故障定位"相关工作定性对照，非候选选择赛道。

## 九、可复现资产清单

- 代码：`tools/chaos_eater_adapter/`（prompt/schema/映射/后端/adapter）、`tools/generate_m1_adapter_plans.py`、`assess_selection_evidence.py`、`compare_selection_methods.py`、`extended_candidate_pool.py`、`generate_extended_*`。
- 产物：`deep_matrix_registry_r{1..3}_m1.json`（12 池）、`extended_registry_r{1..3}_m1.json`（20 池）、`candidate_evidence_status.*`、`selection_comparison_r{1..3}{,_ext}.*`。
- 实验：`confirmation_*`、`m1_batch_*`、`m1_ext_*` 共约 55 次受控注入 JSON（全部含 baseline/inject/recover/cleanup 与分类）。
- 溯源：M1 每次选择含 event/thought/model/tokens；API key 全程环境变量，无落盘。
- 测试：58 通过；三个 lab namespace 无遗留注入。
