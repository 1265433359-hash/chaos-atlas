# 审查问题修复计划

目标：修复实验安全性、测试隔离、证据一致性和统计报告问题；每个阶段都必须有自动化验收，不得直接修改已提交实验结果来“让测试通过”。

## 阶段

| 阶段 | 内容 | 状态 | 主要验收 |
|---|---|---|---|
| 0 | 建立修复分支、记录基线、备份/校验 artifacts | pending | `git status`、Python 版本、测试基线和 artifact hash 已记录 |
| 1 | 修复 Chaos 资源清理和进程生命周期 | pending | NotFound/RBAC/timeout 区分；删除失败重试或明确失败；残留资源测试通过 |
| 2 | 修复 runtime gate 的 fail-open 和 selector 安全边界 | pending | kubectl timeout 生成结构化 blocked；RBAC 不得被判为 name available；空 selector 被拒绝 |
| 3 | 修复测试隔离和测试副作用 | pending | 默认 pytest 只跑单元测试；集成测试显式 opt-in；测试不修改版本化 artifacts |
| 4 | 统一候选池、合同清单和 evidence schema | pending | core/extended registry 与 evidence 严格校验；未知候选/项目显式报错 |
| 5 | 修复 runner provenance 和结果汇总 | pending | 每个 runner report 嵌入 environment fingerprint；baseline/lifecycle/cleanup 字段一致；重复次数动态计算 |
| 6 | 修复 selection 指标与 bootstrap | pending | 只统计 registry universe 内候选；区分 weakness/below_threshold/invalid；bootstrap 使用样本分母 |
| 7 | 回归、重算和审计报告 | pending | 单元/集成/静态/schema 检查通过；重新生成比较结果；旧结果保留 hash 和 superseded 标记 |

## 不可违反的约束

- 不允许用 `git reset --hard`、`git checkout --` 或批量覆盖用户文件。
- 不允许为了通过测试修改实验真值；测试应修正为当前合同和 schema。
- 真实 Kubernetes 注入必须显式人工批准；默认只运行 mock/dry-run/单元测试。
- 每个修改必须带回归测试、失败路径测试和报告 schema 变更说明。

## 交付物

- `artifacts/experiments/execution/remediation_baseline.json`
- `artifacts/experiments/execution/remediation_validation.json`
- 更新后的 runner/gate/test/统计代码
- 更新后的比较报告和 `REMEDIATION_REPORT.md`
