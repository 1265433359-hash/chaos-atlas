# Sock Shop YAML Confidence Native vs Ablation Review

本报告只把同一 mutation 至少 2 次 completed replicate 都出现业务失败的候选标为稳定真实弱点。
业务弱点不等于具体内部根因；没有额外 RCA 证据时，不推断缓存、注册、重试或服务发现机制。

- human_review: pending
- knowledge_base_updated: false

| 方法 | runtime 候选 | 稳定弱点 | 不稳定 | 非弱点 | invalid | 命中率 | 总耗时(s) | 稳定弱点/小时 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| native-full | 19 | 4 | 3 | 12 | 0 | 21.05% | 5230.211 | 2.753 |
| chaosatlas-ablation | 19 | 6 | 3 | 10 | 0 | 31.58% | 7647.607 | 2.824 |

## Category Contribution

| 方法 | 大类 | 稳定弱点 | 不稳定 | 非弱点 |
|---|---|---:|---:|---:|
| native-full | Network degradation | 2 | 3 | 3 |
| native-full | Pod disruption | 2 | 0 | 4 |
| native-full | Resource pressure | 0 | 0 | 5 |
| chaosatlas-ablation | Network degradation | 4 | 3 | 1 |
| chaosatlas-ablation | Pod disruption | 2 | 0 | 4 |
| chaosatlas-ablation | Resource pressure | 0 | 0 | 5 |

## Boundaries

- 方法本体没有修改；修改的是假设生成条件。
- 两方法使用同一套 5 大类与置信停止规则。
- 不要求相同 runtime 预算；时间成本是实验结果。
- pending 审核结果不会自动写入知识库。
