# Findings

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
