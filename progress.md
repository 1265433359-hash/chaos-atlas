# Progress

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
