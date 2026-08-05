# Train Ticket 薄弱点清单（第一轮收尾）

> 汇总日期：2026-08-05
> 被测项目：`FudanSELab/train-ticket` @ `313886e99befb94be6cd45f085c98e0019f59829`
> 全部发现均来自隔离环境 `train-ticket-lab` 的真实注入/静态源码审查，未触碰生产命名空间。

## 清单

| # | 薄弱点 | 证据类型 | 严重度 | 草稿 | 状态 |
|---|---|---|---|---|---|
| 1 | `queryOrdersForRefresh` 在生产路径上禁用了唯一的下游调用 `queryForStationId`（两个 order 服务相同），`ts-order-service -> ts-station-service` 故障注入边在生产请求中不可达；订单 `from`/`to` 返回原始 UUID 而非站名；`queryForStationId` 成为有实现、有单测但生产不可达的死代码 | 静态源码（含行号）+ 单元测试仅覆盖函数级 | 中（benchmark 完整性/误导性韧性） | `2026-08-05_disabled-downstream-call-in-refresh.md` | DRAFT，待人工审核后提交 GitHub issue |
| 2 | Station 在确认的出站延迟下无应用级 timeout/retry/fallback/熔断防御：100ms/500ms/2s 阶梯延迟下响应契约保持但延迟线性恶化（30.1ms -> 216/1021/4021ms）；3s 注入时客户端 5047ms 超时，服务端 6064ms 才完成业务分支；无任何声明性韧性配置 | 运行时（注入+双 Oracle+延迟阶梯+超时边界+服务端日志时间线）+ 静态源码审查 | 高（可用性/延迟 SLO 风险） | `2026-08-05_station-no-timeout-defense.md`（待生成） | DRAFT |

## 提交说明

- 仓库无 `SECURITY.md`/`CONTRIBUTING.md`，以普通 issue 提交。
- 期望回复概率低（项目 2025-11 后推送少、69 个长期零评论 issue）；定位为 correctness/benchmark-integrity 报告而非缺陷修复请求。
- 提交前需人工审核草稿内容与措辞。
