# Sock Shop YAML 分类置信假设生成对比实验设计

**状态：** design-review  
**日期：** 2026-08-14  
**实验对象：** Sock Shop  
**对比方法：** `native-full` vs `ChaosAtlas-ablation`  
**核心口径：** 方法本体不改；改变的是假设生成条件。两个方法都在“真实 YAML 五大类 + 类内特征相关性 + Beta 置信区间停止”条件下独立生成假设，生成到停止后各自完整运行实验。两个方法不限制相同 runtime 预算，耗时是结果指标。

## 1. 目标

本实验要回答：

1. 在真实 YAML 分类置信条件下，`native-full` 和 `ChaosAtlas-ablation` 谁能在 Sock Shop 上发现更多稳定真实弱点。
2. 谁生成的候选更准，非弱点和不稳定候选更少。
3. 谁完成从假设生成到 runtime 验证的总耗时更短。
4. 谁的单位时间收益更高，即稳定真实弱点数 / 总小时数。

## 2. 真实 YAML 五大类

仓库 `raw_yaml/` 当前共有 1935 个真实 YAML。第一版只纳入覆盖主体分布的五个大类，共 1506 个，占 77.8%。

| 大类 | 包含类型 | 数量 | 占比 | 第一版用途 |
|---|---|---:|---:|---|
| Pod disruption | PodChaos | 341 | 17.6% | runtime 必测 |
| Network degradation | NetworkChaos | 428 | 22.1% | runtime 必测，最高优先级 |
| Resource pressure | StressChaos | 352 | 18.2% | runtime 必测，但注意耗时 |
| Protocol/HTTP fault | HTTPChaos + DNSChaos | 263 | 13.6% | gate 通过后 runtime |
| Composite/scheduled fault | Workflow + Schedule | 122 | 6.3% | 第一版少量或静态，防止成本爆炸 |

不纳入第一版 runtime 的类型：IOChaos、TimeChaos、PhysicalMachineChaos、JVMChaos、KernelChaos、AWSChaos、GCPChaos、BlockChaos、AzureChaos。它们保留在后续扩展和静态候选分析中，不作为本轮 Sock Shop runtime 主体。

## 3. 类内特征

五大类内部不继续拆成大量小类，而是抽取特征并用于优先级、覆盖率和置信停止。

通用特征：

| 特征 | 含义 |
|---|---|
| `action_or_target` | 故障动作或目标，如 delay、loss、pod-kill、cpu、memory、response、abort |
| `mode` | Chaos Mesh 作用模式，如 one、all、fixed、fixed-percent |
| `selector_shape` | selector 形状，如 app label、multi-label、namespace-only、empty/high-risk |
| `duration_bucket` | 持续时间桶，如 short、medium、long |
| `intensity_bucket` | 强度桶，如 latency/loss/load/workers 的 low、medium、high |
| `scheduler_present` | 是否带 Schedule/Workflow 时序结构 |
| `target_role` | 映射到 Sock Shop 后的目标角色，如 entry、business-service、data-dependency、supporting-service |
| `call_chain_position` | 映射到业务链路中的位置，如入口层、核心服务、数据库依赖、异步/支撑路径 |

## 4. 特征相关性如何使用

特征相关性不等于置信区间本身，而是置信区间参数的来源。

它影响两件事：

1. **停止阈值 `tau_c`。** 高频且强相关的大类更值得探索，`tau_c` 更小，停止更难。低频或高成本大类 `tau_c` 更大，停止更早。
2. **novel 判定。** 如果一个假设首次覆盖真实 YAML 中的强相关特征组合，例如 `NetworkChaos.delay + mode=one + app selector`，它更应该被记为新增有效信息。

第一版相关性计算只做轻量统计：

| 统计 | 用途 |
|---|---|
| support | 该特征或组合出现次数 |
| entropy | 类内多样性，越高说明不能太早停 |
| pairwise lift | 判断两个特征是否显著共现 |
| top motifs | 每类最主要的高频/强相关特征组合 |

强相关组合定义：

```text
support >= class_count * 0.05
and lift >= 1.5
```

如果某类样本较少，允许保留 top-K motifs，但不因为低频组合扩展 runtime 类别。

## 5. 置信区间停止规则

每个大类维护一个变量：

```text
p_new_c = 在大类 c 下继续生成一个假设还能带来新增有效信息的概率
```

对每个大类维护：

```text
novel_count_c
duplicate_count_c
```

初始先验：

```text
p_new_c ~ Beta(1, 1)
```

每生成一个假设：

```text
如果 hypothesis 是新增有效信息:
    novel_count_c += 1
否则:
    duplicate_count_c += 1

p_new_c ~ Beta(1 + novel_count_c, 1 + duplicate_count_c)
```

停止条件：

```text
generated_c >= min_c
and feature_coverage_c >= coverage_target_c
and upper95(p_new_c) < tau_c
```

强制停止条件：

```text
generated_c == max_c
```

## 6. 新增有效信息 novel 判定

一个假设满足以下任一高价值条件，可记为 `novel=1`：

1. 覆盖新的 Sock Shop 服务目标。
2. 覆盖新的故障动作或故障子类型。
3. 覆盖新的参数强度桶。
4. 覆盖新的 selector/mode 作用范围。
5. 覆盖新的业务调用链位置。
6. 首次覆盖某个真实 YAML 高频/强相关 motif。

如果只是换一种说法，或与已有候选在服务、故障动作、参数范围、调用链位置和 motif 上高度相似，则记为 `novel=0`。

## 7. 第一版阈值

| 大类 | min 假设数 | max 假设数 | `tau_c` | 高频特征覆盖目标 |
|---|---:|---:|---:|---:|
| Network degradation | 4 | 8 | 0.05 | 80% |
| Resource pressure | 2 | 5 | 0.08 | 70% |
| Pod disruption | 3 | 6 | 0.08 | 75% |
| Protocol/HTTP fault | 1 | 4 | 0.10 | 60% |
| Composite/scheduled fault | 0 | 2 | 0.15 | 50% |

这些阈值用于第一版 Sock Shop 实验。后续可以根据运行结果调整，但本轮实验开始后不得临时改阈值。

## 8. 两个方法的输入边界

### native-full

允许使用：

- Sock Shop 部署事实；
- 服务拓扑；
- 业务 oracle；
- 完整项目知识；
- 知识库/历史经验；
- 调用链位置和故障适用规则。

### ChaosAtlas-ablation

允许使用：

- Sock Shop 当前部署事实；
- Kubernetes 服务/Pod/Deployment 信息；
- 业务入口和 oracle 描述；
- 真实 YAML 五大类统计和停止规则。

禁止使用：

- 知识库；
- 历史弱点经验；
- full 方法专用调用链知识；
- full projection 或 historical evidence projection。

## 9. 输出与计时

两个方法都必须输出：

| 文件 | 含义 |
|---|---|
| `hypotheses.json` | 生成的假设列表 |
| `confidence-trace.json` | 每类 Beta 更新、coverage、upper95 和停止原因 |
| `generation-summary.md` | 人类可读生成总结 |
| `mutation_manifest.json` | 编译后的 mutation 与 SHA |
| `gate_report.json` | 静态 gate、server-side dry-run、适用性 gate |
| `runtime_results/` | Sock Shop runtime 报告 |
| `method_timing.json` | generation、compile、gate、runtime、washout、summary 和 total wall-clock |

时间不是预算限制，而是结果指标。最终比较：

```text
total_wall_clock
generation_time
gate_time
runtime_time
stable_weaknesses_per_hour
```

## 10. Runtime 判定

稳定真实弱点：

```text
同一 mutation 至少 2 次 completed replicate 都观测到业务失败
```

其他分类：

| 分类 | 含义 |
|---|---|
| `stable_weakness` | 稳定真实弱点 |
| `unstable_or_nonrepeatable` | 至少一次失败，但不能稳定复现 |
| `no_business_impact` | completed 但无业务影响 |
| `gate_failed` | 编译/适用性 gate 未通过，不进入 runtime |
| `invalid_runtime` | baseline、注入、cleanup、washout 或报告证据不完整 |

每轮 runtime 必须保留 baseline、injection、business observation、diagnostics、recovery、cleanup、global residual scan 和 washout 证据。

## 11. 最终对比表

主表一：发现能力。

| 方法 | 生成假设 | 进入 runtime | 稳定弱点 | 不稳定 | 非弱点 | 命中率 |
|---|---:|---:|---:|---:|---:|---:|

主表二：时间效率。

| 方法 | 生成耗时 | gate 耗时 | runtime 耗时 | 总耗时 | 稳定弱点/小时 |
|---|---:|---:|---:|---:|---:|

主表三：大类贡献。

| 大类 | native-full 稳定弱点 | ablation 稳定弱点 | native-full 非弱点 | ablation 非弱点 | 解释 |
|---|---:|---:|---:|---:|---|

## 12. 证据边界

- 本实验比较的是同一假设生成条件下的方法真实能力，不是修改 native-full 方法本体。
- 不限制相同 runtime 预算；耗时是结果。
- 业务弱点不等于具体内部根因，根因需要单独 RCA。
- 保持 `human_review=pending`。
- 保持 `knowledge_base_updated=false`。
- 不把 pending 结果自动写入知识库。
- 不使用 `git add .` 上传未筛选 runtime 目录。
