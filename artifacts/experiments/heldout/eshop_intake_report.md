# eShop 只读预检报告（ESHOP intake, Stage C）

> 日期：2026-08-10
> 状态：静态 intake 完成;snapshot 见 `eshop_knowledge_snapshot_pre.json`
> 本阶段未部署/未注入/未运行实验;bring-up/稳定/2-baseline 闸门保持 `not_run`

---

## 1. Canonical 来源

| 项 | 值 |
|---|---|
| canonical URL | `https://github.com/dotnet/eShop`（findings.md:82 引用） |
| commit | `9b4f9434f46fdc5c1a6e9e936af2868340cdbc48`（main 浅获取,2026-08-10） |
| license | MIT |
| 获取方式 | WSL shallow clone（仓库外,未提交 git） |
| 实际路径 | `/root/heldout_src/eshop` |

## 2. 关键文件 SHA-256

| 文件 | SHA-256 |
|---|---|
| `src/eShop.AppHost/Program.cs` | `6c0e25977f2068211b776fc57fbb85898c3d6b576c99d3fb168d8dc2388fced7` |
| `src/WebApp/Extensions/Extensions.cs` | `d0009c09da7eb439964985e332e50d64d88f9ed317f6e254a279983655bac66a` |
| `src/WebApp/Services/OrderingService.cs` | `2e8578d1eda8e3ab7ce7e471d6e3d5447e4c80a1a0d1407af74734ce989932c2` |
| `src/Basket.API/Grpc/BasketService.cs` | `cb02d7b4fdf67553847490a0b5ab86614f17cb4c45e7ea53b515ab4fb193fdba` |
| `src/eShop.ServiceDefaults/Extensions.cs` | `61a80ad164411ba51026c5ea571ed3e5c9825186202302a1ff1464be76f8e442` |
| `README.md` | `3ef8cf674084750c4d5db6f9317226f8e0a6ebba932e0ee73c3f9060c2e41ae7` |
| `global.json` | `aa66f8a82b3c2a419c62eabed1c17b7781157fdf6abee04b97b333e2213657cb` |

## 3. 服务清单与服务依赖图

- **API 服务（8 业务 + 基础设施）**:Basket.API、Catalog.API、Ordering.API、Identity.API、Webhooks.API、PaymentProcessor、OrderProcessor、WebApp(Web 前端)
- **基础设施**:EventBus(RabbitMQ)、EventBusRabbitMQ、IntegrationEventLogEF、Ordering.Domain、Ordering.Infrastructure、Shared、HybridApp、ClientApp、WebAppComponents、WebhookClient、eShop.AppHost(Aspire 编排)、eShop.ServiceDefaults(共享)
- 19 个 csproj 项目(8 API + 11 辅助)

**依赖图（Aspire AppHost, Program.cs 静态读取）**:
```
WebApp -> Basket.API, Catalog.API, Ordering.API, Identity.API, RabbitMQ(事件)
mobile-bff (YARP) -> Catalog.API, Ordering.API, Identity.API
Basket.API -> Redis, RabbitMQ
Catalog.API -> RabbitMQ, catalog-db
Ordering.API -> RabbitMQ, order-db
OrderProcessor -> RabbitMQ, order-db (等待 ordering.API)
PaymentProcessor -> RabbitMQ
Webhooks.API -> RabbitMQ, webhooks-db
WebhookClient -> Webhooks.API
```
- HTTP 调用边:WebApp `AddHttpClient<CatalogService>(BaseAddress catalog-api)`、`AddHttpClient<OrderingService>(BaseAddress ordering-api)`;WebhooksSender 用 HttpClientFactory
- gRPC:Basket.API `BasketService`(gRPC)

## 4. 调用超时 / retry / fallback / circuit breaker

- **未发现显式超时配置**:WebApp/Webhooks 的 HttpClient 无显式 Timeout;gRPC Basket 无 per-call deadline
- **未发现 retry/fallback/circuit breaker**:grep `Timeout|Retry|CircuitBreaker|AddPolicyHandler` 无命中
- ServiceDefaults 只做 OpenTelemetry 配置(日志/指标/追踪),无 Resilience 策略
- 可观测:OpenTelemetry 全栈(`eShop.ServiceDefaults/Extensions.cs`),默认 OTLP 导出

## 5. Manifest / 镜像 / replicas / probe / PDB / HPA

- **无 docker-compose、无 k8s manifest**（仓库内仅 `es-metadata.yml` CI 元数据、`.spectral.yml` lint、`ci.yml`）
- Aspire AppHost 用 `AddProject` 编排（开发态,Docker Desktop 生态）
- **availability 候选受限**:无 k8s replicas/PDB/HPA 静态事实可构造（与 Hotel/SOCIALNET 不同）
- 镜像:无 Dockerfile（`find src -name Dockerfile*` 空）

## 6. fault family 可支持

- delay/loss:HTTP/gRPC 边可注入（NetworkChaos 服务级,需先部署）
- kill:PodChaos 需 k8s 部署（当前无 manifest → 环境门槛高）
- **候选池潜力**:8 API 服务 + ~8 调用边 → pilot 24 候选需依赖边级组合,formal 48 需结合事件总线边;**可用性候选因无 k8s manifest 受限** → 标记 `unknown`（部署形态决定,待部署验证）

## 7. go_no_go

**`ready_for_snapshot`**（源码可追溯、commit 固定、服务图/调用边/超时/可观测静态确认）
- 注意:availability 候选潜力 `unknown`（无 k8s manifest）——部署环境门槛是主要 blocked 风险
- bring-up/稳定/2-baseline 闸门 `not_run`

## 8. 泄漏审计（跨栈独立）

- 技术栈 .NET vs Go;仓库独立 dotnet/eShop;SE/DP/JE 无 `eShop` 证据 → leakage `low`
