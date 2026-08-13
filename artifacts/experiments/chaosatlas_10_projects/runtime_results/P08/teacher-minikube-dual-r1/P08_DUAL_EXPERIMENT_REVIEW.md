# P08 Dual Experiment Review

- Project: `P08`
- Context: `minikube`
- Namespace: `chaosatlas-p08`
- Run: `teacher-minikube-dual-r1`
- Review status: `pending_human_review`
- Knowledge base updated: `false`

## Runtime Setup

- Image: `index.docker.io/appsmith/appsmith-ce@sha256:2d657315862dac42b43b6416aa30f70e3f777cb7a46e494ac276028c020ea467`
- Image architecture: `linux/amd64`
- Deployment: one replica, `500m/3000Mi` requests and `2 CPU/4Gi` limits.
- Oracle: `GET /api/v1/health`, expected HTTP 200 with stable response body hash.
- Candidate: `P08-appsmith-server-pod_kill-01`.
- Server-side dry-run: passed for the namespace-local Deployment, Service, and both PodChaos documents.

## Arm Results

| Arm | Baseline | Injected | Recovered | Cleanup | Residual Chaos |
|---|---:|---:|---:|---:|---:|
| `ChaosAtlas-KB` | 5/5 HTTP 200 | yes | 5/5 HTTP 200 | confirmed absent | none |
| `ChaosAtlas-noKB` | 5/5 HTTP 200 | yes | 5/5 HTTP 200 | confirmed absent | none |

Both arms used the same frozen candidate and the same runtime contract. The Appsmith Pod was replaced after PodKill in each arm, readiness returned to one ready/available replica, and the response body hash remained stable across baseline and post-recovery samples.

## Interpretation

This run confirms a bounded runtime observation: a single-replica Appsmith deployment recovered its `/api/v1/health` endpoint after one PodKill in both arms. It does not establish business-workflow resilience, comparative KB/noKB superiority, or a specific root cause. No Eureka, cache, registration, or other mechanism is implicated by this evidence.

The two arms produced the same observed result. The sample is one run per arm and is descriptive only; no statistical superiority claim is made.

## Cleanup

- Both PodChaos resources were deleted and individually confirmed absent.
- P08 had no remaining `PodChaos`, `NetworkChaos`, or `StressChaos` resources.
- The experiment Deployment and Service were deleted and individually confirmed absent.
- The `chaosatlas-p08` namespace remains active but empty for future authorized work.

## Decision

- `human_review`: `pending`
- `auto_apply`: `false`
- `knowledge_base_updated`: `false`
- No unrelated namespace was operated.
