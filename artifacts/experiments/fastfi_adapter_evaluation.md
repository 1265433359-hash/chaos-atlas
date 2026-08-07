# FastFI adapter 可行性评估（M2）

> 日期：2026-08-08
> 来源：`C:\APP\tools\TOSEM-FastFI-Code` @ commit `85e9dbb`（TOSEM）
> 目的：评估能否把 FastFI 提取为 adapter，作为 M2 接入统一候选池对比

## 一、FastFI 架构（故障注入引导的 API 调用点鲁棒性分析）

FastFI 与 ChaosEater 是**完全不同性质**的框架：

| 维度 | ChaosEater | FastFI |
|---|---|---|
| 定位 | 候选**选择**（LLM 从故障类型中挑最有效注入） | 候选**定位**（从故障组合日志求解最小关键调用点集） |
| 核心阶段 | hypothesis → experiment → analysis → improve | ①注入组合故障 → ②记录失败日志 → ③Max-SAT 求解 → ④修复建议 |
| 注入机制 | Chaos Mesh（7 类故障） | **Istio EnvoyFilter**（API 调用点级 ABORT/DELAY） |
| 输入 | k8s manifests + steady states | **多 API 组合注入的失败日志** |
| 输出 | FaultScenario（注入序列） | K 个关键 API 调用点 |
| LLM | 必要（各阶段 agent） | **不需要**（纯算法：DFS 最小命中集 + Max-SAT + 启发式） |

## 二、核心算法（RobustnessOptimizeAPI.py，381 行）

**输入格式**：每个 URL 一个 `fault-*.log`，形如：
```
ID 6: Service injection plan:
    logic-386.api1
    logic-18698.api1
    logic-647.api4
```
- 每个 `ID` = 一次**失败**注入组合（combo）
- 每行 `logic-<api>.api<type>` = 注入的调用点 + 故障类型
- **日志只记录失败实验的组合，不记录成功/失败结果**——文件本身即"失败集合"

**求解目标**：找到最小的 API 调用点集合（budget K），使每个失败 combo 至少被命中一个 → 即"最小命中集"（minimum hitting set）问题：
- 硬约束：覆盖 high-priority URL 的所有失败 combo
- 软约束：最大化覆盖其余 URL 的失败 combo
- 求解器：`dfs_min_hitsets`（DFS 精确最小命中集）+ `two_stage_solver`（Z3 + OR-Tools Max-SAT）+ `heuristic_solver`（贪心）

**前置**：调用图由 `CodeForK8s/util/GetCallGraphFromTrace.py` 从 **Jaeger trace** 构建（网络拓扑 → 每个服务节点的 API 列表）。

## 三、与统一候选池对比协议的根本冲突

M0/M1/M3/M4 的协议定义（`generate_deep_comparison_matrix.py`）：
> 各方法从**同一 12 候选池**中选 K=10 个候选（选择任务），注入后按 U@10/发现率对比。

FastFI **不执行这个任务**——它不"选择要注入什么"，而是"在注入过失败组合之后，定位哪些调用点是关键"。差异：

1. **输入不对齐**：FastFI 的输入是**组合故障注入日志**（每个 URL 数十个 combo）；我们只有**单候选受控证据**（每个候选一个受控实验，baseline→inject→recover）。没有组合注入实验数据，求解器无米下锅。
2. **注入机制不对齐**：FastFI 用 Istio EnvoyFilter（API 调用点级 ABORT/DELAY）；我们的环境是 Chaos Mesh（且 WSL2 无 HTTPChaos tproxy 前置）。集群无 Istio mesh 注入。
3. **输出不对齐**：FastFI 输出"关键 API 调用点"（服务内方法级），不是"候选注入序列"（服务边级）。无法直接映射到 `candidate_id`。
4. **任务定位不对齐**：它属于"故障定位/根因分析"类方法，与我们的"候选选择"方法族（M0/M1/M3/M4）在对比体系中不是同一赛道的。

## 四、强行 adapter 的路径与诚实性检查

| 强行适配方案 | 可行性 | 诚实性 |
|---|---|---|
| A. 用我们分类为 `not_defended` 的单候选证据拼失败日志 | 技术上可拼 | **违反纪律**——单候选受控实验 ≠ 组合失败注入，求解器结果无意义且会误导 |
| B. 部署 Istio + 跑组合注入实验 | 环境大改（Istio mesh + Jaeger + 组合实验预算），成本极高 | 可行但超出当前 lab 范围 |
| C. 复用"调用图生成"作为 I1-global 证据（非 M2） | 部分可提取 | 与 M3(graph-only) 信息层重叠，且 Jaeger 依赖未满足 |

**结论**：FastFI **不能**公平地作为 M2 接入同一候选池选择对比。它的正确位置是论文的"故障定位/修复建议"相关工作对照，而非"候选选择方法"对比。

## 五、决策选项

1. **M2 保持 blocked + 文档化差异（推荐）**：记录"任务定位不对齐"的结论，在论文中作为相关工作进行定性对照；不强跑
2. **M2 降级为"调用图证据"贡献者**：仅提取 trace→DAG 逻辑作为图构建思路参考（标注为 reimplementation），不作为对比方法
3. **部署 Istio 跑真组合实验**：预算/环境成本高，且与 WSL2 限制冲突，不建议现在做

## 六、已核实的可复用资产（供论文与方法论参考）

- 最小命中集求解器（`RobustnessOptimizeAPI.py`：DFS + Max-SAT + 贪心），依赖 z3-solver/pysat/ortools/tqdm 全部可装（已验证 PyPI 可达）
- 故障注入日志格式（combo → 失败集合 → 命中集）
- EnvoyFilter 注入模板（API 调用点级 fault 注入，非 Chaos Mesh）

## 七、与 ChaosEater 对比小结

| | ChaosEater (M1) | FastFI (M2) |
|---|---|---|
| adapter 可提取性 | ✅ 核心选择逻辑可提取（已实现，mock 跑通） | ⚠️ 分析器逻辑可提取，但**任务不对齐** |
| 接入同一候选池 | ✅ 已对齐（选择任务） | ❌ 任务不同（定位任务） |
| 环境依赖 | LLM API/Ollama（明天可用） | Istio + Jaeger（当前 lab 无） |
| 建议 | 继续（真实 LLM 覆盖 mock） | blocked + 文档化，论文中定性对照 |
