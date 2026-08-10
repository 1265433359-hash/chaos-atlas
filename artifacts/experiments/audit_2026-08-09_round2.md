# 项目全面审计记录（第二轮，2026-08-09）

> 承接 methodology_audit.md（第一轮 A1-D4 修复）。本轮审计**新增实验引入的结构性问题**（契约层+可用性层+经验回填），共 9 项，全部修复完成。
> 原则：审计不是"挑错后不改"，是"挑错→修复→记录"闭环。所有修复带证据，可追溯。

---

## 审计发现与修复（9 项）

### 🔴 1. 三方法对比的"冻结"声明与时间线不符（自证循环）
- **问题**：`contract_inventory.py` 最后修改 19:57（提交 3f68115，实验完成之后），但 `sock_three_method_predictions.json` 声称 `frozen_before_execution: True`。decision_engine 的 "4/4" 用了**事后回填**的 SOCK 注册知识，与真盲选 M1 对比不公平。
- **修复**：
  - `sock_three_method_select.py` docstring 加 HONESTY NOTE（拆分两个字段：`m1_blind_frozen_before_execution=True` / `decision_engine_knowledge_frozen_before_execution=False`）
  - 产物 JSON 同步改标注（`3f68115` 前已提交版本被修正）
  - 结论定性改为"知识资产化后验行为"而非"预测优于盲选"

### 🔴 2. 双轨池 16/16"对齐"是自我印证
- **问题**：`sock_dual_track_pool` 的真值来自我们自己的注册知识，引擎消费同一注册——16/16 必然对齐，不能当"方法有效"证据。
- **修复**：docstring + 产物加 `validity: CONSISTENCY check (engine vs its own registry), NOT independent-truth validation`；独立真值指向实验文件（real-chain / pod-kill / CE parity）。

### 🔴 3. 可用性层"追平 CE"存在确认偏误
- **问题**：CE 是独立真实部署（不知道我们候选），我们是在**看到 CE 结论后**手动 kill 验证；且测量不对称（CE=k6 流量下 91%，我们=无流量 Ready 1→0）。
- **修复**：`sock_availability_layer_verified.md` §三 加"确认偏误声明"——表述改为"同一结论，两种独立测量，但我们有 CE 答案在先"，论文须限定。

### 🔴 4. C8 叠加效应没有实验，是定性推理
- **问题**：C8 声称"契约弱 × 可用性弱 = 复合弱点，CE 测不出"，但无联合注入实验。
- **修复**：`unified_experiments_summary.md` C8 降级为"定性推理 + future work（需 delay+kill 联合注入实证）"；"一句话表述"同步修正。

### 🟠 5. verdicts v3 summary 字段过时
- **问题**：summary 还是 v2 的契约层数字，没算可用性层。
- **修复**：`sock_shop_verdicts.json` summary 拆为 `contract_layer` + `availability_layer` 分层汇总。

### 🟠 6. CRLF 破坏脚本可复现性
- **问题**：无 `.gitattributes`，autocrlf=true → `.sh` 在 Windows checkout 转 CRLF，WSL 执行失败（Kconfig 教训重演风险）。
- **修复**：新增 `.gitattributes`（`*.sh text eol=lf` 等）。

### 🟠 7. 恢复时长被环境污染
- **问题**：实验期间 KCM/scheduler 反复崩溃（load 200+），130s/56s/155s 含抖动；user 的 recovered_s 因 scheduler 崩缺失。
- **修复**：`sock_availability_layer_verified.md` §六 加"环境抖动标注"——绝对值仅展示，相对结论（min_ready=0）不受影响。

### 🟠 8. DP 库语义再次混淆（缺位≠防御）
- **问题**：DP-REDUNDANCY-ABSENT-001 把"冗余缺失"存进防御模式库，违反 A1"缺位不是防御"。
- **修复**：从 `defense_pattern_library.json` 移除（5→4）；`backfill_experience_gaps.py` 移除该定义 + docstring 记录原因；缺位规则保留在 contract_inventory AVAILABILITY static_prediction + decision_engine availability_hard_filter。

### 🟠 9. 范围声明与新增实验冲突
- **问题**：methodology_audit C1 声明"实证=网络故障家族"，可用性层（PodChaos）是扩展，C1 未更新。
- **修复**：C1 补"范围扩展（2026-08-09）"——纳入 pod-kill 可用性家族；仍不含 HTTPChaos/组合故障/多副本正例。

---

## 修复后的诚实结论（论文警示）

1. **决策引擎 vs 盲选**：不是等时序公平对比。引擎的 4/4 是"知识资产化后验行为"的证据；M1 单次 4/4 是运气（不可复现）；M0 49% 期望浪费是分布事实。
   - **重验证完成（方案1，2026-08-10 修正）**：原 `sock_frozen_knowledge_rerun.py` 曾调用读 live 的 `score_candidate()` 再用硬编码 `pred` 覆盖——那是 **static prediction audit**，不是 engine replay。修正后（第五锁点）：六函数 + `rank()` 支持 `knowledge_snapshot` 注入，非 None 时**零 live 读取**（测试用抛异常 loader 验证）；产物拆为两个：
     - `sock_frozen_static_prediction_audit.json`（valid 8/8）：静态预测 vs 实验真值——仅证明**预实验静态知识可复现**（evaluation reproducibility of knowledge）；
     - `sock_frozen_decision_engine_replay.json`（**blocked**）：引擎在注入 snapshot 下真实输出（hard_skip/priority/score/reasons），未被静态 pred 覆盖；但因 SE/DP/JE 无实验前干净 commit（f870e32 是 r2-pre 非 Sock-pre，已含 Sock 条目），四源快照无法声明实验前知识 → 完整 replay 标记 **blocked**，不得宣称实验前冻结引擎重放。`loss_bounded` 标记 `static_inferred`。
2. **16/16**：只能证明"引擎与自己的注册知识一致"，不是独立真值验证。论文引用时须以实验文件（real-chain/pod-kill/CE parity）为真值来源。
3. **C8 叠加效应**：**重验证完成（方案4）**：`sock_combined_frontend_carts.json` 证明两故障（downstream delay 2s + pod-kill）可并发注入互不干扰，front-end 全瘫 124s。定量延迟放大被本轮环境负载污染（基线 3.5s），不报告；契约层放大由 SOCK-FRONTEND-CARTS-DELAY-2000 独立证据支撑。论文可写"并发注入可行性已验证"，定量叠加数字需低负载补测。
4. **可用性层 vs CE**：确认偏误已标注，**重验证完成（方案3）**：`sock_blind_availability_predict.py` 不看 CE 报告、仅凭 manifest 对 8 服务预测 → **5/5 runtime 对齐**（其余 3 服务静态推断）。CE 对照降为佐证，"追平"限定为"CE 结论之后的独立复现"。
5. **DP 库**：只存"防御存在"的模式（source_verified 优先）；缺位规则在 contract_inventory / decision_engine，不在 DP 库。

## 未修复项（超出本轮范围，记录）

| 项 | 状态 |
|---|---|
| C8 定量叠加数字（低负载下 delay+kill 联合测量） | future work（需低负载集群） |
| 多副本正例对照 | future work（集群无 replicas>1 服务） |
| 6 个未实测服务可用性（payment/catalogue/queue-master） | 静态推断（AD-REDUNDANCY-001），可选补测 |
| 外部真值（issue 提交） | 待用户确认（reporting/issue_template.md） |
