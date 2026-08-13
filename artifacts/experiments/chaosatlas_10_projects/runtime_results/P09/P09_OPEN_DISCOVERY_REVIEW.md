# P09 Open Discovery Review

- Project: `P09`
- Namespace boundary: `chaosatlas-p09`
- Review status: `pending_human_review`
- Discovery consent: 12 DeepSeek calls, four arms, seeds `1001`, `1002`, `1003`
- Kubernetes mutation applied by this phase: `false`
- Knowledge base update: `false`

## Evidence

- `teacher-minikube-open-r1`: 12/12 transport successes, 0 valid, 12 method-invalid. The runner reconstructed a shortened prompt and omitted the frozen output schema and arm-specific view. The responses therefore lacked the required contract fields. This run is retained as failed evidence and is not reinterpreted as a result.
- `teacher-minikube-open-r2`: 12/12 transport successes, 11 valid, 1 method-invalid. The corrected runner reads each frozen prompt verbatim, including the complete output schema.
- The sole r2 invalid response is `ChaosAtlas-noKB-open`, seed `1003`; the backend finished with `finish_reason=length` and the JSON response was truncated. No automatic 13th call was issued.
- Across r2, the compiler accepted `88` hypotheses with `34` unique canonical signatures. All accepted hypotheses have `execution_ready=false`; none has runtime evidence.
- The 24 `raw.redacted.txt` files match their recorded `raw_sha256` values byte-for-byte. The API key is not present in the evidence.

## Interpretation

The P09 API weakness is supported only by the previously executed bounded pilot: API `/health` returned HTTP 200 in baseline checks, the API PodKill was recovered and cleaned up, and the observed claim is limited to API health-endpoint availability. The open-discovery candidates do not extend that claim to the business workflow.

The open-discovery output is hypothesis material, not a root-cause finding. Repeated candidate families include API `pod_kill`, API `network_delay`, agent-backend `network_loss`/`pod_kill`, and Redis `pod_kill`. These counts describe model output frequency only. They do not establish a weakness, a causal path, or a service mechanism.

No evidence in this phase supports a specific explanation involving Eureka, caching, registration, readiness, or any other mechanism. Such explanations remain unconfirmed and must not be written to the knowledge base without a human-reviewed runtime experiment and supporting logs/traces.

## Decision

- `human_review`: `pending`
- `auto_apply`: `false`
- `execution_ready`: `false` for every accepted hypothesis
- No mutation YAML was applied.
- No knowledge card was created or updated.
- The separate six-call KB/noKB selection preflight remains unexecuted because the explicit authorization covered 12 open-discovery calls and those calls are complete.

## Audit References

- Summary: `artifacts/experiments/chaosatlas_10_projects/open_discovery_results/P09/teacher-minikube-open-r2/summary.json`
- Failed first run: `artifacts/experiments/chaosatlas_10_projects/open_discovery_results/P09/teacher-minikube-open-r1/`
- Corrected run: `artifacts/experiments/chaosatlas_10_projects/open_discovery_results/P09/teacher-minikube-open-r2/`
- Token ledger: `artifacts/experiments/chaosatlas_10_projects/cost_token_ledger.json`
- Prior bounded pilot: `artifacts/experiments/chaosatlas_10_projects/runtime_results/P09/teacher-minikube-pilot-r2/P09_PILOT_REVIEW.md`
