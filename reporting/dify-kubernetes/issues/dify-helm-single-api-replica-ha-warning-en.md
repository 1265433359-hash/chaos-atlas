# Single API replica default needs an explicit production availability warning

**Suggested labels:** `documentation`, `enhancement`

## Summary

The `dify` Helm chart defaults the API Deployment to a single replica. This is reasonable for a development or small test installation, but the chart and its documentation do not make the production availability trade-off sufficiently explicit.

This report is about the Helm chart defaults and deployment guidance, not about the expected HTTP `502` response when a Service has no backend endpoints.

## Environment

- Dify image: `langgenius/dify-api:1.17.0`
- Helm chart: `dify-0.38.0`
- Helm release: `dify-k8s`
- Kubernetes namespace: `dify-k8s-lab`
- API Deployment: `dify-k8s-api`
- API replicas during testing: `1`
- Business endpoint: `/v1/chat-messages`

## Reproduction

1. Install the chart with the default API replica setting, or set `api.replicas: 1`.
2. Confirm that the API Pod is Ready and that a baseline request to `/v1/chat-messages` returns HTTP `200`.
3. Remove the only API Pod or scale the API Deployment to zero replicas.
4. Send Chatflow requests during the disruption.
5. Restore the API replica count.

## Observed behavior

The test was repeated in three independent valid trials. All `3/3` trials returned HTTP `502` while the API Deployment had no serving replica. The service recovered after the original replica count and deployment metadata were restored.

The HTTP `502` is expected when there are no Service endpoints. The concern is that a production-oriented installation can start with one API replica without an explicit high-availability warning or a production example that uses multiple replicas.

## Requested improvement

Please consider:

- Documenting that a single API replica is intended for development, evaluation, or other non-HA environments.
- Providing a production-oriented values example with at least two API replicas.
- Documenting recommended disruption policy, readiness, and rolling-update settings for multiple replicas.
- Calling out any storage requirements or limitations when scaling API replicas.
- Documenting the expected behavior when all API replicas are intentionally scaled to zero.

## Acceptance criteria

- The chart documentation clearly distinguishes single-replica and production configurations.
- A production example shows the required replica and storage settings.
- A two-replica validation demonstrates that removing one API Pod does not create a sustained Chatflow outage.

Detailed sanitized runtime artifacts are available upon request.
