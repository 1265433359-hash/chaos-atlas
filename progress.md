# Progress

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
