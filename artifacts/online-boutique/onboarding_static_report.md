# Online Boutique 接入报告（静态映射，阶段 3a）

> 日期：2026-08-05
> 方法：复用 train-ticket 的「测试节点中心 + 证据链」方法论
> 状态：静态完成，运行时待验

## 版本与来源

- 仓库：`GoogleCloudPlatform/microservices-demo`
- 固定 commit：`9a4616e77f0f9cbcbecaf27d711c38890dda1404`（main，2026-08-04 快照）
- 获取方式：GitHub API tarball（`github.com` git 协议在本机网络不可达，codeload/api 可达）
- 工作区：`online-boutique/`（无 .git 元数据，与 `train-ticket/` 同模式，已被 .gitignore 排除）
- 许可证：Apache-2.0（LICENSE 文件确认）

## 服务清单（11 个业务服务 + 1 个负载生成器）

`adservice, cartservice, checkoutservice, currencyservice, emailservice, frontend, loadgenerator, paymentservice, productcatalogservice, recommendationservice, shippingservice, shoppingassistantservice`

- 语言：Go 为主（checkout/currency/email/frontend/payment/product-catalog/recommendation/shipping/cart），Java（adservice），Python（loadgenerator/shoppingassistant）
- 通信：gRPC（protos/），frontend 对外 HTTP

## 韧性面静态映射（重点）

> 检索范围：`istio-manifests/`、`kubernetes-manifests/`、`helm-chart/`、`docs/`、`kustomize/components/`、各服务源码

### A. 无显式韧性声明

- `istio-manifests/` 仅含 `frontend-gateway.yaml` + `frontend.yaml`（VirtualService/DestinationRule **无 retry/timeout/circuit-breaker** 配置）
- `kustomize/components/service-mesh-istio/` 同样未发现 retry/timeout/circuit 配置
- 官方 `docs/product-requirements.md` 是**部署契约**（golden journey / demo 简洁性 / GKE quickstart），非韧性契约
- 结论：**本项目没有任何声明性的韧性配置（retry/timeout/circuit-breaker）**。这与 README 描述的"演示 Google Cloud 产品（含服务网格）"定位一致——韧性未在默认配置中声明

### B. gRPC 调用超时覆盖（源码级，测试节点中心）

| 调用方 | 目标服务 | 超时 | 降级行为 | 证据 |
|---|---|---|---|---|
| frontend `getAd` | adservice | **100ms**（`rpc.go:120`） | 有降级（`chooseAd` 吞错返回 nil，`handlers.go:527-533`） | `src/frontend/rpc.go:119-124` |
| frontend `getRecommendations` | recommendationservice | **3s**（`rpc.go:212`） | 部分调用点忽略错误（`handlers.go:378` `recommendations, _ :=`） | `src/frontend/rpc.go:212` |
| frontend `getCurrencies` | currencyservice | 无 | **无**（`homeHandler` 硬 500） | `rpc.go:30-44` + `handlers.go:62-66` |
| frontend `getProducts`/`getProduct` | productcatalogservice | 无 | **无**（硬 500） | `rpc.go:45-57` + `handlers.go:67-71` |
| frontend `getCart` | cartservice | 无 | **无**（硬 500） | `handlers.go:72-76` |
| frontend `convertCurrency` | currencyservice | 无 | **无**（硬 500） | `handlers.go:84-90` |
| checkout `chargeCard` | paymentservice | **无** | **无**（`PlaceOrder` 返回 Internal 错误，`service.go`/`main.go:252-254`） | `main.go:252-254, 369-375` |
| checkout `SendOrderConfirmation` | emailservice | **无** | **无**（阻塞主流程） | `main.go:380` |
| checkout `ShipOrder` | shippingservice | **无** | **无**（阻塞主流程） | `main.go:387` |
| checkout `getQuote` | shippingservice | **无** | **无** | `main.go` |
| 所有服务 | gRPC dial | 连接建立无 WithBlock（后台重连语义） | 断连期间调用失败 | `main.go:214` `grpc.NewClient` |

### C. 关键观察（静态假设，需运行时证实）

1. **checkout 业务链（payment → email → shipping）无任何超时/重试/降级**。任一下游挂起 → `PlaceOrder` 无限阻塞（HTTP/gRPC 客户端侧超时取决于前端网关/调用方，服务内无保护）。
2. **frontend 核心数据路径（currencies/products/cart/汇率）无超时 + 硬 500**。productcatalogservice 或 currencyservice 故障 → 整个首页 500，无部分降级。
3. **唯一的"降级"是广告**（100ms 超时 + 吞错），但 100ms 可能过紧（adservice 为 Java 服务，JVM 冷启动/GC 极易超 100ms），导致广告在正常负载下也常失败。
4. `adservice/AdService.java:202` 的 `sleepTime = 10` 位于 `initStats()`（不可达的 TODO 死代码），**不是**请求级延迟——已排除。

## 测试节点中心候选（对齐 train-ticket 方法论）

| 测试节点 | 路径 | 假设 | 预期结果分类 | 优先级 |
|---|---|---|---|---|
| checkout→payment 故障（NetworkChaos 丢包/延迟） | `PlaceOrder → chargeCard → paymentservice` | 无超时无降级 → 下单挂起或失败 | 未防御（hard fail 或挂起） | P0 |
| checkout→email 故障 | `PlaceOrder → SendOrderConfirmation` | 无降级 → 邮件故障阻塞下单成功 | 未防御 | P0 |
| frontend→productcatalog 故障 | `homeHandler → getProducts` | 无超时硬 500 → 整站首页不可用 | 未防御（全站级联） | P0 |
| frontend→adservice 延迟 | `getAd` 100ms 超时 | 超时过紧 → 广告恒失败（降级设计，但正常负载即触发） | 部分防御（设计如此，超时值是否合理） | P1 |
| frontend→recommendations 故障 | `getRecommendations` 3s | 有超时但部分调用点忽略错误 → 不降级也可能不报错 | 部分防御 | P1 |

## 可达性/注入前门控（对齐 `runtime_applicability_gate.py`）

- Kubernetes：Docker Desktop 集群（与 train-ticket 共用 `train-ticket-lab` namespace 或新建 `online-boutique-lab`）
- Chaos Mesh：2.8.3（已装）；注意 HTTPChaos 仍被 WSL2 ebtables 阻断，NetworkChaos/StressChaos 可用
- 注入目标：`kubernetes-manifests/`（release 目录）可 apply；`helm-chart/` 备选；`skaffold.yaml` 用于本地开发部署
- **运行时注入需用户确认**（计划红线：隔离环境 + 实验前只读健康检查）

## 已知限制

- 本报告为静态映射；`main.go:214` 的 `grpc.NewClient` 是否等价于无超时需运行时证实（Go gRPC 无 deadline 时调用无限等待）
- `loadgenerator` 会持续打负载，运行时实验需注意基线噪声（可用 `without-loadgenerator` kustomize component 或暂停）
- 尚未检查 shoppingassistantservice（AI 新服务）与 protos 全量 rpc 定义
