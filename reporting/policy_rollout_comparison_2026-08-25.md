# Legacy / Shadow / Guarded 对照结果

本次不做独立候选池排序实验，而是对 Sock Shop 和 Online Boutique 各执行最多 5 轮端到端批次，按完整 baseline、注入、观察、恢复、cleanup 和 RCA 证据统计。`environment_blocked` 不计为漏洞或 RCA 结果。

## 结果

| 项目 | 模式 | 计划/有效执行 | confirmed finding | RCA confirmed | cleanup verified | 停止 |
|---|---|---:|---:|---:|---:|---|
| Sock Shop | legacy | 5/5 | 2 | 2 | 5/5 | 固定 5 轮 |
| Sock Shop | shadow | 5/5 | 2 | 2 | 5/5 | budget_exhausted |
| Sock Shop | guarded | 5/5 | 2 | 2 | 5/5 | budget_exhausted |
| Online Boutique | legacy | 5/5 | 2 | 2 | 5/5 | 固定 5 轮 |
| Online Boutique | shadow | 5/5 | 2 | 2 | 5/5 | budget_exhausted |
| Online Boutique | guarded r4 | 5/5 | 3 | 3 | 5/5 | budget_exhausted |

候选质量的端到端代理指标为 confirmed finding / 有效执行轮次：Sock Shop 三模式均为 40%；Online Boutique 为 legacy 40%、shadow 40%、guarded 60%。这不是单独的候选池排序结论，而是完整闭环下的有效发现率。

RCA 安全指标为 confirmed RCA / confirmed finding，六个项目/模式单元格均为 100%。停止效率在本配置下相同：shadow 和 guarded 都在第 5 次有效执行后以 `budget_exhausted` 停止，未宣称新方法有早停优势。

## Cleanup 修复记录

Online Boutique 的 guarded-r2 曾真实暴露 `network_loss` 删除后立即读取的异步传播竞态，cleanup attestation 缺失并 fail-closed；没有被当作漏洞。`delete_resource` 现在只对短暂的 `exists` 状态在有限 timeout 内轮询，仍将 NotFound、timeout、RBAC/API error 作为独立状态处理。修复后 guarded-r3 的 network_loss 和 guarded-r4 全部 5/5 cleanup verified。

## 证据入口

- Sock Shop：`artifacts/policy-rollout/sock-shop-compare-legacy-20260825/`、`...-shadow-20260825/`、`...-guarded-20260825/`
- Online Boutique：`artifacts/policy-rollout/online-boutique-compare-legacy-20260825/`、`...-shadow-20260825/`、`...-guarded-20260825-r4/`
- guarded 修复验证：`artifacts/policy-rollout/online-boutique-compare-guarded-20260825-r3/`

结论：在这两个项目、五轮预算和当前候选空间内，新 guarded 机制在候选质量、RCA 确认安全、停止边界和 cleanup 安全上没有观察到 post-fix 退化。该结论不等同于跨项目普适性，也不改变默认策略仍需显式启用的安全边界。
