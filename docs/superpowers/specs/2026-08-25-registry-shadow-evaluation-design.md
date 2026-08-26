# Registry Shadow Evaluation Design

## Goal

评估项目全量画像与假设注册表的覆盖质量，并在不改变现有 policy 选择和 live 安全边界的前提下，展示注册表辅助排序与 legacy 排序的差异。

## Scope

本阶段只处理离线 advisory 数据：

- `project_portrait.json`
- `hypothesis_registry.json`
- `candidate_space.json`
- `hypotheses.json`

不执行 Kubernetes 操作，不调用 live executor，不写 policy state，不写正式知识库。

## Architecture

新增纯函数模块 `tools/registry_shadow.py`，提供：

- `evaluate_registry_quality(...)`：检查五类假设覆盖、条目完整性、稳定去重、runtime 候选对应关系和执行预算分离。
- `build_registry_shadow(...)`：以现有 legacy 排序为基线，生成注册表辅助的只读排序建议；只允许 `execution_eligible=true` 且存在于 candidate pool 的 runtime 条目参与建议。

在 `tools/chaosatlas.py` 增加 `--registry-shadow` 开关。运行完成后生成两个非 stage advisory artifact：

- `registry_quality_report.json`
- `registry_policy_shadow.json`

默认不生成这两个报告，以保持现有 CLI 输出兼容；开启开关后也不改变实际执行候选。

## Quality Contract

质量报告必须包含：

- 五类假设计数及缺失类别；
- 每条假设的必需字段完整性；
- hypothesis id 去重和输入 hash 稳定性；
- runtime hypothesis 与 candidate pool 的交集、缺失和多余项；
- `execution_eligible_count` 与 execution budget 的独立值；
- `claim_scope=advisory` 和无 runtime verdict/knowledge promotion 字段的检查结果。

任何检查失败都记录为报告中的失败项，不把失败转为漏洞结论。

## Shadow Contract

shadow 报告必须同时保存：

- legacy candidate ids 和排序；
- registry-derived runtime candidate ids 和排序；
- top-k 差异、共同候选和只在一侧出现的候选；
- `selection_changed`、`mutation_executed=false`、`policy_state_updated=false`、`formal_knowledge_written=false`。

注册表中的 architecture/configuration/dependency/defense 条目只能作为覆盖统计，不能进入执行建议。

## Determinism and Errors

所有排序和 hash 使用稳定的 canonical JSON；未知 candidate id、重复 hypothesis id、缺失字段或非 advisory claim scope 进入 fail-closed 报告状态。模块不抛出到 live runner，而是返回结构化错误，便于审计。

## Verification

- 单元测试覆盖五类覆盖、字段缺失、未知 candidate、静态假设排除、稳定输出和 shadow 差异。
- `chaosatlas run --registry-shadow` 在 Sock Shop 和 Online Boutique fresh dry-run 中生成两个报告。
- 重复运行报告的输入 hash、候选排序和副作用标志一致。
- 现有默认 dry-run 和 live 路径的测试保持通过。

## Future Boundary

本阶段不让 registry 直接驱动 policy 或 live mutation。只有在两个项目的覆盖质量与 shadow 报告稳定后，才设计 guarded policy 接入。
