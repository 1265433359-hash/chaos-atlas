# ChaosAtlas 项目阶段总览归档

归档日期：2026-08-14  
分支：`remediation/2026-08-09-review`  
最近本地证据提交：`bbfb5c4`  
推送状态：pending，需要用户显式授权后才能推送包含原始实验日志、拓扑/业务证据和 DeepSeek 选择记录的 payload。  
审核状态：`human_review=pending`  
知识库更新：`false`

本文是当前阶段的项目级总览，面向论文写作、后续实验设计和新会话交接。它不替代单次运行报告、原始日志、冻结候选池或人工 RCA。

## 1. 当前阶段一句话结论

ChaosAtlas 已经从“十项目探索和 P02/P09/P08 等项目验证”转入“三个真实微服务项目上的方法能力复盘”。当前最稳的结论是：

> ChaosAtlas 完整方法具备真实弱点发现能力，并在 OpenTelemetry Demo 上表现出高上限；在同候选池控制下，完整方法相对 ablation 的主要优势是候选选择更精准、无效实验更少，而不是在所有项目上发现更多弱点。

## 2. 证据等级标记

- `[CONFIRMED]`：runtime 证据闭环成立，包含 baseline、注入、业务观测、恢复、cleanup、washout 和 SHA。
- `[PENDING]`：人工根因审核未完成，不进入知识库。
- `[BOUNDARY]`：证据只能支持有界结论。
- `[DO-NOT-CLAIM]`：当前材料不能支持的说法。

## 3. 方法范围

当前主动比较方法：

| 方法 | 状态 | 说明 |
|---|---|---|
| `native-full` | active evidence | 原始项目完整能力，上限测试，允许使用项目完整知识 |
| `ChaosAtlas-full` | active evidence | 同候选池/冻结输入下的完整方法 |
| `ChaosAtlas-ablation` | active evidence | 去掉知识视图的消融方法 |
| `ChaosEater-adapter` | auxiliary | 同候选池里有 adapter 对照，但不能冒充官方完整 ChaosEater |
| `ChaosEater-full` | paused/blocked | 官方完整 ChaosEater 尚未形成本机可公平运行证据 |

[DO-NOT-CLAIM] 当前不能写“ChaosEater-full 已完成三项目正式对比”。

## 4. 三真实项目核心结果

详细归档见 `docs/CHAOSATLAS_REAL_PROJECT_REVIEW_2026-08-14.md`。

### 4.1 原始项目完整能力

统计口径：同一个 mutation YAML 至少 2 次 completed replicate 都观测到业务失败，才算一个稳定真实弱点。

| 项目 | native-full 稳定弱点 | ablation 稳定弱点 | 解释 |
|---|---:|---:|---|
| Online Boutique | 2 | 3 | ablation 更直接命中 checkout/cart 路径 |
| OpenTelemetry Demo | 4 | 2 | native-full 高上限，24/24 业务弱点复现实例来自这里 |
| Sock Shop | 4 | 4 | 两者稳定弱点数量打平 |
| 总计 | 10 | 9 | native-full 略多，但优势不稳定 |

[CONFIRMED] 扩展结果矩阵：

| 方法 | 候选数 | 稳定真实弱点 | 不稳定/重复不了 | 非弱点/未发现 |
|---|---:|---:|---:|---:|
| native-full | 20 | 10 | 0 | 10 |
| ChaosAtlas-ablation | 20 | 9 | 2 | 9 |

[CONFIRMED] native-full 在三项目中确认 10 个稳定真实弱点，ablation 确认 9 个。  
[CONFIRMED] native-full 没有不稳定候选；ablation 有 2 个 Sock Shop 不稳定候选。  
[BOUNDARY] OTel 的 24/24 是 24 次复现实例，对应 4 个唯一稳定弱点，不是 24 个不同弱点。

### 4.2 同候选池选择能力

统计口径：冻结候选池不含旧 runtime 结果、RCA 或人工标签；方法只从同一批候选里选择。

| 方法 | 选中唯一候选 | 选中稳定弱点 | 无效候选 | 命中率 |
|---|---:|---:|---:|---:|
| ChaosAtlas-full | 15 | 12 | 3 | 80.0% |
| ChaosAtlas-ablation | 17 | 12 | 5 | 70.6% |
| ChaosEater-adapter | 15 | 11 | 4 | 73.3% |

[CONFIRMED] 同候选池扩展矩阵：

| 方法 | 选中候选 | 稳定真实弱点 | 不稳定/重复不了 | 非弱点/未发现 |
|---|---:|---:|---:|---:|
| ChaosAtlas-full | 15 | 12 | 0 | 3 |
| ChaosAtlas-ablation | 17 | 12 | 0 | 5 |

[CONFIRMED] 同候选池中 full 和 ablation 都选中 12 个稳定真实弱点。  
[CONFIRMED] full 用更少无效候选达到同等真实弱点数量。  
[BOUNDARY] full 的当前优势应写为“选择精度更高”，不能写为“同候选池中发现更多真实弱点”。

## 5. 已确认的真实弱点类型

### Online Boutique

[CONFIRMED] checkout/cart 关键路径对 PodKill 和网络延迟敏感。  
同候选池确认点包括：

- `cartservice network_delay`
- `cartservice pod_kill`
- `checkoutservice network_delay`
- `checkoutservice pod_kill`

主要外部现象：gRPC `UNAVAILABLE`、`DEADLINE_EXCEEDED`、cart failure。

### OpenTelemetry Demo

[CONFIRMED] checkout/cart 是主要真实弱点集中区。  
同候选池确认点包括：

- `cart network_delay`
- `cart pod_kill`
- `checkout network_delay`
- `checkout network_loss`
- `checkout pod_kill`

主要外部现象：gRPC deadline、unavailable、checkout 路径失败。  
[BOUNDARY] `payment network_delay` 在同候选池中 0/2，没有业务影响。

### Sock Shop

[CONFIRMED] catalogue 和 user 路径是当前 oracle 下稳定弱点。  
同候选池确认点包括：

- `catalogue network_delay`
- `catalogue pod_kill`
- `user network_delay`
- `user pod_kill`

主要外部现象：catalogue HTTP 500/timeout，login 401/timeout，orders 500。  
[BOUNDARY] `front-end pod_kill`、`orders` 故障和 `carts network_delay` 在同候选池中未稳定打出业务弱点。

## 6. 十项目线索和平台状态

### P02

[CONFIRMED] R3 已完成 15/15。api-gateway PodKill 业务失败 9/9，discovery-server PodKill 后延迟 HTTP 500 6/6。  
[PENDING] discovery-server 根因审核仍需保持 pending，不能自动写入知识库。

### P09

[CONFIRMED] 已完成健康端点级两臂运行，生命周期、cleanup、washout 均通过。  
[BOUNDARY] 当前 oracle 是 `/health`，支持有界中断/恢复和连接症状，不支持完整业务弱点或方法优越性。

### P08

[BOUNDARY] 历史材料存在，但正式双实验和业务 oracle 可信度仍需单独 gate；不能把健康端点级结果扩大为业务弱点。

### P03 / P06

[BOUNDARY] 当前可确认的是静态 profile 和运行准备推进过；进入正式 runtime 前仍需 namespace、server-side dry-run、baseline、oracle 和残留 gate。

## 7. 证据链和工程产出

[CONFIRMED] 当前阶段新增或强化了以下能力：

- 三真实项目 native-full 输入与运行证据。
- 同候选池冻结、方法输入、DeepSeek 选择、runtime plan 和批量运行器。
- Windows Python 运行时依赖修复：补齐 `grpcio/protobuf`，用于 gRPC 业务 oracle。
- 同候选池 runtime 批处理器：`tools/run_same_pool_runtime_batch.py`。
- OTel runner 白名单修复，允许冻结 OTel app set。
- 审核文档：`artifacts/experiments/chaosatlas_same_pool_fair_2026-08-14-r3/reports/runtime-fair-comparison-review.md`。
- 项目级复盘：`docs/CHAOSATLAS_REAL_PROJECT_REVIEW_2026-08-14.md`。

## 8. 当前不能写入论文的结论

[DO-NOT-CLAIM] 不能声称完整方法在三个项目上全面碾压 ablation。  
[DO-NOT-CLAIM] 不能把 OTel 的 24/24 解释成 24 个不同弱点。  
[DO-NOT-CLAIM] 不能说同候选池 full 发现的真实弱点数量超过 ablation；二者都是 12 个。  
[DO-NOT-CLAIM] 不能声称业务弱点的具体根因是缓存、注册中心、服务发现、重试机制或某个内部机制。  
[DO-NOT-CLAIM] 不能把 ChaosEater-adapter 当官方完整 ChaosEater。

## 9. 论文叙事建议

建议把实验叙事拆成三层：

1. 真实发现能力：native-full 在真实项目上能确认稳定弱点，OTel 上体现高上限。
2. 消融对比：ablation 是强基线，说明仅靠拓扑和业务入口也能命中明显弱点。
3. 控制候选后的选择质量：同候选池证明 full 更少选择无效候选，知识提高了选择精度。

推荐主结论：

> ChaosAtlas 的知识增强不是简单增加所有项目上的弱点数量，而是帮助方法在候选选择阶段减少无效实验；端到端候选生成和知识投影仍是下一阶段需要改进的关键。

数据关系：

- Online Boutique 关键路径明显，ablation 在原始能力和同候选池中都能追上甚至超过 full。
- OpenTelemetry Demo 是 native-full 的高上限证据，4 个唯一弱点带来 24/24 业务弱点复现实例。
- Sock Shop 暴露选择质量差异：同候选池中 full 的非弱点候选为 2，ablation 为 4。
- 原始 full 的问题主要是候选生成浪费；同候选池中的 full 说明知识本身能减少无效选择。

## 10. 下一阶段任务

1. 改进 full 的候选生成，让项目知识直接约束候选池，而不仅用于排序。
2. 为已确认弱点补 RCA：日志、trace、代码路径和配置证据必须能闭环。
3. 对 P03/P06/P08 继续执行 gate，只有业务 oracle 和 server-side dry-run 通过后再进入 runtime。
4. 保持所有新结论 `human_review=pending`，人工审核前不得写入知识库。
5. 推送 `bbfb5c4` 及后续文档提交前，需要用户明确授权包含实验日志和模型选择记录的 payload 出境。

## 11. 阶段归档结论

[CONFIRMED] 当前阶段已经形成可复核的真实项目证据链：原始项目完整能力证明方法有真实发现能力，同候选池实验证明知识增强提高选择精度。  
[PENDING] 端到端 full 仍需改进候选生成和知识投影，根因解释仍需人工 RCA。  
[BOUNDARY] 当前最稳妥的论文表达是“full 更精准、更少无效实验”，不是“full 全面发现更多弱点”。
