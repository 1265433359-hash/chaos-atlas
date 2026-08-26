# Policy Controller Integration Design

## Goal

接入现有候选生成、价值评估和停止策略，使 ChaosAtlas 在批处理主编排器中按“选择一轮、执行一次、确定性反馈、更新状态、再决定”的方式运行，同时保留 legacy、observe、shadow 和 guarded 的渐进式上线模式。

## Non-goals

- 不修改现有候选评分、后验更新或停止算法。
- 不把 `run_closed_loop` 拆成多次注入；它仍然是单次实验执行单元。
- 不在本次把 guarded 设为 CLI 默认模式。

## Contract

候选池在 batch 开始时冻结。policy controller 每轮只返回一个候选或停止原因，并产出可审计 decision artifact。child run 完成后由确定性 adapter 从返回值和 `finding_report.json`、`rca_report.json`、`cleanup_report.json` 投影出 policy feedback。

只有状态为 `live_completed`、cleanup 为 `verified`、分类属于 `confirmed_weakness` 或 `protected` 且证据完整的运行，才允许作为有效 weakness/defense 后验反馈。`environment_blocked` 和 `method_invalid` 只进入审计记录，不更新 weakness/protected 后验；cleanup 未验证的运行也不得更新策略。

legacy 模式保持现有固定候选前缀执行。observe/shadow 计算新策略并写出差异，但不改变执行集合。guarded/default 使用逐轮策略选择。停止判定发生在下一次注入前，停止后不调用 executor。

## Artifacts

- `policy-selection.json`: 首轮兼容 artifact，记录模式、legacy 对照和 fallback。
- `policy-decisions.jsonl`: append-only 每轮 decision/stop 记录。
- `policy-feedback.jsonl`: append-only 每轮确定性 feedback 与是否可更新标记。
- `policy-state.json`: 每次有效反馈后原子更新。
- `batch_summary.json`: 增加 stop reason、轮次和有效反馈计数。

## Safety

child output 目录按 candidate id 隔离；已完成且 cleanup verified 的 child 在 resume 时不重复执行。单次 live 路径仍拒绝非 legacy policy 参数，避免与 batch 重复选择。策略异常在 observe/shadow/guarded 下沿用现有 fail-closed fallback，并写入 decision ledger。
