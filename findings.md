# Findings

## Prior consumption, reproduction, and third migration (2026-08-21 evening)

- The validated prior is now a live decision input, not just an archived verdict: OB kill candidates matching the card get the local_reusable boost plus the observation-window-artifact diagnostic, and unrelated candidates are byte-identical with/without the snapshot. Fail-closed gate: an un-validated verdict cannot produce a retrieval snapshot at all.
- Two independent OB runs (r4/r5) and a third migration to P02 Spring Petclinic (Java/Spring Cloud, gateway oracle) all reached `prior_validated`. The mechanism held across Go/Node and Java stacks; arm B co-proof was 30/37, 31/38, and 70/70 respectively.
- Oracle fidelity decides card closure: the Sock Shop `/` page returns HTTP 200 with an empty product grid while the catalogue chain is broken, so the home page cannot detect a catalogue-db outage. Switching to the `/catalogue` JSON oracle (contract = product array marker) turned an inconclusive run into 54 synchronized outage samples. Closure r1 is retained as evidence of this trap.
- The stateful-singlet case (catalogue-db, mongo) still validated the redundancy mechanism because each replica self-seeds at startup; the closure runner was built to accept the honest opposite outcome (`naive_scale_out_not_a_defense`) rather than forcing promotion.
- The HTTP abort card closed with `transport_abort_propagates`: confirmed Response abort on the front-end->catalogue edge surfaced as HTTP 500 at the oracle with no graceful degradation; no redundancy counterfactual applies to an edge fault, recorded as an explicit exclusion.
- Spring Cloud cold start is an environment fact, not a method failure: the P02 gateway route needed >5 minutes after pod Ready; r1's 300-second baseline window is retained as failed evidence and the runner's window was extended to 1800 seconds.

## Cross-project RCA knowledge projection (2026-08-21)

- The human review decision is now machine-consumable: `project_sock_shop_rca_cross_project.py` refuses to run unless `human_review_decision.json` authorizes projection, and re-derives every evidence claim from the archived artifacts (AllInjected condition, outage timeline sample, empty residue, counterfactual co-proof, replica restoration) instead of trusting the review summary.
- The projection carries an intentionally lossy abstraction: applicability, expected effect, the observation-window-artifact warning, and a scale-out verification recipe. Pod UIDs, sock-shop service names, HTTP samples, and mutation paths stay in the sock-shop audit card (`FA-7ff5b1794a0758d4`) and never enter the Online Boutique KB snapshot.
- `classify_outcome` gates the projection: with the r1+r2 reproductions and complete evidence chain the result is `confirmed_weakness`; without them the tool fails closed rather than projecting a weaker claim.
- The projected prior is provisional by decision. Promotion requires the Online Boutique counterfactual (two-replica kill with surviving-UID proof on one of its single-replica services); until then the OB formal knowledge-base directory is untouched.

## RCA local_reusable retrieval + decision guard (2026-08-21)

- The closed front-end pod-kill line now reaches the decision engine as a guard, not a boost: a matching `local_reusable` card with `closed_boundary=true` (derived from the kind=guard regression intent `closed_runtime_boundary_no_reinjection`) keeps the baseline score and blocks re-injection while preserving next-evidence diagnostics.
- The rca_snapshot projection is deliberately lossy: only engine-consumed fields plus source path/SHA-256 provenance are exported. Evidence dumps stay in the round directory, so retrieval cannot leak raw evidence into ranking inputs.
- Same-project replay on the real r4-final round: both front-end pod-kill candidates are retrieved by family/operation and edge, and all three unrelated candidates rank identically with and without the snapshot — the guard changes only the closed line's decision context.
- Boundary: this is project-local retrieval only. Cross-project reuse still requires human review plus the existing feedback protocol; the formal KB remains untouched.

## Phase 0 project onboarding (2026-08-20)

- A project profile is now a schema/input contract, not proof that a project is runtime-ready. The CLI reports `ready_for_static_analysis` and explicitly leaves runtime as `not_checked`.
- Result claims are normalized independently from existing classifier labels. `response_observed` maps to `response_preserved`, while `defended` requires confirmed injection, evidence, recovery and cleanup.
- Existing gate and knowledge validator behavior remains compatible; focused phase-0 tests passed. Windows pytest cache warnings remain environmental and do not affect assertions.

## Git upload preparation pass (2026-08-14)
- Current branch is `remediation/2026-08-09-review`, local HEAD `f4242b9`, ahead of `origin/remediation/2026-08-09-review` by 5 commits.
- The worktree had 176 visible status entries before cleanup: 26 tracked modifications and 150 untracked entries. The untracked set included many `.tmp-*` verification directories, so upload preparation must not use `git add .`.
- Added `/.tmp-*/` to `.gitignore` to keep local verification directories out of the upload candidate set.
- Created `docs/CHAOSATLAS_UPLOAD_PREP_2026-08-14.md` as the current upload-preparation checklist and linked it from `docs/ARCHIVE_MAP.md`.
- The three-project Word report is now paired with a UTF-8 Markdown source file: `docs/ChaosAtlas_three_project_experiment_report_2026-08-14.docx` and `.md`.
- Word report structural QA passed: DOCX opened with `python-docx`, Chinese text survived (`cjk_count > 3000`), no question-mark replacement occurred, required percentages and review-boundary strings were present, and no obvious secret/token patterns were found. Visual PNG rendering remains unavailable because LibreOffice is not installed and the Microsoft Word PDF fallback timed out.
- Upload boundary: runtime logs, model-selection payloads, and large experiment directories require final selective inclusion and sensitive scan before push. Keep `human_review=pending` and `knowledge_base_updated=false`.

## Project archive pass (2026-08-10)
- The repository already contains substantial experiment evidence for three case-study systems: `train-ticket`, `online-boutique`, and `otel-demo`.
- Existing top-level planning files are UTF-8; PowerShell's default reader displayed mojibake, so new documentation must be written and checked explicitly as UTF-8.
- The worktree is intentionally dirty with user/generated experiment artifacts. Archive edits must not reset or rewrite those artifacts.
- There is no top-level README yet. A project README and separate experiment/knowledge-base guides are required for a private GitHub handoff.
- Current evidence is split across `artifacts/`, `reporting/`, `raw_yaml/`, and `tools/`; the archive should explain these ownership boundaries and distinguish static, runtime, blocked, pending, and exploratory evidence.

## Project summary pass started (2026-08-10)
- The requested deliverable is a repository-wide summary, not another runtime experiment. The summary will use machine-counted files/cards/tests and the existing pinned reports as its source of truth.
- Current inventory: `raw_yaml/` has 1,935 YAML files; `artifacts/` has 1,166 files; `reporting/` has 13 files; `tools/` has 75 top-level Python tools, 6 shell tools, and 38 test modules; `docs/` has 5 guide files plus the top-level README.
- Raw YAML distribution is led by NetworkChaos (428), StressChaos (352), PodChaos (341), HTTPChaos (183), IOChaos (125), TimeChaos (119), and PhysicalMachineChaos (114); the remaining 9 kinds are lower-volume.
- Knowledge bases are present and indexed for three projects: Train Ticket 7 cards, Online Boutique 8 cards, OpenTelemetry Demo 2 cards; each has `index.json` and `validation_report.json`.
- The repository total is currently about 7,227 files / 335.91 MB, but this includes nested source checkouts, generated artifacts, binaries, caches, and temporary outputs; it is not a recommended upload set without a final inclusion review.
- Current Git state is branch `remediation/2026-08-09-review` with extensive pre-existing modified/untracked experiment files plus the documentation added in the prior pass. The workspace is not a clean release snapshot.
- `artifacts/train-ticket/runtime/coverage_matrix.md` gives the clearest first-project accounting: 54 samples = 5 verified, 30 HTTPChaos platform-blocked, 1 not reachable, 1 static-only Workflow, and 17 not run.
- Current card statuses are mostly runtime-validated: Train Ticket has 1 platform-blocked and 1 candidate card; Online Boutique has 8 runtime cards (one statistical repetition); OpenTelemetry Demo has 2 runtime cards.
- The selection-only knowledge ablation completed 36/36 valid static selections with leakage audits passing, but it is descriptive only: ESHOP/SOCIALNET formal pools do not meet preregistered 48-candidate size, environment gates blocked runtime, and human review is pending.
- The code/tool layer groups naturally into catalog/mapping (29), selection/decision (12), runtime execution (15), knowledge (6), reporting/LLM (5), and other helpers (8). The repository also contains 8 persistent `.planning` sessions, including the archive and held-out ablation tracks.
- `governance/README.md` defines the intended publication boundary: nested source is pinned separately, generated logs/caches/credentials are excluded, and every runtime result must retain source mutation, pinned commit, classification, and cleanup evidence.
- Summary pass completed: `docs/PROJECT_SUMMARY.md` is the canonical narrative snapshot; it deliberately marks the current working tree as a research workspace and keeps descriptive ablation results separate from formal runtime claims.

## Successful station oracle and fixture boundary
- Station `SecurityConfig` protects POST/PUT/DELETE `/api/v1/stationservice/stations` with `ROLE_ADMIN`; an attempted temporary fixture creation returned HTTP 403 and produced no mutation. Reading Kubernetes Secrets to bypass that rule is out of scope.
- The service's existing `InitData` seed provides a safe read-only success oracle: `shanghai` resolved to station UUID `80fad31f-143a-4906-a816-622098aef3d1` through both the Station API and Basic-to-Station path.
- Under the same one-worker/80%/45s CPU node, the successful oracle returned ten HTTP 200 responses, preserved the UUID, and logged ten downstream Station calls. cgroup throttling remained measurable (`nr_throttled=409`, `throttled_usec=3044249`).
- The success run's median latency (26.526ms) did not exceed its 27.378ms baseline, while the not-found run increased by 47.457ms. This is a business-oracle difference requiring controlled repetition, not evidence that CPU pressure is harmless or that the not-found path is deterministically slower.

## Basic downstream CPU replay
- The selector-generated Basic CPU candidate passed all runtime gates and reached the intended `ts-basic-service` Pod; Chaos Mesh reported `injectedCount=1`, then `recoveredCount=1`, and cleanup removed the resource.
- cgroup-v2 directly observed resource pressure: `nr_throttled=433` and `throttled_usec=8647513` added during the active window; both counters stayed stable after recovery.
- The test-node-centered path was confirmed at runtime: `BasicController.queryForStationId -> BasicServiceImpl.queryForStationId -> StationController.queryForId -> StationServiceImpl.queryForId`. Ten controlled not-found responses stayed HTTP 200; median latency increased by 47.457ms over the existing 24ms baseline.
- New knowledge boundary: downstream execution can remain functional under CPU throttling, but a not-found oracle does not establish successful station data, timeout, retry, fallback or circuit-breaker defense. The next experiment needs a valid or synthetic station fixture.

## Selector-generated CPU replay
- The top `stress_cpu -> ts-order-service` candidate passed the runtime gate, and `tools/run_stress_with_cgroup.py` started sampling only after Chaos Mesh reported `injectedCount=1`.
- Across 25 cgroup-v2 samples, the active injection window added `nr_throttled=432` and `throttled_usec=15496840`; the post-recovery samples added zero throttling. This is direct resource-effect evidence independent of `metrics-server`.
- The eight exercised read-only order requests all returned HTTP 200 with the expected `Order Not Found` envelope. The Pod recovered with zero restarts and the StressChaos resource was absent after cleanup.
- The new result class is `functional_response_preserved_with_cgroup_throttling`: resource pressure was real, but the business-path oracle was narrow. The next CPU experiment must reach a real downstream order call before generalizing the defense conclusion.

## Runtime findings: applicability before defense
- A real service can be healthy while a Chaos Mesh CRD is only selected, not injected. The HTTPChaos record had `Selected=true` but `injectedCount=0` and `Not Injected/Wait`.
- The concrete blocker was emitted by `chaos-daemon`: `ebtables` is missing from the Docker Desktop WSL2 kernel. Therefore the correct outcome class is `platform_instrumentation_prerequisite_missing`; it must not be labeled defended or not defended.
- StressChaos used the same test-node-centered target and injected successfully. At the bounded profile, the service preserved HTTP 200 responses, readiness, and zero restarts through recovery. Missing `kubectl top` data leaves CPU saturation and throttling unproven.
- New applicability gate for the knowledge base: `YAML valid -> target exists -> request reachable -> injector selected -> injector actually injected -> effect observed -> recovery observed`. Only the last three layers support defense conclusions.
- Runtime evidence files: `artifacts/train-ticket/runtime/baseline_order_service.json`, `http_order_404_result.json`, and `stress_order_cpu_result.json`.
- The applicability gate is now executable and read-only: it rejects the known HTTP tproxy blocker before apply, while allowing the StressChaos mutation only when the real Pod, port, CRD and Chaos Mesh components are healthy.
- `metrics.k8s.io` is not installed in this Docker Desktop cluster, but cgroup-v2 `cpu.stat` is readable inside the real service container. This exposed measurable throttling during the strong short profile without requiring metrics-server.
- Strong short CPU injection preserved the tested HTTP response contract and recovery. The knowledge conclusion is bounded: it covers the selected endpoint, duration and profile, not all order endpoints or the full five-minute workload.
- Network delay can be proven effective without a metrics-server: repeated upstream calls showed a stable approximately 500ms latency increase, Chaos Mesh reported injection and recovery, and both service logs confirmed the downstream edge.
- A successful HTTP 200 during a delay experiment is only functional preservation. It must be paired with latency and downstream-path evidence; otherwise the result could be a non-hit or an unobserved instrumentation failure.
- The Basic->Station path is runtime reachable in the lab, while the original Order->Station card remains deferred. This is why the reachable experiment has its own card instead of upgrading the original candidate.
- At the original 5s delay strength, the same reachable path crossed the 10s client observation budget: the client timed out at 10041ms, while server logs show the downstream handler and normal response around 10s later. This is a partial/no-defense boundary result, not a platform failure.
- Chaos Mesh application is asynchronous. `kubectl apply` returning, `Selected=true`, and `injectedCount=1` are distinct states; only a request issued after `injectedCount=1` can support an effect conclusion. Requests from earlier attempts were explicitly excluded from defense classification.
- The lifecycle gate is now executable as `tools/run_chaos_experiment.py`. It keeps platform blocking, not-injected, transport error, response observed, recovery-unconfirmed, and cleanup evidence distinct. Its smoke run confirmed two requests inside the injection window and verified the resource was absent after cleanup.
- Runtime result classification must normalize both new runner reports and older hand-written artifacts. The classifier now turns the same evidence into explicit labels such as `platform_or_preflight_blocked`, `invalid_not_injected`, `response_preserved_latency_degradation`, and `client_timeout_observed`, while keeping `defense_claim=not_derived`.
- Candidate retrieval must carry both `target_service` and `test_node`; matching only on an experiment ID or downstream service name can transfer Basic->Station evidence to the wrong Station test target. The selector now rejects that implicit transfer and requires exact target/test-node matches.

## 测试节点中心卡片：StressChaos CPU -> ts-order-service
- 原始样本：`raw_yaml/StressChaos/0885ce87187120d724117939.yaml`，配置 `workers=4`、`load=100`、`mode=one`、`duration=5m`，选择 `namespace=train-ticket`、`app=ts-order-service`。
- 目标资源：Deployment 清单为该容器声明 CPU request `50m`、limit `200m`，并在 `12031` 上配置 TCP readiness probe。
- 测试节点中心路径：`CPU stress -> Pod resource limit -> listener/OrderController -> OrderServiceImpl -> readiness/CPU/latency/error observation -> recovery`。
- 关键假设：CPU limit 可能先表现为 throttling/延迟，而不是 readiness 立即失败；TCP readiness 只能证明端口可连接，不能证明业务 SLO 正常。
- 已生成 `artifacts/train-ticket/knowledge_base/KB-TT-STRESS-ORDER-CPU-001.*`，运行前置条件仍为隔离 namespace、固定低速只读请求、资源和业务指标基线。

## 知识库质量门
- `tools/validate_knowledge_base.py` 已将知识卡片纳入可重复校验：索引路径、卡片 ID、测试节点、中心图节点/边、四层有效性、后续证据均为必填。
- 校验还会提示疑似明文密码/token 等敏感值，避免 LLM 知识库把环境凭据带入 YAML 生成上下文。
- 当前报告：`artifacts/train-ticket/knowledge_base/validation_report.json`，4 张卡片通过，0 errors，0 warnings。

## 测试节点中心卡片：HTTPChaos response -> ts-order-service
- 原始样本：`raw_yaml/HTTPChaos/a554bb3751e7b1c20eead94c.yaml`，配置为 `target: Response`、`replace.code: 404`、`port: 12031`、`path: '*'`、`mode: one`、`duration: 5m`。
- 目标与端口：`app=ts-order-service` 静态命中项目 Deployment/Service；`train-ticket/ts-order-service/src/main/resources/application.yml` 声明 `server.port: 12031`，Deployment/Service 清单也声明该端口。
- 入口与内部路径：`OrderController` 在 `OrderController.java:20-180` 暴露多个真实 HTTP 路由，并将请求委托给 `OrderService`；`OrderServiceImpl.java:50-466` 访问 `OrderRepository` 并返回应用层 `Response`，随后 Controller 用 `ResponseEntity.ok` 包装。
- 该测试节点的中心不是某个单一下游函数，而是响应边界：`controller -> service/data -> application response -> injected response rewrite -> client/gateway outcome`。
- 需要运行时区分的两个结果：业务处理是否执行/完成；客户端实际收到的 HTTP 状态和调用方如何处理 404。只依据客户端 404 不能断言“应用失败”，只依据应用日志成功也不能断言“系统防御住了”。
- `path: '*'` 在静态上覆盖多个路由；实际实验必须每次选择一个只读入口，避免把多个业务路径混为一个结果。
- 已生成 `artifacts/train-ticket/knowledge_base/KB-TT-HTTP-ORDER-RESPONSE-404-001.*`，索引中建议为 `candidate_after_isolation_and_baseline`；当前无集群和 Trace，不能执行注入或输出 defended/not_defended。

## 测试节点中心卡片：NetworkChaos -> ts-order-service
- 原始样本：`raw_yaml/NetworkChaos/661b0ac8ed245799ce7b5069.yaml`，配置为 `delay=5s`、`duration=5m`、`mode=one`、`direction=to`，选择 `namespace=train-ticket` 且 `app=ts-order-service`。
- 真实入口：`train-ticket/ts-order-service/src/main/java/order/controller/OrderController.java:66-70` 暴露 `/api/v1/orderservice/order/refresh`，调用 `OrderServiceImpl.queryOrdersForRefresh`。
- 真实下游候选：`OrderServiceImpl.java:208-219` 的 `queryForStationId` 使用 `RestTemplate.exchange` 调用 `http://ts-station-service/api/v1/stationservice/stations/namelist`。
- 可达性反证：`queryOrdersForRefresh` 中唯一生产调用 `queryForStationId` 的语句位于 `OrderServiceImpl.java:200`，目前被注释。当前源码只能证明“下游函数存在”，不能证明“选定业务请求会执行该函数”。
- 单元测试中的 `testQueryForStationId` 直接调用该函数并 mock `RestTemplate`，它是函数级证据，不是生产请求的运行时 Trace 证据。
- 静态扫描未发现 `ts-order-service` 内的 timeout/retry/fallback/circuit-breaker 实现；这只是防御缺口假设，必须用运行时响应、日志、指标和 Trace 验证。
- 已生成 `artifacts/train-ticket/knowledge_base/KB-TT-NETWORK-ORDER-STATION-001.*`，把该样本标记为 `static_only`、`business_path_reachable=not_reachable_in_current_source`、`injection_recommendation=defer`。

## 当前仓库基线
- 根目录只有 `raw_yaml/` 与规划文件，没有 Git 元数据、应用源码、测试代码或加载器；后续必须从 YAML 资产反查真实项目入口，若入口不在本目录需建立外部依赖清单。
- YAML 总量：1,935。按目录：`NetworkChaos` 428、`StressChaos` 352、`PodChaos` 341、`HTTPChaos` 183、`IOChaos` 125、`TimeChaos` 119、`PhysicalMachineChaos` 114、`DNSChaos` 80、`Workflow` 66、`Schedule` 56、`JVMChaos` 37、`KernelChaos` 15、`AWSChaos` 8、`BlockChaos` 4、`GCPChaos` 4、`AzureChaos` 3。
- 资源类型均为 Chaos Mesh CRD；1,934 个 `apiVersion: chaos-mesh.org/v1alpha1`，1 个为 `chaosmesh.chaos-mesh.org/v1alpha1` 变体。
- 解析风险：PyYAML `safe_load` 对至少 32 个文件报 `cannot use dict/list as a dict key`；示例包含 `metadata.name: {}`、namespace/list 嵌套、selector 值类型错误。需要区分 YAML 语法、Kubernetes schema、Chaos Mesh 语义和运行时可达性四层有效性。
- 模板/敏感值信号：发现 `${...}`、`<...>`、`placeholder`、`PLACEHOLDER` 等占位符；包含 `secretName`、云区域/实例、endpoint、volumePath、地址等高风险字段，不能直接注入真实环境。
- 通用字段候选：`action`、`mode`、`selector`、`duration`、`scheduler` 在多个 kind 重复出现，可作为跨资源测试算子入口；资源特有字段（如 NetworkChaos 的 `delay/loss/target`、HTTPChaos 的 `path/replace/abort`、IOChaos 的 `volumePath/errno`）需要单独规则。
- `Workflow`、`Schedule` 是组合/时序资源，必须先解析模板引用、入口、并发和调度，再评估叶子 Chaos；不能只按单文件字段覆盖率判断。

## 外部资料
- 访问日期：2026-08-03；数据来自 GitHub 官方仓库页面/API 与仓库 README。星标/更新时间会变化，仅作为当前筛选快照。
- [GoogleCloudPlatform/microservices-demo](https://github.com/GoogleCloudPlatform/microservices-demo)：20,791 stars、10,272 forks，未归档，Apache-2.0；README 称 Online Boutique 为 11 个微服务的 Kubernetes 云原生电商示例，支持 Kubernetes、gRPC、Istio/Cloud Operations 等，仓库含 `kubernetes-manifests`、Helm、Kustomize、Istio manifests、loadgenerator。
- [open-telemetry/opentelemetry-demo](https://github.com/open-telemetry/opentelemetry-demo)：3,250 stars、6,927 forks，未归档，Apache-2.0；README 称 Astronomy Shop 是面向近真实环境的分布式微服务系统，提供 Docker/Kubernetes 部署、OpenTelemetry 观测、telemetry tests，仓库含 compose、Kubernetes/Helm 相关入口和 `test/`。
- [dotnet/eShop](https://github.com/dotnet/eShop)：10,745 stars、3,757 forks，未归档，MIT；当前为 .NET 9/.NET Aspire 电商参考应用，支持 Docker Desktop、Aspire dashboard、e2e/tests；更适合容器/服务依赖/故障恢复测试，Kubernetes YAML 需要额外确认。
- [FudanSELab/train-ticket](https://github.com/FudanSELab/train-ticket)：903 stars、317 forks，未归档；README 明确为 41 微服务基准系统，提供 Kubernetes + Helm、`make deploy`/`make reset-deploy`、`--with-monitoring`、`--with-tracing` 和测试脚本。当前 YAML 数据中出现 `train-ticket` namespace 54 次，优先级最高。
- [delimitrou/DeathStarBench](https://github.com/delimitrou/DeathStarBench)：940 stars、504 forks，未归档，GPL-2.0；包含 Social Network、Media、Hotel Reservation 等端到端服务，适合高负载、依赖链和性能/故障耦合研究，但部署和负载成本较高，且 README 主要是 benchmark 说明。
- [microservices-demo/microservices-demo](https://github.com/microservices-demo/microservices-demo)（Sock Shop）：3,784 stars、3,002 forks，但已归档；可作历史对照，不建议作为主项目。
- [istio/istio](https://github.com/istio/istio)：38,326 stars、8,361 forks，未归档；平台本身不是业务目标，适合后续研究服务网格策略与 Bookinfo/流量治理，不作为首轮业务项目。
- [chaos-mesh/chaos-mesh](https://github.com/chaos-mesh/chaos-mesh)：7,824 stars、1,026 forks，未归档，Apache-2.0；这是注入工具/控制器，不是被测业务，应与上面的业务项目分开看。

### 初筛结论
- 首选：`FudanSELab/train-ticket`，因为已有 YAML 中出现对应 namespace，且官方部署、监控、tracing、测试入口齐全。
- 次选：`GoogleCloudPlatform/microservices-demo`，社区热度最高且 Kubernetes/服务拓扑/负载生成器完整，适合作为标准化基准。
- 观测优先：`open-telemetry/opentelemetry-demo`，最适合验证“注入后为什么被防御/为什么未被发现”的 trace-metric-log 证据链。
- 高成本研究：`DeathStarBench`，适合后续性能与复杂依赖实验，不建议作为第一阶段落地项目。
- 不推荐主选：已归档 Sock Shop；平台型 Istio/Chaos Mesh 不作为业务被测对象。

## Train Ticket 基线（本地浅克隆）
- 仓库路径：`train-ticket/`；远程：`https://github.com/FudanSELab/train-ticket.git`；分支：`master`；固定 commit：`313886e99befb94be6cd45f085c98e0019f59829`。
- 官方入口：`README.md`、`Makefile`、`hack/deploy/deploy.sh`、`hack/deploy/utils.sh`；默认 `make deploy` 使用 namespace `default`，部署基础设施、MySQL、Nacos、RabbitMQ、服务和服务部署。
- 可选观测：`--with-monitoring` 部署 Prometheus/Grafana；`--with-tracing` 部署 SkyWalking；另有 `deployment/kubernetes-manifests/k8s-with-jaeger/` 和 Docker Compose + Jaeger 方案。
- 可复用故障入口：`deployment/fault-inject-deployment/` 含 Istio `VirtualService`、`DestinationRule` 和 Deployment 注入/清理脚本，可作为“项目原生故障注入”对照组，但不等同于 Chaos Mesh 结果。
- 部署资产统计：`deployment/**/*.y*ml` 共 51 个文件、解析到 533 个文档；其中 14 个 Helm 模板不能作为独立 YAML 直接解析，必须先 `helm template` 后再做 schema 检查。
- 安全边界：部署脚本存在硬编码数据库凭据（报告中不保存具体值）；`deploy_monitoring` 不接收 namespace 参数，可能作用于集群范围；`reset-deploy` 与监控清理路径不完全对称。首轮必须使用专用集群或明确隔离的 namespace，并先做资源清单/回滚演练。
- 运行方式选择：Kubernetes 路径最适合当前 Chaos Mesh YAML；Docker Compose + Jaeger 可作为无集群的静态/应用层预演，但不能验证 Kubernetes selector、CRD、admission 和 PodChaos。

## Train Ticket YAML 映射（当前 corpus）
- `metadata.namespace: train-ticket` 共 54 个，全部可用 PyYAML 解析；类型分布：`HTTPChaos` 30、`NetworkChaos` 15、`StressChaos` 8、`Workflow` 1。
- `HTTPChaos` 主要是 `target: Response`、`path: '*'`、服务端口、`mode: one`、5 分钟 duration；变异包括 response code 404、5 秒 delay 和 1 个 abort。`HTTPChaos` 不使用 `spec.action`，不能用通用 action 规则误判。
- `NetworkChaos` 15 个均为 `action: delay`、`direction: to`、5 秒 latency、5 分钟 duration、`mode: one`；selector 的 `app: ts-*-service` 与项目 Deployment Pod template labels 相匹配。
- `StressChaos` 8 个均为 CPU stress（workers/load）和 `mode: one`；目标主要为 `ts-order-service`、`ts-route-service`、`ts-basic-service`、`ts-station-service`、`ts-user-service`、`ts-travel-service`、`ts-ticketinfo-service`、`ts-travel-plan-service`。
- `Workflow/tt-chaos` 编排 bandwidth、pod-kill、CPU stress、memory stress；其中 Workflow 内 NetworkChaos 只按 namespace `train-ticket`、`mode: all`，是高爆炸半径样本，应先做静态展开和命中数预估。
- 这些样本与项目真实服务标签、部署端口和观测组件形成了可追踪的初始 CFG/DFG 候选：`YAML selector -> Pod label -> service call -> trace/metric -> recovery`。
- 首批静态产物显示：54 个 Train Ticket 样本中 53 个有 selector -> Deployment/Service 匹配，49 个有生产源码函数候选；唯一完全未映射的是组合 Workflow，需要先展开模板叶子节点。

## 本机运行前置条件
- 已有 Docker/Kubectl 客户端（Kubectl v1.36.1、Docker CLI 29.6.1）。
- 未发现 Helm、Maven、Kind、Minikube；当前没有可用 kubectl context，Docker server 也未返回版本信息。
- 结论：当前只能继续静态 YAML/源码/图分析，不能执行 Train Ticket 部署、基线请求或 Chaos Mesh 注入；需要用户提供隔离 Kubernetes 集群/namespace、Helm 和观测入口，或明确安装运行时的授权。
# Latest runtime finding: fixed-warmup Basic CPU comparison (2026-08-04)
- The same test-node-centered `StressChaos` mutation was repeated against two reachable business oracles with identical controls: 3 warm-ups excluded from classification, 10 formal requests, 0.5s interval, 5s timeout, and 25 cgroup samples.
- The seeded success path preserved HTTP 200 and the real station UUID; median latency was 32.581ms versus 27.378ms baseline (+5.203ms). The controlled not-found path preserved HTTP 200 and `status=0, msg=Not exists`; median latency was 33.864ms versus 24ms baseline (+9.864ms).
- Both runs showed CPU throttling (`nr_throttled +434/+423`) while the downstream Station calls and response envelopes remained intact. Runner reports confirm injection, recovery and resource cleanup; post-recovery cgroup deltas were zero.
- LLM training rule: a single business oracle and a noisy ten-sample latency delta are insufficient for a defense claim. Compare success and negative oracles under fixed warm-up/sample windows, then correlate cgroup, upstream/downstream logs, response contract and recovery.
- The next experiment is a bounded stronger CPU profile on the seeded success oracle, stopping at the first HTTP error, timeout, Pod restart or failed recovery. A final read-only kubectl health check could not complete because the permission review timed out twice.

# Strong-profile finding (2026-08-04)
- With 4 CPU workers at 100% for 60s, the seeded success oracle still returned HTTP 200 and the same UUID for all ten formal samples, but median latency increased to 101.404ms from 27.378ms (+74.026ms).
- cgroup evidence showed a much larger throttling window (`nr_throttled +588`, `throttled_usec +167266489`) and zero post-recovery growth. The runner confirmed injection, recovery and cleanup.
- This is partial resilience: response correctness was preserved, latency behavior was not. No timeout or 5xx was observed, so timeout/retry/fallback/circuit-breaker behavior remains unknown.
- Fresh downstream log capture was not available because the read-only permission review timed out. The result is therefore recorded with an explicit log-evidence boundary rather than upgraded to a broader path rule.

# Concurrent-load finding (2026-08-04)
- Keeping r1 CPU stress unchanged and issuing four concurrent callers per batch produced 12 formal success responses, all HTTP 200 with the seeded UUID.
- Median latency was 92.826ms and p95 195.868ms versus 27.378ms baseline. cgroup throttling was confirmed (`nr_throttled +440`, `throttled_usec +8971772`) and recovery added zero counter growth.
- LLM rule: concurrency is an independent test dimension. Sequential success evidence cannot be generalized to concurrent SLO behavior; a correct response can coexist with substantial queueing/resource-contention latency.
- Source inspection found `RestTemplateBuilder.build()` with no application timeout/retry/fallback/circuit-breaker configuration in Basic. The runner's 5s timeout is a measurement boundary, not evidence that the application defended a downstream timeout.
- Repository tests cover the response contract and mocked `RestTemplate` calls, but no endpoint latency SLO or production timeout budget was found. The next latency judgment must therefore be labeled exploratory until an operator-provided SLO is recorded.

# Direct Station test-node finding (2026-08-04)
- The direct `ts-station-service` CPU candidate passed the same runtime gates as Basic and exercised `StationController.queryForStationId -> StationServiceImpl.queryForId -> StationRepository.findByName`.
- Ten formal seeded success requests preserved HTTP 200 and the UUID; median latency rose from 30.146ms to 43.308ms (+13.162ms). cgroup throttling was `nr_throttled +406`, `throttled_usec +16272410`, with zero post-recovery growth.
- This is a distinct test node from Basic-upstream CPU. The same business response remained correct, but the latency effect differed; LLM retrieval must match exact target service and injection location instead of transferring downstream evidence implicitly.
- Fresh Station log capture remains pending because the read-only permission review timed out; the card records that evidence boundary explicitly.

# Direct Station network-delay finding (2026-08-04)
- A bounded `NetworkChaos` with nominal 100ms outbound delay and 20s duration reached the Station Pod and preserved all ten seeded success responses.
- Median latency increased from 30.146ms to 216.022ms (+185.876ms), p95 234.324ms; no timeout or 5xx occurred within the 5s observation budget. Recovery and cleanup were confirmed.
- LLM rule: nominal delay is not equivalent to end-to-end delay. The observed effect must be measured, and the exact delayed dependency must not be named without logs or trace evidence.
- The controlled not-found oracle produced the same pattern: 215.359ms median versus 32.038ms baseline (+183.321ms), with its distinct `Not exists` envelope preserved. Similar success/not-found deltas indicate the injected network edge dominates the observed latency.
- This is not evidence of application-branch defense. The exact outbound dependency and any timeout/retry/fallback behavior still require logs or traces and an explicit latency SLO.
- Source mapping identifies `StationRepository.findByName`; targeted non-credential runtime configuration confirms the deployed datasource as `train-ticket-mysql:3306` (database `ts`). Credentials were not read or stored, and packet-level attribution was not collected.

# Station network delay boundary finding (2026-08-04)
- The success oracle was tested at nominal 100ms, 500ms and 2s outbound delay. Median latencies increased monotonically to 216.022ms, 1021.227ms and 4020.903ms; all observed responses remained HTTP 200 with the seeded UUID.
- The 2s probe approached the 5s client observation budget without crossing it. This is the stopping boundary for the current evidence, not proof that the application has a 5s timeout defense.
- LLM rule: stop escalation when the observation budget is nearly exhausted if no operator SLO exists. Record the boundary and request SLO/Trace evidence instead of forcing a timeout.
- The completed line report packages the test-node-centered graph, dual-oracle matrix, delay ladder, lifecycle proof, redacted static mapping, stopping decision, and the reuse rule for future LLM retrieval.
- A 3s boundary probe crossed the 5s experimental client budget at 5047.049ms. Station completed the post-repository Not Found branch at 6063.895ms, after the client timeout.
- LLM rule: client timeout plus later server completion is partial or missing client-boundary defense. Do not interpret server-side correctness as client resilience, and do not infer retry/fallback without direct evidence.
- The runtime loop is closed at this boundary. The 5s value remains a lab budget rather than a production SLO; `train-ticket-mysql:3306` is runtime-configuration evidence, while packet-level attribution still requires Trace or network observation.
# Paper preparation findings (2026-08-04)
- The first empirical stage supports a conservative method claim: a test-node-centered graph plus runtime gates prevents YAML-level existence from being mistaken for business-path reachability.
- The strongest case-study result is not “HTTP 200 means defense”; it is a timed causal distinction between response preservation, latency degradation, client timeout and later server-side completion.
- The current evidence supports a runtime-configured Station datasource peer (`train-ticket-mysql:3306`) but not packet-level Trace attribution or a production SLO claim.
- The paper-prep report lists the next evaluation requirements: repeated runs, confidence intervals, P0 local graph coverage, independent LLM labels, and a reachable Order workflow.
## Audit verification and remediation

The external review was substantially correct about the runtime safety risks. The namespace and mode checks were previously generator-only, HTTP prerequisite detection was fail-open, and the stress orchestrator could kill its runner before cleanup. Those paths are now enforced in the runtime gate and parent orchestration layer. Classification is centralized, candidate ranking is stable, and the compatibility fuzzy matcher is explicitly limited to legacy records with no `target_service` field.

Artifact checks found nine classification-index mismatches rather than three; all now match their referenced reports. The line report has a canonical classification field, the HTTP blocked vocabulary is normalized, and validation output includes one audit object per card. The workspace now has a root Git baseline while preserving the pinned `train-ticket` repository as an independent nested checkout.

## Archive cleanup finding (2026-08-11)

- Files under `artifacts/experiments/knowledge_ablation_prompts/` are formal frozen inputs and must be retained.
- The 9 `.planning/**/DEEPSEEK_*_PROMPT.md` files are agent handoff drafts, not evidence; they were removed after recording the paths in `docs/ARCHIVE_CLEANUP.md`.
- `.pytest-tmp-final-all/` was disposable test output and was removed. `.pytest_cache/` could not be inspected due to Windows permissions and was left unchanged.

## Paper-preparation review finding (2026-08-11)

- The completed paper-facing core is the TestNode method, applicability gates, bounded runtime evidence, four case studies, knowledge-card schema, and conservative cross-project interpretation.
- Knowledge-base selection ablation and final method head-to-head comparison are incomplete; retain all artifacts but classify both tracks as `parked_future_work`.
- Formal claims require later independent oracle, remaining review gates, common candidate pool/oracle, and project-clustered statistics.
# Open-discovery compiler findings (2026-08-11)

- The existing `open_discovery_compiler.py` validates hypotheses but intentionally sets `execution_ready` to false and does not emit Chaos Mesh YAML.
- The fixed candidate-pool path already emits PodChaos and NetworkChaos YAML and uses the shared applicability gate and runner.
- Topology nodes may be Kubernetes workloads, routing services, or Compose services. A runtime mutation compiler must fail closed when a node has no pod selector or when a Compose node lacks an explicit Kubernetes runtime mapping.
- Dependency-edge faults can be represented safely as NetworkChaos on the resolved source workload with `direction: to`; the destination is retained in provenance. PodChaos and StressChaos are rejected for dependency edges.
- YAML generation must not call kubectl. It must record project, hypothesis signature, graph hash, target resolution, parameters, and generator version for later audit.
- GitHub source restoration finding (2026-08-12): P09 is complete in isolated `sources_restored/P09`; P03/P06 remain incomplete because existing partial clones lack blobs and official archive downloads timed out. Existing snapshots were preserved; see `sources_restored/RESTORATION_MANIFEST.md`.

## P09 digest and validation finding (2026-08-12)

## P08/P09 continuation finding (2026-08-13)

## P08/P09 source and profile continuation finding (2026-08-13)

- P09 fixed source was restored into the new ignored `sources_restored_r2/P09`
  path and matched the registered commit/tree/file count. An isolated digest-
  pinned profile and explicit-path validator report were generated without
  applying Kubernetes resources.
- P09 profile checks passed for namespace locality, forbidden-service exclusion,
  immutable images, and required resources. The deterministic local mock oracle
  returned `P09-MOCK-OK`; this is an offline oracle check, not a runtime gate.
- P08 fixed source was restored into `sources_restored_r2/P08` and matched its
  registered commit. Its Compose contains only `appsmith`, but uses mutable
  `index.docker.io/appsmith/appsmith-ce:release` and has no healthcheck, restart
  policy, or resource limits. The independent P08-r2 static gate therefore
  remains blocked and no runtime namespace was created.
- P09/P08 source/profile regression tests passed: 24 tests. No credentials,
  model calls, Docker operations, or Kubernetes mutations were used.

- P08 remains pre-runtime blocked: its project manifest is `pending_resource_pilot`,
  marks the resource class as very high, and no P08 source-restoration or
  runtime-profile directory is present in the current workspace.
- P09 has a historical restoration manifest, but the referenced
  `sources_restored/P09` directory is absent from the current workspace. The
  preflight now distinguishes this from mutable-image and core-service checks
  with `source_missing:docker/docker-compose.yaml`; it remains fail-closed.
- The P09 preflight regression also covers the valid case where an available
  verified restored source is used when the frozen source is incomplete.
- P08/P09 focused offline tests passed: 26 tests. No cluster mutation, model
  call, credential read, or source restoration was performed in this pass.

- Root cause of the earlier P09 digest block was two-layered: the WSL-native dockerd had no proxy configured, and the old extraction probe matched only `Docker-Content-Digest` with uppercase letters. WSL access through the Windows gateway proxy `172.20.96.1:7890` returned HTTP 200 for all five public manifests; HTTP/2 normalized the header to lowercase.
- Resolved immutable manifest digests are recorded in `runtime_profiles/P09/image-digests.json` and the generated profile. No secret was read, no DeepSeek call was made, and no Docker Desktop operation occurred.
- `validate_profile.py` previously scanned the entire YAML and falsely rejected cleared environment variable names such as `SSRF_PROXY_*`. It now checks only workload/service identity fields, while retaining fail-closed checks for emitted forbidden components.
- Offline profile validation passes. Kubernetes server-side dry-run accepted the Namespace document but rejected namespaced documents because a multi-document server dry-run does not persist the Namespace. A post-check confirmed no `chaosatlas-p09` namespace or resources were created. Real apply remains prohibited pending explicit authorization.
- After explicit deployment authorization, the WSL-native Docker daemon was restarted with a systemd drop-in that preserves `--iptables=false --ip6tables=false`, configures the Windows gateway proxy, and binds the API only to `127.0.0.1:2375`. Registry access then worked and all five fixed images were pulled, including Dify API and Web. The existing kind control-plane container did not survive the daemon restart cleanly: Docker reported stale sandboxes, `layer not mounted`, and cgroup scope creation failures while restoring the control-plane container. This is an environment/runtime recovery failure, not a P09 result; no P09 namespace or workload was applied.

## kind cgroup recovery finding (2026-08-12)

- WSL-native Docker defaults were changed to `cgroupfs` and `default-cgroupns-mode=host`; ordinary containers report `CgroupnsMode=host` and Docker remains localhost-only on `127.0.0.1:2375`.
- kind v0.32.0 hard-codes `--cgroupns=private` in its Docker create request. Under the WSL cgroup-v2/systemd combination this fails with `device or resource busy` while writing `/sys/fs/cgroup/docker/<id>/cgroup.procs`.
- A repository-local temporary Docker API proxy (`tools/docker_kind_proxy.py`) was added. It preserves the original daemon and rewrites only kind's `/containers/create` payload to `CgroupnsMode=host`; direct inspection confirmed the created control-plane container uses `host`.
- The proxy still needs a final end-to-end validation of kind's long kubeadm initialization lifecycle. No successful Kubernetes API or experiment runtime has been claimed from this recovery path.

## Repository handoff findings (2026-08-12)

- The two full upstream source trees under `sources/` and `sources_restored/P09/` total roughly 245 MB and are local experiment inputs, not ChaosAtlas-owned source. They are excluded while restoration provenance is retained.
- `.tmp-chaos-kind-admin.conf`, `.tmp-bridge/`, local Docker configuration, and `CHAOS_ENV_HANDOFF.md` expose machine-specific runtime details and are excluded from publication.
- The curated untracked submission is 631 files and about 4.95 MB, with no untracked file larger than 1 MiB. Existing tracked binaries are unchanged by this handoff.
- No sensitive-value signature or sensitive filename was found in the exact modified/untracked candidate set or in the recorded runtime/model-result artifacts.
# P02 teacher-minikube smoke and formal batch findings (2026-08-12)

- The teacher Minikube smoke report is valid: 5/5 baseline HTTP 200, Chaos Mesh injected_count=1, api-gateway UID replacement, 7 post-recovery HTTP 200 responses, cleanup NotFound confirmation, and no residual Chaos resources.
- The single port-forward warning occurred while the replacement Pod was Ready but port 8080 had not started listening; later oracle success proves recovery and the warning does not invalidate the run.
- The five current method outputs represent two KB mutations, two noKB mutations, and one ChaosEater-adapter mutation. Three repetitions therefore require 15 independent injections.
- `ChaosEater-adapter-open` remains supplementary and cannot be described as official ChaosEater because P02 lacks the required native Skaffold input.
- Earlier P02 runtime evidence uses a different environment and uneven repetitions. Teacher results must be written to `teacher-minikube-formal` and must not be merged by identical YAML identity.
- The first teacher formal batch stopped after one completed run. The second run injected and replaced the target successfully, but its first post-recovery port-forward exited because the new Ready Pod had not started listening on port 8080. Cleanup succeeded and no Chaos resource remained. This is an invalid infrastructure observation, not a noKB method outcome.
- R2 audit found delayed cross-run effects after all three discovery-server kills: the immediately following run observed 8, 9, and 37 consecutive HTTP 500 responses before regaining five baseline successes. This confirms a delayed business outage associated with the mutation, but the generic error body cannot establish the service-discovery mechanism without logs or traces.
- KB and noKB mutations are byte-identical for both targets; the adapter api-gateway mutation is also byte-identical. P02 runtime timing differences therefore cannot be attributed to the knowledge base or method.
# P02 R3 evidence-chain findings (2026-08-13)

- R2 completed all 15 runs, but discovery-server delayed HTTP 500 responses appeared in the next run's baseline because R2 had no sustained post-cleanup washout. It is execution evidence, not a clean head-to-head comparison.
- R3 must attribute delayed effects to the same mutation through `lifecycle.post_cleanup_washout`; every next-run baseline must contain zero failures and every washout must regain the required consecutive HTTP 200 window.
- Root-cause evidence is bounded to experiment-time logs, namespace events, and Zipkin traces. Missing or empty diagnostics keep the mechanism pending and do not invalidate cleanup or fabricate causality.
- KB and noKB mutations for P02 seed-1001 are byte-identical, and the adapter mutation is a subset. Even a clean R3 sequence cannot turn shared-mutation runtime timing into evidence of method superiority or a KB effect.
- Review output remains pending and separate from knowledge feedback. No P02 result can enter P02 itself; only explicit human-reviewed abstractions may enter later projects.

## Four-project offline preparation finding (2026-08-13)

- Online Boutique `r3` is internally consistent: the recorded and actual
  manifest SHA-256 match, all namespace fields are local to
  `chaosatlas-online-boutique`, and the 11 workload images have recorded
  local RepoDigest provenance. This is preparation evidence only; dry-run,
  baseline, and runtime gates are still pending.
- OpenTelemetry Demo `r1` is namespace-local and sanitized, with materialized
  `postgres-init` and `flagd-config` ConfigMaps and a recorded unavailable
  trace backend. Its 12 images remain mutable, so runtime is blocked.
- Train Ticket `r2` deduplicates the four source YAML inputs and rewrites all
  namespaced resources to `chaosatlas-train-ticket`. Its dependency contract
  observes references to `nacos`, `rabbitmq`, `train-ticket-db`,
  `ts-order-mysql`, and `ts-station-mysql`, but no definitions are present.
  Its six image references remain mutable. The profile records both facts and
  keeps runtime apply disabled.
- TeaStore has only historical static intake in this workspace. Its exact
  fixed source snapshot is absent, so no fresh manifest or runtime bring-up
  may be claimed.
- These profiles are source/project-context preparation artifacts. No old
  candidate pool, runtime result, RCA, pending review, or knowledge-base
  update was used as an active method input. `human_review` remains
  `pending`.
# 2026-08-14 三项目两臂续跑发现

- Online Boutique 集群当前 Node Ready、11/11 deployment Ready、全局 PodChaos/NetworkChaos/StressChaos 无残留。
- full H1 的早期诊断批次不作为正式结论；干净正式批次 `formal-r4-runtime-r4` 中 checkoutservice 500ms NetworkChaos 为 2/2 `no_business_impact_observed`。
- full H2 replicate 1 在注入期间 5/5 成功，但清理后第 5 次请求出现 gRPC INTERNAL；paymentservice 与 checkoutservice 随后重启。
- 当前运行器只执行固定 5 次即时恢复请求，任一失败就终止，无法表达“短暂失败后在超时内达到连续成功”的恢复协议。修复前不重复运行该失败命令。
- 机制边界：现有证据只支持注入后的探针/重启和一次支付失败，不支持猜测缓存、注册或内部重试机制。
- `formal-r4-runtime-r2` 在 full H4 rep-2 停止：恢复 33 次均因本地 `127.0.0.1:17070` 拒绝连接而失败；集群中的 cartservice 已 Ready，事件证明其容器被 liveness probe 重启。
- 根因是 `kubectl port-forward svc/cartservice` 随目标容器重启退出且 runner 未重建，属于观测通道故障；不是可归因的业务恢复失败。
- gRPC 输出解析器还要求单行尾部 latency，导致多行 `cart_add_failed` 被降级为 `CLIENT_PROCESS_ERROR`。两处均已按 TDD 修复。
- `formal-r4-runtime-r3` 完成 full 8/8 后，在 ablation h1 checkoutservice PodKill 停止；新 Pod 已 Ready，但本地 checkout 转发 `127.0.0.1:15050` 拒绝连接，32 次恢复采样均无法到达业务 oracle。
- 解析器现按完整 sample block 解析多行 `rpc_error`/`cart_add_failed`；重连判定覆盖冻结的两个本地 oracle 端口 `15050`、`17070`，且仅接受明确 connection-refused/TCP-end 证据。
- Online Boutique 干净正式批次 `formal-r4-runtime-r4` 完成 16/16。可确认的是观测到的业务结果，不据此猜测内部缓存、重试或注册机制：full 的 500ms/30s NetworkChaos 对 checkout/payment/shipping/cart 在 2 次重复中均未造成 oracle 失败；ablation 的 checkout/cart/productcatalog PodKill 在 2 次重复中均造成 oracle 失败，frontend PodKill 2 次均未造成该 oracle 失败。
- OTel provenance gate 仍未关闭；首次 registry 元数据查询的失败发生在本地 repository 名解析（前导 `/`），不是 registry 对目标 tag 的否定证据。
## 2026-08-14 三项目两臂续跑发现
- 接管时 OTel 正式批次 `runtime_results-r3` 仍在运行；最近进度 21/48，前 21 个单元均 `status=completed`。
- 当前活动资源为 `chaosatlas-otel` 中一个预期的 30 秒 NetworkChaos；Chaos Mesh 控制器 Ready，restart count 40，最近一次重启约 43 分钟前。
- Minikube 节点 Ready。沙箱内读取用户 kubeconfig 被拒绝，改用用户授权的本机 `kubectl` 执行权限；这不是集群故障。
- OTel 当前初步分类包含可重复 weakness 和 no-business-impact 两类；正式结论必须等待 48/48 验收及诊断分析。
- 现有 OTel RCA/三项目状态文件仍是早期 2/48 环境阻断版本，正式批次完成后必须重写，不能作为当前最终结论。
- Sock Shop 可复用 `evaluate_runtime_profile`；新增的证据转换明确要求 13/13 deployment Ready（以实际部署数为准）、两次全成功 baseline、completed recovery rehearsal、无 cleanup/residual 错误和稳定 washout。
- Sock Shop 原批次会静默接受少于 4 个候选并执行不足 48 单元，且没有安全续跑语义；已在正式运行前修复为 fail-closed 和 completed-only 复用。
- Sock Shop 原 runner 白名单只有 8 个业务工作负载，而冻结拓扑有 14 个 Deployment；这会错误拒绝 RabbitMQ、数据库和 session-db 等合法模型目标。已对齐到冻结拓扑全量目标。
- OTel 已完成部分显示：checkout/cart PodKill 多次产生业务弱点；500ms network delay 多数维持业务成功；50% loss 至少有一组结果不一致，最终只能逐次陈述，不能推断具体内部机制。
- 原跨根验收器会让先列出的旧失败报告遮蔽同键的新 completed 报告，且未核对 mutation SHA；已修复，避免 OTel r2 历史 H4 环境失败污染 r3 正式验收。
- Sock Shop `runtime-gate-r1` 的失败已定位到冻结输入而非 Chaos：匿名 `GET /orders` 固定返回 `User not logged in`；直连 orders 服务又因旧 Mongo 客户端对 MongoDB 8.2 发出已移除的 `OP_QUERY count` 而返回错误码 352。
- 上游清单对 `carts-db`/`orders-db` 使用无版本 `mongo`，原冻结过程把它解析为运行当日 latest digest，造成应用与数据库协议不兼容。已验证 `mongo:4.4.29` linux/amd64 digest `sha256:6189a342f8da4568b4b111c378a890b1fe186b1bc133742bff8811fe63d2e01e`，并在准备期加入 fail-closed 兼容性约束。
- 前端源码证明订单读路径需要登录 cookie，成功响应码由前端明确设置为 201。新 oracle 为 home -> catalogue -> demo Basic login -> authenticated orders，单次 journey 使用隔离 cookie jar；不把静态 HTML 当作完整业务成功。
# Native runtime launcher finding (2026-08-14)

- The prior `Start-Process` attempt failed before the experiment because the Windows environment contains both `Path` and `PATH`. `Start-Process -Environment` uses a case-insensitive environment dictionary, so the duplicate keys produce `已添加项。字典中的关键字:“Path”所添加的关键字:“PATH”`.
- This is a launcher/environment-bound failure, not evidence against the runner or Minikube. The reproducible workaround is to invoke the existing fixed Python executable directly while inheriting the environment, without constructing an `-Environment` dictionary.
- The native runtime batch then started successfully. Its first five completed reports passed baseline, injection, recovery, cleanup, and residual gates; no knowledge-base write occurred.

# ChaosAtlas-native-full Sock Shop finding (2026-08-14)

- Direct native knowledge use completed 24/24 runtime units. The independent verifier passed: 16 units had no observed business impact and 8 units showed a reproducible business weakness.
- The eight weaknesses are seed-1003 H2/H4/H6/H8, each reproduced 2/2 under 100% outbound packet loss for 30 seconds. Failures were real Sock Shop oracle failures: HTTP 500 and/or timeout.
- Logs provide bounded support for downstream database connectivity failures: `catalogue-db:3306`, `carts-db:27017`, and `orders-db:27017` appear in the corresponding target diagnostics. This does not prove a particular retry, cache, discovery, registration, or circuit-breaker mechanism.
- Sock Shop has no usable Zipkin backend in the frozen topology. Every report records `zipkin-unavailable.json`; no trace-based call-chain claim is made.
- The result is an intentional native-full capability upper bound with project-specific knowledge and allowed pollution. It must not be presented as a fair comparison against full-v1, ablation, or V2-LOO.
- The formal RCA review remains `human_review=pending`, and no knowledge-base update was performed.

# Sock Shop YAML confidence platform-recovery finding (2026-08-14)

- `net-delay-catalogue` ablation replicate 2 is not evidence that the network
  mutation caused a lasting business weakness. Its Chaos resource had already
  recovered and been deleted when the recovery oracle repeatedly returned
  `/catalogue` HTTP 500.
- The direct evidence points instead to an independent deployment condition:
  the stock `session-db` Redis container combines a read-only root filesystem
  with default RDB persistence to `/data`. Redis logged failed background saves
  and then rejected writes with `MISCONF` because
  `stop-writes-on-bgsave-error` was enabled.
- The runtime report remains preserved as `failed`/`invalid_runtime` evidence;
  it is excluded from stable-weakness counting. A new r3 runtime root must
  reuse only completed reports and rerun the affected replicate only after the
  formal baseline is clean.
- The source-side preparation fix disables Redis persistence for that
  read-only session deployment. It is a deployment-stability correction, not a
  ChaosAtlas method change and not a claim about Sock Shop application root
  cause beyond the captured Redis evidence.

# Sock Shop YAML confidence r4 finding (2026-08-14)

- `runtime-exec-r3` was fail-fast. Its `runtime_candidates=10` field reflected
  only the ablation candidates processed before the first stop, not the full
  frozen discovery set. `runtime-exec-r4` therefore reused the 57 completed
  r3 reports and executed the remaining 19 ablation slots, including the
  failed `net-delay-catalogue` retry.
- The exact r3 `net-delay-catalogue` YAML passed server-side dry-run before
  r4. All r4 reports passed baseline, injection, recovery, cleanup, washout,
  diagnostics, and mutation-hash checks; after the batch, the global
  PodChaos/NetworkChaos/StressChaos scan was empty.
- r4's pending review has 19 completed runtime candidates per method:
  native-full has 4 stable weaknesses, 3 nonrepeatable findings, and 12
  no-impact candidates; chaosatlas-ablation has 6, 3, and 10 respectively.
  The stable-weakness yields are 21.05% and 31.58%.
- This is not evidence that the ablation is intrinsically better. The methods
  produced different mutation identities, and r4's newly executed ablation
  slots used the documented 240-second recovery observation budget after the
  Redis remediation. The counts describe end-to-end discovery plus validation
  yield under the recorded conditions.
- No specific internal mechanism is inferred from a business-oracle failure.
  Sock Shop has no usable Zipkin backend in this frozen topology; every
  diagnostics set records the trace state as unavailable. `human_review`
  remains `pending` and `knowledge_base_updated` remains `false`.

# Sock Shop route-aware remaining families finding (2026-08-16)

- The route-aware HTTP rebuild matters: the mutations now target the actual
  service ports and observed call paths, so the HTTP result is not based on
  a generic port or wildcard route assumption.
- Of the 32 HTTP reports, stable weaknesses were produced by HTTP abort on
  `catalogue`, `orders`, and `user`; HTTP delay did not produce a stable
  business failure. This is a business-oracle observation, not a claimed
  implementation root cause.
- Among the 68 completed Stress/Schedule reports, stable weaknesses were
  observed for Schedule-wrapped `PodChaos` `pod-kill` on
  `catalogue-db -> catalogue`, `catalogue -> front-end`,
  `orders-db -> orders`, and `user -> front-end`. The `delay` token in the
  hypothesis IDs is a legacy family label, not the nested Chaos Mesh action.
  `user-db -> front-end` was mixed across the two replicates and is marked
  unstable rather than counted as a real stable weakness.
- The logs support bounded evidence such as catalogue reporting
  `database connection error` during catalogue-db disruption and the
  front-end reporting `Can't set headers after they are sent` in the same
  run. These observations support the affected business path, but they do
  not by themselves prove a particular Eureka, cache, registration, or
  retry mechanism.
- `zipkin.json` sidecars exist and hash correctly, but the frozen Sock Shop
  topology has no usable Zipkin backend. They are therefore evidence of
  trace unavailability, not positive trace attribution.
- DNSChaos is explicitly classified as platform-blocked: Chaos Mesh could
  not create `/etc/resolv.conf.chaos.bak` because `/etc/resolv.conf` was
  read-only. It contributes zero business weaknesses and is not rerun.

# Sock Shop 三方法阶段口径复核（2026-08-16）

- Full 去重台账冻结 114 个 family，全部已有静态适用性处置。`runtime-remaining-route-aware` 的选择清单把其中 38 个已有完成证据的 family 与 58 个后续候选合并为 96 个 runtime cohort family；58 个后续候选中 8 个 DNSChaos 在业务注入前被平台 gate 阻断。其余 18 个是静态 gate failed：6 个 DB/中间件 HTTP abort、6 个 HTTP delay、6 个缺少正确 source->DNS-name 映射的 DNS 假设。
- 对所有 native-full `runtime_reports` 按 `mutation_id + replicate` 选择最新 completed 报告，得到 88 个真正完成注入的 family、176 个重复槽位；全部 baseline、injection、recovery、cleanup 和 washout 字段通过。Full 结果为 15 个稳定 family、3 个一发性/混合 family、70 个两次均未观察到业务弱点的 family；另有 8 个 runtime platform-blocked 和 18 个 static gate rejected，没有未处置 family。
- 15 个稳定 family 中，Schedule 的 4 个 `delay` 名称实际封装的是 `PodChaos/pod-kill`；另一个 `sock-pod-failure-catalogue-002` 的实际 action 也是 `pod-kill`。按故障作用目标合并这些直接/定时重复后，是 10 个问题面，不是 15 个互不相同的代码级 ISSUE。
- 当前最终 Ablation discovery 生成 12 个假设；正式主结果是 catalogue-db PodKill 和 orders-db PodKill 两个稳定弱点。`hyp-003` user PodKill 是 exploratory 多跑结果，不进入正式分母。Full 的 15 个稳定 family 包含这两个可执行弱点，因此覆盖当前 Ablation 的 2/2。
- ChaosEater 的两类阶段结论属于可用性测量层：front-end 单副本单点故障，以及 readiness/recovery 慢。Full 的业务 mutation 15-family 清单不应直接宣称包含这两个 availability issue；ChaosAtlas 的独立 availability 轨道有对应证据，但实验设计晚于已知 ChaosEater 结论，存在确认偏误边界。
- Ablation 即将重做，因此当前 `15 vs 2 vs 2` 只能作为阶段性问题集合盘点，不能作为公平方法优越性统计。
# 2026-08-16 Sock Shop Ablation YAML15

- YAML15 r1 去敏审计发现 Schedule 内嵌 `statusCheck.http.url` 仍保留源域名，故 r1 禁止发送；r2 增加 URL 和 label key 归一化后敏感扫描 0 命中。
- YAML15 r2 fingerprint 为 `48884d9c75014845dd0fe1f6bd20d703c1577cdca6ae5ec2d4bdcd717c1409cf`，prompt SHA-256 为 `36ca40fc1d0d2a45d848f959f0fd754ab2e894f475dbbb8012bf0e700a2d31df`；独立确定性复跑一致。
- Full 时间硬上限的权威来源是 `runtime.../discovery/native-full.json` 的 `timing.generation_seconds=1419.047`，源文件 SHA-256 为 `5ea0f2331ca7cb27ce6c05e195d02d2a055078f74590540e57da11689c28a965`。
- 新 discovery 输出的调用链位置只能标为 `model_inference` 或 `unknown`；后处理适配器保留 YAML15 已获得类别示例这一边界，不再错误标记为无分类可见性。
- 用户与老师确认：新版 Ablation 在 discovery 前获得五类明确标注的真实 YAML，每类 3 个，共 15 个；LLM 自主停止，Full discovery wall-clock 为硬上限。
- 该实验臂应命名为 `chaosatlas-ablation-yaml15`，因为它已获得类别标签，不能继续描述为“无分类 Ablation”。
- YAML15 只补充故障语法和动作示例，不提供知识库、历史弱点、Sock Shop 调用链、Full 假设、置信度、停止轨迹或 runtime outcome。
- 权威语料入口是 `raw_yaml/`：总数 1935，五类 runtime scope 共 1506；现有分类器可提取 kind、action、mode、selector、duration 和 intensity 静态特征。
- 样本选择必须确定性且与结果无关；冻结原始与结构化去敏文本的 SHA-256。

# 2026-08-16 主线整理发现

- README、PROJECT_SUMMARY、ARCHIVE_MAP 和 EXPERIMENT_CATALOG 曾分别保留不同阶段的项目角色或 ChaosEater 状态；当前统一为论文主线四阶段，旧日期文档改为冻结历史入口。
- 当前 Sock Shop 主线 headline 是 Full 15 个稳定 weakness、YAML15 Ablation 9 个稳定 weakness；同候选池、旧 Ablation 和问题面归并不进入主线 headline。
- 关键工具的执行责任已明确分层：静态分类/停止规则不等于 runtime 结果，编译器不调用 kubectl，gate 只做只读适用性判断，runner 才负责完整生命周期。
- 首次 focused pytest 的 17 个错误均发生在 Windows 系统临时目录权限 setup 阶段；改用工作区隔离 basetemp 后 focused suite 通过，未修改生产逻辑。
# 2026-08-16 Sock Shop YAML15 Ablation findings

- DeepSeek self-stopped after 734.188 seconds and 458 calls, below the frozen 1419.047-second Full cap.
- Independent normalization reduced 458 raw hypotheses to 51 families; 46 were executable and 5 database HTTP-abort families were compile-blocked.
- Runtime completed 92/92 slots. Results are 9 stable weaknesses, 0 unstable families and 37 no-impact families.
- Full and YAML15 Ablation overlap on 8 stable problem surfaces. Full-only surfaces are catalogue loss and partition; Ablation-only is user 500ms delay.
- Full 15/88 versus Ablation 9/46 gives Fisher two-sided p=0.813213712; Wilson 95% intervals overlap, so no stable-rate superiority claim is supported.
- All 92 mutation hashes and 552 diagnostic hashes match. Zipkin is unavailable by frozen profile, so no trace-root-cause claim is supported.
- The initial NetworkChaos runner could complete while a probe-restarted target Pod remained NotReady. The runner now requires target Ready after washout; 39 continuation reports record target_ready=true.
- The 53 reused completed reports retain the legacy schema but pass the original lifecycle/hash gates. Their results are not rewritten.
- Git initially normalized evidence YAML from CRLF to LF and ignored `.log` files, which would have invalidated recorded hashes after clone. The formal r2 evidence tree is now `-text -eol`, ignored logs are force-added only for that tree, and staged-blob verification passes 92 mutation plus 552 diagnostic hashes.

# 2026-08-16 YAML15 independent review follow-up

- RED verification reproduced three review findings: compile exclusions were labeled plain `passed`; a model response arriving after the wall-clock deadline could be accepted as self-stop; and DeepSeek retries reused the initial timeout instead of enforcing an absolute request deadline.
- Minimal fixes now pass 30 focused tests, including CLI success for `passed_with_exclusions`, post-response deadline precedence, retry deadline enforcement, and the existing target-ready failure behavior.
- Full `15/88` is composed of two disjoint runtime evidence batches: the first 38 families are under `runtime-canonical-plan-r2` (`8 stable / 2 unstable / 28 no-impact`), and the later 50 are audited by route-aware r3 (`7 / 1 / 42`). The first batch now has a deterministic 76-report verification manifest with per-report SHA-256 plus a 38-family result review.
- Independent review found that rounding the remaining discovery budget to milliseconds could turn `0.0004` into `0.0`, after which truthy fallback restored a 120-second request budget. The payload now preserves sub-millisecond budgets and the request wrapper treats only `None` as “no supplied deadline”; zero expires before opening a request.
- Terminal discovery checkpoints now return unchanged on resume, preventing additional model calls or timing/token evidence drift. The stage review no longer labels the superseded 12-hypothesis Ablation as current, and final audit SHA labels now have an explicit one-to-one `source_paths` map.
## 2026-08-21 仓库瘦身边界

- `tools/bin/` 是本地安装介质，不是 ChaosAtlas 研究输入或运行证据；保留本地但停止版本跟踪可以立即阻止后续体积增长。
- `.pytest-tmp/` 只包含测试生成物，且旧忽略规则 `.pytest-tmp-*` 未覆盖无后缀目录；已补充精确忽略规则并清理。
- Git 历史中的 Helm 二进制仍然存在；彻底减少 clone 体积需要 `git filter-repo` 和 force-push，不能在保守清理中隐含执行。
- `artifacts/`、`raw_yaml/`、知识卡、运行台账和失败轮次是证据链，不能因“看起来冗余”删除。
- 本轮 commit `b879feb` 只包含 `.gitignore`、`docs/ARCHIVE_CLEANUP.md` 和 `tools/bin/` 索引删除；其他工作区修改没有被暂存。
# 当前阶段发现（2026-08-21）

- `KubernetesPreflight` 已覆盖 kubeconfig、namespace、Deployment/Service/Pod、events 和 Chaos 残留检查，但没有输出可供编排器使用的规范化 inventory。
- `OfflineProjectAdapter` 能生成候选，但依赖冻结 facts；live 模式若继续使用它，无法做到面对新部署项目主动发现。
- `build_deployment_node` 和 `compile_scenario` 可复用为 live inventory 到 TestNode/候选的确定性转换层。
- 候选只描述“可验证故障假设”，不代表漏洞；最终结论仍需 lifecycle、业务 Oracle 和 RCA 证据。
- 真实只读验证：`sock-shop-lab` 当前返回 14 个 Deployment、14 个 Service、14 个 Pod；统一 adapter 生成 84 个候选，覆盖 `pod_kill`、`container_kill`、`stress_cpu`、`stress_memory`、`network_loss`、`network_partition`。
- 现有 Sock Shop profile 缺少 HTTP oracle 的 `service` 和 `remote_port`，因此统一 live 命令在候选发现后、任何注入前返回 `environment_blocked`；这是预期的 fail-closed 行为。
- live execute 现在写入 `evidence_refs.json`，默认采集 namespace events 和目标 Deployment logs；采集失败或敏感输出会转为 unavailable，不会被当成 RCA 结论。
- 真实只读 evidence smoke：`sock-shop-lab` events 与 `deployment/front-end` logs 均成功返回 supports evidence，并写入 sha256 artifact。
- live CLI 现在在 executor 前强制写入 `preflight.json`；真实 `sock-shop-lab` preflight 返回 `ready_for_injection`，Chaos residual 为 `clean`，未执行 mutation。
- 业务路径摘要已作为 `business_path_replay` evidence 写入并引用；live 默认只选择与 HTTP Oracle `service` 同名的 `pod_kill` Deployment，显式不匹配候选直接阻断。

## 2026-08-23 Phase 5 fresh deployment findings

- Sock Shop 原始 manifest 含 `front-end` NodePort `30011`；NodePort 是 cluster-wide 资源，fresh namespace 不能复用。副本必须显式转为 ClusterIP，不能把该平台适配误写成应用防御知识。
- Minikube 当前只有 8 GiB 内存。原 `sock-shop-lab` 与完整 fresh copy 同时运行约 28 个业务 Pod，控制面达到 99.5% 内存并出现 TLS handshake timeout；这是部署容量阻断，不是业务弱点、RCA 或防御成功。
- `sock-shop-improvement-lab` 已创建并有 fresh 资源；在 API 恢复前禁止重复 apply、Chaos 注入、Oracle 判定和知识写入。优先通过 API 恢复后执行 adapter cleanup；若控制面持续不可用，需先重启 Minikube，再做 namespace 清理。
- 下一轮 fresh retest 应采用两种可审计方案之一：提高 Minikube Docker 内存，或生成只包含 front-end 及其业务依赖的最小 fresh 拓扑；不能通过删除原实验 namespace 来“腾资源”。
- 已恢复控制面并完成专用 namespace cleanup；原 `sock-shop-lab` 未被删除。现有 profile 的 8GiB/CPU 限制不能原地修改，Minikube 要求 delete/recreate；因此推荐独立高资源 profile，避免破坏已有实验集群。

## Phase 10 follow-up audit findings（2026-08-24）

- 当前 context 的 `chaos-testing` 只有 Chaos Mesh 控制面；本次只读资源发现与证据采集没有把它当成 Sock Shop 业务应用，也没有切换或重建集群。
- 计划动作与证据的 target 边界已验证：Service action 使用 `service_target`，Deployment/Logs 使用 `deployment_target`；这避免 selector 相同或服务名不同导致证据抓错资源。
- `run-r2/smoke_audit.json` 为 `passed`：3 Deployments、4 Services、4 Pods、18 candidates、7 planned actions、5 collector records；禁止命令为 0，Chaos 资源残留扫描为空。
- 本轮只读结果可以证明“计划动作能在真实控制面被安全派发并保留 provenance”，不能证明业务影响、RCA、弱点发现率或 Shadow 优于 Legacy。

## Phase 10.1 Sock Shop context correction findings（2026-08-24）

- 本机 kubeconfig 同时有 `chaosatlas-improvement`、`kind-chaos` 和 `minikube`；8G Sock Shop 实际在 `minikube/sock-shop-lab`，不是默认的 `chaosatlas-improvement`。
- 显式指定 `--context minikube` 后，真实只读 inventory 为 14/14/14，候选空间为 84；这证明前一次 blocked 是 context 选择问题，不需要重建、删除或迁移集群。
- 真实 Sock Shop smoke 选中 `front-end` PodKill 候选，计划 7 个动作，实际 5 个只读动作全部 supports；evidence refs provenance 完整，Service/Deployment target 分离正常。
- 所有命令均只读，敏感扫描 0 命中，Chaos 资源残留 0；本轮没有执行 PodKill，因此没有新的 runtime weakness、RCA 或知识晋级证据。

## Phase 11 Guarded canary findings（2026-08-24）

- 正确的 context 选择使 live preflight 通过：`minikube/sock-shop-lab` 有 14/14/14 资源，Oracle 为 `front-end:80`，注入前 Chaos residual clean。
- 真实 PodKill 造成短暂业务不可达，随后在 replacement Pod Ready 后恢复；这支持“单副本 front-end 在 PodKill 期间存在可用性降级”的受限观察，不支持更深层代码根因或防御机制结论。
- service-target 泄漏是一个真实 planner 输入风险：旧逻辑把最后一个遍历 Service (`user-db`) 绑定到所有候选；修复后每个 candidate 从自己的 deployment node 读取 Service，r2 evidence plan 和 live evidence 均为 `front-end`。
- lifecycle、机制边界和 cleanup 证据完整，RCA 状态为 `confirmed`，但知识状态保持 `provisional`，正式知识库未更新；该结果不是重复实验，也不能单独改变 Shadow gate。
- 全量测试目前有 20 个失败，集中在 `runtime_applicability_gate`/`remediation_phase2_gate` 历史夹具字段契约和 `chaosatlas_batch` 的 OfflineProjectAdapter 调用签名；本轮只验证相关 focused suite，不把全量状态包装成全绿。

## Phase 11 follow-up findings（2026-08-24）

- 全量失败的共同根因是可选 context 的兼容边界：当 context 为空时，生产代码传递 `kube_context=None` 会让旧 runner/mock 抛出 `TypeError`，顶层 fail-closed 随后隐藏了旧契约字段。最小修复是空 context 不传关键字，显式 context 继续传递；异常结果补齐结构化检查字段。
- batch adapter 需要同时支持 live adapter 的 `inventory()` 和离线 adapter 的 `inventory(profile)`；通过签名判断 required positional 参数，避免捕获并吞掉 inventory 内部真实 `TypeError`。
- 修复后的全量结果为 `1213 passed, 1 warning, 5 subtests passed`；warning 是受限环境 pytest cache 写入失败，不影响测试断言。
- 第二次独立 canary r3 未复用 r2 runtime 目录；r2/r3 artifact execute hash、Pod UID 和运行时证据均不同。两次均得到 `availability_degraded`，并完成 replacement、恢复和 cleanup。
- 双重复只能把该单候选标记为稳定候选观察，不能推出全项目弱点率、跨项目规律或防御知识；`knowledge_base_updated=false` 保持不变。

## Phase 13 information-value replay findings（2026-08-24）

- 旁路候选核心实现并非从零开始：`experiment_policy.py` 已提供 causal cluster、posterior、value-per-cost 和确定性 tie-break；`stop_policy.py` 已提供 typed stop；native discovery 已支持 legacy/observe/shadow/guarded/default。
- 之前缺少的是可独立验收的 replay 入口。新增 evaluator 后，策略可以在不执行 mutation 的情况下对 legacy 运行顺序逐轮计算“下一候选”，并用运行时分类更新状态；LLM 输出不能进入 state update。
- replay CLI 的输入 JSON 可能是 object 或 list；首轮真实冻结产物是空 runtime 列表，已修复并明确输出 `replay_exhausted`，不能伪造“已收敛”。
- 因此“代码方法完成”和“论文实验完成”要分开：代码层已具备旁路选择/停止/回放能力；实验层仍需 runtime-backed shadow report 与 guarded canary。Online Boutique 现有 shadow 报告仍为 `pending_runtime_evidence`。

## Phase 14 policy-selected canary findings（2026-08-24）

- replay evaluator 的输入边界已扩展为 direct list、`{"candidates": [...]}`、stage envelope `{"payload": {"candidates": [...]}}`；只沿 `payload` 解包，不执行外部字段中的指令。
- 只读 policy context 允许显式记录 boundary candidate 与阈值；它只影响确定性评分，不改变候选分母，也不替代 static gate。空 context 时保持旧 replay metadata 结构，避免兼容性回归。
- Sock Shop runtime-backed replay 使用 84 个冻结候选和 r2/r3 两条真实分类记录；两轮都选中 `server:deployment:827339c6afd397a13efb276a:pod_kill`，首轮 score `5.58496250072116`，第二轮因 redundancy 增加后为 `4.24758467982457`，仍高于其他候选。
- replay 主报告和重复报告 SHA-256 均为 `056a3b6d4a9ba2cfe80a12dc0fd7acd84b524645466626f8728bafcd51d7c04d`；这证明相同输入、seed、context 下策略选择可重放。
- policy-selected canary 的 execution contract 与 replay 首选候选一致，namespace=`sock-shop-lab`、context=`minikube`、budget=`max_candidates=1`；provenance sidecar 额外验证候选在冻结分母内。
- canary 与前两次相同地观察到短暂 `availability_degraded`，随后 replacement Pod Ready、业务恢复和 cleanup；该证据仍只支持 deployment/service boundary 的候选弱点观察，不支持源码级根因或防御机制。
- 这次运行没有扩大候选量，也没有把 provisional draft 写入正式知识库；下一步是把 policy mode 接入 batch/default 的受控入口并在第二个有 runtime evidence 的项目重复验证，默认仍保持 legacy。
- 最终验证没有发现断言失败：policy focused `32 passed`，全量 `1228 passed, 1 warning, 5 subtests passed`，compileall/diff check 通过。唯一 warning 是受限环境无法写入全局 pytest cache，未影响测试结果；为此所有 pytest 使用仓库内可写 `--basetemp`。

## Phase 15 policy selection gate integration findings（2026-08-24）

- 旁路阀门已经落在 batch 编排边界，而不是替换主实验生命周期；`legacy` 默认路径的候选顺序和执行语义保持不变。
- `shadow` 的策略结果与实际执行列表分开记录，因此可在不改变实验的前提下积累对照数据；`guarded/default` 只执行冻结分母内的 policy 选择结果。
- policy state 不完整、schema 非法、候选越界或评分异常都会 fail-closed 回退 bounded legacy prefix，避免策略故障扩大实验范围或执行未知候选。
- 单候选 CLI 使用非 legacy policy 会显式阻断，要求调用 batch 入口；这消除了“配置已打开但没有真正经过选择阀门”的隐性误用。
- 本轮验证结果为定向 `52 passed`、全量 `1235 passed`（另有 1 个受限 pytest cache warning 和 5 个通过的 subtests）；compileall 和 diff check 均通过。
- 该接入只证明代码契约和离线行为可验收，不证明跨项目发现率提升。下一步实验仍需第二个有 runtime evidence 的项目完成 shadow 对照，再按批准的预算逐步启用 guarded。

## Phase 16 Online Boutique offline Shadow findings（2026-08-24）

- 第二项目现在有非空 runtime-backed Shadow 输入：55 个冻结候选、4 个候选、8 份完整源报告；每个候选两次 `weakness_observed`，且生命周期字段和源 hash 均通过审计。
- 投影器把稳定的双重复现象归一为 policy 层 `confirmed_weakness`，同时保留 `weakness_observed` 原始分类和完整 provenance；该归一化只用于实验策略状态，不进入正式知识库。
- 两次 replay 的输入 hash、决策列表和完整报告 SHA-256 完全一致；`recorded_result_count=4`，四轮 `decision_changed=true`，policy 每轮推荐同一个尚未执行的 `adservice` CPU-stress 候选。
- 由于输入是 Legacy 历史顺序，policy 推荐未执行候选是预期的 Shadow 差异；它不能证明该候选实际更可能发现问题，也不能替代 guarded runtime 验证。
- replay metadata 明确为 `cluster_access=false`、`model_called=false`、`mutation_executed=false`、`formal_knowledge_written=false`；默认 `legacy` 和 guarded gate 均未改变。

## Phase 16 第二项目离线接入 findings（2026-08-24）

- Online Boutique fixture 通过统一 dry-run 编排器，完整产出 inventory、server deployment detection、candidate space、hypotheses、evidence plan、execution contract、artifact index 和 phase6 audit。
- 第二项目的 retrieval 明确为空（`knowledge_status=read_only`、`cards=[]`），因此 Sock Shop 的 `local_reusable` 知识没有被错误复用；知识写入和晋级均保持关闭。
- 该 fixture 的候选分母为 12（frontend/payment 两个 Deployment × 六类服务器部署故障），其中 payment 被静态标记为 singleton availability risk；本结果只验证契约，不代表真实 Online Boutique 集群的完整部署清单。
- dry-run 的执行、分类和 RCA 均带 `claim_scope=synthetic`，结果为 `not_run`；这证明工具不会把规划阶段的假执行包装成漏洞、根因或知识。
- 边界更新：跨项目离线接入已完成；要评价发现质量和 RCA 能力，仍需 Online Boutique 独立 namespace 的真实只读 evidence smoke 及后续 runtime-backed shadow，不能用 fixture 结果替代。

## Phase 17 Online Boutique 真实只读 evidence findings（2026-08-24）

- `minikube/chaosatlas-online-boutique` 可访问，真实只读 inventory 返回 11 个 Deployment、12 个 Service；所有 Deployment 当前为 `0/0`，没有 Pod。
- 真实候选分母为 66（11 个 Deployment × 6 类服务器部署故障），证据计划按预算 1 选择 `frontend/pod_kill`，且 Service target 没有泄漏到其他服务。
- Deployment、Pod state、Service 和 Events 采集成功；Logs 因没有运行中 Pod 为 `unavailable`。这验证了 evidence collector 的“不可用诊断不等于负证据”边界。
- 采集过程只走 `kubectl get`/`kubectl logs` 只读路径，未调用统一 live executor；前后 namespace 副本状态一致，Chaos Mesh 资源残留为 0。
- 该 smoke 不支持任何漏洞、RCA 或防御结论；要进入 runtime-backed shadow，必须先恢复 Online Boutique 副本并完成业务 HTTP Oracle 基线，再申请单候选受控注入。

## Phase 18 Online Boutique runtime 闭环 findings（2026-08-24）

- Online Boutique 在独立 namespace 恢复 11 个单副本 Deployment 后，frontend `/` Oracle 基线稳定为 HTTP 200；两次可用于晋级的运行均完成注入、观察、恢复和 cleanup 生命周期。
- r4 与 r6 的分类均为 `availability_degraded`，RCA 均为 `confirmed`；证据包含 Deployment、Pod、Service、Events、Logs、业务 Oracle 和 service-boundary mechanism，RCA 不宣称源码级根因。
- 相同输入/seed 的重复会得到相同 `run_id`，但 execute/artifact hash 和 Pod UID 仍能证明实际独立执行；promotion stage 仍要求 distinct run_id，因此使用不同 seed 的 r6 作为第二个晋级样本。
- 一次外部同场景 PodChaos 残留曾在首轮完成后短暂出现，且其名称/动作与首轮工件不同；按精确名称清理后复查残留为 0。该事件说明全局 residual scan 必须晚于控制器最终一致窗口，不能只依赖单个 run 的 cleanup 字段。
- `KB-WEAK-9faeb7cf3d7059da` 已成为 Online Boutique 的 `local_reusable` 弱点卡，绑定 project commit、frontend deployment/service boundary 和两次证据指纹；知识回流后 dry-run 首选同一 frontend PodKill，证明知识已影响下一轮候选。
- 当前结论仍是受限的服务边界可用性弱点，不是源码级根因、超时机制或跨项目普遍规律；跨项目迁移仍需 feedback protocol 和独立验证。

## Phase 19 Guarded container-kill findings（2026-08-24）

- Guarded r1 的 recovery false 不是业务未恢复：运行时 Pod 仍为同一 UID，但目标容器以 `exitCode=137` 终止后 restartCount 从 0 增至 1，容器和 Pod Ready，HTTP 在短暂失败后恢复；问题是把所有 `PodChaos` 都套用 Pod replacement identity contract。
- recovery 语义已按 fault family 分离：PodKill 仍要求新 Pod UID；ContainerKill 要求目标容器 restartCount 增长、Pod Ready 稳定和业务 Oracle 成功，不要求新 Pod UID；缺少目标记录或 restart 证据仍 fail closed。
- Guarded r2 输出 `artifacts/phase17-online-boutique-guarded-live-20260824-r2/`：policy 选择与执行均为 `server:deployment:7058d0db85bc2f8c6c290462:container_kill`，Legacy 为 `pod_kill`，`decision_changed=true`、无 fallback。
- r2 lifecycle attestation 全部通过：baseline/injection/observation/recovery/cleanup/independent_oracle 均 true，recovery state 为 `container_restart`，同一 Pod 的 restartCount `0 -> 1`，Chaos cleanup verified，残留为 0。
- r2 的 RCA 仅为 `bounded`、knowledge 为 `provisional`，正式知识库没有更新；这是预期边界，不应写成 confirmed weakness。
- 机制 evidence 生成器已改为按 recovery mode 输出：container restart 不再声称 Pod identity change，并保留 pre/restart counts 和 restarted pod 列表；旧 r1/r2 append-only artifacts 不回写。
- 该修复提高了恢复判定精度和候选可比性，但尚不能证明旁路策略在跨项目发现率、成本或假设精度上优于 Legacy；这些仍需冻结分母上的正式对照实验。

## Phase 20 P02 runtime closure findings（2026-08-24）

- Minikube 控制面资源调整后，P02 真实 inventory 为 10/10/10，`api-gateway` Oracle 可用；服务器部署检测生成 60 个候选，首个受控候选与 Oracle service 对齐。
- r1 与 r4 的完整证据支持受限结论：单副本 `api-gateway` PodKill 会造成短暂业务不可达/连接失败，replacement Pod Ready 后恢复；这属于 deployment/service boundary availability weakness，不是源码级根因。
- r2 的失败根因是证据时间/对象绑定错误：namespace events 是历史全集，文件名虽是 r2，但其中的 PodChaos 对象仍为 r1。此前“实际注入并恢复”的判断不成立，已按 `injection_not_confirmed`/environment blocked 边界排除。
- r3 的失败根因是业务基线瞬态 HTTP 协议异常 `BadStatusLine`，发生在 executor apply 前；只读重复基线随后连续通过，故增加短窗口重试并保留失败样本，不能把 r3 当作弱点重复。
- live 事件证据现在可按当前 mutation name 查询；当 live executor 没有 action identity 时，planned `pod_events` 记录为 `unavailable`，不会使用旧事件支撑 RCA。
- P02 knowledge promotion 只选 r1/r4，生成 `KB-WEAK-172535b133dde433`、`local_reusable` 和 reproduce/guard intents；知识 root 与其他项目隔离，未宣称跨项目迁移。

## Phase 20 follow-up P02 fixture and knowledge replay findings（2026-08-24）

- 离线编排器严格比较 profile/facts 的 `project_id` 和 `project_commit` 是正确边界；原 P02 fixture 同时存在小写 synthetic profile 与大写 formal facts，导致 dry-run 在 onboard 阶段 fail closed。
- Windows 路径不区分 `p02` 与 `P02`，不能只靠大小写文件名区分 facts。当前以 `project_facts_runtime.json` 作为正式大写 P02 的显式变体，小写 `p02` 测试继续使用默认 `project_facts.json`；身份字段仍严格相等。
- 形式 profile dry-run 的回归现已通过，三项目离线回归不再受 P02 mismatch 影响。
- 同一正式 P02 profile/seed 的知识回流对照显示：无知识 retrieval cards=0、首候选为 `admin-server/container_kill`；加载 P02 `local_reusable` 卡后 retrieval cards=1、首候选变为 `api-gateway/pod_kill`。这证明知识改变候选优先级，但不是新 runtime 证据。
- 两个回放均输出 60 个候选、synthetic finding/RCA/knowledge draft，未执行 Kubernetes mutation、未调用模型、未写正式知识库；不能将 dry-run 结果当成新的漏洞或 RCA。
- 全量验证中发现并修复一个与本阶段相邻的可重复性缺陷：ablation 完成时 checkpoint 和函数返回分别重新计算 wall-clock，resume 结果可能不相等；现在写入和返回共用同一结果对象，避免影响后续 checkpoint/replay 审计。

## Phase 21 OTel Demo preflight findings（2026-08-24）

- OTel Demo 当前真实运行时已恢复：`minikube/chaosatlas-otel` 有 11 个可用 Deployment、11 个 Service、11 个 Running Pod；之前的 TLS/API 阻断已不再出现。
- 统一 live batch 只读 preflight 选出一个 `pod_kill` 候选，gRPC `AddItem_then_PlaceOrder` Oracle 配置有效，运行前残留扫描为 clean。
- 因未提供 `approve_live`，生命周期在 gate 停止，未执行 mutation；这证明审批门仍然有效，不能把 preflight ready 写成漏洞、RCA 或知识。
- 下一步是显式批准后执行一个 Shadow 候选，先验证 gRPC 业务观察、恢复和 cleanup，再决定是否进入第二次重复或 policy 对照；默认不扩大候选批次。

## Phase 21 OTel Demo Shadow findings（2026-08-24）

- 单候选 checkout PodKill 真实运行支持受限的 deployment/service boundary 可用性观察：replacement 期间 gRPC PlaceOrder 出现一次不可达，随后 10 次请求成功恢复。
- RCA 状态为 `confirmed`，但根因范围仍限定在服务边界机制；结果不支持源码级根因、超时机制或跨项目普遍规律。
- 生命周期 attestation、replacement identity、业务恢复、cleanup 和独立 residual scan 全部通过；正式知识库保持不变，知识状态为 `provisional`。
- 该轮足以建立 OTel Demo 的第一条 runtime evidence，但不足以晋级 `local_reusable`；下一轮需不同 seed 的独立重复，并继续使用同一 gRPC Oracle 和清理门禁。

## Phase 22 OTel Demo feedback reflow findings（2026-08-24）

- r2/r3 的完整 attestation 满足 feedback protocol 的双重复现门槛，因此 `container_kill` 在项目级 policy state 中由 `unknown` 更新为 `weakness`；这不是正式知识库写入。
- 回流保留原始分类和来源哈希，策略层只使用确定性归一化结果；r1 的 `response_observed`/`bounded` 仍留在审计中，未被错误晋级。
- replay 显示重复 `container_kill` 的 uncertainty/冗余扣分后 value 从 `3.5849625` 降为 `2.2475847`，下一推荐转为 `network_loss`；其它候选未解决，所以停止条件仍为开放状态。
- 回流过程没有执行 mutation、模型调用、集群写操作或正式知识更新；主实验分母和默认 `legacy` 模式均未改变。
- 结论仅支持 OTel Demo 项目级策略状态已学习到该候选的弱点证据，不支持跨项目迁移、全局发现率提升或自动切换 guarded。

## Phase 23 OTel Demo network-loss preflight findings（2026-08-24）

- 反馈后的策略状态已经影响真实 batch 入口：在同一 OTel 候选分母、单候选预算下，实际选择从已确认的 `container_kill` 转向 `network_loss`，且无 fallback。
- `network_loss` 的静态目标仍为 checkout deployment，selector 为 `app=checkout`，恢复契约为 replacement Pod、Ready、业务 gRPC Oracle 和 cleanup。
- 真实只读 preflight 通过：namespace Active、11 个 Deployment/Pod Ready、Oracle 配置有效、Chaos residual 为 0。
- 该轮在 `approve-live` 门前停止，不能解释为 network-loss 弱点、RCA 或防御结果。下一步只有在审核批准后，才执行一次单候选 live canary。

## Phase 24 OTel Demo network-loss execution findings（2026-08-24）

- 批准后的第一次执行没有注入：运行时安全门发现 NetworkChaos 缺少 `mode: one`，说明静态 candidate `compile_eligible` 不能替代最终 mutation YAML 的安全校验。
- 已按 TDD 修复：所有 live `stress_cpu/stress_memory/network_loss/network_partition` manifest 现在显式使用 `mode: one`；回归测试先 RED 后 GREEN，相关验证 `26 passed`。
- 修复后的第二次执行通过 applicability gate，但在 baseline 阶段因 `.venv` 缺少 `google.protobuf` 停止，`injection_confirmed=false`，没有执行 NetworkChaos。
- 安全边界保持完整：两次尝试后 namespace 仍健康、11/11 workload Ready、Chaos residual=0；不把 `injection_not_confirmed` 当作弱点或环境防御结论。
- 当前唯一阻断是本地 OTel gRPC Oracle 依赖，需要在 `.venv` 安装 `grpcio` 和兼容 `protobuf`；外部安装审批返回 502，当前无法在本轮继续 live canary。

## Phase 25 OTel Demo dependency unblock findings（2026-08-24）

- 用户批准继续后，依赖安装请求按系统允许次数重试，但外部审批服务连续超时，未写入 `.venv`。
- 本机不存在可替代的 `grpcurl`、`grpc_cli`、`protoc` 或离线 wheel，因此无法在不改变 Oracle 契约的情况下恢复 baseline。
- 该阻断发生在业务 baseline 之前，仍未执行 NetworkChaos；不能将本轮标记为 network-loss 的运行结果。
- 当前下一步是由外部环境完成 `grpcio/protobuf` 安装后，重新运行同一 guarded 单候选 canary；策略状态、候选分母和默认模式无需改变。

## Phase 26 OTel Demo dependency permission findings（2026-08-25）

- 依赖问题已从“未安装”细化为“安装目录存在但当前用户不可读”：`google/grpc` 包目录及两个 dist-info 均存在，普通 Python 仍无法导入。
- 这解释了 pip 元数据检查的 `PermissionError`，但不能据此假设 Oracle 已可用；生成的 `demo_pb2` import 仍失败。
- Kubernetes 侧没有对应的持续 Chaos 资源，11 个 Pod 均 Running；短暂的资源查询结果随后恢复为 clean，未形成新的运行证据。
- 下一步需要由环境管理员修复 `.venv` 目录 ACL 或在当前用户可读的虚拟环境重新安装依赖；修复后先跑 Oracle import/baseline，再继续 canary。

## Phase 27 OTel Demo network-loss canary findings（2026-08-25）

- `.venv-otel-runtime` is a usable project-local fallback: `google.protobuf` and `grpc` import successfully, while the original `.venv` remains ACL-blocked. No protected files were deleted or replaced.
- The fresh preflight passed on `minikube/chaosatlas-otel` with 11/11 workloads ready, the gRPC PlaceOrder Oracle configured, and no residual Chaos resources.
- The approved `network_loss` mutation was confirmed by Chaos Mesh Apply/Recover for one checkout target. The independent gRPC Oracle recorded a transient degraded observation and then recovered; baseline was 10/10 and cleanup was verified.
- The run is valid runtime evidence (`availability_degraded`, RCA `confirmed`, knowledge `provisional`) but only one replicate. It must not update the project policy state to `weakness` or promote formal/reusable knowledge until a distinct second complete replicate is reviewed.
- After cleanup, all Chaos resource classes were empty and all 11 OTel Pods were Running. The remaining environment task is an administrator ACL repair for the original `.venv`; until then use `.venv-otel-runtime` for this Oracle.

## Phase 28 OTel Demo `.venv` ACL repair findings（2026-08-25）

- The initial ACL grant ran elevated as `DESKTOP-D53KD3M\\23741`, while the active Codex process is `DESKTOP-D53KD3M\\codexsandboxoffline`; therefore the first grant did not affect the actual runtime user.
- After explicit authorization, the active user was granted access to the exact gRPC/protobuf targets and the two dependency paths named by the next import errors. No environment recreation or deletion was performed.
- The original `.venv` now passes `import google.protobuf, grpc`; `pip show` reports `grpcio 1.83.0` and `protobuf 7.36.0`; the focused policy-feedback test passes (`4 passed`).
- The dependency permission blocker is resolved. The next live canary, if approved, can use `.venv\\Scripts\\python.exe`; the prior canary remains valid evidence and does not need replay solely because the interpreter path changed.

## Phase 29 OTel Demo network-loss dual-replicate findings（2026-08-25）

- The second guarded `network_loss` run used `seed=1002` and a distinct run identity `live-aa28cef942de`; it reproduced the first run's bounded checkout deployment/service-boundary result.
- Both runs have complete lifecycle attestations, independent gRPC Oracle evidence, confirmed Apply/Recover behavior, transient availability degradation, RCA `confirmed`, and verified cleanup. The namespace is clean after the second run and all 11 workloads remain Running.
- The feedback bundle preserves run-specific classify/RCA/cleanup/runtime hashes. The deterministic policy layer now marks only this project-local `network_loss` candidate as `weakness`; formal knowledge remains untouched.
- The offline selection replay moves the next action to `network_partition` and leaves the stop condition open. This is the intended uncertainty-reduction behavior, not a claim that all checkout failure modes are confirmed.

## Phase 30 NGINX Kubernetes Ingress deployment preparation findings（2026-08-25）

- `nginx/kubernetes-ingress` should be treated as an ingress-layer system under test, not as a replacement for the existing business microservice projects.
- The first deliverable is a reproducible isolated deployment plus a namespace-local HTTP fixture and two failure-free baseline windows. It must not produce weakness, defense, RCA, or knowledge claims.
- The deployment must use a unique IngressClass and must not change the cluster default or overwrite another ingress controller.
- The existing ChaosAtlas contracts are sufficient: read-only Kubernetes preflight, namespace-first server-side dry-run, explicit live approval, independent business oracle, evidence references, recovery, cleanup and residual scan.
- Future candidate families are planned only: controller PodKill/ContainerKill, controller-to-backend delay/loss, backend PodKill, reviewed config reload, and structured replica reduction. They remain non-executable until the method and profile are frozen.
- The detailed staged plan is `docs/superpowers/plans/2026-08-25-nginx-kubernetes-ingress-deployment.md`.

## Phase 23 OTel Demo weakness promotion findings（2026-08-24）

- 晋级前审计确认 r5/r7 的 run identity、seed、项目身份和因果身份一致但运行 fingerprint 不同；r6 未参与晋级。
- 两次运行都包含 baseline、injection、observation、recovery、cleanup 和 independent oracle attestation；分类为 `availability_degraded`，RCA transition 为 `confirmed`，cleanup 为 `verified`，没有 unsupported claim 或高严重度矛盾。
- `KB-WEAK-fd0bcc9a763e4bdf` 的机制级别为 `service_boundary`，声明范围是 checkout deployment 被 pod_kill 时可能出现可用性降级；没有升级为源码根因、超时机制或跨项目规律。
- promotion artifacts、卡片副本和 regression intents 已写入独立 promotion output，并复制到 OTel 专用 runtime knowledge root；既有 `KB-OTEL-CHECKOUT-*` 文件未改变。
- dry-run 回流只改变 retrieval 输入：无知识 `cards=0`，加载本轮 root `cards=1`；两次都保留 `synthetic`/`not_run` 边界，未把规划结果包装成漏洞或 RCA。
- 验证中一次 Windows `WinError 5` 临时文件替换失败在单测重跑中消失；随后以全新 basetemp 且禁用 cache provider 的全量套件通过，结果为 `1263 passed`。

## Phase 24 Sock Shop third-project runtime findings（2026-08-24）

- Sock Shop 运行前检查确认 `minikube/sock-shop-lab` 为 Active，14/14 Deployment Ready，front-end 单副本和 HTTP homepage Oracle 可用，Chaos residual 为 0。
- 真实 r1/r2 的完整生命周期均通过；两次不同 seed 产生不同 run identity，业务观察均出现受控短暂可用性降级并恢复，RCA 只到 deployment/service boundary。
- `KB-WEAK-452bd9a809fa41f2` 的 claim 为 front-end 单副本 `pod_kill` 可能导致短暂可用性降级；没有声称源码级根因、超时机制或防御机制。
- promotion history 只包含两个完整 runtime 子目录；gate-only preflight artifact 被排除，避免把审批阻断误作环境弱点或有效重复。
- 知识回流对照中无知识 `cards=0`，加载 Sock Shop 卡片 `cards=1`；两个 dry-run 都是 synthetic/not_run，没有执行 mutation、调用模型或写入其他项目知识。

# 2026-08-25 Online Boutique guarded cleanup investigation

- `guarded-r2/network_loss` executor artifact recorded `kubectl delete` output as deleted, but the immediate verification returned `verify_status=exists`; the NetworkChaos had not finished asynchronous deletion.
- `kubernetes_lifecycle_executor.py` correctly propagated `cleanup_confirmed=false`, invalid attestation, and `cleanup_report.status=blocked`; this is a fail-closed safety result, not a false weakness.
- The likely root cause is a single immediate post-delete read in `delete_resource`; legacy/shadow passing is timing-dependent and does not disprove the race.
- Required regression: first verification may report `exists`, a later verification reports genuine NotFound, and the final cleanup result must be confirmed without weakening RBAC/timeout/error classification.

# 2026-08-25 Legacy/Shadow/Guarded comparison result

- Sock Shop: legacy/shadow/guarded each ran 5/5, with 2 confirmed findings and 2 confirmed RCA transitions; cleanup was 5/5 verified in every mode.
- Online Boutique post-fix r4: guarded ran 5/5 with 3 confirmed findings, 3 confirmed RCA transitions, cleanup 5/5 verified, zero blocked/failed, and `budget_exhausted` after the fifth round.
- Online Boutique legacy and shadow each ran 5/5 with 2 confirmed findings, 2 confirmed RCA transitions, cleanup 5/5 verified. The guarded r3 partial batch had two honest preflight blocks (`workload deployments are not fully available`); these were excluded from weakness/RCA denominators and followed by a stable r4 batch.
- Candidate-quality proxy used for this gate is confirmed findings per valid executed round: Sock Shop 40%/40%/40%; Online Boutique 40%/40%/60% for legacy/shadow/guarded. This is an end-to-end outcome rate, not an isolated candidate-pool ranking experiment.
- RCA safety proxy is confirmed RCA per confirmed finding: 100% in all six post-fix mode/project cells. Stop efficiency is equal at the configured five-round budget: shadow/guarded both stopped with `budget_exhausted` after five executions; no early-stop advantage is claimed.
- Cleanup safety is 100% verified for all post-fix comparison runs. The earlier guarded-r2 Online Boutique network_loss cleanup block was a real asynchronous-delete race, now covered by the polling regression and not hidden or reclassified.
# 2026-08-25 项目全量画像与假设注册表阶段

- 当前 `chaosatlas run` 已有 inventory、server deployment detection、candidate space 和 advisory hypotheses，但 live batch 只为 Oracle 对应 Deployment 生成有限故障候选。
- NGINX Ingress 5 轮批次的候选池为 6、执行预算为 5；`fixture-backend` 因 Oracle 目标过滤没有进入候选池，说明“候选生成”和“实验执行”需要分离。
- 新阶段先增加两个 advisory artifact：项目画像描述实体/依赖/观测/覆盖，假设注册表描述架构、配置、依赖、运行时和防御假设；注册表内容不得含 runtime verdict 或 knowledge promotion 状态。
- 当前 policy 仍消费现有 runtime candidate pool；注册表质量验证通过后，再接入 policy 选择，避免未验证的静态假设直接进入 live mutation。

- 已实现 `tools/hypothesis_registry.py`：画像包含项目身份、namespace、Deployment/Service、依赖、业务 Oracle、candidate coverage 和 knowledge-card ids；注册表稳定排序并按五类输出 `architecture/configuration/dependency/runtime/defense`。
- 所有注册表条目均为 `claim_scope=advisory`；只有已有 runtime candidates 为 `execution_eligible=true`。PDB、readiness、资源限制等未知信息只生成 `needs_verification` 假设，不生成 weakness、RCA 或知识晋级结论。
- `tools/chaosatlas.py` 在 mapping/retrieval 后写出 advisory envelopes：`project_portrait.json`、`hypothesis_registry.json`；它们不属于 STAGES，不调用 executor，不改变 live gate、policy budget 或正式知识写入路径。
- fresh Sock Shop dry-run 结果：23 条假设，runtime 12 条，architecture 2 条，configuration 6 条，dependency 1 条，defense 2 条；执行预算 1，最终仍为 synthetic/not_run。
- 当前鸿沟：注册表仍是观察与审计输入，policy 还只消费 runtime candidate pool；下一步应先做 registry 覆盖/质量离线评估，再以 shadow 方式接入 policy，不能直接把静态假设转成注入动作。

## Registry Shadow 质量评估结果（2026-08-25）

- 新增 `tools/registry_shadow.py`，对五类假设、必需字段、重复 ID、advisory 边界、runtime candidate 对应关系和执行预算做确定性检查。
- 新增 `--registry-shadow`，生成 `registry_quality_report.json` 与 `registry_policy_shadow.json`；两个文件都是 advisory 非 stage artifact。
- Sock Shop：23 条假设，12 条 runtime eligible，质量 `passed`；Online Boutique：21 条假设，12 条 runtime eligible，质量 `passed`。
- 两个项目的 legacy 与 registry shadow 首选候选当前一致；这表示 shadow 没有造成选择漂移，不表示 registry 已经提升发现率。
- 重复 Sock Shop dry-run 的 shadow input hash、候选排序、selection_changed 和全部副作用标志一致；mutation、policy state、formal knowledge 均为 false。
- 下一步边界：先保留 shadow 审计结果，不能把 registry-derived order 直接用于 live；需要更多项目和真实回放证据后再设计 guarded policy 接入。

## Registry Policy Signal 接入结果（2026-08-26）

- 新增 `tools/registry_policy_signal.py`：仅接受质量 `passed` 的 advisory registry runtime 条目，生成归一化 priority bonus，固定上限为 `0.25`。
- `score_experiment` 仅在显式 context 存在时增加 `registry_priority_bonus`；不改变 posterior、stop policy、candidate pool 或 legacy 行为。
- `run_live_batch` 在 shadow/guarded/default 模式生成 `registry-policy-input.json`，并记录 `registry-policy-decisions.jsonl`；legacy 不读取 signal。
- fixture 级检查显示 Sock Shop 与 Online Boutique 均可生成 ready signal，各 6 个 Oracle-scoped candidate，无 fallback。
- 回归结果：相关 policy/batch/orchestrator 测试 `82 passed`；shadow 保持 legacy 实际执行，guarded 只执行 registry-selected allow-listed candidate。
- 当前边界：invalid signal 会被记录为 fallback 并不提供 bonus；现有 policy 安全门仍然有效，真实 guarded canary 尚未执行。

## NGINX Registry Guarded Canary（2026-08-26）

- 运行前只读检查通过：`chaosatlas-improvement/chaosatlas-nginx-ingress` Active，`nginx-ingress` 与 `fixture-backend` 均 `1/1`，所有 Chaos 资源为空。
- 单候选 guarded 批次安全完成：`completed=1`、`blocked=0`、`failed=0`、`cleanup_failed=0`；子运行分类为 `response_observed`，RCA `bounded`，cleanup `verified`，未形成 confirmed finding。
- registry signal 状态为 `fallback`，原因 `quality_not_passed`；决策 ledger 记录了该回退，实际选择来自现有 policy，不能作为 registry 优先级生效的验证。
- 根因定位：真实 `KubernetesProjectAdapter.inventory()` 只采集 Deployment/Service/Pod，没有依赖边；NGINX live registry 因此 `dependency=0`，五类质量门失败。该缺口不是 live 故障，也不应被判定为项目漏洞。
- 当前结论：可以继续做 NGINX 生命周期测试，但在补齐依赖画像或明确“未知类别”质量策略前，不能声称新 registry signal 已在真实 guarded 测试中生效。

## NGINX Registry Dependency Portrait 修复与 Guarded 重测（2026-08-26）

- `KubernetesProjectAdapter.inventory()` 现在只读采集并归一化 Ingress 路由，且从 Service selector 推导 Service→Deployment 边；Ingress 查询失败作为 warning，不会覆盖 Deployment/Service/Pod 的基础环境状态。
- live inventory 同时携带 profile 业务 Oracle，保持 live 与 offline portrait 字段契约一致；新增依赖边、Ingress 和 Oracle 字段的 adapter 回归通过。
- NGINX 单候选 guarded 重测 `artifacts/policy-rollout/nginx-ingress-registry-guarded-20260826-r2`：registry quality `passed`、signal `ready`，dependency=3，假设总数 23（architecture=2、configuration=4、dependency=3、runtime=12、defense=2）。
- guarded 第一轮选择 `container_kill`，legacy 首选为 `pod_kill`，`decision_changed=true`；该结果证明 registry priority signal 已在真实编排器中生效，但不代表 `container_kill` 已形成可晋级的跨重复知识。
- 生命周期结果为 1/1 completed、confirmed finding=1、RCA `confirmed`、cleanup `verified`；没有正式知识库写入。运行后 namespace 内 Chaos 资源为空，两个 Deployment 均 1/1 Ready。
- 当前边界：NGINX 仍只验证了一个候选和一个重复，不能据此宣布该机制跨项目稳定；下一步应按既定预算完成 NGINX 的候选覆盖/复现，或转入第二项目验证。

## NGINX Guarded Budget-10 批次结果（2026-08-26）

- 批次输出：`artifacts/policy-rollout/nginx-ingress-registry-guarded-20260826-r3-budget10`；registry signal 全程 `ready`，没有 fallback。
- 当前候选空间只有 6 个 runtime candidate，逐轮选择顺序为 `container_kill`、`network_loss`、`network_partition`、`pod_kill`、`stress_cpu`、`stress_memory`；每轮均完成 cleanup verification。
- 实际执行 6/10，完成 6，blocked=0，failed=0，cleanup_failed=0。第 7 轮因候选空间耗尽停止，`policy_stop_reason=blocked`，不是预算耗尽，也没有为凑足预算重复注入。
- `container_kill`、`network_loss`、`network_partition`、`pod_kill` 得到 `availability_degraded` 且 RCA `confirmed`；`stress_cpu` 与 `stress_memory` 为 `response_observed`/`unsupported`，原因是证据不完整，未计入确认弱点。
- 批次汇总 confirmed finding=4、RCA confirmed=4、正式知识库更新=0；所有结果仍为 project-local provisional，不能据此直接晋级稳定知识或跨项目结论。
- 下一步应先扩展并冻结 NGINX 的候选契约（如 backend_pod_kill、network_delay、config_reload、replica_reduction），同时补齐压力类证据契约，再重新使用预算 10；不应通过重复已有候选来填充预算。

## NGINX PodKill 独立重复与 Issue 草案（2026-08-26）

- 使用新 seed `2001` 和 run identity `live-2e85236769cb` 独立重复 `pod_kill`；与预算 10 批次中的 `live-20dd996b1b0d` 具有相同项目、namespace、Deployment、故障类型和 `service_boundary` 因果身份。
- 两次均为完整有效运行：baseline、injection、observation、recovery、cleanup 和 independent Oracle 全部通过；首个观测请求不可达，Pod 替换后恢复 HTTP 200，cleanup verified。
- 该重复支持“单副本 nginx-ingress 在 Pod 替换窗口产生短暂入口可用性下降”的项目级 Issue，但仍不声称源码级根因或跨项目规律。
- Issue 草案已写入 `reporting/nginx-kubernetes-ingress/issues/2026-08-26_single-replica-ingress-availability.md`，未进行外部提交，需用户审核。

## 三项验收收口结果（2026-08-26）

- Online Boutique 使用 `minikube/chaosatlas-online-boutique` 完成 registry-ready guarded canary 和新 seed 独立重复；两次 signal 均为 `ready`、cleanup verified，第一轮 `response_observed`，重复轮出现一次短暂 `availability_degraded`，RCA 为 bounded/confirmed 边界，未晋级正式知识。
- 新增 `tools/nginx_candidate_contracts.py` 与测试，冻结 NGINX 10 类候选的目标、参数、前置条件、恢复和证据契约；6 类现有动作可执行，`network_delay`、`backend_pod_kill`、`config_reload`、`replica_reduction` 明确保持 `pending_method_freeze`，不会误入 live。
- 全量回归通过：`1310 passed, 5 subtests passed`。直接修复系统 pytest 临时目录 ACL 的申请因审批服务 503 被拒，因此使用项目内 `--basetemp` 完成等价测试；系统 ACL 遗留不影响测试结论。
- 三项验收结论：方法可在已有 profile/Oracle/隔离 namespace 项目上受控使用；尚不等于任意项目、所有候选和生产默认开启均已验收。正式知识晋级仍需 promotion gate，新增 4 类候选仍需各自 executor 实现和 live 证据。

## 仓库结构整理发现（2026-08-26）

- 当前仓库是产品代码、实验输入、运行证据、外部源码和本机状态的混合体；问题主要是生命周期边界不清，不是单纯目录数量过多。
- path-only inventory 将 321,434 个文件稳定分为：主线源代码/测试 1,169、主线元数据 5、审阅文档 105、实验输入 1,935、生成证据 22,063、外部源码 38,194、本机生成 257,765、本机状态 198；未分类为 0。
- `tools/bin`、`sources_restored*`、`.venv`、`.tmp*` 等目录已明确标注为外部或本机类别，避免把工具分发物和运行环境误当作产品源码。
- 本阶段只建立地图、政策和检查工具，不移动或删除历史 artifacts/raw YAML；后续路径迁移必须单独批准并通过引用与全量测试验证。

- GitHub 发布验证完成：整理提交已出现在 `remediation/2026-08-09-review`，远端分支指针与本地提交一致；默认分支尚未自动变更。
