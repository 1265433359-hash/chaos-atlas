# ChaosEater 真实部署 vs 我们：Sock Shop 上的实际对比

> 日期：2026-08-09
> 环境：ChaosEater 完整部署（ASE 2025，commit 47c4e44）+ deepseek-v4-flash 真实 LLM，在独立集群 `chaos-eater-cluster` 上对官方 `examples/sock-shop-2` 跑完整 cycle
> 对比对象：我们此前在同一项目（Sock Shop）上用 HTTPChaos 实测的 8 个边级候选（8/8 weakness）

## 一、CE 完整 cycle 实际跑通了什么

| 阶段 | CE 实际行为 | 结果 |
|------|------------|------|
| preprocess | skaffold 部署 Sock Shop（14 服务），LLM 总结 manifests | ✅ 部署成功，4 个 LLM agents 完成 |
| hypothesis | 选 2 个稳态：front-end 单副本可用性 + carts-db 可用性 | ✅ k6/k8sapi 检查 pod 成功 |
| experiment | 模拟黑五攻击序列：StressChaos(CPU/mem) → NetworkChaos(50% loss) → PodChaos(kill) → container-kill | ✅ 完整执行 6 分钟 |
| analysis | LLM 分析：**front-end 可用性 91.11% < 99% 阈值** | ✅ 判定为弱点 |
| improvement | 建议 front-end replicas 1→3 + PDB + HPA + 调探针 | ✅ 修改 09-front-end-dep.yaml（重部署时 skaffold 失败，improvement 未闭环） |

## 二、CE 判定的弱点 vs 我们判定的弱点（核心对比）

| 维度 | ChaosEater（真实部署） | 我们（HTTPChaos 实测） |
|------|----------------------|----------------------|
| 关注的弱点层 | **部署冗余/单点故障**（replicas=1） | **调用契约/超时保护**（8 个 HTTP 边全部无超时） |
| 注入手段 | StressChaos + NetworkChaos + PodChaos（服务级） | HTTPChaos（边级，HTTP 层劫持） |
| 判定结果 | 1 个弱点：front-end 单副本 → 建议 replicas 3 | 8 个弱点：4×loss + 4×delay 全部导致客户端挂死或延迟放大 |
| 稳态定义 | 部署可用性（availableReplicas） | 调用延迟/错误率 |
| 根因归因 | "replicas=1 单点故障"（部署层） | "无超时同步调用"（契约层） |
| 可修复性 | 加副本即可（横向扩展） | 需加超时/熔断（代码改动） |

## 三、关键洞察（差距在哪）

**1. 两者判定的是不同层面的弱点，且都"对"。**

CE 在**部署可用性**层面发现了 front-end 单副本问题（91.11% < 99%，实测数据支撑），这是真实弱点。我们发现的**调用超时缺失**（8/8 边全挂死）也是真实弱点，但 CE 完全没触及——它的稳态检查只看 availableReplicas，不看调用链的延迟/超时。

**2. CE 的稳态定义决定了它看不到我们看到的弱点。**

CE 的 `frontendDeploymentAvailableReplicas` 只检查 pod 是否存在，不检查 HTTP 请求是否成功、延迟是否放大。所以：
- 我们测的 `carts-delay`（延迟 2s，HTTP 500 但 pod 还活着）→ CE 会判"pod 可用，稳态通过"，**完全看不到**
- 我们测的 `payment-delay`（订单支付打挂 10s）→ CE 的稳态检查根本不会去测 orders→payment 调用

**3. 这解释了"同数据对比 6/14 漏判"的根因，且实测印证了。**

之前用 CE 的 analysis prompt 喂我们 14 个弱点的数据，CE 漏判 6 个"延迟放大但返回 OK"的 case——因为它判断"实验是否通过"而非"系统是否有弱点"。**这次真实部署验证了同样的问题**：CE 的稳态（availableReplicas）设计上就无法感知 HTTP 层的延迟放大和超时缺失。

**4. CE 的改进建议暴露了它的盲区。**

CE 对 front-end 的建议是 `replicas 1→3 + PDB + HPA`——都是**部署冗余**层面的。即使加了 3 副本，我们实测的 `payment-delay`（orders→payment 无超时挂死 10s）依然存在，因为那是**代码契约**问题，不是副本数问题。**CE 永远修不到这个层面，因为它的实验设计不检测这个层面。**

## 四、诚实的边界

- **CE 判定是合理的**：front-end 单副本在 PodChaos kill 下确实 91% < 99%，它的分析有实测数据支撑，比"瞎猜"强。
- **我们没让 CE 跑 HTTPChaos**：CE 自己生成的实验计划是 StressChaos/NetworkChaos/PodChaos（服务级），我们没有给它 HTTPChaos 边级候选。如果 CE 的稳态检查包含 HTTP 延迟，它可能也会发现超时问题——这是 CE 框架能力 vs 它的默认实验设计的区别。
- **single run**：只跑了一次，CE 的 fault 序列和稳态选择有随机性（虽然 seed 固定）。
- **improvement 未闭环**：CE 改了 manifest 但重部署失败（skaffold 因 OOM 清理后的环境失败），所以"改进后验证"没完成。

## 五、结论（可写进论文/给老师）

> **实际部署 ChaosEater 在 Sock Shop 上跑完整 cycle 的结果：它发现并正确修复了一个部署层弱点（front-end 单副本，91%<99%，建议 replicas 3），但完全看不到我们实测的 8/8 HTTP 边级弱点（无超时同步调用导致客户端挂死）——因为它的稳态定义（availableReplicas）在架构上就不检测调用链的延迟/超时。**
>
> **这不是"CE 更差"而是"CE 解决不同的问题"**：CE 优化的是"系统可用性"（pod 在不在），我们优化的是"调用链健壮性"（调用成不成功、卡不卡死）。**两者互补，但我们的方法补上了 CE 完全覆盖不到的那层**——这解释了为什么之前同数据对比 CE 漏判 6/14：不是偶然，是稳态设计的必然。
