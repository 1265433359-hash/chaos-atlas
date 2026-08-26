# ChaosAtlas 原生部署可用性与故障恢复能力层实施计划

> **给 GLM 的执行说明：** 本计划必须按任务顺序执行。每个任务先写失败测试，再写最小实现，再运行 focused tests；不得把 ChaosEater 写成 ChaosAtlas 的专用分支。步骤使用 checkbox (`- [ ]`) 跟踪。

**目标：** 将部署可用性、服务级故障编排、故障恢复判定和 manifest 改进重测建设为 ChaosAtlas 的原生能力，使 ChaosEater 的 Sock Shop cycle 只是一个可被该能力自然表达和验证的 profile。

**非目标：** 不复制 ChaosEater 的 LLM agent 架构、源码、prompt 或完整 cycle；不把 CE 的脚本、阈值和故障序列作为 ChaosAtlas 核心依赖；不把 `availableReplicas` 硬编码成全局唯一判据；不以“发现相同 weakness 数量”作为覆盖证明；不修改既有契约层判定语义；不在没有独立证据时自动把静态风险写成确认弱点。

**核心架构：** 现有 TestNode/局部影响图主要以服务调用边为中心。本计划新增两种同级节点：`deployment_node` 和 `scenario_node`。部署节点连接 Deployment、ReplicaSet、Pod、Service、probe、PDB、HPA、流量入口和恢复路径；场景节点表示可顺序或并发执行的故障阶段。既有 baseline -> inject -> observe -> recover -> cleanup 生命周期、适用性门禁和证据链保持不变，只扩展目标类型、oracle 类型和恢复状态。ChaosEater 只提供能力需求的外部参照；核心 schema、编译器、runner 和 oracle 不依赖 CE artifact。

**技术栈：** Python 3 标准库、Kubernetes API、Chaos Mesh、现有 runner、pytest。离线阶段不得调用 LLM、网络或集群。

---

## 一、现有代码边界

GLM 开始前必须阅读下列文件，不得先设计新框架再忽略既有接口：

| 文件 | 当前职责 | 本计划中的变化 |
|---|---|---|
| `tools/contract_inventory.py` | 源码契约和服务级 availability 静态事实 | 从 Sock 专用常量扩展为可版本化部署 profile，保留旧 schema 兼容 |
| `tools/decision_engine.py` | 契约/知识 hard filter 和排序 | 支持 deployment/scenario candidate；`AD-REDUNDANCY` 只作静态先验，不直接替代 runtime oracle |
| `tools/run_chaos_experiment.py` | 单故障生命周期与恢复 | 支持服务级目标、可用性采样和 scenario phase 元数据 |
| `tools/run_sock_shop_two_arm.py` | Sock Shop PodChaos/Schedule runner | 复用 selector、cleanup、UID 和 recovery 逻辑，不复制一套新 runner |
| `tools/runtime_applicability_gate.py` | 平台/目标/注入门禁 | 增加 deployment profile 和 scenario phase 校验 |
| `tools/classify_runtime_result.py` | 运行结果分类 | 增加 availability/recovery outcome，但保留原分类兼容 |
| `tools/feedback_protocol.py` | 独立 oracle 和知识反馈 | 允许服务级 availability evidence 进入 card，但禁止 runtime verdict 泄漏到 projected knowledge |
| `tools/run_native_full_discovery.py` | manifest/native knowledge 驱动假设生成 | 作为 blind service-level discovery 的入口，不创建 CE 专用发现器 |
| `tools/open_discovery_mutation_compiler.py` | 假设编译为 Chaos Mesh YAML | 扩展 scenario/并发阶段编译，保留现有单故障编译 |
| `tools/tests/` | 既有回归测试 | 新增纯函数、schema、编译器、oracle、报告测试 |

**禁止修改：** 不得删除或重命名已有 `contract_inventory` 字段、已有 runner 分类、已有知识快照 provenance 字段；如需扩展，必须增加 `schema_version` 和兼容读取。

---

## 二、统一数据契约

### 2.1 `deployment_node`

新增模块 `tools/deployment_capability.py`，定义下列纯数据函数：

```python
def build_deployment_node(
    *, project_id: str, project_commit: str, namespace: str,
    deployment: dict[str, Any], service: dict[str, Any] | None,
    source_refs: list[str], manifest_sha256: str,
) -> dict[str, Any]: ...

def validate_deployment_node(node: dict[str, Any]) -> list[str]: ...

def deployment_signature(node: dict[str, Any]) -> str: ...
```

输出必须包含：

```json
{
  "node_type": "deployment_node",
  "project_id": "sock-shop",
  "project_commit": "40-hex",
  "namespace": "sock-shop",
  "deployment": {
    "name": "front-end",
    "selector": {"name": "front-end"},
    "desired_replicas": 1,
    "containers": ["front-end"],
    "resources": {"requests": {}, "limits": {}}
  },
  "service": {"name": "front-end", "port": 80, "target_port": 8079},
  "availability_profile": {
    "pdb": null,
    "hpa": null,
    "liveness_probe": {},
    "readiness_probe": {},
    "manifest_facts_status": "verified"
  },
  "source_refs": ["relative/path.yaml"],
  "manifest_sha256": "sha256"
}
```

规则：绝对路径、驱动器路径、`..`、敏感值和缺失 `project_commit` 必须 fail closed；未知字段可保留但不能参与判定。

### 2.2 `scenario_node`

同一模块定义：

```python
def build_scenario_node(
    *, scenario_id: str, deployment_nodes: list[dict[str, Any]],
    phases: list[dict[str, Any]], oracle: dict[str, Any],
    recovery: dict[str, Any], cleanup: dict[str, Any],
) -> dict[str, Any]: ...

def validate_scenario_node(scenario: dict[str, Any]) -> list[str]: ...

def scenario_signature(scenario: dict[str, Any]) -> str: ...
```

每个 phase 必须包含：`phase_id`、`mode` (`ordered` 或 `concurrent`)、`faults`、`duration_s`、`target_node_ids`、`inject_confirmation`、`cleanup_owner`。每个 fault 必须包含：`kind`、`action`、`selector`、`parameters`、`target_node_id`。

### 2.3 oracle schema

新增 `tools/availability_oracle.py`，同时保存 CE-compatible 和 ChaosAtlas-native 两组指标：

```json
{
  "ce_steady_state": {
    "metric": "deployment.availableReplicas",
    "minimum_available": 1,
    "ratio_threshold": 0.99,
    "max_zero_streak": 1,
    "sample_interval_s": 1
  },
  "native_recovery": {
    "replacement_identity_required": true,
    "ready_required": true,
    "business_probe": "sock-shop-order-or-homepage",
    "stable_samples": 3,
    "deadline_s": 180,
    "cleanup_required": true
  }
}
```

注意：ChaosEater 前端实际使用 `availableReplicas >= 1`、99% 和最大连续零值 1；`carts-db` 使用至少 95% 的 `>=1` 观测。不得把 `desired_replicas` 替换成 CE 的 `minimum_available`。

### 2.4 capability coverage schema

新增报告字段，不用 weakness 数量代表能力：

```json
{
  "schema_version": 1,
  "tool": "chaosatlas_capability_coverage",
  "profile": "chaoseater-sock-shop",
  "native_path": {
    "deployment_model": "verified",
    "scenario_compiler": "verified",
    "oracle": "verified",
    "recovery": "verified",
    "improvement": "not_run"
  },
  "cells": [
    {
      "track": "ce_replay",
      "target": "front-end",
      "phase": "stress-loss-kill",
      "oracle": "availableReplicas",
      "input_parity": "verified",
      "execution": "verified",
      "recovery": "verified",
      "attribution": "verified",
      "improvement": "not_run"
    }
  ],
  "claim": "partial_capability_coverage"
}
```

`claim` 只能是 `full_native_capability`、`partial_capability_coverage`、`blocked`。只要必需 cell 为 `not_run` 或 `blocked`，不得输出 `full_native_capability`。

---

## 三、任务顺序

### Task 1: 建立 deployment/scenario 数据契约

**Files:**
- Create: `tools/deployment_capability.py`
- Create: `tools/tests/test_deployment_capability.py`
- Modify: `tools/contract_inventory.py`

- [ ] 写失败测试：合法 Deployment node 通过；缺 namespace、commit、selector、manifest hash、资源引用或含绝对路径时失败。
- [ ] 写失败测试：scenario phase 缺 target、duration、cleanup owner、fault kind 或 phase mode 时失败；并发 phase 必须至少包含两个可解析 fault 或明确标记单目标。
- [ ] 实现上述纯函数、canonical JSON hash 和 schema validation；不访问集群。
- [ ] 将现有 `AVAILABILITY` 转换为 schema v3 兼容输出，保留 `replicas/pdb/hpa/probes/static_prediction` 旧字段。
- [ ] 运行：`python -m pytest tools/tests/test_deployment_capability.py -q`，预期全部通过。

### Task 2: 从 manifest 构建全量部署候选和局部影响图

**Files:**
- Create: `tools/build_deployment_capability_pool.py`
- Modify: `tools/project_registry.py`
- Modify: `tools/decision_engine.py`
- Create: `tools/tests/test_build_deployment_capability_pool.py`
- Modify: `tools/tests/test_decision_engine.py`

- [ ] 从固定 source tree/manifest 读取所有 Deployment、Service、PDB、HPA 和 probes，生成 deployment nodes；读取失败时输出 `static_blocked`，不能默认 replicas=1。
- [ ] 为每个 deployment node 生成 fault families：`pod_kill`、`container_kill`、`stress_cpu`、`stress_memory`、`network_loss`、`network_partition`，只有 compiler 支持且 selector 可验证才标记 `compile_eligible`。
- [ ] 生成 deployment-local impact graph：`Deployment -> ReplicaSet -> Pod`、`Service -> selector -> Pod`、`probe -> Pod readiness`、`fault -> Pod/Service`、`recovery -> replacement Pod -> business probe`。
- [ ] 将 `availability_hard_filter` 改为消费 node snapshot；只在 `replicas==1 and pdb is null` 时产生 `availability_static_prior`，不得直接返回最终 runtime weakness。
- [ ] 保证 edge candidate 和 deployment candidate 在同一 `rank()` 接口中可共存；旧 edge 测试输出必须不变。
- [ ] 运行：`python -m pytest tools/tests/test_build_deployment_capability_pool.py tools/tests/test_decision_engine.py -q`。

### Task 3: 把 CE cycle 表达成普通 scenario node

**Files:**
- Create: `tools/compile_scenario_node.py`
- Modify: `tools/open_discovery_mutation_compiler.py`
- Modify: `tools/run_sock_shop_two_arm.py`
- Create: `tools/tests/test_compile_scenario_node.py`

- [ ] 实现 ordered/concurrent phase 编译，禁止在 compiler 中检查 `method_id == ChaosEater`。
- [ ] 用普通 schema 表达 CE Sock Shop 场景的四阶段：
  - phase 0 concurrent: StressChaos CPU 100% + memory stress，目标 `front-end` 和 `carts-db`；
  - phase 1 concurrent: NetworkChaos loss 50%，目标 `front-end` 和 `carts-db`；
  - phase 2 concurrent: PodChaos pod-kill，目标 `front-end` 和 `carts-db`；
  - phase 3: PodChaos container-kill，目标 `rabbitmq-exporter` container。
- [ ] 编译结果必须为 namespace-local YAML，带稳定 name、phase ID、target node ID、duration 和 cleanup ownership。
- [ ] 编译器先运行 `validate_scenario_node()`，任何未解析 selector、跨 namespace target、未知 fault 参数直接返回 `method_invalid`。
- [ ] 测试 dry-run 只生成 canonical manifest 和 hash，不调用 kubectl。
- [ ] 运行：`python -m pytest tools/tests/test_compile_scenario_node.py -q`。

### Task 4: 实现双 oracle availability/recovery 判定

**Files:**
- Create: `tools/availability_oracle.py`
- Modify: `tools/classify_runtime_result.py`
- Modify: `tools/run_chaos_experiment.py`
- Create: `tools/tests/test_availability_oracle.py`
- Modify: `tools/tests/test_runtime_classification_consistency.py`

- [ ] 实现纯函数：`availability_ratio(samples, minimum_available)`、`max_zero_streak(samples)`、`recovery_deadline(samples, deadline_s)`、`replacement_identity(before, after)`、`business_probe_stability(samples, k)`。
- [ ] CE oracle 从 Deployment status 读取 `availableReplicas`，API 查询失败按 CE 脚本规则计为 0；不得用 Ready-only 采样代替。
- [ ] Native recovery oracle 要求：旧 Pod UID 消失或被明确替换、replacement Ready、业务探针连续 K 次成功、cleanup confirmed。
- [ ] 分类必须区分：`availability_defended`、`availability_degraded`、`recovery_timeout`、`probe_restart_escape`、`no_readiness_false_recovery`、`platform_blocked`、`method_invalid`。
- [ ] `Running` 但未 Ready、Ready 但业务探针失败、Chaos 绑定旧 namespace 且新 Pod 逃逸，均不能判为恢复。
- [ ] 添加 fixtures 覆盖：single-pod kill、no-readiness、probe restart、scheduler failure、正常多副本保活、cleanup 残留。
- [ ] 运行：`python -m pytest tools/tests/test_availability_oracle.py tools/tests/test_runtime_classification_consistency.py -q`。

### Task 5: 把恢复和污染归因纳入知识/证据层

**Files:**
- Modify: `tools/judgment_experience.py`
- Modify: `tools/feedback_protocol.py`
- Modify: `artifacts/experiments/availability_defense_design.md`
- Create: `tools/tests/test_availability_feedback.py`

- [ ] 将 `JE-RECOVERY-001` 扩展为有边界的 recovery judgment：必须带 recovery deadline、独立 oracle 和环境状态；`source_verified=false` 时只能生成 `bounded` 机制结论。
- [ ] 增加 `AD-SELFHEAL-001`：runtime recovery 超过 profile deadline 或业务恢复未完成，判 `recovery_timeout`；绝对时长受环境污染时只保留相对结论。
- [ ] 增加 `AD-PROBE-001`：探针触发的 SIGKILL/restart 与应用自愈分开；注入停止后新 Pod 逃逸必须标记 `probe_restart_escape`。
- [ ] availability evidence 进入 feedback card 时包含 baseline/injection/observation/recovery/cleanup/independent_oracle 六项；projected knowledge 禁止包含 runtime verdict、Pod UID 和具体实验结果。
- [ ] 测试 blocked、unavailable、contradictory evidence 不得晋级为 confirmed weakness 或 reusable defense。
- [ ] 运行：`python -m pytest tools/tests/test_availability_feedback.py tools/tests/test_feedback_protocol.py tools/tests/test_judgment_experience.py -q`。

### Task 6: 让 native discovery 能发现部署级假设

**Files:**
- Modify: `tools/run_native_full_discovery.py`
- Modify: `tools/open_discovery_compiler.py`
- Modify: `tools/chaosatlas_two_arm_protocol.py`
- Create: `tools/tests/test_native_deployment_discovery.py`

- [ ] 在 manifest-only bundle 中加入 deployment nodes、scenario fault catalog 和 generic availability/recovery vocabulary；不得加入 CE 已选 hypothesis、runtime evidence、旧 weakness 或 CE verdict。
- [ ] 输出 schema 增加 `target_kind: deployment|scenario|dependency_edge`，并要求 deployment hypothesis 有 `expected_steady_state`、`recovery_expectation`、`validation_plan`。
- [ ] 保留现有 at-most-8 hypothesis、compile gate、seed 和 snapshot hash 规则；deployment hypothesis 使用同一预算和 same common input。
- [ ] 生成两类离线产物：`native_discovery_output.json` 和 `coverage_denominator.json`；静态候选全集只作为 denominator，不当作 discovery 证据。
- [ ] 测试：没有知识视图时可以生成 deployment hypothesis；输入含 `candidate_id`、runtime observation、CE verdict 时 fail closed。
- [ ] 运行：`python -m pytest tools/tests/test_native_deployment_discovery.py tools/tests/test_chaosatlas_two_arm_protocol.py -q`。

### Task 7: 统一 runner 执行 ordered/concurrent scenario

**Files:**
- Create: `tools/run_deployment_scenario.py`
- Modify: `tools/run_chaos_experiment.py`
- Modify: `tools/run_sock_shop_two_arm.py`
- Modify: `tools/runtime_applicability_gate.py`
- Create: `tools/tests/test_run_deployment_scenario.py`

- [ ] 新 runner 只编排 scenario，不重新实现 kubectl/Chaos Mesh primitive；primitive 通过现有 runner/helper 调用。
- [ ] 每个 phase 开始前确认 namespace、target selector、Chaos Mesh controller/daemon、目标 Pod Ready；每个 fault 记录 resource UID 和 injectedCount。
- [ ] concurrent phase 必须等待所有 fault confirmed 后再观测；phase 清理必须确认所有资源删除后才进入下一 phase。
- [ ] ordered phase 记录 `phase_start/end`、`fault_start/end`、`observation_window`、`recovery_window`，并保留原始 status stream。
- [ ] 运行失败必须区分 `environment_blocked`、`method_invalid`、`apply_failed`、`injection_not_confirmed`，不能归为 defended 或 weakness。
- [ ] dry-run 测试不得修改集群；integration test 使用 mock kubectl/Chaos API，不依赖真实 cluster。
- [ ] 运行：`python -m pytest tools/tests/test_run_deployment_scenario.py tools/tests/test_runtime_applicability_gate.py -q`。

### Task 8: 实现 manifest improvement/retest 原生闭环

**Files:**
- Create: `tools/deployment_improvement.py`
- Create: `tools/tests/test_deployment_improvement.py`
- Modify: `tools/feedback_protocol.py`

- [ ] 对 `availability_degraded`/`recovery_timeout` 生成结构化 patch proposal：精确 source file、JSON Pointer/YAML path、old value、new value、reason、expected oracle change、rollback。
- [ ] 支持至少三类 patch：replicas/PDB/HPA redundancy、readiness/liveness probe、resource limits/requests；不允许任意文本替换。
- [ ] patch 必须在 fresh namespace 或 immutable copy 中应用，运行 `kubectl diff --server-side --dry-run=server`（若环境不可用则显式 blocked）。
- [ ] 重新运行同一 scenario node 和同一 oracle；输出 `improvement_verified`、`regression`、`deployment_blocked` 或 `not_run`。
- [ ] 测试 patch 不覆盖用户未声明文件、不修改原始 source tree、rollback 可恢复、验证失败不能被标记 verified。
- [ ] 运行：`python -m pytest tools/tests/test_deployment_improvement.py -q`。

### Task 9: 生成原生能力覆盖报告，保留可选 CE validation profile

**Files:**
- Create: `tools/capability_coverage_report.py`
- Create: `artifacts/experiments/chaos_eater_capability_profile.json`
- Create: `tools/tests/test_capability_coverage_report.py`
- Modify: `docs/CHAOSATLAS_METHOD_DETAILED_FOR_SUPERVISOR_2026-08-16.md`

- [ ] 从原生能力 schema 生成 deployment availability/recovery profile；该 profile 不读取 CE artifact。
- [ ] 将 CE archived input 作为可选 external validation profile 转换到同一 schema；使用 native scenario compiler/runner 时不得添加 CE-specific branch。该 replay 不是 native capability 的必要条件。
- [ ] 报告 coverage cells：`deployment_model`、`hypothesis_generation`、`scenario_compilation`、`fault_execution`、`ce_steady_state`、`native_recovery`、`attribution`、`improvement_retest`，每个 cell 标记 `verified/static_only/blocked/not_run`。
- [ ] 同时报告 `native_capability_coverage` 和 `ce_profile_validation`；不报告“我们的 weakness 数量超过 CE”作为结论。
- [ ] 完整能力声明只要求必需 native capability cells 为 `verified`；存在 blocked/not_run 只能输出 partial。CE external validation 单独标记 `not_run` 或 `blocked`，不混入 native capability 分母。
- [ ] 运行：`python -m pytest tools/tests/test_capability_coverage_report.py -q`。

---

## 四、离线执行顺序

GLM 必须先完成所有离线任务，再申请真实集群执行：

```powershell
python -m pytest tools/tests/test_deployment_capability.py tools/tests/test_build_deployment_capability_pool.py tools/tests/test_compile_scenario_node.py -q
python -m pytest tools/tests/test_availability_oracle.py tools/tests/test_availability_feedback.py tools/tests/test_native_deployment_discovery.py -q
python -m pytest tools/tests/test_run_deployment_scenario.py tools/tests/test_deployment_improvement.py tools/tests/test_capability_coverage_report.py -q
python -m pytest tools/tests -q --basetemp .pytest-tmp-deployment-capability
git diff --check
```

离线 dry-run：

```powershell
python tools/build_deployment_capability_pool.py --project sock-shop --manifest-root artifacts/experiments/chaos_eater_deployed --output artifacts/experiments/chaosatlas_deployment_capability_dryrun_2026-08-20
python tools/compile_scenario_node.py --scenario artifacts/experiments/chaos_eater_capability_profile.json --output artifacts/experiments/chaosatlas_deployment_capability_dryrun_2026-08-20
python tools/run_deployment_scenario.py --scenario artifacts/experiments/chaosatlas_deployment_capability_dryrun_2026-08-20/scenario.json --dry-run --output artifacts/experiments/chaosatlas_deployment_capability_dryrun_2026-08-20/dry-run
python tools/capability_coverage_report.py --input artifacts/experiments/chaosatlas_deployment_capability_dryrun_2026-08-20 --output artifacts/experiments/chaosatlas_deployment_capability_dryrun_2026-08-20/capability_coverage.json
```

GLM 不得使用 `git add .`，不得覆盖已有非空 artifact 目录，不得读取或写入 API key，不得在未确认环境 gate 前启动集群实验。

---

## 五、真实集群验收

真实运行必须使用独立 namespace、固定 source commit、固定 image digest、固定 seed 和 fresh output directory。

### Gate A：部署和基线

- 所有目标 Deployment、Service、Chaos Mesh controller/daemon Ready。
- 业务 baseline 连续通过；k6 profile 记录请求数、并发、入口和 timeout。
- `availableReplicas`、Ready Pod UID、业务 probe 和 controller status 同步采样。

### Gate B：原生服务级能力验证

- 至少选择一个有入口流量的 Deployment 和一个内部关键 Deployment；
- 覆盖至少一种资源压力、网络故障和 Pod/Container 故障；
- 至少验证一个 ordered scenario 和一个 concurrent scenario；
- 每个 phase 注入确认、观测、清理和恢复证据齐全。

CE Sock Shop sequence 可以作为单独的 `external_validation` 附录运行，但不参与 ChaosAtlas native capability 的定义或实现。

### Gate C：Native recovery

- `availableReplicas` 结果与 CE oracle 单独输出；
- recovery 必须完成 replacement identity + Ready + business probe 连续成功 + cleanup；
- 探针重启、无 readiness 假恢复、scheduler/control-plane 失败单独分类。

### Gate D：Improvement retest

- 至少对一个可用性/恢复问题应用结构化 manifest patch；
- fresh namespace 重部署；
- 重跑相同 scenario 和相同 oracle；
- 结果必须为 `improvement_verified` 或明确 `deployment_blocked`，不能省略。

---

## 六、最终判定标准

### 可以声称“ChaosAtlas 原生覆盖该能力层”

必须同时满足：

1. deployment/scenario node 无 CE 专用分支；
2. native discovery 能从 manifest-only 输入生成部署级 hypothesis；
3. ordered/concurrent scenario 能执行服务级多目标故障；
4. 通用 deployment-availability oracle（可配置 `availableReplicas`、比例和连续零值）和 ChaosAtlas recovery oracle 同时可用；
5. recovery attribution 能区分真实恢复与假恢复/污染；
6. 至少一条 manifest improvement 已重部署并复测；
7. 必需能力 cells 全部 `verified`。

### 只能声称“部分覆盖”

任何一个核心能力为 `static_only`、`blocked` 或 `not_run`，或 improvement 尚未重测，都只能使用 `partial_capability_coverage`。

### 禁止声称

- “我们发现的 weakness 覆盖了 CE 的全部 weakness”；
- “我们只要采样 Ready pod 就具备 CE 的可用性能力”；
- “静态 replicas=1 就等于已经证明恢复失败”；
- “可选 CE replay 成功就证明 ChaosAtlas 在所有项目上都具备该能力”；
- “环境 blocked 是 defended 或 weakness”。

---

## 七、给 GLM 的提交与交接规则

每个 Task 完成后必须提交：

1. 修改文件清单；
2. focused test 命令和完整输出摘要；
3. artifact/schema 版本和输入 hash；
4. 未完成项、environment blocked 项和不支持的 claim；
5. 下一 Task 的前置条件。

最终交接必须包含：

```text
native_model_status
native_discovery_status
scenario_compiler_status
availability_oracle_status
recovery_attribution_status
improvement_retest_status
ce_profile_validation_status
capability_coverage_json
known_blockers
```

不得用“测试通过”替代上述能力状态；单元测试通过只证明接口正确，不能替代真实集群 Gate A-D。
