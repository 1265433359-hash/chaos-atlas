# ChaosEater adapter 可行性评估

> 日期：2026-08-08
> 来源：`C:\APP\tools\chaos-eater` @ commit `47c4e44`（ASE 2025）
> 目的：评估能否提取 ChaosEater 的核心候选选择逻辑为 adapter，接入统一候选池对比（M1）

## 一、ChaosEater 架构（LLM 混沌工程全自动循环）

```
Preprocessor → Hypothesis → Experiment → Analysis → Improvement → Postprocessor
                 │              │           │           │
                 fault          plan       analyze     improve
                 scenario       workflow
```

核心是 **agentic workflow**：各阶段用 LLM agent 协作。完整运行需要：
- LLM API（OpenAI/Anthropic/Gemini 或本地 Ollama）
- Docker Compose 部署（frontend GUI + backend + sandbox）
- Kubernetes + Chaos Mesh 环境（我们已有）

## 二、候选选择核心逻辑（adapter 可提取部分）

### 阶段 1：FaultScenarioAgent（候选生成）
- **输入**：K8s manifest 概览 + steady states（系统稳态）+ CE 指令
- **输出**：`FaultScenario` = { event（真实事件假设）, thought（推理）, faults（故障注入序列） }
- **故障类型枚举**（hard-coded）：PodChaos/NetworkChaos/DNSChaos/HTTPChaos/StressChaos/IOChaos/TimeChaos
- 每个 `Fault` = { name（类型）, name_id, scope（注入目标资源） }
- 关键：**LLM 从枚举中选择 + 指定 scope**，这与我们的候选宇宙（12 场景）天然对齐

### 阶段 2：FaultRefiner（候选细化）
- 在 FaultScenarioAgent 输出基础上细化故障参数（经故障模板约束）

### 阶段 3：ExperimentPlanAgent + Plan2WorkflowConverter（候选→注入）
- LLM 制定实验计划（时间表/预验证/注入/后验证）
- **Plan2WorkflowConverter 是纯算法**（非 LLM）：把故障计划转成 ChaosMesh Workflow YAML
- 注入执行依赖我们的 runner（已有）

## 三、adapter 提取方案（对照统一候选池接口）

我们的接口（`generate_deep_comparison_matrix.py`）：
```python
{
  "candidate_id": "OB-PAYMENT-DELAY-2000",
  "method": "random-template",  # 或 ChaosEater-adapter
  "target": {"service": "paymentservice", "namespace": "online-boutique-lab"},
  "mutation": "artifacts/experiments/execution/mutations/ob-payment-delay-one.yaml",
  "gate_decision": "ready_for_injection"
}
```

**ChaosEater-adapter 的核心**：用 FaultScenarioAgent（复用其 prompt 逻辑）代替随机选择——
- 输入：项目的 manifest 摘要 + steady states（我们从知识库/实验基线提取）+ 12 场景候选宇宙
- 输出：LLM 排序/选择的候选子集（映射到我们的 candidate_id）
- 然后走我们的 runner 注入（与 M0/M3/M4 同预算、同 gate）

**不提取的部分**（完整 ChaosEater 的额外环节，不在对比范围内）：
- Analysis（LLM 分析结果）
- Improvement（LLM 修复建议）
- 这些属于"完整 CE 循环"而非"候选选择"，对比时明确标注 adapter 范围

## 四、可执行性结论

| 维度 | 评估 |
|---|---|
| 依赖 | ✅ 可装（pydantic-v1 + langchain + kubernetes，PyPI 可达） |
| 核心逻辑 | ✅ 清晰可提取（FaultScenarioAgent prompt + Fault schema） |
| LLM 需求 | ⚠️ 需 API key 或 Ollama 本地模型（qwen3 等） |
| 与现有接口 | ✅ 天然对齐（候选 + scope → mutation + gate） |
| 诚实性 | ✅ 标注 `ChaosEater-adapter`，不伪装原样结果（协议要求） |

**结论**：ChaosEater 的候选选择逻辑**可以提取为 adapter**，工作量可控（复用 prompt + schema，接我们的候选池/runner）。前置条件是 **LLM 可用**（用户 API key 或装 Ollama）。

## 五、决策选项

1. **提取 adapter（推荐）**：写 `ChaosEaterAdapter` 模块，复用 FaultScenarioAgent 逻辑，跑同候选池对比——需要用户提供 LLM key 或装 Ollama
2. **只做"选择逻辑" mock**：不真调 LLM，按 ChaosEater 论文的枚举+scope 策略手写选择器（标注为 reimplementation，不是原样）
3. **挂起**：记录评估结论，等有 LLM 环境再做

## 六、FastFI 备注（M2）

- 已克隆（commit `85e9dbb`，14MB）
- 核心：调用图生成（CodeForGeneratreCallGraph）+ Max-SAT 求解器（RobustnessOptimizeAPI.py）
- 需要 Istio + Jaeger + conda python3.9
- 适配难度高于 ChaosEater（依赖 Istio 环境）；adapter 提取需先理解调用图生成逻辑

## 七、实现状态（2026-08-08）

**已实现并跑通（mock 后端）**：`tools/chaos_eater_adapter/` 包 + `tools/generate_m1_adapter_plans.py`。

| 组件 | 文件 | 说明 |
|---|---|---|
| 提示词（提取自 FaultScenarioAgent） | `prompts.py` | SYS/USER 模板 + JSON 格式指令，加"从候选池选 N 个"约束 |
| 数据结构（Fault/FaultScenario） | `schemas.py` | 纯 dataclass 复刻，7 种故障类型枚举原样保留 |
| 候选池映射 | `mapping.py` | 故障类型 ↔ 候选池 family 双向映射，I0 级（不泄漏静态评分） |
| LLM 后端（可插拔） | `llm_backend.py` | `OpenAICompatBackend`（OpenAI/DeepSeek/Ollama 通用）+ `MockBackend`（确定性管线验证，**非**真实选择） |
| Adapter 编排 | `adapter.py` | prompt 构建 → 后端调用 → FaultScenario 解析 → 去重/预算 → 排名 |
| 项目上下文（I0） | `contexts.py` | 仅 manifest 可见事实（服务/边/声明强度），无测量结论 |
| 生成脚本 | `generate_m1_adapter_plans.py` | 读既有 registry → M1 plans → 新 registry（原文件不动） |

**产物**：`deep_matrix_registry_r1_m1.json` / `r2` / `r3`（mock:seed101/202/303），每份 M1=10 plans、全局 rank 1-10、同候选池；`evaluate_deep_comparison_matrix.py` 消费通过（ready_for_injection 10/10）。测试：`tests/test_chaos_eater_adapter.py` 17 例，全量 58 测试通过。

**待真实 LLM**：API key 到位后执行
`python tools/generate_m1_adapter_plans.py --replicate N --seed S --backend openai-compat --base-url <endpoint> --api-key <key> --model <model>`
（Ollama 用 `http://localhost:11434/v1`）。真实结果将覆盖 mock 产物并记录 model/tokens/event 溯源；mock 结果**不得**作为真实 ChaosEater 选择上报。

**纪律**：不改 `generate_deep_comparison_matrix.py`（M1 默认保持 blocked，既有测试断言稳定）；M1 的 available 状态只出现在 `*_m1.json` 增量产物中，且逐条标注 adapter 来源。
