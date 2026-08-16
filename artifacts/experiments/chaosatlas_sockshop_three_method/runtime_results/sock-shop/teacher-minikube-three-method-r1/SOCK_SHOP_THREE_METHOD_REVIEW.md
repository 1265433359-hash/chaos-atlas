# Sock Shop Three-Method Review

## Scope

This review covers the new `sock-shop` namespace run in Minikube on August 13,
2026. Historical Sock Shop directories and historical ChaosEater output were
not reused as current comparison results.

## Method Status

`ChaosAtlas-full` and `ChaosAtlas-ablation` both completed with the same
front-end `PodChaos` mutation and the same lifecycle contract. Both reports
have `status=completed`, passed baseline, confirmed injection, recovered the
front-end deployment, confirmed Chaos resource deletion, observed no global
Chaos residuals, and reached ten stable washout HTTP 200 responses.

`ChaosEater-full` is `environment_blocked`. The native Skaffold input exists,
and the official ChaosEater source at commit `47c4e44` imports successfully in
an isolated Python environment with local Ollama model `qwen2.5:7b`.
Execution is still blocked because this machine has no `skaffold` executable
and no `chaos-eater/k8sapi:1.0` image. The Minikube API also experienced TLS
timeouts during the third-arm preflight; the final read-only check found
`catalogue`, `payment`, and `user` Pods not Ready. A Skaffold download request
was blocked by the execution approval service. The adapter and historical CE
output are not substituted for the official arm.

## Evidence Interpretation

The selected mutation killed one of three front-end replicas. Both executable
arms continued returning HTTP 200 during the eight post-injection samples and
recovered with a replacement Pod. This run therefore does not confirm a
front-end business weakness under this three-replica PodKill scenario.

No specific root cause is supported by the diagnostic evidence. Front-end and
carts logs were empty, catalogue logs contained health calls, and the native
Sock Shop input did not deploy a tracing-server Service, so Zipkin capture was
unavailable. No claim about Eureka, cache behavior, registration, or another
mechanism is made.

This is not a complete three-method head-to-head result because the official
ChaosEater arm is blocked by the local execution environment. The current
evidence is therefore two completed ChaosAtlas arms plus one environment
block, not a three-method comparison. Human review remains `pending`, and the
knowledge base was not updated.
