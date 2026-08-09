# 审查发现摘要

- 清理验证把所有非零 kubectl get 结果当成资源不存在，可能造成 Chaos 资源残留。
- probe restart runner 在清理未确认时清空 active_resource，丢失最终清理机会。
- runtime gate 的 kubectl 超时未结构化处理，mutation name availability 对 RBAC/timeout fail-open。
- 空 labelSelectors 会退化为 namespace 全量 Pod 查询，实验目标不再确定。
- 根 pytest 未隔离 otel-demo 集成测试；测试会写入 issue/knowledge/selection artifacts。
- selection comparison 将 20 个 evidence 候选和 12 个 core registry 混合，产生负剩余候选。
- own_discovery_evidence 未区分有效生命周期、weakness、below_threshold 和 invalid。
- bootstrap weighted recall 使用固定总体分母；severity schema 改变时排名不稳定。
- runner report 未绑定 environment fingerprint，且 runner 内部分类没有 baseline。
- 汇总报告将场景重复次数写死为 3，实际输入记录为 4 条/场景。
- 未知项目 ID 静默回退到 TT。
- 实验结论范围仍限于 NetworkChaos delay/loss + 少量 PodChaos/StressChaos；外部方法不是独立复现。
