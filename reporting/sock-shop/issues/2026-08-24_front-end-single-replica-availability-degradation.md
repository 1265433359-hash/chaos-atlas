# Issue Draft - Sock Shop - front-end single replica causes transient unavailability during Pod replacement

> Status: DRAFT - for review before submission. Not yet posted to GitHub.
> Target: Sock Shop repository/maintainer issue tracker.
> Submission channel: normal issue; this is a resilience/design concern, not a security report.
> Confidence: HIGH - two independent isolated live runs with valid runtime attestation, confirmed RCA, recovery, and cleanup.

## Title

Sock Shop: single-replica front-end becomes temporarily unavailable during Pod replacement

## Summary

The `front-end` Deployment runs with a single replica. When that Pod is killed,
the Service has no Ready endpoint during the replacement window and the
homepage HTTP oracle becomes unavailable for several probes. The workload
recovers after the replacement Pod becomes Ready, but users can observe a
short interruption during an otherwise routine Pod restart or node disruption.

This behavior was reproduced twice with independent seeds in the isolated
`sock-shop-lab` namespace. The runtime RCA is confirmed at the service boundary;
the report does not claim a source-level bug in the application code.

## Environment

- Repository: Sock Shop deployment used by the isolated ChaosAtlas lab
- Branch / commit pinned: `6e83eb6ffdf1bce43e332337a3bb0fc40327d039` (runtime RCA snapshot)
- Deployment (isolated lab): Kubernetes context `minikube`, namespace `sock-shop-lab`
- Workload: `front-end` Deployment, Service `front-end`, HTTP `/`, expected status 200
- Chaos Mesh version: not captured in this run; the PodChaos CRD was available

## Evidence

### 1. Static evidence

`artifacts/sock-shop/sock-shop-lab-manifest.yaml:254-259` defines the
`front-end` Deployment with `replicas: 1`. The Service selector at lines
312-313 routes traffic to that single workload.

### 2. Runtime evidence

Both runs had valid attestation fields for baseline, injection, observation,
recovery, cleanup, and an independent business oracle.

| Run | Baseline | Injected observation | Recovery | Cleanup |
|---|---|---|---|---|
| `live-7313fcfe4076` (seed 1001) | 3/3 HTTP 200 | first probe found no running Pod; next probes were connection refused; later probes returned 200 | replacement Pod Ready; original/new Pod UIDs differed | PodChaos deleted and verified absent |
| `live-85981dc4d4a5` (seed 1002) | 3/3 HTTP 200 | same pattern: no running Pod, connection refused, then 200 | replacement Pod Ready; original/new Pod UIDs differed | PodChaos deleted and verified absent |

The corresponding artifacts are:

- `.tmp-project-onboard-sockshop-live-r1/finding_report.json`
- `.tmp-project-onboard-sockshop-live-r1/rca_report.json`
- `.tmp-project-onboard-sockshop-live-r1/runtime/business/live-7313fcfe4076.json`
- `.tmp-project-onboard-sockshop-live-r3/finding_report.json`
- `.tmp-project-onboard-sockshop-live-r3/rca_report.json`
- `.tmp-project-onboard-sockshop-live-r3/runtime/business/live-85981dc4d4a5.json`

## Reproduction

```powershell
# From the pinned Sock Shop deployment and isolated namespace
$env:PYTHONPATH='.'
python tools/chaosatlas.py run `
  --profile artifacts/project_profiles/sock-shop/project_profile.json `
  --mode live `
  --output <output-dir> `
  --kube-context minikube `
  --candidate-id server:deployment:827339c6afd397a13efb276a:pod_kill `
  --seed 1002 `
  --approve-live
```

Before injection, establish that `GET /` returns HTTP 200. During the
replacement window, probe the same endpoint until the replacement Pod is
Ready. After recovery, verify HTTP 200 and confirm that the PodChaos resource
has been deleted.

## Impact

- User-facing homepage requests can fail or be refused during the replacement
  window.
- The impact is limited to the availability window observed for the single
  front-end replica; no data-integrity impact was observed.
- The system recovers automatically after Kubernetes creates a Ready
  replacement Pod.

## Suggested fix

If continuous availability during routine Pod disruption is an intended
property of the deployment, consider running at least two `front-end` replicas
with an appropriate rolling-update/PDB policy and verify that the Service keeps
one Ready endpoint during replacement. If single-replica operation is
intentional for a demo or resource-constrained lab, document the expected
availability interruption explicitly.

## Notes

- This is a resilience/design issue, not a security vulnerability.
- The finding is confirmed only at the Kubernetes service boundary; it does not
  infer a source-level root cause.
- The knowledge card remains `provisional` pending the project's chosen
  remediation/defense contract; no automatic deployment change was applied.
- The two live runs left zero Chaos resources in `sock-shop-lab`.
