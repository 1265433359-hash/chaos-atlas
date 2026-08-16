# Experiment Catalog

This is the paper-facing index of comparison experiments. It intentionally
summarizes evidence without duplicating every run file. Follow the artifact
links for exact values, hashes, and raw logs.

Paper-mainline status is defined by
[`docs/CHAOSATLAS_PAPER_MAINLINE.md`](CHAOSATLAS_PAPER_MAINLINE.md). This
catalog preserves historical rows for audit, but same-pool and
preselected-candidate results are frozen and must not be used as the current
method comparison.

## Case-Study Matrix

| Project | Fault family | Main workload/oracle | Result class | Evidence location |
|---|---|---|---|---|
| Train Ticket | Station network delay (100 ms, 500 ms, 2 s, 3 s boundary) | Station success and Not Found oracles | Response contract preserved at lower delays; latency grows; client timeout can precede server completion | `artifacts/train-ticket/runtime/`, `artifacts/train-ticket/knowledge_base/KB-TT-NETWORK-STATION-DELAY-001.*` |
| Train Ticket | CPU stress at Basic, Order, and Station | Read-only HTTP/business envelopes | Cgroup throttling observed; response can remain correct while latency degrades | `artifacts/train-ticket/runtime/`, `artifacts/train-ticket/knowledge_base/KB-TT-STRESS-*.md` |
| Train Ticket | HTTP response replacement | HTTPChaos target candidates | Platform-blocked by WSL2 `ebtables`; not an application defense result | `artifacts/train-ticket/knowledge_base/KB-TT-HTTP-ORDER-RESPONSE-404-001.*` |
| Train Ticket | Order to Station network candidate | Refresh workflow | Static path exists, current business call is not reachable/verified | `artifacts/train-ticket/knowledge_base/KB-TT-NETWORK-ORDER-STATION-001.*` and `reporting/train-ticket/issues/` |
| Online Boutique | Payment delay/loss | Checkout PlaceOrder | Delay propagates; loss can hang to caller deadline | `artifacts/online-boutique/deep_experiments_report.md`, `stat_repetition_result.json` |
| Online Boutique | Shipping delay/loss | Checkout shipping path | Sequential downstream calls can double delay; loss is fatal to the caller | `artifacts/online-boutique/knowledge_base/KB-OB-CHECKOUT-SHIPPING-FAILURE-001.json` |
| Online Boutique | Email delay/loss | Checkout email path | Delay propagates; loss can degrade gracefully in this project path | `artifacts/online-boutique/knowledge_base/KB-OB-CHECKOUT-EMAIL-FAILURE-001.json` |
| Online Boutique | Product catalog failure | Frontend core path | Core path has no equivalent degradation in the observed run | `artifacts/online-boutique/knowledge_base/KB-OB-FRONTEND-PRODUCTCATALOG-FAILURE-001.json` |
| Online Boutique | Probe restart race | Payment service | Probe restart can remove the old injection; reinjection restores the effect | `artifacts/online-boutique/knowledge_base/KB-OB-PAYMENT-PROBE-RESTART-RACE-001.json`, `artifacts/online-boutique/reject_escape_result.json` |
| Online Boutique | Payment + email multi-fault | Checkout | Sequential downstream delays add approximately linearly | `artifacts/online-boutique/knowledge_base/KB-OB-CHECKOUT-MULTI-FAULT-001.json`, `artifacts/online-boutique/mixed_pool_results.json` |
| OpenTelemetry Demo | Payment delay/loss | Checkout PlaceOrder | Delay propagates through the path; loss reaches the caller deadline | `artifacts/opentelemetry-demo/experiment_results.md` |
| OpenTelemetry Demo | Email delay/loss | Checkout email path | Runtime behavior differs from Online Boutique and is retained as a comparison, not generalized | `artifacts/opentelemetry-demo/knowledge_base/KB-OTEL-CHECKOUT-EMAIL-FAILURE-001.json` |
| Sock Shop | HTTP delay/loss on eight core edges (frozen historical) | Orders and front-end business paths | Historical edge-level result: 6/8 weakness, 2/8 defended; not the current autonomous full-vs-ablation denominator | `artifacts/sock-shop/sock_shop_cross_project_validation.md`, `artifacts/sock-shop/sock_orders_future_get_verified.md`, `artifacts/sock-shop/sock_shop_verdicts.json` |
| Sock Shop improved-method ablation | Autonomous hypothesis generation and real injection | Sock Shop business oracle | Mainline stage: complete method and knowledge-free ablation; current headline is recorded in the paper-mainline summary and final ledgers | `artifacts/experiments/chaosatlas_sockshop_ablation_discovery_2026-08-15-r1/`, `artifacts/experiments/chaosatlas_sockshop_r5_runtime_2026-08-15-r1/` |
| Sock Shop older two-arm pilot (frozen) | `front-end` PodKill | Front-end HTTP 200 oracle | Historical descriptive pilot; no business weakness or specific root cause confirmed; official ChaosEater arm blocked | `artifacts/experiments/chaosatlas_sockshop_three_method/runtime_results/sock-shop/teacher-minikube-three-method-r1/` |
| Sock Shop historical ChaosEater comparison (frozen) | Deployment availability and recovery | Service replicas, probes, and kill/recovery paths | Frozen supplementary material only; not a current third-arm result | `artifacts/experiments/chaos_eater_deployed_vs_ours.md`, `artifacts/experiments/chaos_eater_vs_evidence_chain.md` |
| P09 current two-arm runtime | API/Redis PodKill, API delay/loss/CPU stress | P09 `/health` oracle | 10/10 lifecycle-complete reports; API PodKill caused transient health interruption; Redis PodKill produced worker connection symptoms; no business weakness, root cause, or method-superiority claim | `artifacts/experiments/chaosatlas_10_projects/runtime_results/P09/teacher-minikube-two-arm-r4/P09_TWO_ARM_REVIEW.json` |

## Comparison Dimensions

The current cross-project comparison is organized by dimensions rather than a
single aggregate score:

- **Applicability:** target exists, workload is reachable, and injection actually occurs.
- **Business contract:** status, payload, or domain envelope remains valid.
- **Latency:** p50/p95 change under the same timeout and concurrency budget.
- **Failure semantics:** delay, loss, kill, probe restart, or multi-fault behavior.
- **Defense semantics:** timeout, retry, fallback, circuit breaker, graceful degradation, or no defense observed.
- **Recovery:** controller recovery, application recovery, and cleanup are separately recorded.
- **Observability:** logs, metrics, traces, and whether an alert is automatic or manual.

Do not rank projects by raw latency across different languages, deployments, or
workloads. Use paired deltas within a project and report project-clustered
uncertainty for cross-project claims.

## Sock Shop Historical Comparison Contribution

Sock Shop historical evidence is a transfer study with bounded claims:

1. **Knowledge transfer:** the rule that synchronous downstream calls without
   an effective timeout are high-risk remained useful in a new project.
2. **Rule-boundary discovery:** the simple `loss > delay` prior failed on the
   payment-delay edge because the real orders path has a 5-second asynchronous
   timeout. The knowledge base must retain counterexamples and applicability
   conditions, not only positive rules.
3. **Layer unification:** the same workflow represented call-contract weakness,
   defended edges, replica/probe/PDB availability weakness, and recovery in one
   evidence chain.
4. **Auditable output:** compared with historical ChaosEater material, the method
   records structured weakness/defense status, source anchors, runtime evidence,
   and reusable knowledge entries. This supports a research hypothesis about
   coverage and output form, not a completed current head-to-head or superiority claim.

The older Sock Shop two-arm PodKill pilot is descriptive only. It used the same
mutation for both arms and the official ChaosEater execution was
`environment_blocked`; therefore it is not a completed three-method experiment.

## Frozen Same-Pool and Knowledge Selection Material

The archived selection track compares `LLM-blind`, `LLM-generic`, and
`LLM-full-pre` under the same candidate pool, model, prompt, seed, runner, and
oracle rules. The frozen protocol is
[`artifacts/experiments/llm_knowledge_ablation_protocol_v1.md`](../artifacts/experiments/llm_knowledge_ablation_protocol_v1.md).

This track is frozen historical material. It does not establish superiority over
another method, and its metrics must not be collapsed into the real-project
case-study or Sock Shop autonomous ablation results.

Current status: **frozen and excluded from the paper mainline**. The protocol,
selection artifacts, and partial analysis are preserved for audit. Do not cite
same-pool percentages as the current knowledge-base effectiveness result.

The official ChaosEater native replay is now a **stage reference** with a
different measurement layer and is included only with that boundary. A formal
same-layer comparison against the complete official ChaosEater method remains
**future work**. Existing adapter, M0/M1, and comparison-ledger outputs support
descriptive historical background only.

## Reproduction Status

| Track | Status | Interpretation |
|---|---|---|
| Train Ticket first loop | complete with explicit limits | Strongest current paper example |
| Online Boutique comparison | runtime and statistical evidence archived | Cross-project semantics, not a universal law |
| OpenTelemetry Demo comparison | runtime evidence archived | Observability and implementation contrast |
| Sock Shop autonomous full-vs-ablation | active paper mainline; review state in ledgers | Real-project hypothesis generation and runtime issue/weakness evidence; exact denominators remain ledger-defined |
| Same-pool/preselected selection | frozen historical | Preserved for audit, excluded from current mainline statistics |
| Official ChaosEater native replay | stage reference | Five native runs are archived; measurement layer and model differ from ChaosAtlas |
| Same-layer official ChaosEater comparison | future work | A machine-ledgered, same-oracle, same-layer comparison is not completed |
| HTTPChaos on current WSL2 kernel | blocked | Requires non-WSL2 or a compatible kernel/controller prerequisite |

## Separate Future Project Queue

The next execution queue is separate from the current paper mainline. It
contains Online Boutique, OpenTelemetry Demo, Train Ticket, and TeaStore;
Sock Shop's improved-method ablation is recorded in the mainline above, while
older pilots remain frozen.
Each active project runs only `ChaosAtlas-full` and `ChaosAtlas-ablation`;
ChaosEater remains deferred as a same-layer formal comparison. Online Boutique now has a fresh namespace-isolated
manifest with loadgenerator excluded and offline oracle-contract validation, but
still requires immutable image digests, an authorized namespace-first dry-run,
and fresh baseline/oracle validation. The other two reusable projects require
their own fresh manifests and gates. TeaStore has a static intake only and
still requires exact source restoration, profile rendering, bring-up, and stable
baseline gates.

The machine-readable queue is
`artifacts/experiments/chaosatlas_followup_four_projects_2026-08-13/queue_manifest.json`.
