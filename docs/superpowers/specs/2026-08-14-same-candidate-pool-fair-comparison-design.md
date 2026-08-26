# 三项目同候选池公平对比设计

状态：`implementation-ready`

日期：2026-08-14

## 目标

在 Online Boutique、OpenTelemetry Demo、Sock Shop 三个已经部署验证过的真实项目上，比较不同方法在同一候选池中的选择能力。该实验不再比较“谁生成了候选”，而是比较“给同一批候选和同一预算，谁更会选真实有效的故障”。

## 方法

正式方法先冻结为三类：

- `ChaosAtlas-full`：接收候选池、冻结拓扑、业务 oracle，以及允许的 ChaosAtlas 知识视图。
- `ChaosAtlas-ablation`：接收候选池、冻结拓扑和业务 oracle，不接收知识视图。
- `ChaosEater-adapter`：接收候选池、冻结拓扑和业务 oracle，使用 ChaosEater 风格的实验假设/稳态描述，但不读取 ChaosAtlas 知识。

如果后续要跑官方完整 ChaosEater，应作为单独轨道报告，不能和 adapter 混称。

## 候选池冻结

候选池只从运行前可见事实生成：

- 冻结 Kubernetes 拓扑、Deployment/Service selector、replica 数。
- 项目业务 oracle 和 runner 支持的故障族。
- 项目 namespace 和 runner 白名单。
- 固定中性参数阶梯：`pod_kill`、`network_loss=100%`、`network_delay=500ms/2000ms`、`cpu_stress=80%`。

候选池不得包含：

- native-full、full、ablation 或 ChaosEater 的运行结果。
- `weakness_observed`、`no_business_impact_observed`、RCA、日志结论、人工审核标签。
- 历史 mutation 路径、旧候选排序、旧模型输出。

每个候选必须有稳定 `candidate_id`、项目、目标服务、故障族、参数、预期业务不变量、编译出的 YAML、YAML SHA-256。

## 选择预算

每个项目、每个方法、每个 seed：

- 输入同一个候选池。
- 最多选择 4 个候选。
- 每个候选执行 2 次 replicate。
- 候选 ID 是统计单位，replicate 只用于确认复现。

三个方法不能互相读取本轮输出。候选池固定后不因任何方法的结果改变。

## 运行与验收

复用现有三项目 runner：

- Online Boutique：`tools/run_online_boutique_two_arm.py`
- OpenTelemetry Demo：`tools/run_otel_two_arm.py`
- Sock Shop：`tools/run_sock_shop_two_arm.py`

每个单元必须满足：

- baseline 无失败。
- Chaos 注入被确认。
- 恢复被确认。
- Chaos 资源删除且全局残留为空。
- washout 稳定。
- diagnostics captured。
- mutation 和 diagnostics SHA-256 与实际文件一致。

结果报告只允许区分：

- `confirmed_weakness`
- `no_business_impact_observed`
- `environment_blocked`
- `method_invalid`
- `unsupported`

具体根因必须保持 `human_review=pending`，除非另有人审证据。

## 输出目录

正式输出使用新目录，非空则创建后缀目录：

```text
artifacts/experiments/chaosatlas_same_pool_fair_2026-08-14-r1/
  candidate_pools/
  method_inputs/
  selection_results/
  runtime_results/
  reports/
  manifest.json
```

## 成功标准

第一阶段成功标准是候选池冻结和静态校验通过：

- 三项目候选池都非空。
- 所有 YAML server-side dry-run 通过。
- 所有候选 namespace 精确限制在项目 namespace。
- 候选池 manifest 记录 SHA-256。
- 方法输入扫描确认不含 runtime label、RCA、旧 mutation 路径或 credential。

第二阶段才启动正式选择和注入。

