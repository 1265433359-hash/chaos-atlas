# ChaosAtlas 离线统计器

入口：`tools/analyze_chaosatlas_statistics.py`

默认读取 `artifacts/experiments/chaosatlas_10_projects` 下已经冻结的
`open_discovery_results`、`runtime_results` 和 `cost_token_ledger.json`，输出：

- `analysis_outputs/chaosatlas_statistics/statistics.json`
- `analysis_outputs/chaosatlas_statistics/statistics.md`

也可以通过 `--input` 提供规范化 JSON 或 JSONL。单条记录至少应包含
`project_id`、`arm`、`seed`；计数型字段可使用
`submitted`、`valid_outputs`、`generated`、`compiler_accepted`、`executable`、
`confirmed_weaknesses`、`protected_targets`、`method_invalid`、
`environment_blocked`、`recovery_successes`、`recovery_attempts`。复杂数据可把
指标放在 `metrics` 下，或者把每个 arm 放在 `arms` 对象中。

统计规则固定为：每个项目的 3 个 seed 先求项目内均值，项目是推断单位；LLM
调用、候选 hypothesis 和 runtime repetition 不作为独立项目样本；KB/noKB
使用同一项目的配对差值 `mean(KB) - mean(noKB)`，最后仅对可计算的项目差值
给出均值、中位数、标准差、最小值和最大值。缺失分母或证据输出 `null`，不会
把 environment-blocked、missing 或 method-invalid 隐式改成 0。

示例：

```powershell
python tools/analyze_chaosatlas_statistics.py
python tools/analyze_chaosatlas_statistics.py --input path/to/records.jsonl --expected-projects 10
```
