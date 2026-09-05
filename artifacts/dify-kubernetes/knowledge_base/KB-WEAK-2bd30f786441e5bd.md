# KB-WEAK-2bd30f786441e5bd

- Project: `dify-kubernetes`
- Target: `dify-k8s-api`
- Fault: `network_bandwidth`
- Parameter level: `baseline`
- RCA status: `confirmed`
- Valid reproductions: `3`

## Mechanism

network_bandwidth may affect dify-k8s-api availability or business behavior

## Evidence

- `live-97c147178dde`: `C:\APP\project\chaos-atlas\.runs\dify-k8s-repeated-coverage-60hypotheses-verified-20260901\trials\025-network_bandwidth-dify-k8s-api-r01\attempt-02`
- `live-01cce4c4e9a1`: `C:\APP\project\chaos-atlas\.runs\dify-k8s-repeated-coverage-60hypotheses-verified-20260901\trials\025-network_bandwidth-dify-k8s-api-r02\attempt-02`
- `live-8a2f443c9c3b`: `C:\APP\project\chaos-atlas\.runs\dify-k8s-repeated-coverage-60hypotheses-verified-20260901\trials\025-network_bandwidth-dify-k8s-api-r03\attempt-02`

## Boundaries

- cross_project_transfer_requires_existing_feedback_protocol
- must_not_be_promoted_to_timeout_mechanism_without_source_evidence
