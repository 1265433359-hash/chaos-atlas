# 项目实验总结与归档计划

目标：在继续新增实验前，建立四项目、三方法轴、统一台账和证据等级的可追溯归档；不覆盖历史结果，不把 pilot 写成 superiority 证据。

## 阶段

| 阶段 | 内容 | 状态 | 交付物 | 验收标准 |
|---|---|---|---|---|
| A0 | 冻结当前仓库和结果状态 | completed | git 状态、commit、artifact hash、未提交变更清单 | 历史产物只读；用户已有修改不回退 |
| A1 | 建立项目注册表 | in_progress | `project_registry_archive.json` | 明确 TT、OB、OTEL、Sock Shop 的版本、namespace、镜像、测量轨道、已执行/未执行项目 |
| A2 | 建立方法注册表 | pending | `method_registry_archive.json` | 区分 M0/M1/M3/M4/A0-A4/decision_engine/Ours-full/CE official/CE AnalysisAgent；记录输入信息层和故障域 |
| A3 | 合并实验台账 | pending | `run_ledger_master.json`、`run_ledger_master.md` | 将既有 83 次与 r2 24 次分区合并；区分独立注入、确认、派生分类、预测和无效尝试 |
| A4 | 建立证据等级和结论矩阵 | pending | `claim_evidence_matrix.md` | 每条结论标记 confirmed / pilot / supplementary / blocked / self-referential / future work |
| A5 | 建立候选池和方法×项目矩阵 | pending | `project_method_matrix.csv`、`candidate_pool_registry.json` | 记录候选是否已执行、是否 protected、是否有真实链路、是否可用于公平 head-to-head |
| A6 | 整理报告入口 | pending | `ARCHIVE_INDEX.md`、更新 `unified_experiments_summary.md` 的状态说明 | 只有一个权威入口；旧报告保留并标记 historical/superseded，不删除 |
| A7 | 生成最终汇报表 | pending | 项目总表、方法总表、CE 对照表、限制清单 | 不使用任意总分；选择、测量、证据三条轴分开呈现 |

## 归档原则

- 四个项目都可以写入“研究范围”；只有实际同协议执行的项目才可以写入对应 head-to-head 结果。
- `Ours-full`、`decision_engine`、`ChaosEater-adapter`、`ChaosEater official` 必须分开注册，不能混称。
- `83` 是 r2 前的 lifecycle-complete 台账；r2 的 `24` 次尝试必须先记录 invalid、重试、环境阻断和 runner 版本，再合并总览。
- 原始 JSON、YAML、LLM 原始响应和日志只追加不覆盖；修正结论写新版本。
- “选择器无显著差异”“测量层有增量”“证据链更适合审计”分别归档，不合成一个总分。

## 禁止事项

- 不删除或重写历史实验真值。
- 不把未部署的 OTEL/TT r2 候选从分母删除后继续称为等预算 `U@8`。
- 不把 CE AnalysisAgent 使用 Ours 生成的输入当作独立外部真值。
- 不在归档完成前继续扩大实验规模。
