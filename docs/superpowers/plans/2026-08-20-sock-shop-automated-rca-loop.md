# Sock Shop 自动 RCA 与经验迭代闭环实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不改变现有混沌实验生命周期语义的前提下，为 Sock Shop 建立“弱点案例 -> RCA 假设 -> 证据/反证 -> 区分动作 -> 知识卡 -> 回归意图”的可审计自动闭环。

**Architecture:** 新增一个无副作用的 RCA 核心层，负责案例、证据、假设、状态转换和动作评分；新增 Sock Shop 适配器，将现有 `sock_shop_verdicts.json`、可用性证据和静态 manifest 事实编译成三个 RCA 案例。知识投影器只生成 `provisional` 草稿和回归意图，不直接修改正式知识库；只有通过确定性晋级门槛的卡片才允许进入本项目知识库，跨项目复用继续走现有反馈协议。

**Tech Stack:** Python 3、标准库 `json`/`hashlib`/`argparse`/`pathlib`、现有运行报告 JSON、现有 `unified_experiment_protocol.py`、`classify_runtime_result.py`、`decision_engine.py` 和 pytest/unittest 测试体系。

---

## 文件边界

| 文件 | 职责 |
|---|---|
| `tools/rca_loop.py` | 通用 RCA 数据结构、规范化 ID、证据范围校验、状态转换、知识晋级和动作评分；无文件写入和集群副作用。 |
| `tools/sock_shop_rca.py` | Sock Shop 结果适配、三类 RCA 假设模板、现有证据引用和 pilot artifact 编译；只读已有证据，写入显式 output 目录。 |
| `tools/validate_rca_loop.py` | 校验 RCA case、hypothesis、action plan、knowledge draft 和 regression intent 的 schema、路径边界、hash 和状态一致性。 |
| `tools/compile_rca_regression.py` | 将 `local_reusable` 或明确允许复用的 `provisional` case 编译为下一轮 `reproduce`、`discriminate`、`guard` 意图；不执行注入。 |
| `tools/tests/test_rca_loop.py` | 通用数据契约、证据极性、状态机、晋级门槛和动作评分测试。 |
| `tools/tests/test_sock_shop_rca.py` | Sock Shop 三类案例、假设模板、证据引用、pilot 输出和安全过滤测试。 |
| `tools/tests/test_validate_rca_loop.py` | 校验器正例、越界路径、敏感值、状态不一致和缺失字段测试。 |
| `tools/tests/test_compile_rca_regression.py` | 回归意图生成、卡片状态过滤、快照哈希和反例降级测试。 |
| `artifacts/sock-shop/rca_loop/` | 第一轮机器产物目录：`manifest.json`、`cases/`、`hypotheses/`、`action_plan.json`、`knowledge_drafts/`、`regression_intents.json`、`validation_report.json`。该目录不等同于正式 `knowledge_base`。 |
| `docs/KNOWLEDGE_BASE.md` | 补充 RCA card 的检索和晋级边界说明；不删除现有规则。 |

## Task 1: 建立 RCA 核心数据契约

**Files:**
- Create: `tools/rca_loop.py`
- Test: `tools/tests/test_rca_loop.py`

- [ ] **Step 1: 写失败测试，锁定核心常量和纯函数接口**

在 `tools/tests/test_rca_loop.py` 中加入以下测试入口：

```python
from rca_loop import (
    RCA_STATES,
    KNOWLEDGE_STATES,
    build_weakness_id,
    make_evidence,
    validate_evidence_scope,
)


def test_status_enums_and_stable_weakness_id() -> None:
    assert RCA_STATES == {"pending", "bounded", "confirmed", "rejected"}
    assert "local_reusable" in KNOWLEDGE_STATES
    assert build_weakness_id("sock-shop", "front-end->catalogue", "HTTPChaos", "abort") == "WS-sock-shop-front-end-catalogue-httpchaos-abort"


def test_evidence_requires_polarity_scope_and_reference() -> None:
    evidence = make_evidence(
        evidence_id="EV-001",
        kind="runtime_log",
        polarity="supports",
        claim_scope="front-end->catalogue",
        source_ref="artifacts/sock-shop/logs/catalogue.log",
        interpretation="catalogue-side request failure appears during the injection window",
    )
    assert validate_evidence_scope(evidence, "front-end->catalogue")["valid"] is True
    assert validate_evidence_scope(evidence, "orders->payment")["valid"] is False
```

`RCA_STATES`、`KNOWLEDGE_STATES`、`build_weakness_id`、`make_evidence` 和
`validate_evidence_scope` 必须在实现前不存在，确保测试先失败。

- [ ] **Step 2: 运行测试确认失败**

运行：

```powershell
python -m pytest tools/tests/test_rca_loop.py -q
```

预期：由于 `rca_loop` 尚未创建而失败。

- [ ] **Step 3: 实现最小数据契约和规范化函数**

在 `tools/rca_loop.py` 中实现：

```python
RCA_STATES = {"pending", "bounded", "confirmed", "rejected"}
KNOWLEDGE_STATES = {
    "none", "provisional", "local_reusable",
    "cross_project_pending", "cross_project_reusable", "contested",
}
EVIDENCE_POLARITIES = {"supports", "contradicts", "unavailable", "neutral"}


def build_weakness_id(project_id: str, edge: str, family: str, operation: str) -> str:
    # Lowercase, replace all non-alphanumeric runs with one hyphen, and retain
    # the WS prefix so the ID is stable across repeated reports.
    import re
    parts = [project_id, edge, family, operation]
    normalized = [re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") for value in parts]
    return "WS-" + "-".join(item for item in normalized if item)


def make_evidence(*, evidence_id: str, kind: str, polarity: str,
                  claim_scope: str, source_ref: str,
                  interpretation: str, sha256: str | None = None,
                  window: dict[str, str] | None = None) -> dict[str, Any]:
    if polarity not in EVIDENCE_POLARITIES:
        raise ValueError(f"unsupported evidence polarity: {polarity}")
    if not evidence_id or not kind or not claim_scope or not source_ref or not interpretation:
        raise ValueError("evidence_id, kind, claim_scope, source_ref and interpretation are required")
    return {
        "evidence_id": evidence_id,
        "kind": kind,
        "polarity": polarity,
        "claim_scope": claim_scope,
        "source_ref": source_ref.replace("\\", "/"),
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "window": window or {},
        "sha256": sha256,
        "interpretation": interpretation,
    }


def validate_evidence_scope(evidence: dict[str, Any], claim_scope: str) -> dict[str, Any]:
    errors = []
    if evidence.get("polarity") not in EVIDENCE_POLARITIES:
        errors.append("unsupported_polarity")
    if evidence.get("claim_scope") != claim_scope:
        errors.append("claim_scope_mismatch")
    source_ref = str(evidence.get("source_ref") or "")
    if not source_ref or source_ref.startswith(("/", "\\")) or ":" in source_ref or ".." in source_ref.split("/"):
        errors.append("source_ref_must_be_relative")
    if not str(evidence.get("interpretation") or "").strip():
        errors.append("interpretation_required")
    return {"valid": not errors, "errors": errors}
```

实现要求：拒绝未知极性、空 `source_ref`、空 `interpretation` 和 claim scope
不匹配；`unavailable` 只能作为不可用证据，不能计入支持或反对计数；所有规范化
JSON 使用 `sort_keys=True`、紧凑分隔符和 `ensure_ascii=True`。

- [ ] **Step 4: 运行测试确认通过并补充不可用证据测试**

增加测试：不可用证据必须验证通过但不增加支持计数；含 `password=REDACTED`、`token=REDACTED`
或绝对路径的证据引用必须被 validator 拒绝，而不是写入 artifact。

运行：

```powershell
python -m pytest tools/tests/test_rca_loop.py -q
```

预期：所有核心数据契约测试通过。

- [ ] **Step 5: Commit**

```powershell
git add tools/rca_loop.py tools/tests/test_rca_loop.py
git commit -m "feat: add RCA evidence data contract"
```

## Task 2: 实现 RCA 状态机和知识晋级门槛

**Files:**
- Modify: `tools/rca_loop.py`
- Test: `tools/tests/test_rca_loop.py`

- [ ] **Step 1: 写状态转换失败测试**

加入以下测试：

```python
from rca_loop import evaluate_rca_transition, evaluate_knowledge_promotion


def test_bounded_requires_boundary_and_supporting_evidence() -> None:
    result = evaluate_rca_transition(
        current="pending",
        target="bounded",
        boundary_confirmed=True,
        supporting_evidence=1,
        required_evidence_complete=False,
        discriminating_action=False,
        high_severity_contradiction=False,
    )
    assert result == {"allowed": True, "reason": "stable_boundary_with_supporting_evidence"}


def test_confirmed_rejects_plausible_but_unproved_mechanism() -> None:
    result = evaluate_rca_transition(
        current="pending",
        target="confirmed",
        boundary_confirmed=True,
        supporting_evidence=2,
        required_evidence_complete=False,
        discriminating_action=True,
        high_severity_contradiction=False,
    )
    assert result["allowed"] is False
    assert result["reason"] == "required_evidence_incomplete"


def test_local_promotion_requires_regression_and_reproduction() -> None:
    result = evaluate_knowledge_promotion(
        current="provisional",
        weakness_status="confirmed",
        rca_status="bounded",
        valid_reproductions=2,
        valid_counterfactuals=0,
        lifecycle_complete=True,
        direct_evidence=True,
        applicability_complete=True,
        regression_complete=True,
        contradiction=False,
    )
    assert result["allowed"] is True
    assert result["next_status"] == "local_reusable"
```

- [ ] **Step 2: 运行测试确认失败**

```powershell
python -m pytest tools/tests/test_rca_loop.py -q
```

预期：函数未定义或返回值不满足门槛。

- [ ] **Step 3: 实现状态转换和审计原因**

在 `tools/rca_loop.py` 中实现：

```python
def evaluate_rca_transition(*, current: str, target: str,
                            boundary_confirmed: bool,
                            supporting_evidence: int,
                            required_evidence_complete: bool,
                            discriminating_action: bool,
                            high_severity_contradiction: bool) -> dict[str, Any]:
    allowed_transitions = {
        "pending": {"pending", "bounded", "confirmed", "rejected"},
        "bounded": {"pending", "bounded", "confirmed", "rejected"},
        "confirmed": {"bounded", "confirmed", "rejected"},
        "rejected": {"rejected", "pending"},
    }
    if current not in RCA_STATES or target not in RCA_STATES:
        return {"allowed": False, "reason": "unknown_rca_state"}
    if target not in allowed_transitions[current]:
        return {"allowed": False, "reason": "illegal_rca_transition"}
    if target == "bounded" and (not boundary_confirmed or supporting_evidence < 1):
        return {"allowed": False, "reason": "bounded_requires_boundary_and_support"}
    if target == "confirmed":
        if high_severity_contradiction:
            return {"allowed": False, "reason": "high_severity_contradiction"}
        if not required_evidence_complete:
            return {"allowed": False, "reason": "required_evidence_incomplete"}
        if not discriminating_action:
            return {"allowed": False, "reason": "discriminating_action_required"}
    if target == "rejected" and not high_severity_contradiction and supporting_evidence > 0:
        return {"allowed": False, "reason": "rejection_requires_falsifier"}
    reason = {
        "bounded": "stable_boundary_with_supporting_evidence",
        "confirmed": "required_evidence_and_discriminating_action_complete",
        "rejected": "falsifier_or_reproducible_contradiction",
    }.get(target, "state_unchanged")
    return {"allowed": True, "reason": reason, "next_status": target}


def evaluate_knowledge_promotion(*, current: str, weakness_status: str,
                                 rca_status: str, valid_reproductions: int,
                                 valid_counterfactuals: int,
                                 lifecycle_complete: bool,
                                 direct_evidence: bool,
                                 applicability_complete: bool,
                                 regression_complete: bool,
                                 contradiction: bool) -> dict[str, Any]:
    if contradiction:
        next_status = "contested" if current in {"local_reusable", "cross_project_pending", "cross_project_reusable"} else "provisional"
        return {"allowed": True, "reason": "meaningful_counterexample", "next_status": next_status}
    if current == "provisional":
        if weakness_status not in {"confirmed", "protected"}:
            return {"allowed": False, "reason": "weakness_status_not_eligible"}
        if valid_reproductions < 2 and not (valid_reproductions >= 1 and valid_counterfactuals >= 1):
            return {"allowed": False, "reason": "reproduction_gate_incomplete"}
        if not lifecycle_complete or not direct_evidence:
            return {"allowed": False, "reason": "evidence_gate_incomplete"}
        if not applicability_complete or not regression_complete:
            return {"allowed": False, "reason": "operational_card_fields_incomplete"}
        if rca_status not in {"bounded", "confirmed"}:
            return {"allowed": False, "reason": "rca_status_not_reusable"}
        return {"allowed": True, "reason": "local_reuse_gates_passed", "next_status": "local_reusable"}
    if current == "local_reusable":
        return {"allowed": True, "reason": "requires_cross_project_review_or_replication", "next_status": "cross_project_pending"}
    return {"allowed": False, "reason": "promotion_not_allowed_from_current_state"}
```

规则必须显式覆盖：非法转换、`pending -> bounded`、`pending -> confirmed`、
`bounded -> confirmed`、反证导致 `confirmed -> bounded`、反例导致知识卡
降级为 `provisional` 或 `contested`。返回值必须包含 `allowed`、`reason` 和
在允许时的 `next_status`，不允许只返回布尔值。

- [ ] **Step 4: 补充环境阻断和反例测试**

测试环境阻断不能通过 `weakness_status=confirmed`；测试高严重性反证不能让
`rca_status=confirmed` 晋级；测试 `local_reusable` 的反例会进入 `contested`，
且不会删除原 evidence refs。

- [ ] **Step 5: 运行测试并提交**

```powershell
python -m pytest tools/tests/test_rca_loop.py -q
git add tools/rca_loop.py tools/tests/test_rca_loop.py
git commit -m "feat: add RCA and knowledge state gates"
```

## Task 3: 实现确定性证据动作规划器

**Files:**
- Modify: `tools/rca_loop.py`
- Test: `tools/tests/test_rca_loop.py`

- [ ] **Step 1: 写动作评分和 fail-closed 测试**

测试以下行为：源码/config 查询优先于日志，日志优先于业务重放，业务重放优先于新注入；
动作缺少 namespace、precondition、cleanup 或 output schema 时不能被选中；能区分两个假设的动作
优先级高于只能支持一个假设的动作。

```python
from rca_loop import plan_next_action


def test_planner_prefers_safe_high_information_action() -> None:
    actions = [
        {"action_id": "A-runtime", "kind": "business_replay", "hypotheses_separated": 2,
         "evidence_gain": 3, "cost": 2, "risk": 1, "environment_uncertainty": 0,
         "preconditions": ["baseline_pass"], "cleanup": ["washout"], "output_schema": "runtime"},
        {"action_id": "A-source", "kind": "source_lookup", "hypotheses_separated": 2,
         "evidence_gain": 3, "cost": 1, "risk": 0, "environment_uncertainty": 0,
         "preconditions": ["source_snapshot"], "cleanup": ["none"], "output_schema": "source"},
    ]
    selected = plan_next_action(actions, available_preconditions={"baseline_pass", "source_snapshot"})
    assert selected["selected"]["action_id"] == "A-source"


def test_planner_rejects_action_without_cleanup_contract() -> None:
    action = {"action_id": "A-bad", "kind": "pod_kill", "hypotheses_separated": 3,
              "evidence_gain": 5, "cost": 0, "risk": 0, "environment_uncertainty": 0,
              "preconditions": [], "output_schema": "runtime"}
    assert plan_next_action([action], available_preconditions=set())["status"] == "pending"
```

- [ ] **Step 2: 实现动作 schema、评分和选择器**

实现以下函数：

```python
def score_action(action: dict[str, Any]) -> dict[str, Any]:
    """Return information_gain, total_cost, priority and validation errors."""
    required = {"action_id", "kind", "hypotheses_separated", "evidence_gain", "cost", "risk", "environment_uncertainty", "preconditions", "cleanup", "output_schema"}
    errors = sorted(required - set(action))
    if not action.get("cleanup"):
        errors.append("cleanup_contract_required")
    if not action.get("output_schema"):
        errors.append("output_schema_required")
    information_gain = int(action.get("hypotheses_separated", 0)) + int(action.get("evidence_gain", 0))
    total_cost = int(action.get("cost", 0)) + int(action.get("risk", 0)) + int(action.get("environment_uncertainty", 0))
    return {"action_id": action.get("action_id"), "information_gain": information_gain, "total_cost": total_cost, "priority": information_gain - total_cost, "errors": errors}


def plan_next_action(actions: list[dict[str, Any]],
                     available_preconditions: set[str]) -> dict[str, Any]:
    """Select the highest-scoring safe action or return pending with reasons."""
    eligible = []
    rejected = []
    for action in actions:
        scored = score_action(action)
        missing = sorted(set(action.get("preconditions", [])) - available_preconditions)
        if scored["errors"] or missing:
            rejected.append({"action_id": action.get("action_id"), "errors": scored["errors"], "missing_preconditions": missing})
            continue
        eligible.append({**action, "score": scored})
    if not eligible:
        return {"status": "pending", "reason": "no_safe_applicable_action", "rejected": rejected}
    selected = sorted(eligible, key=lambda item: (-item["score"]["priority"], str(item["action_id"]))) [0]
    return {"status": "planned", "selected": selected, "rejected": rejected}
```

评分使用设计文档中的公式：`information_gain + evidence_completeness_gain +
causal_discrimination_gain - execution_cost - risk - environment_uncertainty`。
排序相同分数时按 `action_id` 字典序，保证复现一致。此模块只编译动作，不调用
`kubectl`、Docker 或外部模型。

- [ ] **Step 3: 运行测试并提交**

```powershell
python -m pytest tools/tests/test_rca_loop.py -q
git add tools/rca_loop.py tools/tests/test_rca_loop.py
git commit -m "feat: add deterministic RCA action planner"
```

## Task 4: 编译 Sock Shop 三类 RCA 案例和假设

**Files:**
- Create: `tools/sock_shop_rca.py`
- Test: `tools/tests/test_sock_shop_rca.py`

- [ ] **Step 1: 用冻结 fixture 写三类案例的失败测试**

测试输入使用仓库已有的 `artifacts/sock-shop/sock_shop_verdicts.json`，并在测试中构造最小的 manifest/static evidence fixture，不读取实时集群。

```python
from sock_shop_rca import build_sock_shop_pilot


def test_sock_shop_pilot_builds_three_case_families(tmp_path) -> None:
    output = build_sock_shop_pilot(
        verdict_path=Path("artifacts/sock-shop/sock_shop_verdicts.json"),
        output_root=tmp_path,
        project_commit="sock-shop-fixture-commit",
        round_id="pilot-r1",
    )
    assert [case["case_family"] for case in output["cases"]] == [
        "single_replica_podkill", "catalogue_db_podkill", "http_abort_propagation"
    ]
    assert all(case["weakness_status"] == "confirmed" for case in output["cases"])
    assert output["cases"][1]["rca_status"] == "bounded"
```

- [ ] **Step 2: 运行测试确认失败**

```powershell
python -m pytest tools/tests/test_sock_shop_rca.py -q
```

- [ ] **Step 3: 实现 Sock Shop 证据适配和三类假设模板**

在 `tools/sock_shop_rca.py` 中实现：

实现三个公开函数，并严格采用以下算法：

```python
def build_sock_shop_pilot(*, verdict_path: Path, output_root: Path,
                          project_commit: str, round_id: str) -> dict[str, Any]:
    """Read frozen verdicts, build cases/hypotheses/actions, and write output_root."""
    # 1. Reject a non-empty output_root; load verdict_path as a JSON object.
    # 2. Normalize the contract-layer candidates and availability-layer verdicts.
    # 3. Build exactly three case families from the mapping below.
    # 4. Call hypotheses_for_case and actions_for_case for each case.
    # 5. Write manifest.json, cases/*.json, hypotheses/*.json and action_plan.json.
    # 6. Return the same manifest object after recording input SHA-256 and statuses.


def hypotheses_for_case(case: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the fixed hypothesis templates selected by case_family."""
    # Select templates by case["case_family"], initialize every hypothesis with
    # status="pending", empty evidence_for/evidence_against, unsupported_claims,
    # required_evidence, falsifiers and next_action=None.


def actions_for_case(case: dict[str, Any], hypotheses: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return safe, schema-complete evidence actions for live hypotheses."""
    # For every live hypothesis emit action_id, kind, target_scope,
    # hypotheses_separated, evidence_gain, cost, risk,
    # environment_uncertainty, preconditions, cleanup, output_schema and
    # stop_conditions; then call plan_next_action with the case preconditions.
```

具体映射必须固定如下：

- 单副本 PodKill：生成 `singleton_workload_no_redundancy`，要求 manifest
  `replicas=1`/PDB 事实、Ready 下降和业务影响；可选下一步为隔离扩到两副本后的 PodKill。
- `catalogue-db` PodKill：生成 `database_connection_unavailable` 和
  `catalogue_error_propagation` 两个竞争假设；没有 scoped log/source/counterfactual
  链接时保持 `rca_status=bounded`。
- HTTP abort：生成 `transport_failure_propagates_as_business_error`；只能把结论
  限定在服务边界，不能自动命名为 `missing_timeout`。

每个 hypothesis 必须包含 `expected_observations`、`falsifiers`、`required_evidence`、
`evidence_for`、`evidence_against`、`unsupported_claims`、`status` 和 `next_action`。
所有引用使用相对路径，禁止把 manifest 中的密码或 token 写入输出。

- [ ] **Step 4: 编译 pilot artifact 并验证输出**

命令接口固定为：

```powershell
python tools/sock_shop_rca.py `
  --verdict artifacts/sock-shop/sock_shop_verdicts.json `
  --output artifacts/sock-shop/rca_loop `
  --project-commit sock-shop-fixture-commit `
  --round-id pilot-r1
python tools/compile_rca_regression.py `
  --rca-root artifacts/sock-shop/rca_loop `
  --output artifacts/sock-shop/rca_loop/knowledge_drafts
```

输出必须包含 `manifest.json`、`cases/*.json`、`hypotheses/*.json` 和
`action_plan.json`，并记录输入 hash、每个 case 的状态、选中的下一动作以及未满足门槛。
已存在且非空的 output 目录必须拒绝覆盖，改用新目录由调用方显式指定。

- [ ] **Step 5: 运行测试并提交**

```powershell
python -m pytest tools/tests/test_sock_shop_rca.py -q
git add tools/sock_shop_rca.py tools/tests/test_sock_shop_rca.py
git commit -m "feat: compile Sock Shop RCA pilot cases"
```

## Task 5: 实现 RCA artifact validator

**Files:**
- Create: `tools/validate_rca_loop.py`
- Test: `tools/tests/test_validate_rca_loop.py`

- [ ] **Step 1: 写 validator 失败测试**

覆盖以下情况：合法三案例 artifact 通过；case 缺少 `weakness_status` 失败；hypothesis
把 `client_timeout` 解释成 `missing_timeout` 但没有 source/config evidence 失败；绝对路径、
敏感字段、越界 `source_ref`、case/hypothesis `weakness_id` 不一致失败；`unavailable`
证据不进入 support/contradiction 计数。

- [ ] **Step 2: 实现命令行和校验函数**

实现以下接口：

```python
def validate_case(case: dict[str, Any], root: Path) -> list[str]:
    # Check required IDs/statuses, replica lineage, evidence references and
    # that every source_ref resolves inside root or is explicitly unavailable.


def validate_hypothesis(hypothesis: dict[str, Any], case: dict[str, Any]) -> list[str]:
    # Check weakness_id equality, required lists/status, evidence polarity,
    # claim scope, and reject mechanism claims without matching direct evidence.


def validate_action_plan(plan: dict[str, Any], cases: list[dict[str, Any]]) -> list[str]:
    # Check case IDs, action IDs, preconditions, cleanup, output schema and the
    # selected action returned by plan_next_action.


def validate_artifact(root: Path) -> dict[str, Any]:
    # Load manifest, all case/hypothesis/action files, run the three validators,
    # write validation_report.json and return {"valid", "errors", "warnings"}.
```

CLI 固定为：

```powershell
python tools/validate_rca_loop.py --root artifacts/sock-shop/rca_loop
```

validator 必须输出 `validation_report.json`，返回码为 0/1；只允许 `root` 下的相对文件引用，
拒绝 `..`、驱动器路径、UNC 路径和敏感值模式。它不修改 case 和 hypothesis 原文。

- [ ] **Step 3: 运行 focused tests 和 pilot 校验**

```powershell
python -m pytest tools/tests/test_validate_rca_loop.py -q
python tools/validate_rca_loop.py --root artifacts/sock-shop/rca_loop
```

预期：测试通过，pilot validator 报告为 `valid=true`。

- [ ] **Step 4: 提交**

```powershell
git add tools/validate_rca_loop.py tools/tests/test_validate_rca_loop.py
git commit -m "feat: validate RCA evidence artifacts"
```

## Task 6: 生成知识草稿和下一轮回归意图

**Files:**
- Create: `tools/compile_rca_regression.py`
- Test: `tools/tests/test_compile_rca_regression.py`
- Modify: `tools/decision_engine.py`
- Modify: `tools/query_knowledge_base.py`

- [ ] **Step 1: 写回归编译器失败测试**

测试以下规则：`provisional` 只能生成 `discriminate`/`reproduce` 规划，不能改变高影响候选排序；
`local_reusable` 可以生成 `reproduce` 和 `guard`；`contested` 不得生成可执行意图；每个意图必须带
`oracle`、`required_evidence`、`stop_rule`、来源 card ID 和 snapshot hash。

```python
from compile_rca_regression import compile_regression_intents


def test_provisional_card_generates_discrimination_intent_only() -> None:
    card = {"id": "KB-RCA-001", "knowledge_status": "provisional",
            "weakness_status": "confirmed", "rca_status": "bounded",
            "applicability_conditions": ["real_business_path"],
            "regression_recipe": {"oracle": "sock-shop-catalogue"},
            "next_evidence": ["scoped_catalogue_logs"],
            "stop_rule": "stop after two valid reproductions"}
    result = compile_regression_intents([card], snapshot={"cards": [card]})
    assert [item["kind"] for item in result["intents"]] == ["discriminate"]
    assert result["intents"][0]["source_card_id"] == "KB-RCA-001"
```

- [ ] **Step 2: 实现知识投影和回归编译**

在 `tools/compile_rca_regression.py` 中实现：

```python
def project_knowledge_draft(case: dict[str, Any], hypotheses: list[dict[str, Any]],
                            actions: list[dict[str, Any]]) -> dict[str, Any]:
    # Copy only normalized test-node, graph, four-layer, evidence-summary and
    # next-evidence fields; add RCA statuses, applicability, exclusions,
    # counter_evidence, regression_intents and stop_rule; never add secrets.


def compile_regression_intents(cards: list[dict[str, Any]],
                               snapshot: dict[str, Any]) -> dict[str, Any]:
    # Canonicalize snapshot, compute SHA-256, reject contested cards, emit one
    # bounded intent per eligible card, and include source_card_id, snapshot
    # hash, oracle, required_evidence and stop_rule in every intent.
```

`project_knowledge_draft` 必须生成现有知识库要求的 `id`、`version`、`status`、
`evidence_state`、`project`、`project_commit`、`test_node`、`test_node_centered_graph`、
`four_layer_validation`、`next_evidence`，并添加 `weakness_status`、`rca_status`、
`knowledge_status`、`mechanism_level`、`applicability_conditions`、`exclusion_conditions`、
`counter_evidence`、`regression_intents` 和 `stop_rule`。`provisional` 草稿放入
`artifacts/sock-shop/rca_loop/knowledge_drafts/`，不写入正式 `knowledge_base/index.json`。

`compile_regression_intents` 必须用规范化 JSON 计算 snapshot SHA-256，并把 `source_card_id`、
`snapshot_sha256`、`oracle`、`required_evidence` 和 `stop_rule` 写入每个 intent。

CLI 固定为：

```powershell
python tools/compile_rca_regression.py --rca-root artifacts/sock-shop/rca_loop --output artifacts/sock-shop/rca_loop/knowledge_drafts
```

命令读取 `cases/`、`hypotheses/` 和 `action_plan.json`，生成 knowledge drafts 与
`regression_intents.json`；输出目录非空时拒绝覆盖。

- [ ] **Step 3: 以最小兼容方式接入 decision/query**

在 `tools/decision_engine.py` 增加一个可选参数 `rca_snapshot: dict[str, Any] | None = None`，
沿 `score_candidate(candidate, knowledge_snapshot=None, rca_snapshot=None)` 和
`rank(candidates, knowledge_snapshot=None, rca_snapshot=None)` 逐层传递该参数；仅当卡片
`knowledge_status=local_reusable` 且没有 `contested=true` 时增加候选解释和诊断要求；
`provisional` 和 `cross_project_pending` 只能作为说明，不得改变既有 hard filter、protected skip
和排序结果。

在 `tools/query_knowledge_base.py` 增加 `--rca-status`、`--knowledge-status` 和
`--weakness-id` 过滤；Sock Shop RCA 草稿通过显式 `--rca-root` 查询，不把 provisional 卡片混入
现有正式卡片总数。

- [ ] **Step 4: 运行测试并提交**

```powershell
python -m pytest tools/tests/test_compile_rca_regression.py tools/tests/test_decision_engine.py -q
git add tools/compile_rca_regression.py tools/tests/test_compile_rca_regression.py tools/decision_engine.py tools/query_knowledge_base.py
git commit -m "feat: compile RCA knowledge and regression intents"
```

## Task 7: 生成三案例 pilot 产物并接入文档边界

**Files:**
- Modify: `docs/KNOWLEDGE_BASE.md`
- Create: `artifacts/sock-shop/rca_loop/manifest.json`
- Create: `artifacts/sock-shop/rca_loop/cases/*.json`
- Create: `artifacts/sock-shop/rca_loop/hypotheses/*.json`
- Create: `artifacts/sock-shop/rca_loop/action_plan.json`
- Create: `artifacts/sock-shop/rca_loop/knowledge_drafts/*.json`
- Create: `artifacts/sock-shop/rca_loop/regression_intents.json`
- Create: `artifacts/sock-shop/rca_loop/validation_report.json`

- [ ] **Step 1: 运行离线 pilot 编译**

```powershell
python tools/sock_shop_rca.py --verdict artifacts/sock-shop/sock_shop_verdicts.json --output artifacts/sock-shop/rca_loop --project-commit sock-shop-fixture-commit --round-id pilot-r1
python tools/compile_rca_regression.py --rca-root artifacts/sock-shop/rca_loop --output artifacts/sock-shop/rca_loop/knowledge_drafts
python tools/validate_rca_loop.py --root artifacts/sock-shop/rca_loop
```

只读归档证据；不调用 kubectl、Docker、LLM 或网络。若目录已存在且非空，先停止，不覆盖已有结果。

- [ ] **Step 2: 检查三类输出的状态和边界**

必须得到：

- 单副本案例 `weakness_status=confirmed`，RCA 至少 `bounded`，机制限定为无冗余；
- `catalogue-db` 案例 `weakness_status=confirmed`，RCA 在没有连接日志/源码关联时保持 `bounded`；
- HTTP abort 案例只能生成服务边界传播结论，不能自动写 `missing_timeout`；
- 每个案例至少有一个自动生成的下一动作；
- 每个 provisional 草稿都有 `next_evidence` 和回归意图；
- 所有引用都能解析到现有 artifact 或明确标记 `unavailable`；
- `knowledge_base_updated` 保持 `false`，正式知识库数量不增加。

- [ ] **Step 3: 更新知识库规范说明**

在 `docs/KNOWLEDGE_BASE.md` 增加“RCA loop artifacts”小节，明确：

- `rca_loop/knowledge_drafts` 是临时/项目内调查产物，不等同于正式知识卡；
- `weakness_status`、`rca_status`、`knowledge_status` 必须独立解释；
- `bounded` 是允许的成功结果，不能被强行提升为 `confirmed`；
- 只有 `local_reusable` 才能影响本项目高影响候选排序；
- `cross_project_pending` 仍需现有 feedback protocol；
- pending 或 contested 证据不能静默覆盖历史记录。

- [ ] **Step 4: 运行完整 pilot 验收并提交**

```powershell
python -m pytest tools/tests/test_rca_loop.py tools/tests/test_sock_shop_rca.py tools/tests/test_validate_rca_loop.py tools/tests/test_compile_rca_regression.py tools/tests/test_decision_engine.py tools/tests/test_feedback_protocol.py -q
python tools/validate_rca_loop.py --root artifacts/sock-shop/rca_loop
python tools/validate_knowledge_base.py --root artifacts/train-ticket/knowledge_base
git diff --check
```

检查通过后，只暂存本任务新增的 RCA 工具、测试、规范说明和 `artifacts/sock-shop/rca_loop/`，不得使用 `git add .`。

```powershell
git add docs/KNOWLEDGE_BASE.md tools/rca_loop.py tools/sock_shop_rca.py tools/validate_rca_loop.py tools/compile_rca_regression.py tools/decision_engine.py tools/query_knowledge_base.py tools/tests/test_rca_loop.py tools/tests/test_sock_shop_rca.py tools/tests/test_validate_rca_loop.py tools/tests/test_compile_rca_regression.py artifacts/sock-shop/rca_loop
git commit -m "feat: close Sock Shop automated RCA loop"
```

## Task 8: 端到端闭环回归和后续执行接口验收

**Files:**
- Modify: `tools/tests/test_sock_shop_rca.py`
- Modify: `tools/tests/test_compile_rca_regression.py`
- Modify: `tools/tests/test_decision_engine.py`
- Modify: `docs/KNOWLEDGE_BASE.md`

- [ ] **Step 1: 验证经验确实反向影响下一轮**

构造一张 `local_reusable` 的 Sock Shop 边界卡，运行候选选择后确认：

- 候选包含来源 card ID；
- 业务 oracle 被强制绑定到真实业务链路；
- 诊断需求包含该卡的 `next_evidence`；
- 已关闭的边界带有 `closed_runtime_boundary_no_reinjection` 停止规则；
- 同一输入快照重复运行产生相同候选排序、action plan 和 snapshot hash。

- [ ] **Step 2: 验证反例回流**

向已生成卡片添加 `contradicts` evidence，确认：

- RCA 从 `confirmed` 降为 `bounded` 或 `rejected`；
- knowledge 从 `local_reusable` 变为 `provisional` 或 `contested`；
- 原卡片、原证据、原 snapshot hash 保留；
- 新一轮决策不再把 contested 卡片当作强先验。

- [ ] **Step 3: 运行完整回归集**

```powershell
python -m pytest tools/tests -q --basetemp .pytest-tmp-rca-loop
python tools/validate_rca_loop.py --root artifacts/sock-shop/rca_loop
python tools/validate_knowledge_base.py --root artifacts/train-ticket/knowledge_base
git diff --check
```

预期：新增 RCA 测试、现有知识协议测试和现有知识库 validator 全部通过；不启动集群实验，不触发外部模型调用。

- [ ] **Step 4: Commit**

```powershell
git add tools/tests/test_sock_shop_rca.py tools/tests/test_compile_rca_regression.py tools/tests/test_decision_engine.py docs/KNOWLEDGE_BASE.md
git commit -m "test: verify RCA feedback loop and counterexamples"
```

## 实施后的明确边界

1. 第一版自动完成的是案例创建、假设生成、证据状态维护、下一步动作规划、知识草稿和回归意图生成。
2. 第一版不在测试执行期间自动调用 kubectl，也不替历史 pending 结果背书；实际注入仍由现有 runtime runner 和显式 gate 执行。
3. 只有下一轮运行产生新的完整证据后，才能把相应 `provisional` 草稿晋级为 `local_reusable`。
4. 跨项目知识仍然使用现有 `feedback_protocol.py` 的 review/order/round 隔离，不由 RCA 模块绕过。
5. 任何业务弱点都可以有 `rca_status=bounded`；系统成功的标准是证据边界清楚、下一动作可执行，而不是强行产出一个根因名称。

## 计划自检

- 规格第 2 节目标 1-4 覆盖在 Task 1-5；目标 5-7 覆盖在 Task 6-8；目标 8 覆盖在 Task 1、5、7、8。
- 规格第 3 节非目标通过 Task 7 的离线 pilot、Task 8 的无集群/无外部模型验收和显式跨项目边界落实。
- `pending`、`bounded`、`confirmed`、`rejected`、`provisional`、`local_reusable`、`cross_project_pending`、`cross_project_reusable` 和 `contested` 均有数据契约、状态测试或验证任务。
- 未使用“稍后补充”“适当处理”“TODO”等未落地步骤；每个代码任务给出具体路径、函数接口、测试命令和预期结果。
- 实现顺序保持 TDD：先测试、确认失败、写最小实现、运行 focused tests、再提交。
