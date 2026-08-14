# ChaosAtlas 两臂真实项目自主发现实验设计

**状态：** design-review-pending
**日期：** 2026-08-13
**正式方法：** `ChaosAtlas-full`、`ChaosAtlas-ablation`
**正式项目：** Online Boutique、OpenTelemetry Demo、Sock Shop

## 1. 研究问题

本实验回答：

> 在真实部署的微服务项目中，跨项目人工审核通用知识是否提升 ChaosAtlas 的自主故障发现、实际执行、业务影响识别、恢复清理和证据闭环能力？

本实验不比较 ChaosEater，不使用 ChaosEater adapter，不把历史候选池选择实验或固定 mutation pilot 当作正式自主发现结果。

## 2. 实验矩阵

| 维度 | 冻结值 |
|---|---|
| 项目 | Online Boutique、OpenTelemetry Demo、Sock Shop |
| 方法 | `ChaosAtlas-full`、`ChaosAtlas-ablation` |
| seed | 1001、1002、1003 |
| 总调用数 | 3 x 2 x 3 = 18 |
| 每次最大生成假设数 | 8 |
| 每次最大执行假设数 | 4 |
| 每个执行假设的独立重复数 | 2 |
| 正式运行单元上限 | 3 x 2 x 3 x 4 x 2 = 144 |
| 超出预算的假设 | `budget_not_executed`，不进入运行分母 |
| 故障范围 | `pod_kill`、`network_delay`、`network_loss`、`container_cpu_stress`，以项目能力 gate 为准 |
| 运行范围 | 仅项目专属 namespace |
| human review | `pending`，不自动写知识库 |

每个项目、seed 和方法拥有独立的输入、输出、运行账本和 hash。正式输出放入新的版本化目录，不覆盖历史目录。

## 3. 方法输入边界

### 3.1 共享输入

两种方法对同一项目和 seed 接收字节级一致的：

- 固定项目 commit 和 source-tree hash；
- 脱敏后的部署拓扑和依赖边；
- 资源、服务和可达 workload 合约；
- Chaos Mesh 能力和参数边界；
- namespace、恢复、清理和超时运行契约；
- 输出 schema、模型预算和 seed。

共享输入不得包含候选池、candidate ID、历史选择顺序、运行时 oracle、旧 mutation、旧 RCA 或另一方法输出。

### 3.2 `ChaosAtlas-full`

只允许接收跨项目、人工审核后的通用知识抽象。知识视图只能包含：

- 通用故障家族和适用条件；
- 通用防御机制模式；
- 适用性边界和反例条件；
- provenance、source commit 和 projection hash。

不得接收三个目标项目各自的历史知识卡、历史运行结果、旧 mutation、旧 RCA 或旧候选排序。

### 3.3 `ChaosAtlas-ablation`

不接收任何知识视图或 feedback projection。除知识视图外，其余输入、prompt 骨架、预算、seed、编译器和运行契约必须与 `ChaosAtlas-full` 一致。

## 4. 自主发现和执行流程

每个方法在每个项目和 seed 中独立执行：

1. 读取冻结项目证据和方法允许的输入视图。
2. 自主生成最多 8 个故障假设。
3. 通过统一安全编译器校验 target、target kind、fault family、参数、调用链、业务不变量、验证计划和恢复预期。
4. 按模型原始输出顺序选择前 4 个通过编译的假设执行；不按历史知识、人工判断或另一方法输出重排。
5. 每个进入预算的假设执行 2 次独立重复。每次重复都重新完成 baseline、注入、观察、恢复、Chaos 资源删除、全局残留扫描和 washout。
6. 只有满足两次有效复现和完整证据条件的假设，才可分类为 `confirmed_weakness`。
7. 保存每次重复的业务响应、服务日志、事件、trace、资源状态和所有 SHA-256。
8. 将编译失败、预算未执行、环境阻断和运行失败分别记录，不把它们混成方法弱点。

“自主发现”要求故障假设由方法输出产生。预先给定 mutation 只能作为 runner smoke test 或历史 pilot，不得进入正式发现率、issue yield 或方法优越性统计。

## 5. 部署和运行 gate

每个项目必须先完成以下离线和集群 gate：

1. 固定 commit、镜像 digest、本地 provenance 和脱敏 manifest。
2. 目标 namespace 独占，server-side dry-run 先验证 namespace，再验证 namespaced resources。
3. 部署后所有 required Pods Ready，业务入口和依赖服务可达。
4. 使用同一业务 oracle 完成两个无失败 baseline window。
5. 完成一次不注入的 recovery/cleanup rehearsal。
6. 运行前确认全局 `podchaos,networkchaos,stresschaos` 无残留。
7. 任一 cleanup failure、namespace 越界、oracle 不稳定或安全编译器 defect 都停止该项目。

项目通过 gate 之前不调用正式模型、不执行正式 mutation。

## 6. 项目业务 oracle

### Online Boutique

使用 frontend golden journey 加 PlaceOrder checkout workflow。必须同时记录 HTTP 状态、响应契约、订单流程结果和恢复后的连续成功窗口；loadgenerator 不作为正式 oracle，避免背景负载污染。

### OpenTelemetry Demo

使用 checkout PlaceOrder workflow 和稳定的响应/deadline 合约。业务结果由独立 oracle 判断，trace 仅作为旁证；若 trace backend 不可用，必须明确记录 unavailable，不得假设 trace 存在。

### Sock Shop

使用 front-end 可达性、catalogue 浏览和 orders 读路径组成只读 golden journey。必须记录 HTTP 状态、关键响应字段、依赖可达性和恢复后的连续成功窗口；不得只用 Pod Ready 代替业务 oracle。

每个 oracle 的请求、超时、成功条件、失败条件、状态重置和稳定窗口必须在运行前冻结，运行中不得按结果改口径。两次重复之间必须完成恢复和 washout；若第二次重复无法从同一冻结基线开始，该假设标记为无效重复，不得补跑第三次来替代协议要求。

## 7. 结果分类和主要指标

每个假设独立分类为：

- `confirmed_weakness`：至少两次有效复现，baseline、injection、observation、recovery、cleanup 和 independent oracle 全部通过；
- `protected`：注入已确认，但独立业务 oracle 保持正确且有防御证据；
- `latent_risk`：有静态或不完整旁证，未完成有效运行确认；
- `unsupported`：证据不足以支持风险或防御结论；
- `environment_blocked`：部署、平台或外部依赖阻断；
- `method_invalid`：模型输出或安全编译违反协议。

主要报告指标：

1. hypothesis validity rate；
2. executable rate；
3. confirmed weakness yield；
4. protected-target yield；
5. novel issue yield，仅作为描述性指标，且相对于独立冻结的评估参考；
6. business-impact rate；
7. recovery success rate；
8. cleanup and washout success rate；
9. evidence completeness；
10. RCA accuracy，仅对具备独立真值和充分证据的条目计算；
11. token、运行时间和人工审核时间。

不把模型假设数、重复执行数或不同项目的原始 latency 直接当作独立样本。先报告每个项目的 paired `full - ablation` 差值，再报告三个项目的描述性汇总。

## 8. 污染控制

- 目标项目历史运行结果只能留在 audit artifacts，不能进入该项目本次 prompt。
- `ChaosAtlas-full` 和 `ChaosAtlas-ablation` 互不接收对方本轮输出。
- ablation 永远不接收 feedback projection。
- pending RCA、未审核卡片、旧 candidate pool 和旧 mutation 不得成为正式输入。
- 每个 prompt、common input、knowledge projection 和编译输出记录 SHA-256。
- 正式运行前执行 contamination audit；失败则阻断模型调用。

## 9. 证据目录

正式结果使用新的目录根：

```text
artifacts/experiments/chaosatlas_two_arm_real_projects_2026-08-13/
  manifests/
  input_bundles/
  runtime_profiles/
  runtime_results/
  reports/
```

单项目运行目录至少包含：

- `manifest.json`；
- `full/` 和 `ablation/` 独立输出；
- 每个假设的 canonical hypothesis、compiled intent 和 mutation YAML；
- baseline、injection、observation、recovery、cleanup、washout；
- 关键服务日志、events、trace 或 unavailable 记录；
- `sha256.json`；
- 每个假设的两次重复记录和重复级别结果；
- method-level review report；
- `human_review: pending`。

旧的 P09、P02、Sock Shop fixed-mutation pilot 和候选池实验只作为历史工程证据，不复制到正式结果目录，不进入正式统计。

## 10. 停止规则和声明边界

以下任一情况发生时停止当前项目：连续三次传输失败、Chaos 资源删除失败、全局残留、oracle 不稳定、namespace 越界或安全编译器缺陷。

本实验完成后允许的结论是：

> 在三个指定真实项目和固定预算条件下，比较有无跨项目通用知识对 ChaosAtlas 自主故障发现与验证闭环的影响。

不允许的结论是：

- ChaosAtlas 对所有微服务项目普遍更强；
- 知识视图必然提升所有故障家族；
- 仅凭静态假设或 HTTP health 通过证明业务安全；
- 将历史 pilot 或候选池排序结果写成正式自主发现结果。
