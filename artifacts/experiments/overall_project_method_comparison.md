# 项目与方法总对比总结

> 时间范围：2026-08-07 至 2026-08-09
> 项目：Train Ticket、Online Boutique、OpenTelemetry Demo、Sock Shop
> 目的：统一说明测试项目、方法轴、测量轴、结果和结论边界。

## 1. 总体结论

本项目目前不能压缩成一个“谁的 U@K 更高”的总分。实验实际比较了三条正交轴：

1. **选择轴**：测哪个服务、调用边或故障候选。
2. **测量轴**：从服务端口、真实业务入口还是 Pod 可用性曲线观察影响。
3. **证据轴**：是否完成 baseline、注入确认、恢复、清理、根因定位和知识回流。

现有证据支持的总判断是：

- 选择器方面，M0、ChaosEater 风格 LLM、图方法和 decision engine 尚未被统计证明存在稳定优劣。
- 真实业务链路测量能发现直连端口测量看不到的代码级超时和防御行为。
- Ours 的主要增量在受控生命周期、结构化证据链、源码根因、知识资产化和跨测量层组合，而不是单纯的候选 Top-K 选择准确率。
- ChaosEater 官方流程已经在 Sock Shop 发现部署可用性问题；这与 Ours 发现的调用契约问题属于不同层次，不能合并成单一胜负。

## 2. 项目总表

| 项目 | 主要测试内容 | 主要测量方式 | 主要方法 | 代表性结果 | 证据定位 |
|---|---|---|---|---|---|
| Train Ticket | Station、Basic、Order 的 delay/loss/CPU 候选；timeout 边界 | 直连端口/HTTPChaos | M0、M1、M3/M4、A0-A4、decision engine | 选择方法无显著差异；TT-BASIC 曾出现预测偏差，后续被修正 | `comparison_full_summary.md`、`prospective_round1_result.md` |
| Online Boutique | payment、cart、checkout、currency、email、shipping、productcatalog；含 protected 边 | 直连 gRPC/NetworkChaos | M0、M1、图方法、decision engine、r2 三方法 pilot | 混合池中 decision engine 与 M1 均 5/6；r2 实际 OB 候选 8/8 为弱点，选择区分度饱和 | `mixed_pool_comparison.md`、`r2_head_to_head.md` |
| OpenTelemetry Demo | checkout、email、currency、shipping、cart、quote 等调用边 | 直连 HTTP/gRPC/NetworkChaos | M0、M1、M3/M4、CE AnalysisAgent、Ours evidence chain | 延迟放大、旁路耦合和无超时调用被证据链定位；r2 因集群无镜像未执行 | `chaos_eater_vs_evidence_chain.md`、`comparison_full_summary.md` |
| Sock Shop | orders 真实下单链路；payment/shipping/carts 等边；服务级 Pod kill | 真实业务链路 + availability Ready-pod 采样 | decision engine、M1、M0、Ours full、ChaosEater 官方部署 | 真实链路修正直连误判；decision engine 4/4 命中并跳过 2 个 protected 候选；CE 找到 front-end 单副本可用性问题 | `chaos_eater_deployed_vs_ours.md`、`unified_experiments_summary.md` |

## 3. 方法轴总表

| 方法 | 输入/信息层 | 实际职责 | 已有证据 | 结论边界 |
|---|---|---|---|---|
| M0 Random | I0、无知识 | 随机候选基线 | 作为浪费率和随机期望基线 | 不是竞争方法 |
| M1 ChaosEater 风格 adapter | I0、LLM 常识 | 生成候选排序 | 未知候选扩展中 5/5 验证为弱点；r1 为 3/4 | 单次/小样本，不能代表官方 CE 全系统 |
| M3/M4 Graph | I0 + 全局/局部图 | 按图和静态风险排序 | 已知池中稳定但未显著领先；对 score-0 扩展存在盲区 | 选择器，不是完整流水线 |
| A0-A4 消融 | 逐步加入图、runtime gate、evidence、feedback | 分解 Ours 组件贡献 | 说明 score、gate、evidence 各层的作用 | 不能替代跨项目主实验 |
| decision engine | 契约清单、SE/DP/JE、硬过滤 | 无 LLM 的知识驱动选择 | Sock r1 4/4 命中、2/2 正确 skip | 属于知识闭环验证，样本仍小 |
| Ours-full | 选择 + 注入 + 生命周期 + 判定 + RCA + 知识回流 | 完整方法流水线 | 83 次既有台账、源码根因、证据链、真实链路和可用性双轨 | 目前没有被证明总体优于 CE |
| ChaosEater official | manifests、steady states、fault agents、analysis、improvement | 官方完整 cycle | Sock Shop 发现 front-end availableReplicas 91.11% < 99% | 关注部署可用性，不等于调用契约测试 |
| ChaosEater AnalysisAgent | 实验结果文本 | 解释实验现象 | 14 个 ours 生成数据中约 6 个漏判，0 个结构化根因 | 输入和真值由 Ours 生成，属于输出形态对照 |

`FastFI` 因任务和故障域不对齐，不能进入这张主比较表；应单独标记为 out-of-domain。

## 4. 测量轴总表

| 测量方式 | 能回答的问题 | 主要优点 | 系统性盲区 |
|---|---|---|---|
| Direct | 某服务端口在网络故障下是否报错或变慢 | 便宜、易批量执行 | 看不到部分业务代码级 timeout/fallback；可能把直连超时误当成系统弱点 |
| Real-chain | 用户业务入口是否最终成功、是否跨服务放大 | 能观察 Future.get、业务 deadline、状态和级联 | 前置数据构造复杂，成本高 |
| Availability | Pod kill 后副本、Ready、PDB、自愈是否满足目标 | 能观察部署冗余和恢复 | Pod 活着不代表业务调用健康 |

Sock Shop 的同一故障已经显示：直连可得到约 12s 挂死，而真实业务入口在 5s `Future.get` 处返回受控错误。这个差异属于测量层结论，不应归因给某个选择器。

## 5. 关键定量结果

| 结果 | 数值 | 正确解释 |
|---|---:|---|
| B1 20 候选池 | M1 约 0.658；bootstrap CI 全跨 0 | 未证明选择器优越 |
| 前瞻 r1 | Ours 2/4，M1 3/4 | M1 略高但样本不足 |
| M1 扩展候选 | 5/5 验证为真实弱点 | CE 风格探索能提供有效方向；验证和 RCA 由 Ours 完成 |
| P4 decision engine | 4/4 命中，2/2 正确 skip | 知识资产在已知闭环中的收益 |
| Sock real-chain | decision engine 4/4；M0 随机约 49% 浪费 | 真实链路下知识硬过滤有价值，但样本小 |
| CE official Sock cycle | front-end availableReplicas 约 91.11% < 99% | CE 在部署可用性层发现真实问题 |
| 既有台账 | 83 次 lifecycle-complete（历史，TT/OB/OTEL） | 见 `archive/run_ledger_master.json`（已与 r2 24 合并为 107 记录，分开计数不混为一个数） |
| r2 新尝试 | 24 次；7 次基线无效（checkout 重启） | r2 为 **partial pilot（仅 OB）**：OTEL 4 + TT 1 候选 environment_blocked；17 有效观测（8 首跑 + 9 确认）；U@8 6 vs 6 vs 5 非 superiority |

## 6. Ours 与 ChaosEater 的正确总对比

| 层次 | Ours | ChaosEater | 当前判断 |
|---|---|---|---|
| 候选选择 | 契约、图、经验和 LLM 探索 | hypothesis/fault scenario LLM | 未证明谁总体更准 |
| 调用契约 | 真实业务链路、timeout、延迟放大、旁路耦合 | 默认 steady state 不检测 HTTP 语义 | Ours 在该层有明显增量 |
| 部署可用性 | 已用 availability 轨道独立复现 | 官方 cycle 原生覆盖 | 两者可达到一致结论，CE 先展示该能力 |
| 证据链 | baseline、注入、恢复、清理、RCA、源码行、知识卡 | 以 AnalysisReport 自由文本为主 | Ours 更适配审计和后续修复 |
| 改进闭环 | 可形成 issue、根因和知识回流 | 官方可生成 improvement，但本次重部署未闭环 | Ours 的闭环证据更完整，但缺少外部 issue 确认 |
| 泛化 | 四个系统都有实验，但 head-to-head 不完整 | 官方 Sock Shop cycle | 尚不能声称跨项目全面优于 |

## 7. 必须保留的实验边界

1. 四个项目都做过实验，但 r2 三方法 head-to-head 实际只执行了 Online Boutique（OTEL 4 + TT 1 候选 environment_blocked，见 `archive/candidate_pool_registry.json`）。
2. Sock Shop 的 CE 官方 cycle 与 Ours 契约层测试不是同一故障域，不能直接合并成一个胜负分。
3. CE AnalysisAgent 对照使用了 Ours 生成的真实实验数据和根因标签，存在自证循环风险。
4. r2 的 OTEL/TT 候选未部署，且 OB 执行池 8/8 全为弱点，存在环境截断和 **ceiling/saturation effect**（非 floor effect：全 weakness 池使选择区分度饱和于上限）。
5. “83 次”（历史）与“r2 24 次”分开计数：master 台账 107 记录 = 91 独立注入 + 9 确认 + 7 无效基线；67 个派生/预测/汇总文件明确不计入独立实验。r2 的 U@8 = 6 vs 6 vs 5 **不得写成全面 superiority**（样本 8，无统计显著，且仅 OB）。
6. **ChaosEater-adapter ≠ ChaosEater official**：前者是本项目 LLM 盲排序（经我们 OpenAI-compat adapter），后者是官方完整部署 cycle（commit 47c4e44）；两者在 `archive/method_registry_archive.json` 分开记录，任何声称不得混称。

## 8. 可直接写入论文的结论

> 我们在 Train Ticket、Online Boutique、OpenTelemetry Demo 和 Sock Shop 四个微服务系统上，分别考察了候选选择、真实业务链路测量和部署可用性测量。实验未证明任一候选选择器在一般同质候选池上具有统计显著优势；主要差异来自测量位置和证据资产化。真实业务链路能够暴露直连端口测量不可见的代码级超时与耦合防御，availability 轨道能够覆盖副本冗余和 Pod 自愈问题。ChaosEater 在部署可用性层发现了真实单副本弱点，而 Ours 在调用契约、结构化证据、源码根因和知识回流方面提供了额外覆盖。因此，两者更准确的关系是“部署可用性互补 + 调用契约增量”，而不是已经被统一实验全面证明的胜负关系。
