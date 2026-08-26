# ChaosAtlas Knowledge Closed Loop Execution Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 ChaosAtlas 从“生成 RCA 草稿”推进为能够自动发现问题、执行安全诊断、根据证据更新根因状态、生成经验并驱动下一轮验证的知识闭环。

**Architecture:** 保留现有 TestNode、业务 Oracle、运行时生命周期和知识库校验器。新增不可变的证据账本、只读证据 collector、依赖注入的受控 executor 和闭环编排器。确定性引擎负责状态、门禁、晋级和停止；LLM 只能提出假设或解释，不能裁决证据真实性。

**Tech Stack:** Python 3、标准库、pytest、现有 Kubernetes/Chaos Mesh runner、JSON artifact。第一阶段先离线和 mock executor，第二阶段才接入真实 Kubernetes executor。

---

## 目标与验收映射

| 用户目标 | 实现阶段 | 最终验收 |
|---|---|---|
| 自动找问题 | Task 2 | 无历史 verdict 时仍能从项目快照生成候选，并经过环境/业务 Oracle 门禁 |
| 自动找根因 | Task 3-4 | 每个假设自动得到 `pending/bounded/confirmed/rejected`，缺证据时停止 |
| 自动形成经验 | Task 5 | 自动生成 provisional 卡，满足门槛后晋级 local_reusable |
| 自动形成迭代 | Task 6 | 卡片 ID、snapshot hash 和 next evidence 进入下一轮输入并改变诊断计划 |
| 自动验证改进 | Task 7 | 同一场景、Oracle、预算复测后输出 improvement_verified 或明确 blocked/regression |

## 当前明确边界

1. `dry_run` 只证明动作契约，不产生运行时支持证据。
2. `environment_blocked`、`injection_not_confirmed`、`business_not_reachable`、`recovery_timeout` 不得计入 weakness 或 defense。
3. `bounded` 是成功的有界结论，不得被自动升级成具体内部根因。
4. `provisional` 和 `contested` 不得改变高影响候选排序。
5. 只有 `local_reusable` 才能影响下一轮排序或诊断要求。
6. 真实动作必须通过显式 gate、namespace allow-list、cleanup 和残留扫描。

## Task 1: 修正证据和状态语义

**Files:**
- Modify: `tools/rca_loop.py`
- Modify: `tools/rca_runtime_loop.py`
- Modify: `tools/validate_rca_loop.py`
- Test: `tools/tests/test_rca_loop.py`
- Test: `tools/tests/test_rca_runtime_loop.py`
- Test: `tools/tests/test_validate_rca_loop.py`

- [ ] 增加 `claim_level` 和统一状态语义：`dry_run`、`blocked`、`executed`、`injection_not_confirmed`、`environment_blocked`、`effect_unobserved`、`recovery_timeout`。
- [ ] 规定 `confidence` 不能高于证据状态：`bounded` 不得写成机制级 `1.0`；没有 required evidence 时必须保留缺口。
- [ ] 修正 `unsupported_claims` 只列未满足的 required evidence，不把已经满足的证据重复列为缺口。
- [ ] 让 validator 拒绝“状态已 confirmed 但 evidence incomplete”“dry_run 产生 supports”“blocked 结果改变 RCA/knowledge 状态”。
- [ ] 先写失败测试，再运行：

```powershell
python -m pytest tools/tests/test_rca_loop.py tools/tests/test_rca_runtime_loop.py tools/tests/test_validate_rca_loop.py -q --basetemp .pytest-tmp-rca-boundary
```

- [ ] focused tests 通过后提交：`git commit -m "fix: enforce RCA claim and execution boundaries"`

## Task 2: 建立证据 collector 接口

**Files:**
- Create: `tools/evidence_collectors.py`
- Create: `tools/tests/test_evidence_collectors.py`
- Modify: `tools/rca_runtime_loop.py`

- [ ] 定义统一 `EvidenceCollector` 接口，支持 `manifest/config`、`source_span`、`logs/events`、`business_replay`、`recovery` 五类 collector。
- [ ] collector 只返回结构化结果：source ref、时间窗口、sha256、claim scope、polarity、unavailable reason 和 satisfies。
- [ ] collector 不读取密钥、不调用外部 LLM；文件路径、namespace、时间窗口和敏感值全部 fail closed。
- [ ] 为每类 collector 编写正常、不可用、越界、敏感值和 scope mismatch 测试。
- [ ] mock collector 能被 runtime loop 调用并写入不可变 action artifact。
- [ ] 运行 focused tests 和 `python -m compileall tools/evidence_collectors.py tools/rca_runtime_loop.py`。
- [ ] 提交：`git commit -m "feat: add bounded RCA evidence collectors"`

## Task 3: 建立受控 executor 和执行证明

**Files:**
- Create: `tools/rca_action_executor.py`
- Create: `tools/tests/test_rca_action_executor.py`
- Modify: `tools/rca_runtime_loop.py`
- Modify: `tools/validate_rca_loop.py`

- [ ] 定义 executor 输入/输出契约，必须携带 action、project snapshot、namespace policy、budget、baseline contract、cleanup contract。
- [ ] 先实现 `MockRCAExecutor`，覆盖成功、注入未确认、业务不可达、恢复超时、清理失败和敏感输出。
- [ ] 生成 attestation：baseline、injection、observation、recovery、cleanup、independent oracle、comparison eligibility。
- [ ] 只有完整 attestation 且 action status 为 `executed` 时，证据才可参与 RCA 晋级。
- [ ] 执行结果采用 append-only 写入，禁止覆盖同 action ID 的历史结果。
- [ ] 运行：

```powershell
python -m pytest tools/tests/test_rca_action_executor.py tools/tests/test_rca_runtime_loop.py -q --basetemp .pytest-tmp-rca-executor
```

- [ ] 提交：`git commit -m "feat: add attested RCA action executor"`

## Task 4: 完成 Sock Shop 自动 RCA

**Files:**
- Modify: `tools/sock_shop_rca.py`
- Modify: `tools/rca_runtime_loop.py`
- Modify: `tools/tests/test_sock_shop_rca.py`
- Modify: `tools/tests/test_rca_runtime_loop.py`

- [ ] `catalogue-db`：执行 scoped catalogue logs、直接依赖重放和恢复检查，区分 `database_connection_unavailable` 与 `catalogue_error_propagation`。
- [ ] 单副本：执行相同业务 Oracle 下的 replica=1/replica=2 反事实；只确认部署冗余边界，不推导应用内部机制。
- [ ] HTTP abort：执行真实业务路径、直接依赖路径和 fault removal recovery；没有源码/config 时不得生成 `missing_timeout`。
- [ ] 每个 action 结果自动回写 case、hypothesis、evidence ledger、next action 和 promotion audit。
- [ ] 至少一个案例在 mock executor 下完成 `pending -> bounded -> confirmed`，至少一个案例完成反例降级。
- [ ] 运行 Sock Shop focused suite 和 RCA runtime suite。
- [ ] 提交：`git commit -m "feat: close Sock Shop RCA execution feedback"`

## Task 5: 经验卡晋级和反例回流

**Files:**
- Modify: `tools/compile_rca_regression.py`
- Modify: `tools/feedback_protocol.py`
- Modify: `tools/query_knowledge_base.py`
- Create: `tools/tests/test_knowledge_feedback_loop.py`

- [ ] `provisional` 只能生成 `reproduce/discriminate`。
- [ ] `local_reusable` 必须满足两次复现，或一次复现加一次反事实，并具备生命周期、直接证据、适用条件、回归意图和停止规则。
- [ ] `contested` 不得生成可执行 intent，也不得影响候选排序。
- [ ] 反例必须保留旧 card、旧 evidence、旧 snapshot hash 和降级原因。
- [ ] snapshot 采用规范化 JSON hash，并写入下一轮输入。
- [ ] focused tests 验证晋级、降级、反例和确定性 hash。
- [ ] 提交：`git commit -m "feat: enforce knowledge promotion and counterexample feedback"`

## Task 6: 闭环编排和下一轮迭代

**Files:**
- Create: `tools/run_closed_loop.py`
- Create: `tools/tests/test_run_closed_loop.py`
- Modify: `tools/decision_engine.py`
- Modify: `tools/compile_rca_regression.py`

- [ ] 提供 `onboard`、`discover`、`diagnose`、`learn` 四个可审计阶段。
- [ ] 每轮记录 input hash、parent round、card IDs、snapshot hash、budget、approval、action results 和 cleanup report。
- [ ] `local_reusable` 卡片必须改变下一轮诊断要求或候选排序；`provisional/contested` 只能提供说明。
- [ ] 同一输入快照重复运行必须得到相同 action plan、排序和 snapshot hash。
- [ ] 没有安全适用动作时自动停止并写入 `pending`，不能无限重试。
- [ ] 运行离线端到端闭环测试。
- [ ] 提交：`git commit -m "feat: orchestrate automated knowledge closed loop"`

## Task 7: 结构化改进与复测

**Files:**
- Modify: `tools/deployment_improvement.py`
- Modify: `tools/run_deployment_scenario.py`
- Create: `tools/tests/test_closed_loop_improvement.py`

- [ ] 只允许结构化 patch：replicas、PDB、probe、resource requests/limits。
- [ ] patch 作用于 immutable source copy 或 fresh namespace，原始源码不可变。
- [ ] 使用相同 scenario、seed、业务 Oracle、观察窗口和 recovery rule 复测。
- [ ] 输出严格限定为 `improvement_verified`、`regression`、`deployment_blocked`、`not_run`。
- [ ] 改进结果回流到 RCA 和知识卡；失败不能自动生成 defense。
- [ ] 提交：`git commit -m "feat: verify knowledge-guided deployment improvements"`

## 最终验收

```powershell
python -m pytest tools/tests -q --basetemp .pytest-tmp-rca-closed-loop
python tools/validate_rca_loop.py --root artifacts/sock-shop/rca_loop
python tools/validate_knowledge_base.py --root artifacts/train-ticket/knowledge_base
python -m compileall tools
git diff --check
```

最终必须有一条完整机器可读链路：

```text
candidate
 -> executed action
 -> attested evidence
 -> RCA transition
 -> provisional card
 -> next-round input
 -> changed diagnosis/selection
 -> reproduction or counterexample
 -> promotion/demotion
```

只有完成 Task 6，才能声称“自动知识迭代闭环”；完成 Task 7 后，才能进一步声称“知识指导改进并通过复测验证”。
