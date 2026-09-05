# KB-WEAK-bed11071366a9eaf

- Project: `dify-kubernetes`
- Target: `dify-k8s-plugin-daemon`
- Fault: `config_drift`
- Parameter level: `baseline`
- RCA status: `confirmed`
- Valid reproductions: `3`

## Mechanism

config_drift may affect dify-k8s-plugin-daemon availability or business behavior

## Evidence

- `live-aee0aa4807b2`: `C:\APP\project\chaos-atlas\.runs\dify-k8s-llm-policy-guarded-20260902-r2\trials\0037-server-deployment-7e068c4a2f5079ba8c5ee4f5-config_drift-r01\attempt-01`
- `live-bbd0bfdfe236`: `C:\APP\project\chaos-atlas\.runs\dify-k8s-llm-policy-guarded-20260902-r2\trials\0038-server-deployment-7e068c4a2f5079ba8c5ee4f5-config_drift-r02\attempt-02`
- `live-a521681e73f6`: `C:\APP\project\chaos-atlas\.runs\dify-k8s-llm-policy-guarded-20260902-r2\trials\0039-server-deployment-7e068c4a2f5079ba8c5ee4f5-config_drift-r03\attempt-02`

## Boundaries

- cross_project_transfer_requires_existing_feedback_protocol
- must_not_be_promoted_to_timeout_mechanism_without_source_evidence
