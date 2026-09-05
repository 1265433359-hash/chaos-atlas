# KB-WEAK-ebbeca487a2f410f

- Project: `dify-kubernetes`
- Target: `dify-k8s-proxy`
- Fault: `container_kill`
- Parameter level: `baseline`
- RCA status: `confirmed`
- Valid reproductions: `3`

## Mechanism

container_kill may affect dify-k8s-proxy availability or business behavior

## Evidence

- `live-00f5a595472b`: `C:\APP\project\chaos-atlas\.runs\dify-k8s-llm-policy-guarded-20260902-r2\trials\0195-server-deployment-ccd24654800ba2ff158f1d0a-container_kill-r01\attempt-01`
- `live-c3096f465a7b`: `C:\APP\project\chaos-atlas\.runs\dify-k8s-final-20260903\trials\0001-server-deployment-ccd24654800ba2ff158f1d0a-container_kill-r02\attempt-01`
- `live-8296ff829163`: `C:\APP\project\chaos-atlas\.runs\dify-k8s-final-20260903\trials\0002-server-deployment-ccd24654800ba2ff158f1d0a-container_kill-r03\attempt-01`

## Boundaries

- cross_project_transfer_requires_existing_feedback_protocol
- must_not_be_promoted_to_timeout_mechanism_without_source_evidence
