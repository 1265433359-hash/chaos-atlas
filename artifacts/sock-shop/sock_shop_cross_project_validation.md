# Sock Shop 跨分布验证报告（第 4 项目）

## 验证目标
非循环跨分布验证：用前 3 项目知识（决策引擎，无 LLM）预测第 4 项目（Sock Shop，Java 为主，与 Train Ticket/Online Boutique/OTel 分布不同）的候选优先级，对比 M1 盲选 LLM 与 M0 随机。

## 环境突破（前置工作）
- **WSL2 自定义内核**：官方内核缺 `CONFIG_BRIDGE_EBT_BROUTE`，HTTPChaos 报 "kernel doesn't support ebtables 'nat' table"。编译 6.18.33.2 同源内核，内置 `BRIDGE_EBT_BROUTE=y` + `BRIDGE_EBT_T_NAT=y` + `BRIDGE_EBT_REDIRECT=y` + `ISO9660_FS=y` + `ADDRTYPE=y`，解锁 **HTTP 层边级注入**（此前 NetworkChaos 仅服务级）。
- **绕开 docker-desktop**：对照实验证明自定义内核破坏 docker-desktop VM 引导（官方内核 20s 就绪 vs 自定义卡死）。改为 Ubuntu WSL 内 dockerd + kind 集群，节点容器继承 BROUTE 支持。
- 可行性与 8 候选完整生命周期验证见 `httpchaos_feasibility.md`。

## 预测（冻结于执行前，sock_shop_predictions.json）
| 方法 | top-6 预测 |
|------|-----------|
| decision_engine（知识库，无 LLM） | 4×LOSS + 2×DELAY（loss 全部排到 delay 前） |
| M1 盲选 LLM | 3×LOSS + 3×DELAY（含 payment-delay） |
| M0 随机 | 混合 6 个 |

## 执行结果（sock_shop_verdicts.json）
8/8 候选均为 weakness（severity 2 或 3）：
- **sev3（客户端 10s 挂死）**：carts-loss, catalogue-loss, payment-loss, **payment-delay**
- **sev2（2s 精确延迟 / 快速失败但有服务不可用事实）**：shipping-loss, carts-delay, catalogue-delay, shipping-delay

关键事实：**Sock Shop 核心下单链路的全部 8 个 HTTP 边均无超时保护**——任何故障注入都暴露弱点。

## 三方法对比（诚实结果）
| 指标 | decision_engine | M1 盲选 | M0 随机 |
|------|----------------|---------|---------|
| top-6 命中 | 6/6 | 6/6 | 6/6 |
| severity 加权 | 15 | **16** | 15 |

**结论（不夸大）**：
1. **floor effect**：候选池全落在无保护的核心链路，8/8 全弱，三方法命中数无区分度。
2. **M1 盲选 severity 加权略高**：它把 payment-delay 排进 top6（实际 sev3），决策引擎因"delay<loss"先验漏掉它。**决策引擎在本池上不优于盲选**，如实记录。
3. 随机在此池上因全弱也有 6/6 命中——再次验证候选池构造偏差的影响。

## 跨分布知识可迁移性（真正的正面证据）
尽管三方法打平，知识库规则在本项目**成立**：
- SE 规则"无超时同步调用 = 高风险"在全新分布（Sock Shop）8/8 验证——前 3 项目学到的知识**可迁移**。
- 决策引擎的"loss > delay"先验在 payment-delay 失准（实际 delay 也挂死）→ **这是知识闭环要修正的条目**：delay 的严重度取决于调用方是否同步等待（Sock 的 orders→payment 同步等待无超时）。

## 诚实边界
- 候选池 8 个由我们按业务链路构造，全在核心链路上（选择偏差）。
- 单池、单样本、无重复（B1 教训：无统计功效）。
- HTTPChaos abort 语义与 NetworkChaos loss 语义不完全等价（HTTP 层 vs 网络层）。
- shipping-loss 判 sev2 而非 sev3 是人工判定（快速失败=调用方有容错）；若判 sev3，severity 加权持平 16，结论对判定敏感。
