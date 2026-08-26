# Sock Shop Full Top 11 修正版实验设计

## 目标

从 Full 已去重的 114 个 family 代表中，完全按冻结置信度降序选取前 11 个。选择过程不得读取 runtime outcome、历史证据可得性或 gate 结果，也不得用后续候选替换 blocked 候选。

## 输入与身份

- Full family 代表来源：`chaosatlas_sockshop_r5_dedup_2026-08-15-r5/overlap_audit.json`。
- 注册排序身份继续保留 `kind + action + target + call_chain_position + normalized_parameters`，用于复现原 Full 去重结果。
- 另行计算 executable mutation identity，忽略自由文本调用链位置和 metadata，用于识别物理相同的注入。
- 排序键为 `(-confidence_score, source_order, mutation_instance_key)`，冻结前 11 个。

## Gate

每个 Top 11 候选依次检查：文件 SHA-256、namespace、CRD、selector、Pod Ready、目标端口/协议、资源名冲突、Chaos 组件前置条件和 server-side dry-run。

Gate 结果只允许 `ready_for_injection`、`blocked`、`not_applicable`。任何 blocked/not-applicable 候选保留原排名，不补抽第 12 名。HTTPChaos 的 server-side dry-run 通过只代表 API 接受，不代表目标端口和协议有效。

## 运行证据

- 已有两份 completed、生命周期完整且 executable mutation 严格相同的报告时，只复核，不重跑。
- 缺少双重复证据且 gate ready 的候选，在新目录中 fresh 执行两次。
- blocked/not-applicable 候选不注入，进入“假设有效率”分母，不进入稳定弱点率 runtime 分母。
- 每轮保持 baseline、injection、recovery、cleanup、global scan、washout 和 diagnostics 协议。

## 统计

- 假设可执行率：`ready / 11`。
- 稳定弱点率：两次均复现的 mutation / gate ready 且拥有两份有效报告的 mutation。
- 一次复现单列 unstable。
- 分别报告生成置信度、gate 状态、运行来源（historical/fresh）和 wall-clock。
- 旧 evidence-backed 2/11 结果降级为历史筛选口径，不覆盖。

## 审核边界

- `human_review=pending`。
- `knowledge_base_updated=false`。
- 不调用模型，不重新生成 Full 假设。
- 不安装或修复 Chaos Mesh；平台前置条件缺失按 blocked 记录。
