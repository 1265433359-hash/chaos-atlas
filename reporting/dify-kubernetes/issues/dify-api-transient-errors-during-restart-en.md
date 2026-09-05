# Single Dify API Replica Exposes Transient HTTP 502 Responses During Restart

**Affected project:** Dify Kubernetes deployment configuration

**Suggested labels:** `availability`, `kubernetes`, `deployment`, `needs-investigation`

## Summary

In a Dify Kubernetes deployment with one API replica, terminating the API Pod or its `api` container causes Chatflow requests to temporarily fail with HTTP `502`. The service eventually recovers, but user requests fail during the replacement window. This report is primarily about the single-replica deployment behavior; multi-replica failover was not tested in these trials.

## Environment

- Dify version: `1.17.0`
- API image: `langgenius/dify-api:1.17.0`
- Helm chart: `dify-0.38.0`
- API replicas during testing: `1`
- Kubernetes context: `chaosatlas-dify`
- Namespace: `dify-k8s-lab`
- Business endpoint: `/v1/chat-messages`

## Steps to Reproduce

1. Deploy Dify with `dify-k8s-api` configured as one replica and verify that the Chatflow baseline request succeeds.
2. For the Pod test, apply a Chaos Mesh `PodChaos` with `action: pod-kill`, `mode: one`, and `duration: 30s`.
3. For the container test, apply a Chaos Mesh `PodChaos` with `action: container-kill`, `containerNames: [api]`, `mode: one`, and `duration: 30s`.
4. Send Chatflow requests continuously while the Pod or container is being replaced.
5. Record HTTP status codes, error types, readiness transitions, endpoint changes, and recovery time.

## Actual Behavior

- `container_kill`: all three valid trials observed multiple HTTP `502` responses followed by HTTP `200` recovery.
- `pod_kill`: one valid trial recovered without a business failure; one ended as `business_unreachable` after repeated `502`/`400` responses; and one ended as `degraded` after repeated `502` responses followed by HTTP `200` recovery.
- All six valid trials eventually passed the recovery and cleanup checks.

## Expected Behavior

With multiple API replicas, the Service should promptly remove the non-Ready Pod from its endpoints and route requests to another Ready instance. In a single-replica deployment, Dify or its deployment documentation should clearly define the expected restart interruption and provide guidance for avoiding it in production.

## Suggested Investigation

- Check `terminationGracePeriodSeconds` and application graceful-shutdown handling.
- Verify that the readiness probe fails promptly before the process stops accepting traffic.
- Measure Service endpoint propagation and kube-proxy forwarding delay.
- Review Gunicorn and application shutdown, connection reuse, and keep-alive behavior.
- Repeat the test with two or more API replicas and compare the error rate and recovery window.

## Acceptance Criteria

- With two or more API replicas, restarting one API Pod does not cause a sustained Chatflow outage.
- For single-replica deployments, the documentation states that restart-time interruption is expected and recommends a production replica count.
- If zero-error failover is not possible, define and meet an explicit error-rate and recovery-time SLO.
- Readiness state, Service endpoints, and application logs explain every failed request.

## Reproduction Evidence

- Dify version: `1.17.0`
- API image: `langgenius/dify-api:1.17.0`
- API replicas during testing: `1`
- Faults: Chaos Mesh `pod-kill` and `container-kill`, each targeting one API instance for `30s`.
- Result: all `3/3` container-kill trials observed multiple HTTP `502` responses followed by HTTP `200` recovery. In the pod-kill trials, `2/3` observed transient failures and `1/3` recovered without a business failure.
- Recovery: all `6/6` valid trials passed the recovery and cleanup checks.

Detailed sanitized runtime artifacts are available upon request.
