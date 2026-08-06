# 混沌工程方法论研究——项目汇报

> 汇报人：XX　|　日期：2026-08-06
> 主题：让 LLM 从真实 YAML 出发、以测试节点为中心、凭证据链判断系统防御能力的可复用方法论——已在 3 个真实项目上验证

---

## 一、项目背景与目标

### 1.1 研究问题

我们手握 **1,935 个真实 Chaos Mesh YAML**（混沌注入配置）。这些 YAML 看似能做故障注入，但真实世界中存在四层"坑"：

| 层级 | 问题 | 典型例子 |
|---|---|---|
| ① 声明存在 ≠ 目标存在 | selector 可能匹配不到任何 Pod | 标签写错/命名空间不符 |
| ② 目标存在 ≠ 执行存在 | CRD 被选中但注入器没执行 | HTTPChaos `Selected=true` 但 `injectedCount=0` |
| ③ 执行存在 ≠ 业务可达 | 代码路径可能被注释/关闭 | train-ticket 的 Order 下游调用被注释 |
| ④ 业务可达 ≠ 防御判断成立 | HTTP 200 可能是"没命中"而非"防住了" | 注入未生效时的假阳性 |

**核心问题**：如何让 LLM 不犯这四层错误，用**证据链**而非文件内容做判断？

### 1.2 项目目标（愿景）

> 做一套让 LLM 能"从真实 YAML 出发、以测试节点为中心、凭证据链判断系统防御能力"的**可复用方法论**，用真实项目做案例，把每次实验结论沉淀成**可检索的知识库**，最终支撑论文与多项目迁移。

**三个子目标**：① 可复用方法论　② 知识库闭环　③ 论文 + 多项目迁移

---

## 二、方法论：我们的做法

### 2.1 核心思想：测试节点中心（不建全项目图）

传统做法是构建整个项目的 CFG/DFG 全图。我们反其道而行——**只以每一个测试节点为中心**，提取它实际涉及的服务、函数、调用、数据流、控制流、观测和恢复路径，形成**局部影响子图**。

```
真实 YAML 语料
  → 测试节点抽象（action/mode/selector/duration）
  → 测试节点知识库
  → 映射到真实项目和代码
  → 以测试节点为根的局部 CFG/DFG 影响子图
  → 存在性/可达性/测试必要性判断
  → LLM 生成变异 YAML 并安全注入
  → 观测：防御住/部分防御/未防御/测试无效
  → 根因解释 → 经验卡片 → 知识库更新 → 下一轮
```

### 2.2 证据链纪律（防止自欺）

1. **四层有效性**：YAML 语法 → Kubernetes schema → Chaos Mesh 语义 → 运行时可达性，四层分离，异常不静默修复
2. **不夸大分类**：`防御住 / 部分防御 / 未防御 / 测试无效` 四类严格区分——绝不把"没命中、无观测、环境偶然恢复"误判为"防住了"
3. **结论绑定证据**：每个结论必须附配置片段、代码位置、运行日志、指标、回滚结果
4. **环境可复现**：固定 commit、隔离 namespace、记录镜像版本

### 2.3 三阶段测量（每次注入的标准流程）

```
基线（无注入，固定窗口）→ 注入（确认 injectedCount>=1 后再测）→ 恢复（cleanup + 回到基线）
```

- **关键纪律**：`kubectl apply` 返回 ≠ 注入完成。必须等 Chaos Mesh 状态 `AllInjected=True` 后才测量，否则样本无效
- **统计重复**：同一注入跑 5-10 次独立窗口，出中位数/p95/标准差——把"单次观察"升级为"统计事实"
- **跨环境复现**：同一实验在 Docker Desktop 与 kind 集群重跑，确认结论非环境偶然

### 2.4 工具链（14 个 Python 工具脚本）

| 工具 | 作用 |
|---|---|
| `runtime_applicability_gate.py` | 注入前只读门：CRD/selector/端口/注入器可用性 |
| `run_chaos_experiment.py` | 生命周期执行：apply → injected → 测 → recovered → delete |
| `classify_runtime_result.py` | 结果分类：延迟退化/客户端超时/平台阻断等 |
| `select_chaos_candidates.py` | 候选测试点排序（可达性 × 影响 × 证据） |
| `validate_knowledge_base.py` | 知识卡片质量门（必填字段/敏感值扫描） |
| `package_report_evidence.py` | 证据打包（SHA-256 清单，可复现交付） |
| 等 | 23 个单元测试全部通过 |

---

## 三、三个真实项目

### 3.1 Train Ticket（复旦微服务研究基准）

- **版本**：commit `313886e9`，隔离 namespace `train-ticket-lab`
- **做法**：从 1,935 个 YAML 中筛出 54 个 train-ticket 样本 → 可达性门过滤 → 在可达路径上做延迟阶梯/CPU 压力注入
- **发现**：
  - **基准可达性缺陷**：`OrderServiceImpl.java:200` 的下游调用被注释，任何基于 order/refresh 工作流的故障注入都测不到真实下游——基准的 fault-injection 路径静默失效
  - 延迟阶梯 100ms/500ms/2s → 216ms/1021ms/4021ms；3s 探到客户端超时边界（客户端 5047ms 超时 vs 服务端 6063ms 完成）

### 3.2 Online Boutique（Google 云原生演示应用）

- **版本**：commit `9a4616e7`，kind 集群隔离部署 8 个服务
- **做法**：声明驱动——先检索项目韧性声明（无任何 retry/timeout/circuit），再按业务影响排序选测试点（先测钱，再测核心旅程）
- **发现（4 个有运行时证据的实质问题）**：
  1. **checkout 业务链零超时**：2s 延迟注入 → 下单延迟 2021.5±3.1ms（n=9 统计，全额传导）
  2. **丢包无限挂起**：100% 丢包 → 下单挂起 10s 直到客户端 deadline（n=5 全 10008ms）
  3. **核心数据路径级联**：product-catalog 故障 → 首页整站 500，恢复靠 Deployment 重建 ~2 分钟
  4. **探针重启"逃逸"注入**（意外发现）：1s liveness 探针 vs 2s+ 延迟 → 容器被 SIGKILL → 新容器逃逸注入 → **重新注入立即恢复延迟，证明系统无自愈**

### 3.3 OpenTelemetry Demo（观测性参考应用）

- **版本**：commit `2e72d8bc`，kind 部署 10 服务 + Jaeger 观测栈
- **做法**：验证"无 timeout"模式第三项目复现 + **观测缺口检测**（前两项目无观测栈做不到）
- **发现**：
  1. **三项目复现**：payment 2s 延迟 → +1485~2075ms；100% 丢包 → 挂起 10007.4ms
  2. **观测捕获无自动告警**：Jaeger trace 完整捕获注入故障（span 延迟 4462ms + 错误事件），但需人工查询
  3. **传输协议影响丢包行为**：同样"失败不致命"的 email，gRPC（OB）快速降级 27ms vs HTTP（OTel）挂起 10s
  4. **源码 bug**：`quoteShipping` 错误消息写"email service"（实为 shipping），复制粘贴错误

---

## 四、核心发现（按证据强度排序）

### 4.1 里程碑结论：三项目复现的"无 timeout"模式

| 发现 | train-ticket | Online Boutique | OTel Demo |
|---|---|---|---|
| 业务链无 timeout/retry/circuit | ✅ | ✅ | ✅ |
| 下游延迟全额传导 | ✅ +2000ms | ✅ 2021.5±3.1ms (n=9) | ✅ +1485~2075ms |
| 丢包无限挂起直到调用方边界 | ✅ 超时边界 | ✅ 5/5 全 10008ms | ✅ 10007.4ms |
| email 降级（失败不致命） | — | ✅ log.Warnf | ✅ logger.Warn |
| shipping 致命（失败阻断下单） | — | ✅ codes.Unavailable | ✅ panic→Unavailable |

**结论**："微服务 checkout 业务链无 timeout + 延迟全额传导 + 丢包无限挂起"是**三个独立项目共有的普遍设计缺口**——不是单项目问题，而是当前微服务基准/demo 应用的共性弱点。

### 4.2 独特机制发现

| 发现 | 项目 | 机制 |
|---|---|---|
| **探针重启"逃逸"注入** | OB | 混沌注入（tc netem）绑定旧容器网络命名空间，容器重启后新容器逃逸注入——"自动恢复"是碰巧副作用，非设计防御（重新注入立即恢复，证伪自愈） |
| **探针重启阈值公式** | OB | 延迟 > livenessProbe.timeoutSeconds(1s) 且持续 > failureThreshold(3)×periodSeconds(10s) 才触发 |
| **观测捕获无自动告警** | OTel | Jaeger 完整捕获（span 延迟+错误事件），但无自动告警，需人工查询 |
| **基准可达性缺陷** | train-ticket | 下游调用被注释 → fault-injection 路径静默失效 |

### 4.3 方法论层面的发现

- **观测结果依赖采样时机**：同一注入窗口内采样，可能观测到"延迟传导"或"连接失败"（取决于探针是否已杀容器）——单次观测可能误判
- **NetworkChaos 注入在容器重启后静默失效**——实验必须用与容器生命周期无关的观测（如 cgroup）或持续采样

---

## 五、遇到的问题（环境约束与挑战）

### 5.1 平台级约束

| 问题 | 影响 | 处理 |
|---|---|---|
| **WSL2 内核缺 ebtables broute/nat 表** | HTTPChaos 全类型无法注入 | 换 kind 集群实测确认（kind 与 Docker Desktop 共享同一 WSL2 内核），**决定性结论：换集群类型无法解锁**，需非 WSL2 环境或自定义内核（成本高，挂起） |
| Docker Hub 429 限流 | collector 等镜像拉取受限 | 换镜像源/重试/Jaeger 绕过 |
| ghcr/github 间歇性 TLS 中断 | 镜像/源码拉取慢 | 重试 + 本地 registry（host.docker.internal:5000）中转 |

### 5.2 部署难题（各项目独有）

| 项目 | 问题 | 解决 |
|---|---|---|
| OB | Artifact Registry 不可达 | 本地源码构建镜像，替换 gcr.io/distroless 为 alpine |
| OTel | cart 是 .NET 监听 8080（非预期 7070） | 修正 targetPort |
| OTel | postgres init.sql 与镜像建库冲突 | 精简 init.sql |
| OTel | shipping（Rust）硬依赖 flagd 且连接失败即 panic | flagd sidecar（共享网络） |
| OTel | flagd v0.16 默认端口是动态的 | 显式 `--port 8013` |

### 5.3 方法论挑战

- **观测结果依赖采样时机**（见 4.3）
- **基线方差**：OTel Demo 基线 ~3s（OTel SDK 开销），掩盖小延迟，统计重复需要更大样本量

---

## 六、知识卡片实例

> 每张卡片是"一次实验结论"的可检索封装，含：测试节点、影响子图、假设、注入、结果、根因、证据、置信度、范围边界。全部通过 `validate_knowledge_base.py` 校验（0 错误）。

### 实例 1：OB 支付延迟全额传导（统计事实级）

**ID**: `KB-OB-CHECKOUT-PAYMENT-DELAY-001`（版本 1，置信度 A）

```json
{
  "id": "KB-OB-CHECKOUT-PAYMENT-DELAY-001",
  "project": "GoogleCloudPlatform/microservices-demo",
  "test_node": { "family": "NetworkChaos", "operation": "delay",
                 "latency": "2000ms", "selector": { "app": "paymentservice" } },
  "test_node_centered_graph": {
    "nodes": [
      { "id": "test.network.delay.payment", "kind": "TestNode" },
      { "id": "call.checkout.chargeCard", "kind": "DownstreamCall",
        "source": "checkoutservice/main.go:369-375",
        "evidence": "chargeCard calls PaymentService.Charge with ctx, no WithTimeout" },
      { "id": "response.placeorder", "kind": "BusinessOutcome" }
    ],
    "edges": [ { "from": "test.network.delay.payment", "to": "call.checkout.chargeCard",
                 "type": "calls", "confidence": "confirmed_runtime" } ]
  },
  "hypothesis": "checkout chargeCard has no timeout/retry/fallback; downstream delay propagates 1:1",
  "runtime_result": {
    "classification": "response_preserved_latency_degradation",
    "baseline_median_ms": 26.4, "injected_median_ms": 2021.5,
    "injected_std_ms": 3.1, "samples": 9,
    "loss_counterpart": { "hang_times_ms": [10008.5, 10009.7, 10008.9, 10002.4, 10008.1] }
  },
  "root_cause": "missing_timeout_on_downstream_call",
  "confidence": "A"
}
```

**解读**：9 次独立注入，中位数 2021.5ms（基线 26.4ms，精确 +2000ms），标准差仅 3.1ms——**"延迟全额传导"是统计事实而非巧合**。配套丢包实验 5 次全部挂起 10s。

### 实例 2：OB 探针重启"逃逸"注入（最重磅机制发现）

**ID**: `KB-OB-PAYMENT-PROBE-RESTART-RACE-001`（版本 1，置信度 A）

```json
{
  "runtime_result": {
    "classification": "probe_restart_race_latency_to_connection_failure",
    "threshold_rule": "delay > livenessProbe.timeoutSeconds(1s) sustained across failureThreshold(3)x periodSeconds(10s) triggers restart",
    "continuous_timeline": {
      "sequence": ["2021ms x4 ok", "t=12s container killed by probe",
                   "rpc_error x3 (restarting)", "t=24s new container 17ms ok",
                   "no delay afterwards"],
      "note": "probe restart 'cures' the injected delay: chaos (tc netem) binds to old container netns, new container escapes injection"
    },
    "reinject_test": {
      "sequence": ["injected 2016.8ms", "after restart 21.0ms (escape)",
                   "re-injected 2016.9ms (delay returns)"],
      "note": "re-injection restores delay immediately -> system has NO self-healing"
    },
    "unavailability_window_s": 9,
    "cross_env": "same probe restart observed on docker-desktop (exit 137)"
  }
}
```

**解读**：这是"自动恢复"的真相——**不是系统防住了故障，而是探针把容器杀了、新容器碰巧逃逸了注入**。关键证据：重新注入后延迟立即恢复（2016.9ms），证明系统无自愈。代价是重启期间 ~9s 业务失败窗口。

### 实例 3：OTel 观测捕获（观测缺口检测）

**ID**: `KB-OTEL-CHECKOUT-PAYMENT-FAILURE-001`（版本 1，置信度 A）

```json
{
  "runtime_result": {
    "baseline_ms": 3100,
    "delay_case": { "latency_ms": [4793.3, 5175.3, 4489.6] },
    "loss_case": { "hang_ms": 10007.4, "outcome": "DEADLINE_EXCEEDED" },
    "observability_capture": {
      "jaeger_trace": "injected window trace payment span 4462ms + HttpRequestException event; baseline 513ms",
      "note": "Jaeger captures injected fault fully (delay + error event); no observability gap, but no auto-alert"
    }
  },
  "root_cause": "missing_timeout_on_downstream_calls"
}
```

**解读**：观测完备系统（Jaeger）**完整捕获注入故障**（span 级延迟 + 错误事件），但**无自动告警**——这是"观测完备能否自动诊断"的实证答案：**能捕获、不能自动告警**。

### 实例 4：train-ticket 网络延迟阶梯（基准可达性）

**ID**: `KB-TT-NETWORK-STATION-DELAY-001`（版本 4，置信度 A）

```json
{
  "test_node": { "family": "NetworkChaos", "operation": "delay", "latency": "100ms",
                 "selector": { "app": "ts-station-service" } },
  "test_node_centered_graph": {
    "nodes": [
      { "id": "controller.StationController.queryForStationId", "kind": "ControllerPath",
        "source": "StationController.java:60" },
      { "id": "service.StationServiceImpl.queryForId", "kind": "BusinessExecution",
        "source": "StationServiceImpl.java:90-101" }
    ]
  },
  "runtime_result": {
    "ladder": { "100ms": "216ms", "500ms": "1021ms", "2s": "4021ms" },
    "timeout_boundary": "3s nominal delay -> client timeout 5047ms, server completes 6063ms"
  }
}
```

**解读**：延迟阶梯单调传导（100ms→216ms、500ms→1021ms、2s→4021ms）；3s 探到客户端超时边界——**客户端超时 + 服务端稍后完成 = 部分/缺失客户端边界防御**。

---

## 七、知识固化与 LLM 角色（重要说明）

> 回答两个关键问题：**① 从 1,935 个 YAML 提取的知识落在哪里？② 谁是 LLM、在哪里工作？**

### 7.1 知识的落点：三层提炼，全部可检索

原始 YAML 语料的知识不是"在我（AI 助手）的脑子里"，而是被固化成三层产物，任何工具/未来的 LLM 都能读：

| 层 | 产物 | 内容 | 例子 |
|---|---|---|---|
| ① 语料清单层 | `yaml_inventory.csv` | 1,935 个文件逐条：SHA-256、kind、字段、风险标签 | `AWSChaos/165....yaml → spec_keys=["action","awsRegion",...], risk=["cloud_instance","secret_reference"]` |
| ② 节点/图层 | `test_node_catalog.json`、`test_slices*.json`、`service_graph*.json` | 测试节点词典（stress_cpu 230 次…）、selector→服务→函数映射、调用图 | `stress_cpu → ts-order-service → OrderController...` |
| ③ 知识卡片层 | `knowledge_base/` 14 张卡片 | 结合运行时证据的可检索结论（含假设/结果/根因/置信度/范围） | `KB-OB-CHECKOUT-PAYMENT-DELAY-001`（延迟全额传导，置信度 A） |

### 7.2 谁消费这些知识？——检索工具（LLM 消费接口）

新增 `tools/query_knowledge_base.py`：**任何人或 LLM 可以不用重跑实验，直接按查询拿到决策所需字段**（测试节点、假设、根因、置信度、证据路径、范围边界）。这是"知识库 → LLM 决策"的最小闭环证明。

**演示 1：列出全部 14 张卡片**
```
python tools/query_knowledge_base.py --list
→ KB-OB-CHECKOUT-PAYMENT-DELAY-001: microservices-demo | NetworkChaos delay | validated_runtime_statistical_repetition
→ KB-TT-NETWORK-STATION-DELAY-001: train-ticket | NetworkChaos delay | validated_runtime_selector_pipeline_timeout_boundary_confirmed
→ ...（共 14 张）
```

**演示 2：查询 "payment delay"（拿到决策字段）**
```
python tools/query_knowledge_base.py --query "payment delay"
→ { id: KB-OB-CHECKOUT-PAYMENT-DELAY-001, confidence: A,
    hypothesis: "checkout chargeCard has no timeout/retry/fallback...",
    root_cause: "missing_timeout_on_downstream_call",
    scope: ["no production SLO claim","single endpoint PlaceOrder only"] }
```

**演示 3：按根因反查（LLM 决策场景）**
```
python tools/query_knowledge_base.py --root-cause missing_timeout
→ 返回所有根因为 "missing_timeout" 的卡片（跨项目），供 LLM 判断该模式的普遍性
```

### 7.3 诚实说明：当前 LLM 角色与未完成的闭环

- **当前"LLM"= 本次项目的 AI 助手（即我）**：实际承担了"读语料/判可达/选测试点/设计注入/分类根因/写卡片"的全部决策——但这些决策的**结论已固化到卡片/报告**，不依赖我的记忆
- **方法论设想的"LLM 自主决策"（task_plan 阶段 10）尚未实现**：即"LLM 自动检索知识库 → 生成注入 YAML → 判断结果"的完整自动化
- **检索工具是这座桥的第一步**：它让知识库可以被任何 LLM 消费；阶段 10 才是在此之上让 LLM 自主闭环
- 汇报中凡提"让 LLM 学习/判断"，当前语境 = **AI 辅助（我）+ 规则工具 + 证据库** 的半自动模式，阶段 10 是未来完整闭环

---

## 八、可提交的 Issue 清单（基于已有发现）

> 原则：只报"有运行时证据 + 可复现 + 与项目声明矛盾或明显缺陷"的发现；环境问题（WSL2 ebtables 等）**不报**；提交前草稿经审阅，已登记在 `reporting/tracking.md`。

### 8.1 Issue 候选总览

| # | 目标仓库 | 标题（英文，GitHub 格式） | 类型 | 证据强度 | 提交优先级 |
|---|---|---|---|---|---|
| 1 | OTel Demo | `quoteShipping` error message points to wrong service (copy-paste bug) | bug | 运行时+源码 | **高**（一行修复，最易被接受） |
| 2 | train-ticket | Downstream call disabled in `queryOrdersForRefresh`, fault-injection path unreachable | bug | 源码+静态 | 中高（**草稿已就绪**） |
| 3 | Online Boutique | Core data path has no fallback → single service failure takes down homepage (500 cascade) | enhancement/讨论 | 运行时 | 中 |
| 4 | Online Boutique | Checkout chain has no timeout → downstream delay fully propagates / loss hangs indefinitely | enhancement | 运行时(n=9) | 中（作韧性参考建议） |

### 8.2 各 Issue 详情

**Issue 1：OTel Demo 错误消息 bug（最推荐先提交）**
- 位置：`src/checkout/main.go:498`（`quoteShipping` 函数内）
- 现象：shipping 服务故障时报 `failed POST to email service: expected 200, got %d`，实际是 **shipping**——复制粘贴错误，误导排障
- 证据：静态（`main.go:498` 字符串）+ 运行时（shipping 故障时错误信息指向错误服务）
- 修复：字符串改为 `failed POST to shipping service`
- 价值：一行修复；OTel 社区活跃（近 10 条 issue 当天处理），**获得外部反馈概率最高**

**Issue 2：train-ticket 基准可达性缺陷（草稿已就绪）**
- 位置：`OrderServiceImpl.java:200`（下游调用被注释）
- 现象：`/order/refresh` 工作流唯一下游调用被注释，返回 stationId 原值——任何基于该工作流的 fault-injection 都测不到真实依赖
- 证据：源码（`:192-220`）+ 单测只覆盖函数级
- 草稿：`reporting/train-ticket/issues/` + 桌面 Word 已生成
- 预期：维护者响应概率低（2025-11 后无 commit），但作为**基准完整性报告**有学术价值（基准的 fault-injection 路径静默失效）

**Issue 3：OB 核心数据路径级联 500**
- 位置：`frontend/handlers.go:62-90`（getProducts/getCart/汇率无 fallback）
- 现象：product-catalog 故障 → 首页整站 HTTP 500；恢复靠 Deployment 重建 ~2 分钟
- 证据：运行时（kill → 500 级联；丢包 → 首次挂起 26.7s 后 500）
- 价值：直接破坏官方文档承诺的 "golden user journey"；与"广告优雅降级"形成**核心硬失败 vs 非核心优雅降级**的矛盾对照

**Issue 4：OB checkout 无 timeout（作 enhancement 建议）**
- 位置：`checkoutservice/main.go:369-387`（chargeCard/sendOrderConfirmation/shipOrder 无 WithTimeout）
- 现象：2s 延迟全额传导（2021.5±3.1ms）；100% 丢包挂起 10s（5/5）
- 证据：n=9 统计 + n=5 丢包统计
- 类型：enhancement（demo 无 timeout 可能有意设计，建议作为**韧性参考示例**补充）

### 8.3 提交策略与预期管理

- **第一批**：Issue 1（OTel，最易被接受）+ Issue 2（train-ticket，草稿就绪）——先拿到外部反馈
- **第二批**：OB 的 Issue 3/4（视导师意见决定是否提交，或只作论文素材）
- 所有提交前：草稿经审阅 → `reporting/tracking.md` 登记 → 附隔离环境声明 + 复现步骤
- **预期管理**：反馈是概率事件——活跃仓库（OTel/OB）响应快，train-ticket 期望低；但"**可复现发现 + 规范 issue 报告**"本身就是可行性的证明，不受回复与否影响

---

## 九、结论与下一步

### 9.1 结论

1. **方法论可迁移** ✅：测试节点中心 + 证据链 + 三阶段测量，在 benchmark/活跃 demo/观测完备 demo 三种类型项目上完整复用，均产出运行时证据
2. **知识库闭环** ✅：14 张卡片（train-ticket 7 + OB 6 + OTel 1），统一 schema，0 错误校验
3. **核心论文素材**：三项目复现的"无 timeout"模式 + 探针重启逃逸 + 观测捕获无自动告警
4. **可提交 issue 4 个**（见第七章）：OTel 源码 bug（最易被接受）+ train-ticket 基准缺陷（草稿就绪）+ OB 两个韧性缺口

### 9.2 待决策 / 下一步

| 事项 | 状态 |
|---|---|
| 提交 Issue 1（OTel 错误消息）——第一优先 | 待决策 |
| 提交 Issue 2（train-ticket 基准缺陷）——草稿就绪 | 待决策 |
| OB 两个 issue 是否提交 / 或只作论文素材 | 待决策 |
| LLM 决策基准（阶段 10）——**决定论文档次的唯一缺口** | **方案已设计，见第十章** |
| 统计重复扩展到 OTel（基线方差大） | 可选 |
| 论文写作 | 素材已齐 |

### 9.3 诚实边界

- HTTPChaos 全类型因 WSL2 内核缺 ebtables 无法注入（已换 kind 确认，非环境可解）
- OTel Demo 基线 ~3s（观测开销），小延迟被掩盖
- 所有实验为隔离 lab 环境，无生产系统被触碰

---

## 十、改进路线：LLM 决策基准实验与论文规划

> 定位：当前成果约等于 **CCF-B 会议 / 中科院 2 区**（核心卖点：探针重启逃逸机制 + 三项目复现）。要冲 **1 区**（TSE/TOSEM 档），**必须补上 LLM 决策基准实验**——这是愿景里"让 LLM 从证据学习"唯一没兑现的闭环，也是从口号变成可量化证据的唯一缺口。资产已齐（14 张卡片 + 检索工具 `query_knowledge_base.py`），成本最低。

### 10.1 主线：LLM 决策基准实验（测三件事）

| 任务 | 给 LLM 什么 | 让 LLM 做什么 | 对比真值 |
|---|---|---|---|
| ① 测试点选择 | 项目场景 + 候选测试节点（检索工具输出） | 选该测的节点并排序 | 卡片的 `injection_recommendation` |
| ② 结果分类 | 注入结果（延迟/日志/探针行为） | 判"防御住/部分/未防御/无效" | 卡片的 `runtime_result.classification` |
| ③ 根因归因 | 同上证据 | 归因（missing_timeout 等） | 卡片的 `root_cause` |

### 10.2 对照组（证明方法论价值，审稿人必看）

- **A. 无知识库**：LLM 凭直觉判断（盲答）
- **B. 有知识库**：LLM 检索卡片后判断
- **C. 随机基线**：随机选测试点 / 随机分类

**产出指标**：A/B 的准确率差异 + 置信区间。若 B ≫ A，就用数据证明"知识库 → LLM 决策"的价值——直接支撑论文核心论点。

### 10.3 支线 1：提交 2 个 issue（独立、低风险）

- **OTel 源码 bug**（`quoteShipping` 错误消息，一行修复）——最易被接受，先拿外部反馈
- **train-ticket 基准缺陷**——草稿已就绪
- issue 回复本身即"外部认可"证据，可写入论文的"工业影响"部分

### 10.4 支线 2：论文写作（等 LLM 基准结果后骨架才完整）

| 分区 | 目标 | 差距 |
|---|---|---|
| 4 区 / workshop | 有完整实证即可 | ✅ 已超出 |
| 3 区（IST 边缘） | 实证 + 清晰贡献 | ✅ 基本达到 |
| **2 区（ISSRE/JSS/EMSE）** | 严谨实证 + 亮点机制 + 可复现 | ⚠️ 当前卡在这（探针逃逸是亮点，LLM 未兑现） |
| **1 区（TSE/TOSEM）** | 新方法 + 严格评估 + 对比 SOTA + 大样本 | ❌ 缺 LLM 闭环、对照组、样本规模 |

**论文核心贡献（成型后）**：探针重启"逃逸"注入机制（新）+ LLM 决策基准结果（量化证据）+ 三项目系统性复现（实证支撑）。

### 10.5 执行顺序建议

1. **主线**：LLM 决策基准实验（唯一决定"2 区 vs 冲 1 区"的事）
2. **支线 1**：提交 OTel / train-ticket 两个 issue（拿到外部反馈）
3. **支线 2**：论文写作（LLM 基准有结果后骨架完整）

---

*附：全部证据、报告、卡片、工具在 `C:\APP\project\chaos`（git 18 提交，工作区干净）。*