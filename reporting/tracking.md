# 提交追踪表（Issue Tracking）

> 规则：所有对外提交（issue/PR）先在此登记 → 草稿经用户确认 → 提交后更新状态。
> 状态：draft | open | confirmed | fixed | closed | wontfix | not-submitted
> 不期待回复的仓库（如 train-ticket）也要登记，便于追溯"提交过什么、为何无回复"。

| 日期 | 项目 | Issue 标题 | 状态 | 维护者响应 | 备注 |
|---|---|---|---|---|---|
| 2026-08-10 | open-telemetry/opentelemetry-demo | OpenTelemetry Demo: shipping quote failure reports "email service" instead of "shipping service" | open | pending | https://github.com/open-telemetry/opentelemetry-demo/issues/3818 |
| 2026-08-10 | FudanSELab/train-ticket | Train Ticket: station lookup exceeds the client timeout under a 3-second outbound delay | open | pending | https://github.com/FudanSELab/train-ticket/issues/311 |
| 2026-08-10 | FudanSELab/train-ticket | Train Ticket: /order/refresh may skip the ts-order-service to ts-station-service station-name lookup | open | pending | https://github.com/FudanSELab/train-ticket/issues/310 |
| 2026-08-10 | GoogleCloudPlatform/microservices-demo | Online Boutique: paymentservice probe restarts the container after a 2-second delay | open | pending | https://github.com/GoogleCloudPlatform/microservices-demo/issues/3475 |
| 2026-08-10 | GoogleCloudPlatform/microservices-demo | Online Boutique: Checkout waits for delayed or unavailable payment, shipping, and email services | open | pending | https://github.com/GoogleCloudPlatform/microservices-demo/issues/3474 |
| 2026-08-10 | GoogleCloudPlatform/microservices-demo | Online Boutique: home page returns HTTP 500 while productcatalogservice is unavailable | open | pending | https://github.com/GoogleCloudPlatform/microservices-demo/issues/3473 |
| 2026-08-23 | open-telemetry/opentelemetry-demo | OpenTelemetry Demo: unavailable emailservice blocks PlaceOrder until the caller deadline | draft | pending | `reporting/opentelemetry-demo/issues/2026-08-23_emailservice-blocks-placeorder.md`; not yet submitted |
| 2026-08-24 | Sock Shop | Sock Shop: single-replica front-end becomes temporarily unavailable during Pod replacement | draft | pending | `reporting/sock-shop/issues/2026-08-24_front-end-single-replica-availability-degradation.md`; review pack SS-ISSUE-001; not yet submitted |
| 2026-08-24 | Sock Shop | Sock Shop: a single catalogue-db replica removes the catalogue endpoint during pod replacement | draft | pending | `reporting/sock-shop/issues/2026-08-24_catalogue-db-single-replica-catalogue-outage.md`; review pack SS-ISSUE-002; not yet submitted |
| 2026-08-24 | Sock Shop | Sock Shop: catalogue transport abort propagates to the front-end without a graceful response contract | draft | pending | `reporting/sock-shop/issues/2026-08-24_front-end-catalogue-abort-no-graceful-degradation.md`; review pack SS-ISSUE-003; not yet submitted |

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
