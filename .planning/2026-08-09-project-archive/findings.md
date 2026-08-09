# 归档发现

## 已确认事实

- 研究范围涉及四个项目：Train Ticket、Online Boutique、OpenTelemetry Demo、Sock Shop。
- 方法存在三条正交轴：候选选择、测量位置、证据链/知识闭环。
- 既有统一台账记录 83 次 lifecycle-complete；r2 新增 24 次尝试，尚未合并到主台账。
- r2 实际只在 Online Boutique 执行；OTEL/TT 候选因镜像未部署而未执行。
- 选择方法方面，20 候选池 bootstrap CI 跨 0；r1 和 r2 都不足以支持总体 superiority。
- Sock Shop 真实业务链路揭示了 direct 测量对代码级 timeout 防御的盲区。
- ChaosEater 官方 Sock Shop cycle 主要覆盖 deployment availability；Ours 主要覆盖 call-chain contract 和 evidence chain。

## 当前口径风险

- `unified_experiments_summary.md` 的项目范围、轮次数量和实际资产存在不一致。
- r2 的“等预算 U@8”受到未部署项目和同质正样本池影响，只能作为 partial pilot。
- r2 有 7/24 基线无效尝试，需在 master ledger 中显式记录。
- `overall_project_method_comparison.md` 是当前综合叙事草稿，正式归档前仍需和 master ledger 对齐。

## 需要单独保留的结论

1. 选择算法目前没有统计显著总体优势。
2. 真实业务链路测量能暴露 direct 测量不可见的代码级防御。
3. 知识资产化和证据链使发现结果更可审计、可复用。
4. Ours 与 ChaosEater 目前是分层互补，不是已被统一协议证明的全面胜负。
