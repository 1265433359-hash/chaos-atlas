# Single plugin-daemon replica causes full Chatflow outage during pod replacement

**Affected project:** Dify Kubernetes deployment configuration

**Suggested labels:** `enhancement`, `plugin-daemon`, `high-availability`, `helm`, `kubernetes`

## Summary

The tested Dify Kubernetes deployment runs the plugin daemon with one replica. Removing that only pod leaves the Chatflow path without a serving plugin daemon while Kubernetes replaces it. During the replacement window, Chatflow requests are unavailable for approximately the observation window.

This report concerns the deployment availability default and production guidance. It is not claiming that the Dify application should serve successful Chatflow requests when its only plugin daemon is intentionally unavailable.

## Environment

- Dify version: `1.17.0`
- API image: `langgenius/dify-api:1.17.0`
- Helm chart: `dify-0.38.0`
- Installation type: Self Hosted
- Kubernetes context: `chaosatlas-dify`
- Namespace: `dify-k8s-lab`
- Plugin daemon replicas: `1`
- Business endpoint: `/v1/chat-messages`

## Steps to Reproduce

1. Deploy Dify with one plugin-daemon replica.
2. Verify that the baseline Chatflow request succeeds.
3. Remove the only plugin-daemon pod or perform an equivalent pod replacement.
4. Send Chatflow requests continuously during replacement.
5. Restore the deployment and verify readiness, business recovery, and cleanup.

## Actual Behavior

The `pod_kill` experiment was repeated three times. Each valid trial observed the Chatflow path becoming unavailable while the only plugin-daemon pod was being replaced. The deployment recovered after a new Ready pod was available, and all three trials passed recovery and cleanup verification.

## Expected Behavior

Production-oriented Kubernetes guidance should make the single-replica availability trade-off explicit and provide a multi-replica configuration. With at least two plugin-daemon replicas, replacing one pod should leave another Ready instance available to serve requests, subject to the documented availability SLO.

This report focuses on deployment availability and production guidance. It is
separate from runtime error classification issues such as `400 invalid_param`.

## Suggested Investigation

- Document whether one replica is intended only for development or single-node labs.
- Provide a production example with at least two plugin-daemon replicas.
- Add a suitable `PodDisruptionBudget` and rolling-update settings.
- Verify readiness, graceful shutdown, connection draining, and Service endpoint propagation.
- Repeat the experiment with two replicas and measure error rate and recovery time.

## Acceptance Criteria

- The Helm chart and documentation clearly state the availability implications of one replica.
- A production example configures at least two plugin-daemon replicas.
- Losing one replica does not create a sustained Chatflow outage in a two-replica test.
- Replica count, PDB, rollout policy, and the resulting availability SLO are documented.

## Reproduction Evidence

- Run: `dify-k8s-llm-policy-guarded-20260902-r2`
- Fault: plugin-daemon `pod_kill`
- Result: `3/3` valid trials observed Chatflow unavailability during replacement.
- Cleanup: `3/3` verified.

This is primarily a deployment hardening and documentation issue. A two-replica comparison is still required before assigning a Dify application bug severity.
