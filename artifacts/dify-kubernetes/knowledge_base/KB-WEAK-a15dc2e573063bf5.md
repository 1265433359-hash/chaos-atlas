# KB-WEAK-a15dc2e573063bf5

- Project: `dify-kubernetes`
- Target: `dify-k8s-api`
- Fault: `container_kill`
- Parameter level: `baseline`
- RCA status: `confirmed`
- Valid reproductions: `3`

## Mechanism

container_kill may affect dify-k8s-api availability or business behavior

## Evidence

- `live-a61793dfd3d6`: `C:\APP\project\chaos-atlas\.runs\dify-k8s-repeated-coverage-60hypotheses-verified-20260901\trials\019-container_kill-dify-k8s-api-r01\attempt-02`
- `live-6b416b273a14`: `C:\APP\project\chaos-atlas\.runs\dify-k8s-repeated-coverage-60hypotheses-verified-20260901\trials\019-container_kill-dify-k8s-api-r02\attempt-02`
- `live-4c85c3c77f2e`: `C:\APP\project\chaos-atlas\.runs\dify-k8s-repeated-coverage-60hypotheses-verified-20260901\trials\019-container_kill-dify-k8s-api-r03\attempt-02`

## Boundaries

- cross_project_transfer_requires_existing_feedback_protocol
- must_not_be_promoted_to_timeout_mechanism_without_source_evidence
