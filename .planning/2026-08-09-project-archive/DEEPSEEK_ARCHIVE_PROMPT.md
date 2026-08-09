# DeepSeek 执行提示词：项目实验总结与归档

你是本项目的归档工程师。请在 `C:\APP\project\chaos` 内完成“实验资产归档和总总结”，不要新增实验，不要修改历史实验真值。

## 总目标

建立四项目、三方法轴、统一实验台账、证据等级和报告入口，使项目可以被审计、复现和写入论文。

四个项目是：

- Train Ticket
- Online Boutique
- OpenTelemetry Demo
- Sock Shop

三条方法轴必须分开：

1. 选择轴：M0、M1、M3/M4、A0-A4、decision engine、Ours-full、ChaosEater adapter、ChaosEater official。
2. 测量轴：direct、real-chain、availability。
3. 证据轴：baseline/injection/recovery/cleanup、分类、RCA、知识回流。

## 执行阶段

### A1：项目注册表

创建：`artifacts/experiments/archive/project_registry_archive.json`

每个项目至少记录：

- project_id
- display_name
- repository/version/commit（未知就写 `unknown`，禁止猜测）
- namespace
- image/deployment availability
- tested_workflows
- fault_families
- measurement_tracks
- executed_candidates
- not_executed_candidates
- held_out_status
- evidence_files

### A2：方法注册表

创建：`artifacts/experiments/archive/method_registry_archive.json`

每个方法至少记录：

- method_id
- exact_definition
- input_information_tier
- model/prompt/seed（适用时）
- candidate_budget
- supported_fault_domain
- measurement_track
- runtime_runner
- evidence_output
- projects_used
- fair_head_to_head_status
- known_limitations

必须把 `ChaosEater-adapter` 与 `ChaosEater official` 分开，不能把通用 LLM ranker 直接称作官方 ChaosEater。

### A3：主实验台账

创建：

- `artifacts/experiments/archive/run_ledger_master.json`
- `artifacts/experiments/archive/run_ledger_master.md`

合并来源：

- 既有 `run_ledger.json` 的 83 次 lifecycle-complete 记录
- r2 `r2_runs/*.json` 的 24 次尝试

每一条记录必须区分：

- independent_injection
- confirmation_run
- invalid_baseline
- invalid_not_injected
- cleanup_failed
- environment_blocked
- derived_classification
- prediction/ranking
- summary/evaluation

严禁把派生 JSON 当成独立实验。r2 的 7/24 基线无效尝试必须显式记录。

### A4：候选池注册表

创建：`artifacts/experiments/archive/candidate_pool_registry.json`

记录每个候选：

- candidate_id
- project_id
- target/edge
- fault
- protected_status
- executed_status
- ground_truth_status
- source_registry
- usable_for_head_to_head
- exclusion_reason

OTEL/TT 在 r2 中未部署的候选必须标记 `environment_blocked/not_executed`，不能简单删除。

### A5：结论证据矩阵

创建：`artifacts/experiments/archive/claim_evidence_matrix.md`

每条重要结论使用以下字段：

| Claim | Evidence | Scope | Status | Limitation |
|---|---|---|---|---|

状态只能使用：

- `confirmed`
- `pilot`
- `supplementary`
- `blocked`
- `self_referential`
- `future_work`

必须单独列出：

- 选择器未被统计证明总体优越
- 真实业务链路能看到 direct 测量看不到的代码级防御
- Ours 的证据链/RCA/知识资产化增量
- ChaosEater 官方部署可用性发现
- CE AnalysisAgent 自证循环限制
- r2 不是完整四项目 head-to-head

### A6：归档总入口

创建：`artifacts/experiments/archive/ARCHIVE_INDEX.md`

入口必须链接到：

- 项目注册表
- 方法注册表
- 主实验台账
- 候选池注册表
- 结论证据矩阵
- `overall_project_method_comparison.md`
- 原始实验报告目录
- r2 报告及其限制

对旧报告只添加状态说明，不删除、不覆盖原始 JSON/YAML/日志。

### A7：更新综合总结

只在 A1-A6 完成后，更新：

`artifacts/experiments/overall_project_method_comparison.md`

和

`artifacts/experiments/unified_experiments_summary.md`

更新时必须修正：

- 项目总数为四个
- r2 实际只执行 Online Boutique
- 既有 83 次与 r2 24 次分开计数
- “floor effect”改为准确的 `ceiling/saturation effect`
- 不把 `6 vs 6 vs 5`写成全面 superiority
- 不把 ChaosEater-adapter 写成 ChaosEater official

## 禁止事项

1. 不运行 Kubernetes、Chaos Mesh、port-forward 或真实注入。
2. 不下载镜像、不改环境、不重跑 r2。
3. 不修改任何历史实验真值、原始运行 JSON、YAML、LLM 原始响应。
4. 不删除用户已有修改，不使用 reset/checkout/clean。
5. 不猜测缺失的 commit、版本、镜像或真值；缺失写 `unknown`。
6. 不使用一个综合加权总分替代三条方法轴。
7. 不把未部署候选从记录中删除。

## 验收要求

完成后执行只读检查：

- JSON 全部可解析
- 所有 candidate_id 在候选池中唯一
- 所有 run 记录有 `project_id`、`method_id`、`status`、`source_file`
- 83 与 24 的来源和状态可追溯
- 派生文件没有计入独立实验数
- 四项目、方法轴、测量轴在所有总表中口径一致
- `git diff --check` 通过
- 不产生新的集群或外部网络副作用

## 最终回报格式

请返回：

1. 修改/新增文件清单
2. 每个阶段完成状态
3. 独立实验总数及分项口径
4. 四项目 × 方法矩阵摘要
5. 仍然无法证明的结论
6. 运行过的只读验证命令及结果
7. 未完成项和原因

不要只回复“完成”，必须给出文件路径和统计数字。
