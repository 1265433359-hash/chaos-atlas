# KB-WEAK-3aab84e96bba503a

- Project: `dify-kubernetes`
- Target: `dify-k8s-plugin-daemon`
- Fault: `network_loss`
- Parameter level: `baseline`
- RCA status: `confirmed`
- Valid reproductions: `3`

## Mechanism

network_loss may affect dify-k8s-plugin-daemon availability or business behavior

## Evidence

- `live-441cf2b24c9b`: `C:\APP\project\chaos-atlas\.runs\dify-k8s-llm-policy-guarded-20260902-r2\trials\0103-server-deployment-7e068c4a2f5079ba8c5ee4f5-network_loss-r01\attempt-01`
- `live-146de7bf8656`: `C:\APP\project\chaos-atlas\.runs\dify-k8s-llm-policy-guarded-20260902-r2\trials\0104-server-deployment-7e068c4a2f5079ba8c5ee4f5-network_loss-r02\attempt-01`
- `live-f9958e06cce5`: `C:\APP\project\chaos-atlas\.runs\dify-k8s-llm-policy-guarded-20260902-r2\trials\0105-server-deployment-7e068c4a2f5079ba8c5ee4f5-network_loss-r03\attempt-01`

## Boundaries

- cross_project_transfer_requires_existing_feedback_protocol
- must_not_be_promoted_to_timeout_mechanism_without_source_evidence
