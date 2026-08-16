# ChaosAtlas R5 实验方案审阅简报

> 用途：提交给 GLM 5.3 审阅实验设计、去重规则、公平性和下一步执行方案。
> 当前状态：方案待审阅，`human_review=pending`，未将任何结果写回知识库。

## 1. 研究目标

本轮不是把两个方法改成相同方法，而是保留它们的原始边界，观察完整方法中的知识、分类和置信度机制是否能提高真实故障假设的质量。

比较对象：

- `ChaosAtlas-full`：使用真实 YAML 抽象出的知识、调用链、故障适用条件、历史证据、五类 YAML 分类和置信度停止机制。
- `ChaosAtlas-ablation`：不接收知识库投影，不接收五类分类，不计算置信度；由 LLM 自主生成假设并自主判断是否停止。

这不是同候选池实验，也不是相同故障下的纯执行能力实验。主要问题是：Full 的高置信度选择，是否比 Ablation 的无知识随机对照更容易找到真实、可复现的业务弱点。

## 2. 已冻结或已观察事实

### 2.1 YAML 与分类

- 原始 YAML 总数：`1935`。
- 五大类运行范围：`1506`。
- 统计数量：Pod disruption `341`，Network degradation `428`，Resource pressure `352`，Protocol/HTTP fault `263`，Composite/scheduled fault `122`。
- 当前五类协议 SHA-256：`0148c758d5fe6428354f0070aa9007824f9d33dbce81c96c7a80090808c3fd0b`。

### 2.2 Discovery 与 canonical 结果

- r5 handoff 记录的 confidence discovery：Full `608` 条，Ablation `543` 条；五类均达到 `confidence_saturated`。
- 当前 runtime-ready 输入文件中的候选数量为 Full `460`、Ablation `498`。这与上一条数量属于不同阶段，必须在最终报告中解释来源，不能直接混用。
- 当前 canonical artifact 记录：Full `86` 个，Ablation `89` 个。
- 当前 canonical 规则是每个方法内按 `method|target|kind|action` 保留第一条假设。
- 当前规则没有把 `call_chain_position` 和故障参数纳入 canonical identity。

### 2.3 已完成 runtime 证据

- 当前可核验的 native-full runtime 目录中，已完成 `38` 个 mutation、`76` 份报告，每个 mutation 两次重复。
- 这 `76` 份报告的 `status=completed`，baseline、注入、恢复、删除、全局残留和 washout 均通过。
- 观察分类：`18` 份 `weakness_observed`，`58` 份 `no_business_impact_observed`。
- 这批 native-full 结果覆盖的是已经完成的候选，不应直接宣称 `86` 个 canonical mutation 全部已运行。
- 旧的 stratified pilot 中，Ablation 已完成 `4` 份报告，均完成生命周期；该 pilot 使用了带类别的缩减选择，不符合下面的新 Ablation discovery 边界，因此不计入新正式实验。
- 最近一次集群检查：`chaosatlas-sock-shop` 内 14 个 Pod Ready，全局 PodChaos、NetworkChaos、StressChaos、HTTPChaos、DNSChaos、Schedule、Workflow 无残留。

## 3. 新实验想法

### 3.1 Ablation 的停止方式

Ablation 仍然不使用分类和置信度：

1. 使用与 Full 相同的项目快照、拓扑、oracle 和公共输入。
2. Prompt 中不出现五类分类、置信度字段、Full 的 confidence trace 或知识投影。
3. LLM 自己决定是否继续生成。
4. 为了避免 Ablation 因无限时间获得额外机会，以 Full 对应 seed 的 discovery wall-clock 时间作为硬上限。
5. Ablation 可以提前停止，但不能超过该上限；记录实际停止时间和 `stop_reason`。

这里的“时间上限等于 Full discovery 时间”是待 GLM 重点审阅的设计决定。

### 3.2 两边各自去重

必须先保留原始假设，再做统一归一化。

建议建立两层 identity：

```text
fault_family_key = kind + normalized_action + target_service + call_chain_position
mutation_instance_key = fault_family_key + normalized_parameters
```

`normalized_parameters` 至少包括 duration、intensity、direction、path、delay、loss、CPU load 和 memory size 等真正影响实验语义的字段。

Full 的同一 `fault_family_key` 中保留置信度最高的一条；置信度相同则比较证据完整性，再相同才按首次生成顺序保留。

Ablation 没有置信度，因此同一 family 中保留首次生成且结构最完整的一条，不能根据 runtime 结果挑选。

### 3.3 重合与独有划分

设：

```text
F = Full 去重后的 fault family 集合
A = Ablation 去重后的 fault family 集合
```

划分为：

```text
family-overlap = F ∩ A
full-only = F - A
ablation-only = A - F
```

此外单独记录 `strict-overlap`：只有 family key 和归一化参数都一致，才允许把两个假设当作完全相同的 runtime 题目。

如果两边都是 `orders + NetworkChaos + delay`，但一个是 100ms、另一个是 2s，则是 `family-overlap`，不是 `strict-overlap`。

## 4. 样本选择

### 4.1 Full 样本

从 `strict-overlap` 中按 Full 的置信度选高置信度假设，命名为 `overlap-high-confidence`。

从 `full-only` 中按 Full 的置信度选高置信度假设，命名为 `full-only-high-confidence`。

选择前先按可执行 gate 过滤。Protocol/HTTP 和 Composite/scheduled 如果仍然无法执行，只记录为 blocked，不得放入实际弱点率分母。

### 4.2 Ablation 样本

- 对 `overlap-high-confidence`：使用 Full 已生成的同一份 mutation YAML，交给 Ablation runtime 重新执行。这样可以复用 Full 报告，并在同一故障上比较两边。
- 对 `full-only-high-confidence`：从 `ablation-only` 中使用固定随机种子随机抽取相同数量的假设。
- Ablation-only 抽样不使用 category、confidence、业务结果或人工挑选。
- 抽样前冻结清单；清单生成后不允许因某个结果好或坏而换样本。

如果 Full-only 高置信度样本数为 `N`，则 Ablation 需要执行：

```text
overlap-high-confidence 数量 + N 个 ablation-only 随机样本
```

每个 mutation 两次重复。Full 不重复执行，只复用已有且生命周期完整的 `status=completed` 报告。

## 5. 三组最终比较

| 组别 | Full | Ablation | 主要回答的问题 |
|---|---|---|---|
| overlap-high-confidence | 复用已有 Full 报告 | 执行同一份 Full mutation | 同一故障上，两边 oracle 结果是否一致 |
| full-only-high-confidence | 复用已有 Full 报告 | 不执行对应不存在假设 | Full 是否能发现 Ablation 没有发现的高价值故障 |
| ablation-only-random | 不执行 | 随机等数量执行 | 无知识 Ablation 的随机候选真实产出如何 |

主要指标：

- 稳定真实弱点数及比例；
- 两次是否都复现；
- 一次性或不可重复结果数；
- baseline、注入、恢复、cleanup、washout 失败数；
- family overlap 和 strict overlap；
- discovery wall-clock 时间；
- Full 已有 runtime 时间与 Ablation 新 runtime 时间，分别记录，不强行声称 runtime 预算相同。

## 6. 当前已知问题

1. **当前 canonical key 过粗。** 只使用 target、kind、action，可能合并不同调用链位置和不同故障强度。
2. **novelty 判定与最终 dedup 规则不一致。** 当前 novelty 还观察 call-chain position 和 motifs，但 canonical selection 没有使用它们。
3. **Full 当前保留第一条，而不是最高置信度条目。** 这会影响高置信度抽样。
4. **Ablation 原始输出没有统一结构。** 需要离线归一化 action 别名、kind、target 和调用链位置，但不能把分类和置信度注入 Ablation 的 prompt。
5. **不同阶段候选数量不一致。** `608/543`、`460/498`、`86/89` 属于 discovery、runtime-ready 和 canonical 不同阶段，最终报告必须逐层说明。
6. **当前 Full runtime 证据不是 86 个 canonical mutation 全部完成。** 必须按实际 completed report 统计，不能按计划数量统计。
7. **两个被 gate 阻断的大类不能进入 runtime 弱点率分母。** 只能报告为静态发现或平台阻断。
8. **当前 4 份 Ablation stratified pilot 不应混入新 Ablation 结果。** 它们的生成协议已经使用了分类缩减选择。

## 7. 请求 GLM 5.3 重点审阅

请重点判断：

1. 用 Full discovery wall-clock 作为 Ablation 的最大停止时间，是否比匹配 LLM 调用次数或 token 数更合理？
2. `fault_family_key` 是否应包含 `call_chain_position`？哪些参数必须进入 `mutation_instance_key`？
3. Full 重复项保留最高置信度，Ablation 重复项保留首次代表，是否会造成选择偏差？
4. 用 Full 的高置信度独有样本对比 Ablation-only 的固定种子随机等数量样本，是否能支持“置信度机制有效”的结论？
5. `family-overlap` 与 `strict-overlap` 是否应该分别作为主分析和敏感性分析？
6. Ablation 的随机样本是否需要做事后分布报告，或者还需要额外的 post-hoc matched-strata 敏感性分析？
7. 现有 76 份 Full completed reports 是否足以支撑该设计；哪些样本缺失会导致选择偏差？
8. 稳定弱点率、一次性结果和平台 gate 失败应如何分别进入分母和置信区间？
9. 当前方案是否有知识污染、runtime 结果反哺、选择后调样本或重复计数风险？
10. 请指出任何会导致实验结论不能成立的致命问题，并给出必须在 runtime 前完成的修复清单。

## 8. 执行门槛

在 GLM 审阅通过前，不开始新一轮正式 Ablation runtime。

通过后按以下顺序执行：

1. 完成 old-key/new-key 离线审计；
2. 冻结 Full/Ablation 去重和 overlap/full-only/ablation-only 清单；
3. 重新生成无分类、无置信度的 Ablation discovery；
4. 生成并哈希 selection manifest；
5. 对所有选中 mutation 做 server-side dry-run；
6. 只运行 Ablation 缺失的报告，Full 不重复；
7. 每轮确认恢复、删除、全局无残留和 washout；
8. 生成 pending human-review 报告，不更新知识库；
9. 最后再决定是否有必要投入时间跑完整 86/89 canonical 全量批次。

## 9. 实验边界

- 只操作 `chaosatlas-sock-shop` namespace。
- 不修改 Docker、Minikube 或 Chaos Mesh。
- 不读取或输出任何 API key、GitHub token 或其他凭据。
- 不重新运行已经完成的 Full 报告。
- 不把 pending 审核结果写回知识库。
- 不覆盖已有实验目录；每次续跑使用新的 r 后缀目录。
- 任何一次 baseline、恢复、cleanup 或全局残留检查失败，均不计为真实弱点结果。
