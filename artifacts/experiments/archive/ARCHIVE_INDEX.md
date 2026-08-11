# 实验归档总入口（ARCHIVE INDEX）

> 日期：2026-08-09
> 目的：四项目、三条方法轴、统一实验台账、证据等级、报告入口——使项目可审计、可复现、可写入论文。
> 原则：只新增状态说明，不删除/不覆盖任何历史 JSON/YAML/日志真值。

## 归档清单

| 归档件 | 文件 | 内容 |
|---|---|---|
| 项目注册表 | `archive/project_registry_archive.json` | 四项目（TT/OB/OTEL/SOCK）：repo、namespace、镜像可用性、执行/未执行候选、held-out 状态 |
| 方法注册表 | `archive/method_registry_archive.json` | 三条方法轴（选择/测量/证据），CE-adapter 与 CE-official 严格分开 |
| 主实验台账 | `archive/run_ledger_master.json` / `.md` | **普通 run records 107 = 83（历史 lifecycle-complete）+ 24（r2）**；独立注入总数 91 = 83（历史）+ 8（r2 首跑）；r2 确认 9、无效基线 7；67 派生文件不计入 |
| Sock Shop 独立轨道 | `archive/sock_track_ledger.json` / `.md` | **13 条 Sock 独立证据（8 契约/真实链路边判定 + 5 availability pod-kill），单独统计，不并入 107** |
| 候选池注册表 | `archive/candidate_pool_registry.json` | 54 唯一候选，OTEL/TT 未部署标记 environment_blocked（不删除） |
| 结论证据矩阵 | `archive/claim_evidence_matrix.md` | 关键结论 + 状态枚举（confirmed/pilot/supplementary/self_referential/blocked/future_work） |
| 综合方法对比 | `overall_project_method_comparison.md` | 三方法轴总表（A7 更新） |
| 统一实验总结 | `unified_experiments_summary.md` | 跨轮统一结论（A7 更新口径） |

## 原始实验报告目录（只读引用，未修改）

- 选择轴对比：`artifacts/experiments/comparison_full_summary.md`、`m1_vs_m5select_comparison.md`、`prospective_round1_result.md`
- 混合池：`artifacts/online-boutique/mixed_pool_comparison.md`
- CE 部署对比：`artifacts/experiments/chaos_eater_deployed_vs_ours.md`、`chaos_eater_vs_evidence_chain.md`
- Sock 契约层：`artifacts/sock-shop/sock_orders_future_get_verified.md`
- Sock 可用性层：`artifacts/sock-shop/sock_availability_layer_verified.md`
- r2 head-to-head：`artifacts/experiments/execution/remediation/r2_head_to_head.md`
- 审查修复：`REMEDIATION_REPORT.md`、`artifacts/experiments/audit_2026-08-09_round2.md`
- 原始运行 JSON：`artifacts/experiments/execution/`（历史 83）、`execution/remediation/r2_runs/`（r2 24）
- 论文素材：`artifacts/papers/paper_writing_archive.md`

## r2 报告及其限制（必读）

- 报告：`execution/remediation/r2_head_to_head.md`
- **限制**：
  1. r2 只在 OB 执行（OTEL 4 + TT 1 候选 environment_blocked，非删除）
  2. 8 候选全 weakness = ceiling/saturation effect（非 floor effect；无 protected 边，方法区分度无法显现）
  3. U@8 = 6 vs 6 vs 5，样本 8，**不是** superiority
  4. 不是跨项目验证；跨项目优于 CE 需 held-out 项目
  5. ChaosEater-adapter ≠ ChaosEater official（分开计）

## 使用指引（写论文/审计时）

1. 引"实验次数" → 用 `run_ledger_master.json`（107 记录 / 91 独立注入 / 83 历史 + 24 r2 分开）
2. 引"候选" → 用 `candidate_pool_registry.json`（54 唯一，含状态）
3. 引"方法" → 用 `method_registry_archive.json`（三轴分离）
4. 引"结论" → 用 `claim_evidence_matrix.md`（状态枚举）
5. 引"项目" → 用 `project_registry_archive.json`（四项目）

## 当前论文冻结边界（2026-08-11）

- 当前论文版本使用主线运行证据、Train Ticket/Online Boutique/OTel Demo
  语义对照、Sock Shop 分层验证和已验证知识卡。
- 知识库 selection-only 消融和最终方法 head-to-head 对比标记为
  `parked_future_work`。协议、快照、prompt、选择记录和中间结果全部保留，
  但 formal runtime、独立 oracle、剩余审查门禁、共同候选池和项目聚类统计
  尚未完成。
- 暂不从这两个轨道写正式效果量、superiority 或跨项目统计结论；后续恢复时
  必须重新核对 claim-evidence matrix 和冻结协议。
