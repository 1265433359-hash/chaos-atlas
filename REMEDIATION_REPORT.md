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
