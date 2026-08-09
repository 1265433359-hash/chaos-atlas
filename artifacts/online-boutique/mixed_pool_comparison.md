# 混合池对比实验报告（OB 重建 + 唯一真 protected 边）

> 日期：2026-08-09
> 目的：在"含 protected 边"的混合候选池上，验证决策引擎（契约+知识）是否优于 M1 盲选 LLM 和 M0 随机
> 关键资产：重建 Online Boutique（11 服务），唯一源码级真 protected 边 = frontend→adservice（100ms 请求级超时，frontend/rpc.go:120）

## 一、候选池（8 候选：3 protected + 5 unprotected）

| 候选 | 类型 | 预期 | 实测 |
|------|------|------|------|
| OB-FRONTEND-ADSERVICE-DELAY-2000 | protected | defended | ✅ 31→127ms（100ms 超时吸收 2s） |
| OB-FRONTEND-ADSERVICE-DELAY-500 | protected | defended | ✅ 28→130ms（同上） |
| OB-FRONTEND-ADSERVICE-LOSS-100 | protected-loss | defended | ✅ 9→131ms（超时兜底，页面 200） |
| OB-FRONTEND-CURRENCY-DELAY-2000 | unprotected | weakness | ✅ 28→8011ms（8s 客户端挂死） |
| OB-FRONTEND-PRODUCTCATALOG-DELAY-2000 | unprotected | weakness | ✅ 28→2030ms（2s 精确放大） |
| OB-CHECKOUT-PAYMENT-DELAY-2000 | unprotected | weakness | ✅ 25→2024ms（下单 2s 放大） |
| OB-CHECKOUT-SHIPPING-DELAY-2000 | unprotected | weakness | ✅ 25→4027ms（4s 双倍延迟 + HTTP 500） |
| OB-CHECKOUT-CART-DELAY-2000 | unprotected | weakness | ✅ 25→2069ms（2s + HTTP 500） |

**核心机制验证**：protected 边注入 2s 延迟仅 +96ms（100ms 超时兜底），unprotected 边注入 2s 延迟 → 8s 挂死或 2-4s 放大。**决策引擎的契约过滤判断正确**——它跳过 protected 边是知识在起作用。

## 二、三方法对比（预算=6，预测冻结于执行前）

| 指标 | decision_engine | M1 盲选 | M0 随机(100 trials) |
|------|----------------|---------|---------------------|
| 命中弱点 | 5/6 | 5/6 | 均值 3.72，95%CI [3,5] |
| severity 加权 | 12 | 12 | ~8 |
| protected 误选 | 1 | 1 | 均值 2.28 |

## 三、统计结论（诚实）

1. **决策引擎和 M1 盲选打平**（5/6 vs 5/6，sev 12 vs 12）——**未显示出契约知识的优势**。
2. 两者都优于随机（命中 5 > 随机均值 3.72），但 **88% < 95% 未达统计显著**。
3. **根因**：M1 盲选 LLM 凭架构推断也避开了 adservice（"广告服务非关键路径"是通用常识），无需契约清单。**本池的 protected 边太"明显"**——它不仅是 protected，还是非关键服务，双重线索让盲选也能识别。

## 四、实验局限（必须记录）

- **池子太小**（8 候选）→ 统计功效低（B1 教训重演）
- **protected 边非关键**：adservice 是广告，失败只影响非核心功能。真正的区分需要"关键路径上的 protected 边"（如 checkout→productcatalog 若有真超时），此时盲选无法仅凭"非关键"推断
- **候选池构造偏差**：5/8 是 weakness，随机也能中 3.72
- **契约清单修正的价值未被本池体现**：修正了 OB productcatalog（连接级 3s 误标）和新增 adservice，但决策引擎的 SKIP 机制只被 2 个候选触发

## 五、下一步（区分方法优劣的正确池子）

1. **需要"关键路径 protected 边"**：找一个核心链路上有真超时/重试的下游（如 Sock Shop orders→payment 若有超时、或构造注入点），盲选无法靠"非关键"推断
2. **增大池子**：16-24 候选，混合关键/非关键、protected/unprotected，随机基线用分布而非单次
3. **用 McNemar 配对检验**：两方法在同一批候选上的差异

## 六、本实验的真正收获（非对比结论）

尽管方法对比未拉开差距，本实验确立了三个可靠事实：
1. **OB 唯一真 protected 边（adservice 100ms）的防御机制被精确验证**：2s 注入只 +96ms
2. **契约清单修正有效**：productcatalog 3s 误标为连接级已纠正
3. **OB 混合池工具链可复用**：镜像构建、部署、注入、测量全链路跑通，为更大池子实验铺路
