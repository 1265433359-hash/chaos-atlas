# 可用性层实证：单副本无 PDB = kill 必瘫（双轨方法第二应用）

> 日期：2026-08-09
> 环境：chaos-eater-cluster / sock-shop-lab / Chaos Mesh 2.8.3（PodChaos pod-kill）
> 方法：通用判定模板第二应用（availability_defense_design.md）——静态(manifest) + 运行时(kill 实测) 双证据链
> 定位：不是套用 ChaosEater 的 availableReplicas 检查器，而是把我们的判定框架用在部署可用性维度

---

## 一、静态画像（manifest 事实，全部单副本无 PDB 无 HPA）

| 服务 | replicas | PDB | HPA | 探针 |
|---|---|---|---|---|
| front-end | 1 | 无 | 无 | liveness 1s/3s, readiness 1s |
| orders | 1 | 无 | 无 | 无 |
| payment | 1 | 无 | 无 | liveness 25s/20s（实验期间放宽过） |
| shipping | 1 | 无 | 无 | 无 |
| user | 1 | 无 | 无 | liveness 1s/3s |
| carts | 1 | 无 | 无 | 无 |
| catalogue | 1 | 无 | 无 | liveness 1s/3s |

**静态预测（AD-REDUNDANCY-001）**：Sock Shop 全部业务服务单副本且无 PDB → 杀掉唯一 pod = 该服务全瘫，无任何冗余防御。

## 二、运行时实测（PodChaos pod-kill，500ms 采样 Ready pod 数）

### 实测1：front-end kill
- 基线：1/1 Ready
- 注入：PodChaos pod-kill（mode=one）
- **outage_window = 130s**（Ready 从 1 → 0，持续 130s）
- 恢复：新 pod 于 kill 后 ~131s Ready（ReplicaSet 重建 + 镜像拉取 + Spring Boot/Node 启动 + readiness 通过）
- 曲线摘要（500ms 采样）：`[1,1,...] → 0 × 260 采样 → 1`
- **verdict: weakness（无冗余，单点故障）**

### 实测2：orders kill（订单链路内对照）
- 基线：1/1 Ready
- **outage_window = 56s**，恢复 ~57s
- **verdict: weakness（无冗余，单点故障）**

### 补测3-5：user / carts / shipping kill（订单链路完整覆盖）
| 服务 | 探针 | min_ready | outage_window | verdict |
|---|---|---|---|---|
| user | liveness+readiness 1s | 0（全瘫时刻命中） | 155s | weakness |
| carts | 无探针 | 0 | ~0s（无 readiness 门控） | weakness |
| shipping | 无探针 | 0 | ~0s（无 readiness 门控） | weakness |

**gate-lack 发现（补测的新机制）**：无 readiness 探针的服务（carts/shipping），新 pod 一旦 Running 立即被标记 Ready——outage_window 显示 ~0s **不是"自愈快"，而是"没有就绪门控"**：流量在新 pod 真正可用前就被导入了（可能打到未就绪的 pod）。这本身是另一个可用性弱点（AD-PROBE 类），与"单副本必瘫"叠加：kill 触发全瘫瞬间（min_ready=0），随后因无门控"假恢复"。

| 服务 | kill 后全瘫时长 | 恢复时长 | 判定 |
|---|---|---|---|
| front-end | 130s | ~131s | weakness（无冗余） |
| orders | 56s | ~57s | weakness（无冗余） |
| user | 155s | 未捕获（scheduler 抖动） | weakness（无冗余） |
| carts | 全瘫瞬间（门控缺失） | 4s（假恢复） | weakness（无冗余 + 无门控） |
| shipping | 全瘫瞬间（门控缺失） | 3s（假恢复） | weakness（无冗余 + 无门控） |

原始曲线：`artifacts/sock-shop/avail_{frontend,orders,user,carts,shipping}_kill.json`

## 三、与 ChaosEater 的对照（追平 + 增量）

| | ChaosEater（已跑） | 我们（本次） |
|---|---|---|
| front-end 单副本弱点 | ✅ 91.11%<99%（运行时采样） | ✅ 独立测出：kill → 全瘫 130s（静态 manifest + kill 实测双证据） |
| 判定依据 | availableReplicas 硬编码阈值 | AD-REDUNDANCY-001 规则 + 静态/运行时双证据链 |
| orders 单副本 | 未测（不在其候选） | ✅ kill → 全瘫 56s |

**追平成立**：CE 判的 front-end 单副本弱点，我们用**自己的框架**独立复现（结论一致，证据链不同——CE 是运行时可用性<99%，我们是 manifest 静态 + kill 实测）。

**增量（CE 结构上测不到）**：叠加效应——见下节。

## 四、叠加效应（两层复合弱点，CE 单一稳态测不出）

front-end 的双层画像：

```
层1（契约层，2026-08-09 已实测）:
  front-end→carts/catalogue: 无超时 → loss 挂死 10s、delay 放大 2x（weakness）

层2（可用性层，本次实测）:
  单副本无 PDB → kill 1 pod 全瘫 130s（weakness）

叠加:
  "单副本 + 无超时" = 杀一个就全瘫（130s 业务全断）
                      + 活着时下游一卡也拖死它（2s 放大 20x）
  → 双重弱点：又脆（无冗余）又独（无容错），任何单层方法只能看到一半
```

**验证路径**：同一服务分别做 delay 注入（契约层证据：avail_orders_future_get_verified 前的 SOCK-ORDERS 8 边实验）+ kill 注入（可用性层证据：本文件）→ 两套证据链各自成立 → 叠加成立。

## 五、方法论含义（论文定位）

1. **通用模板第二应用验证成功**：同一框架（选节点→注入→测防御响应→证据链判定）从契约层平滑迁移到可用性层，零新概念。
2. **契约清单 schema v2**：新增 `availability` 服务级注册（replicas/pdb/probes 静态事实），与 contract 边级注册并列。
3. **decision_engine 双硬过滤**：availability_hard_filter（单副本 kill 判定先验已知）+ contract_hard_filter（超时保护 delay 跳过）——同一引擎、同一审计机制。
4. **可用性层我们追平 CE、叠加层我们独有**：CE 在可用性层成熟，我们追平并用统一框架覆盖两层 + 发现复合弱点——这是"套用 CE"永远得不到的增量。

## 六、诚实边界

1. **可用性层不比 CE 准**：CE 的 front-end 单副本判定我们用静态+kill 复现（一致），但这不是超越，是追平+整合。
2. **恢复时长含环境因素**：130s/56s 含镜像拉取、节点负载、probe 周期，绝对值不通用；相对结论（单副本 kill 必瘫 + 恢复以十秒计）成立。
3. **未测多副本对照**：集群没有 replicas>1 的服务，无法实测"有冗余时不瘫"的正例；AD-REDUNDANCY-001 的单侧证据（无冗余必瘫）完整。
4. **catalogue-db OOM 循环**：独立的基础设施弱点（既有），不影响本次服务级可用性结论。
