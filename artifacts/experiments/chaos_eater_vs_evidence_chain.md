# ChaosEater analysis vs 我们的证据链根因：真实数据对照

> 日期：2026-08-09
> 方法：提取 ChaosEater `AnalysisAgent`（commit 47c4e44）的 SYS/USER prompt + AnalysisReport schema，喂入**我们的真实实验数据**（同 LLM deepseek-v4-flash），对比它产出的分析 vs 我们的证据链根因。
> 样本：14 个已确认弱点的候选（来自 20 池 + 前瞻）。

## 一、核心发现

**ChaosEater 的 analysis 能"描述现象"（step-by-step、引用日志强），但不能"判定弱点"——它把"实验断言通过/失败"当成目标，而不是"发现弱点"。**

| 候选 | ChaosEater analysis 结论 | 我们的证据链根因 |
|---|---|---|
| OB-PAYMENT-DELAY-2000 | ❌ **"no failed unittests → 注入未造成 client 可见错误"**（漏判） | missing_timeout_on_downstream_call（2s 注入 1:1 放大到 2021ms 无超时） |
| OTEL-EMAIL-DELAY-2000 | ❌ **"supports hypothesis: finite email latency does not block order path indefinitely"**（**误判**） | missing_isolation_on_non_critical_side_effect（email 2s → PlaceOrder 4.9-5.3s 串行阻塞） |
| OB-CART-DELAY-2000 | ❌ "failed... failure signature consistent"（只描述不归因） | missing_timeout_on_cart_read_in_checkout_flow |
| TT-STATION-DELAY-2000 | ✅ **识别出 2× 放大 + no_timeout 契约 + resilience concern**（分析最好的一例） | latency_amplification（一致） |
| OB-PAYMENT-LOSS-100 | ⚠️ 描述 10s DEADLINE_EXCEEDED 但无根因结论 | missing_timeout_on_downstream_call |

## 二、为什么它漏判（根因，可写论文）

1. **世界观不同**：ChaosEater 的 experiment_result 是 `Passed/Failed unittests`——它判断"实验是否验证了假设"，不是"系统是否有弱点"。所以"延迟放大但返回 OK"的 case，它判为"实验通过"，永远不识别为弱点。
2. **没有判定经验层**：我们独有的 JE-COUPLING-001（旁路耦合 = 高价值弱点）让 OTEL-EMAIL-DELAY 被识别；ChaosEater 没有这条规则，把"最终返回 OK"当成"不阻塞"——**误判了最严重的耦合弱点**。
3. **输出形态**：它是自由文本 report，无法直接用于"哪个候选需要修复"的决策；我们是结构化 root_cause + 源码行（可提交 issue、可进知识库）。

## 三、必须诚实的亮点

- **TT-STATION-DELAY-2000** 它分析对了（2× 放大、no_timeout、resilience concern）——说明它不全是差的，描述能力在"明显失败"的 case 上可靠。
- 14 个里 **4 个误判为"实验通过"**（OB-PAYMENT-DELAY / OTEL-EMAIL-DELAY / OB-PRODUCTCATALOG-DELAY-500 / OB-CART-DELAY / OTEL-CHECKOUT-DELAY / TT-ORDER——实际是 6 个被判通过），**0 个给出结构化根因标签**；**1 个（TT-STATION）分析质量接近我们**。

## 四、对老师结论（可验证性对比）

> "**把同一份真实实验数据交给 ChaosEater 的 analysis 阶段（完整框架的分析器）和我们自己的证据链，结果是：ChaosEater 能描述现象、但无法判定弱点——它对 6/14 的弱点漏判为'实验通过'，对 OTEL-EMAIL 耦合弱点明确误判，且 0/14 给出结构化根因；我们的证据链对全部 14 个给出源码锚定的根因（如 checkoutservice/main.go:369 无 WithTimeout），可直接转化为可提交的 issue。差异不在'谁会分析'，而在'谁的分析能验证、能锚定、能复用'——这来自我们的判定经验层（如 JE-COUPLING-001）和契约清单，而这两者 ChaosEater 没有。**"

## 五、产物

- `chaos_eater_analysis_results.json`：14 份 ChaosEater analysis（真实数据输入）
- `our_evidence_chain_root_causes.json`：14 个证据链根因（源码锚定）
- 本文件：对照分析
