# 可用性防御维度设计：通用模板的第二应用（不是套用 CE）

> 日期：2026-08-09
> 定位：方法论扩展设计稿（v1），覆盖 CE 的部署可用性层，但用我们自己的框架
> 核心主张：我们的方法论是一个**通用判定模板**（选节点 → 注入 → 测防御响应 → 证据链判定），
> 契约层是它的第一个应用，可用性层是它的第二个应用——不是抄 CE 的 availableReplicas 检查器。
> 前提：CE 只覆盖可用性层；我们补上后两层都覆盖 + 跨层叠加（CE 结构上测不到）。

---

## 一、通用模板（我们方法的内核，不变）

```
1. 选一个测试节点（服务/边）
2. 注入一种故障（delay/loss/kill/资源压力）
3. 测量系统的防御响应（吸收？兜底？挂死？自愈？）
4. 凭证据链判定（defended / weakness，静态+运行时双证据）
```

| 维度 | 契约层（已实现） | 可用性层（本设计） |
|---|---|---|
| 注入故障 | NetworkChaos delay/loss（HTTP 层） | PodChaos kill / StressChaos 资源压力 |
| 测什么响应 | 调用会不会被超时吸收 / 会不会挂死 | 可用性会不会掉 / 能不能自愈 / 恢复多快 |
| 静态证据 | 源码/配置（WithTimeout、Future.get） | manifest（replicas、PDB、探针） |
| 运行时证据 | 注入实测（TimeoutsException、挂死时长） | kill 实测（可用性曲线、恢复时长） |
| 判定产出 | explicit_timeout → defended / no_timeout → weakness | 有冗余自愈 → defended / 单副本无自愈 → weakness |

**同一个模板，第二个应用。** 这是"覆盖 CE 层面"的方式：不是把 CE 的检查器搬进来，而是把我们自己的判定框架用在第二个防御维度上。

---

## 二、契约清单扩展：availability_defense 注册（复用现有机制）

契约清单现在每条边注册 `contract`（超时防御）。扩展为每个服务注册 `availability_defense`（可用性防御）：

```json
"SOCK-front-end": {
  "contract": "no_timeout",
  "availability_defense": {
    "replicas": 1,
    "pdb": null,
    "liveness_probe": {"path": "/", "port": 8079, "initial": 300, "period": 3},
    "readiness_probe": {"path": "/", "port": 8079, "timeout": 1},
    "hpa": null,
    "static_prediction": "single-replica, no PDB -> kill 1 pod = total outage; liveness exists -> self-heal attempt only if container dies, not if pod killed"
  }
}
```

字段全部来自**静态可审计证据**（manifest/deployment yaml），和 contract 一样是"系统声明的事实"，不是测试参数。

---

## 三、判定规则扩展：可用性规则组（进同一判定引擎，不是硬编码阈值）

decision_engine 现在组合 SE/DP/JE 三库。新增可用性规则，**同引擎、同权重机制**：

### 新知识库条目：可用性防御模式（AD-*，放 defense_pattern_library 或独立）
```
AD-REDUNDANCY-001: replicas=1 且无 PDB → kill 1 pod = 全瘫 → 缺冗余弱点
AD-SELFHEAL-001:   kill 后可用性 < 100% 且恢复 > 阈值(如 2s) → 自愈慢弱点
AD-PROBE-001:      readiness 探针 timeout 过小 → 抖动期被摘流量（可用性假摔）
```

### 判定流程（与契约层并列）
```
候选 = SOCK-front-end-kill-1
静态:  availability_defense.replicas=1, pdb=null → AD-REDUNDANCY-001 命中 → 预测 weakness
运行时: PodChaos kill front-end → 可用性采样曲线 0/1 持续 Xs → 无自愈
判定:  静态+运行时一致 → weakness（缺冗余），证据链完整
```

### 与 CE 的关键区别（来源不同）
| | CE | 我们 |
|---|---|---|
| 可用性稳态 | 硬编码 availableReplicas | **注册化的防御维度**（进契约清单） |
| 判定阈值 | 写死 99% | **规则化**（AD-* 库，confidence 权重） |
| 证据 | 只看运行时数字 | **静态(manifest) + 运行时(kill) 双证据链** |
| 可审计 | 黑盒规则 | 每条 AD-* 有 evidence_cases，可追溯 |

---

## 四、运行时验证流程（复用双证据链）

```
1. 静态画像: 读 manifest → replicas/pdb/probe → 预测
2. 注入:     PodChaos kill（或 StressChaos CPU 打满）
3. 采样:     可用性采样器（周期 500ms，数 Ready pod + 探针状态）→ 曲线
4. 恢复:     等自动恢复（k8s ReplicaSet 重建），记录恢复时长
5. 判定:     AD-* 规则 + 双证据 → defended/weakness
6. 恢复:     清理注入，确认回到基线
```

与契约层实验（baseline→inject→recover→cleanup）完全同构，只是注入器从 NetworkChaos 换成 PodChaos。

---

## 五、增量：跨层叠加效应（CE 结构上测不到）

**这是本设计的真正价值，不是"我们也测可用性"。**

单一稳态检查器（CE）只能看一层。两层都测之后，出现**单层方法看不到的复合弱点**：

```
front-end 复合画像（两层叠加）：
  层1（契约）: 无超时调用 → 下游卡 2s 拖到 2s+（weakness）
  层2（可用性）: 单副本无 PDB → kill 1 pod 全瘫（weakness）
  叠加: 单副本 + 无超时 = 不仅杀一个就瘫，活着时下游一卡也拖死
        → "双重视角下比任何单层都脆弱" ← CE 永远测不出
```

### 叠加效应定义（v1 提案）
```
复合弱点 = 契约层弱点 ∧ 可用性层弱点（同一服务）
严重度 = max(sev_contract, sev_avail) + 叠加惩罚（如 +1）
可验证 = 对同一服务分别做 delay 注入（契约）+ kill 注入（可用性），
         两套证据链各自成立 → 叠加成立
```

---

## 六、与 CE 的对比验证设计（论文可写）

同一系统（Sock Shop）上：
| 实验 | CE（已跑） | 我们（扩展后） |
|---|---|---|
| 部署可用性层 | front-end 单副本 91%<99% → 弱点 ✅ | **同候选：我们 kill 实测 + manifest 静态 → 同弱点**（追平） |
| 调用契约层 | 结构上不测 | 8 边画像（4 weak + 4 defended） |
| 复合弱点 | 无概念 | front-end 单副本 × 无超时 → 叠加弱点 |

**结论句（论文）**：同一系统上，CE 只覆盖可用性层（1 个弱点）；我们的统一框架覆盖两层（可用性 1 + 契约 8 + 叠加 1），且可用性层与 CE 结论一致（证明框架对 CE 层面有效），叠加效应是 CE 结构上测不到的唯一增量。

---

## 七、诚实边界（必须保留）

1. **可用性层我们不比 CE 准**——该层 CE 已成熟，我们是追平+整合，不是超越。论文不能主张"可用性测得更准"。
2. **叠加效应需实证**——v1 是设计提案，需对 Sock Shop front-end 跑两套注入验证后才成立。
3. **AD-* 规则需积累**——初始只有 3 条，覆盖度有限；证据链越多规则越可信（与 SE/DP 同样的积累机制）。
4. **CE 若未来扩展稳态定义**——它也可能测到部分契约层；我们主张的是"统一框架 + 叠加"而非"唯一性"。

---

## 八、实施路线（A 档：设计；B 档：实施）

### A 档（设计定稿，本文件）
- [x] 通用模板阐述
- [x] 契约清单 availability_defense schema
- [x] AD-* 规则 + 判定流程
- [ ] 叠加效应定义评审（+1 惩罚是否合理）
- [ ] 与论文叙事整合（定位句）

### B 档（实施，需另行确认）
1. 契约清单加 availability_defense 字段（Sock Shop 全服务静态画像）
2. 可用性采样器脚本（周期 500ms 数 Ready pod → 曲线 + 恢复时长）
3. PodChaos/StressChaos 注入流程封装（sock_execute 同构）
4. AD-* 规则进 defense_pattern_library / 新库
5. Sock Shop front-end 实测（kill + delay 双注入）→ 验证叠加效应
6. 更新 sock_shop_verdicts.json（可用性层并入）+ unified_experiments_summary.md
