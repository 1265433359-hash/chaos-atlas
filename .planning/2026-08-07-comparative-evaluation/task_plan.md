# 混沌测试方法对比实验设计

## 目标

基于当前项目已经完成的 Train Ticket、Online Boutique 和 OpenTelemetry Demo 实验能力，设计一套可执行、可复现、可写入论文的公平对比协议，用来比较 Random/YAML、ChaosEater、FastFI、Cast-style、Graph-only 与本项目完整方法的问题发现效果。

## 阶段

| 阶段 | 状态 | 交付物 |
|---|---|---|
| 1. 盘点现有方法、环境和证据 | complete | 可复用资产、限制和被测项目清单 |
| 2. 定义研究问题与公平性边界 | complete | RQ、假设、输入权限、预算与统一 Oracle |
| 3. 设计实验矩阵和执行流程 | complete | 方法 x 项目 x 场景 x 重复次数矩阵 |
| 4. 定义问题判定、指标与统计 | complete | 独立问题规则、指标公式、统计检验 |
| 5. 设计数据记录和人工复核 | complete | Run/Issue/Adjudication 记录模板 |
| 6. 输出可执行对比协议 | complete | `artifacts/experiments/comparative_evaluation_protocol.md` |
| 7. 一致性检查 | complete | 已核对 runner/分类器入口、标签语义、预算计算、统计独立性和 Markdown 结构 |

## 核心约束

- 不把“生成实验数”当成“发现问题数”。
- 所有方法共享同一被测版本、工作负载、故障执行器、观测窗口和最终问题判定规则。
- 方法可使用的信息必须分档披露，不能把 trace-aware 方法与 YAML-only 方法伪装成同等输入。
- 外部方法无法原样运行时，必须标为 `style/inspired reimplementation`，与官方复现分开报告。
- 已知问题用于验证召回率，隐藏问题必须通过盲测和独立根因去重评审确认。

## 错误记录

| 错误 | 尝试 | 处理 |
|---|---:|---|
| 暂无 | 0 | - |
