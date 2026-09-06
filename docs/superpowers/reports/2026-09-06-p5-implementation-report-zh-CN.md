# P5 实验能力实现与只读验收报告

日期：2026-09-06

## 结论

P5 的实现层已经接入统一 RunEngine 的单候选入口，但本轮没有执行真实业务写入、故障注入或上游 Issue 提交。新增代码提供完整的 32+9 计划、可证伪假设、配对对照与三次复现门、证据门、知识快照、成本摘要和人工审核 Issue 草稿；实时模式没有冻结 Oracle 时会 fail-closed。

## 实现状态

- `src/chaosatlas/experiments/p5.py`：统一 P5 契约与确定性门禁。
- `P5RunCoordinator`：仅调用现有 `RunEngine.run_candidate`，不创建第二条生命周期；未获冻结 Oracle 的 live 请求返回 `blocked_oracle_approval`。
- `scripts/run_p5_plan.py`：读取外置 32+9 能力证据并生成每项目计划及总报告，不执行注入。
- `tests/test_p5_experiments.py`：计划分母、假设、三次复现、Issue 门、知识快照和 RunEngine 门禁测试。

## 离线测试

```text
专项：7 passed
全量：466 passed
compileall：通过
git diff --check：通过
```

## 真实只读证据

输入为 `%LOCALAPPDATA%\\ChaosAtlas\\runs\\p5-static-coverage-20260906` 中四个项目的真实 CapabilityBootstrapper 输出；计划输出位于 `%LOCALAPPDATA%\\ChaosAtlas\\runs\\p5-plan-20260906`。四个项目各保留 41 项分母，合计 164 项：

| 项目 | blocked | canary_required | inapplicable | Issue 草稿 |
|---|---:|---:|---:|---:|
| Immich | 19 | 17 | 5 | 0 |
| Medusa | 19 | 17 | 5 | 0 |
| Rocket.Chat | 19 | 17 | 5 | 0 |
| ERPNext | 19 | 17 | 5 | 0 |

这些结果证明计划生成和分母保留，不证明业务事务、故障能力或机制已经真实验证。

随后通过 `scripts/run_four_app_phase1.py` 对当前 `chaosatlas-apps` 集群完成真实只读验收：4/4 工作负载 Ready、4/4 服务 Oracle 通过、4/4 统一 RunEngine dry-run 通过。原始材料位于 `%LOCALAPPDATA%\\ChaosAtlas\\runs\\four-app-phase1-20260906`。该结果证明环境可进入后续阶段，不改变 19 项能力阻断状态。

## 证据边界与后续准入

- `real_fault_execution=false`；没有真实故障证据，不能声称四项目 41 项已支持。
- 没有三次独立真实复现、机制证据、恢复清理和敏感审查全通过的案例，因此没有 Issue 草稿。
- P5 复现门现要求每次有唯一 `run_id`、唯一 `reset_id`，并引用已记录的 baseline/control；重复记录不能被计入独立复现。
- 首次真实事务仍需人工批准冻结契约（步骤、对象范围、断言、补偿、哈希）；批准后才可使用 P5RunCoordinator 的 live 路径。
- 综合验收报告为 `partial`，唯一失败是现存并被 Dify 挂载的 `environment-reports` 卫生门；其余 compileall、架构契约、Sock Shop/Online Boutique dry-run 和 product-boundary 均通过。
