# KB-WEAK-0b46536c1dac425c

- Project: `dify-kubernetes`
- Target: `dify-k8s-api`
- Fault: `network_bandwidth`
- Parameter level: `baseline`
- RCA status: `confirmed`
- Valid reproductions: `3`

## Mechanism

network_bandwidth may affect dify-k8s-api availability or business behavior

## Evidence

- `live-2fb90c91d448`: `C:\APP\project\chaos-atlas\.runs\dify-k8s-llm-policy-guarded-20260902-r2\trials\0002-server-deployment-67dcdb5758b38b11a5076a0d-network_bandwidth-low-r01\attempt-01`
- `live-76abffdad78d`: `C:\APP\project\chaos-atlas\.runs\dify-k8s-llm-policy-guarded-20260902-r2\trials\0003-server-deployment-67dcdb5758b38b11a5076a0d-network_bandwidth-low-r02\attempt-01`
- `live-cffb453eea04`: `C:\APP\project\chaos-atlas\.runs\dify-k8s-llm-policy-guarded-20260902-r2\trials\0004-server-deployment-67dcdb5758b38b11a5076a0d-network_bandwidth-low-r03\attempt-01`

## Boundaries

- cross_project_transfer_requires_existing_feedback_protocol
- must_not_be_promoted_to_timeout_mechanism_without_source_evidence
