# DeepSeek 任务：修正 held-out protocol v1，生成 v1.1

请在 `C:\APP\project\chaos` 内直接实施协议修正。当前 Hotel intake 已确认 `go_no_go=blocked`，本任务只修改协议定义和验证文档，不取得 Hotel 项目、不下载、不部署、不运行任何实验。

## 禁止事项

- 不启动 Kubernetes、Chaos Mesh、port-forward 或真实注入；
- 不运行 pilot 或正式 head-to-head；
- 不下载 Hotel 仓库、不修改环境；
- 不修改 TT/OB/OTEL/Sock 历史真值；
- 不把 Hotel intake 从 `blocked` 改成 `ready`；
- 不使用 `git reset`、`checkout`、`clean`。

## 目标

保留 v1 原文件作为历史冻结版本，新增并冻结：

```text
artifacts/experiments/heldout/heldout_protocol_v1_1.md
artifacts/experiments/heldout/heldout_protocol_v1_1.json
```

在 v1.1 中明确标记：

```text
supersedes: heldout_protocol_v1
amendment_reason: budget/statistics/replicate semantics correction
```

不能直接覆盖 v1。

## 必须修正的问题

### 1. 统一 CE official bring-up 预算

Markdown 中的 `X 小时`必须删除，统一固定为：

```text
CE official bring-up budget = 4h
```

同时保留 Hotel 自身的 bring-up gate：2h bring-up、30min 稳定观测、连续两次 baseline 失败即 blocked。明确这是两个不同闸门：CE 预算和 Hotel 环境闸门。

### 2. 修正统计结论层级

必须写清楚：

- 单个 Hotel：只能报告描述性结果，不能声称 superiority；
- 两个项目：只能作为最小复现，不支持强跨项目显著性；
- 至少三个 held-out 项目：才允许跨项目结论；
- CI 应对“项目级配对差值”做 bootstrap 或 permutation，而不是要求每个项目自己的 CI 都不跨 0；
- 候选嵌套于项目，不能把同一项目候选当作独立样本。

删除或改写旧的：

```text
差值 bootstrap 95% CI 不跨 0（单 held-out 项目上）
```

改成：

```text
正式跨项目结论：至少 3 个 held-out 项目的项目级配对差值，聚类 bootstrap/permutation 95% CI 不跨 0。
```

### 3. 固定 replicate、seed 和 K 的统计单位

协议必须明确：

```text
一个 method-seed = 一次独立候选选择，预算固定 K
每个选中候选最多 2 次确认运行
Weakness@K 按候选计数，不按重复运行次数计数
```

并分别规定：

- decision engine：确定性选择，1 个 selection replicate，确认运行规则固定；
- LLM 方法：3 个预注册 seed，每个 seed 独立消耗 K；
- Random：固定明确数量，例如 20 个 seed，每个 seed 独立消耗 K；
- 报告 seed-level 分布、均值/中位数和预注册聚合规则；
- 不得把 LLM 的 3 个 seed 与 Ours 的一次确定性选择直接当作同一个样本数。

### 4. 明确候选池规模的单位

不要只写 `48-64 candidates`。必须明确：

```text
pilot: 每个 held-out 项目 24-32 候选
formal: 每个 held-out 项目 48-64 候选
```

如果实际想用总池规模，则必须写出每个项目的最小候选数和分层比例。候选池必须包含 protected、unprotected、unknown，并覆盖 delay/loss/kill（项目能力不具备时写明 unavailable）。

### 5. 修正 CE blocked 的分母规则

必须改成：

```text
CE official 在某项目无法完成 bring-up 或稳态建立
=> 该项目的 CE 对比线标记 environment_blocked
=> 不从剩余候选中删除后继续宣称 Ours 胜出
=> 不把 blocked 当作算法 superiority
```

不要只写“CE blocked 的候选不进主指标分母”，这会造成选择性分母偏差。

### 6. 澄清 Equal-information 与 Ours-generic

必须写清楚：

- Equal-information 线中，所有方法获得同一候选元数据；
- Ours-generic 是消融组，即使收到候选元数据，也禁用项目特定 contract/availability；
- Ours-full-pre 才使用 Hotel 静态 intake 后冻结的项目 contract/availability；
- Realistic end-to-end 线允许 Ours 和 CE 使用各自标准输入，但不得把该线结果写成纯选择算法 superiority。

## 交付物

新增 v1.1 的 Markdown 和 JSON，并在文件开头注明 v1 被 superseded。同步更新 heldout 计划中的协议版本引用，但不要修改 Hotel intake 的 `blocked` 结论。

## 只读验收

```powershell
python -m json.tool artifacts/experiments/heldout/heldout_protocol_v1_1.json > $null
rg -n "X 小时|单 held-out 项目上|formal_candidates.*48-64|environment_blocked" artifacts/experiments/heldout/heldout_protocol_v1_1.md artifacts/experiments/heldout/heldout_protocol_v1_1.json
git diff --check
```

验收中不得再出现 `X 小时` 或“单项目 CI 不跨 0”这类旧表述。

## 回报格式

返回：

1. 新增/修改文件清单；
2. v1.1 相对 v1 的每项修正；
3. CE 预算、K、seed、replicate、候选规模的最终值；
4. CI 和项目聚类规则；
5. CE blocked 的最终分母规则；
6. Hotel intake 仍为 blocked 的证据；
7. JSON、grep 和 diff 检查结果；
8. 新 commit ID。

完成后停止，等待主代理审核；未经审核不得进入 P2、pilot 或正式实验。
