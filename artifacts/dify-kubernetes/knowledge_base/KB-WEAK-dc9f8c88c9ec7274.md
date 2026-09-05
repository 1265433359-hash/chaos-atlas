# KB-WEAK-dc9f8c88c9ec7274

- Project: `dify-kubernetes`
- Target: `dify-k8s-api`
- Fault: `network_bandwidth`
- Parameter level: `baseline`
- RCA status: `confirmed`
- Valid reproductions: `3`

## Mechanism

network_bandwidth may affect dify-k8s-api availability or business behavior

## Evidence

- `live-3280e2065844`: `C:\APP\project\chaos-atlas\.runs\dify-k8s-llm-policy-guarded-20260902-r2\trials\0005-server-deployment-67dcdb5758b38b11a5076a0d-network_bandwidth-high-r01\attempt-01`
- `live-bca22191ee72`: `C:\APP\project\chaos-atlas\.runs\dify-k8s-llm-policy-guarded-20260902-r2\trials\0006-server-deployment-67dcdb5758b38b11a5076a0d-network_bandwidth-high-r02\attempt-01`
- `live-8c6f90693e6b`: `C:\APP\project\chaos-atlas\.runs\dify-k8s-llm-policy-guarded-20260902-r2\trials\0007-server-deployment-67dcdb5758b38b11a5076a0d-network_bandwidth-high-r03\attempt-01`

## Boundaries

- cross_project_transfer_requires_existing_feedback_protocol
- must_not_be_promoted_to_timeout_mechanism_without_source_evidence
