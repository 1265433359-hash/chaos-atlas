# DeepSeek 第二轮任务：修正实验归档的一致性问题

你是本项目的归档维护工程师。请在 `C:\APP\project\chaos` 内修正归档提交 `6acb7c6` 中发现的口径、索引和验证问题。

## 目标

让归档满足以下条件：

1. 四个项目都可追溯，但 Sock Shop 的异构证据不伪装成普通 runner run。
2. 主台账中的 `method_id`、项目 ID、候选 ID 全部可以交叉引用。
3. 候选池中的每个候选都有明确的 ground-truth 状态和故障族。
4. 所有数字口径自洽，尤其是 `83/91/107` 和 r2 的 `8/9/7` 分解。
5. r2 的结论不超过其样本和实验范围支持的强度。
6. 只做归档和文档修正，不重跑实验，不改历史真值。

## 必须修正的问题

### 1. 补充 Sock Shop 独立轨道台账（P1）

新增：

- `artifacts/experiments/archive/sock_track_ledger.json`
- `artifacts/experiments/archive/sock_track_ledger.md`

从现有 Sock Shop 产物中整理并明确列出：

- 8 条契约/真实链路候选或边判定证据；
- 5 个 availability kill 文件；
- 每条记录的 `project_id`、`method_id`、`status`、`source_file`、`measurement_track`、`evidence_type`；
- 哪些是候选/边判定、哪些是服务 kill、哪些不是普通注入 run。

不要把这 13 条异构证据硬塞进 `run_ledger_master` 的普通 run 数字。更新 `ARCHIVE_INDEX.md` 和相关总结，明确区分：

```text
普通 run records: 107（TT/OB/OTEL 历史 + OB r2）
Sock Shop independent track evidence: 单独统计，不并入 107
```

若原始文件不足以确认某字段，写 `unknown`，不得猜测。

### 2. 闭合 method ID 外键（P1）

检查 `artifacts/experiments/archive/run_ledger_master.json` 中所有 `method_id`。当前至少出现：

- `our_evidence_chain`
- `orchestration_track`
- `r2_execute_one`

在 `method_registry_archive.json` 中为这些 ID 增加正式记录，或增加明确的 `aliases`/`canonical_method_id` 映射。不得只在 Markdown 里解释而让 JSON 外键悬空。

同时保证：

```text
每个 run.method_id 能解析到 method_registry.method_id 或其 alias
每个 method 的 measurement_track、runner、evidence_output 可追溯
ChaosEater-adapter 与 ChaosEater-official 必须保持独立
```

### 3. 补全候选池 ground truth 并修正故障族解析（P1）

为 `candidate_pool_registry.json` 的全部 54 个候选补齐：

- `ground_truth_status`：使用已有证据，只能填 `confirmed_weakness`、`confirmed_non_weakness`、`unknown` 或项目中已有等价枚举；
- `exclusion_reason`：对未执行/环境阻塞候选给出可追溯原因。

修正 `tools/build_candidate_registry.py` 的故障族解析。禁止使用：

```python
cid.split("-")[-1]
```

因为它会把 `OB-CART-DELAY-2000` 解析成 `2000`。应显式识别 `delay`、`loss`、`kill`、`cpu_stress` 等故障族；无法判断时写 `unknown`，并保留原始 candidate ID。

补充或更新针对带数值后缀 candidate ID 的单元测试。

### 4. 修正 run ledger 数字口径（P1）

修正 `run_ledger_master.md`、`unified_experiments_summary.md`、`overall_project_method_comparison.md` 和相关索引中的表述。

必须统一为：

```text
历史 lifecycle-complete runs: 83
r2 独立首跑: 8
r2 确认运行: 9
r2 无效基线: 7
总 run records: 107 = 83 + 24
独立注入总数: 91 = 83 + 8
```

不要写成“83 + 17 = 91”或把 17 个有效 r2 观测误称为独立注入。若保留“r2 有效观测 17”，必须明确它是 `8 首跑 + 9 确认` 的观测分类，不是独立数。

### 5. 修正实验模块数量（P2）

`unified_experiments_summary.md` 当前标题仍写“实验地图（7轮）”，但正文列出 1 到 12。改成准确的“12 个实验模块”或“多轮实验模块地图”，不要重新解释历史实验。

### 6. 降低 r2 结论强度（P2）

在 `claim_evidence_matrix.md`、`r2_head_to_head.md` 和总总结中，将 `U@8 = 6 vs 6 vs 5` 定位为 OB 单项目 pilot/blocked evidence：

- 说明没有正式统计显著性检验；
- 说明 8 个候选均已观察到 weakness，存在 ceiling/saturation effect；
- 说明样本量和候选池不支持选择器 superiority 或跨项目泛化；
- 推荐结论文字：`当前样本未显示明确差异，统计功效不足`。

不得写成三方法全面优越、已超过 ChaosEater 或跨项目有效。

### 7. 补全提交文件清单并修复 whitespace（P2）

审核提交 `6acb7c6` 的完整文件清单。回报中不得漏列：

- `tools/run_stress_with_cgroup.py`
- `tools/tests/test_remediation_round2_stress_preflight.py`

对本轮修改执行：

```powershell
git diff --check 6acb7c6^ 6acb7c6
```

修复 `artifacts/experiments/overall_project_method_comparison.md` 文件末尾的多余空行，直到命令返回成功且无 whitespace error。不要修改无关文件。

## 禁止事项

- 不运行 Kubernetes、Chaos Mesh、port-forward 或真实注入；
- 不下载镜像、不改环境、不访问外部网络；
- 不重跑任何历史实验或 r2；
- 不修改历史 JSON/YAML、原始日志、原始 LLM 响应和已冻结真值；
- 不删除候选，不把 environment_blocked 候选从注册表中抹掉；
- 不使用 `git reset`、`checkout`、`clean` 等破坏性命令。

## 只读验收

完成后运行并保存结果：

1. 归档 JSON 全部可解析；
2. 54 个 `candidate_id` 唯一；
3. 每条普通 run 有 `project_id`、`method_id`、`status`、`source_file`；
4. 每个普通 run 的 `method_id` 可解析到 method registry 或 alias；
5. 每个候选都有 `ground_truth_status`；
6. `83 + 24 = 107`、`83 + 8 = 91` 的口径检查通过；
7. Sock Shop 记录只出现在独立轨道台账或明确标注的证据表中；
8. `git diff --check 6acb7c6^ 6acb7c6` 返回 0；
9. 运行已有定向测试，报告通过数和失败数。

## 回报格式

请按以下顺序回报：

1. 修改/新增文件完整清单；
2. 每个问题的修正证据；
3. 普通台账与 Sock Shop 独立轨道的最终数字；
4. 外键、候选 ground truth、数字口径和 whitespace 验证结果；
5. 测试命令及结果；
6. 仍未能证明的科学结论和原因；
7. 新 commit ID。

只报告实际执行和验证过的内容，不要以“理论上完成”代替证据。
