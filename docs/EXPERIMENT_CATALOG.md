# Experiment Catalog

This is the paper-facing index of comparison experiments. It intentionally
summarizes evidence without duplicating every run file. Follow the artifact
links for exact values, hashes, and raw logs.

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
| Sock Shop | HTTP delay/loss on eight core edges | Orders and front-end business paths | Paper-facing edge-level result: 6/8 weakness, 2/8 defended; the machine ledger separately reports delay/loss variants and inferred loss defenses | `artifacts/sock-shop/sock_shop_cross_project_validation.md`, `artifacts/sock-shop/sock_orders_future_get_verified.md`, `artifacts/sock-shop/sock_shop_verdicts.json` |
| Sock Shop vs ChaosEater | Deployment availability and recovery | Service replicas, probes, and kill/recovery paths | ChaosEater exposes availability-layer risks; our evidence chain adds call-contract, business-oracle, source-anchor, and structured root-cause evidence | `artifacts/experiments/chaos_eater_deployed_vs_ours.md`, `artifacts/experiments/chaos_eater_vs_evidence_chain.md` |

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

## Sock Shop Comparison Contribution

Sock Shop is a transfer and method-comparison study with four bounded claims:

1. **Knowledge transfer:** the rule that synchronous downstream calls without
   an effective timeout are high-risk remained useful in a new project.
2. **Rule-boundary discovery:** the simple `loss > delay` prior failed on the
   payment-delay edge because the real orders path has a 5-second asynchronous
   timeout. The knowledge base must retain counterexamples and applicability
   conditions, not only positive rules.
3. **Layer unification:** the same workflow represented call-contract weakness,
   defended edges, replica/probe/PDB availability weakness, and recovery in one
   evidence chain.
4. **Auditable output:** compared with ChaosEater's free-form analysis, the
   method records structured weakness/defense status, source anchors, runtime
   evidence, and reusable knowledge entries. The evidence supports a
   difference in coverage and output form, not a universal superiority claim.

## LLM and Knowledge Ablation

The supplementary ablation compares `LLM-blind`, `LLM-generic`, and
`LLM-full-pre` under the same candidate pool, model, prompt, seed, runner, and
oracle rules. The frozen protocol is
[`artifacts/experiments/llm_knowledge_ablation_protocol_v1.md`](../artifacts/experiments/llm_knowledge_ablation_protocol_v1.md).

This ablation isolates knowledge contribution to the LLM decision component. It
does not establish superiority over another method, and its metrics must not be
collapsed into the case-study results.

Current status: **parked for later continuation**. The protocol and partial
selection artifacts are preserved, but the formal runtime execution, remaining
review gates, independent oracle, and clustered statistical analysis are not
complete. Do not cite its intermediate metrics as a finished ablation result.

The final method head-to-head comparison is also **parked**. Existing
ChaosEater, M0/M1, and comparison-ledger outputs support descriptive coverage
and output-form observations only. A future continuation must freeze one common
candidate pool and oracle before producing any superiority claim.

## Reproduction Status

| Track | Status | Interpretation |
|---|---|---|
| Train Ticket first loop | complete with explicit limits | Strongest current paper example |
| Online Boutique comparison | runtime and statistical evidence archived | Cross-project semantics, not a universal law |
| OpenTelemetry Demo comparison | runtime evidence archived | Observability and implementation contrast |
| Held-out knowledge ablation | parked; protocol/bring-up/selection artifacts preserved | Runtime execution, remaining gates, independent oracle, and clustered statistics are incomplete |
| Final method head-to-head comparison | parked; descriptive artifacts preserved | Not a completed superiority evaluation; common pool/oracle/statistical closure remains |
| HTTPChaos on current WSL2 kernel | blocked | Requires non-WSL2 or a compatible kernel/controller prerequisite |
