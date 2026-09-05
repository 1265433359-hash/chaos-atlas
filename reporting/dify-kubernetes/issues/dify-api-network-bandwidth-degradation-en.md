# API returns HTTP 500 after a PostgreSQL timeout under network degradation

**Suggested labels:** `bug`, `performance`, `availability`, `networking`

## Summary

When the network bandwidth available to the Dify API workload is constrained,
Chatflow requests can return HTTP `500` and take several seconds to complete.
The API logs show that the request fails because the API cannot receive a
PostgreSQL response before the database connection times out.

The database timeout is then exposed as a generic HTTP `500`, rather than as a
clear, bounded, and diagnosable dependency or timeout error.

## Environment

- Dify version: `1.17.0`
- API image: `langgenius/dify-api:1.17.0`
- Deployment platform: Kubernetes
- Namespace: `dify-k8s-lab`
- Business endpoint: `POST /v1/chat-messages`
- Fault target: the Dify API workload
- Fault profile: `1mbps`, queue limit `1000`, buffer `1000`, duration `30s`
- Fault direction: `to`
- Fault mode: `one`

## Steps to Reproduce

1. Verify that the baseline Chatflow request returns HTTP `200` and record its
   latency.
2. Apply a one-target network bandwidth limit to the Dify API workload using
   the profile above.
3. Send the same Chatflow request while the limit is active.
4. Record the HTTP status, end-to-end latency, API logs, database logs, and
   downstream dependency timings.
5. Remove the bandwidth limit and verify that the business path recovers.
6. Repeat the test after restoring the deployment state.

## Actual Behavior

Under the bandwidth fault, the first observed Chatflow request returned:

```text
HTTP 500 after approximately 7.9 seconds
```

Later requests returned HTTP `200`, but took approximately `18.0-20.6`
seconds. The same baseline request normally took approximately `1.3-1.7`
seconds.

Across the low and high bandwidth profiles, six valid trials reproduced the
same pattern: an initial HTTP `500` followed by successful but much slower
responses. The business path recovered after the fault was removed.

## Initial Root-Cause Evidence

During the failed request, the Dify API log contained:

```text
psycopg2.OperationalError:
could not receive data from server: Connection timed out

sqlalchemy.exc.OperationalError: (psycopg2.OperationalError) could not receive
data from server: Connection timed out

POST /v1/chat-messages HTTP/1.1 500 ... 7.9...
```

This supports the following immediate failure chain:

```text
API network bandwidth is constrained
    -> API-to-PostgreSQL communication is delayed
    -> PostgreSQL response exceeds the active connection timeout
    -> psycopg2/SQLAlchemy raises OperationalError
    -> the exception reaches the HTTP handler
    -> the endpoint returns generic HTTP 500
```

The logs identify the PostgreSQL receive timeout as the immediate technical
cause of the observed `500`. Because the network fault affects the API's
traffic generally, additional downstream calls may also contribute to the
long successful latency. The exact timeout, connection-pool, and exception
handling configuration still needs to be confirmed.

## Expected Behavior

When network capacity or a downstream dependency is degraded, Dify should:

- enforce explicit and documented timeout budgets;
- return a stable, diagnosable dependency or timeout error, such as HTTP
  `502`, `503`, or `504`, where appropriate;
- avoid exposing an unexplained generic HTTP `500` for a known transient
  dependency failure;
- bound total request latency; and
- avoid uncontrolled retries that amplify load during the outage.

Returning an error under severe network degradation may be unavoidable. The
issue is the error classification, lack of controlled degradation, and
excessive request latency.

## Suggested Investigation

- Review API PostgreSQL connection and statement timeout settings.
- Review SQLAlchemy connection-pool behavior after a receive timeout.
- Identify the API exception handler responsible for mapping
  `psycopg2.OperationalError` to the HTTP response.
- Correlate API request IDs with PostgreSQL logs and connection metrics.
- Run an isolated API-to-PostgreSQL network fault to separate database effects
  from Redis, Worker, plugin, and model-provider effects.
- Measure retry counts, queueing, and downstream timings during the fault.
- Define and test a latency and error-rate budget for this degradation profile.

## Acceptance Criteria

- PostgreSQL connection timeouts are classified as dependency or timeout
  failures rather than unexplained generic HTTP `500` responses.
- Critical downstream calls have documented and enforced timeout and retry
  budgets.
- Requests terminate within the documented latency budget under the tested
  bandwidth profile.
- Recovery after bandwidth restoration is verified without manual repair.
- The behavior is covered by an automated network-degradation regression test.

## Reproduction Evidence

- ChaosAtlas run: `dify-k8s-llm-policy-guarded-20260902-r2`
- Fault: one API target constrained to `1mbps` with queue limit `1000`, buffer
  `1000`, duration `30s`, direction `to`, and mode `one`.
- Result: six valid trials across low and high profiles reproduced an initial
  HTTP `500` after approximately `7.9` seconds, followed by HTTP `200`
  responses taking approximately `18.0-20.6` seconds.
- Baseline: approximately `1.3-1.7` seconds for the same Chatflow request.
- Recovery: the business path recovered after the bandwidth limit was removed.
- Cleanup: all valid trials passed cleanup verification.

The evidence establishes a reproducible runtime behavior and identifies the
PostgreSQL receive timeout as the immediate cause of the failed request. It
does not yet isolate every downstream contributor to the later high latency.
