# Registry Policy Signal Integration Design

## Goal

将经过质量校验的 runtime hypothesis priority 作为 policy 的受限输入，并保持 legacy、shadow、guarded 的渐进上线和现有 live 安全边界。

## Current Gap

`project_portrait.json`、`hypothesis_registry.json` 和 `registry_policy_shadow.json` 已能离线生成，但 `run_live_batch` 的 `PolicyController` 仍只消费候选池、policy state 和普通 policy context。registry 目前不会影响候选优先级。

## Design

新增纯确定性 registry signal adapter：

1. 读取 registry quality payload 和 hypothesis registry；
2. 仅接受 `claim_scope=advisory`、quality `passed`、`kind=runtime`、`execution_eligible=true` 且 candidate ID 存在于冻结 candidate pool 的条目；
3. 生成 candidate ID 到 bounded priority bonus 的映射和 registry input hash；
4. 将映射作为 policy context 的只读字段传给现有评分函数；
5. 不扩大 candidate pool，不允许静态假设进入执行列表。

bonus 必须有固定上限并确定性计算，不能覆盖 policy state 的 runtime posterior，也不能让低价值候选绕过 stop policy。相同输入必须产生相同映射和排序。

## Mode Semantics

- `legacy`：不读取 registry signal，选择和执行行为保持现状。
- `shadow`：计算并记录 registry-policy 选择，与 legacy 选择并列保存；实际执行仍使用 legacy candidate。
- `guarded`/`default`：只有 registry quality 通过、candidate pool/hash 完全匹配、所有既有 preflight/applicability/Oracle/recovery/cleanup gate 通过时，才允许执行 registry-policy 选中的 runtime candidate。

任何 registry 缺失、格式错误、质量失败、hash 不匹配、未知 candidate 或 signal 越界，都 fail-closed 回退 legacy，并在 decision ledger 中记录 `registry_signal_fallback` 原因。

## Artifacts

批次输出新增：

- `registry-policy-input.json`：输入 hash、允许的 runtime IDs、bounded priority map、质量状态；
- `registry-policy-decisions.jsonl`：每轮 legacy selection、registry selection、实际 execution selection、fallback reason 和 stop decision。

现有 `policy-decisions.jsonl`、`policy-feedback.jsonl`、`batch_manifest.json` 和 child run 目录继续保留。registry signal 不写正式知识库或全局 policy state。

## Verification

- 单元测试覆盖 signal 过滤、上限、未知 ID/hash/质量失败回退、legacy/shadow/guarded 模式差异和确定性；
- 离线 fake-executor shadow/guarded 回放确认 shadow 不改变实际执行，guarded 只执行 allow-listed runtime candidate；
- Sock Shop 和 Online Boutique 先做离线 shadow，再做一轮显式批准的 guarded 单候选 canary；
- 所有已有 policy、batch、RCA、cleanup 测试保持通过。

## Boundary

本阶段只让已验证的 runtime priority 进入 policy。它不把 architecture/configuration/dependency/defense 假设直接当作漏洞，也不自动修改默认策略；guarded 成为默认仍需独立验收。
