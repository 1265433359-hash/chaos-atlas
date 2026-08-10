# DeepSeek 任务：冻结 held-out 对比协议并完成 Hotel 预检

请在 `C:\APP\project\chaos` 内直接实施本任务。当前只允许完成协议冻结、Hotel 可行性预检和静态知识快照构造；不要运行正式实验。

## 绝对禁止

- 不启动 Kubernetes、Chaos Mesh、port-forward、HTTPChaos 或真实注入；
- 不运行 pilot，不运行 CE head-to-head，不执行任何新 fault injection；
- 不下载镜像、不访问外部网络、不修改环境规则；
- 不把实验结果写回 Hotel snapshot；
- 不修改 TT/OB/OTEL/Sock 历史真值；
- 不使用 `git reset`、`checkout`、`clean`；
- 不把空 contract 称为 `Ours-full`。

## 目标

为第一个真正 held-out 项目 Hotel 建立可审计的 confirmatory protocol，区分：

1. `Ours-full-pre`：Hotel 源码/manifest 静态 intake 后冻结项目特定 contract/availability + 通用 SE/DP/JE；
2. `Ours-generic`：空项目特定 contract，仅使用通用 SE/DP/JE 的消融组；
3. `ChaosEater-official`：官方完整 pipeline；
4. `ChaosEater-adapter`：项目已有 adapter，必须与 official 分开；
5. `Random`：同预算随机基线。

## P0：协议文件

新增：

```text
artifacts/experiments/heldout/heldout_protocol_v1.md (superseded by heldout_protocol_v1_1.md)
artifacts/experiments/heldout/heldout_protocol_v1.json (superseded by heldout_protocol_v1_1.json)
```

协议必须在任何 Hotel 实验前冻结，并明确：

- 主比较线：Equal-information 和 Realistic end-to-end；
- 方法定义、输入信息层、候选预算 `K`、随机种子和 runner；
- 主指标：`Weakness@K`；
- 辅助指标：`Protected-waste@K`、漏检估计、证据生命周期完整率、RCA 锚定率、单位有效发现成本；
- 不允许将不同量纲指标事后等权合成总分；
- CE official bring-up 预算、blocked 规则和 failure policy；
- Hotel 闸门：bring-up 2h、稳定观测 30min、连续两次 baseline 失败即 blocked、禁止改规则过闸门；
- pilot 规模 24-32 候选；正式确认规模 48-64 候选；
- pilot 通过条件和终止条件；
- 选中候选执行、未选 audit set、oracle pass 的关系；
- 结果不可回填 selection snapshot；
- 单 Hotel 只能声称“在 Hotel 协议下”，至少三个 held-out 项目才允许写跨项目结论；
- 预注册胜出条件：至少两个 held-out 项目上 Ours 不降低 Weakness@K，并在预先指定的证据或单位成本终点上优于 CE；不能把 environment_blocked 当作算法胜利。

统计规则必须写明：候选嵌套在项目内，置信区间按项目聚类；不能把同一项目的所有候选当作独立样本。

## P1：Hotel 只读预检

先搜索仓库已有的 Hotel/Hotel Reservation 项目、README、manifest、镜像引用、业务工作流和测试入口。若项目不存在或无法确认来源，直接报告 `environment_blocked`，不得下载或部署。

新增：

```text
artifacts/experiments/heldout/hotel_intake_report.md
artifacts/experiments/heldout/hotel_intake_report.json
```

报告至少包括：

- project/repository/version/commit（未知写 `unknown`）；
- 服务数、工作流数、可观测入口；
- 可用 manifest、源码和镜像的路径；
- 可构造的 contract/availability 事实；
- 不能确认的字段和原因；
- 是否具备至少 30 个中性候选的生成条件；
- 可覆盖的 fault families；
- 是否满足 2h/30min/2 baseline 闸门（此阶段只能写 `not_run`，不能伪造通过）；
- `go_no_go`：只能是 `ready_for_snapshot`、`blocked` 或 `needs_human_decision`。

注意：此阶段禁止运行集群，因此 bring-up 和稳定性闸门必须保持 `not_run`，不能填 `passed`。

## P2：静态知识快照

只有在 Hotel intake 找到可靠源码/manifest 后，才新增：

```text
artifacts/experiments/heldout/hotel_knowledge_snapshot_pre.json
```

快照必须使用现有 `validate_knowledge_snapshot()` 兼容 schema，并包含：

```text
schema_version
provenance.kind
provenance.source_commit
provenance.provenance_completeness
provenance.source_files
provenance.sha256
contract.contracts
contract.availability
contract.candidate_map
selection_experience
defense_pattern_library
judgment_experience
source_provenance 五字段
```

规则：

- 源码/manifest 静态分析可以在实验前写入 contract/availability；
- 实验结果、CE 输出、人工 runtime verdict 不得写入；
- 无项目特定 contract 时必须显式标记 `Ours-generic`，不能伪装成 Ours-full；
- 当前工作区的 posthoc 知识不能自动冒充 Hotel pre snapshot；
- 每个源文件记录实际路径和 SHA-256；不可访问来源标记 `unavailable`；
- 如果五源无法证明为 experiment-pre，snapshot 状态必须是 `blocked`。

## 测试和验证

只运行本地静态检查和单元测试：

```powershell
python -m json.tool artifacts/experiments/heldout/heldout_protocol_v1.json (superseded by heldout_protocol_v1_1.json) > $null
python -m json.tool artifacts/experiments/heldout/hotel_intake_report.json > $null
python -m json.tool artifacts/experiments/heldout/hotel_knowledge_snapshot_pre.json > $null
pytest -q tools/tests/test_decision_engine.py tools/tests/test_sock_frozen_knowledge_rerun.py
git diff --check
```

如果某个 JSON 因 Hotel 不存在而不应创建，必须在回报中明确说明，不要生成空壳文件。

## 回报格式

请返回：

1. 修改/新增文件完整清单；
2. 协议中的方法、预算、主指标、辅助指标和胜出条件；
3. Hotel intake 的证据路径和 `go_no_go`；
4. Ours-full-pre 与 Ours-generic 的区别；
5. snapshot provenance、SHA 和 unavailable 来源；
6. 运行过的只读命令及结果；
7. 未完成项和原因；
8. commit ID。

不要返回“已完成”这种无证据结论。完成后停止，等待主代理审核；未经审核不得进入 pilot 或正式实验。
