# 提交追踪表（Issue Tracking）

> 规则：所有对外提交（issue/PR）先在此登记 → 草稿经用户确认 → 提交后更新状态。
> 状态：draft | open | confirmed | fixed | closed | wontfix | not-submitted
> 不期待回复的仓库（如 train-ticket）也要登记，便于追溯"提交过什么、为何无回复"。

| 日期 | 项目 | Issue 标题 | 状态 | 维护者响应 | 备注 |
|---|---|---|---|---|---|
| 2026-08-05 | FudanSELab/train-ticket | Disabled downstream call in `queryOrdersForRefresh` | not-submitted | — | 草稿在 `reporting/train-ticket/issues/`，用户与导师决策中 |
| 2026-08-05 | GoogleCloudPlatform/microservices-demo | F2: frontend 核心数据路径无降级 → 整站级联 500 | draft | — | 证据在 `artifacts/online-boutique/findings.md`，用户决策中 |
| 2026-08-05 | GoogleCloudPlatform/microservices-demo | F1: checkout 业务链无 timeout → 全额传导/无限挂起 | draft | — | 同上（作 F2 佐证或单独提交） |

## 响应预期参考（2026-08-05 核实）

| 仓库 | 最近 push | 开放 issue | 响应信号 |
|---|---|---|---|
| train-ticket | 2025-11-21 | 69 | 大量多年 0 评论 → 期望值低 |
| microservices-demo | 2026-08-04 | 78 | 活跃，近 10 条当天处理 → 期望值高 |
| opentelemetry-demo | 2026-08-04 | 81 | 活跃，近 10 条当天关闭 → 期望值高 |
| dotnet/eShop | 2026-06-08 | 182 | 活跃，但部分安全 issue 挂 2 个月 → 中 |

## 提交 checklist

- [ ] 无 SECURITY.md 时走普通 issue；有则查安全渠道
- [ ] 附 pin 的 commit + 隔离环境声明 + 复现步骤
- [ ] 不含凭据/secret 值
- [ ] 证据链完整（静态位置 + 运行时三阶段测量 + 日志）
- [ ] 区分 bug / enhancement / 设计权衡
- [ ] 用户已审阅草稿
