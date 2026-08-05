# 候选项目矩阵（Projects Matrix）

> 更新：2026-08-05（数据来自 GitHub API，快照性质，会变化）
> 用途：后续项目选择依据。活跃度数据是决策关键，不是印象。

## 已选定/已接入

| 项目 | 仓库 | 定位 | 活跃度（2026-08） | 报告价值 | 状态 |
|---|---|---|---|---|---|
| Train Ticket | FudanSELab/train-ticket | 微服务基准（研究） | push 2025-11-21，69 open issues 大量 0 评论 | 低（基准无韧性是设计使然；但基准完整性发现可报） | ✅ 完整闭环 |
| Online Boutique | GoogleCloudPlatform/microservices-demo | 云原生 demo（Google） | **push 2026-08-04**，78 open，近 10 条当天处理 | 中高（核心路径无降级 vs 广告降级的矛盾） | ✅ 完整闭环 |

## 候选（未接入）

| 项目 | 仓库 | 定位 | 活跃度（2026-08） | 报告价值 | 备注 |
|---|---|---|---|---|---|
| OpenTelemetry Demo | open-telemetry/opentelemetry-demo | 观测性参考应用 | **push 2026-08-04**，81 open，近 10 条当天关闭 | 中高（观测完备 → 适合验证"观测缺口"发现） | 观测证据链最完整，适合下一个 |
| .NET eShop | dotnet/eShop | .NET 参考电商 | push 2026-06-08，182 open | 中（有 .NET resilience 库 → 可测"库是否覆盖所有路径"） | 需 .NET/容器环境 |
| DeathStarBench | delimitrou/DeathStarBench | 高负载基准 | — | 低（benchmark，报告价值弱） | 高成本，留作研究 |
| Sock Shop | microservices-demo/microservices-demo | 电商示例 | **已归档** | — | 不推荐 |
| Istio | istio/istio | 服务网格平台 | — | 平台非业务目标 | 不做被测对象 |
| Chaos Mesh | chaos-mesh/chaos-mesh | 注入工具 | — | 非被测业务 | 工具视角 |

## 选择标准（下次选项目时）

1. 活跃维护（近 6 个月有 commit）——保证 issue 被看
2. 有 CI/测试——能跑复现
3. 有韧性/SLO/降级声明——找"声明了但没生效"的 bug
4. 部署成本可控
5. 与已有发现形成对照（train-ticket 无韧性 vs Online Boutique 部分降级 → 下一站最好测"有完整韧性栈"的项目，验证"库/栈是否覆盖所有路径"）
