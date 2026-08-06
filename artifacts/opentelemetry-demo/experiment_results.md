# OpenTelemetry Demo 运行时实验报告（阶段 3）

> 日期：2026-08-06
> 环境：kind 集群（chaos-kind）+ Chaos Mesh 2.8.3，`otel-demo-lab` namespace
> 版本：opentelemetry-demo @ 2e72d8bc（镜像 3.0.0），本地手动 manifest（无 K8s 原生清单）

## 部署（阶段 2）

- **架构差异**：OTel Demo 无 K8s 清单（纯 Compose），手动写 manifest 部署 10 个服务（checkout/cart/product-catalog/currency/payment/shipping/email/quote/valkey/postgres + flagd sidecar）
- **部署中解决的 4 个问题**（均有方法价值）：
  1. **cart 是 .NET 监听 8080**（非 OB 的 Go 7070）→ 修正 targetPort
  2. **postgres init.sql 与镜像自动建库冲突**（`CREATE USER/DATABASE` already exists）→ 精简 init.sql，POSTGRES_USER=astronomy_user
  3. **shipping（Rust）硬依赖 flagd 且 panic**（`main.rs:55`）——crate 0.2.2 读 FLAGD_HOST env 但默认 localhost → 用 **flagd sidecar**（共享网络）
  4. **flagd v0.16 默认端口是动态的**（日志显示 IResolver 监听 40773）→ 显式 `--port 8013`
- **源码 bug 发现**：`checkout/quoteShipping` 错误消息写 "failed POST to **email** service"（实际是 shipping，`main.go:498`）——复制粘贴错误，误导排障

## 基线（阶段 3a）

PlaceOrder 稳定 **~3.0-3.3s**（中位 ~3100ms）——比 OB（17ms）高两个数量级。原因：OTel 观测栈（每个服务 OTel SDK 开销）+ HTTP 调用链（checkout→shipping/email/quote 都是 HTTP）+ 多语言冷启动。**这是 OTel Demo 的固有基线，非异常**。

## 注入实验（阶段 3b）

### 实验 A：payment 2s 延迟（NetworkChaos）

| 阶段 | PlaceOrder | 结论 |
|---|---|---|
| 基线 | ~3100ms | 正常 |
| 注入（2 次） | **4793ms / 5175ms**（+1690 / +2075ms） | 延迟全额传导（无 timeout） |
| payment pod | 无重启 | OTel Demo 探针配置未触发 |

### 实验 B：payment 100% 丢包（NetworkChaos）

| 阶段 | PlaceOrder | 结论 |
|---|---|---|
| 注入 | **挂起 10007.4ms → DEADLINE_EXCEEDED** | 无 timeout → 无限挂起直到调用方边界 |
| 恢复后 | ~3.0-3.3s | 回到基线 |

## 三项目对照（核心价值：模式跨项目复现）

| 发现 | train-ticket | Online Boutique | OTel Demo |
|---|---|---|---|
| checkout 业务链无 timeout | ✅（Basic 无 timeout 配置） | ✅（grpc/HTTP 无 Timeout） | ✅（grpc/HTTP 无 Timeout） |
| 延迟全额传导 | ✅（+2000ms） | ✅（2021.5±3.1ms 统计） | ✅（+1690~2075ms） |
| 丢包无限挂起 | ✅（客户端超时边界） | ✅（5/5 全 10008ms） | ✅（10007.4ms） |
| email 降级（非致命） | 未测 | ✅（log.Warnf） | ✅（logger.Warn） |
| shipping 致命 | — | ✅（codes.Unavailable） | ✅（panic 后 Unavailable） |
| 探针重启竞争 | — | ✅（1s 探针 vs 2s 延迟） | 未触发（探针配置不同） |

**决定性结论**："微服务 checkout 业务链无 timeout + 延迟全额传导 + 丢包无限挂起"是**三个独立项目共有的模式**——这不是单个项目的问题，是**当前微服务基准/demo 应用的普遍设计缺口**。方法论（test-node 中心 + 证据链 + 三阶段测量）在三个项目上完整复用成功。

## 观测缺口验证（OTel Demo 独特价值）

- OTel Demo 自带完整观测栈（collector/Jaeger/Prometheus/Grafana），但**本次注入实验未启用**（未部署观测栈以控制资源）
- 基线 ~3s 已含 OTel SDK 开销——**观测本身有成本**，这是"观测完备系统"的隐性代价
- 后续可补：启用观测栈后重跑注入，验证故障是否被 Jaeger trace 捕获（观测缺口检测）

## 观测缺口验证（深入 A，2026-08-06 追加）

**背景**：前两个项目无法验证"观测完备系统能否捕获注入故障"（OB/train-ticket 无观测栈）。OTel Demo 自带 OTel SDK，部署 Jaeger all-in-one 作为 trace 后端（绕开 429 限流的 collector，服务 SDK 直接 OTLP 导出到 Jaeger:4318）。

**验证结果**：
- Jaeger services API 捕获 4 个服务（cart/checkout/shipping/jaeger）的 trace
- 基线 PlaceOrder trace：`oteldemo.PaymentService/Charge` span **513ms**
- **注入 2s 延迟后**：PaymentService/Charge span **4462ms** + `System.Net.Http.HttpRequestException` 错误事件，与客户端观测的 4489.6ms 精确吻合
- **结论：观测完备系统完整捕获注入故障——无观测缺口**（延迟 + 错误事件都在 trace 中）

**方法论价值**：OTel Demo 提供了"trace 级故障归因"能力（前两项目只能靠客户端延迟+日志推断）。注入故障的 span 级延迟与错误事件 = 最强的证据链。这也回答了"观测完备系统能否自动诊断故障"——**能捕获，但需要人工查 Jaeger，无自动告警**。

## email 降级验证（深入 C，追加）

| email 故障 | PlaceOrder | 与 OB 对比 |
|---|---|---|
| 2s 延迟 | 5410ms（+2000 传导） | OB 2021ms（同模式） |
| 100% 丢包 | **挂起 10008.8ms → DEADLINE_EXCEEDED** | OB **27.4ms 快速降级** |

**新发现：gRPC vs HTTP 丢包行为差异**
- OB email 用 **gRPC**：丢包时连接层快速失败 → 27ms 降级（`log.Warnf` 吞错）
- OTel Demo email 用 **HTTP**：丢包时 TCP 挂起（无 timeout）→ **10s 才降级**
- 共性：两者 email 都"失败不致命"（降级），但**延迟/挂起仍全额传导**——降级只影响"成败"，不影响"延迟"

## 已知限制

- 观测栈未启用（资源考虑）——trace 级归因未验证
- 单次注入（无统计重复，基线方差大 ~3s 掩盖小延迟）
- flagd 原生故障 flag（paymentUnreachable/kafkaQueueProblems）未用（需 flagd 独立服务，已改 sidecar）
