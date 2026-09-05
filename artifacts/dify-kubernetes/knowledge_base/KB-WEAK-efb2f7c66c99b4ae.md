# KB-WEAK-efb2f7c66c99b4ae

- Project: `dify-kubernetes`
- Target: `dify-k8s-plugin-daemon`
- Fault: `container_kill`
- Parameter level: `baseline`
- RCA status: `confirmed`
- Valid reproductions: `3`

## Mechanism

container_kill may affect dify-k8s-plugin-daemon availability or business behavior

## Evidence

- `live-d5cf7b8952c3`: `C:\APP\project\chaos-atlas\.runs\dify-k8s-llm-policy-guarded-20260902-r2\trials\0018-server-deployment-7e068c4a2f5079ba8c5ee4f5-container_kill-r01\attempt-01`
- `live-2d229df397d0`: `C:\APP\project\chaos-atlas\.runs\dify-k8s-llm-policy-guarded-20260902-r2\trials\0019-server-deployment-7e068c4a2f5079ba8c5ee4f5-container_kill-r02\attempt-01`
- `live-f5f6fd723ac2`: `C:\APP\project\chaos-atlas\.runs\dify-k8s-llm-policy-guarded-20260902-r2\trials\0020-server-deployment-7e068c4a2f5079ba8c5ee4f5-container_kill-r03\attempt-01`

## Boundaries

- cross_project_transfer_requires_existing_feedback_protocol
- must_not_be_promoted_to_timeout_mechanism_without_source_evidence
