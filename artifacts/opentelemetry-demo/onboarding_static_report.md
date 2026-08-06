# OpenTelemetry Demo 接入报告（静态映射，阶段 0/1）

> 日期：2026-08-06
> 方法：复用「测试节点中心 + 证据链」方法论
> 状态：静态完成，运行时待验

## 版本与来源

- 仓库：`open-telemetry/opentelemetry-demo`
- 固定 commit：`2e72d8bcdf754603e956406808630bc9663c992c`（main，2026-08-05 快照）
- 获取方式：GitHub API tarball
- 工作区：`otel-demo/`（已加入 .gitignore）
- 许可证：Apache-2.0

## 部署方式（关键差异：无 K8s 原生清单）

- 仓库**只有 Docker Compose**（compose.yaml + 扩展），无 kubernetes-manifests/helm 目录
- K8s 部署走**外部官方 Helm chart**：`open-telemetry/opentelemetry-helm-charts` repo，chart `otel-helm/opentelemetry-demo` v0.41.0（appVersion 3.0.0）
- 镜像源：`ghcr.io/open-telemetry/demo:<version>-<service>`（**本机可达，已验证 checkout 镜像拉取成功**）
- 依赖镜像：flagd（ghcr）、postgres（Docker Hub 可达）、valkey（ghcr）、collector-contrib（Docker Hub，**429 限流**）

## 服务与语言

30+ 服务，核心业务：ad / cart / checkout(Go) / currency / email(Ruby) / frontend(Node) / image-provider / payment(Node) / product-catalog(Go) / quote / recommendation(Python) / shipping(Rust) / fraud-detection(Java) / accounting / chatbot

通信：gRPC 为主（pb/ + genproto），checkout→shipping/email 用 **HTTP**

## 韧性声明检索（重点）

### A. 无显式韧性声明
- 源码全量检索 retry/timeout/circuit-breaker/fallback：仅发现 chatbot 的 `AGENT_CHAT_INTERFACE_TIMEOUT=300s`（AI 接口配置）和 frontend webpack fallback（构建无关）——**业务服务无显式韧性配置**（与 OB 相同模式）
- 无 Istio/K8s 清单层声明（仓库无 K8s 清单）

### B. checkout 调用链（测试节点中心，对齐 OB 方法论）

**静态映射**（`src/checkout/main.go`）：

| 调用 | 协议 | 超时 | 错误处理 | 证据 |
|---|---|---|---|---|
| `GetCart` (cart) | gRPC | 无 | 致命（PlaceOrder 返回 err） | :520 |
| `GetProduct` (product-catalog) | gRPC | 无 | 致命 | :538-540 |
| `convertCurrency` (currency) | gRPC | 无 | 致命 | :542-544 |
| `Charge` (payment) | gRPC | 无 | 致命（chargeCard） | :573 |
| `quoteShipping`/`shipOrder` (shipping) | **HTTP** | 无（http.Client 无 Timeout） | **致命**（`codes.Unavailable`） | :366-369, :619 |
| `sendOrderConfirmation` (email) | **HTTP** | 无 | **降级**（logger.Warn） | :403-404 |

**与 Online Boutique 的惊人相似**：
- checkout 业务链**全部无 timeout**（gRPC `grpc.NewClient` 无 deadline，HTTP `&http.Client{}` 无 Timeout）——`main.go:212` httpClient 构造**未设 Timeout**
- shipping 致命（`codes.Unavailable`，与 OB 的 `shipOrder` 同语义）
- email 降级（`logger.Warn`，与 OB 的 `log.Warnf` 同模式）
- **shipping 用 HTTP 而非 gRPC**（OB 是 gRPC）——传输协议不同，但"无 timeout + 致命"模式一致

## 测试节点中心候选（对齐方法论）

| 测试节点 | 路径 | 假设 | 预期分类 | 优先级 |
|---|---|---|---|---|
| checkout→payment 故障 | PlaceOrder → Charge | 无 timeout → 延迟全额传导/挂起 | 未防御 | P0 |
| checkout→shipping 故障（HTTP） | PlaceOrder → shipOrder | 无 timeout → 挂起 + 致命（Unavailable） | 未防御 | P0 |
| checkout→email 故障（HTTP） | PlaceOrder → sendOrderConfirmation | 降级（Warn）→ 失败不致命 | 部分防御 | P1 |
| frontend→product-catalog 故障 | 首页 → gRPC | 无 timeout → 级联/挂起 | 未防御 | P1 |

## 观测面（本项目独特价值）

- **自带完整 OTel 观测栈**：otel-collector + jaeger（trace）+ prometheus（metric）+ grafana + opensearch（log）
- **与 OB 的本质区别**：OB 无观测，我们靠 cgroup/日志手工观测；OTel Demo 自带 trace/metric/log 全链路——**可验证"注入的故障是否被观测栈捕获"（观测缺口检测）**，这是前两个项目做不到的
- 候选实验：注入后检查 Jaeger trace 是否显示故障 span、Prometheus 指标是否反映 SLO 越界——**"观测完备的系统"能否提供故障归因证据**

## 已知限制

- 无 K8s 原生清单 → 运行时部署依赖 Helm chart（外部 repo，版本 0.41.0 vs 源码 commit 2e72d8bc 不完全对齐，需接受 chart 默认镜像 tag）
- collector-contrib 镜像 Docker Hub 429 限流（可重试/换 tag）
- 部署成本：30+ 服务（含 observability 栈）对 Docker Desktop 资源压力大，建议只部署核心业务子集（checkout/cart/product-catalog/currency/payment/shipping/email + minimal collector）
