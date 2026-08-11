# Archive and Cleanup Record

更新日期：2026-08-11

本次整理采用“证据保留、工作草稿清理”的原则。实验真值和可复现输入不删除；
只清理明确属于代理操作指令或测试临时目录的内容。

## 保留范围

- `raw_yaml/`：原始 YAML、路径和哈希。
- `artifacts/`：项目静态映射、运行时证据、JSON/CSV 台账、知识卡、报告和归档索引。
- `artifacts/experiments/archive/`：跨项目主台账、候选池、方法注册表和 claim-evidence matrix。
- `artifacts/experiments/knowledge_ablation_prompts/`：正式消融实验实际使用的冻结 prompt，属于实验输入，不是无关草稿。
- `.planning/*/task_plan.md`、`findings.md`、`progress.md`：历史工作过程和决策记录。
- `reporting/`、`governance/`、`tools/` 及测试：论文材料、治理规则和可复用实现。

## 本次清理

以下 9 个文件是临时生成的 DeepSeek 操作提示词，不属于实验结果、协议输入或知识资产，已删除：

- `.planning/2026-08-09-project-archive/DEEPSEEK_ARCHIVE_CORRECTION_PROMPT.md`
- `.planning/2026-08-09-project-archive/DEEPSEEK_ARCHIVE_PROMPT.md`
- `.planning/2026-08-09-project-archive/DEEPSEEK_FROZEN_REPLAY_FINAL_AUDIT_PROMPT.md`
- `.planning/2026-08-09-project-archive/DEEPSEEK_FROZEN_REPLAY_FIX_PROMPT.md`
- `.planning/heldout_head_to_head_2026-08-10/DEEPSEEK_HELDOUT_FULL_EXECUTION_PLAN_PROMPT.md`
- `.planning/heldout_head_to_head_2026-08-10/DEEPSEEK_HELDOUT_PROTOCOL_INTAKE_PROMPT.md`
- `.planning/heldout_head_to_head_2026-08-10/DEEPSEEK_P1_P2_HOTEL_INTAKE_PROMPT.md`
- `.planning/heldout_head_to_head_2026-08-10/DEEPSEEK_PROTOCOL_V1_1_CORRECTION_PROMPT.md`
- `.planning/heldout_head_to_head_2026-08-10/DEEPSEEK_STAGE_B_PROJECT_SELECTION_PROMPT.md`

`.pytest-tmp-final-all/` 是 pytest 生成的临时目录，也已删除。`.pytest_cache/`
属于忽略目录，但当前 Windows 权限不允许读取，因此没有强制处理。

## 归档入口

- 总归档索引：`artifacts/experiments/archive/ARCHIVE_INDEX.md`
- 文件归档规则：`docs/ARCHIVE_MAP.md`
- 项目总览：`docs/PROJECT_SUMMARY.md`
- GitHub 上传前清单：`docs/GITHUB_PRIVATE_HANDOFF.md`

本次清理没有删除任何实验数据，没有配置 Git remote，也没有执行 GitHub 上传。
