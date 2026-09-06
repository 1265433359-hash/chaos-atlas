# P5 四项目正式有界实验与证据报告

日期：2026-09-07。批准事务契约批次：`87f929e0d52510871fb19d8e8bc40a46f1002dd9ff921d5d26be0579a5648db3`。

## 1. 结论

P5 的首轮正式有界实验已经完成，证据包位于：

`%LOCALAPPDATA%\ChaosAtlas\runs\p5-formal-evidence-20260907-d`

四个项目的 32 核心 + 9 provisional 扩展能力均完成静态判定，保留 4 × 41 = 164 个分母。Immich、Medusa、ERPNext 各完成一次当前统一 `RunEngine` 的真实 `secret_rotation` 低强度 canary；每次都使用可销毁应用副本、人工冻结的事务 Oracle、真实 Kubernetes Secret 修改和机制确认，并完成业务恢复、故障清理和环境释放。三次均为 no-impact，未发现达到因果复现门槛的异常。

Rocket.Chat 仍按已确认方案 A 保持 `restricted-workspace` 阻断：本轮没有接受外部工作区注册、许可证条款或版本切换，因此没有执行 Rocket.Chat 真实事务和故障。P5 正式包的状态是 `completed_with_documented_blocker`，不是“四项目全部真实通过”。

本轮没有真实 LLM 调用。运行记录为 `deterministic_fallback`；当前没有可用的 DeepSeek provider 凭据，所以不能宣称 LLM 策略已获得真实验证，也不能声称 LLM 优于确定性策略。

## 2. 本阶段实现

1. `P5RunCoordinator` 改为调用唯一的 `RunEngine.run`，隔离、批量、事务 Oracle 与清理不再被 `run_candidate` 旁路。
2. 新增真实 canary 准入门。只有 batch 完成、隔离 Ready、注入及机制确认、runtime attestation、真实业务基线/观察/恢复、故障清理、业务清理、环境释放、冻结契约绑定和敏感审查全部通过，运行才计入真实证据。
3. 修复 P5 总报告状态聚合；现在按状态累加 164 个单元，不再生成 `blocked:16 = 1` 形式的错误统计。
4. 新增正式证据打包入口 `scripts/run_p5_formal_package.py`。它读取外置能力矩阵和真实运行，fail closed 校验后输出计划、能力矩阵、环境/租约、Oracle 引用、假设与决策引用、运行结果、复现账本、RCA、知识快照清单、覆盖、成本和 Issue 清单。
5. 正式包中的每个关键源文件及每个包内产物均记录 SHA-256；原始运行、凭据和临时状态继续保留在仓库外。

## 3. 41 项静态结论

每个项目当前矩阵相同：

| 状态 | 每项目 | 四项目合计 | 含义 |
|---|---:|---:|---|
| `supported` | 4 | 16 | 已有对应运行机制证据；不等于本轮对每项都重跑事务实验 |
| `canary_required` | 16 | 64 | 执行路径存在，但仍需目标级真实低强度 canary |
| `blocked` | 16 | 64 | 当前环境/执行能力缺少前置条件 |
| `inapplicable` | 5 | 20 | 当前项目画像没有相应资源语义 |
| 合计 | 41 | 164 | 分母未删除 |

此前 19 项 blocked 中，`secret_rotation`、`image_pull_failure`、`pod_unschedulable` 已借助通用 Kubernetes L2 执行机制和真实机制证据转为 `supported`；剩余 16 项仍如实保留。这里的“supported”是故障机制能力，不是 41 项业务行为均已得到真实事务验证。

## 4. 当前统一方法的真实证据

| 项目 | 事务 Oracle | 故障/机制 | 结果 | 清理 |
|---|---|---|---|---|
| Immich | `immich-asset-roundtrip-v3` | `secret_rotation` / `secret_value_reflected` | baseline、observe、recovery 全通过；0 finding | 业务、故障、namespace 均清理 |
| Medusa | `medusa-cart-lineitem-v3` | `secret_rotation` / `secret_value_reflected` | baseline、observe、recovery 全通过；0 finding | 业务、故障、namespace 均清理 |
| Rocket.Chat | `rocketchat-message-roundtrip-v3` 已冻结 | 未执行 | `restricted-workspace` | 未创建实验租约 |
| ERPNext | `erpnext-todo-crud-v3` | `secret_rotation` / `secret_value_reflected` | baseline、observe、recovery 全通过；0 finding | 业务、故障、namespace 均清理 |

采用的原始运行及关键哈希：

- Immich：`p4-unified-immich-secret-rotation-canary-20260906-ai`；batch `79e6370e...9281246f`；isolation `32d699c6...0979184`。
- Medusa：`p5-unified-medusa-secret-rotation-canary-20260906-aj`；batch `5ba16750...92b5851`；isolation `007d800e...9601395`。
- ERPNext：`p5-unified-erpnext-secret-rotation-canary-20260906-ak`；batch `25210611...05f5d3`；isolation `2f8d7b03...3ccb3e0`。

正式包重新校验结果：3/3 canary 的所有准入门为 true；敏感值命中为空；最终 `chaosatlas-apps` context 中无 `ca-l1-*`、`ca-l2-*` 或 `ca-l3-*` 残留 namespace。正式包 `artifact-manifest.json` 文件 SHA-256 为 `2b335098...250c000`，其中列出的产物哈希复核无失败。

## 5. Issue、因果复现与学习边界

- 三次 canary 都没有业务异常，因此没有启动“三次独立异常复现 + 配对无故障对照”流程。不能把三个不同项目的 no-impact 运行拼成某个异常的三次复现。
- `reproduction_attempt_count=0`，`valid_reproduction_count=0`，`qualified_finding_count=0`，`issue_draft_count=0`。
- Issue 清单明确记录零草稿；没有为了产出数量而降低证据门槛，也没有向任何上游提交 Issue。
- 三次 no-impact 与 Rocket.Chat blocker 已进入本轮外置知识/决策清单，但没有执行跨项目知识晋级。
- 成本目前只可靠记录实验次数 3、LLM 调用 0；没有可靠采集端到端墙钟时间，因此 `wall_time_seconds_measured=false`，不把默认零值解释成零耗时。

## 6. implemented / tested / real-evidence

提交前自动验收：专项 P5 测试 `11 passed`；仓库全量测试 `594 passed`；`compileall` 与 `git diff --check` 通过。仓库综合验收为 `partial`：architecture contracts `12 passed`、Sock Shop/Online Boutique dry-run 和 product boundary 均通过；唯一失败仍是工作区中现存的 `environment-reports`。该目录被用户现有 Dify 环境挂载，本阶段未删除或移动，也不把这项卫生失败解释为 P5 代码失败。综合验收原始报告位于 `%LOCALAPPDATA%\ChaosAtlas\runs\p5-repository-acceptance-20260907-b.json`。

| 能力 | 已实现 | 自动测试 | 真实证据 |
|---|---:|---:|---|
| P5 统一调用 `RunEngine.run` | 是 | 是 | 三项目真实 canary 经同一入口 |
| 41 项分母与状态保留 | 是 | 是 | 四份当前外置 bootstrap，合计 164 |
| 真实 canary fail-closed 证据门 | 是 | 是 | 3/3 全门通过；篡改反例被测试拒绝 |
| 冻结事务 Oracle 绑定 | 是 | 是 | 三个真实 canary 的契约 hash 匹配 |
| 机制、恢复、双清理、释放 | 是 | 是 | 三项目 `secret_value_reflected`，零 namespace 残留 |
| 异常三次独立复现门 | 是 | 是 | 本轮无异常，未触发真实复现 |
| Issue 草稿门 | 是 | 是 | 本轮 0 草稿；无真实正例验证 |
| 真实 LLM 假设/选择 | 接口与门禁已有 | 结构/降级测试 | 无；本轮确定性 fallback |
| Rocket.Chat 完整方法运行 | 已具备契约与编排 | 有离线/历史只读检查 | 无；受限工作区阻断 |
| 164 项全面真实注入 | 未完成 | 不适用 | 无；仅 3 个当前统一 canary |

## 7. 可用于论文的口径

可以引用：四项目静态能力分母 164；状态分布 `supported=16`、`canary_required=64`、`blocked=64`、`inapplicable=20`；当前统一事务+故障真实 canary 3 次，机制确认 3 次，合格异常 0，Issue 草稿 0，真实 LLM 调用 0，Rocket.Chat 环境阻断 1 项目。

不能引用为已证明：四项目 41 项均可真实执行、164 项均完成业务实验、方法已找到应用缺陷、LLM 带来收益、未知第五项目的迁移能力、或 Rocket.Chat 已通过完整方法。

这四个项目仍属于方法开发/能力验证集。下一步若继续研究，应在不回灌本轮结果的冻结知识快照下选择新的第五项目做迁移评估；该工作不属于本轮 P5 完成证据。
