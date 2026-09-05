# Plugin daemon restart is exposed as HTTP 400 `invalid_param`

**Suggested labels:** `bug`, `plugin-daemon`, `reliability`, `kubernetes`

## Summary

When the Dify plugin daemon is restarted, a valid Chatflow request can receive
HTTP `400` with the error code `invalid_param`. The same request succeeds with
HTTP `200` after the plugin runtime becomes available again.

The client request is not malformed. A temporary plugin-daemon dependency
failure is being exposed as a client parameter-validation error, which is
misleading and makes retry and alert handling difficult.

## Environment

- Dify version: `1.17.0`
- API image: `langgenius/dify-api:1.17.0`
- Deployment platform: Kubernetes
- Namespace: `dify-k8s-lab`
- Plugin daemon replicas: `1`
- Business endpoint: `POST /v1/chat-messages`
- Chatflow mode: `advanced-chat`

## Steps to Reproduce

1. Deploy Dify and configure a working Chatflow with an installed model plugin.
2. Verify that the Chatflow request returns HTTP `200` with the expected
   response shape.
3. Send the same request while restarting the `plugin-daemon` container.
4. Record the API response status, error code, plugin-daemon readiness, pod
   restart count, and timestamps.
5. Wait for the plugin runtime to become available and send the same request
   again.
6. Repeat the test after restoring the deployment state.

## Actual Behavior

During the restart window, the valid Chatflow request returns responses such
as:

```text
HTTP 400
error code: invalid_param
```

After the plugin daemon and its plugin runtime recover, the same request
returns HTTP `200` with a valid Chatflow response.

Observed across three independent valid trials:

- Trial `0018`: three consecutive `400 invalid_param` responses, then `200`.
- Trial `0019`: six consecutive `400 invalid_param` responses, then `200`.
- Trial `0020`: ten consecutive `400 invalid_param` responses, then `200`.
- All three trials recovered successfully.

## Initial Root-Cause Evidence

The plugin-daemon logs captured during the failure contain the following
sequence:

```text
no plugin states found in redis
no plugin available nodes found
no available node, plugin runtime not found
```

The daemon also logged the plugin dispatch request as HTTP `404` while the
runtime was unavailable. This supports the following failure chain:

```text
plugin daemon restart
    -> plugin runtime is not registered or not restored yet
    -> Redis has no state for the plugin runtime
    -> plugin daemon has no available node and returns 404
    -> API exposes the dependency failure as 400 invalid_param
```

The immediate cause is therefore a plugin-runtime availability or recovery
window, not invalid user input. The exact source-level cause of the missing
Redis state or the API error mapping still needs to be confirmed in the
startup/registration and API exception-handling paths.

## Expected Behavior

If the request is valid and the plugin daemon is temporarily unavailable, Dify
should return a documented service-availability or dependency error, such as
HTTP `503`, rather than HTTP `400 invalid_param`.

The response should clearly indicate that the failure is transient and may be
retryable. It should not imply that the client needs to change a valid request.

## Suggested Investigation

- Trace one request across the API and plugin daemon using a shared trace ID.
- Identify the API code path that converts the plugin-daemon failure into
  `invalid_param`.
- Compare the plugin runtime registration timestamp with the pod readiness
  timestamp.
- Record the relevant Redis plugin-state keys before restart, during startup,
  and after recovery.
- Ensure readiness does not become successful before the required plugin
  runtime is available, or make the API handle that transition explicitly.
- Define timeout and retry behavior for transient plugin-daemon unavailability.

## Acceptance Criteria

- A valid Chatflow request does not receive `400 invalid_param` solely because
  the plugin daemon is restarting.
- Temporary plugin-daemon unavailability is represented by a documented,
  distinguishable, and retryable error contract.
- Logs identify the unavailable plugin dependency and include correlation data.
- Plugin runtime registration and readiness behavior are covered by an
  automated restart regression test.
- The fix is verified both with a single plugin-daemon replica and with a
  multi-replica deployment where applicable.

## Reproduction Evidence

- ChaosAtlas run: `dify-k8s-llm-policy-guarded-20260902-r2`
- Trials: `0018`, `0019`, and `0020`
- Fault: plugin-daemon `container_kill`
- Result: `3/3` valid trials reproduced `400 invalid_param` responses during
  the restart window, followed by valid `200` recovery responses.
- Cleanup: `3/3` trials passed cleanup verification.

The evidence establishes a reproducible runtime behavior and its immediate
dependency failure chain. It does not claim that the exact source-level root
cause has been fully isolated.
