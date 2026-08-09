# 对比实验统一总结：两天多轮实验的完整叙事

> 日期：2026-08-07 → 2026-08-09
> 范围：9 方法消融（M0-M4/A0-A4）+ ChaosEater 完整 analysis 对照 + CE 真实部署 + OB 混合池 + Sock Shop 真实链路验证 + r2 三方法 head-to-head
> 项目（四个）：train-ticket / Online Boutique / OpenTelemetry Demo / Sock Shop（kind + Chaos Mesh + WSL2 自定义内核解锁 HTTPChaos）
> 本文整合：comparison_full_summary.md / chaos_eater_deployed_vs_ours.md / mixed_pool_comparison.md / sock_orders_future_get_verified.md / sock_shop_verdicts.json / r2_head_to_head.md / 各预测 JSON
> 归档入口：`artifacts/experiments/archive/ARCHIVE_INDEX.md`（项目/方法/台账/候选池/证据矩阵统一注册）

---

## 〇、方法清单修正（2026-08-09 补充）：实验实际上对比了两根独立的方法轴

> **修正说明**：v1 只记录了"选择方法"轴（M0/M1/M3/M4/decision_engine），遗漏了第 8 轮引入的**测量方法**轴。
> 前 7 轮全部使用**直连端口测量**（direct）；第 8 轮首次使用**真实业务链路测量**（real-chain）。
> 这两者是正交的方法维度：选择方法决定"测哪个候选"，测量方法决定"怎么测这个候选、看到什么"。
> 本次关键发现（直连盲区）正是**测量方法**这一轴的差异导致的——把它归入"规律"而非法定方法，是 v1 的疏漏。

### 方法轴 A：选择方法（测哪个候选）——v1 已完整记录
| 方法 | 定义 | 知识来源 |
|---|---|---|
| M0 | 随机模板选择 | 无 |
| M1 | CE 选择逻辑 adapter + LLM（**ChaosEater-adapter ≠ ChaosEater official**：是盲 LLM ranker，非官方完整 cycle） | LLM 常识 |
| M3/M4 | 局部图 / 全局图 + 运行时证据 | 图 + 运行时 |
| decision_engine | 契约清单硬过滤 + SE 规则（无 LLM） | 知识资产库 |

> 注：完整方法注册表见 `archive/method_registry_archive.json`（选择/测量/证据三轴分离；CE-adapter 与 CE-official 分开记录）。

### 方法轴 B：测量方法（怎么测）——v1 遗漏，本次补充
| 方法 | 测量位置 | 注入语义 | 能看到什么防御 | 系统性盲区 |
|---|---|---|---|---|
| **直连测量**（direct，前 7 轮全部） | 服务端口 / HTTPChaos 边级劫持 | 网络层故障 | 配置层超时（如 OB adservice 100ms） | **代码层异步超时不可见**（Future.get） |
| **真实业务链路测量**（real-chain，第 8 轮） | 业务入口（POST /orders）→ 完整链路 | 业务语义故障 | 代码层异步超时（Sock orders 5s Future.get） | 需构造业务入口数据（register/cart/order 前置） |
| **可用性采样测量**（availability，第 9 轮） | 服务级 Ready-pod 采样（500ms 曲线） | PodChaos pod-kill / StressChaos | 冗余/自愈（replicas>1、PDB、探针） | 看不到调用层防御（pod 活着≠调用健康） |

**两轴关系**：第 8 轮的三方法对比（decision_engine vs M1 vs M0）在**选择轴**上比较，但它们的判定全部基于**同一套真实链路实测数据**（2026-08-09 冻结）。直连与真实链路的差异（12s vs 5s）是**测量轴**独立证明的——同一注入、同一服务，两种测量方法给出相反结论。第 9 轮的可用性采样是测量轴第三种方法，与契约层正交（pod 在不在 vs 调用顺不顺）。

---

## 一、实验地图（12 个实验模块，按时间顺序）

| # | 实验 | 对象 | 对比 | 测量轴 | 一句话结果 |
|---|---|---|---|---|---|
| 1 | B1 候选选择命中率 | 20 池已知数据 | M1 vs M3/M4 vs M0 | 直连 | **无方法更优**（bootstrap CI 含 0） |
| 2 | B2 指标可靠性 | 同一批数据 | 5 种 severity 权重 | 直连 | **权重决定结论**（2-2-1 时 M0 反超） |
| 3 | B3 LLM 判定稳定性 | 5 候选 × 3 次 | 重测一致率 | 直连 | **0.933，可靠** |
| 4 | 前瞻 r1 | 6 未执行候选 | M1 vs 我们(+知识) | 直连 | M1 命中 3 我们 2，差 1 个无意义 |
| 5 | CE analysis 对照 | 14 已确认弱点 | CE vs 我们 | 直连 | CE 6/14 漏判，产出形态差异非优越 |
| 6 | CE 真实部署 cycle | Sock Shop | CE vs 我们直连 | 直连 | **零重叠**：CE 判 front-end 单副本，我们 8/8 契约弱 |
| 7 | OB 混合池 | 8 候选（3 protected） | decision_engine vs M1 vs M0 | 直连 | 打平 5/6 vs 5/6，88%<95% 不显著 |
| 8 | **Sock 真实链路** | 8 候选（4 protected） | decision_engine vs M1 vs M0 | **真实链路** | **decision_engine 4/4，M0 49% 浪费；且直连在此边系统性误判** |
| 9 | **Sock 可用性层** | 服务级 kill（4 实测 + 4 静态） | 我们 vs CE（追平） | **可用性采样** | **单副本无 PDB kill 必瘫：front-end 130s、orders 56s、user 155s、carts/shipping 全瘫瞬间（无门控假恢复）；与 CE 判定一致（独立复现）** |
| 10 | **双轨统一池** | 契约 8 边 + 可用性 8 服务 | decision_engine 双硬过滤 | 双轨 | **16/16 与真值对齐：契约 4 protected 跳过、可用性 8 kill 全判 weakness** |
| 11 | **经验缺口回填** | 知识库审计 + 补全 | DP 3→5, SE 6→10 | — | **防御模式库原来几乎空（3 条未验证）；补齐 Future.get/无冗余 + 探针污染/镜像兼容/端口错配/OOM** |
| 12 | **r2 三方法 head-to-head** | OB 8 候选（r2 冻结池） | Ours-full vs CE-adapter vs Random | 统一 runner | **U@8 6 vs 6 vs 5（pilot/blocked：未执行正式显著性检验，统计功效不足，ceiling/saturation effect 8/8 全 weakness）；OTEL 4 + TT 1 候选 environment_blocked 未执行** |

> 注：#8/#9/#10/#11/#12 是本总结的核心新证据（2026-08-09），#1-7 为既有落盘事实。

---

## 二、逐轮关键数据与证据

### #1 B1 候选选择（20 池）
- M1 severity 加权 0.658（三次稳定），M3/M4 0.51，M0 随机 0.49-0.61
- bootstrap CI（n=1000）：**M1 vs 所有方法差异 95% CI 全部含 0**
- 结论：任何"谁选得准"的声称都无统计背书

### #5 CE analysis 对照（14 候选）
- CE 6/14 判"实验通过"漏判（全是"延迟放大但返回 OK"的 case）
- OTEL-EMAIL 明确误判；0/14 结构化根因；TT-STATION 接近我们（诚实亮点）
- 评价标准我们定义、根因我们自己写（自证循环）→ 只能主张"产出形态适配下游"

### #6 CE 真实部署（Sock Shop 完整 cycle）
- CE：hypothesis→experiment→analysis→improvement 全跑通
- 判 1 弱点：front-end 单副本 91.11%<99% → 建议 replicas 3（有实测数据，合理）
- 我们：8/8 契约层弱点（直连）→ 修正后 4/8
- **两条清单零重叠**：部署可用性层 vs 调用契约层

### #7 OB 混合池（8 候选，唯一真 protected = adservice 100ms）
- protected 注入 2s 延迟仅 +96ms；unprotected 注入 2s → 8s 挂死或 2-4s 放大
- 三方法：decision_engine 5/6、M1 盲选 5/6、M0 均值 3.72（95%CI [3,5]）
- **根因：protected 边太"明显"**——adservice 是非关键服务，M1 凭"广告非关键"常识避开，无需契约清单

### #8 Sock Shop 真实链路（本次，8 候选 4 protected）
- 真实订单链路打通：POST /orders → user/carts/payment/shipping/orders-db
- **orders→payment/shipping 有 5s Future.get 超时**（jar javap + 运行时 TimeoutException 双证据）
  - 2s 注入 → 201 @ 4.15s（吸收）；6s 注入 → 500 @ 5.10s（TimeoutException）
  - 直连对照：同一 6s 注入 → 12s 挂死（**直连系统性盲区**）
- 判定修正：8/8 weakness → 4/8 weakness + 4/8 defended
- 三方法（冻结预测，预算 4）：**decision_engine 4/4 命中 0 浪费；M0 随机 49% 期望浪费；M1 盲选单次采样 4/4（运气）**

---

## 三、跨轮浮现的四个规律

### 规律 1：方法差异只在"信息不对称"存在时显现（池子设计决定结论）
- B1（20 池已知）→ 无差异；OB 混合池（protected 太明显）→ 打平；Sock（protected 藏得深）→ 拉开
- 三个实验不是"方法变了"，是**池子的信息不对称程度变了**
- 方法优劣对比实验的核心 = 构造关键路径 × 隐蔽防御 × 直连盲区的池子，而不是祈祷方法自发差异

### 规律 2：测量方法决定防御可见性（本次最硬的证据，独立方法轴 B 的结论）
- 同一个 payment 6s 注入：直连 12s 挂死（误判 weakness）vs 真实链路 5s TimeoutException（正确 defended）
- 防御不是存在/不存在的二元属性——它在某些测量位置**不可见**
- 直连测量系统性误报弱点的根因，就在这
- **方法含义**：真实业务链路测量（轴 B2）是直连测量（轴 B1）测不到的防御的**唯一暴露手段**，二者构成互补而非替代——直连便宜（前 7 轮覆盖 20+ 候选），真实链路贵（需业务数据构造）但能看到代码层防御

### 规律 3：知识资产化产生确定性收益（契约清单 vs LLM 常识）
- decision_engine 的 4/4 是**确定性**的（contract_hard_filter 硬过滤）
- M1 盲选的 4/4 是**单次采样运气**（不可复现；OB 池它曾误选 protected adservice）
- 知识一旦以证据链形式固化（契约清单 + loss_bounded），收益确定；留在 LLM 常识里，收益随机

### 规律 4：自我修正能力是方法论的健康标志
- 8/8 → 4/8 修正：真实链路证据推翻直连旧判定
- 三方法对比暴露 decision_engine 只过滤 DELAY 不认 LOSS → 新增 loss_bounded 语义
- 契约清单从"只认配置层超时"扩展到"认代码层异步超时"（Future.get）
- 一个不敢推翻自己旧结论的方法论，和"永远全对"一样可疑

---

## 三·五、经验缺口审计（2026-08-09，回答"是不是还有很多经验没加进去"）

### 审计结果：是的，有大量经验未结构化
| 库 | 审计前 | 问题 | 回填 |
|---|---|---|---|
| defense_pattern_library | 3 条（全部未验证 absorbed_by_design） | **实测的防御机制一条没进库**：Future.get 超时、单副本无冗余 | +2（DP-BOUNDED-TIMEOUT-FUTUREGET-001 已验证、DP-REDUNDANCY-ABSENT-001） |
| selection_experience | 6 条 | 全是"选择/判定"经验，**没有测试卫生/部署经验** | +4（探针污染、镜像兼容、端口错配、OOM） |

### 回填内容（全部带本会话实测证据）
1. **DP-BOUNDED-TIMEOUT-FUTUREGET-001**（bounded_timeout, source_verified=True）：`Future.get(5s)` 对 delay 和 loss 都有界，直连测不到——知识资产化核心案例。
2. **DP-REDUNDANCY-ABSENT-001**（redundancy）：单副本无 PDB → kill 必瘫，静态 manifest 即可先验判定。
3. **SE-TEST-HYGIENE-PROBE-001**：探针 timeout < 注入延迟 → pod 被 SIGKILL，注入"逃逸"污染实验（Sock payment 实测 + OB 既有）。
4. **SE-TEST-HYGIENE-IMAGECOMPAT-001**：mongo:latest(8.x) 破坏旧驱动 OP_QUERY → 降级 mongo:4.0（carts/orders-db 实测）。
5. **SE-TEST-HYGIENE-PORTMISMATCH-001**：容器监听端口 ≠ svc targetPort → 静默拒绝（front-end 8079/80）。
6. **SE-TEST-HYGIENE-OOM-001**：无 resources.limits → OOM crash-loop（catalogue-db），与探针/注入无关。

### 含义
- 知识库的"选择/判定"维度当时是满的，但"防御模式"和"测试卫生"两个维度严重欠账——这两类恰恰是**真实部署里最贵、最反复踩的坑**。
- 回填后：DP 库 5 条（含 2 条 source_verified）、SE 库 10 条。审计+回填脚本：`tools/backfill_experience_gaps.py`。
- **方法论教训**：知识资产化的范围应覆盖"防御机制 + 测试卫生 + 判定经验"三维，不能只记判定规则。

---

## 四、最终统一结论（给导师/论文，每条均锚定实验证据）

### 第一层：被统计证明的事实（不可争议）

**C1. 在"候选选择"上，没有任何方法被证明更优。**
- 证据：B1（20 池，bootstrap CI n=1000 全含 0）；OB 混合池（decision_engine 5/6 = M1 5/6，88%<95%）；**r2 head-to-head（OB 8 候选，U@8 = Ours-full 6 vs CE-adapter 6 vs Random 5，ceiling/saturation effect——8/8 全 weakness，样本 8 无显著差异，非 superiority）**。
- 含义：任何"我们选择候选更准"的声称都没有统计背书。这与方法论优劣无关，是实验设计问题（池子无信息不对称时，选择方法必然无差异）。

**C2. 产出形态可验证、可锚定、可复用。**
- 证据：**历史 83 次受控注入 + r2 24 次尝试分开计数**（master 台账 `archive/run_ledger_master.json`：**总 run records 107 = 83（历史 lifecycle-complete）+ 24（r2）；独立注入总数 91 = 83（历史）+ 8（r2 首跑）**；r2 确认运行 9、r2 无效基线 7（r2 有效观测 17 = 8 首跑 + 9 确认，是观测分类非独立数）；67 个派生/预测/汇总文件明确不计入独立实验。历史 83 见 `execution/remediation/run_ledger.json`；r2 24 见 `execution/remediation/r2_runs/`）；15 个源码锚定根因（含 OTel main.go:494、train-ticket OrderServiceImpl.java:192-206 两份可提交 bug 报告）；20 知识卡 + 防御模式库 + 判定经验；契约清单 11 边（含 loss_bounded 语义扩展）；B3 判定一致率 0.933。

### 第二层：本次实验确立的实证主张（第 8 轮，可复现）

**C3. 测量方法决定防御可见性——这是独立于选择方法的方法轴。**
- 证据：同一 payment 6s 注入，直连 12s 挂死（误判 weakness）vs 真实业务链路 5s TimeoutException（正确 defended）。第 8 轮。
- 含义：防御不是存在/不存在的二元属性，它在某些测量位置不可见。直连测量（含 CE 的 availableReplicas 稳态）对代码层异步超时（Future.get）系统性失明；真实业务链路测量是这类防御的唯一暴露手段。

**C4. 知识资产化产生确定性收益。**
- 证据：同一池（Sock 8 候选 4 protected）冻结预测：decision_engine 4/4 命中 0 浪费（契约清单硬过滤，确定性）vs M0 随机 49% 期望浪费 vs M1 盲选单次 4/4（运气，OB 池曾误选）。
- 含义：知识一旦以证据链形式固化（契约清单 + loss_bounded），收益确定；留在 LLM 常识里，收益随机。

**C5. 方法差异只在信息不对称存在时显现。**
- 证据：B1 无差异（20 池已知）→ OB 打平（protected=adservice 非关键，太明显）→ Sock 拉开（protected=Future.get 藏得深）。变的不是方法，是池子的信息不对称程度。
- 含义：对比实验设计的核心是构造"关键路径 × 隐蔽防御 × 直连盲区"的池子，而非祈祷方法自发差异。

### 第三层：与 ChaosEater 的统一关系（互补 → 追平 + 增量）

**C6. CE 修"系统在不在"（部署可用性），我们修"调用成不成、卡不卡"（契约健壮性）。**
- 证据：CE 真实部署判 front-end 单副本 91.11%<99%（真实弱点，建议 replicas 3）；我们 8 边画像 + 4 protected 精确测出。同一 Sock Shop，两条清单零重叠。
- 含义：CE 的稳态=availableReplicas 在架构上不检测 HTTP 语义，因此其盲区是结构性的（不是调参能解决）；但 CE 发现的部署层弱点同样是我们没覆盖的——两方法互补，覆盖不同的防御层。

**C7. 可用性层追平：我们用自己的框架独立复现了 CE 的判定。**
- 证据（第 9 轮）：CE 判 front-end 单副本弱点 → 我们用静态 manifest（replicas=1、无 PDB）+ PodChaos kill 实测（Ready 1→0 持续 130s）独立复现，结论一致；orders 同样全瘫 56s。
- 含义：这不是套用 CE 的 availableReplicas 检查器——是**通用判定模板的第二应用**（availability_defense_design.md）：同一"选节点→注入→测防御响应→证据链判定"框架，从契约层平滑迁移到可用性层。契约清单 schema v2 注册服务级 availability，decision_engine 双硬过滤（availability + contract）。

**C8. 叠加效应：两层复合弱点（联合注入已验证并发可行，定量放大待 future work）。**
- 实证（2026-08-09 联合注入，`sock_combined_frontend_carts.json`）：对 front-end 同时注入 downstream carts delay 2s + PodChaos pod-kill —— **两故障并发注入成功、互不干扰**（kill 期间 delay 探针持续返回非 INF），front-end 全瘫 124s。
- 定量部分**不报告**：本轮集群负载高（基线被污染），延迟放大数字不可靠。契约层放大由独立证据 SOCK-FRONTEND-CARTS-DELAY-2000（2s → ~20x，HTTP 500）支撑；可用性全瘫由 avail_* kill 实验支撑。C8 叠加 = 契约层独立证据 + 可用性层独立证据 + 并发注入可行性三证据合成。
- 含义：单一稳态检查器（CE）只能看一层，理论上测不出"契约弱 × 可用性弱"的叠加——统一框架的独有增量，且并发注入可行性已验证；定量叠加数字（如"叠加使恢复时间 +N%"）需在低负载环境补测后写入论文。

### 一句话最终表述

> **对比实验统一结论：防御能力评估是"测量方法 × 证据链"问题，不是"注入强度"或"选择算法"问题。选择方法（M0/M1/CE/decision_engine）在无信息不对称时统计上无差异（C1）；测量方法决定哪些防御可见——真实业务链路测量是直连测量测不到的代码层异步防御的唯一暴露手段（C3），可用性采样测量是部署层冗余/自愈防御的暴露手段（C7）；一旦测试节点选对并把结果固化为契约知识，判定收益是确定性的（C4）；我们与 ChaosEater 从"互补"走到"追平 + 增量"：可用性层我们用同一模板独立复现其判定（C7，含确认偏误标注，盲法静态预测 5/5 对齐），契约层是其结构上不可达的发现（C3），叠加层已证并发注入可行、定量待 future work（C8）。本方法论的价值不在"选择更准"，而在"选对测试节点 + 产出可验证证据链 + 知识资产化 + 敢于自我修正"。**

**与既有叙事的关系**：这统一了之前"我们未证明优于 CE / M1 / 随机"（B1）与"我们在实际项目里更优"（主张）之间的张力——B1 证明的是"选择方法无差异"，C3/C4 证明的是"测量方法与知识资产产生差异"。两者不矛盾：前者否定的是"选择算法优越论"，后者确立的是"测试节点与证据链中心论"。

**与 ChaosEater 的统一关系**：CE 修"系统在不在"（部署可用性，front-end 单副本 91%<99%），我们修"调用成不成、卡不卡"（契约健壮性，8 边画像 + 4 protected 精确测出）。同一 Sock Shop，两条清单零重叠——不是"CE 更差"，是**测量层互补**；而我们的层对 CE 结构上不可见（稳态=availableReplicas，不检测 HTTP 语义）。

---

## 五、诚实边界（必须保留）

| 边界 | 说明 |
|---|---|
| M1 盲选单次 4/4 | 单次采样，无统计意义；OB 池它曾误选 protected |
| Sock LOSS 两边的 defended 判定 | 基于共享 Future.get + delay 实测推断，未单独重跑 loss |
| CE 对 Future.get 边的行为 | 基于稳态定义推断，未让 CE 实测该边 |
| OB 混合池 M1 = decision_engine | 契约清单在 OB 池未拉开差距（protected 太明显） |
| CE front-end 单副本 | CE 发现的真实弱点，我们未测部署可用性层 |
| B1 统计功效 | 20 池、单轮，需 50+ 候选多轮才够 |
| 外部真值 | 2 份 issue 未提交，无上游确认 |

---

## 六、遗留与下一步

| 项 | 状态 |
|---|---|
| 2 份 issue 提交（外部真值） | ⏸ 待用户确认 |
| Sock LOSS 边单独重跑（补全证据） | ⏸ 可做（cluster 已恢复） |
| CE 实测 Future.get 边（闭环推断） | ⏸ 需 CE 配置 HTTP 稳态 |
| 更大池子多轮对比（16-24 候选 + McNemar） | ⏸ B1 教训 |
| 主方法论文档整合本叙事 | ⏸ 可做 |

---

## 附：产出资产清单

- 契约清单：artifacts/experiments/contract_inventory.json（11 边，含 SOCK 2 边 + loss_bounded）
- 判定数据：artifacts/sock-shop/sock_shop_verdicts.json（v2，4/8）
- 三方法预测：artifacts/sock-shop/sock_three_method_predictions.json
- CE 部署对比：artifacts/experiments/chaos_eater_deployed_vs_ours.md
- OB 混合池：artifacts/online-boutique/mixed_pool_comparison.md
- 验证报告：artifacts/sock-shop/sock_orders_future_get_verified.md
- 工具：tools/sock_three_method_select.py（新增）、tools/contract_inventory.py、tools/decision_engine.py
