# 三项目跨项目对照总结（方法论可迁移证据）

> 日期：2026-08-06
> 目的：把三个真实项目的发现合成方法论的核心证据——"测试节点中心 + 证据链"方法论在**不同类型**的真实系统上完整复用

## 项目谱系（类型覆盖）

| 项目 | 类型 | 观测能力 | 维护活跃 | 版本 |
|---|---|---|---|---|
| train-ticket | 微服务研究基准（Fudan SELab） | 无（自建 cgroup/日志） | 低（2025-11） | 313886e9 |
| Online Boutique | 云原生演示应用（Google） | 无（自建观测） | 高（2026-08-04） | 9a4616e7 |
| OpenTelemetry Demo | 观测性参考应用（OTel 社区） | 完整 OTel 栈 | 高（2026-08-04） | 2e72d8bc |

## 核心模式：三项目复现的"checkout 无 timeout"发现

| 发现 | train-ticket | OB | OTel Demo |
|---|---|---|---|
| 业务链无 timeout/retry/circuit | ✅ 静态+运行时 | ✅ 静态+运行时 | ✅ 静态+运行时 |
| 下游延迟 1:1 全额传导 | ✅ +2000ms | ✅ 2021.5±3.1ms (n=9) | ✅ +1485~2075ms |
| 丢包无限挂起直到调用方边界 | ✅ 超时边界 | ✅ 5/5 全 10008ms | ✅ 10007.4ms |
| email 降级（失败不致命） | — | ✅ log.Warnf | ✅ logger.Warn |
| shipping 致命（失败阻断下单） | — | ✅ codes.Unavailable | ✅ panic→Unavailable |
| 传输协议影响丢包行为 | — | gRPC 27ms 快速降级 | HTTP 挂起 10s |

**结论**："微服务 checkout 业务链无 timeout + 延迟全额传导 + 丢包无限挂起"是**三个独立项目共有的普遍设计缺口**——不是单项目问题，而是当前微服务基准/demo 应用的共性弱点。这本身就是可发表的方法论结论。

## 独特机制发现（各项目独有）

| 发现 | 项目 | 机制 |
|---|---|---|
| 探针重启"逃逸"注入 | OB | 1s liveness 探针 vs 2s+ 延迟 → SIGKILL 容器 → 新容器逃逸 tc netem 注入；非自愈（重新注入立即恢复） |
| 探针重启阈值公式 | OB | 延迟 > timeoutSeconds 持续 > failureThreshold×periodSeconds 才触发 |
| 观测捕获无自动告警 | OTel Demo | Jaeger 完整捕获注入故障（span 延迟+错误事件），但需人工查询 |
| 源码 bug（错误消息误导） | OTel Demo | quoteShipping 错误写 "email service"（实为 shipping） |
| 基准可达性缺陷 | train-ticket | Order 下游调用被注释（fault-injection 路径静默失效） |

## 方法论验证（三项目各证明一环）

| 方法论环节 | 证明项目 | 证据 |
|---|---|---|
| 测试节点中心静态映射 | 全部 | 每个项目 1 小时内产出候选测试点 |
| 可达性门（selector→真实资源→注入器） | train-ticket/OB | ebtables 阻断识别、Order 不可达识别 |
| 三阶段测量（基线/注入/恢复） | 全部 | 所有实验精确数值 |
| 不夸大分类 | 全部 | 未把"没命中/环境偶然"当"防御" |
| 统计重复→统计事实 | OB | n=9 std 3.1ms；n=5 全 10008ms |
| 跨环境复现 | OB | kind vs Docker Desktop 一致 |
| 观测缺口检测 | OTel Demo | trace 级故障归因 |
| 知识库闭环 | 全部 | 14 张卡片 0 错误校验 |

## 环境约束（方法论边界）

| 约束 | 影响 | 出路 |
|---|---|---|
| WSL2 内核缺 ebtables broute/nat | HTTPChaos 全类型无法注入 | 非 WSL2 环境或自定义内核（成本高，挂起） |
| Docker Hub 429 限流 | collector 等镜像拉取受限 | 换镜像源/重试（Jaeger 绕过成功） |
| ghcr/github 间歇性 TLS | 镜像/源码拉取慢 | 重试+本地 registry |

## 对愿景的支撑

1. **方法论可迁移** ✅：同套 test-node 中心 + 证据链在 3 个不同类型项目完整复用，均产出运行时证据
2. **知识库可检索** ✅：14 张卡片，schema 统一，校验器保证质量
3. **论文素材** ✅：三项目复现模式（无 timeout）+ 独特机制（探针逃逸/观测缺口/基准缺陷）
4. **可报告发现** ⏳：OB F1-F3 与 train-ticket 缺陷已记录待决策；OTel Demo 源码 bug（错误消息）可直接报

## 待决策项（用户在 tracking.md 已登记）

- train-ticket issue（草稿就绪）
- OB issue（F1 无 timeout / F2 核心路径级联 / F3 探针）
- OTel Demo 源码 bug（quoteShipping 错误消息）
