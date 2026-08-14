# ChaosAtlas 三真实项目阶段复盘归档

归档日期：2026-08-14  
分支：`remediation/2026-08-09-review`  
本地证据提交：`bbfb5c4`  
推送状态：pending，需要显式授权推送包含原始实验日志、拓扑/业务证据和 DeepSeek 选择记录的 payload。  
审核状态：`human_review=pending`  
知识库更新：`false`

本文归档 Online Boutique、OpenTelemetry Demo、Sock Shop 三个真实项目上的当前阶段结果。它区分两类能力：

1. 原始项目完整能力：`native-full` 与 `ChaosAtlas-ablation` 各自按自己的流程理解项目、生成候选、选择故障并注入。
2. 同候选池选择能力：`ChaosAtlas-full` 与 `ChaosAtlas-ablation` 面对同一冻结候选池，只比较候选选择质量。

## 标记约定

- `[CONFIRMED]`：有 runtime 报告、baseline、注入、业务观测、恢复、cleanup、washout 和 SHA 证据支持。
- `[PENDING]`：人工根因审核未完成，不能进入知识库。
- `[BOUNDARY]`：证据边界，说明可以说到哪里。
- `[DO-NOT-CLAIM]`：当前证据不能支持的结论。

## 证据入口

### 原始项目完整能力

- Sock Shop native-full：`artifacts/experiments/chaosatlas_native_full_2026-08-14-r1`
- Online Boutique native-full：`artifacts/experiments/chaosatlas_native_full_2026-08-14-r4/online-boutique/runtime-results-r2`
- OpenTelemetry Demo native-full：`artifacts/experiments/chaosatlas_native_full_2026-08-14-r4/opentelemetry-demo/runtime-results-r2`
- Online Boutique ablation：`artifacts/experiments/chaosatlas_two_arm_real_projects_2026-08-13-r4/runtime_results/online-boutique/formal-r4-runtime-r4`
- OpenTelemetry Demo ablation：`artifacts/experiments/chaosatlas_two_arm_real_projects_2026-08-14-otel/runtime_results-r3`
- Sock Shop ablation：`artifacts/experiments/chaosatlas_two_arm_real_projects_2026-08-14-sock-shop/runtime_results-r3` and `runtime_results-r4`

### 同候选池选择能力

- 冻结批次：`artifacts/experiments/chaosatlas_same_pool_fair_2026-08-14-r3`
- 有效 runtime：`artifacts/experiments/chaosatlas_same_pool_fair_2026-08-14-r3/runtime_results-r2`
- 审核报告：`artifacts/experiments/chaosatlas_same_pool_fair_2026-08-14-r3/reports/runtime-fair-comparison-review.md`

## 复现弱点统计口径

[CONFIRMED] 本文把“真实可复现弱点”定义为同一个 mutation YAML 至少 2 次 completed replicate 都观测到业务失败。单次 `weakness_observed`、失败重跑、mixed 结果不计入稳定弱点数。

[BOUNDARY] `weakness_observed` 是业务 oracle 层面的现象确认，不等于内部根因确认。Zipkin/trace 后端在同候选池 OTel 和 Sock Shop 运行中不可用，因此不能用这些运行声称具体调用链根因。

## 原始项目完整能力结果

这组实验衡量端到端能力：方法需要自己完成项目理解、候选生成、候选选择和真实注入。

| 项目 | native-full 稳定弱点 | ablation 稳定弱点 | 结论 |
|---|---:|---:|---|
| Online Boutique | 2 | 3 | ablation 多 1 个 |
| OpenTelemetry Demo | 4 | 2 | native-full 多 2 个 |
| Sock Shop | 4 | 4 | 打平 |
| 总计 | 10 | 9 | native-full 略多 |

runtime 复现实例数：

| 方法 | 业务弱点复现实例 |
|---|---:|
| native-full | 36 |
| ChaosAtlas-ablation | 32 |

[CONFIRMED] OpenTelemetry Demo 是 native-full 的最强证据点：4 个唯一弱点、24 次业务弱点复现实例，即之前讨论的 `24/24`。  
[BOUNDARY] 这个 `24/24` 不是 24 个不同弱点，而是 4 个唯一故障多次复现。  
[CONFIRMED] Online Boutique 和 Sock Shop 上 native-full 没有稳定压过 ablation。  
[PENDING] 这说明端到端完整流程仍受候选生成、知识投影和排序策略影响。

## 同候选池选择能力结果

这组实验固定候选池，排除“谁出题更容易”的影响，只比较“谁更会从同一批候选里选真实弱点”。

候选池中被验证出的真实可复现弱点：

| 项目 | 候选池稳定弱点 |
|---|---:|
| Online Boutique | 4 |
| OpenTelemetry Demo | 5 |
| Sock Shop | 4 |
| 总计 | 13 |

方法选择结果：

| 方法 | 选中唯一候选 | 选中稳定弱点 | 无效候选 | 命中率 |
|---|---:|---:|---:|---:|
| ChaosAtlas-full | 15 | 12 | 3 | 80.0% |
| ChaosAtlas-ablation | 17 | 12 | 5 | 70.6% |

分项目：

| 项目 | ChaosAtlas-full | ChaosAtlas-ablation | 结论 |
|---|---:|---:|---|
| Online Boutique | 4/4 | 4/4 | 打平 |
| OpenTelemetry Demo | 4/5 | 5/6 | ablation 多选中 1 个真实弱点，但也多选无效候选 |
| Sock Shop | 4/6 | 3/7 | full 更稳，少选假阳性 |
| 总计 | 12/15 | 12/17 | 真实弱点数量打平，full 命中率更高 |

[CONFIRMED] 同候选池中 full 和 ablation 都选中 12 个稳定真实弱点。  
[CONFIRMED] full 用更少候选达到同样真实弱点数量，说明它的优势主要体现在选择效率和减少无效实验。  
[BOUNDARY] 这不是“full 发现的真实弱点绝对数量更多”，而是“full 的选择精度更高”。

## 当前可写结论

[CONFIRMED] 原始项目完整能力中，native-full 发现 10 个稳定真实弱点，ablation 发现 9 个，native-full 略高但优势不稳定。  
[CONFIRMED] native-full 在 OpenTelemetry Demo 上表现出明显高上限，达到 24/24 业务弱点复现实例。  
[CONFIRMED] 同候选池选择能力中，full 和 ablation 都选中 12 个稳定真实弱点，但 full 的无效候选更少，命中率 80.0% 高于 ablation 的 70.6%。  
[CONFIRMED] full 的当前稳定优势更适合表述为“提高候选选择精度、减少无效实验”，而不是“在所有项目上发现更多弱点”。

## 当前不能写的结论

[DO-NOT-CLAIM] 不能声称 native-full 在三个项目上全面碾压 ablation。  
[DO-NOT-CLAIM] 不能把 OTel 的 24/24 写成 24 个不同弱点。  
[DO-NOT-CLAIM] 不能声称同候选池中 full 发现的真实弱点数量超过 ablation；二者都是 12 个。  
[DO-NOT-CLAIM] 不能声称具体根因是缓存、注册中心、服务发现、重试机制或某个内部机制，除非后续人工 RCA 补充直接证据。  
[DO-NOT-CLAIM] 不能把 `ChaosEater-adapter` 冒充官方完整 ChaosEater。

## 问题与解释

### 为什么原始项目完整能力不稳定

[PENDING] 当前证据显示，知识本身不是无效；问题更可能出在端到端链路：

- 项目知识投影可能没有精确对齐当前业务 oracle。
- 候选生成可能太散，选入了理论上重要但实验下不敏感的点。
- 某些项目关键路径过于明显，ablation 靠拓扑和业务入口常识也能命中。
- Sock Shop 这类项目存在明显假阳性点，例如 front-end、orders 或 carts 在当前 oracle 下不一定能稳定打坏业务。

### 为什么同候选池里 full 更值得保留

[CONFIRMED] 当候选池固定后，full 没有增加真实弱点总数，但减少了无效候选。  
[BOUNDARY] 这说明 full 的知识价值目前主要体现为选择过滤，而不是端到端候选生成已经完全成熟。

## 后续建议

1. 把论文主表拆成两个层次：端到端真实能力表、同候选池选择效率表。
2. 在文字中明确区分“复现实例数”和“唯一稳定弱点数”。
3. 保留 `human_review=pending`，不要把这些运行自动写入知识库。
4. 下一阶段优先改进 full 的候选生成/知识投影，再复跑端到端能力，而不是只重复同候选池选择。
5. 如果要报告具体根因，需要为已确认弱点补充 RCA：服务日志、trace 后端、请求链路和代码/配置证据。

## 一句话归档结论

[CONFIRMED] ChaosAtlas native-full 已在三个真实项目上确认 10 个稳定真实弱点，ablation 确认 9 个；同候选池中 full 和 ablation 都选中 12 个稳定真实弱点，但 full 以更少无效候选达到同等发现数量。当前最稳妥的结论是：完整方法具备真实弱点发现能力，知识增强提高了候选选择精度，但端到端候选生成和知识投影仍需改进。
