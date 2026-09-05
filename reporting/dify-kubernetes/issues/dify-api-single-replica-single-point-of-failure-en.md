# Dify Helm Deployment Defaults to a Single API Replica Without a Production Availability Warning

**Affected project:** Dify Helm/Kubernetes deployment configuration

**Suggested labels:** `kubernetes`, `availability`, `deployment`, `documentation`

## Summary

The tested Dify Kubernetes deployment runs the `dify-k8s-api` Deployment with one replica. When that sole replica is removed or the Deployment is scaled to zero, Dify Chatflow requests return HTTP `502` because the Service has no API instance available to serve the request.

The `502` response is expected when there are no backend endpoints. The concern is that a production-oriented deployment configuration can run with a single API replica without an explicit high-availability warning or a production example using multiple replicas. This should be treated as a deployment hardening issue rather than an application-logic bug.

## Environment

- Dify version: `1.17.0`
- API image: `langgenius/dify-api:1.17.0`
- Helm chart: `dify-0.38.0`
- Kubernetes context: `chaosatlas-dify`
- Namespace: `dify-k8s-lab`
- Business endpoint: `/v1/chat-messages`
- Baseline expected response: HTTP `200`

## Steps to Reproduce

1. Deploy Dify on Kubernetes with `dify-k8s-api` configured as a single replica.
2. Verify that the API Pod is Ready and that a baseline request to `/v1/chat-messages` returns HTTP `200`.
3. Scale the API Deployment to zero replicas, or remove its only API Pod.
4. Send Chatflow requests through `/v1/chat-messages` during the disruption.
5. Restore the original replica count and record the HTTP status code and recovery time.

## Actual Behavior

The `replica_reduction` fault was executed in three independent trials. All three business probes observed `business_unreachable` with HTTP `502` while the API Deployment had no serving replica. The original replica count and deployment metadata were restored successfully after each trial.

## Expected Behavior

For a production deployment, the documented configuration should make the availability trade-off explicit and provide a multi-replica example. With at least two API replicas, losing one API Pod or performing a rolling update should leave another Ready API Pod serving requests. When all replicas are intentionally scaled to zero, the expected behavior should be documented as an unavailable service rather than treated as an application error.

## Suggested Investigation

- Document that a single API replica is suitable only for development or other non-HA environments.
- Provide a production example with at least two Ready API replicas.
- Use a `PodDisruptionBudget` as a complementary safeguard for voluntary disruptions; it cannot replace multiple replicas or prevent involuntary Pod loss.
- Distribute replicas across nodes or failure domains with pod anti-affinity.
- Verify the Service selector, readiness probe, and rolling-update strategy.
- Confirm that the rollout strategy preserves a serving replica when multiple replicas are configured.

## Acceptance Criteria

- The deployment documentation clearly distinguishes single-replica development settings from production settings.
- The production example configures at least two API replicas and an appropriate disruption policy.
- In a two-replica test, removing one API Pod does not create a sustained Chatflow outage.
- Replica count, PDB, Service configuration, and disruption-test results are documented.

## Reproduction Evidence

- Dify version: `1.17.0`
- API image: `langgenius/dify-api:1.17.0`
- API replicas during testing: `1`
- Fault: scaled the API Deployment from one replica to zero.
- Result: `3/3` valid trials returned HTTP `502` and were classified as `business_unreachable`.
- Recovery: the original replica count and deployment metadata were restored successfully after each trial.

Detailed sanitized runtime artifacts are available upon request.
