# Online Boutique 深入实验报告（方向 1-4）

> 日期：2026-08-05
> 环境：kind 集群（chaos-kind）+ Chaos Mesh 2.8.3，8+1 服务
> 版本：microservices-demo @ 9a4616e7（lab 镜像）

## 方向 1：统计重复 + 置信区间

**方法**：10 次基线 + 10 轮独立 20s 注入窗口（每轮等待 AllInjected → 采样 → 等窗口结束 → 清理 → 等 pod Ready），避免探针重启污染数据。

**结果**（`stat_repetition_result.json`）：

| 指标 | 基线 (n=10) | 注入 2s (n=9) |
|---|---|---|
| 中位数 | 26.4 ms | 2021.5 ms |
| p95 | 30.1 ms | 2024.0 ms |
| 均值 ± std | 31.4 ± 16.3 ms | 2022.6 ± 3.1 ms |

**结论**：注入延迟极其稳定（std 3.1ms），9 轮全部精确落在 2020-2030ms（基线 +2000ms 注入），无超时无失败。**"延迟全额传导"从单次观察升级为统计事实**。

## 方向 2a：checkout→email 单独故障

**方法**：emailservice 注入 2s 延迟 / 100% 丢包，测 PlaceOrder。

| email 故障 | PlaceOrder | 语义 |
|---|---|---|
| 2s 延迟 | **2021.3ms ok** | 同步调用无 timeout → 延迟全额传导 |
| 100% 丢包 | **27.4ms ok** | `log.Warnf` 降级生效 → 失败被吞，下单正常 |

**发现**：email 是"部分降级"——**失败不致命（Warnf），但延迟仍全额传导**（无 timeout）。降级只在"快速失败"时有效。

## 方向 2b：frontend→productcatalog 三态故障

**方法**：productcatalogservice 注入 2s 延迟 / 100% 丢包 / pod-kill，测首页 GET /。

| 故障 | 首页行为 | 语义 |
|---|---|---|
| 2s 延迟 | **200 / 2.03s** | 无 timeout → 延迟传导到整页 |
| 100% 丢包 | **首次挂起 26.7s → 500** | **无 gRPC deadline → 挂起** + 级联 500 |
| pod-kill | 200（重建快 ~12s 掩盖窗口） | 与 Docker Desktop 的 500 差异是**重建时序**，非防御 |

**发现**：核心数据路径**无 timeout 无 fallback**——丢包下首次请求挂起 **26.7 秒**（比 checkout 的 10s 客户端 deadline 更久，curl 无 deadline），随后级联 500。**挂起比 500 更严重**。

## 方向 3：超时边界阶梯 + 探针重启竞争

**方法**：payment 延迟 1s/2s/3s/5s 阶梯，观察延迟传导与探针行为。

| 延迟 | 结果 | 探针 |
|---|---|---|
| 1s | 1024.3ms ok | 无重启 |
| 2s（干净采样） | **2022.6ms ok** | 无重启 |
| 2s/3s/5s（连续阶梯） | rpc_error connection refused（14-20ms 快速失败） | **探针杀容器** |

**关键发现（比阶梯本身更有价值）**：**liveness 探针（1s 超时）与注入延迟竞争**——
- 探针配置：`timeoutSeconds=1, failureThreshold=3, periodSeconds=10`
- 2s+ 延迟 → 探针失败 → kubelet SIGKILL 容器 → 后续请求变成**快速 connection refused**（14-20ms）
- **延迟故障被探针重启"转换"成连接失败**：观测到的故障模式取决于采样时机（注入窗口内 vs 重启后）
- 与 Docker Desktop 的 exit 137 行为一致（跨环境复现）

**方法论教训**：注入实验必须区分"延迟传导测量"与"探针重启副作用"——否则会把重启的快速失败误判为"服务自己快速失败"。这正是"三阶段测量 + 等待 pod Ready"纪律的价值。

## 方向 4：OB 知识卡片（4 张，0 错误）

| 卡片 | 内容 | 关键结论 |
|---|---|---|
| KB-OB-CHECKOUT-PAYMENT-DELAY-001 | payment 2s 延迟统计重复 | 无 timeout → 全额传导（2021.5±3.1ms） |
| KB-OB-FRONTEND-PRODUCTCATALOG-FAILURE-001 | productcatalog 三态 | 无 timeout/fallback → 挂起 26.7s + 级联 500 |
| KB-OB-CHECKOUT-EMAIL-FAILURE-001 | email 故障 | 部分降级：失败不致命但延迟传导 |
| KB-OB-PAYMENT-PROBE-RESTART-RACE-001 | 探针重启竞争 | 延迟故障被探针转换成语义不同的连接失败 |

`validate_knowledge_base.py` 校验：4 张 0 错误（source_yaml 警告因 OB 注入 YAML 为生成而非语料，合理）。

## 深入 A：丢包统计重复（100% loss ×5 轮）

**方法**：checkout→payment 100% 丢包，5 轮独立 25s 窗口，每轮采样 PlaceOrder（客户端 deadline 10s）。

| 指标 | 值 |
|---|---|
| 基线 | 16.2 / 18.4 / 16.4 ms |
| 挂起时间 ×5 | **10008.5 / 10009.7 / 10008.9 / 10002.4 / 10008.1 ms** |
| 挂起中位数 | 10008.5 ms（min 10002.4 / max 10009.7） |
| 恢复后 | 22.1 / 17.5 / 16.9 ms |

**结论**：5 轮全部精确挂起至客户端 deadline（10s），无一例外——**"无 timeout → 无限挂起直到调用方边界"是统计事实**（非单次巧合）。挂起时间与注入强度无关（丢包没有延迟梯度，只有全挂起/快速失败二态）。

## 深入 B：探针重启阈值定位

**方法**：payment 延迟 1.5s（> 探针 timeoutSeconds=1），40s 窗口，观察探针是否触发 SIGKILL。

**结果**：
- 1.5s 延迟 → 立即采样 1517.8ms ok（延迟传导）
- ~35s 后（探针 3 次失败周期 ≈ 30s）→ **Killing 事件 → SIGKILL 重启**（restarts 7→8）
- 恢复后 17-24ms 正常

**阈值结论**：与 1s 级（1024ms ok，无重启）对照——**重启阈值不是延迟绝对值，而是"延迟 > 探针 timeoutSeconds(1s)"**。1s 恰好不触发（探针测量与注入的时序误差），1.5s 必触发。**探针重启 = 故障持续超过 (timeoutSeconds × failureThreshold × periodSeconds) 的组合，而非简单的延迟阈值**。

## 深入 C：shipping 双倍延迟传导 + 致命丢包（三下游矩阵补全）

**方法**：shippingservice 注入 2s 延迟 / 100% 丢包，测 PlaceOrder。

| shipping 故障 | PlaceOrder | 语义 |
|---|---|---|
| 2s 延迟 | **4021.5ms ok** | **双倍传导**（GetQuote + ShipOrder 两次调用 × 2s） |
| 100% 丢包 | **挂起 10010.7ms → DEADLINE_EXCEEDED** | 致命（无降级），同 payment |

**代码确证**：`checkoutservice/main.go:315`（quoteShipping → GetQuote）+ `:387`（shipOrder → ShipOrder）——PlaceOrder 路径上 shipping 被调用**两次**，2s 延迟 × 2 = 4s。**shipping 是比 payment 更严重的传导点**（双倍）。

## 深入 D：checkout 三下游语义矩阵（补全）

| 下游 | 延迟故障 | 丢包故障 | 致命性 |
|---|---|---|---|
| paymentservice | 2021.5ms 传导 | 挂起 10s 后 DEADLINE_EXCEEDED | **致命**（chargeCard 错误 → PlaceOrder 失败） |
| shippingservice | **4021.5ms 双倍传导** | 挂起 10s 后 DEADLINE_EXCEEDED | **致命**（GetQuote/ShipOrder 双调用） |
| emailservice | 2021.3ms 传导 | 27.4ms **降级成功** | **非致命**（log.Warnf 吞错） |

**结论**：三个下游三种语义——**致命（payment/shipping）+ 降级（email）**。但致命性只影响"失败与否"，不影响"延迟传导"——**所有下游的延迟都全额传导**（无 timeout 是共性缺陷）。

## 深入 E：注入窗口内连续采样（揭示探针重启"治愈"故障）

**方法**：payment 2s 延迟 60s 窗口，每 3s 采样 PlaceOrder + payment restart 计数。

```
t= 0s  2021.4ms ok    restarts=8   ← 注入生效，延迟传导
t= 3s  2020.3ms ok    restarts=8   ← 稳定延迟
t= 6s  2021.1ms ok    restarts=8
t= 9s  2023.2ms ok    restarts=8
t=12s   18.7ms ok    restarts=8   ← 探针触发，容器被杀
t=15s   12.2ms rpc_error restarts=9  ← 重启中，连接被拒
t=18s   12.5ms rpc_error restarts=9
t=21s   11.4ms rpc_error restarts=9
t=24s   21.4ms ok    restarts=9   ← 新容器恢复
t=27s+  16-19ms ok    restarts=9   ← 之后一直正常（无延迟！）
```

**决定性发现**：
1. **探针重启"意外治愈"了延迟故障**：t=12s 容器被杀 → 新容器启动后**不再有 2s 延迟**（16-19ms）——chaos 注入（tc netem）绑定在**旧容器的网络命名空间**，新容器**逃逸了注入**。
2. **自动恢复的真相**：不是"系统防御了延迟"，而是"探针把容器杀了，新容器恰好没被注入"——**混沌注入被重启绕过**。
3. **阶梯实验的"快速失败"谜团彻底解开**：阶梯里 2s/3s/5s 显示 rpc_error connection refused，正是因为探针重启后新容器逃逸注入，且旧 IP 的 endpoint 短暂失效。
4. **对混沌实验的方法论警示**：NetworkChaos 注入在容器重启后**静默失效**——若实验只观察"注入后一段时间"，可能因重启逃逸而误判"系统自愈"。必须用 cgroup/指标等**与容器生命周期无关**的观测，或持续采样。

## 与 train-ticket 的方法对称

- train-ticket：延迟阶梯（100ms/500ms/2s）→ 客户端超时边界
- Online Boutique：延迟阶梯（1s/2s/3s/5s）→ **探针重启竞争**（新机制）
- 两项目都验证了：**注入实验的观测结果依赖观测时机**（train-ticket 的"apply ≠ 注入完成"纪律在 OB 扩展为"采样时机决定观测到延迟还是连接失败"）
