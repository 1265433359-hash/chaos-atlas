# 前瞻对比结果（第一轮）：我们的方法 vs M1

> 日期：2026-08-09
> 设计：6 个未执行候选，两个方法各挑 top-4，选择后执行全部 6 个（双方对结局都未知，非循环）。唯一变量 = 我们的知识层（契约清单 + 判定经验）。
> **诚实结论：这一轮 M1 略优（8 vs 6）。必须如实报告，不粉饰。**

## 候选结局（6 个全部执行，r1）

| 候选 | 结局 | severity | 我们的方法 | M1 |
|---|---|---|---|---|
| OTEL-CURRENCY-LOSS-100 | 10s DEADLINE_EXCEEDED | 3 | ✅ 选 | ✅ 选 |
| OB-FRONTEND-CURRENCY-DELAY-2000 | client_timeout | 3 | ✅ 选 | ✅ 选 |
| OB-PRODUCTCATALOG-DELAY-2000 | 1:1 无放大（2023ms，3s timeout 保护） | below_threshold | ❌ 选错 | ❌ 选错 |
| OTEL-PRODUCTCATALOG-DELAY-2000 | 8.9s 放大（severity 2） | 2 | ❌ 没选 | ✅ **选对** |
| OTEL-SHIPPING-DELAY-2000 | INTERNAL 7s | 3 | ❌ 没选 | ❌ 没选（都漏） |
| TT-BASIC-DELAY-2000 | 1:1 无放大（2024ms） | below_threshold | ❌ **选错**（预测会放大） | ❌ 没选 |

## 计分（severity 加权，各挑 4）

| 方法 | 命中 | severity 加权 | 说明 |
|---|---|---|---|
| **我们的方法** | 2（curr-loss + ob-curr） | **6** | 分歧点 TT-BASIC 预测错 |
| **M1** | 3（curr-loss + ob-curr + otel-prodcat） | **8** | 分歧点 OTEL-PRODUCTCATALOG 选对 |
| 随机期望 | ~2.7 | — | 6 池 4 弱点，抽 4 期望 2.67 |

## 三个必须诚实解读的事实

1. **M1 的分歧点选择命中**：它选了 OTEL-PRODUCTCATALOG-DELAY-2000（8.9s 放大），我们没选。我们的分歧点 TT-BASIC-DELAY-2000 预测"无超时→放大"是**错的**——TT-BASIC 是单调用路径，1:1 传递不放大（和 TT-BASIC-500 一致）。

2. **知识层把 LLM 带偏了一次**：契约清单正确说了"TT basic 无超时"，但"无超时→自动放大"的推断对 basic 不成立（结构简单无扇出）。**这是知识层过度泛化**，是 A1 教训的复发（无超时 ≠ 自动弱点，要看结构）。

3. **双方都漏掉 OTEL-SHIPPING（severity 3）**：6 池里 4 个弱点，随机期望就 2.67——这个池太小，双方各 4 选，漏 1 个严重弱点说明**样本不足以下结论**。

## 这对"我们 vs 其它方法"意味着什么

- **这一轮不能宣称我们更优**——M1 略优且我们知识层带偏一次。
- **但也没有任何方法显著占优**：4 弱点池、各 4 选、差异 = 1 个候选（8 vs 6），无统计意义（B1 教训）。
- **可改进点（真实收获）**：知识层应作为**硬约束**而非软提示——契约清单明确"OB catalog 有 3s timeout 保护"，LLM 还是选了它（双方都选错）。如果知识层把"受保护候选"直接排除/降级（防御模式库 C2 的用法），我们会在 OB-PRODUCTCATALOG 上少浪费一个选择。
- **OTEL-SHIPPING 双方都漏**：这是可写成论文的点——LLM（盲或有知识）在"shipping 这类延迟→INTERNAL 错误"路径上都不敏感。

## 下一步建议

- 要得到有意义的胜负，需要**更大池（15-20 新候选）+ 多轮（3 轮以上）**，且知识层改硬约束。
- 当前诚实定位：**第一轮前瞻 pilot，M1 8 vs 我们 6，差异 = 1 个分歧候选，无统计意义；知识层带偏一次（TT-BASIC），双方都漏 1 个 severity-3（OTEL-SHIPPING）。**
