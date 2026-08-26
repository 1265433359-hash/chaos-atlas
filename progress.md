# Progress

## 2026-08-24 信息增益策略与证据规划收尾

- 修正静态候选分母：当冻结拓扑同时存在 `service/<name>` 与 `workload/<name>` 节点时，生成与 native handoff 对齐的 `target_kind=service` 候选；不存在成对节点时不扩大分母。相关测试 `6 passed`。
- 使用冻结输入 `artifacts/experiments/chaosatlas_native_full_2026-08-14-r4`、Online Boutique、seed `1001` 完成离线 Legacy/Shadow replay；产物目录为 `artifacts/policy-rollout/online-boutique-r4-shadow-20260823/`。
- Legacy 选择 H4/H6/H8 对应的 3 个 service 候选；Shadow 在相同分母和预算下选择 H6 对应的 1 个候选。两边均无 runtime 输入，故不能推断弱点发现率或无效率改善，comparison gate 保持 `pending_runtime_evidence`，未开启 `guarded`。
- replay JSON 已重新计算并通过一致性校验：comparison 中的 Legacy/Shadow 报告与独立报告完全一致，未知候选为 0，`runtime_executed=false`、`model_called=false`。
- 新增确定性只读证据规划器 `tools/evidence_action_planner.py`，并接入 `chaosatlas run`：advisory 只能映射到白名单 evidence actions；未知候选、签名不匹配或恢复契约缺失时 fail closed；live executor 前要求计划状态为 `planned` 且候选在计划内。
- 修复归档完整性漂移：generic-rules JSON 固定 LF；70 个 ESHOP/SOCIALNET mutation map 与 manifest 哈希改为当前 LF YAML 的实际 SHA，YAML 内容未改动；旧保护评估夹具补齐 `defense_claim_type` 和完整证据字段。
- 验证：策略/候选/replay 聚焦套件 `18 passed`；证据规划与闭环聚焦测试通过；`compileall` 和 `git diff --check` 通过；全量 `1200 passed, 1 warning, 5 subtests passed`。唯一警告是 Windows pytest cache 目录权限，不影响断言结果。

## 2026-08-21 统一离线闭环编排器

- 按已批准规格实现 `tools/chaosatlas.py run --mode dry-run`，固定顺序为项目接入、inventory、服务器部署检测、候选映射、经验检索、advisory 假设、门禁、基线、合成执行、分类、RCA、知识草稿和回归意图。
- 新增运行契约、checkpoint/resume、离线项目 adapter、服务器部署检测 adapter、只读知识 provider 和 fake executor；CE/native 未进入本阶段真实执行。
- 三项目离线回放：Sock Shop、Online Boutique、P02 均通过同一编排器路径。
- 验证：focused suite `18 passed`（含三项目回放）；Sock Shop CLI 实跑输出 `dry_run_ready`，未生成 runtime weakness/defended/confirmed 结论。

## 2026-08-21 三步推进：检索接入、二次复现、第三迁移（2026-08-21 晚）

- 步骤 1（OB 检索接入）：新增 `build_ob_rca_snapshot.py`（读 `ob_validation_decision.json`，verdict 非 `prior_validated` 即 fail-closed；只投影 abstraction + provenance）和 `run_ob_rca_retrieval_replay.py`。真实重放：两个 OB kill 候选被先验卡命中并加分、携带 observation-window-artifact 诊断，两个无关候选分数不变；产物 `cross-project-r1/ob-retrieval-replay-r1/`。
- 步骤 2（二次复现）：`ob-validation-r5` 独立复现同样 `prior_validated`（arm A 7 中断共证、arm B 31 防御共证、生命周期干净）。
- 步骤 3a（sock-shop 两张 provisional 卡闭合）：`run_sock_shop_card_closure.py` 双臂闭合 catalogue-db（r1 因 `/` oracle 不穿透 catalogue 链路而无差异，保留为证据；r2 改用 `/catalogue` JSON oracle 后 arm A 54 中断共证、arm B 10 防御共证 → `redundancy_mechanism_confirmed`）；http-abort 单臂确认（`transport_abort_propagates`，500、无优雅降级）。`apply_card_closure.py` 按闭合 disposition 确定性晋级两张卡至 v2 `local_reusable`，RCA 验证器 `valid=True errors=0 warnings=0`。
- 步骤 3b（第三迁移，P02 Spring Petclinic 替代无 HTTP 入口的 OTel）：`run_p02_prior_validation.py` 双臂验证 customers-service（oracle `/api/gateway/owners/1`）。r1 保留为失败证据（Spring 冷启动网关路由解析 >300s，基线窗口不足）；r2 在预热栈上 `prior_validated`（arm A 13 中断共证、arm B 70/70 防御共证、生命周期干净）。Java/Spring 栈与 Go/Node 栈的第三次迁移成立，台账见 `cross-project-r1/migration_ledger.json`。
- 集群收尾：sock-shop 保持原状；OB 与 P02 namespace 均缩回 parked replicas=0；全局 PodChaos/HTTPChaos 为空。
- 验证：全量 `tools/tests` 1033 passed + 5 subtests，仅剩 2 个既有 pinned-hash 漂移；新增 12 个测试（OB snapshot/replay 6 + card closure 门禁 2 + reducers 增补 4 在既有文件内）。

## 2026-08-21 OB 先验验证闭环（跨项目复用完成）

- 用户授权集群操作后执行两臂对照验证（`tools/run_ob_prior_validation.py` + `tools/ob_prior_validation.py` 归约器，10 个单测）：目标 `chaosatlas-online-boutique/productcatalogservice`（单副本无 PDB），oracle 为 frontend `/product/<id>`（经 productcatalog + currency）。
- r1/r2 失败保留为证据：冷启动窗口 5xx（runner 增加有界基线重试与 HTTP 状态码记录）、`/api/products` 在该 frontend 构建中不存在（404，改用 `/product/OLJCESPC7Z`）。
- r3 发现真实竞态：替代 Pod 在被杀同一秒创建并抢先重新注册 endpoints，但业务 gRPC 预热仍失败——中断窗口存在而旧判据（业务失败 AND endpoints 空）漏检。归约器改为"业务失败且注入前 Ready 的 Pod 已消失"共证判据（带 4 个新测试）。
- r4 最终结果 `prior_validated`：arm A 7 个中断共证样本、arm B 64/64 存活 Pod UID/IP 共证防御样本、生命周期干净（PodChaos 全局无残留、副本还原、namespace 缩回 parked 状态 replicas=0）。
- `ob_validation_decision.json` 记录先验从 provisional 晋级 `validated_on_target_project`；正式 OB 知识库目录仍未改动。
- 全量 `tools/tests` 1027 passed + 5 subtests，仅剩 2 个既有 pinned-hash 漂移。

## 2026-08-21 跨项目知识投影（sock-shop -> Online Boutique）

- 人工审核完成：项目所有者阅读 `runtime-live-r4-final/HUMAN_REVIEW.zh-CN.md` 后决定 `approved_local_reuse_with_cross_project_projection`，记录于 `human_review_decision.json`；跨项目模式为 `provisional_prior_pending_target_project_validation`。
- 新增 `tools/project_sock_shop_rca_cross_project.py`：fail-closed 执行投影。程序化复核证据链（r2 AllInjected、时间轴含中断样本、两轮 residual 为空、r4 冗余对照 defended 共证、副本数还原）而非信任文件名；`classify_outcome` 必须给出 `confirmed_weakness`；经 `build_feedback_card` + `validate_knowledge_card_boundary` + `build_next_kb` 后再次检查投影卡无 evidence/target/classification 字段且无 FORBIDDEN_KB_MARKERS 文本。
- 投影产物 `artifacts/sock-shop/rca_loop/cross-project-r1/`：审计卡 `FA-7ff5b1794a0758d4`（保留全部证据，留在 sock-shop 侧）、OB KB 快照（只含 abstraction：适用条件、预期效应、"早期成功样本不是防御"、扩容验证配方）。
- 验证：新增 5 个投影测试（决定门禁、反事实缺失、无中断样本、非 local_reusable 卡、泄漏检查）+ feedback_protocol 回归全绿；全量 `tools/tests` 1017 passed + 5 subtests，仅剩 2 个既有 pinned-hash 漂移。
- 边界：正式 OB 知识库目录未修改；投影是 provisional prior，须在 OB 单副本服务上完成对照验证后才可晋级。

## 2026-08-21 Sock Shop RCA local_reusable 检索与决策 guard 闭环

- 新增 `tools/build_sock_shop_rca_snapshot.py`：把 `runtime-live-r4-final` 的知识草稿投影为决策引擎消费的 `rca_snapshot`（schema_version=1）。只投影引擎字段（无 evidence dump），记录来源路径与 SHA-256；schema 漂移、未知 knowledge_status、缺 regression intents 全部 fail-closed。
- `closed_boundary` 从该轮 kind=guard 回归意图（`closed_runtime_boundary_no_reinjection`）推导：`tools/decision_engine.py` 中匹配的 `local_reusable` 闭合卡不再加分，而是输出"closed runtime boundary; re-injection guarded"并保留 next-evidence 诊断；provisional/contested 行为不变。
- 新增 `tools/run_sock_shop_rca_retrieval_replay.py`：固定 5 个 Sock Shop 候选的同项目离线重放。真实快照结果：2 个 front-end pod-kill 候选被 guard 卡命中且不加分，3 个无关候选排名与无快照基线完全一致；产物在 `artifacts/sock-shop/rca_loop/retrieval-replay-r1/`。
- 验证：新增/相关测试 79 passed；全量 `tools/tests` 1012 passed + 5 subtests，仅剩 2 个既有 pinned-hash 漂移失败（历史消融产物，未触碰）。py_compile 通过。无集群操作、无模型调用、无知识库正式写入。
- 边界：跨项目复用仍需人工审核与既有 feedback protocol；正式 KB 未更新。
- 后续收尾（同日）：提交了上一轮 RCA disambiguation/redundancy 代码与产物链（commit `9ba36d2`，225 个文件，敏感扫描仅命中 serviceaccount 挂载元数据）；生成 `runtime-live-r4-final/HUMAN_REVIEW.zh-CN.md` 人工审核材料，明确列出 r4 的 3 defended + 12 platform_blocked 样本构成、1 条已降级反对证据和三项待审决定（local_reuse 批准 / 跨项目投影授权 / 驳回处置）。审核决定写入 `human_review_decision.json` 前跨项目迁移保持阻塞。

## Phase 2 native discovery space (2026-08-20)

- Added `tools/candidate_coverage_denominator.py` to enumerate static `dependency_edge`, `deployment`, and `scenario` candidates from frozen topology/deployment facts.
- Added independent `coverage_denominator/seed-*.json` artifacts to `run_native_full_discovery.py`; denominator is `static_only` and contains no runtime results or CE verdicts.
- Native discovery prompts now receive only bounded candidate facts and explicitly forbid runtime verdicts, runtime observations, mutation paths, and CE-selected hypotheses.
- Extended `decision_engine.rank()` with a native candidate path that accepts deployment/edge/scenario candidates without legacy project-prefix parsing; knowledge can alter priority and diagnostics only.
- Missing selector, business oracle, or recovery contract produces `blocked` candidates. Deployment capability nodes now carry a declared recovery contract.
- Verification: Phase 1 + Phase 2 focused combination `46 passed`; full runtime/cluster execution remains `not_run` and no native capability claim is made from offline tests alone.

## Phase 0 project onboarding (2026-08-20)

- Added `tools/project_onboarding.py` with profile schema validation, local-input inspection, unified result mapping and defense-claim gates.
- Added `artifacts/project_profiles/sock-shop/project_profile.json` and `docs/PROJECT_ONBOARDING.md`.
- Integrated `result_contract` into `runtime_applicability_gate.py` and `classify_runtime_result.py`; integrated optional profile validation into `validate_knowledge_base.py`.
- Verification: 29 focused tests + 5 subtests passed; 186 RCA/knowledge integration tests passed; profile CLI returned `ready_for_static_analysis`; Python compilation and `git diff --check` passed.
- Boundary: runtime remains `not_checked`; no cluster, deployment, injection, model call or secret access occurred.

## Session 4 offline statistics (2026-08-12)

- Added `tools/analyze_chaosatlas_statistics.py` and `docs/CHAOSATLAS_STATISTICS.md`.
- The analyzer aggregates three seeds inside each project, never treats LLM calls as independent samples, computes project-level KB-minus-noKB deltas, and summarizes the delta distribution across observed projects.
- It reads normalized JSON/JSONL or auto-discovers open-discovery/runtime/token-ledger artifacts; absent denominators remain `null`.
- Generated `analysis_outputs/chaosatlas_statistics/statistics.json` and `.md`. Current frozen evidence contains P02 only, so the report is explicitly `incomplete_missing_projects` (1/10), not a complete 10-project claim.
- Added `tools/tests/test_analyze_chaosatlas_statistics.py`; focused verification: 4 passed (pytest cache warning only).

## Main experiment priority reset (2026-08-12)

- The primary deliverable is now the 10-project open-discovery track; the fixed candidate-pool three-arm track is parked as a secondary control.
- Added `tools/main_experiment_orchestrator.py`. It is offline-only: it reads frozen gate/topology evidence, checks native ChaosEater Skaffold eligibility, writes the 90-row main ledger, and can emit the P02 Compose-to-kind selector map. It does not read the DeepSeek key, call an LLM, apply Kubernetes resources, or inject faults.
- Generated `artifacts/experiments/chaosatlas_10_projects/main_experiment_ledger.json`: 10 projects, 3 seeds, `ChaosAtlas-KB-open`, `ChaosAtlas-noKB-open`, and `ChaosEater-official`; 6 P02 ChaosAtlas rows are ready only after explicit LLM consent, 84 rows are blocked by project/runtime or official-input gates.
- Generated `artifacts/experiments/chaosatlas_10_projects/runtime_profiles/P02/runtime-map.json`, mapping frozen Compose service nodes to namespace-local Deployment selectors from the static profile.
- Official ChaosEater is not currently runnable for these frozen projects because no native `skaffold.yaml` entrypoint was found. `ChaosEater-adapter-open` remains supplementary and cannot replace it.
- Verification: 24 focused open-discovery/compiler/topology tests passed. No DeepSeek request or mutation was performed.
- Added `tools/run_main_experiment_dry_run.py` and an explicit P02 fixture artifact. The fixture passed open-discovery compilation and mutation compilation, producing one namespace-local NetworkChaos YAML with provenance; it is marked `dry_run_fixture` and excluded from metrics.
- Kubernetes read-only preflight passed (`kind-chaos-kind`, node Ready, Pod/Network/Stress/Workflow CRDs present). P02 static profile and generated NetworkChaos passed server-side dry-run after reconciling `customers-service` to the already deployed 1Gi request/limit; reconciliation is recorded in `runtime_profiles/P02/kubernetes-static/profile_reconciliation_2026-08-12.json`.
- Added `MAIN_DEPLOYMENT_REMEDIATION.md`, an ordered queue for the remaining nine deployment gates. Static inputs are now tracked separately from runtime eligibility so blocked projects do not stall input freezing.

## 2026-08-10 project archive pass
- Added top-level `README.md` under the confirmed project name **ChaosAtlas**.
- Added `docs/ARCHIVE_MAP.md`, `docs/EXPERIMENT_CATALOG.md`, `docs/KNOWLEDGE_BASE.md`, `docs/CODE_GUIDE.md`, and `docs/GITHUB_PRIVATE_HANDOFF.md`.
- Documentation separates static, runtime, blocked, pending, and exploratory evidence; maps the three case-study families; and records the explicit no-upload-until-approved gate.
- Existing user/generated experiment files were not reset or rewritten.
- Verification complete: all three knowledge-base validators returned `valid: true`; Train Ticket reported 7 cards with no warnings, while generated YAML warnings for Online Boutique (8 cards) and OpenTelemetry Demo (2 cards) remain explicit and expected.
- Full regression suite passed with an isolated repository temp directory: `249 passed, 1 warning, 5 subtests passed`. The warning is pytest cache permission noise; no test assertion failed.
- Documentation path resolution, trailing-whitespace, and sensitive-token scans passed for the new README/docs files.
- Upload remains gated on explicit owner approval; no remote was configured and no data was pushed.

## 2026-08-10 project summary pass
- Started a read-only repository-wide inventory for `docs/PROJECT_SUMMARY.md`; no runtime mutation or remote action is planned.
- Completed the inventory and added `docs/PROJECT_SUMMARY.md` with the current repository scale, directory ownership, three case studies, evidence levels, knowledge-base/ablation status, paper boundaries, limitations, and prioritized next steps.
- Consistency checks passed: concrete summary paths resolve, no high-signal credential patterns or trailing whitespace found, and `git diff --check` reports no content errors.

## Paper preparation checkpoint (2026-08-04)
- Created `artifacts/train-ticket/paper_prep_stage_summary.md` as the evidence-backed stage report for paper writing.
- The current stage is summarized as: real YAML inventory -> test-node-centered local graph -> applicability gate -> bounded injection -> dual Oracle and multi-signal observation -> result classification -> knowledge feedback.
- Current publishable case study: Station NetworkChaos delay preserves response contracts below the boundary, crosses the 5s experimental client budget at 3s nominal delay, and logs server-side completion after client timeout.
- Next stage priorities: repeat the core profiles for statistical summaries, standardize local CFG/DFG exports, build an LLM decision benchmark, then extend to a reachable Order workflow and HTTPChaos after platform prerequisites are fixed.

## Station NetworkChaos two-oracle replay (2026-08-04)
- Captured a read-only direct Station not-found baseline: median 32.038ms, envelope `status=0,msg=Not exists,data=stationName`.
- Replayed the same 100ms/20s outbound delay with 3 warm-ups and 10 formal requests. All not-found responses preserved the exact envelope; median latency was 215.359ms (+183.321ms).
- Compared to the success oracle (+185.876ms), the near-equal latency deltas show a reproducible network-edge effect rather than a success/not-found branch-specific failure.
- Upgraded `KB-TT-NETWORK-STATION-DELAY-001` to v2 and added `generated_station_network_delay_oracle_comparison.json` plus a not-found classification record.
- Initial log capture was blocked by the permission-review timeout, so the first redacted edge mapping used the source default `ts-station-mysql:3306`. The closure run later captured Station logs and confirmed the deployed non-credential datasource setting as `train-ticket-mysql:3306`.

## Station NetworkChaos delay ladder (2026-08-04)
- Ran bounded success probes at nominal 100ms, 500ms and 2s outbound delay. Median latencies were 216.022ms, 1021.227ms and 4020.903ms respectively; all responses remained HTTP 200 with the seeded UUID.
- The 2s probe used a 60s duration and 3 warm-ups plus 5 formal requests to keep the full window inside one injection. Injection, recovery and cleanup were confirmed.
- No timeout occurred, but 4.02s approached the 5s client observation budget. Added `generated_station_network_delay_boundary_comparison.json` and upgraded the NetworkChaos Station card to v3.
- Stopped further delay escalation. The 5s runner timeout is recorded as a technical boundary only; an operator-defined SLO or runtime trace is required before another boundary injection.
- Finalized `station_network_delay_line_report.json` and `.md`, added the line-level classification record, and marked the Station NetworkChaos runtime line complete; external SLO/Trace is now an optional production-meaning gate rather than a runtime-loop blocker.

## Station NetworkChaos timeout-boundary closure (2026-08-04)
- Ran one controlled not-found request with nominal 3s outbound delay and a 5s experimental client budget. The client timed out at 5047.049ms after confirmed injection.
- Station logs show controller entry at `13:15:36.350Z` and the post-repository Not Found branch at `13:15:42.414Z`, 6063.895ms after request start and about 1.017s after client timeout.
- Chaos Mesh recovered the selected Pod and the runner confirmed resource deletion. The result is classified as `client_timeout_server_completion_after_delay`, not client-side defense.
- Upgraded `KB-TT-NETWORK-STATION-DELAY-001` to v4 and closed the runtime loop. Targeted non-credential environment inspection confirmed the datasource peer as `train-ticket-mysql:3306`; production SLO meaning and packet-level attribution remain outside the proven evidence.
- Updated the selector with `closed_runtime_boundary_no_reinjection`; the card remains retrievable but mutation generation will no longer treat this line as ready. Two decision regression tests pass.

## Direct Station NetworkChaos replay (2026-08-04)
- Generated `station-network-delay-candidate-r1.yaml` from the real 5s Station NetworkChaos source, bounded to 100ms and 20s; runtime gate passed.
- Replayed the direct `shanghai` success oracle with 3 warm-ups and 10 formal requests. All responses returned HTTP 200 and the seeded UUID.
- Median latency was 216.022ms versus 30.146ms baseline (+185.876ms); p95 was 234.324ms. The nominal 100ms delay therefore produced a larger end-to-end effect.
- Injection, recovery and cleanup were confirmed. Added `KB-TT-NETWORK-STATION-DELAY-001` v1 and a classification-index record. Exact delayed dependency remains unproven because fresh logs/traces were unavailable.

## Direct Station CPU replay (2026-08-04)
- Generated `station-stress-cpu-candidate-r1.yaml` from the real Station StressChaos source and passed the runtime gate: Station Pod Ready, zero restarts, port 12345 present, Chaos Mesh components Ready.
- Replayed the same 1-worker/80%/45s profile with 3 warm-ups excluded and 10 formal direct Station requests. All responses returned HTTP 200 and the seeded UUID.
- Median latency was 43.308ms versus 30.146ms Station baseline (+13.162ms). cgroup deltas were `usage_usec +21800650`, `nr_throttled +406`, `throttled_usec +16272410`; post-recovery deltas were zero.
- Added `KB-TT-STRESS-STATION-CPU-001` v1, the unified direct Station result and a classification-index record. The result is intentionally separate from the Basic-upstream card because injection location changes the test-node-centered graph.

## Basic CPU concurrent replay (2026-08-04)
- Added optional `--request-concurrency` to both chaos runners; default remains sequential (`1`). Formal requests run in bounded concurrent batches; warm-up remains sequential and excluded from classification.
- Health gate passed before injection: Basic Pod Ready, zero restarts, port 15680 present, Chaos Mesh controller/daemon Ready.
- Replayed r1 CPU stress with 3 warm-ups and 12 formal success requests at concurrency 4. All responses returned HTTP 200 with the seeded UUID; median latency was 92.826ms, p95 195.868ms, versus 27.378ms baseline.
- cgroup deltas were `usage_usec +21996936`, `nr_throttled +440`, `throttled_usec +8971772`; post-recovery deltas were zero, and cleanup was confirmed.
- Added `generated_basic_stress_success_concurrent_result.json`, classification/index evidence, and upgraded the Basic CPU card to v5. Static source review confirms no configured Basic application timeout/retry/fallback/circuit-breaker; the 5s runner timeout is only an observation budget.

## Basic CPU strong profile (2026-08-04)
- Generated isolated `basic-stress-cpu-candidate-r2-strong.yaml` with 4 workers, 100% load and 60s duration; target and oracle remained unchanged.
- Used the same fixed controls: 3 warm-ups excluded from classification, 10 formal requests, 0.5s interval, 5s timeout, and 35 cgroup samples. Injection and recovery gates passed.
- All formal requests returned HTTP 200 with the seeded station UUID. Median latency was 101.404ms versus 27.378ms baseline (+74.026ms); classifier result: `response_preserved_latency_degradation`.
- cgroup active-window deltas were `usage_usec +29415432`, `nr_throttled +588`, `throttled_usec +167266489`; post-recovery deltas were zero. Runner confirmed `recoveredCount=1` and resource cleanup.
- Fresh log capture was not completed because the read-only permission review timed out; this is explicitly marked as an evidence boundary. At this intermediate strong-profile step the Basic CPU card was v4; the later concurrency evidence is the current v5 card. Both record partial resilience rather than full defense.

## Controlled Basic CPU oracle repetition (2026-08-04)
- Added warm-up controls to `tools/run_chaos_experiment.py` and `tools/run_stress_with_cgroup.py`; warm-ups are recorded separately and excluded from formal classification.
- Replayed the same one-worker/80%/45s mutation for `shanghai` and `stationName` with 3 warm-up requests, 10 formal requests, 0.5s request interval, 5s timeout and 25 cgroup samples.
- Seeded success: HTTP 200 and the same station UUID for all formal requests; median 32.581ms versus 27.378ms baseline (+5.203ms); cgroup `nr_throttled +434`, `throttled_usec +8107212`.
- Controlled not-found: HTTP 200 with the same `status=0, msg=Not exists` envelope for all formal requests; median 33.864ms versus 24ms baseline (+9.864ms); cgroup `nr_throttled +423`, `throttled_usec +3061704`.
- Both runs reached the real Basic-to-Station path, Basic/Station logs matched 10 formal calls per oracle, `recoveredCount=1`, cleanup was confirmed, and post-recovery cgroup counters did not grow.
- Added `generated_basic_stress_warmup_result.json`, paired warm-up reports, log evidence, classification records, and upgraded `KB-TT-STRESS-BASIC-CPU-001` to v3 at that stage (later v5 after the concurrency replay). The conclusion is bounded downstream resilience with a small latency increase, not proof of timeout/retry/fallback defense.

## Successful station oracle CPU replay (2026-08-04)
- A temporary REST fixture attempt was rejected by the real Station `SecurityConfig` with HTTP 403; no data was created and no database Secret was accessed.
- Added the read-only `tools/capture_http_observation.py` path and used the existing `InitData` station `shanghai` instead. Basic and Station baselines both returned the same real station UUID.
- Replayed the same Basic CPU mutation against `GET /api/v1/basicservice/basic/shanghai`. Ten requests returned HTTP 200 with the UUID; median latency was 26.526ms versus 27.378ms baseline.
- cgroup evidence remained real: `nr_throttled +409`, `throttled_usec +3044249`, with zero post-recovery counter growth. Basic and Station logs confirmed all ten successful downstream calls.
- Added the success result, log evidence and `basic_stress_oracle_comparison.json`; Basic CPU card is now v2 and records both not-found and successful-oracle behavior.

## Basic downstream CPU replay (2026-08-04)
- Generated the `basic-stress-cpu` candidate from the test-node selector report, passed the isolated runtime applicability gate, and replayed it with `run_stress_with_cgroup.py`.
- The request path was `GET /api/v1/basicservice/basic/stationName`; Basic and Station logs confirmed all 10 upstream/downstream executions.
- The 45s one-worker/80% profile produced `nr_throttled +433` and `throttled_usec +8647513`; post-recovery samples added zero throttling. All 10 requests returned HTTP 200 with the controlled `Not exists` envelope; median latency rose from 24ms to 71.457ms.
- Added `KB-TT-STRESS-BASIC-CPU-001` and unified result/log evidence. Re-running the selector now promotes `ts-basic-service` CPU from `needs_runtime_gate` to `ready_candidate_with_runner`.

## Selector-generated CPU replay (2026-08-03)
- Replayed the top selector-generated CPU candidate with `tools/run_stress_with_cgroup.py`. The runner waited for `injectedCount=1`, then captured 25 cgroup-v2 samples, and owned recovery plus cleanup.
- CPU candidate evidence: `nr_throttled` increased by 432 and `throttled_usec` by 15,496,840 microseconds during the active window; post-recovery samples added zero throttling. Eight read-only order requests returned HTTP 200 and the Pod had zero restarts.
- Added `artifacts/train-ticket/runtime/generated_stress_result.json` and `generated_stress_classification.json`; the CPU card is now v4 and the knowledge index reports `validated_runtime_selector_pipeline`.
- Bounded conclusion: measurable CPU throttling with the exercised response contract preserved. This is not a universal defense claim for all order workflows or the original five-minute profile.
- Re-ran the selector after the card update: `stress_cpu` now retrieves the v4 CPU card and the selector-generated replay as the exact-service/test-node runtime match; other services remain `needs_runtime_gate`.

## Latest NetworkChaos runtime evidence (2026-08-03)
- Reused the raw `NetworkChaos` delay motif only after redirecting it to a reachable test-node-centered path: `app=ts-basic-service` in isolated namespace `train-ticket-lab`, 500ms, 45s, direction `to`.
- Applicability gate passed: CRD and Chaos Mesh components ready, selector matched `ts-basic-service-b974d68cb-cmvpw`, target port 15680 existed, and the mutation name was available before apply.
- Runtime trace confirmed `BasicController -> BasicServiceImpl -> ts-station-service -> StationController`; the original `ts-order-service -> ts-station-service` candidate remains a separate static-only/deferred card because its production call is commented out.
- Twenty requests during the active window stayed HTTP 200 with the same response envelope. Repeated delayed samples were 525-532ms versus 20-57ms baseline; recovered samples returned to 24-32ms.
- Chaos Mesh reported selected=true, injectedCount=1, recoveredCount=1 and AllRecovered=true. The Pod stayed Ready with zero restarts. The resource and temporary port-forward were deleted after the run.
- Result classification is `functional_response_preserved_with_latency_degradation`: the experiment proves a bounded response contract under delay, but does not prove timeout, retry, fallback, circuit-breaker or SLO protection.
- Added `artifacts/train-ticket/runtime/network_basic_station_result.json` and the independent card `artifacts/train-ticket/knowledge_base/KB-TT-NETWORK-BASIC-STATION-001.*`; the knowledge-base index now contains 4 cards and validates with 0 errors and 0 warnings.
- A follow-up 5s profile was executed atomically after waiting for `injectedCount=1`. The 10-second client timed out at 10041ms, while Basic and Station logs showed the downstream handler and normal business response around 10 seconds after request start. Evidence is in `artifacts/train-ticket/runtime/network_basic_station_5s_result.json`.
- A post-cleanup read-only request returned HTTP 200 in 76ms with the baseline response envelope, confirming application-path recovery after the timeout experiment.
- Added `tools/run_chaos_experiment.py`, which reuses the applicability gate and enforces `apply -> injectedCount >= 1 -> request -> recoveredCount >= 1 -> delete`. The runner writes an auditable report and does not convert HTTP 200 into a defense conclusion.
- Runner smoke report `artifacts/train-ticket/runtime/runner_network_smoke.json`: two real requests returned HTTP 200 at 270.420ms and 122.801ms during a 100ms injected delay; injection and recovery were confirmed and the resource was absent after cleanup.
- Runner blocked smoke report `artifacts/train-ticket/runtime/runner_http_blocked.json`: HTTPChaos was rejected before apply because the ebtables prerequisite is missing.
- Added `tools/classify_runtime_result.py` to normalize runner and legacy runtime artifacts. It classifies platform blocking, non-injection, response preservation with latency degradation, client timeout, recovery and cleanup without asserting a defense claim. The Basic->Station card is now version 2 with automated classification evidence.
- Added `artifacts/train-ticket/runtime/classification_index.json`, a retrieval index spanning the HTTP, StressChaos and NetworkChaos runtime evidence states.
- Added `tools/select_chaos_candidates.py`; it joins the 54 test-node-centered slices with the four knowledge cards and runtime classifications, then emits ranked mutation constraints without applying YAML. Current reports correctly rank Basic Network and Order CPU as runner-ready, and mark Order HTTP as platform-blocked.
- Added `artifacts/train-ticket/runtime/candidate_selection_summary.md` for the current LLM retrieval decisions and safety contract.
- Added `tools/generate_candidate_mutations.py`; it preserves the parent hash, rewrites the namespace/selector, bounds duration and intensity, and never applies YAML itself.
- Replayed the top selector-generated Network candidate end to end. Evidence is in `generated_network_runner_result.json` and `generated_network_classification.json`; the Basic->Station card is now version 3 with selector-pipeline evidence.
- Two earlier 5s attempts were rejected as invalid effect evidence because the request ran before injection or after the resource had already recovered. This added an execution rule to the card: apply completion is not injection completion; wait for the controller status before measuring.

## Live runtime evidence (2026-08-03)
- Docker Desktop Kubernetes and Chaos Mesh 2.8.3 are verified. All live resources are isolated in namespace `train-ticket-lab`; the existing `default` and `chaos-testing` workloads were not used as targets.
- The original Train Ticket MySQL Helm chart was not used because its Xenon `postStart` hook stayed in `PodInitializing`. The lab runtime uses a MariaDB-compatible substitution with the same application protocol, plus standalone Nacos and RabbitMQ.
- Real `codewisdom/ts-order-service:1.0.1` and `codewisdom/ts-station-service:1.0.1` images started successfully after exposing Nacos 9848/9849 and lowering Nacos JVM memory for Docker Desktop.
- Baseline endpoint: `GET /api/v1/orderservice/order/00000000-0000-0000-0000-000000000000` returned HTTP 200 with `Order Not Found` three times.
- HTTPChaos experiment: the Pod was selected but `injectedCount=0`; Chaos Daemon reported missing WSL2 `ebtables`. This is an instrumentation prerequisite failure, not a defense result. Evidence is in `artifacts/train-ticket/runtime/http_order_404_result.json`.
- StressChaos experiment: one worker at 80 percent for 45 seconds injected successfully (`injectedCount=1`) and recovered (`recoveredCount=1`, `AllRecovered=true`). The Pod stayed Ready with zero restarts and the read-only request stayed HTTP 200. Evidence is in `artifacts/train-ticket/runtime/stress_order_cpu_result.json`.
- Knowledge cards were updated and validated: 4 cards, 0 errors, 0 warnings.
- Added `tools/runtime_applicability_gate.py`; it reports HTTPChaos as `blocked` before apply and StressChaos as `ready_for_injection` by checking CRD, controller/daemon, selector, Pod readiness, port and injector prerequisites.
- Added `tools/capture_cgroup_cpu.py`; cgroup-v2 counters provide a metrics-server-independent CPU/throttling observation path.
- Strong short CPU profile (4 workers, 100 percent, 60 seconds) injected and recovered successfully. cgroup deltas were `nr_throttled=593` and `throttled_usec=183615850`; 25 read-only requests stayed HTTP 200 and the Pod had zero restarts.

## Latest stress-card update
- 已建立第三张卡片：`raw_yaml/StressChaos/0885ce87187120d724117939.yaml` 的 `order-stress-cpu`，确认 `workers=4`、`load=100`、`duration=5m`、`mode=one` 与 `ts-order-service` 目标一致。
- 已将 Deployment 的 CPU request/limit（50m/200m）和 TCP readiness probe 纳入测试节点中心图；资源压力、业务 SLO、探针行为和恢复状态全部保持为运行时待验证。
- 当前知识库覆盖三类节点：HTTP response replacement、Network delay、CPU stress；每张卡片都保存静态证据、可达性状态、测试价值假设、结果判定规则和下一步证据。

## Knowledge-base quality gate
- 新增 `tools/validate_knowledge_base.py`，校验索引与卡片 ID/路径一致性、测试节点中心图、四层有效性字段、后续证据列表，并扫描疑似敏感值。
- 已运行校验：4 张卡片、0 errors、0 warnings，报告写入 `artifacts/train-ticket/knowledge_base/validation_report.json`。

## Latest HTTP response-card update
- 已建立第二张对照卡片：`raw_yaml/HTTPChaos/a554bb3751e7b1c20eead94c.yaml` 的 `order-http-code`，确认 `app=ts-order-service`、端口 `12031`、`target=Response`、`replace.code=404`、`path=*` 与真实应用/Deployment/Controller 路由一致。
- HTTP 响应卡片的核心经验：必须把“业务处理是否完成”和“客户端收到什么 HTTP 状态”拆成两个结果节点；只看到 404 不能直接判定应用失败或系统防御成功。
- 已生成 `artifacts/train-ticket/knowledge_base/KB-TT-HTTP-ORDER-RESPONSE-404-001.json`、对应 Markdown，并加入知识库索引。该样本可在隔离环境完成基线后进入候选注入队列；当前运行证据仍为 `pending`。

## Latest evidence update
- 已核对 `raw_yaml/NetworkChaos/661b0ac8ed245799ce7b5069.yaml`：`NetworkChaos.delay`、`namespace=train-ticket`、`app=ts-order-service`、`direction=to`、`mode=one`、`latency=5s`、`duration=5m`。
- 已核对真实业务入口：`OrderController.java:66-70` 的 `/api/v1/orderservice/order/refresh` 调用 `queryOrdersForRefresh`。
- 已核对候选下游调用：`OrderServiceImpl.java:208-219` 使用 `RestTemplate.exchange` 调用 `ts-station-service`；但生产调用点 `OrderServiceImpl.java:200` 被注释，当前刷新业务路径不证明可达。
- 已生成知识库卡片：`artifacts/train-ticket/knowledge_base/KB-TT-NETWORK-ORDER-STATION-001.json`、对应 Markdown 和 `index.json`。
- 当前判定：YAML/目标/候选函数静态存在；业务可达性未成立；防御与恢复只能保持 `pending`；该注入应 `defer`，不能作为已覆盖下游故障的样本。

## 2026-08-03
- 恢复被中断的 YAML 混沌测试规划任务。
- 创建 `task_plan.md`、`findings.md`、`progress.md`。
- 完成只读扫描：仓库无源码/测试入口，存在 1,935 个 YAML，按 Chaos Mesh 资源分类；记录了 API 版本、字段共性、占位符和 32 个结构化解析异常样本。
- 计划调整：先做资产清单与四层有效性分级，再反查外部真实项目加载入口；无入口证据的 YAML 只能进入“待验证”队列。
- 已将详细执行表写入 `task_plan.md`：阶段 0-8、YAML 测试点矩阵、CFG/DFG 节点/边规范、注入结果分类、知识库卡片字段和里程碑顺序。
- 当前停点：阶段 0 仍为 `in_progress`（尚未生成逐文件 inventory/fingerprint）；等待用户确认计划范围，以及提供/指定真实项目源码、CRD/控制器版本和可用隔离环境；在此之前不执行 YAML 注入。
- 完成 GitHub 候选调研：核对 Online Boutique、OpenTelemetry Demo、Train Ticket、.NET eShop、DeathStarBench、Sock Shop、Istio、Chaos Mesh 的星标快照、归档状态、README、部署入口和观测能力。
- 结论：Online Boutique 适合作为高热度标准基准；FudanSELab/train-ticket 与当前 `raw_yaml` 中 54 个 `train-ticket` namespace 直接对应，适合作为本项目主线；OpenTelemetry Demo 适合优先验证观测证据链。
- 将原阶段表扩展为 17 个原子步骤，增加了项目选择、环境复现、四层有效性、CFG/DFG、注入审批、结果归因、知识库审核和回归治理的进入条件。
- 用户已选择 `FudanSELab/train-ticket` 作为首个真实被测项目；下一步只做仓库接入、版本固定和部署入口核对，不启动混沌注入。
- 已浅克隆仓库并固定 `master` commit `313886e99befb94be6cd45f085c98e0019f59829`；核对 README/Makefile/部署脚本/观测与 Istio fault-injection 入口。
- 基线风险已记录：默认 namespace `default`、监控可能集群范围、部署脚本存在硬编码凭据、Helm 模板不能直接当原始 YAML 解析；当前仍禁止直接 `make deploy` 或执行注入。
- 已完成 54 个 `train-ticket` YAML 与真实 Deployment labels 的静态映射：HTTPChaos 30、NetworkChaos 15、StressChaos 8、Workflow 1；识别出 namespace `mode: all` Workflow 为高爆炸半径候选。
- 根据用户澄清，计划已重构为“测试节点中心”：每类测试单独提取局部影响子图，只分析该测试涉及的函数、调用、数据流、控制流、观测和恢复路径；全局项目图仅作为索引，不作为主要测试对象。
- 已生成首批机器产物：`artifacts/train-ticket/yaml_inventory.csv`、`test_node_catalog.json`、`train_ticket_test_slices.json`、`summary.json` 和人读摘要 `README.md`。
- 结果：1,935 个 YAML 均为可解析顶层 mapping；34 个文件有语义形状问题。全量高频节点为 `stress_cpu` 230、`pod_pod-kill` 220、`network_delay` 213、`stress_memory` 142、`network_partition` 99；Train Ticket 子集为 HTTP response replacement 15、network delay 15、HTTP delay 14、CPU stress 8、HTTP abort 1、Workflow 1。
- 静态局部切片已覆盖 54 个 Train Ticket 样本；selector -> Deployment/Service 为静态证据，函数候选为 source scan 结果，运行时可达性/Trace 仍未验证。
- 验证摘要：53/54 个样本命中 Deployment/Service，49/54 个样本找到生产函数候选；Workflow 单独进入模板展开队列。
- 已完成局部子图细化：54 个样本分为 HTTP 30、Network 15、Stress 8、Workflow 1；提取 14 个服务模块、1,479 个静态函数候选和 910 条函数调用边；Workflow 展开 4 个叶子节点，namespace 级 mode=all 去重后有 65 个 app 候选。
- 新产物：`artifacts/train-ticket/train_ticket_test_slices_refined.json`、`refined_summary.json`、`refined_report.md`。静态函数和调用边仍待运行 Trace 证实，下一步先做单服务基线，不执行 Workflow 注入。
- 已生成跨服务静态图：`train_ticket_service_graph.json`、`train_ticket_test_slices_graph.json`、`service_graph_summary.json`、`service_graph_report.md`；46 个服务模块、172 条候选调用边，`ts-order-service -> ts-station-service` 已定位到生产源码 `OrderServiceImpl.java:211`。
- 当前证据链分三层：selector->Deployment（静态清单）、Deployment->函数/下游服务（静态源码）、函数->真实请求（运行 Trace 待补）。只有第三层完成后才进入注入决策。
- 运行前置检查：Kubectl v1.36.1 和 Docker CLI 29.6.1 存在；Helm/Maven/Kind/Minikube 缺失；无 kubectl context，Docker server 无响应。因此本轮不部署、不生成运行时结论。
## DeepSeek audit remediation (2026-08-05)

- Verified the supplied audit against source and artifacts. Findings 1-5 and 7-12 were confirmed; finding 6 was partly a false positive because fuzzy matching is a deliberate compatibility path for legacy records without `target_service`.
- `runtime_applicability_gate.py` now enforces `train-ticket-lab`, `mode: one`, selector namespace equality, and HTTPChaos positive tproxy/ebtables evidence. Unknown HTTP prerequisites fail closed.
- `run_chaos_experiment.py` and `classify_runtime_result.py` share one classifier and one exit-code policy. Injection-unconfirmed runs delete immediately instead of waiting through the recovery budget.
- `run_stress_with_cgroup.py` now derives the cgroup selector from the mutation, rejects pre-existing mutation names, computes a recovery-aware process budget, and performs verified parent cleanup after runner termination. Multi-Ready-Pod cgroup selection is rejected.
- Candidate ranking is deterministic, blast-radius metadata is present in every Train Ticket slice, and the evidence index now matches every referenced classification report. The Station line report has an explicit top-level classification.
- Knowledge-base validation now emits per-card checks. HTTP platform-blocked vocabulary is canonicalized as `blocked_by_platform_prerequisite`.
- Initialized the workspace Git repository with baseline commit `3836b8a` and an ignore policy that keeps the pinned nested source checkout and generated logs out of workspace history.

## 2026-08-05 第一项目收尾（阶段 A/B/C）
- 文档/状态收尾：task_plan 阶段表更新（4/7/8/9 -> complete，10 -> in_progress）；新增 54 样本验证状态矩阵 `runtime/coverage_matrix.{csv,md}`；定义 P0 回归集 `runtime/p0_regression_set.md`（7 项，含命令与变更检测规则）。
- 工具链审计缺口关闭（commit `029e454`）：HTTPChaos fail-closed 正则不再被否定句穿透（`not supported`/`unavailable` 实测 blocked）；`yaml.YAMLError` 三处处理（gate/runner/stress，畸形 YAML 产出 blocked 报告而非崩溃）；`resource_exists` 仅把显式 NotFound 当不存在、RBAC/超时抛异常并触发兜底删除；`invalid_request_configuration` 退出码 2；runner 强制分类与共享分类器标签通过 `classification_note` 调和；`runtime_matches`/`mutation_constraints` 输出改用 slice 自身 primary test node；新增 `primary_test_node` 跳过通用 `selector` 节点（修复 basic-stress-cpu 匹配 5 条运行时记录）；重新生成 refined/graph slices 使 blast_radius_flag 覆盖默认输入（53/54，零内容漂移）；validator 根锚定 + checks_ran；WARMUP-001 分类对齐。回归测试 12 -> 19，全绿。
- 覆盖矩阵结论：54 样本中 5 条实验线 verified（Station 延迟阶梯/边界、Basic/Order/Station CPU、Basic->Station 网络）、30 HTTPChaos 平台阻断、1 Order->Station 不可达（项目缺陷）、1 Workflow 静态高爆炸半径、17 个未运行（12 network_delay + 5 stress_cpu，跨服务扩展空间）。
- 薄弱点清单：见 `reporting/train-ticket/issues/`（Order refresh 禁用下游调用草稿 + Station 无超时/熔断防御草稿）。
- 统计重复实验（2026-08-05）：Station 延迟 100ms x3（中位 216.2-228.6ms，均值 224.2ms，95% CI [206.9,241.6]）、500ms x3（1019.5-1023.3ms，均值 1021.5ms，CI [1016.8,1026.2]，重复性极高）、Basic CPU r1 x3（40.9-63.6ms，均值 51.4ms，CI [23.1,79.8]，方差较大属预期——CPU throttling 效应）。全部 HTTP 200、注入/恢复/清理确认。产物：`runtime/stat_repeat/experiment_matrix.csv` + `summary.json` + `batch.log`。修复了 runner 缺失 `import yaml` 的回归（commit 内含，新增静态回归测试）。
- 薄弱点报告：`reporting/train-ticket/issues/README.md`（清单）+ `2026-08-05_disabled-downstream-call-in-refresh.md`（静态）+ `2026-08-05_station-no-timeout-defense.md`（运行时证据，含统计重复数据）。两份均为 DRAFT，待人工审核后提交。

## Online Boutique deep experiments + environment expansion (2026-08-05/06)
- **Second project (microservices-demo @ 9a4616e7) full loop completed**: static resilience mapping -> isolated lab deploy (online-boutique-lab) -> 4 baseline experiments (payment delay/loss, productcatalog kill, ad degradation) -> statistical repetition -> deeper fault semantics -> 6 knowledge cards.
- **Cross-environment reproduction (kind)**: same NetworkChaos payment 2s delay reproduces +2000ms and probe-SIGKILL identically on kind vs Docker Desktop; core findings are cross-environment facts, not environment accidents.
- **HTTPChaos unlock investigation (path 2)**: created chaos-kind cluster (kind v0.32.0) + Chaos Mesh 2.8.3; conclusive finding - HTTPChaos tproxy needs legacy ebtables broute/nat tables absent from WSL2 kernel (6.18.33.2-microsoft-standard) shared by kind and Docker Desktop; cluster type swap does not unlock it; need non-WSL2 env or custom kernel.
- **Statistical repetition (n=9)**: payment 2s delay -> 2021.5±3.1ms median; full propagation is a statistical fact. Loss (n=5): PlaceOrder hangs 10002-10010ms to client 10s deadline every time - infinite-hang-until-caller-boundary is statistical.
- **3-downstream semantics matrix**: payment fatal (2021ms delay / hang-10s loss), shipping DOUBLE fatal (4021.5ms = 2 calls GetQuote+ShipOrder / hang-10s loss), email degraded (2021ms delay / 27ms graceful loss via log.Warnf). ALL propagate delay (no timeout is common flaw).
- **Probe-restart race discovered**: 1s liveness probe under 2s+ delay triggers SIGKILL after ~35s (failureThreshold 3 x period 10s); threshold = delay > timeoutSeconds. Continuous sampling (t=0..85s) showed restart ESCAPES injection (new container no delay) - chaos binds to old netns.
- **Re-injection test (decisive)**: after restart escape (21ms), re-injecting restores 2021ms immediately -> system has NO self-healing; "auto-recovery" is a lucky side-effect of probe restart with ~9s business-failure window cost.
- **Multi-fault**: payment+email simultaneous 2s delay -> 4016.2ms (linear sum 17+2020+2020); sequential downstream calls sum delays, no concurrency/dedup/degradation.
- **Knowledge base**: 6 OB cards created (payment-delay, productcatalog-failure, email-failure, probe-restart-race, shipping-failure, multi-fault), validate_knowledge_base 0 errors; train-ticket remains 7 cards.
- **Reporting infrastructure built**: issue_template.md, tracking.md, project_intake.md, projects_matrix.md, package_report_evidence.py (SHA-256 manifest), 23 unit tests pass.
- **Issue status**: train-ticket draft (disabled downstream call) saved as Word to Desktop + md in reporting/train-ticket/issues/ - pending user/supervisor decision. Online Boutique findings recorded but NOT submitted as issues - pending decision.
- **Environment assets**: chaos-kind cluster + Chaos Mesh 2.8.3 + 8 OB services preserved; local registry (host.docker.internal:5000) for image loading; Docker Desktop cluster untouched.

## Project 3: OpenTelemetry Demo (2026-08-06)
- **Onboarding**: pinned open-telemetry/opentelemetry-demo @ 2e72d8bc; static mapping found checkout no-timeout pattern REPLICATES 3rd project (gRPC NewClient no deadline, HTTP &http.Client{} no Timeout, shipping fatal via HTTP codes.Unavailable, email degraded logger.Warn); native fault flags (paymentUnreachable/kafkaQueueProblems) discovered.
- **Deploy (kind, otel-demo-lab)**: 10 services via manual manifest (no K8s manifests in repo - compose only). Solved 4 deploy issues: .NET cart listens 8080 (not 7070), postgres init.sql CREATE conflict (lite version + astronomy_user), shipping (Rust) flagd panic -> flagd sidecar, flagd v0.16 dynamic default port -> --port 8013. Found source bug: checkout quoteShipping error says "email service" but is shipping (main.go:498 copy-paste).
- **Baseline**: PlaceOrder ~3.1s (OTel SDK overhead + HTTP chain + multi-language).
- **Injection**: payment 2s delay -> +1690/+2075/+1485ms (full propagation); 100% loss -> hang 10007.4ms DEADLINE_EXCEEDED. KEY: no-timeout + full-propagation + infinite-hang now replicated across 3 projects (train-ticket/OB/OTel-Demo).
- **Observability gap detection (deep)**: deployed Jaeger all-in-one (OTLP direct from SDKs, collector Docker Hub 429-limited). Injected 2s payment delay -> Jaeger trace PaymentService/Charge span 4462ms + HttpRequestException event (baseline 513ms) - injected fault FULLY captured, NO observability gap, but NO auto-alert (manual Jaeger query needed).
- **email degradation (deep)**: 2s delay -> 5410ms propagation; 100% loss -> hang 10008.8ms vs OB's 27.4ms (gRPC fast-fail vs HTTP hang) - degradation only affects pass/fail, not latency/挂起 propagation.
- **Knowledge base**: 2 OTel cards (including `KB-OTEL-CHECKOUT-PAYMENT-FAILURE-001`); current archive totals 17 cards across 3 projects (Train Ticket 7, Online Boutique 8, OpenTelemetry Demo 2), with all three validators returning `valid: true`.
- **Environment**: jaeger + 10 services preserved in otel-demo-lab; chaos-kind cluster shared with OB experiments.

## LLM knowledge-base ablation protocol (2026-08-10)
- Added `artifacts/experiments/llm_knowledge_ablation_protocol_v1.md` as a draft DeepSeek execution handoff.
- The protocol isolates `LLM-blind`, `LLM-generic`, and `LLM-full-pre` under the same model, prompt, candidate pool, seed, runner, and oracle conditions.
- It requires pre-experiment snapshot provenance, leakage scans, independent full-pool oracle evaluation, project-clustered statistics, cost accounting, and human review gates before formal claims.
- **2026-08-10 project archive pass started**: confirmed existing UTF-8 planning files, a deliberately dirty worktree with ongoing experiment artifacts, and no top-level README. Planned local-only documentation for paper preparation, comparison experiments, knowledge-base reuse, and a user-gated GitHub private-repository handoff. No remote or upload action authorized.

## Workspace archive cleanup (2026-08-11)
- Added `docs/ARCHIVE_CLEANUP.md` to distinguish retained evidence from disposable workspace instructions.
- Retained formal ablation prompts under `artifacts/experiments/knowledge_ablation_prompts/` because they are frozen experiment inputs.
- Removed 9 temporary `.planning/**/DEEPSEEK_*_PROMPT.md` files and the generated `.pytest-tmp-final-all/` directory; no experiment data or historical reports were removed.
- `.pytest_cache/` was left untouched because Windows denied access; GitHub remote/upload remains disabled pending explicit approval.

## Paper-preparation review (2026-08-11)
- Re-read the repository-level archive, four case studies, TestNode evidence chain, knowledge-base guide, experiment catalog, and master archive index.
- Added `analysis_outputs/SUMMARY.md`, `analysis_outputs/RISKS.md`, and `analysis_outputs/status.json`.
- Updated project docs to freeze the current paper boundary: knowledge-base ablation and final method head-to-head comparison are preserved but parked as `parked_future_work`.
- Regression suite remains green at 249 passed; no runtime experiment or GitHub upload was started.
# Open-discovery compiler progress (2026-08-11)

- 2026-08-12 continuation: inspected the four-session handoff. P09 exact restored source is present in `sources_restored/P09` (13,455 observed files; required runtime files and Compose SHA verified). Added source-restore and profile-preflight manifests. Profile generation remains fail-closed because WSL-native Docker has no verified Dify/Postgres/Busybox core image digests; no placeholder digest, cluster apply, or DeepSeek call was used.
- Fixed `tools/analyze_chaosatlas_statistics.py`: discovery validity is response-level, and runtime `valid_runs` no longer enters executable-hypothesis rates. Regenerated `analysis_outputs/chaosatlas_statistics/`; focused statistics tests pass and the full suite remains green at 286 tests.
- Completed read-only official ChaosEater audit at commit `47c4e44bc897014d22fa1cb3079a0e7d28011fbc`: native path requires a zipped Skaffold project with root `skaffold.yaml` and referenced Kubernetes manifests; P02 has no native Skaffold input, so its adapter result remains supplementary only. Evidence: `artifacts/experiments/chaosatlas_10_projects/chaoseater_official_audit.json`.
- Full regression after handoff changes: 290 passed, 5 subtests passed. No DeepSeek request, Docker Desktop action, or cluster mutation occurred.
- Acceptance pass (2026-08-12): all four-session work packages reviewed. P09 remains blocked at immutable image provenance; P03/P06 restoration remains incomplete; official ChaosEater audit and project-clustered statistics are present. Added `artifacts/experiments/chaosatlas_10_projects/ACCEPTANCE_REPORT_2026-08-12.md`. Corrected P09 restore manifest to use the verified Git tree SHA from the restoration manifest. No experiment inputs or runtime results were changed.
- Runtime-gate consistency pass (2026-08-12): registry manifest queries through the approved external path timed out, and the local proxy HTTPS path closed the connection; no image tags or guessed digests were accepted. Corrected the gate index and consent report to reflect the actual state: P02 `execution_ready=1` but `method_result_eligible=0`; 8 projects environment-blocked and 1 out-of-domain. No DeepSeek key read or request sent.

- P02 retry on 2026-08-12 crossed the registry gate using a WSL-only relay (`172.18.0.1:7890 -> 172.20.96.1:7890`); all required images eventually pulled. Runtime remained blocked because the preserved kind cluster's kube-proxy is configured for IPVS but its service table stayed empty under the WSL kernel's incomplete iptables/filter support, while CoreDNS readiness stayed 503. The API gateway consequently could not resolve `config-server`. P02 was cleaned up, the relay stopped, and no baseline or mutation was run. Evidence: `artifacts/experiments/chaosatlas_10_projects/runtime_profiles/P02/pilot_blocked_2026-08-12.json`. This is an environment gate, not a method result; DeepSeek was not read or called.

- Retried the authorized P02 runtime smoke deployment after the user enabled a proxy. Windows inspection showed `KumiryoCore.exe` listening only on `127.0.0.1:7890`; kind's containerd was configured for `172.18.0.1:7890`, and node-side TCP plus Kubernetes events both showed `connection refused`. All ten digest-pinned workloads remained in `ImagePullBackOff`; no baseline or mutation was run. The isolated `chaosatlas-p02` namespace was deleted successfully. Evidence: `artifacts/experiments/chaosatlas_10_projects/runtime_profiles/P02/pilot_retry_2026-08-11.json`. This is an environment block, not a ChaosAtlas result; next gate is enabling KumiryoCore Allow LAN or an equivalent host-reachable listener.

- Started implementation after confirming the previous four-project runs used pre-registered or pre-generated mutation YAML rather than an open hypothesis-to-YAML path.
- Existing runtime state remains read-only for this turn; no DeepSeek request and no cluster mutation will be performed.
- Added `tools/open_discovery_mutation_compiler.py`: deterministic target resolution, PodChaos/NetworkChaos/StressChaos YAML generation, provenance, and fail-closed upstream/signature/namespace/selector checks.
- Added Pod template labels to the topology IR and 10 focused compiler tests. Focused tests and full suite passed: 10 focused; 278 total plus 5 subtests.
- Formal ten-project execution remains blocked by the existing runtime gate (`0/10 execution_ready`); this turn did not apply any mutation.

## Overnight handoff verification (2026-08-12)

- Rechecked the authorized WSL-native Docker engine: Docker client `29.6.1` reached server `29.1.3`; the preserved `chaos-kind-control-plane` container is up.
- Rechecked the Kubernetes API through the user kubeconfig with read-only commands: node `chaos-kind-control-plane` is `Ready` on Kubernetes `v1.36.1`; Chaos Mesh CRDs remain present.
- The runtime service-network gate is still blocked. `kindnet` exits while synchronizing nftables/iptables because the WSL kernel lacks the required nfqueue and iptables extensions; `kube-proxy` remains configured for `mode: ipvs` and repeatedly fails to create NAT/filter chains and IPVS service state. CoreDNS replicas are `Running` but `0/1` Ready.
- P02's static profile remains `runtime_apply_allowed=false`; no namespace was created in this verification, and no baseline, oracle, ChaosAtlas-KB, ChaosAtlas-noKB, or ChaosEater-adapter run was started. This is an environment block, not a project or method finding.
- DeepSeek credentials were not read and no external request was sent. The stored consent checklist still requires explicit approval of the exact call plan, model settings, token ceiling, retry policy, and monetary ceiling after a project passes runtime gates.
- Offline preparation was revalidated without secrets: open-discovery bundle generation/audit reports `120` files with no LLM call, selection-only preflight reports `36` records and `preflight_passed`, and the focused topology/mutation test set reports `19 passed`.

## P02 runtime gate completion (2026-08-12)

- Recovered the P02 namespace after the WSL proxy relay was unavailable. A temporary relay was used only for bring-up and was stopped after runtime preparation.
- Fixed the public Spring Petclinic config repository at commit `323993ce2519c6d02df63e08bf4458d123d3b611`, mounted it as `p02-config-repo`, and switched Config Server to the native profile. This removed the remote JGit/GitHub request from the experiment runtime path.
- The first two gateway baseline windows were correctly recorded as `baseline_invalid`: API Gateway was not yet listening because Config Server remote fetches timed out. No method or mutation result was derived from them.
- After native config, all 10 P02 Pods became Ready. `customers-service` hit `OOMKilled` at the original 512Mi limit; a bounded 1Gi memory override was applied and the replacement Pod remained stable. This is an environment adjustment, not a project finding.
- Valid baseline: 10 `GET /` samples through localhost port-forward, all HTTP 200 with 3597-byte body; cold sample 287.369ms and steady samples 59.181-77.601ms. Evidence: `artifacts/experiments/chaosatlas_10_projects/runtime_profiles/P02/baseline_gateway_valid_2026-08-12.json`.
- Correct business oracle was verified at `GET /api/gateway/owners/1`, returning HTTP 200 and owner/pets data. `/owners` and `/vets` were invalid paths for this gateway and are not treated as application failures. Evidence: `artifacts/experiments/chaosatlas_10_projects/runtime_profiles/P02/business_oracles_valid_2026-08-12.json`.
- Chaos Mesh controller Pods and PodChaos/NetworkChaos/StressChaos CRDs are present; no Chaos resource was applied. Formal gate record: `artifacts/experiments/chaosatlas_10_projects/runtime_profiles/P02/runtime_gate_2026-08-12.json`.
- DeepSeek key was not read and no DeepSeek request was sent. The next action requires explicit consent for the exact three-arm call plan, model settings, token cap, retry policy, and cost ceiling.

## P02 three-arm selection pilot preparation (2026-08-12)

- Added `tools/run_p02_three_method_selection.py` for the P02 seed-1001 fixed-pool pilot. It shares the frozen 16-candidate order and K=8 across `ChaosAtlas-KB`, `ChaosAtlas-noKB`, and `ChaosEater-adapter`; it records prompt/bundle hashes, redacted raw responses, structured selections, and token ledger rows.
- Added optional `max_output_tokens` support to the shared OpenAI-compatible backend, sent as the API `max_tokens` request field.
- Fixed BOM-safe JSON loading and filtered audit-only knowledge-card fields before prompt construction.
- Offline dry-run passed: KB/noKB prompt hashes differ, candidate pool hash is `8b2bcafc...`, and no forbidden evidence fields are present. Related adapter and selection tests: 20 passed.
- User authorized the P02 three-call pilot with model `deepseek-v4-flash`; no real request has been sent in this entry yet.
- Attempted the authorized runner through the managed external-execution gate; the gate rejected it because the request would transmit project-derived candidate/configuration content to `https://api.deepseek.com/v1` without explicit payload-and-budget approval. The key was not read and zero requests were sent. No workaround will be attempted; await explicit approval of the external data transfer.

## Main experiment priority reset (2026-08-12)

- User clarified that the primary deliverable is the 10-project open-discovery experiment, not the fixed-candidate three-arm selection pilot.
- Frozen priority document: `artifacts/experiments/chaosatlas_10_projects/MAIN_EXPERIMENT_PRIORITY.md`.
- Main arms are `ChaosAtlas-KB-open`, `ChaosAtlas-noKB-open`, and `ChaosEater-official`; `ChaosEater-adapter-open` is supplementary only.
- The P02 fixed-pool selection runner and its three calls are parked until the main track produces project-level results. No DeepSeek key was read and no request was sent.

## Formal knowledge-ablation gate hardening (2026-08-12)

- Added `tools/validate_chaosatlas_experiment.py`, an offline fail-closed gate
  for the 30 open-discovery KB/noKB bundle pairs. It checks shared evidence,
  topology, runtime contract, seed, and schema identity while requiring the KB
  view to be absent from noKB.
- Extended `tools/feedback_protocol.py` with `knowledge_projection()`,
  `validate_ablation_pair()`, and `validate_knowledge_card_boundary()`. Audit
  cards retain runtime evidence, but later-project KB snapshots receive only
  source provenance and a reviewed abstraction; same-project/future-project
  feedback remains rejected.
- Added five focused regression tests covering projection isolation, prompt
  pair identity, review/order gates, and runtime-field rejection. Result:
  `7 passed`; offline input gate: `valid=true`, `checked_ablation_pairs=30`.
- Updated `artifacts/experiments/chaosatlas_10_projects/protocol_v2_open_discovery.md`
  to distinguish the P02 source-context pilot from the formal cross-project
  feedback ablation and to require project-clustered paired statistics.

## Deployment preflight continuation (2026-08-12)

- Audited the next deployment candidates without reading credentials or
  changing the cluster. P01 eShop remains blocked because the frozen commit
  has no Compose/Kubernetes/Dockerfile application deployment and an empty
  topology profile.
- Added `tools/p06_deployment_preflight.py`: P06 Directus has a Dockerfile and
  dependency matrix, but the frozen sparse snapshot lacks `package.json` and
  `pnpm-lock.yaml`; its Compose file contains databases/infra only, not the
  Directus application service. Runtime apply remains false.
- Added `tools/p03_deployment_preflight.py`: P03 Saleor Compose references
  missing `.devcontainer` env files and build inputs (`pyproject.toml`,
  `uv.lock`, `manage.py`) in the frozen snapshot. Runtime apply remains false.
- Added `tools/p09_deployment_preflight.py`: P09 Dify has a full multi-service
  Compose, but requires missing `.env`/`middleware.env`, digest pinning, and a
  reduced profile excluding external/high-blast-radius services and external
  model calls. Runtime apply remains false.
- Added `tools/build_deployment_preflight_index.py` and committed evidence at
  `artifacts/experiments/chaosatlas_10_projects/deployment_preflight_index.json`.
  It records four environment blocks separately from method outcomes; no model
  calls or cluster mutations occurred. Focused preflight tests: `4 passed`.

## Parallel handoff plan (2026-08-12)

- Added `artifacts/experiments/chaosatlas_10_projects/PARALLEL_WORK_PACKAGES.md`.
- The critical path is exact source restoration, then a reduced digest-pinned
  P09 or P03 runtime profile and deterministic oracle. Separate packages cover
  official ChaosEater audit, project-clustered statistics, and user review.
- Parallel sessions must not overwrite frozen evidence, read the DeepSeek key,
  call the model, touch Docker Desktop, or apply runtime mutations before the
  corresponding gate and explicit approval.
- GitHub source restoration (2026-08-12): P09 restored completely in isolated `sources_restored/P09` with commit/tree/file count and required-file checks. P03/P06 commit/tree verified, but full blobs could not be safely restored due partial-clone promisor errors and GitHub archive timeout; marked `blocked_incomplete`. Manifest written at `sources_restored/RESTORATION_MANIFEST.md`. No deployment, cluster mutation, or DeepSeek call.

## P09 digest remediation (2026-08-12)

- Reproduced the registry path through WSL and Windows gateway proxy `172.20.96.1:7890`; Docker Hub manifest access is available from WSL. The dockerd process still has empty proxy fields, so no daemon restart or Docker Desktop action was taken.
- Corrected the digest probe to use a simple WSL script and case-insensitive `Docker-Content-Digest` extraction. Resolved five immutable digests for BusyBox, Postgres, Redis, Dify API, and Dify Web; evidence is in `runtime_profiles/P09/image-digests.json`.
- Generated `minimal-profile.yaml` and `profile_manifest.json`. Offline validation passes namespace-local, forbidden-services, immutable-images, and required-resources checks. The forbidden-service validator now checks identity fields only, avoiding false positives from cleared optional endpoint variable names.
- Kubernetes `kubectl apply --dry-run=server` against `kind-chaos-kind` accepted the Namespace but rejected namespaced documents because the Namespace is not persisted during a multi-document dry-run. Read-only post-check found no namespace or resources. `server-side-dry-run.json` records this limitation; `apply_allowed` remains false.
- Focused regression suite: `10 passed, 1 warning, 5 subtests passed`. The attempted root `tests` path was invalid because this repository has no root `tests` directory.
- Deployment authorization was received, but apply was deliberately not started. The WSL dockerd systemd drop-in is active with the proxy and `127.0.0.1:2375`; all five P09 digest-pinned images were pulled successfully. Restart recovery left the existing kind control-plane container unstable (`layer not mounted`, stale sandbox, and cgroup scope errors), and kubeconfig/API readiness could not be restored reliably. No P09 namespace, Secret, Pod, or Chaos resource was created.
- Non-destructive recovery attempt: disabled the control-plane container restart loop, started the existing `chaos-kind-control-plane`, and waited for kubelet/containerd. The container exited with code 255 again; Docker logs show repeated stale sandbox/layer and cgroup-scope failures during runtime restoration. The cluster is therefore not safe to use for P09 apply. Rebuilding `chaos-kind` is now the recommended next step, pending separate explicit authorization because it removes current cluster runtime objects.

- 2026-08-12 kind rebuild completed: WSL-native Docker remains `29.1.3`, `cgroupfs`, localhost-only. kind v0.32.0's hard-coded `--cgroupns=private` was overridden only during cluster creation by a trap-protected `/usr/bin/docker` wrapper, then the original Docker CLI was restored automatically. `chaos-kind` reached kind's full Ready phase; the control-plane container was confirmed `cgroupns=host`, `running=true`, and stable across a 30-second poll with no restart growth. A fresh kubeconfig was exported to `C:\Users\xiao junyang\.kube\chaos-kind-config` because the existing `config` file was locked. This is runtime recovery evidence only; Chaos Mesh and P09 have not been applied.

## Repository handoff audit (2026-08-12)

- Added repository ignores for machine-local Docker/Kubernetes/proxy state, planning sessions, environment files, and full third-party source snapshots. Restoration manifests remain versioned.
- Replaced the P05 runtime `.env` dependency with a sanitized `.env.example`; the local environment file remains ignored. Removed an accidental 24-byte proxy-mirror scratch file.
- Exact candidate scans found no GitHub PAT, API key, bearer credential, private key, or inline kubeconfig material. Candidate filenames also contain no kubeconfig, private-key, credential, or live environment file.
- The first full pytest run had two setup errors because the global pytest temporary directory was inaccessible. Re-running with a repository-local isolated basetemp passed: `290 passed, 5 subtests passed`.
- Offline experiment validation passed with `valid=true` and `checked_ablation_pairs=30`. P09 profile validation passed all static checks and correctly retained `apply_allowed=false`.
# 2026-08-12 P02 teacher-minikube formal batch

- Validated the teacher smoke injection report and final cluster cleanup.
- Hardened `run_p02_podchaos.py` with cluster identity, experiment identity, global residual-Chaos checks, full namespace stability, and fail-closed injection/recovery/cleanup outcomes.
- Added `run_p02_formal_batch.py`, a plan-first and explicit-execute 15-run orchestrator with per-run gates, method-output separation, rotation, immutable output handling, and stop-on-first-failure behavior.
- Added the teacher execution guide and four focused tests; focused P02 test run passed 7 tests.
- Full regression passed: 297 tests and 5 subtests. Secret-pattern scan found no credential material in the changed implementation, test, or guide files.
- No DeepSeek credential was read, no API request was sent, and this workstation did not mutate a Kubernetes cluster.
- Formal-batch implementation was committed as `c7a434a` and pushed to `remediation/2026-08-09-review`; the pre-existing timestamp-only manifest change remained unstaged.
- Diagnosed the teacher batch stop: injection, UID replacement, and cleanup succeeded, while the first post-recovery port-forward hit the application startup window. Updated the runner to retry tunnel creation within the existing 120-second recovery budget while still requiring the full post-recovery HTTP 200 count.
- Pulled teacher commit `78d0751` with 15/15 R2 reports. Added an offline P02 summarizer and detected three reproducible delayed HTTP-500 carryover events after discovery-server kills.
- Added a formal post-cleanup washout gate: observe at least 60 seconds and require the final 10 business-oracle samples to be consecutive HTTP 200 before the next mutation.
# 2026-08-13 P02 R3 evidence completion

# 2026-08-13 Active method scope reset

- User decision: defer ChaosEater experiments and later unified comparison.
- Active next-project work is limited to `ChaosAtlas-KB-open` (complete method)
  and `ChaosAtlas-noKB-open` (complete-method ablation).
- Historical ChaosEater artifacts are retained but frozen as method-owned audit
  data. They are excluded from active ledgers, mutation selection, current
  project-clustered statistics, and ChaosAtlas knowledge feedback.
- Updated the main priority and open-discovery protocol with mandatory
  contamination controls: byte-identical common inputs, separate method-owned
  outputs, no same-project or future-project feedback, no runtime feedback into
  noKB, residual-Chaos checks, cleanup/washout gates, source/image/topology hash
  checks, and independent oracle evaluation.
- Updated `tools/main_experiment_orchestrator.py` so the default ledger emits
  only the two active arms. ChaosEater requires the explicit
  `--include-chaoseater` flag for a future unified comparison.
- Added `tools/tests/test_main_experiment_orchestrator.py`; focused scope
  regression passes.

# 2026-08-13 Project summary and archive

- Verified the current Sock Shop evidence: `ChaosAtlas-full` and
  `ChaosAtlas-ablation` are completed; `ChaosEater-full` remains
  `environment_blocked`; human review remains pending and the KB was not updated.
- Confirmed the Sock Shop two arms used the same front-end PodKill mutation, so
  the run is descriptive and cannot support a method superiority claim.
- Added `docs/CHAOSATLAS_PROJECT_ARCHIVE_2026-08-13.md` and
  `artifacts/experiments/CHAOSATLAS_ARCHIVE_INDEX_2026-08-13.json`.
- Updated `README.md`, `docs/PROJECT_SUMMARY.md`, and
  `docs/EXPERIMENT_CATALOG.md` to distinguish current two-arm evidence from
  historical ChaosEater comparison material.
- Recorded the next active queue as Online Boutique, OpenTelemetry Demo,
  Train Ticket, and TeaStore; only `ChaosAtlas-full` and `ChaosAtlas-ablation`
  are in scope. Sock Shop remains archived and P08/P03/P06 remain in the frozen
  ten-project ledger.

# 2026-08-13 P08/P09 continuation

# 2026-08-13 Follow-up four-project queue

- Added the offline-only queue manifest at
  `artifacts/experiments/chaosatlas_followup_four_projects_2026-08-13/`.
- The queue contains Online Boutique, OpenTelemetry Demo, Train Ticket, and
  TeaStore, and only `ChaosAtlas-full` plus `ChaosAtlas-ablation`.
- Online Boutique, OpenTelemetry Demo, and Train Ticket have reusable runtime
  assets but require fresh manifests, baselines, and namespace-first dry-runs.
- TeaStore has only static intake evidence in this workspace; exact source
  restoration, profile rendering, bring-up, and baseline gates remain pending.
- No model call, credential read, deployment, or Chaos Mesh mutation occurred.
- Full-suite verification with a repository-local basetemp reached 394 passed and
  4 failures before the P03 test-contract update: two historical hash-drift
  failures and two stale P03 assertions. The P03 assertions are now updated;
  the historical hash drift remains explicitly unresolved.

# 2026-08-13 Archive consistency repair

- Corrected the archive index to record P03/P06 as
  `static_profile_passed_server_dry_run_pending`, matching their `r6` static
  profile and pending authorized-cluster-session evidence.
- Added the missing `status` field to every archive-index follow-up queue entry.
- Hardened `tools/prepare_project_gates.py` so source completeness requires both
  deployment assets and required application files.
- Added a regression test that fails when a required file such as P03
  `manage.py` is missing, then passes after the gate fix.
- Focused archive/gate regression: 18 passed. Contamination audit: 120 bundles
  and 30 KB/noKB pairs valid. Full repository regression: 397 passed and 2
  pre-existing historical knowledge-ablation hash-drift failures; those
  artifacts were not modified.
- Archive remains human-review pending and knowledge-base updates remain false.
- The next active work is offline preparation for Online Boutique, followed by
  OpenTelemetry Demo, Train Ticket, and TeaStore. Runtime mutation remains
  blocked until each project has a fresh manifest, authorized namespace-first
  dry-run, independent oracle baseline, and cleanup/washout contract.

# 2026-08-13 Online Boutique fresh manifest

- Added `tools/prepare_followup_online_boutique.py` with fail-closed offline
  checks for source namespace, loadgenerator exclusion, frontend health probe,
  checkout entrypoint, target namespace rewrite, and no-overwrite output.
- Added four regression tests. The first generated profile exposed a Windows
  text-newline hash mismatch; `online-boutique-r1` is retained as failed
  preparation evidence, and `online-boutique-r2` was regenerated with byte-level
  manifest writes.
- `online-boutique-r2` static gate passed. The recorded manifest SHA-256
  matches the file on disk:
  `c7f24acb22a13a19bf942b59c4227eedc8ea2c70b7feda82088bcf60fe82c38c`.
- The fresh profile contains 11 Deployments in
  `chaosatlas-online-boutique`, excludes `loadgenerator`, and records the
  `AddItem_then_PlaceOrder` plus `frontend /_healthz` oracle contracts.
- Image digest resolution, authorized namespace-first dry-run, baseline
  windows, and runtime injection remain pending. No namespace was created or
  mutated in this step.

# 2026-08-13 P08/P09 source and profile continuation

- 2026-08-14 Git upload preparation: checked branch state and found local
  HEAD `f4242b9` ahead of origin by 5 commits, with many additional tracked
  modifications and untracked experiment outputs.
- Rebuilt the three-project Word report with improved landscape layout,
  table styling, and a UTF-8 Markdown source file:
  `docs/ChaosAtlas_three_project_experiment_report_2026-08-14.docx` and
  `.md`.
- Added `docs/CHAOSATLAS_UPLOAD_PREP_2026-08-14.md` and linked it from
  `docs/ARCHIVE_MAP.md`.
- Added `/.tmp-*/` to `.gitignore` so local verification directories do not
  pollute upload candidates. No `git add .` was used.
- Word report structural QA passed; LibreOffice PNG rendering remains
  unavailable and the Word PDF fallback timed out, so visual render QA is not
  claimed.
- Upload-prep focused regression passed: 118 tests passed with a single
  existing `.pytest_cache` permission warning. Staged sensitive scan passed:
  70 staged files, 0 strict high-risk secret matches; the earlier broad scan
  only flagged `tokens=MAX_OUTPUT_TOKENS` as a code-variable false positive.
- Created local commit `Archive project upload preparation`; branch is now
  ahead of origin by 6 commits. Push was not executed.

- Restored P09 commit `cd0e88c680dec24dcd423b880302104f13d28462` into the new
  ignored path `sources_restored_r2/P09`; tree SHA `f0344ffb...91aca9`, 13,455
  Git files, and all required deployment files verified.
- Generated isolated `runtime_profiles/P09-r2` from the restored source using
  five existing immutable image digests. Profile validation and the local
  deterministic mock oracle both passed; Compose SHA matched the manifest and
  `runtime_apply_allowed` remains false.
- Added an explicit-path P09 profile validator and retained the old validator
  entry point as a compatibility wrapper, so new profile reports do not
  overwrite historical evidence.
- Restored P08 commit `107634b7e3229bb69d53674cb9ebc67bc1ed02a8` into the new
  ignored path `sources_restored_r2/P08`; tree SHA
  `8942eb9ca4169c8eab7434b8066b5c1718cf1206`, 13,540 Git files, and Docker/
  Helm deployment assets verified.
- P08 static gate remains blocked: its Compose has one `appsmith` service with
  mutable `appsmith-ce:release`, no healthcheck, no resource limits, and no
  deterministic runtime oracle; no namespace or workload was created.
- No DeepSeek/GitHub credential was read, no external model call was made, and
  no Kubernetes mutation was performed.

- Rechecked the teacher Minikube context: `chaosatlas-p02` remained healthy and
  `kubectl get podchaos,networkchaos,stresschaos -A` returned no resources.
- P08 remains blocked before runtime: its manifest is marked
  `pending_resource_pilot`, estimates a very-high resource footprint, and the
  workspace has no restored P08 source tree or runtime profile.
- P09's historical restoration manifest claims a complete `sources_restored/P09`
  tree, but that directory is absent in the current workspace. No source or
  image provenance was guessed, and no namespace or workload was applied.
- Fixed `tools/p09_deployment_preflight.py` to use a verified restored source
  only when present and to emit `source_missing:docker/docker-compose.yaml`
  fail-closed when neither source tree is available. Added regression coverage.
- P08/P09 offline regression: 26 tests passed. No DeepSeek credential, GitHub
  token, external model call, Docker/Minikube repair, or runtime mutation was
  performed.

- Added per-run diagnostic sidecars for five scoped service logs, namespace events, and Zipkin traces, including status, return code, path, size, SHA-256, and explicit unavailable/empty states.
- Enabled diagnostic capture by default in the formal batch and froze all washout/diagnostic parameters in the batch manifest.
- Extended the offline summarizer to attribute R3 delayed failures to the same run's washout, require failure-free baselines and stable washouts for a clean sequence, and keep identical-YAML method claims ineligible.
- Added a pending human review pack that never updates the KB automatically.
- Targeted P02 tests passed: 15 tests before the final protocol-manifest assertion was added.
- The first final-suite run found one incorrect test expectation for repository-relative paths; the implementation correctly emitted a relative path, so the assertion was corrected before rerunning.
- Final regression passed: 309 tests and 5 subtests. R2 compatibility and the pending-review/no-KB-write boundary were checked separately and passed.
- Sensitive-pattern scan found no credential material in the intended P02 R3 change set.
- Committed the P02 R3 evidence chain as `727c9a5` and pushed it to `remediation/2026-08-09-review`; the pre-existing selection-only manifest timestamp change remained unstaged.

# 2026-08-13 P09 two-arm runtime continuation

- Rechecked P09 on teacher Minikube: context `minikube`, namespace
  `chaosatlas-p09` healthy, and the global
  `podchaos,networkchaos,stresschaos` audit returned no resources.
- Audited the open-discovery boundary: only `seed-1001` and `seed-1002`
  ChaosAtlas KB/noKB bundles are eligible; all ChaosEater directories and the
  truncated `seed-1003` noKB result remain excluded.
- Materialized the first fresh P09 two-arm input under
  `runtime_results/P09/teacher-minikube-two-arm-r2`; five mutations per active
  arm compiled and non-profile targets were fail-closed. Mutation hashes
  matched provenance and all ten server-side dry-runs passed.
- Tightened the P09 residual audit to use a global read-only `kubectl get ... -A`
  query and added regression coverage.
- The first full-arm runtime attempt failed before Kubernetes import with
  `ModuleNotFoundError: tools` because the runner was invoked as a direct
  script. No report was written, no mutation was applied, P09 remained healthy,
  and the global Chaos audit stayed empty.
- Added direct-script invocation coverage and fixed the runner to bootstrap the
  repository import path. Focused P09 regression now passes (`33 passed`) using
  a repository-local pytest basetemp because the default Windows pytest temp
  directory is inaccessible.
- The r2 directory is intentionally retained as failed-attempt evidence and
  will not be overwritten. The next runtime attempt uses a new
  `teacher-minikube-two-arm-r3` directory.
- The first r3 runtime invocation also stopped before Kubernetes mutation:
  `run_p09_chaos.py` does not accept `--washout-seconds`. The command exited
  during argument parsing, the new r3 directory is retained, and the cluster
  remained healthy with no global Chaos resources. The next attempt uses a new
  r4 directory and the runner's supported ten-success washout contract.

# 2026-08-13 Four-project offline preparation continuation

- Re-ran the Train Ticket preparation test after implementation: 3/3 passed,
  then added a regression for the image provenance sidecar. The required red
  test failed because `image-provenance.json` was absent; the minimal writer
  change made the test green at 4/4.
- Generated the non-empty-safe fresh profile
  `runtime_profiles/train-ticket-r2`; its manifest SHA-256 is
  `6429e77cd4d536ed28082e84693f1487f45556b2729a574b2aa528040d43cdc9`,
  matching the recorded value. Namespace rewrite and resource deduplication
  passed.
- Train Ticket remains statically blocked by missing `nacos`, `rabbitmq`,
  `train-ticket-db`, `ts-order-mysql`, and `ts-station-mysql` dependency
  definitions, plus unresolved immutable provenance for six images. No
  dependency values or credentials were read.
- Updated the four-project queue and archive status. Online Boutique
  `runtime_profiles/online-boutique-r3` is the only profile eligible for an
  authorized Namespace-first dry-run; its digest-pinned manifest hash is
  `f0e1be74107db90602b4ad562bf22f5b554e0bf77fa812a0f9faa80440ab2d3f`.
- OpenTelemetry Demo `r1` remains blocked only by missing immutable image
  provenance; TeaStore remains blocked because the exact source snapshot is
  absent from this workspace. Runtime deployment and Chaos injection were not
  performed for any of the four queued projects.
# 2026-08-14 三项目两臂续跑

- 接管 HEAD `84a751b` 的脏工作树，保留所有已有用户/历史变更。
- 集群核验：context=minikube，node Ready，Online Boutique 11 个 deployment 均 1/1，全局 Chaos 资源为空。
- 根因定位：Online Boutique runner 的即时固定批次恢复门槛会误判清理后的短暂恢复窗口。
- 正在按 TDD 增加“连续成功恢复轮询且保留失败样本”的回归测试。
- RED 已验证：新测试因 `collect_sustained_successes` 尚不存在而在收集阶段失败。
- 已实现有界恢复轮询：失败会重置连续成功计数，全部样本保留在 `recovery.business`，默认 180 秒内要求连续 5 次成功。
- `formal-r4-runtime-r2` 完成 7 个 eligible 单元后在 full H4 rep-2 停止；cleanup/global scan 均无残留。
- 诊断确认 cartservice 重启导致本地 port-forward 永久退出；修复 runner 在明确本地转发断连时重建 checkout/cart 两条转发，并修复多行 cart failure 解析。
- 相关回归：`37 passed, 5 subtests passed`。下一正式批次使用全新 `formal-r4-runtime-r3`，不混用旧 runner 结果。
- `formal-r4-runtime-r3` 的 full 8/8 eligible；ablation h1 rep-1 因 checkout port-forward 随 PodKill 退出而停止，cleanup/global scan 清洁。
- 已推广观测通道恢复到 checkout/cart 两端，并修复多行 RPC 错误解析；相关回归更新为 `38 passed, 5 subtests passed`。
- `formal-r4-runtime-r4` 已完成 Online Boutique 16/16：所有报告均为 `completed` 且 runner 判定 eligible；full 的 8 个单元均为 `no_business_impact_observed`，ablation 的 checkout/cart/productcatalog PodKill 各 2/2 为 `weakness_observed`，frontend PodKill 2/2 未观察到业务影响。最终独立字段与诊断哈希复核正在进行。
- Online Boutique 收尾只读集群检查：Minikube node Ready、11 个业务 Pod Running、全局 PodChaos/NetworkChaos/StressChaos 空。
- OTel 首次公开 registry digest 查询失败：GHCR repository 字符串使用 `Substring(7)` 留下前导 `/`，服务返回 `NAME_INVALID`。未写入 provenance、未部署、未调用模型；下一次使用正确的 `Substring(8)`。
## 2026-08-14 三项目两臂正式实验续跑
- 已接管运行中的 OTel 批次 cell 492，未中断、未重跑已完成单元。
- 已核对 HEAD `84a751b`、当前分支 `remediation/2026-08-09-review`；工作树存在大量前置变更，后续只选择性暂存本次范围。
- 已核对 Minikube 节点 Ready、Chaos Mesh 控制器 Ready/restarts=40；最近进度 21/48。
- 全局 Chaos 扫描只看到当前 OTel runner 正在执行的预期 NetworkChaos，等待 runner 自行恢复和清理。
- 只读预检确认沙箱 `PATH` 中无 `python`；未安装或修改环境，后续将使用已存在的本机 Python。
- 为 Sock Shop 部署 gate 新增纯函数 `sock_shop_cluster_facts`：先观察 2 个测试因缺失函数失败，再实现并验证 `5 passed`。该函数只规范化健康、双基线、rehearsal、cleanup、全局残留和 washout 证据，不访问集群。
- 收紧 Sock Shop 批次：新增测试先因缺少 completed-only 查找函数失败；实现后 `3 passed`。现在每个 handoff 必须恰好 4 个选择、每个 mutation 文件必须存在，且跨新目录只复用 `status=completed` 的旧报告。
- 新增 `run_sock_shop_deployment_gate.py`，绑定 server-side dry-run、动态 Deployment 健康、双基线、payment PodKill rehearsal、cleanup/global residual、washout 和 runtime profile。两次定位导入上下文后，Sock Shop gate/runner/profile/batch 组合测试 `13 passed`。
- OTel 最近进度 26/48；节点与 Chaos Mesh 控制器稳定，扫描时全局无 Chaos 残留。
- 修正 Sock Shop runner 目标集与冻结拓扑不一致：14 个 Deployment 全部可被精确 selector 选择，未放宽 namespace/mode/kind；组合测试 `14 passed`。
- 收紧 DeepSeek 发现完整性：只有每次 handoff 恰好选择 4 个且编译器生成 4 个 mutation 才算 valid。发现/编译器/Sock Shop 协议组合测试 `30 passed`。
- 修复跨根验收器：同一实验键优先 completed 报告，核对 mutation 与诊断文件实际 SHA-256，要求 diagnostics captured 和 global scan errors 为空；测试 `2 passed`。
- OTel 最近进度 35/48；十分钟内推进 9 个单元，控制器 restarts=40，全局无 Chaos 残留。
- 新增离线两臂汇总器，按 discovery intent 和 completed 报告统计每个 hypothesis 的重复一致性，仅陈述业务 oracle 观测并固定机制推断禁区；与验收器测试 `3 passed`。
- OTel 原始批次自然完成 48/48；全局无 Chaos 残留，控制器 Ready/restarts=40。严格验收 passed：full 24、ablation 24，weakness 22、no-business-impact 26，所有 mutation/diagnostic SHA 匹配。
- 已缩容完成的 OTel namespace 并记录原副本数；新 Sock Shop 14 个 Deployment 已部署。runtime gate 在注入前因两次基线非全成功而 fail-closed，未执行 rehearsal/DeepSeek。
- 诊断 Sock Shop baseline：14/14 Deployment Ready、全局 Chaos 扫描为空；失败稳定集中在 `/orders`。
- 只读探测确认匿名 `/orders` 为 500 `User not logged in`，直连 orders 为 Mongo error 352；定位为错误 oracle 加无版本 Mongo 漂移。
- 按 TDD 修复认证订单 journey 和 Mongo 兼容性 gate：红测试确认旧行为，最终 `6 passed`。下一步生成 `input-bundles-r2` 并执行 server-side dry-run。
# 2026-08-14 ChaosAtlas-full-v2 projection 重建

- 按 TDD 重建 `tools/build_full_v2_projection.py`：正式 schema 改为 `test_node_rules`、`call_chain_rules`、`fault_applicability_rules`、`outcome_taxonomy`、`negative_evidence`、`historical_fault_pattern_support` 和 `evidence_boundaries`。
- V2 正向规则只使用 runtime validated cards；pending/static/platform-blocked 仅进入负证据或边界。历史 YAML 目录只作为静态排序先验，不复制 raw YAML、路径、项目名、服务名或 mutation 信息。
- 生成的正式投影位于 `artifacts/experiments/chaosatlas_full_v2_projection_2026-08-14-r3/full-v2-projection.json`；canonical projection SHA-256 为 `fe1438cbd39c295be80ca97703c6e3c8ecdd1af9486690cdb53f2f73a60a83d3`，文件 SHA-256 为 `89bdcf42150f54cf2efea4ebf396293bb398716df9b65f6cd749a4d35fdb7b2b`。
- r3 统计：17 张知识卡输入、15 张运行时正证据、2 张非运行时边界证据、7 条测试节点规则、11 条调用链规则、6 条故障适用规则、8 类结果、7 类历史故障模式先验。敏感/项目污染扫描通过。
- Focused regression passed: `8 passed` for `tools/tests/test_build_full_v2_projection.py` with only the existing Windows `.pytest_cache` permission warning。
# 2026-08-14 ChaosAtlas-native-full Sock Shop runtime

- User clarified the target method: use the native project knowledge directly, without generalized V2 projection or leave-one-project-out mapping.
- Native input manifest: `artifacts/experiments/chaosatlas_native_full_2026-08-14-r1/inputs/manifest.json`; `projection_used=false`, `pollution_intentionally_not_excluded=true`, `human_review=pending`, `knowledge_base_updated=false`.
- DeepSeek discovery completed before runtime: 3 seeds, 4 selected hypotheses and 4 compiled mutations per seed.
- The first runtime launcher failed before Kubernetes because Windows exposes both `Path` and `PATH`; PowerShell `Start-Process -Environment` builds a case-insensitive dictionary and raised a duplicate-key error. The failed launcher was not retried.
- A materially different launcher using the existing fixed Python interpreter and inherited environment started successfully. Offline batch integrity confirmed 24/24 units and 0 missing mutations.
- Runtime batch output: `artifacts/experiments/chaosatlas_native_full_2026-08-14-r1/runtime-results-r1`.
- Current progress: 5/24 completed, all five reports `status=completed`, all five classifications `no_business_impact_observed`; the sixth unit is running.
- Live cluster checks during the batch: Sock Shop Pods healthy and `kubectl get podchaos,networkchaos,stresschaos -A` returned no residual resources at each sampled checkpoint.
- Runtime batch completed 24/24. Independent verification passed with 24 reports, 16 `no_business_impact_observed`, and 8 `weakness_observed`.
- The eight weak reports are seed-1003 H2/H4/H6/H8, each reproduced twice. All lifecycle, cleanup, washout, diagnostics, and SHA-256 checks passed; final global Chaos scan was empty.
- Weakness RCA is recorded in `artifacts/experiments/chaosatlas_native_full_2026-08-14-r1/native-full-rca-review.md`. It confirms business impact and bounded database-connectivity log evidence, while keeping Zipkin-unavailable and mechanism inference boundaries explicit.

# Sock Shop YAML confidence native-vs-ablation (2026-08-14)

- Added and verified `tools/yaml_confidence_categories.py`: all 1,935 raw YAML files are inventoried, including parse-failure rows with parent-directory kind fallback.
- Added and verified `tools/yaml_confidence_stopping.py`: Beta posterior upper-95 approximation, novelty reasons, motif coverage, and max/min stop semantics.
- Added and verified `tools/build_sock_shop_confidence_inputs.py`: native-full and ablation inputs are separated, with `human_review=pending` and `knowledge_base_updated=false`.
- Added and verified `tools/run_sock_shop_confidence_discovery.py`: fake-model contract passes; ablation payload excludes knowledge projection fields.
- Added and verified `tools/run_sock_shop_confidence_runtime.py`: mutation compilation is namespace-local and SHA-recorded; HTTP/composite categories are retained as gate failures rather than executed.
- Added and verified `tools/review_sock_shop_confidence_experiment.py`: stable weakness requires at least two completed replicates with business failure.
- Direct-script import regression was found and fixed for all four new CLI modules.
- Offline artifact directory: `artifacts/experiments/chaosatlas_sockshop_yaml_confidence_2026-08-15-r1/`.
- Offline classification result: 1,935 total, 1,506 in five-category runtime scope. Counts are Pod 341, Network 428, Stress 352, Protocol/HTTP 263, Composite/Scheduled 122.
- Fake discovery result: native-full 25 hypotheses; ablation 25 hypotheses. Static runtime plan: each arm has 19 runtime candidates and 6 gate failures.
- No DeepSeek key was read, no external model request was sent, and no Kubernetes mutation was performed in this phase.
- Date note: the artifact directory keeps the requested `2026-08-15-r1` naming, while this execution occurred on August 14, 2026.

# 2026-08-14 Sock Shop YAML confidence runtime recovery

- `runtime-exec-r2` stopped after 58 reports: all 38 native-full reports were
  completed; ablation had 19 completed reports and one failed
  `net-delay-catalogue` replicate-2 report.
- The failed report confirmed injection, Chaos resource recovery, deletion, and
  an empty global Chaos scan. It failed only at business recovery: 85/87
  recovery journeys returned HTTP 500 on `/catalogue`, so it did not satisfy
  the mandatory recovery/washout gate and is not a business-weakness result.
- Diagnostics traced the 500 to the front-end session Redis path. `session-db`
  used `readOnlyRootFilesystem: true` with no writable `/data` volume; Redis
  background RDB writes therefore failed with `Read-only file system`, and
  `stop-writes-on-bgsave-error=yes` surfaced `MISCONF` to the oracle.
- Added a TDD regression in `test_prepare_sock_shop_two_arm.py`; the RED run
  failed on missing Redis args and the GREEN run passed 3 tests after
  `prepare_sock_shop_two_arm.py` disables RDB/AOF persistence for this
  read-only `session-db` configuration.
- The live `session-db` Pod was set to
  `stop-writes-on-bgsave-error=no` as a namespace-local temporary remediation.
  The direct deployment-args persistence command is unsupported by this
  kubectl version, so the durable source-side fix remains in the manifest
  preparer and the running Pod configuration is explicitly recorded.
- A fresh, no-injection formal cookie-based oracle completed 5/5 successful
  journeys after remediation. Immediately before continuation,
  `kubectl get podchaos,networkchaos,stresschaos -A` was empty.
- Next action: create `runtime-exec-r3`, reuse only `status=completed` reports
  from r2, then execute the corrected retry of the failed unit and all
  remaining ablation units.

# 2026-08-14 Sock Shop YAML confidence r4 closure

- The artifact directory keeps the requested `2026-08-15` naming, while the
  r4 report timestamps are on August 14, 2026 UTC.
- The exact `net-delay-catalogue` mutation passed server-side dry-run. Before
  execution, all 14 Sock Shop Pods were Ready and the global
  PodChaos/NetworkChaos/StressChaos scan was empty.
- `runtime-exec-r4` reused 57 completed r3 reports and executed 19 remaining
  ablation report slots. This included the failed `net-delay-catalogue`
  replicate-2 retry plus 18 slots that r3 never reached because its
  fail-fast plan stopped early.
- All 76 r4 reports are `completed`: failure-free baselines, confirmed
  injection, business recovery, cleanup absence, stable washout, captured
  diagnostics, and mutation SHA-256 verification all passed. Final global
  Chaos scan was empty.
- The pending review records native-full as 4 stable weaknesses / 19 runtime
  candidates (21.05%, 5,230.211 seconds) and chaosatlas-ablation as 6 / 19
  (31.58%, 7,647.607 seconds). These are method-specific discovery yields,
  not a causal superiority claim: candidate identities differ, and the newly
  completed ablation slots used the documented 240-second recovery budget.
- Fixed two offline evidence-accounting defects with TDD: fail-fast plans now
  report planned versus processed runtime candidates, and the review tool
  ignores nested diagnostic JSON, infers a five-category label from a mutation
  ID when needed, and derives method wall-clock time from reports.
- Focused runtime/review regression: 25 passed. The only warning is the
  pre-existing Windows `.pytest_cache` ACL warning. No knowledge-base update,
  key read, or external model request occurred in this closure.

# Sock Shop route-aware remaining families closure (2026-08-16)

- The HTTP family was rebuilt against the frozen Sock Shop topology before
  execution: front-end uses port 8079; service calls use port 80 and the
  observed route prefixes (`/catalogue*`, `/carts*`, `/orders*`,
  `/paymentAuth*`, `/shipping*`, `/login*`). The 16 HTTP abort/delay
  mutations produced 32 completed reports.
- The formal route-aware audit combines those 32 HTTP reports with 68
  completed Stress/Schedule reports. It excludes DNSChaos from business
  statistics because the canary was platform-blocked before business
  injection. Audit output: `runtime-remaining-route-aware-2026-08-15-r3/final-audit.json`.
- The 100 audited reports all pass baseline, injection, recovery, cleanup,
  washout, mutation SHA-256, and diagnostic sidecar SHA-256 checks. The
  formal set contains 50 mutation families, 7 stable weaknesses, and 1
  mixed one-shot weakness. The mixed result is not counted as stable.
- The stable Schedule cases are Schedule resources whose actual nested
  action is `PodChaos` `pod-kill` on a 30-second schedule; the `delay` word
  in their hypothesis IDs is not the Chaos Mesh action field.
- DNS evidence was archived separately as
  `runtime-remaining-route-aware-2026-08-15-r3/dns-runtime-blocked.json`.
  The daemon failed while attempting to back up read-only
  `/etc/resolv.conf`; this is a platform applicability result, not a
  Sock Shop weakness, and no DNS rerun is planned without a platform change.
- Human review is still `pending`; `knowledge_base_updated` remains `false`.

# Sock Shop 三方法阶段归档（2026-08-16）

- 恢复并读取根规划文件，核对脏工作树；未覆盖或删除任何既有实验目录。
- 结构化扫描 Full 报告并按 `mutation_id + replicate` 去重：88 个注入 family、176 completed slots、15 stable、3 unstable、70 no-business-impact；88/88 family 的 baseline/injection/recovery/cleanup/washout 字段通过。
- 继续对齐 114-family 去重台账、runtime plan 和后续 selection manifest，确认 114 个 family 全部已有处置：96 个进入 runtime cohort（88 个完成注入、8 个 DNSChaos 在注入前 platform-blocked），其余 18 个为 static gate rejected。18 个不是遗漏未评估。
- 复核 15 个稳定 mutation YAML，确认 4 个 Schedule family 的真实嵌套 action 为 `PodChaos/pod-kill`，并发现 `sock-pod-failure-catalogue-002` 名称与实际 `pod-kill` action 不一致。
- 复核 R5 最终 Ablation：12 个 discovery 假设，正式稳定弱点 2 个；Full 覆盖 catalogue-db 与 orders-db 两个可执行弱点。
- 新增 `docs/SOCK_SHOP_THREE_METHOD_STAGE_REVIEW_2026-08-16.md` 和 `analysis_outputs/sock_shop_three_method_stage_2026-08-16.json`，并更新 README、论文主线、项目总览与归档索引中的过时 headline。
- 最终完整验证 11/11 通过：JSON 可解析；114=96+18、96=88+8、88=15+3+70；15 个 stable ID 数量匹配；6/6 证据路径存在；前后两批结果分别为 8/2/28 与 7/1/42；生命周期字段通过；敏感模式 0 命中；diff check 通过。
- 未调用模型、未读取密钥、未运行 Kubernetes 注入、未提交 Git。Ablation 后续重做时替换当前 Ablation 分栏，不与旧分母叠加。
# 2026-08-16 Sock Shop Ablation YAML15

- TDD 完成 YAML15 选择器：首次 RED 为模块缺失；实现后 3/3 通过。
- 正式 r1 审计发现嵌套 URL 未去敏；补 URL/label key RED 测试后修复，r2 重新冻结且未覆盖 r1。
- r2 生成 15 个示例，原始/去敏 hash 全部匹配，prompt hash 匹配，敏感模式 0 命中；独立复跑 fingerprint 与 prompt hash 一致。
- TDD 完成 YAML15 discovery：新增 manifest/prompt hash fail-closed、五类各 3 校验、调用链来源约束；相关 11/11 通过。
- TDD 扩展后处理 runtime adapter：新臂保留分类示例可见性并复用公共编译器；三组相关测试合计 14/14 通过。
- fake discovery 在 1419.047 秒上限下自主停止，4 个假设全部编译为 runtime 候选；未调用外部模型、未读取 key、未操作集群。
- 已确认采用五类明确标注、每类 3 个真实 YAML 的前置示例设计。
- 已复核语料、分类器、旧 Ablation discovery runner 和现有 Full/Ablation 边界。
- 已新增设计文档 `docs/superpowers/specs/2026-08-16-sockshop-ablation-yaml15-design.md`。
- 已新增实施计划 `docs/superpowers/plans/2026-08-16-sockshop-ablation-yaml15-plan.md`。
- 下一步：先写 YAML15 选择器失败测试，再实现确定性选择与结构化去敏。
# 2026-08-16 Sock Shop YAML15 Ablation closure

- Reproduced the missing post-washout target readiness behavior with a failing runner test, implemented the target Ready gate, and passed 15 runner tests plus 47 focused YAML15 tests.
- Waited for payment Ready and confirmed the global Chaos resource set was empty before continuation.
- Created `runtime-exec-deepseek-r2`, reused 53 completed r1 reports, reran failed `hyp-028-rep-2`, and executed the remaining 38 slots. The runtime process exited 0 with 92 completed reports.
- Independent audit: 46 families; 9 stable, 0 unstable, 37 no-impact; 92/92 lifecycle-valid; 92/92 mutation hashes and 552/552 diagnostic hashes matched.
- Final cluster check: 14/14 Sock Shop Pods Ready and no PodChaos, NetworkChaos, StressChaos, HTTPChaos, DNSChaos, Schedule or Workflow resources globally.
- Added `final-audit.json` and `FINAL_REVIEW.zh-CN.md`; updated stage review, paper mainline, project summary and machine stage summary. Human review remains pending and the knowledge base was not updated.
- Encountered one non-experiment PowerShell summary error by passing FileInfo through the pipeline without `.FullName`; the corrected read used `-LiteralPath $f.FullName`. No experiment command was repeated because of this reporting-only error.
- Added an immutable `.gitattributes` rule for the formal YAML15 r2 tree. After `git add --renormalize -f`, direct Git-index verification passed with 92 reports, 92 mutation hashes, 552 diagnostic hashes, zero missing and zero mismatch.

# 2026-08-16 YAML15 review hardening

- Ran the new regression set. The first run found a missing `pytest` test import; after correcting the test harness, RED was 3 failed / 26 passed for the intended behaviors.
- Implemented the three minimal production fixes and added CLI coverage; GREEN is 30 passed.
- Located and corrected the Full evidence boundary: first 38 families are in `runtime-canonical-plan-r2`, later 50 in route-aware r3. Generated a 76-report SHA verification manifest and a 38-family result review; both pass and are now referenced by the combined provenance.
- Affected Sock Shop/YAML15 regression is 96 passed plus 5 subtests. Full `tools/tests` is 640 passed plus 5 subtests and the same 2 pre-existing pinned-hash drift failures; implicated historical files are unchanged in this worktree.
- JSON, batch arithmetic, mixed-schema boundary, source SHA, and 5-pattern sensitive scans pass. `git diff --check` formatting findings were corrected.
- Final live check: context `minikube`, all 14 Sock Shop Pods Ready, and no PodChaos/NetworkChaos/StressChaos/HTTPChaos/DNSChaos/Schedule/Workflow resources remain.
- Independent reviewer reported no Critical issues and two Important issues. Fixed the sub-millisecond deadline escape and stale `15 vs 2 vs 2` wording; also fixed terminal checkpoint resume and added explicit source paths.
- Review-fix regression: 19 passed. Updated affected suite: 99 passed plus 5 subtests. Updated full suite: 643 passed plus 5 subtests, with only the same 2 historical pinned-hash drift failures.
- Created commit `d72a2c1` with the explicit 2,013-file Sock Shop R5/YAML15 whitelist. Cleared 96 post-commit index-only log normalization entries without changing working files; unrelated existing modifications and untracked directories remain untouched.

# 2026-08-16 ChaosAtlas 主线整理归档

- 当前整理范围冻结为：论文主线入口、项目总览、README、归档地图、实验目录和主线关键工具注释；历史实验产物保持原路径不动。
- 已核对主线：初始 TestNode/局部影响子图/门禁/证据链架构；Online Boutique、OpenTelemetry Demo、Train Ticket 三项目及 6 个已提交 issue；Sock Shop Full 15 个稳定 weakness 与 YAML15 Ablation 9 个稳定 weakness；ChaosEater 官方原生流程作为不同测量层的阶段参照。
- 已确认冻结历史材料：same-pool、预选池、旧 Ablation、早期 Sock Shop pilot、ChaosEater-adapter；这些材料保留审计价值，不进入当前主线统计。
- 归档整理不运行 Kubernetes、不调用模型、不读取密钥，不更新知识库，不暂存无关未跟踪实验目录。
- 最终验证：主线关键工具 `py_compile` 通过；focused suite `66 passed, 5 subtests passed`；全量 suite `643 passed, 2 failed, 5 subtests passed`，两个失败均为既有 generic-rules/mutation-map pinned-hash drift；文档 `git diff --check` 通过，归档入口断言通过，敏感模式扫描无命中。
- 本轮创建的两个 pytest 隔离临时目录已删除；已有 `.pytest_cache` 和其他用户目录未处理。整理结果未提交、未推送。
## 2026-08-21 GitHub 上传前保守清理

- 核对 `origin/remediation/2026-08-09-review`：当前本地 HEAD 为 `ea82922`，未执行推送。
- 确认 `tools/bin/` 中 5 个本地工具分发文件被 Git 跟踪，其中两个 `helm.exe` 完全重复；本轮仅从索引移除，工作区文件保留。
- 清理根目录 `.pytest-tmp/` 测试缓存；实验 `artifacts/`、`raw_yaml/`、知识卡和失败证据未触碰。
- `.gitignore` 新增 `/tools/bin/` 和 `/.pytest-tmp/`；`docs/ARCHIVE_CLEANUP.md` 增加保守瘦身记录。
- 未执行 `git filter-repo`、force-push 或远端删除；待用户单独授权后再讨论历史瘦身。
- 本地清理提交：`b879feb chore: exclude local tool bundles and pytest cache`；未推送远端。
- 全量验证：`1036 passed, 2 failed`；失败仍为既有 `generic_rules_sha_pinned` 和 `mutation_map_hashes_match` 漂移。
# 2026-08-21 真实 inventory 阶段

- 已确认下一阶段边界：只读 Kubernetes inventory -> Deployment/TestNode -> 自动候选；不在发现阶段注入或更新知识库。
- 已开始实现 `KubernetesProjectAdapter`，将复用现有部署节点和场景编译协议。
- 已完成 `tools/kubernetes_project_adapter.py`：只读读取 Deployment/Service/Pod，去敏后生成 inventory、部署节点和 6 类故障候选。
- 已接入 `tools/chaosatlas.py --mode live`；真实运行前仍要求业务 Oracle 的 `service`/`remote_port` 和 `--approve-live`。
- 验证：54 个相关测试通过；真实 `sock-shop-lab` 只读发现 14/14/14 资源、84 个候选；没有执行 apply/delete/patch。
- 已完成 evidence -> RCA 交接：live `observe`/`classify` 引用 `evidence_refs.json`，`rca_report.json` 明确 `pending`、待补业务 Oracle/机制证据和 `promotion_allowed=false`。
- 验证：63 个相关测试通过；真实 events/logs 只读 smoke 成功；未执行任何注入。
- 已接入 live preflight：kube context、namespace、Deployment/Service/Pod、events、Chaos 残留全部通过后才允许 executor。
- 最终验证：67 个相关测试通过；真实 preflight `ready_for_injection`、residual `clean`；集群 Chaos 资源列表为空；未执行注入。
- 已补齐去敏业务路径回放 evidence，并增加 Oracle service 与 live 候选目标一致性门禁；不匹配时不会调用 executor。
- 已将 live 生命周期证据接入现有 RCA 状态机：baseline/injection/observation/recovery/cleanup 由 attestation 确定性映射，不再手工固定 `pending/none`。
- 业务不可达、注入未确认和环境阻断保持 `pending/none`，不会进入漏洞或防御结论；完整生命周期但缺机制区分证据时进入 `bounded/provisional`。
- `knowledge_draft.json` 现由 `project_knowledge_draft` 生成，`regression_intents.json` 现由统一编译器生成；provisional 只产生 `discriminate` 验证意图，不写正式知识库。
- 验证：live/RCA 相关回归 `68 passed`；`compileall` 和 `git diff --check` 通过；真实 Sock Shop 只读 live smoke 完成到 gate，因 profile 缺少业务 Oracle service/remote_port 按预期阻断，未执行注入。
- 已补齐 Sock Shop live Oracle：`front-end:80`，并扩展六类服务器部署故障的 live scenario 编译：PodKill、ContainerKill、CPU/Memory Stress、Network Loss/Partition。
- 新增 `tools/chaosatlas_batch.py` 与 CLI `--max-candidates/--all-candidates`：候选计划固定后逐候选独立运行目录、独立 preflight、证据、RCA、知识草稿和清理报告，单候选失败不会污染后续候选。
- 修复真实 Kubernetes inventory 的 Deployment `metadata.name`、嵌套 selector/replica 读取；真实无批准批次 smoke 规划 2 个候选，2 个均在 `approve_live` 门前阻断，executor 调用数为 0，未产生 Chaos 资源。
- 验证：live 批次相关回归 `63 passed`；`compileall`、`git diff --check` 通过。下一步才是显式批准后的受控小批次，并补机制证据到 RCA 区分动作。
- 已将 executor 的 `mechanism_evidence` 透传到运行记录；只有 source_ref 文件可安全采集且证据满足 `mechanism_evidence` 时，才作为区分动作输入，缺失机制证据继续保持 `bounded`。
- `build_case_from_hypothesis` 的必需证据增加机制证据项；机制证据 + 完整生命周期的测试可进入 `confirmed` RCA，普通完整生命周期仍只能 `bounded/provisional`。
- 最终阶段验证：相关回归 `79 passed`；`compileall` 和 `git diff --check` 通过；Kubernetes 全局 Chaos 残留 `0`。

# 2026-08-23 Phase 4 防御知识晋级接入

- 新增 `tools/defense_promotion_stage.py`：只读取显式 history root 的直接子目录，要求 `run_manifest.json`、`classify.json`、`observe.json`、`cleanup_report.json` 四件套；非目录和不完整目录结构化记录为 rejected，不递归扫描 artifacts。
- 将防御晋级加入 `tools/chaosatlas.py` 的 `promote_defense` checkpoint stage；未提供 history 时写入 `not_run`，提供 history 时调用既有两次独立运行晋级器。
- 新增 CLI 参数 `--defense-history-root` 和 `--knowledge-write-root`；`--knowledge-root` 保持只读，只有显式 write root 才复制 `local_reusable` 卡片和 regression intents。
- 新增冲突记录接口：旧知识卡不覆盖，记录 snapshot SHA-256、运行 fingerprint、原因和空 guard intents，状态为 `contested`。
- advisory 假设增加 `advisory_status`：无 provider 时为 `deterministic_fallback`；有 provider 时通过候选 ID 白名单解析，不能修改最终分类或制造新候选。
- 验证：Phase 4 focused suite `74 passed`；`python -m compileall -q tools`、`git diff --check`、CLI `run --help` 均通过；仅有既存 pytest cache 权限 warning。
- 边界：未执行真实集群注入、未读取 API key、未扫描全局 artifacts、未自动写入正式知识库；Train Ticket live latency fixture 和 Phase 5 deployment patch/retest 仍待后续阶段。

# 2026-08-23 Train Ticket latency boundary fixture

- 新增 `tools/train_ticket_latency_fixture.py`，只读消费冻结的 Station delay ladder、baseline、r4 timeout runner 和 server-completion evidence。
- fixture 固化 100ms/500ms/2s 的 `response_preserved_latency_degradation` 与 3s 的 `client_timeout_server_completion_after_delay` 两类不同 claim scope。
- 明确 `defense_claim_type=null`、`knowledge_status=provisional`、`rca_status=bounded`；没有 operator SLO、retry/fallback/circuit-breaker 机制证据时不生成 `guard`。
- 通过统一 regression compiler 只生成 `discriminate` 意图；不修改现有 Train Ticket artifact 或知识库。
- 验证：Phase 4 + Train Ticket suite `76 passed`；仅有既存 pytest cache 权限 warning。
- Phase 4 exit gate：complete。下一阶段为 Phase 5 结构化部署 patch、fresh deploy 和同场景复测。

# 2026-08-23 Phase 5 离线改进复测门

- 扩展 `tools/deployment_improvement.py` 的结构化 patch 白名单：replicas、PDB min/max、HPA min/max/target CPU、readiness/liveness 和 resource requests/limits。
- patch 只写入 immutable source copy，原始 source tree 保持不变；非法 pointer、旧值不匹配、路径不安全时 fail closed。
- `run_improvement_retest` 支持显式 `server_side_dry_run` validator；validator 非 ready 时在 executor 前返回 `deployment_blocked`。
- 固化四态结果：`improvement_verified`、`regression`、`deployment_blocked`、`not_run`；新增 `improvement_evidence`，只有同 scenario contract、同 oracle、recovery/cleanup 通过才允许 knowledge update。
- `feedback_protocol.py` 新增 `validate_improvement_evidence`，失败改进不会生成 defense claim。
- 验证：跨 Phase 4/5 focused suite `85 passed`；compileall 和 diff check 通过，仅有 pytest cache 权限 warning。
- 当前边界：真实 fresh namespace/deployment adapter 尚未接入；未执行任何 live patch、apply 或重新部署。下一步是实现显式批准的 fresh-deploy adapter，并用 Sock Shop redundancy 场景完成一次真实复测。

# 2026-08-23 Phase 5 fresh-deploy adapter

- 新增 `tools/fresh_deploy.py`：对 immutable manifest copy 做 namespace allow-list 校验、server-side dry-run、显式 live apply 和 cleanup。
- 默认 `allow_live=False`；未明确批准时不调用 apply/delete。错误 namespace、无 YAML、解析失败和 server-side dry-run 失败均返回 `deployment_blocked`。
- `run_improvement_retest` 现在在 patched copy 上执行 server-side dry-run callback，再进入 scenario executor；因此校验的是实际待部署内容而不是原始 source。
- 验证：Phase 4/5/fresh-deploy focused suite `88 passed`；未调用 kubectl，未执行 live apply/delete，未操作 Minikube。
- Phase 5 当前状态：离线与 adapter 门完成；真实 fresh namespace 复测仍 pending，需要显式选择 namespace、manifest source 和 live approval。

# 2026-08-23 Phase 5 fresh deployment execution

- 新增 `tools/prepare_fresh_manifest.py`：从 Sock Shop 原始 manifest 生成不可变 namespace-rewritten copy，记录 source/manifest SHA-256 和资源身份；原始文件字节保持不变。
- 新增显式 `--strip-node-ports`：仅在副本中将跨 namespace 冲突的 NodePort Service 转为 ClusterIP，并记录 `node_port_rewrites`；原始 `front-end` NodePort 不变。
- 新增 `tools/run_fresh_deploy.py`：默认 server-side dry-run；仅 `--apply-live --approve-live` 允许部署，`--cleanup --approve-live` 允许清理；脚本/模块两种导入方式均覆盖。
- 验证：新增准备器/包装器 focused suite `10 passed`（使用工作区 basetemp；仅有既存 pytest cache ACL warning）。
- 真实准备产物：`artifacts/sock-shop/improvement/fresh-sock-shop-improvement-lab-nodeport-stripped/`，source SHA `ae545e54...38d8253`，copy SHA `56f5c884...3877d5d`。
- 真实 server-side dry-run 首次因 `front-end` NodePort `30011` 与原 namespace 冲突而 `deployment_blocked`；去除副本 NodePort 后 28 个资源 API 校验通过。
- 已按 live gate 创建专用 namespace 并部署 fresh copy，apply 返回 0；但双份 Sock Shop 使 Minikube 达到 `7.96GiB/8GiB`、约 `409% CPU`、PIDS `4486`，API server TLS handshake timeout。
- 未开始 Oracle、故障注入或知识更新；当前必须先恢复控制面并清理 `sock-shop-improvement-lab`，再决定采用精简 fresh 拓扑或增加 Minikube 资源。
- 控制面恢复后已执行 `run_fresh_deploy --cleanup --approve-live`；cleanup 返回 `cleanup_verified`，`sock-shop-improvement-lab` 已删除，原 `sock-shop-lab` 保留 14 个 Pod。
- 现有 profile 重启时明确拒绝原地改资源：`You cannot change the memory size for an existing minikube cluster`；当前容器仍为 8GiB 上限。后续应使用独立 `chaosatlas-improvement` profile（16GiB/8 CPU），或在完整备份后删除重建原 profile。

# 2026-08-23 Phase 5 改进副本同场景真实复测

- `tools/deployment_improvement.py` 支持多文档 YAML 的 `document_selector.kind/name`，不再把 patch 固定写入第一个文档；自动生成的 Deployment 建议带有 selector。
- 生成不可变副本 `fresh-sock-shop-improvement-lab-nodeport-stripped-front-end-replicas-2`，仅将 `Deployment/front-end` 的 `/spec/replicas` 从 `1` 改为 `2`；原副本 SHA-256 `56f5c884...3877d5d` 保持不变，改进副本 SHA-256 `58e85854...0d73b0`。
- 在独立 `chaosatlas-improvement` profile 中完成 server-side dry-run、显式 live apply、14 个 Deployment Ready 和 `front-end:80` HTTP 200。
- 复用 `front-end pod_kill`、seed `1001`、HTTP Oracle、180s recovery 和 cleanup contract 完成真实复测：baseline `availability_degraded`，after `availability_defended`；注入、60s 观察窗口、恢复、Chaos 清理均有证据。
- 写入 `artifacts/sock-shop/improvement/live-improvement-r1-exec/improvement_evidence.json`，状态 `improvement_verified`，结构化校验通过，允许改进知识更新；after RCA 仍为 `bounded`、知识仍为 `provisional`，因此正式知识库未自动晋级。
- 复测 namespace 已清理；残留扫描：namespace `0`、业务 Pod `0`、全局 Chaos 资源 `0`。focused suite `16 passed`，`compileall` 与 `git diff --check` 通过。

# 2026-08-23 Phase 5.2 真实改进复测与防御知识晋级

- 新增统一 `python tools/chaosatlas.py improve` 入口，串联结构化 patch、namespace bootstrap、patched manifest server-side dry-run、显式 live apply、Ready 等待、既有 live closed loop、cleanup、证据比较和知识晋级。
- 多文档 YAML patch 已支持 `document_selector.kind/name`，本轮只修改不可变副本中的 `Deployment/front-end.spec.replicas`（1 -> 2）；原始 manifest 和原 `minikube` / `sock-shop-lab` 保持不变。
- 在独立 `chaosatlas-improvement` profile 的 `sock-shop-improvement-lab` 中完成第二次独立真实复测：baseline `availability_degraded`，after `availability_defended`；两次 after 运行均通过，改进证据为 `improvement_verified`，cleanup 为 `cleanup_verified`。
- 防御知识已满足两次独立复现晋级门禁，正式卡为 `KB-DEF-cf55cc7c4470c9b6`，`project_commit=6e83eb6ffdf1bce43e332337a3bb0fc40327d039`，状态 `local_reusable`，防御范围明确为 deployment-boundary redundancy；不宣称应用内部 timeout/retry/fallback。
- 正式回归意图已写入 `artifacts/knowledge/live-improvement/regression_intents.json`；旧的 `runtime-unknown` 重复卡从正式知识目录移除，历史运行目录中的原始晋级产物保留用于审计。
- 最终验证：focused suite `26 passed`；`compileall`、`git diff --check`、正式知识 JSON 校验和集群残留检查均通过。

# 2026-08-23 Phase 6 单候选产品化闭环

- 新增 `tools/phase6_audit.py`：统一生成 execution contract、artifact index 和 phase6 audit；记录项目/commit、approval、namespace allow-list、单候选预算、恢复时长、阶段状态、知识库写入状态和 cleanup。
- `tools/chaosatlas.py run` 现在在 dry-run、live success、environment blocked 和 method invalid 路径都生成 `execution_contract.json`、`artifact_index.json` 和 `phase6_audit.json`；单次运行不会绕过显式 promotion 写正式知识库。
- 修复 live Oracle 门禁顺序：缺少业务 `service/remote_port` 时在 inventory 前返回 `environment_blocked`，不再误报 `method_invalid`。
- 三项目离线回放通过：Sock Shop、Online Boutique、P02 均为 `dry_run_ready`，每个 audit 均为 cleanup `verified`、`max_candidates=1`、`knowledge_base_updated=false`。
- 在独立 `chaosatlas-improvement` profile / `sock-shop-improvement-lab` 完成真实单候选闭环：server-side dry-run、live apply、14 个 Deployment Ready、`front-end pod_kill`、RCA 和知识草稿均完成；结果为 `live_completed`、`availability_defended`、RCA `bounded`、knowledge `provisional`、cleanup `verified`。
- 真实 canary 证据保存在 `artifacts/sock-shop/phase6/live-closed-loop-r1/`；专用 namespace 已删除，全局 Chaos 残留为 0，原 `minikube/sock-shop-lab` 保留 14 个 Pod。
- 最终验证：Phase 6 focused suite `42 passed`；审计模块完成 RED -> GREEN，compileall、git diff check、live artifact contract 和集群残留检查均通过。

# 2026-08-23 Phase 7 DeepSeek advisory 接入

- 新增 `tools/deepseek_advisory.py`：显式读取 DeepSeek key 文件或环境变量，默认 endpoint 为 DeepSeek OpenAI-compatible API、模型为 `deepseek-v4-flash`；仅发送去敏项目事实、候选空间和知识摘要。
- `chaosatlas.py run` 新增 `--advisory-provider deterministic|deepseek`、`--api-key-file`、`--base-url`、`--model`；默认仍是 deterministic fallback，未显式选择时不读取密钥。
- advisory 输出通过候选 ID、字段、禁止结论字段和标量元数据白名单解析；LLM 不能创建候选、决定漏洞/防御分类、RCA 或知识晋级。
- 修复模型返回 fenced/preamble JSON 和长输出截断边界；提示限定最多 8 个紧凑假设，DeepSeek token 上限调整为 2600，截断或非法输出安全 fallback。
- 使用本地 DeepSeek key 完成一次真实 Sock Shop dry-run：`advisory_status=completed`、模型 `deepseek-v4-flash`、8 个 advisory 假设；审计仍为 `dry_run_ready`、`knowledge_base_updated=false`、RCA 未运行、cleanup `verified`。证据目录：`.tmp-phase7-deepseek-run3/`（临时验证产物）。
- 验证：Phase 7 focused suite `41 passed`；`python -m compileall -q tools`、`git diff --check` 通过。未执行 Kubernetes 注入，未写入正式知识库。
- 边界：当前 DeepSeek 只参与“候选假设和证据动作建议”；要实现完整自动闭环，下一步是把 advisory 选择与 live candidate budget、证据动作计划和受控执行回放做成可审计的第二轮迭代。

# 2026-08-24 Phase 8 证据动作计划器

- 新增 `tools/evidence_action_planner.py`：把已验证候选和 advisory 假设转换为固定的只读证据动作，包括 deployment/service facts、Pod 状态、事件、日志、业务基线和机制证据。
- 计划器只接受静态候选 ID，校验目标签名和完整恢复契约；未知候选、签名不匹配、非法预算和恢复契约缺失均 fail-closed，不执行任何动作。
- `tools/chaosatlas.py run` 在 hypotheses 后、gate 前写入 `evidence_plan.json`；计划进入 artifact index，支持 resume 输入哈希复用，不增加用户侧命令或新的执行器接口。
- live 路径要求最终 Oracle 候选属于证据计划，计划阻断时在 executor 前返回 `environment_blocked`；dry-run 只记录计划，不触发 Kubernetes 或正式知识库写入。
- Kubernetes deployment candidate 现在透传已验证的 recovery contract，避免真实 live 候选因信息丢失被误阻断。
- 实际 Sock Shop dry-run：计划状态 `planned`，单候选预算 `1`，生成 `7` 个只读动作，phase6 audit `dry_run_ready`，`knowledge_base_updated=false`。
- 验证：证据计划、ChaosAtlas、DeepSeek、hypothesis 和 Kubernetes adapter focused suite `49 passed`；compileall 和 diff check 通过。
- 边界：当前阶段只生成和门禁证据动作计划，尚未自动执行多候选证据循环；下一阶段是把通过计划的只读动作接入 live evidence collector，再复用现有注入/RCA状态机。

# 2026-08-24 Phase 9 计划证据动作接入 live collector

- 新增 `tools/planned_evidence.py`：只派发 `evidence_plan.json` 中已批准且 `read_only=true` 的 Deployment、Service、Pod、事件和日志动作；blocked/unplanned action 不调用 collector。
- 扩展 `KubernetesEvidenceCollector` 的只读接口：`collect_deployment_facts`、`collect_service_facts`、`collect_pod_state`，均执行 namespace-safe 的 `kubectl get ... -o json` 并复用敏感信息检查、哈希和 unavailable evidence 契约。
- live `_collect_live_evidence` 现在优先消费 evidence plan；证据记录携带 `planned_action_id`，`evidence_refs.json` 记录 `planned_action_ids` 和 `evidence_plan_ref`，可以审计“计划动作 -> 证据”对应关系。
- 现有 business oracle/lifecycle/mechanism evidence 逻辑保持不变；计划动作不产生漏洞、防御、RCA 或知识结论。
- 验证：Phase 9 focused suite `53 passed`；Sock Shop dry-run `dry_run_ready`；compileall 和 diff check 通过。
- 边界：尚未在真实集群执行本阶段的完整计划证据采集与多候选循环；下一步是使用已批准的独立 namespace 做一次只读 evidence plan live smoke，再决定是否接入自动候选迭代。

# 2026-08-24 Phase 10 真实只读 evidence-plan smoke

- 在当前可用的 `chaos-testing` namespace 做了真实只读 smoke；由于 `sock-shop-lab` 当前不存在，没有把 Chaos Mesh 控制面冒充 Sock Shop 项目做业务结论。
- 计划动作使用真实资源目标：Deployment `chaos-controller-manager`、Service `chaos-mesh-controller-manager`、Pod selector、Events、Logs；5/5 动作成功返回 supports evidence，5/5 证据有 SHA-256 和 `planned_action_id`。
- 发现并修复 Deployment/Service/Pod 原始 Kubernetes JSON 可能包含 token/secret 字段的问题：collector 现在先做字段级 allow-list projection，再执行敏感扫描和写盘；真实 smoke 敏感模式扫描无命中。
- 修复部署目标与 Service 目标可能不同的情况：候选支持 `service_target`，计划保留 `deployment_target`，dispatcher 分别使用正确资源名。
- 集群只读检查：`chaos-testing` 保持存在，4 个 Pod，未执行 apply/delete/patch/Chaos 注入。
- 最终验证：Phase 10 focused suite `54 passed`；compileall 和 diff check 通过。
- 当前边界：Sock Shop 真实业务 evidence-plan smoke 仍需恢复/部署一个独立的 Sock Shop namespace；下一步是用明确批准的独立 namespace 完成真实单候选计划闭环，然后再扩展多候选自动迭代。

# 2026-08-24 Phase 10 follow-up audit

- 在已有 Phase 10 只读 smoke 之后，使用独立目录 `artifacts/phase9-readonly-smoke-20260824/run-r2/` 重新核验计划到证据的映射；5 条 collector records 全部有 `planned_action_id`，7 个计划动作完整保留。
- 计划 Service target 为 `chaos-mesh-dns-server`，实际记录命令为 `kubectl get service chaos-mesh-dns-server -n chaos-testing -o json`；Deployment/Logs 仍使用选中 Deployment target。
- 命令审计无 apply/delete/patch/replace/create/exec 或 Chaos 注入，输出文件扫描无禁止操作文本；`runtime_executed=false`、`model_called=false`、`formal_knowledge_written=false`。
- 验证：Phase 9/10 相关 suite `56 passed`；全量 `tools/tests` `1206 passed, 1 warning, 5 subtests passed`；compileall 和 diff check 通过。
- 结论：只读证据链在当前控制面可用，但没有业务应用 namespace，不改变 `pending_runtime_evidence` 或 `guarded` 边界；后续仍需独立业务 namespace 与显式 live mutation 批准。

# 2026-08-24 Phase 10.1 Sock Shop 正确 context 只读 smoke

- 用户确认本机有两个 Minikube 集群；只读核对发现 `minikube` context 才是 8G Sock Shop 集群，`sock-shop-lab` 存在，包含 14 Deployments、14 Services、14 Pods。此前 `chaosatlas-improvement` 的 `environment_blocked` 仅反映默认 context 选错，不是 Sock Shop 集群缺失。
- 本轮不修改 kubeconfig 当前 context；所有 adapter/collector 命令均显式前缀 `--context minikube`，独立输出为 `artifacts/phase9-readonly-smoke-20260824/sock-shop-minikube-r1/`。
- 真实 inventory 生成 84 个候选，证据计划选择 `front-end` PodKill；7 个计划动作中执行 Deployment、Service、Pod、Events、Logs 五类，5/5 records 为 `supports`，5/5 带 `planned_action_id`。
- 审计：`status=passed`、available=5、unavailable=0、敏感扫描 0、禁止命令 0、Chaos 资源残留 0；`runtime_executed=false`、`model_called=false`、`promotion_allowed=false`。
- 当前结论：Phase 9 证据动作已在真实 Sock Shop namespace 完成只读闭环；仍未执行注入，不能据此声称发现率、RCA 或 Shadow 优于 Legacy。

# 2026-08-24 Phase 11 Guarded Sock Shop canary

- 用户明确批准执行单候选 guarded canary，目标固定为 `minikube/sock-shop-lab` 的 `front-end` PodKill，候选 ID 为 `server:deployment:827339c6afd397a13efb276a:pod_kill`。
- 注入前发现 live inventory 的 `service_target` 泄漏为 `user-db`；新增双 deployment/service 回归测试先 RED，再将 candidate 构建改为读取各自 `node.service`，adapter suite GREEN（4 passed），重新生成 r2 evidence plan 后 `front-end -> front-end` 正确。
- 第一次 live 启动因沙箱禁止写原始 kubeconfig lock 在 executor 前 `environment_blocked`，没有触碰集群；第二次使用工作区临时 kubeconfig 副本并显式设置 KUBECONFIG，run `live-7313fcfe4076` 返回 `live_completed`，临时副本已删除，原 context 保持 `chaosatlas-improvement`。
- 生命周期证据：preflight `ready_for_injection`；baseline 3/3 HTTP 200；PodChaos injection confirmed；observe 短暂 `business_unreachable` 后 HTTP 200 恢复；replacement UID `ddee...` -> `14772...`；cleanup 删除并确认资源 absent；14/14 Pods Ready；全局 Chaos 资源 0。
- 结果：`classify.result=availability_degraded`；`rca_status=confirmed`、`weakness_status=candidate`；`knowledge_status=provisional`；生成 `knowledge_drafts/KB-RCA-sock-shop-front-end-pod-kill-intent.json` 与 1 个 regression intent；`phase6_audit.knowledge_base_updated=false`，未写正式知识库。
- 证据目录：[phase10 canary r2](C:\Users\23741\Desktop\XIAO\ChaosAtlas\artifacts\phase10-guarded-canary-20260824-front-end-podkill-r2)。
- 验证：直接相关 focused suite `26 passed, 1 warning`；compileall/diff check 通过。全量 suite `1193 passed, 20 failed, 5 subtests passed`，失败为既有 gate 夹具/API 兼容问题，需后续单独处理。

# 2026-08-24 Phase 11 显式 kube context 与 Sock Shop live 闭环

- `chaosatlas run` 新增 `--kube-context`，并贯通 Kubernetes inventory、preflight、Chaos Mesh gate/apply/delete、恢复轮询、业务 port-forward 和计划证据 collector；不再依赖进程默认 context。
- `KubernetesPreflight` 在显式 context 下直接报告 requested context，避免 `kubectl config current-context` 把默认 context 误写入审计结果。
- 在真实 `minikube/sock-shop-lab` 使用一条命令完成单候选 live 闭环：14 个 Deployment、14 个 Service、14 个 Pod 发现；`front-end pod_kill` 注入确认；业务 Oracle、事件、日志、恢复和清理均成功，计划动作 7 个、证据记录 12 个、不可用证据 0 个。
- 运行结果：`live_completed`，分类 `availability_degraded`，RCA `confirmed`，知识草稿 `provisional`，回归意图已生成；未指定 `--knowledge-write-root`，因此正式知识库保持未写入。
- 运行目录：`.tmp-phase11-sock-shop-live-r1/`；真实 Chaos 残留为 0，原 `sock-shop-lab` 保持可用。
- 验证：context/preflight/lifecycle/native focused suite `69 passed`，补充 context 报告回归后 `5 passed`；`compileall` 与 `git diff --check` 通过。
- 当前边界：单候选受控闭环已可用；正式知识晋级需要显式 knowledge write/promotion root 和对应反馈门禁，多候选信息增益循环仍未默认开启。

# 2026-08-24 Phase 11 follow-up: baseline repair and independent canary r3

- 复现并定位全量测试的 19 个失败：runtime gate 在空 context 时把 `kube_context=None` 传给旧 runner/mock，顶层异常 fail-closed 返回又缺少历史 `checks` 字段；batch adapter 同时需要兼容 `inventory()` 与 `inventory(profile)`。
- 生产修复保持显式 context 传播：空 context 不传关键字，显式 context 仍贯通；fail-closed 结果保留 `scope_guard`、target pod、target port、mutation name 和 injector prerequisite 结构；batch 通过签名识别 profile-aware inventory。
- 相关回归 `32 passed, 5 subtests passed`；全量 `tools/tests` `1213 passed, 1 warning, 5 subtests passed`。warning 仅为受限环境无法写入全局 pytest cache。
- 在 `minikube/sock-shop-lab` 执行第二次独立 `front-end` PodKill，输出目录为 `artifacts/phase10-guarded-canary-20260824-front-end-podkill-r3/`；r3 artifact index 与 execute hash 均不同于 r2，replacement UID 为 `14772cd8-0c4f-4d9b-abc3-d050204ed670 -> 7a6b5c4e-97a4-4290-ae23-a1e401949f79`。
- r3 lifecycle：`live_completed`、injection confirmed、observe=`degraded`、classification=`availability_degraded`、RCA=`confirmed`、weakness=`candidate`、knowledge=`provisional`、cleanup=`verified`；运行后全局 Chaos 资源为 0，front-end Pod 保持 Ready。
- r2/r3 两次均为同一受控降级模式，支持“单副本 front-end PodKill 会造成短暂可用性降级并在 replacement Pod Ready 后恢复”的稳定候选观察；正式知识库仍未更新。
- 已按 `AGENTS.md` 使用 `email-notify` 将本次 success 完成摘要写入本地 pending outbox；通知内容未包含密钥或敏感文件内容。

# 2026-08-24 Phase 13 information-value replay evaluator

- 核对结果：`experiment_policy`、`stop_policy`、policy CLI、feedback、schema、causal identity、native discovery 和 rollout 测试全部通过，policy focused suite 为 `35 passed`。
- 新增 `tools/evaluate_experiment_value_policy.py`：按冻结候选分母建立 policy state，在每个 legacy runtime result 前计算 policy next candidate，随后只用确定性 runtime classification 更新状态，输出 `input_sha256`、decision diff、candidate states 和 stop record。
- TDD 验证：模块缺失时先得到 RED；实现后 replay tests `3 passed`。CLI 同时兼容候选/结果 JSON 的 object 和 list 根节点。
- 对既有 Online Boutique shadow 分母执行离线回放：输出 `artifacts/policy-rollout/online-boutique-r4-shadow-20260823/information-value-replay.json`，由于冻结 runtime 结果为空，明确记录 `recorded_result_count=0`、`stop_reason=replay_exhausted`、`cluster_access=false`、`model_called=false`、`mutation_executed=false`。
- 当前完成度判断：旁路候选的确定性选择、状态、停止和离线验收入口已完成；尚缺一组 runtime-backed shadow replay 和一次 policy-selected guarded canary，因此尚不能切换默认模式或宣称方法实验完成。

# 2026-08-24 Phase 14 policy-selected guarded canary

- 为 replay evaluator 增加 stage envelope 解包和只读 `--context` 输入；先运行 RED 测试确认旧 CLI 拒绝 `payload.candidates`/`--context`，实现后 replay focused suite 为 `5 passed, 1 warning`。
- 从真实 Sock Shop `phase10` candidate space 冻结 84 个候选，使用 r2/r3 `classify.json` projection（均为 `confirmed_weakness`、evidence `complete`）执行 runtime-backed shadow replay。
- replay 证据：`policy_version=ig-stop-v1`、`candidate_state_count=84`、`recorded_result_count=2`；两轮 policy recommendation 均为 `server:deployment:827339c6afd397a13efb276a:pod_kill`，`decision_changed=0`，stop=`replay_exhausted`；重复运行 SHA-256 与主报告一致。
- 只读 context 明确 `boundary_candidate_ids`、confidence/value 阈值和 `cluster_access/model_called/mutation_executed=false`；策略没有访问集群或调用模型。
- 按 replay 首个 policy-selected candidate 执行新 live canary：输出 `artifacts/phase14-policy-selected-guarded-canary-20260824-front-end-podkill-r1/`，显式 `minikube/sock-shop-lab`，单候选预算 1、operator approval=true。
- canary 验收：`live_completed`、preflight `ready_for_injection`、`availability_degraded`、RCA `confirmed`、cleanup `verified`、Chaos residual=0、front-end replacement 后 Ready；`knowledge_status=provisional`、`knowledge_base_updated=false`。
- 新增 `policy_selected_canary.json`，绑定 replay、denominator、context 和 execution contract SHA-256，且 `candidate_in_frozen_denominator=true`、`contract_matches_policy_selection=true`。
- 当前边界：旁路候选方法已完成 Sock Shop 的 runtime-backed shadow + 一次 guarded canary 验收；仍不能据此宣称全项目命中率提升、默认 rollout 或正式知识晋级。
- 最终验证：policy focused suite `32 passed, 1 warning`；全量 `tools/tests` `1228 passed, 1 warning, 5 subtests passed`；`python -m compileall -q tools` 和 `git diff --check` 通过。runtime assertion 检查 replay hash 相等、0 decision change、sidecar 两项一致性、分类/RCA/cleanup、知识库未更新和 Chaos residual=0。
- 收尾状态：Phase 14 complete；默认 policy mode 仍为 legacy，Online Boutique 空 runtime shadow 仍标记 `pending_runtime_evidence`，未自动扩大候选范围或写入正式知识库。
- 已按 `AGENTS.md` 使用 `email-notify`，success 通知已持久化到本地 pending outbox；通知内容未包含密钥、token 或完整文件内容。

# 2026-08-24 Phase 15 policy selection gate 接入完成

- `tools/policy_selection_gate.py` 已作为主流程旁路阀门：只消费冻结候选分母和结构化 policy state，不绕过 applicability gate、Oracle、RCA、recovery 或 cleanup。
- `tools/chaosatlas_batch.py` 已支持 `policy_mode`、state/context 输入和 policy budget，并把选择结果、执行结果、fallback、stop reason 与输入 hash 写入 batch manifest 和独立 JSON 工件。
- `tools/chaosatlas.py` 已支持四个 policy 参数；非 legacy 模式若未使用 `--all-candidates`/`--max-candidates` 会返回 `blocked_policy_mode_requires_batch`，防止参数表面生效而主流程未接入。
- 离线 smoke：Shadow 记录 `candidate-b` 但执行 legacy `candidate-a`；Guarded 执行 `candidate-b`；非法 state 回退 `candidate-a`，并记录 `fallback_reason=policy_error`。
- 验证：定向 suite `52 passed, 1 warning`；完整 `tools/tests` `1235 passed, 1 warning, 5 subtests passed`；compileall 与 diff check 通过。
- 状态：已达到项目实验开始前的接入验收点。本轮没有新的 Kubernetes mutation、没有模型调用、没有正式知识晋级。

# 2026-08-24 Phase 16 Online Boutique 非空 Shadow 回放

- 新增 `tools/project_runtime_projection.py`：把冻结候选池和历史 `unified-lifecycle-v1` 报告投影为 policy evaluator 可消费的确定性 runtime 反馈；未知候选、重复 replicate、生命周期不完整、混合分类均 fail-closed。
- 使用 Online Boutique same-pool-fair r3 候选文件冻结 55 个候选；仅纳入 `runtime_results-r2` 中 4 个候选的 8 份报告，每个候选两次 replicate 均为 `weakness_observed`，baseline/injection/recovery/cleanup/washout 全部通过。
- 投影结果为 4 条 `confirmed_weakness` policy feedback，但保留原始分类、源路径、源 SHA-256 和投影理由；这不是正式知识晋级或源码根因结论。
- 离线 replay 两次输出一致：`recorded_result_count=4`、`decision_changed=4`、`stop_reason=replay_exhausted`，replay SHA-256=`8e0107564612916397485ab9f2ad43081daa0bc9724ed1fdf2a3d7584b9605e4`。
- 四轮中 policy 均推荐尚未执行的 `adservice` CPU-stress 候选，Legacy 记录的是 cartservice/checkoutservice 四个候选；该差异仅说明策略建议不同，不等同于策略优越性。
- 验证：投影 focused suite `4 passed, 1 warning`；artifact assertions `9/9`；本轮无 Kubernetes mutation、无模型调用、无正式知识写入。

# 2026-08-24 第二项目 Online Boutique 离线接入复核

- 使用 `tools/tests/fixtures/chaosatlas_offline/online-boutique/project_profile.json` 执行统一 `chaosatlas run --mode dry-run`，输出为 `.tmp-online-boutique-knowledge-dryrun/`；没有 Kubernetes 连接、模型调用或 mutation。
- 同一编排器完整走通 `onboard -> inventory -> server_deployment_detection -> mapping -> retrieval -> hypotheses -> gate -> baseline -> execute -> observe -> classify -> rca -> learn -> promote_defense -> regression`，summary 状态为 `dry_run_ready`。
- Online Boutique 知识 root 为空，`retrieval.knowledge_status=read_only` 且 `cards=[]`；Sock Shop 的正式知识没有跨项目泄漏。
- 离线 inventory 发现 `frontend`/`payment` 两个 Deployment 和 12 个候选；服务器部署检测标记 `payment` 的 `singleton_availability_risk`，evidence plan 按单候选预算选择 `frontend/container_kill`，动作均为只读。
- 后续阶段明确为 `synthetic`：`finding_report.result=not_run`、`rca_status=not_run`、知识晋级为 `promotion_allowed=false`，回归意图均为不可执行 draft；因此没有把离线规划误报为漏洞或 RCA。
- 结论：跨项目的项目接入、知识隔离、服务器部署检测、候选映射和证据计划契约已验证；下一步是对第二项目建立独立 namespace 的真实只读 evidence smoke，再进行 runtime-backed shadow 对照，仍不默认切换 policy 或扩大 live 候选。

# 2026-08-24 第二项目 Online Boutique 真实只读 evidence smoke

- 显式使用 `minikube` context、`chaosatlas-online-boutique` namespace，通过现有 KubernetesProjectAdapter、服务器部署检测、候选映射、evidence planner 和 planned collector 完成真实只读采集；输出为 `.tmp-online-boutique-runtime-evidence-smoke/`。
- 实际 inventory 为 11 个 Deployment、12 个 Service、0 个 Pod，生成 66 个服务器部署候选；按单候选预算选择 `frontend/pod_kill`，Deployment 与 Service target 均正确绑定到 `frontend`。
- 7 个计划动作中 4 个证据 `supports`（Deployment、Pod state、Service、Events），1 个日志动作因无运行中 Pod 返回 `unavailable`；所有记录均带 `planned_action_id`，不可用证据没有被解释为弱点或防御。
- 审计状态为 `passed`，`runtime_executed=false`、`model_called=false`、`formal_knowledge_written=false`；未调用 live executor、未执行 apply/scale/delete/patch，Chaos 资源残留为 0。
- 环境边界：Online Boutique 当前所有 Deployment 都是 `0/0`，所以尚不能执行业务 Oracle、注入、恢复、RCA 或 runtime shadow；下一步需在该独立 namespace 恢复可用副本，并经过显式 live approval 后做单候选 shadow。

# 2026-08-24 Online Boutique runtime shadow 与弱点知识晋级

- 在隔离 namespace `minikube/chaosatlas-online-boutique` 将 11 个 Deployment 恢复到 1 副本，全部通过 Available，frontend HTTP `/` 基线连续返回 200。
- 首次 runtime shadow 输出 `.tmp-online-boutique-live-shadow-r4/`：单候选 `frontend/pod_kill` 注入确认，观察到短暂业务不可达后恢复，分类 `availability_degraded`，RCA `confirmed`，cleanup `verified`，正式知识未写入。
- 第二次同 seed 重复的 `run_id` 与首轮相同，未用于晋级；改用 seed `1002` 的独立输出 `.tmp-online-boutique-live-shadow-r6/`，结果同样为 `availability_degraded`、RCA `confirmed`、cleanup `verified`，且执行哈希与 Pod UID 均不同。
- 使用 r4+r6 通过 `weakness_promotion_stage` 两次独立复现门禁，生成并发布 `KB-WEAK-9faeb7cf3d7059da`，状态 `local_reusable`，有效复现 2 次，生成 `reproduce` 和 `guard` regression intents。
- 正式知识目录为 `artifacts/knowledge/weakness-online-boutique-frontend-pod-kill-r4-r6/`；旧版 `validate_knowledge_base.py` 依赖另一种 index/card schema，不能作为新版 weakness promotion card 的验证器，promotion stage 结果才是本阶段权威结果。
- 回流验证：使用该 knowledge root 重新 dry-run，检索到 1 张 Online Boutique 卡，候选首选回到 `server:deployment:online-boutique:frontend:pod_kill`，7 个证据动作按预算生成；当前 namespace 副本保持 1，Chaos 残留为 0。

# 2026-08-24 Phase 12 正式知识写入与批量 context 贯通

- 使用统一 `chaosatlas run` dry-run 验证显式 `--defense-history-root` + `--knowledge-write-root`：两次独立 redundancy history 晋级为 `KB-DEF-cf55cc7c4470c9b6`，独立写入 `defense_card.json`、兼容卡副本和 `regression_intents.json`；原正式知识目录未覆盖。
- `knowledge_promotion.json` 记录 `status=promoted`、`valid_reproductions=2`、`defense_claim_type=redundancy` 和 stop rule；Phase 6 audit 的 `knowledge_base_updated=true`。
- 批量 `run_live_batch` 和 `--all-candidates/--max-candidates` 贯通 `kube_context`：规划器、每个子运行的 inventory/preflight/evidence/lifecycle 都使用显式 context。
- 真实 batch 无批准 smoke 在 `minikube/sock-shop-lab` 发现 6 个 Oracle 覆盖候选，执行 2 个子运行；两个均在 live approval 门前 `environment_blocked`，preflight context 均为 `minikube`，未发生 apply/delete/Chaos 注入，残留为 0。
- 验证：新增批量 context 测试通过；formal knowledge dry-run `dry_run_ready`；批量 smoke 无 mutation；Phase 12 focused suite `68 passed`，compileall 和 `git diff --check` 通过。

# 2026-08-24 Phase 19 Guarded r1 diagnosis and r2 verification

- 根因证据：Guarded r1 的 `container_kill` 注入确认，目标 Pod UID 保持不变；容器旧状态 `exitCode=137`，当前容器 `restartCount=1`、Ready，HTTP 观察从短暂连接失败恢复到 200。旧恢复门只接受新 Pod UID，因此产生 `recovery=false`、`comparison_eligible=false` 的误判。
- 先写 RED 回归：container restart contract、evidence planner、lifecycle hook 和 runtime helper 测试按旧行为失败；实现后通过 GREEN。
- 新增 `tools/recovery_contract.py`：`pod_kill` 使用 `pod_replacement`；`container_kill` 使用 `container_restart`，`replacement_identity_required=false`、`container_restart_required=true`。
- `wait_for_container_ready` 按目标 Pod 的 container restartCount 增长、Ready、期望副本数和连续稳定检查判定恢复；PodKill 原有 UID replacement 检查未放松。
- 接入范围：`kubernetes_project_adapter.py`、`chaosatlas_adapters.py`、`build_deployment_capability_pool.py`、`evidence_action_planner.py`、`kubernetes_lifecycle_executor.py`、`run_chaos_experiment.py`、`chaosatlas.py`。
- 定向验证：recovery/contract/evidence/lifecycle `20 passed`；adapter/compile/runner `28 passed`；chaosatlas evidence suite `40 passed`；仅有受限 pytest cache warning。
- Guarded r2：`artifacts/phase17-online-boutique-guarded-live-20260824-r2/`，policy `guarded`，Legacy=`frontend/pod_kill`，policy/execution=`frontend/container_kill`，`decision_changed=true`、`fallback_used=false`。
- r2：`live_completed`，observe=`pass`，recovery=`container_restart`，restartCount `0 -> 1`，attestation `valid=true`、`comparison_eligible=true`，cleanup=`verified`，Chaos residual=0；classification=`response_observed`，RCA=`bounded`，knowledge=`provisional`，正式知识库未更新。
- r2 运行工件生成于机制文案修复前，历史机制文件保持 append-only；代码和回归测试已改为按 recovery mode 生成准确解释，不回写历史工件。

# 2026-08-24 Phase 20 P02 productized runtime closure

- P02 namespace `minikube/chaosatlas-p02` 已恢复为 10 个 Deployment、10 个 Service、10 个 Ready Pod；HTTP Oracle `GET /api/gateway/owners/1` 基线通过。
- 真实只读 inventory/服务器部署检测生成 60 个候选；首个候选为 `server:deployment:39ebc79a28193a1a21380fdc:pod_kill`，证据计划使用显式 `minikube` context。
- `r1` 和 `r4` 两次不同 seed 的 live run 均为 `live_completed`，PodChaos injection/recovery、业务观察、replacement UID、RCA confirmed 和 cleanup verified 全部通过；运行后 Chaos residual=0。
- `r2` 没有作为重复样本：事件文件只包含旧 `r1` 的 PodChaos 事件，且 executor 没有 lifecycle attestation；`r3` 在注入前因瞬态 `BadStatusLine` 基线失败，未执行 mutation。
- 新增 executor fault boundary provenance、PodChaos event `involvedObject.name` 过滤和 baseline HTTP protocol failure 短窗口重试；相关 focused suite `22 passed`，证据规划/lifecycle suite `21 passed`，compileall 通过。
- 通过 `tools/weakness_promotion_stage.py` 使用 `r1+r4` 晋级 P02 独立知识卡 `KB-WEAK-172535b133dde433`，状态 `local_reusable`，有效复现 2 次，并生成 reproduce/guard regression intents；写入 `artifacts/knowledge/weakness-p02-api-gateway-pod-kill-r1-r4/`。

# 2026-08-24 P02 offline identity and knowledge replay follow-up

- 全量回归首次暴露 P02 离线 fixture 的 profile/facts identity mismatch；没有放宽生产校验。
- `tools/chaosatlas.py` 现在在正式 profile 使用大写 project_id 时选择 `project_facts_runtime.json`，小写测试 fixture 继续使用 `project_facts.json`，避免 Windows 大小写不敏感路径串用 facts。
- 新增 `test_p02_runtime_profile_uses_exact_case_facts_variant`；三项目离线编排和该回归共 `4 passed`，随后全量 `tools/tests` 为 `1261 passed, 5 subtests passed`，compileall 通过。
- 成对 P02 dry-run 输出：
  - 无知识：`artifacts/p02-phase20-no-knowledge-replay-r1/`，retrieval cards=0，首候选 `server:deployment:P02:admin-server:container_kill`。
  - 加载 P02 知识：`artifacts/p02-phase20-knowledge-replay-r1/`，检索到 `KB-WEAK-172535b133dde433`，首候选变为 `server:deployment:P02:api-gateway:pod_kill`。
- 两次均为 `dry_run_ready`，候选数 60，claim scope 为 `static/synthetic`；未调用模型、未执行 mutation、未写正式知识库。
- 修复并验证既有 ablation completed-resume 的 wall-clock 非确定性：checkpoint 与首次返回现在共用同一 payload；相关回归 `2 passed`，最终全量 `tools/tests` 为 `1262 passed, 5 subtests passed`。
- 最终检查：`compileall -q tools` 通过，`git diff --check` 通过，P02 两个 dry-run artifact assertions 通过。

# 2026-08-24 OTel Demo runtime preflight

- 只读检查 `minikube/chaosatlas-otel`：namespace Active，11 个 Deployment、11 个 Service、11 个 Pod，全部 Ready/Running。
- 统一 live batch 输出：`artifacts/opentelemetry-demo/chaosatlas-preflight-20260824-r2/`；单候选计划为 `server:deployment:e6b73b454a44174b26e2ceb6:pod_kill`。
- 子运行在 `gate` 因 `live execution requires explicit approve_live` 停止；其 `preflight.json` 为 `ready_for_injection`，gRPC `PlaceOrder` Oracle 已配置，Chaos residual 全部 clean。
- 本轮 `injection_performed=false`、未调用 live executor、未产生 RCA/知识晋级；下一步需要用户明确批准一个 OTel Demo 单候选 Shadow。

# 2026-08-24 OTel Demo single-candidate Shadow

- 用户明确批准后执行 `minikube/chaosatlas-otel` 单候选 `checkout/pod_kill`；输出为 `artifacts/opentelemetry-demo/chaosatlas-shadow-live-20260824-r5/`。
- lifecycle 全部通过：baseline gRPC PlaceOrder 10/10，注入确认，观察首个请求因 checkout replacement 短暂不可达，随后 10 次业务请求成功，replacement Pod Ready，cleanup verified。
- 运行结果：batch `completed`，classification=`availability_degraded`，RCA=`confirmed`，knowledge=`provisional`，formal knowledge unchanged；生成 1 个 reproduce regression intent。
- 独立复核：11 个 Deployment 全部 Available、checkout replacement Pod Running，Chaos Mesh PodChaos/NetworkChaos/StressChaos/HTTPChaos/DNSChaos/IOChaos/TimeChaos/Schedule/Workflow 均无残留。
- 机器断言通过：`attestation.valid=true`、`comparison_eligible=true`、`injection_confirmed=true`、`recovery.confirmed=true`、`cleanup_confirmed=true`；OTel Shadow artifact assertions passed。

# 2026-08-24 OTel Demo deterministic feedback reflow

- Produced `artifacts/opentelemetry-demo/chaosatlas-guarded-feedback-20260824/` containing before/after policy state, aggregate input, audit, and guarded replay.
- r2 and r3 each carried valid baseline, injection, observation, recovery, cleanup, and independent-oracle attestation. The feedback protocol converted the pair from raw `availability_degraded` to policy classification `confirmed_weakness`.
- `container_kill` state is now `weakness` with posterior `{weakness: 0.85, protected: 0.05, below_threshold: 0.10}`. r1 remains `response_observed`/`bounded` and is explicitly non-confirming.
- Offline replay changed the recommendation from `container_kill` to `network_loss`; stop stayed open because unresolved candidates remain. Replay flags confirm no cluster access, model call, mutation, or formal knowledge write.
- Explicit `minikube` verification found the OTel namespace Active, 11/11 workloads Ready/Running, no Chaos resources, and no `.guarded-grpc-runtime` directory. Current kube context was not changed.

# 2026-08-24 OTel Demo network-loss guarded preflight

- Ran `artifacts/opentelemetry-demo/chaosatlas-guarded-preflight-network-loss-20260824/` with the feedback-updated policy state and `policy_budget=1`.
- Policy selected `server:deployment:e6b73b454a44174b26e2ceb6:network_loss`; `decision_changed=true`, `fallback_used=false`, and the candidate remained inside the six-candidate denominator.
- Runtime preflight was `ready_for_injection` on explicit `minikube`: 11/11 workloads ready, checkout gRPC Oracle configured, and PodChaos/NetworkChaos/StressChaos/HTTPChaos/DNSChaos/IOChaos/TimeChaos/Schedule/Workflow all clean.
- Because `approve-live` was intentionally omitted, the gate returned `environment_blocked` before mutation. `injection_performed=false`; no RCA, classification, cleanup mutation, or formal knowledge write occurred.

# 2026-08-24 OTel Demo network-loss guarded execution attempt

- Approved guarded execution selected `server:deployment:e6b73b454a44174b26e2ceb6:network_loss` with no policy fallback.
- First attempt was correctly fail-closed because generated `NetworkChaos` omitted `spec.mode`; patched `tools/compile_scenario_node.py` to emit `mode: one` for stress/network families and added a regression assertion in `test_chaosatlas.py`.
- Second attempt passed runtime applicability preflight with `mode=one`, but stopped before injection at business baseline: `.venv` cannot import `google.protobuf` from the generated OTel client.
- The dependency install request for `grpcio`/`protobuf` was rejected by the external approval service with HTTP 502; no local wheel cache exists. No workaround or unsafe bypass was attempted.
- Final safety check: `chaosatlas-otel` Active, 11/11 workloads Ready/Running, all Chaos residual classes clean. Focused suite `26 passed, 5 subtests passed`; compileall and diff check passed.

# 2026-08-24 OTel Demo dependency unblock attempt

- Continued after user approval and retried installation of `grpcio>=1.83.0` and `protobuf>=7.35.1` into `.venv`.
- External permission review timed out on both allowed retries. No installation occurred, and no workaround was attempted.
- No offline wheel cache, `grpcurl`, `grpc_cli`, or `protoc` alternative exists on the machine. The gRPC baseline therefore remains unavailable.
- The cluster remains safe: no Chaos resources, no mutation, and the previously verified 11/11 Ready workloads remain the only runtime state.

# 2026-08-25 OTel Demo dependency permission check

- A read-only recheck found `.venv\Lib\site-packages` entries for `google`, `grpc`, `grpcio-1.83.0.dist-info`, and `protobuf-7.36.0.dist-info`, created during the failed installation attempts.
- The current user cannot read those directories (`Access denied`), so `google.protobuf` and the generated OTel client still fail to import.
- An elevated read-only import check was rejected by the external approval service. No ACL workaround was attempted.
- `chaosatlas-otel` has no active Chaos resources and all 11 Pods remain Running; no new mutation occurred.

# 2026-08-24 OTel Demo weakness promotion and knowledge replay

- r5 and r7 are independent `checkout/pod_kill` runtime runs: `live-bd6615973e93`/seed `1001` and `live-aa28cef942de`/seed `1002`; both are `availability_degraded`, RCA `confirmed`, cleanup `verified`, with complete lifecycle attestation.
- r6 was explicitly excluded because it was produced before the batch seed-propagation fix and reused the r5 run identity.
- `weakness_promotion_stage.py` returned `status=promoted`, card `KB-WEAK-fd0bcc9a763e4bdf`, `knowledge_status=local_reusable`, and `valid_reproductions=2`; the card preserves both run fingerprints, evidence references and project commit.
- Generated regression intents are `reproduce` and `guard`, bound to the same gRPC PlaceOrder Oracle, `same project and commit`, and the recorded stop rule.
- Publication is isolated under `artifacts/opentelemetry-demo/knowledge_base/chaosatlas-runtime-20260824-r1/`; existing OTel cards were not overwritten.
- OTel dry-runs with and without the card are both `dry_run_ready`, candidate count 66, `claim_scope=synthetic`, and RCA `not_run`; retrieval changes from 0 to 1 card while the checkout PodKill boundary remains first.
- Final full verification passed: `1263 passed in 33.73s`; no new Kubernetes mutation or model call occurred.

# 2026-08-24 Sock Shop third-project runtime closure

- 显式使用 `minikube/sock-shop-lab` 做只读健康检查：namespace Active，14 个 Deployment 全部 `1/1`，业务 Pod Ready，front-end Oracle 可用，Chaos residual 为空。
- 无审批的首个 batch 只在 `gate` 因 `live execution requires explicit approve_live` 停止，不计入 runtime 重复，也没有发生 mutation。
- r1 `live-60df2cdfe869`/seed `3001` 与 r2 `live-a6269a1b2195`/seed `3002` 均完成 baseline、injection、observation、recovery、cleanup 和 independent oracle attestation；分类均为 `availability_degraded`，RCA `confirmed`，cleanup `verified`。
- 通过 `weakness_promotion_stage.py` 晋级 `KB-WEAK-452bd9a809fa41f2`，状态 `local_reusable`，有效复现数 2，卡片绑定 Sock Shop runtime commit `6e83eb6ffdf1bce43e332337a3bb0fc40327d039`、front-end deployment/service boundary 和两次 evidence fingerprint。
- 生成的 regression intents 为 `reproduce` 和 `guard`，并写入独立 history/promotion/knowledge roots；没有覆盖既有 Sock Shop 或其他项目知识。
- 无知识/加载本轮卡片的 dry-run 均为 `dry_run_ready`、候选数 12、`claim_scope=synthetic`、RCA `not_run`；retrieval 从 0 张变为 1 张，首候选保持 front-end PodKill。
- 本阶段没有扩大候选批次、没有模型调用，也没有把 dry-run 结果当作新漏洞或 RCA。
# 2026-08-24 Phase 26 knowledge consumption contract

- `KnowledgeProvider.retrieve()` now filters formal weakness cards by exact `project` and optional `project_commit`, returning deterministic rejection reasons.
- Added `knowledge_consumption.json` to every unified run. It records accepted cards, rejected cards, rejection counts, target identity and whether cross-project pending knowledge exists.
- Added `tools/knowledge_migration_audit.py` for offline multi-root validation. Foreign cards remain `cross_project_pending` and are never executable.
- Added flat `chaosatlas-weakness-knowledge-v1` validation with independent evidence-run, RCA, promotion-audit and regression-intent checks.
- Verification complete: focused contract/orchestrator tests `47 passed`; full `tools/tests` `1268 passed`; compileall, diff hygiene and all four project flat-card validations passed.
- Offline CLI smoke `.tmp-phase26-sock-consumption-r2/` generated `knowledge_consumption.json`; the fixture card was correctly rejected as `project_commit_mismatch`, proving the commit pin is enforced.
- Remaining product gates: Phase 27 structured improvement retest acceptance; Phase 28 three-project one-command acceptance and explicit guarded-default decision.

# 2026-08-24 Phase 27-28 final acceptance

- Phase 27 reused the existing isolated Sock Shop improvement evidence: same scenario/oracle/recovery/cleanup contract, `improvement_verified`, cleanup verified, and deployment-boundary redundancy knowledge with two independent evidence runs.
- Phase 28 added `tools/final_acceptance.py` and a deterministic report contract. The real report `.tmp-phase28-final-acceptance-r1/final_acceptance.json` is `passed` with 4 accepted project-local knowledge roots, 3 synthetic dry-run records and 1 verified improvement record.
- The report explicitly records `kubernetes_mutation=false`, `llm_called=false`, `formal_knowledge_written=false`, and `default_policy_decision=retain_legacy`.
- The product gate is complete with guarded/default rollout intentionally disabled; future live expansion must still use explicit approval and project-specific safety budgets.

# 2026-08-25 OTel Demo network-loss canary recovery

- The protected `.venv` still contains `grpcio`/`protobuf` directories that the current user cannot read. The project-local `.venv-otel-runtime` is complete and imports both `google.protobuf` and `grpc` successfully, so the gRPC Oracle contract was preserved without rebuilding or deleting `.venv`.
- Fresh preflight on `minikube/chaosatlas-otel` passed: 11/11 workloads Ready, the CheckoutService gRPC Oracle configured, and all Chaos residual classes clean.
- The approved guarded single-candidate run selected `server:deployment:e6b73b454a44174b26e2ceb6:network_loss` and completed with baseline 10/10, confirmed Apply/Recover lifecycle, transient `availability_degraded` observation, RCA `confirmed`, cleanup `verified`, and `confirmed_finding_count=1`.
- Post-run cluster verification returned zero `networkchaos`, `podchaos`, `stresschaos`, `httpchaos`, `dnschaos`, `iochaos`, `timechaos`, schedules and workflows; all 11 OTel Pods remained Running.
- No policy-state or formal-knowledge write was performed: this is one replicate, so the existing two-replicate feedback gate remains closed and the generated knowledge artifact is `provisional` only.

# 2026-08-25 OTel Demo `.venv` ACL repair

- With explicit administrator authorization, recursively granted the active Codex sandbox user access only to `.venv\Lib\site-packages\google`, `grpc`, `grpcio-1.83.0.dist-info`, `protobuf-7.36.0.dist-info`, plus the `typing_extensions.py` and matching dist-info path that the runtime actually reported as unreadable.
- `icacls` completed every target with zero failed files. The original `.venv` now imports `google.protobuf` and `grpc`, and `pip show` reads `grpcio 1.83.0` and `protobuf 7.36.0`.
- Verification of `tools/tests/test_experiment_policy_feedback.py` passed (`4 passed`). The prior `.venv-otel-runtime` fallback remains intact and was not deleted.

# 2026-08-25 OTel Demo network-loss dual-replicate feedback

- Reused the repaired original `.venv` for a fresh `seed=1002` preflight and live run. Preflight passed with 11/11 workloads ready, the gRPC PlaceOrder Oracle configured, and all residual Chaos classes clean.
- The second run is distinct (`live-aa28cef942de`) and completed the full lifecycle with `availability_degraded`, RCA `confirmed`, cleanup `verified`, and valid baseline/injection/observation/recovery/cleanup/independent-oracle attestation.
- Aggregated the two independent runs (`live-bd6615973e93`, `live-aa28cef942de`) with immutable source hashes under `artifacts/opentelemetry-demo/chaosatlas-guarded-feedback-20260825-network-loss/`.
- `experiment_policy_feedback` updated only the copied project-local policy state: `network_loss` is now `weakness`, evidence quality is `complete`, and the state history contains the prior `container_kill` plus this aggregate feedback event.
- Offline replay selects `network_partition` next and keeps `stop_reason=null`; no model call, Kubernetes mutation, formal knowledge write or default guarded rollout occurred during feedback.

# 2026-08-25 NGINX Kubernetes Ingress deployment preparation

- User requested a plan and progress table for deploying `nginx/kubernetes-ingress` before the ChaosAtlas method is fully frozen.
- Current session is planning-only: no Helm install, `kubectl apply`, fault injection, model call, credential read, or knowledge write was performed.
- Deployment plan saved to `docs/superpowers/plans/2026-08-25-nginx-kubernetes-ingress-deployment.md`.
- Current status: M0 scope/safety boundary complete; M1 read-only cluster preflight through M7 handoff pending.
- Required next gate: verify the current cluster and existing ingress-controller state, then freeze release/chart/values/image-digest provenance before requesting live deployment approval.

# 2026-08-25 Cross-project policy rollout continuation

- Confirmed Online Boutique recovery baseline: 11/11 Deployments available, namespace Active, zero Chaos resources after manual residual cleanup and frontend rollout restart.
- Inspected guarded-r2, legacy, and shadow network_loss artifacts. Guarded-r2 cleanup failed closed because deletion verification saw the resource still present immediately after a successful delete command.
- Next action is TDD for asynchronous cleanup verification; no production fix or new live mutation has been made in this turn yet.

# 2026-08-25 Legacy/Shadow/Guarded comparison completed

- Added a failing regression for delete-then-eventual-NotFound cleanup and fixed `tools/run_chaos_experiment.py` to recheck only the transient `exists` state within the bounded timeout. NotFound, timeout, RBAC and API error paths remain fail-closed.
- Verification: cleanup remediation suite `17 passed`; focused lifecycle/orchestrator/batch suite `75 passed` with repository-local basetemp.
- Online Boutique guarded-r3 confirmed the fix on `network_loss`: cleanup changed to `verified`, but two preflight blocks required a stable rerun.
- Online Boutique guarded-r4 completed 5/5: 3 confirmed findings, 3 RCA confirmed, cleanup 5/5 verified, no failed or blocked rounds, stop `budget_exhausted`.
- Cross-project comparison is recorded in `reporting/policy_rollout_comparison_2026-08-25.md`; guarded remains a validated experimental mode, not an automatic default.
# 2026-08-25 项目全量画像与假设注册表

- 用户确认主线：项目全量画像 → 大量架构/配置/依赖/运行时假设 → 价值排序 → 少量候选执行 → RCA/Issue/知识回流。
- 已完成代码勘察：现有 `tools/chaosatlas_hypothesis.py` 负责候选排序和 advisory 解析，但没有独立的项目画像/假设注册表 artifact。
- 已创建实现计划：`docs/superpowers/plans/2026-08-25-project-portrait-hypothesis-registry.md`。
- 当前状态：计划与持久化上下文已更新，下一步按 TDD 先添加注册表失败测试。

## 完成记录（2026-08-25）

- `tools/hypothesis_registry.py` 已完成并通过稳定性、去重、五类假设和未知 PDB 证据边界测试。
- `tools/chaosatlas.py` 已在 retrieval 后生成 `project_portrait.json` 与 `hypothesis_registry.json` advisory artifacts；resume 会复用已有产物。
- 相关回归：`60 passed`；`python -m compileall -q tools/hypothesis_registry.py tools/chaosatlas.py` 通过。
- fresh dry-run：`dry_run_ready`；23 条假设、12 条 runtime execution-eligible、执行预算 1；未调用 live executor，未写入正式知识库。
- 阶段状态：完成。保留边界：registry 尚未接入 policy 选择，下一阶段先做 shadow 评估和覆盖质量门。

## Registry Shadow 阶段完成（2026-08-25）

- 新增 `tools/registry_shadow.py` 与 `tools/tests/test_registry_shadow.py`，覆盖健康注册表、fail-closed 错误、静态假设排除、排序差异和确定性。
- `chaosatlas run --registry-shadow` 现在会写出质量报告和 policy shadow 报告；不带开关的默认运行不产生这两个文件。
- 相关编排器回归：`61 passed`；`python -m compileall -q tools/registry_shadow.py tools/chaosatlas.py` 通过。
- Sock Shop 和 Online Boutique fresh dry-run 均 `dry_run_ready`，质量均 `passed`；重复 Sock Shop 报告稳定。
- 阶段状态：完成。下一阶段是基于 shadow 结果评估 registry runtime 优先级是否具备进入 guarded policy 的证据，不自动切换默认策略。

## Registry Policy Signal 阶段完成（2026-08-26）

- 已完成 signal adapter、bounded scoring、batch context 接入和 shadow/guarded ledger。
- 相关回归：`82 passed`；`compileall` 通过；Sock Shop/Online Boutique fixture signal 均 `ready`。
- shadow 实际执行保持 legacy；guarded 仅允许 registry runtime allow-list 候选；无 signal 时默认 policy 路径不变。
- 未执行 Kubernetes mutation，未更新正式知识库；真实 guarded canary 需下一阶段单独批准。

## NGINX Registry Guarded Canary 结果（2026-08-26）

- 已执行一次显式批准的 NGINX 单候选 guarded canary，前置 namespace/workload/residual 检查通过。
- 生命周期安全结果：1/1 completed，`response_observed`，RCA `bounded`，cleanup `verified`，Chaos residual 为 0；没有 confirmed finding。
- registry-policy-input 为 `fallback: quality_not_passed`，原因是 live inventory 未提供 dependency edges，导致 registry 五类质量门缺少 dependency 类。
- 阶段状态：运行安全通过但 registry signal 验证为 partial；下一步先补齐 live dependency portrait/unknown-category 处理，再重跑一轮 registry-enabled guarded canary。

## NGINX Registry Dependency Portrait 修复与 Guarded 重测（2026-08-26）

- 已补齐 live adapter 的 Ingress 路由、Service selector→Deployment 依赖边和 profile 业务 Oracle；依赖观测保持只读，Ingress 查询失败只产生 warning。
- adapter、hypothesis registry、registry shadow、registry signal、batch 回归共 `28 passed`。
- NGINX 重测输出：`artifacts/policy-rollout/nginx-ingress-registry-guarded-20260826-r2`。registry quality `passed`、signal `ready`，dependency=3，假设总数 23；guarded 第一轮从 legacy 的 `pod_kill` 切换到 `container_kill`，`decision_changed=true`。
- live 生命周期 `1/1 completed`，RCA `confirmed`，cleanup `verified`，confirmed finding=1；未写入正式知识库。重测后 Chaos 资源为空、两个 Deployment 均 Ready。
- 阶段状态：live registry signal 已完成一次真实生效验证；仍需更多候选/重复和第二项目验证，不能将单轮结果外推为跨项目稳定性结论。

## NGINX Guarded Budget-10 批次结果（2026-08-26）

- 已按预算 10 启动 guarded 批次；当前 live candidate pool 只有 6 个，因此实际完成 6 轮，第 7 轮因候选耗尽以 `blocked` 停止，未重复注入。
- 6/6 生命周期完成，cleanup 全部 verified；4 个故障得到 RCA confirmed 的 `availability_degraded`，2 个压力故障因证据不完整保持 unsupported。
- registry signal 全程 ready，无 fallback；批次未写入正式知识库。
- 阶段状态：停止策略已验证能正确区分“预算未耗尽但候选空间已耗尽”。下一阶段是扩展并冻结 NGINX 新候选契约和压力证据契约，再进行第二轮预算 10 验证。

## NGINX PodKill 独立重复与 Issue 草案（2026-08-26）

- 已用新 seed 完成 `pod_kill` 独立重复；两次运行因果身份一致，业务退化和恢复结果一致，生命周期与 cleanup 全部通过。
- 已生成用户审核用 Issue 草案：`reporting/nginx-kubernetes-ingress/issues/2026-08-26_single-replica-ingress-availability.md`。
- 当前状态：可以提交一个边界明确的项目级可用性 Issue；正式知识晋级仍需保持 project-local 范围并等待外部审核结果。

## 三项验收收口结果（2026-08-26）

- Online Boutique registry-ready guarded canary 与独立重复完成，证明新 registry signal 可跨到第二个真实项目；两次均无 cleanup 残留。
- NGINX 候选契约 catalog 完成并绑定 live 执行边界：10 类总契约、6 类 executable、4 类 pending method freeze。
- 全量测试使用项目 basetemp 通过：`1310 passed, 5 subtests passed`；系统 Temp ACL 仍待管理员处理，pytest cache warning 已知且不影响结果。
- 当前主线状态：核心组合方法可受控使用；要达到“任意项目一条命令、所有候选自动执行并自动晋级知识”的最终形态，仍需实现新增 executor、第二项目更多覆盖和 promotion gate 验证。

## 方法身份与覆盖统计固化（2026-08-26）

- 新增 `tools/problem_identity.py`：完整 runtime lifecycle、RCA confirmed 和 cleanup verified 才能进入有效问题统计；`weakness_id` 保留故障方法差异，`issue_id` 聚合同一项目/目标/业务表面的多种故障方法，`causal_cluster_id` 继续保持方法级因果身份。
- 新增 `tools/coverage_report.py`：只读扫描 RCA artifacts，区分 artifact、有效运行、独立 weakness 和独立 issue；当前扫描 `artifacts/` 得到 149 个 RCA artifacts、66 个有效运行、15 个唯一 confirmed weakness、5 个独立问题、5 个有归属项目，27 个无项目归属历史 artifacts 被单独计数。
- 当前按项目的独立问题统计为：NGINX 1、Online Boutique 1、OpenTelemetry Demo 1、P02 1、Sock Shop 1；这是按当前问题表面聚类的统计，不代表所有生产故障域已经覆盖。
- 新增 `tools/fault_executor_registry.py`，并让 `tools/nginx_candidate_contracts.py` 校验 executor 状态；6 个基础方法保持 ready，`network_delay`、`backend_pod_kill`、`config_reload`、`replica_reduction` 继续 pending_method_freeze，不允许 live。
- focused regression：10 个身份/覆盖/执行器/NGINX 契约测试通过；全量 `tools/tests` 为 `1318 passed, 1 warning, 5 subtests passed`，`compileall tools` 通过。
- 扩展前仍需把 coverage report 接入批次汇总，并为 4 个 pending 方法补齐真实 executor；本次没有执行 live mutation，也没有更新正式知识库。

## 仓库结构整理与 GitHub 发布准备（2026-08-26）

- 完成仓库全量 inventory：321,434 个文件，主线源代码/测试 1,169 个，实验输入 1,935 个，生成证据 22,063 个，外部源码 38,194 个，本机生成 257,765 个；未分类 0 个。
- 新增 `docs/REPOSITORY_MAP.md`、`docs/REPOSITORY_CLEANUP_POLICY.md`，明确产品、输入、证据、归档和永不提交数据边界。
- 新增 `tools/repository_inventory.py` 与 2 个回归测试；修复隐藏目录和外部源码路径分类后 focused suite 为 `2 passed`。
- `.gitignore` 增加根目录临时文件、`.tmp/`、`.pytest-cache-disabled/`、通知队列、OTel 本地虚拟环境和 inventory 输出规则。
- 尚未移动或删除任何实验数据；全量测试和选择性提交审查待完成。

## GitHub 发布完成（2026-08-26）

- 本地整理提交 `cd2f45e` 已推送到 `origin/remediation/2026-08-09-review`。
- `git ls-remote` 已核对远端指针为 `cd2f45e71ca26bc9f91adc3f220d85e0af95b04f`。
- 工作树中剩余的 artifacts 变更和未跟踪实验目录仍按清理政策保留在本机，未进入本次发布。
