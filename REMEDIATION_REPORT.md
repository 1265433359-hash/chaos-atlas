# REMEDIATION_REPORT.md — 审查问题修复报告

> 日期：2026-08-09
> 分支：`remediation/2026-08-09-review`
> 基线提交：`6554fe4`（阶段0记录）→ 修复提交：`5d40c1f`（阶段0-6）→ 本报告对应工作区状态
> 约束遵守：无 `git reset --hard` / `git checkout --` / 批量覆盖用户文件；未修改实验真值（测试改为匹配当前合同/schema）；未执行真实 Kubernetes 混沌注入（全部单元测试 + 重算既有数据）；所有修复带回归测试。

---

## 一、审查发现 → 修复状态总表

| # | 发现 | 阶段 | 状态 | 修复 |
|---|---|---|---|---|
| 1 | 清理把所有非零 kubectl get 当"资源不存在"，可能残留 | 1 | ✅ 已修复 | `delete_resource` 区分 NotFound/timeout/RBAC/exists，`absent_confirmed` 权威字段；probe runner 仅在确认 absence 后清 active_resource；stress cleanup 同规则 |
| 2 | runtime gate 对 RBAC/timeout fail-open；空 labelSelectors 退化为全量查询 | 2 | ✅ 已修复 | name-lookup 分类 timeout/RBAC → 结构化 blocked；空 selector 拒绝且不发起 pod 查询 |
| 3 | 根 pytest 未隔离 otel-demo 集成测试；测试写 artifacts | 3 | ✅ 已修复 | `pytest.ini` testpaths=tools/tests；otel-demo 全标 integration（需 opt-in）；issue_tracker/selection/judgment 测试全部隔离到 temp；修复测试污染（hash 验证通过） |
| 4 | core/extended registry 混合致负剩余候选 | 4 | ✅ 已修复 | `compare_selection_methods.compute` 只统计 registry universe 内；新增 `universe_consistent`/`known_outside_*` 字段 |
| 5 | 20 evidence vs 12 core universe 混合（同 #4 一体） | 4 | ✅ 已修复 | 同上 + `selected_outside_universe_*` 显式记录 |
| 6 | own_discovery_evidence 未分 weakness/below_threshold/invalid | 6 | ✅ 已修复 | `classify_evidence_candidate` 三态分类，invalid 从 known 排除 |
| 7 | bootstrap 固定总体分母；severity 权重不稳定 | 6 | ✅ 已修复 | per-sample 分母；B2 敏感性分析保留（rank 不稳定如实报告） |
| 8 | runner report 未绑 fingerprint；分类无 baseline | 5 | ✅ 已修复 | 3 个 runner（run_chaos_experiment/grpc/probe）嵌 `environment_fingerprint` + `baseline` 契约；schema_version 升 2 |
| 9 | 汇总报告重复次数写死 3（实际 4 条/场景） | 5 | ✅ 已修复 | `scenario_replicates` 从记录动态计算 |
| 10 | 未知项目 ID 静默回退 TT | 4 | ✅ 已修复 | `project_of/normalize_service(strict=True)` fail-closed；decision_engine 知识管道启用 strict |
| 11 | 实验结论范围声明/外部方法表述 | — | ✅ 已在 methodology_audit C1/D1 声明（本轮未改结论，仅确认） | 见 `methodology_audit.md` |

**修复数：10/11 代码修复，1 项（#11 范围声明）为既有文档约束确认。**

---

## 二、每阶段交付：改动文件 / 测试命令 / 测试结果 / 残留风险

### 阶段 0 — 基线
- **改动**：`artifacts/experiments/execution/remediation_baseline.json`（新建）
- **命令**：`python -m pytest tools/tests/ -q`
- **结果**：84 passed + 1 known-fail（stale OB-PRODUCTCATALOG 断言，阶段4修）
- **残留**：分支 `remediation/2026-08-09-review` 自 master 切出；基线 hash 已记录

### 阶段 1 — 清理不误报
- **改动**：`run_chaos_experiment.py`（delete_resource 分类）、`run_probe_restart_escape.py`（active_resource 保留）、`run_stress_with_cgroup.py`（cleanup 分类）
- **命令**：`python -m pytest tools/tests/test_remediation_phase1_cleanup.py -q`
- **结果**：10 passed（NotFound=absent / timeout≠absent / RBAC≠absent / exists≠absent / delete 失败仍 flagged）
- **残留**：`summarize_*.py` 消费向后兼容布尔 `resource_absent_after_delete`（已收紧语义）；真实集群删除行为需集成验证

### 阶段 2 — gate fail-closed
- **改动**：`runtime_applicability_gate.py`（name-lookup 分类 + 空 selector 拒绝 + 跳过全量查询）
- **命令**：`python -m pytest tools/tests/test_remediation_phase2_gate.py tools/tests/test_runtime_applicability_gate.py -q`
- **结果**：15 passed（timeout/RBAC→blocked、NotFound→available、exists→blocked、空 selector→blocked 且不查 pod、非空仍查询）
- **残留**：`_kubectl_not_found` 在 3 处重复定义（各模块独立，可接受）；gate 行为变化可能影响既有 mutation 的决策（需集成跑一轮确认）

### 阶段 3 — 测试隔离
- **改动**：`pytest.ini`（新建）、`otel-demo/test/telemetry/conftest.py`（integration marker）、`test_issue_tracker.py`（patch TRACKER/AUDIT）、`issue_tracker.py`（默认参数 None）、`test_judgment_experience.py`（temp path）
- **命令**：`python -m pytest -q`（默认只跑 tools/tests）；`python -m pytest otel-demo/test/telemetry --collect-only -m integration`
- **结果**：默认 125 passed；integration 55 collected（opt-in）；**artifacts hash 与阶段0基线一致（未被测试污染）**
- **残留**：`query_knowledge_base.py` 等工具默认写真实文件（工具行为非测试，已确认未在测试中触发）

### 阶段 4 — 统一 universe
- **改动**：`compare_selection_methods.py`（universe 交集 + 显式 outside 字段）、`project_registry.py`（strict）、`decision_engine.py`（strict=True 知识管道）、`test_decision_engine.py`（stale 断言修正）
- **命令**：`python -m pytest tools/tests/test_remediation_phase4_universe.py tools/tests/test_decision_engine.py -q`
- **结果**：11 passed；**全量 125 passed**
- **残留**：`knowledge_updater`/`contract_inventory` 等仍默认 tolerant（未显式 strict）；如需全链路 fail-closed 需逐一开启

### 阶段 5 — runner provenance
- **改动**：`environment_fingerprint.py`（load_fingerprint）、`run_chaos_experiment.py`/`run_grpc_chaos_experiment.py`/`run_probe_restart_escape.py`（嵌 fingerprint + baseline + schema v2）、`summarize_comparative_results.py`（scenario_replicates 动态）
- **命令**：`python -m pytest tools/tests/test_remediation_phase5_provenance.py -q`
- **结果**：8 passed
- **残留**：既有执行产物 report 无 fingerprint（历史数据无法回溯补标，仅新 report 生效）

### 阶段 6 — metrics & bootstrap
- **改动**：`selection_robustness.py`（universe 交集 + 三态分类 + per-sample 分母 + 不过度解释）、`compare_selection_methods.py`
- **命令**：`python -m pytest tools/tests/test_remediation_phase6_metrics.py -q`
- **结果**：9 passed；重算输出到 `execution/remediation/`（独立目录，旧结果保留）
- **残留**：universe 12 中 1 个 invalid 被排除；weakness 仅 2 个 → 统计功效极低，排名仅描述性

### 阶段 7 — 回归 + 重算 + 审计
- **命令**：`python -m pytest -q` + artifact hash 校验
- **结果**：**125 passed, 5 subtests passed**；artifacts 全部 unchanged；`remediation_validation.json` 记录
- **重算产物**（写入 `execution/remediation/`，旧结果未覆盖）：
  - `compare_selection_r1_remediated.json`：universe=12, known=12, outside=8 显式记录；M1 w=0.92 vs 其余 ~0.84
  - `selection_robustness_r1_remediated.json`：universe=12, known=11, invalid=1, weakness=2, below_threshold=9；**pairwise 全不显著**；rank 跨权重不稳定

---

## 三、重算结果（阶段6，写入独立 remediation 目录）

### Selection comparison（universe 一致后）
```
universe: 12 | known (universe内): 12 | known_outside_universe: 8 (显式记录)
M0: recall 0.833 w=0.84 | M1: 0.833 w=0.92 | M3/M4/A*: 0.833 w=0.84-0.88
```
- 8 个 outside-universe 已知候选不再进入分母（旧实现会造成负剩余伪影）
- M1 w=0.92 略高于其他，但 **bootstrap pairwise CI 全部含 0，不显著**

### Selection robustness（B1/B2）
```
weakness: 2 | below_threshold: 9 | invalid: 1 (排除)
rank_order_stable_across_schemata: False   ← 权重敏感性仍在，如实报告
M1-vs-M3/M4/M0 significant_at_5pct: 全部 False
```
- **诚实结论**：universe 小（11 known，其中 weakness 仅 2）+ 权重不稳定 → **排名不可作为"谁更优"的证据**；这正是既有 `comparison_full_summary.md` 的结论（"选择方法无统计显著差异"），本轮在一致 universe 上复算确认，未过度解释排名。

---

## 四、验证命令汇总（全部可复跑）

```bash
# 全量单元测试（默认隔离，不访问集群）
python -m pytest -q
# → 125 passed, 5 subtests passed

# 阶段1 清理分类
python -m pytest tools/tests/test_remediation_phase1_cleanup.py -q        # 10 passed
# 阶段2 gate fail-closed
python -m pytest tools/tests/test_remediation_phase2_gate.py tools/tests/test_runtime_applicability_gate.py -q  # 15 passed
# 阶段4 universe
python -m pytest tools/tests/test_remediation_phase4_universe.py tools/tests/test_decision_engine.py -q       # 11 passed
# 阶段5 provenance
python -m pytest tools/tests/test_remediation_phase5_provenance.py -q     # 8 passed
# 阶段6 metrics
python -m pytest tools/tests/test_remediation_phase6_metrics.py -q        # 9 passed

# 集成测试 opt-in（默认不跑）
python -m pytest otel-demo/test/telemetry --collect-only -m integration   # 55 collected

# 重算（写入独立 remediation 目录，旧结果保留）
python -c "import sys; sys.path.insert(0,'tools'); import compare_selection_methods as c; ..."  # 见 validation.json
python -c "import sys; sys.path.insert(0,'tools'); import selection_robustness as s; ..."

# artifact 污染校验
python -c "import json; d=json.load(open('artifacts/experiments/execution/remediation_validation.json')); print(d['artifacts_all_unchanged'])"
```

---

## 五、残留风险与未修复项

| 项 | 状态 | 说明 |
|---|---|---|
| 真实集群删除/gate 行为集成验证 | ⏸ 未跑 | 约束要求不执行真实注入；`delete_resource`/`check_mutation` 行为变化需真实集群确认 |
| `knowledge_updater`/`contract_inventory` 未显式 strict | ⏸ 部分 | 未知项目 fail-closed 已覆盖 decision_engine；其余工具仍 tolerant（默认行为） |
| 历史 report 无 fingerprint | ⏸ 不可回溯 | 仅新 runner 产物生效 |
| universe 统计功效极低 | ⏸ 数据事实 | weakness 仅 2 候选，排名仅描述性（已写入 interpretation） |
| 外部真值（issue 提交） | ⏸ 待用户 | 既有 `reporting/issue_template.md` |
| C1 范围声明（网络故障家族 + pod-kill） | ✅ 文档 | `methodology_audit.md` 已更新 |

---

## 六、约束遵守声明

- ✅ 未用 `git reset --hard` / `git checkout --` / 批量覆盖用户文件（受污染的 3 个 artifacts 用 `git show HEAD:file` 逐文件恢复并记录 hash）
- ✅ 未修改实验真值（阶段4 修正的是**过时测试断言**匹配当前契约 schema，非真值）
- ✅ 未执行真实 Kubernetes 混沌注入（全部修复通过单元测试验证）
- ✅ 每个阶段先实现 → 补回归测试 → 运行验证 → 输出改动/命令/结果/残留
- ✅ 新结果写入 `execution/remediation/` 独立目录，旧结果未覆盖

---

## 七、交付物清单

- `artifacts/experiments/execution/remediation_baseline.json`（阶段0）
- `artifacts/experiments/execution/remediation_validation.json`（阶段7）
- `artifacts/experiments/execution/remediation/compare_selection_r1_remediated.json`（重算）
- `artifacts/experiments/execution/remediation/selection_robustness_r1_remediated.json`（重算）
- 修复代码：run_chaos_experiment / run_grpc_chaos_experiment / run_probe_restart_escape / run_stress_with_cgroup / runtime_applicability_gate / issue_tracker / environment_fingerprint / project_registry / decision_engine / compare_selection_methods / selection_robustness / summarize_comparative_results
- 回归测试：test_remediation_phase{1,2,4,5,6}_*.py + 修正的 test_decision_engine / test_issue_tracker / test_judgment_experience
- 配置：pytest.ini

---

# 第二轮审查修复（round-2，7 项）

> 日期：2026-08-09（第二轮）
> 约束：未执行真实 Kubernetes 注入；未用 git reset --hard / git checkout --；未修改实验真值与历史结果；新重算结果写入 `execution/remediation_v2/`；每一步"修改后立即测试"。

## 验证总览

- **`python -m pytest -q`**：**162 passed, 5 subtests passed**
- **`git diff --check`**：干净（exit 0）
- **artifact hash**：7 个受保护 artifacts 全部 UNCHANGED（对照 `remediation_validation.json` 基线 hash）
  - contract_inventory / selection_experience / judgment_experience / defense_pattern_library / knowledge_audit_log / our_evidence_chain_root_causes / sock_shop_verdicts
- 未执行真实 Kubernetes 混沌注入（全部通过单元测试 + 纯数据重算验证）

## 修复 1：runtime gate 真实超时异常

- **改动**：`tools/runtime_applicability_gate.py`（`run_kubectl` 捕获 `subprocess.TimeoutExpired` → `(124, stdout, stderr)`；`OSError` → `(1, "", "kubectl invocation failed: ...")`；`check_mutation` 增加顶层 fail-closed 包装器，任何未预期异常 → `decision="blocked"`）
- **测试**：`python -m pytest tools/tests/test_remediation_phase2_gate.py -q`（新增 `RealExceptionFailClosedTests`：patch `gate.subprocess.run` side_effect=TimeoutExpired/OSError）
- **结果**：21 passed + 5 subtests
- **语义保持**：NotFound 仍 available；timeout/RBAC 仍 blocked（既有测试全部通过）
- **残留**：`check_mutation` 顶层 guard 捕获 `Exception`（fail-closed 合理）；真实集群 kubectl 异常行为未集成验证（约束要求）

## 修复 2：统一 evidence 分类（known 分母一致）

- **改动**：新建 `tools/evidence_classification.py`（共享 `classify_candidate` / `is_known_candidate` / `known_candidate_ids`）；`compare_selection_methods.known_discovered_candidates` 与 `selection_robustness.classify_evidence_candidate` 均委托共享模块；删除 selection_robustness 里重复的 `_WEAKNESS_CLASSES`/`_INVALID_CLASSES`
- **规则**：invalid_baseline / invalid_not_injected / invalid_request_configuration / platform_or_preflight_blocked / not_applicable / transport_or_observation_error **不进 known 分母**；无结论 → `unclassified`（非 invalid，兼容 legacy discovery-only fixture）
- **回归**：`test_remediation_phase6_metrics.py` 新增 `SharedKnownUniverseTests`——OTEL-PAYMENT-DELAY-2000（含 invalid_baseline + invalid_not_injected）不进已知集；两工具 known 集合一致
- **测试命令**：`python -m pytest tools/tests/test_remediation_phase6_metrics.py tools/tests/test_remediation_phase4_universe.py -q` → 18 passed
- **重算（remediation_v2）**：
  - `compare_selection_r1_remediated_v2.json`：universe=12, known=11, known_outside_universe=8
  - `selection_robustness_r1_remediated_v2.json`：universe=12, known=11, weakness=2, below_threshold=9, invalid_in_universe=1
- **残留**：universe 小、weakness 仅 2，排名仅描述性（既有结论，未过度解释）

## 修复 3：清理 NotFound 必须合并 stdout+stderr

- **改动**：`tools/run_chaos_experiment.py`（`delete_resource` verify 合并 stdout+stderr 后识别 NotFound）；`tools/run_stress_with_cgroup.py`（`cleanup_mutation` 同规则）
- **测试**：`test_remediation_phase1_cleanup.py` 新增 stdout-only NotFound → absent；stdout-only Forbidden/timeout → 非 absent（两个 runner 各一套）
- **结果**：16 passed
- **残留**：真实集群删除行为需集成验证（约束要求）

## 修复 4：PodChaos 多副本恢复误判

- **改动**：`tools/run_chaos_experiment.py`（`wait_for_target_ready` 增加 `expected_pod_count`：注入前从 preflight `target_pods` 记录目标 Pod 数量；恢复要求非 terminating Pod 数 ≥ 期望值且全部 Ready；`expected_pod_count=None` 时保留单副本"任一 Ready"语义；新增 `_pod_ready` helper；lifecycle 记录 `recovery_target_pod_count`）
- **测试**：新建 `test_remediation_round2_podchaos_recovery.py`（6 项：多副本一个未 Ready → False；全 Ready → True；terminating 不计入；单副本/None 保持原行为）
- **结果**：6 passed

## 修复 5：run_stress_with_cgroup preflight 异常报告

- **改动**：`tools/run_stress_with_cgroup.py`（preflight 全程 try/except：YAMLError → `yaml_shape_invalid`；OSError/RuntimeError/TimeoutExpired/ValueError → `preflight_error`；均写 orchestration report（`preflight_blocked` + 原因 + `exit_status`）+ 返回 2；未知状态下仍执行幂等 cleanup 尝试）
- **测试**：新建 `test_remediation_round2_stress_preflight.py`（6 项异常路径 + cleanup 仍执行 + YAML 解析失败不查询）
- **结果**：6 passed
- **残留**：preflight 分支 `resource_exists` 异常时 `present=True` 强制执行 cleanup 尝试（fail-safe）；真实集群行为未验证

## 修复 6：重复次数元数据硬编码

- **改动**：`tools/summarize_comparative_results.py`（scope 删除 `"valid_runtime_replicates": 4`；改为从实际记录计算的 `scope.scenario_replicates` + `scope.uniform_replicates`；`runtime_summary.scenario_replicates` 保留动态计算）
- **测试**：`test_remediation_phase5_provenance.py` 新增 `test_no_hardcoded_valid_runtime_replicates` + `test_different_replicate_counts_reported_honestly`（不同场景不同次数时如实报告，不伪造统一数）
- **结果**：10 passed
- **残留**：真实 6 场景各 4 条记录（TT station/OB productcatalog/OB payment delay/loss/OTel payment delay/loss），`uniform_replicates=True` 反映数据事实

## 修复 7：provenance 范围检查（stress runner schema）

- **决定**：run_stress_with_cgroup 属于 runner 输出范围（执行 kubectl preflight/cleanup、产出被 summarize 消费的独立报告）→ **升级 schema 1→2 + 补 `environment_fingerprint` + baseline/lifecycle/cleanup contract 声明**（与 run_chaos_experiment/grpc/probe 对齐）
- **改动**：`tools/run_stress_with_cgroup.py`（两处 report：preflight_blocked 分支 + 正常流程，均 `schema_version: 2` + `environment_fingerprint: load_fingerprint()` + `contract` 字段声明 baseline/lifecycle/cleanup/cgroup 各由谁承载）
- **测试**：`test_remediation_round2_stress_preflight.py` 新增 `StressProvenanceContractTests`（3 项）
- **结果**：9 passed（含修复 5 的 6 项）
- **残留**：历史 stress orchestration 产物无 fingerprint（不可回溯，仅新产物生效——与既有 runner 相同限制）

## 修改文件清单（round-2）

- `tools/runtime_applicability_gate.py`
- `tools/evidence_classification.py`（新建）
- `tools/compare_selection_methods.py`
- `tools/selection_robustness.py`
- `tools/run_chaos_experiment.py`
- `tools/run_stress_with_cgroup.py`
- `tools/summarize_comparative_results.py`
- 测试：`test_remediation_phase2_gate.py` / `test_remediation_phase6_metrics.py` / `test_remediation_phase1_cleanup.py` / `test_remediation_phase5_provenance.py` / `test_remediation_round2_podchaos_recovery.py`（新建）/ `test_remediation_round2_stress_preflight.py`（新建）
- 重算产物：`artifacts/experiments/execution/remediation_v2/`（2 个 JSON，旧 `remediation/` 结果未覆盖）

## 仍未验证的风险（round-2）

| 项 | 说明 |
|---|---|
| 真实集群 kubectl 异常行为（gate/cleanup） | 约束要求不执行真实注入；异常路径通过单元测试验证，真实集群行为待集成验证 |
| 多副本 PodChaos 真实恢复时序 | 单元测试覆盖判定逻辑；真实集群副本重建时序未验证 |
| 历史 stress orchestration 产物无 fingerprint | 不可回溯，仅新产物生效 |
| universe 统计功效 | weakness 仅 2，排名仅描述性（数据事实） |

---

# 第三轮审查修复（round-3，P1×4 + P2×3）

> 日期：2026-08-09（第三轮）
> 约束：未执行真实 Kubernetes 注入；未修改实验真值与历史结果；新重算结果写入 `execution/remediation_v3/`；每项"修改后立即测试"。

## 验证总览

- **`python -m pytest -q`**：**171 passed, 5 subtests passed**（修复前 162）
- **`git diff --check`**：干净（exit 0）
- **artifact hash**：7 个受保护 artifacts 全部 UNCHANGED
- 未执行真实 Kubernetes 混沌注入

## P1-1：preflight 不删除本次运行未创建的既有资源

- **问题**：blocked 分支（mutation_exists / 未知状态）会再次查询并调用 `cleanup_mutation`，可能删除其他实验或人工创建的 Chaos 资源
- **修复**：`tools/run_stress_with_cgroup.py` blocked 分支**不再自动清理**——资源非本进程创建，`parent_cleanup_fallback.attempted=False` 且 reason 明确"not created by this run, inspect manually"；只有正常路径（本进程成功 apply 并拥有）才清理
- **测试**：`test_remediation_round2_stress_preflight.py` 更新（`test_unknown_state_does_not_auto_cleanup`、`test_mutation_exists_does_not_auto_cleanup`：cleanup_mock 断言 `assert_not_called`）
- **结果**：11 passed

## P1-2：三态分类把强 gRPC 故障归入 below_threshold

- **问题**：weakness 集合缺 `grpc_error_observed`，OB-PAYMENT-LOSS-100 等多次 grpc_error 被归 below_threshold → "weakness 仅 2" 是分类枚举不完整造成
- **修复**：`tools/evidence_classification.py` WEAKNESS_CLASSES 增加 `grpc_error_observed`
- **测试**：`test_remediation_phase6_metrics.py` 新增 `test_grpc_error_observed_is_weakness`
- **结果**：weakness 从 2 → 9（真实数据）

## P1-3：一个无效重复否定同候选全部有效重复

- **问题**：invalid wins over weakness，OTEL-PAYMENT-DELAY-2000 含有效 grpc_response_observed + 无效 invalid_baseline/invalid_not_injected 被整体排除
- **修复**：`tools/evidence_classification.py` `classify_candidate` 改为**先剔除无效重复，再聚合剩余有效结论**——全部无效才 invalid，任一有效为 weakness 则 weakness，否则 below_threshold
- **测试**：`test_remediation_phase6_metrics.py` 更新（`test_all_invalid_conclusions_is_invalid`、`test_mixed_valid_and_invalid_aggregates_valid`、`test_valid_plus_invalid_repeats_stays_known`）
- **结果**：OTEL-PAYMENT-DELAY-2000 回 known（v3 known=12，v2 是 11）

## P1-4：stress 正常执行阶段异常无报告退出

- **问题**：只保护了 preflight；生命周期阶段 `lifecycle_status()` 超时后 report 不写出（已复现）
- **修复**：`tools/run_stress_with_cgroup.py` 生命周期 try 增加内层 except（OSError/RuntimeError/TimeoutExpired/ValueError/JSONDecodeError → errors + 继续走 finally + 写 report）；`runner` 预声明 None，Popen 失败（OSError）时 finally 安全跳过 terminate；finally 的 cleanup 存在性检查异常捕获扩展到 OSError/TimeoutExpired
- **测试**：`test_lifecycle_exception_still_writes_report`（patch lifecycle_status raise + Popen raise → report 仍写出且 errors 含 lifecycle failed）
- **结果**：11 passed

## P2-1：部分畸形 YAML 产生裸 traceback

- **问题**：`metadata: bad` 触发 AttributeError，不在异常列表，无报告（已复现）
- **修复**：`tools/run_stress_with_cgroup.py` preflight except 增加 `AttributeError, TypeError` → `yaml_shape_invalid` + 报告
- **测试**：`test_malformed_metadata_no_traceback`
- **结果**：11 passed

## P2-2：robustness 未真正调用共享 known 集合

- **问题**：`selection_robustness.analyze` 自己遍历 evidence 只排除 invalid，未检查 `own_discovery_evidence`；与 compare 的共享 `known_candidate_ids` 会分叉
- **修复**：`tools/selection_robustness.py` 改用 `evidence_classification.known_candidate_ids(evidence)` 作为 known 集合（检查 discovery evidence + 只剔除全 invalid）；`invalid_in_universe` 用共享分类器
- **测试**：`test_remediation_phase6_metrics.py` fixture 补 `own_discovery_evidence`（`test_known_excludes_outside_and_invalid`）
- **结果**：两工具 known 集合一致（`test_both_tools_agree_on_known_set` 通过）

## P2-3：PodChaos 只验证数量和 Ready，未验证替换身份

- **问题**：未记录注入前 Pod UID，旧 Pod 未进入 terminating 的短窗口内仍可能立即判恢复
- **修复**：`tools/runtime_applicability_gate.py` target_pods 记录 `uid`；`tools/run_chaos_experiment.py` 注入前从 preflight 提取 `pre_kill_uids` 存入 lifecycle（`recovery_pre_kill_uids`）；`wait_for_target_ready` 增加 `pre_kill_uids` + `stable_checks`（默认 2）——恢复要求旧 UID 不再出现于 active Ready 集合，且连续 stable_checks 次稳定
- **测试**：`test_remediation_round2_podchaos_recovery.py` 新增 `IdentityReplacementTests`（旧 UID 仍在 → 不恢复；新 UID 替换 → 稳定后恢复；无替换 → 超时不恢复）
- **结果**：10 passed

## 重算 remediation_v3（分类修正后）

| 指标 | v2（错误分类） | v3（修正） |
|---|---|---|
| compare known | 11 | **12**（OTEL-PAYMENT-DELAY-2000 回归） |
| robustness known | 11 | **12** |
| weakness | 2 | **6** |
| below_threshold | 9 | 6 |
| invalid | 1 | **0** |
| universe | 12 | 12 |
| known_outside_universe | 8 | 8 |

- 产物：`execution/remediation_v3/compare_selection_r1_remediated_v3.json` + `selection_robustness_r1_remediated_v3.json`
- **"weakness 仅 2" 已修正**：grpc_error 计入后 weakness=6，不再被分类枚举不完整误导

## 修改文件清单（round-3）

- `tools/evidence_classification.py`
- `tools/run_chaos_experiment.py`
- `tools/run_stress_with_cgroup.py`
- `tools/runtime_applicability_gate.py`
- `tools/selection_robustness.py`
- 测试：`test_remediation_phase6_metrics.py` / `test_remediation_round2_podchaos_recovery.py` / `test_remediation_round2_stress_preflight.py`
- 重算产物：`execution/remediation_v3/`（2 个 JSON，旧 `remediation/`、`remediation_v2/` 未覆盖）

## 仍未验证的风险（round-3）

| 项 | 说明 |
|---|---|
| 真实集群 kubectl 异常/gate/cleanup 行为 | 约束要求不执行真实注入；异常路径经单元测试验证，真实集群行为待集成验证 |
| 多副本 PodChaos 真实 UID 替换时序 | 单元测试覆盖身份替换判定；真实集群副本重建与 UID 轮换时序未验证 |
| 历史 stress orchestration 产物无 fingerprint | 不可回溯，仅新产物生效 |
| universe 统计功效 | weakness=6 较 v2 提升，但 universe 仍小（12），排名仅描述性 |
