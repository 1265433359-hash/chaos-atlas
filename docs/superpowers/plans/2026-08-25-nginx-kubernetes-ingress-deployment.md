# NGINX Kubernetes Ingress Deployment Plan

> **For agentic workers:** This document is a deployment preparation plan. Live Kubernetes mutation requires explicit approval, an allow-listed namespace, and a passed read-only preflight.

**Goal:** Deploy `nginx/kubernetes-ingress` as an isolated, reproducible ingress-layer fixture so that future ChaosAtlas experiments can test gateway routing, upstream failure propagation, recovery, and cleanup after the method is frozen.

**Architecture:** Treat NGINX Ingress Controller as the system under test and a small namespace-local HTTP echo service as the independent business oracle. Freeze the controller source/release, Helm values, rendered manifests, image digests, cluster context, namespace, and oracle contract before any live write. Keep deployment validation and future fault injection as separate phases.

**Tech Stack:** Kubernetes, Helm, `nginx/kubernetes-ingress`, NGINX Ingress Controller, ChaosAtlas project profiles, `kubectl` read-only preflight, server-side dry-run, and the existing ChaosAtlas evidence collectors.

---

## Scope

Included:

- Read-only inspection of the selected Kubernetes context and existing ingress controllers.
- A dedicated namespace, for example `chaosatlas-nginx-ingress`, subject to the namespace allow-list.
- A pinned NGINX Ingress Controller release and image digests.
- Helm rendering, namespace-first server-side dry-run, explicit apply, readiness checks, and cleanup rehearsal.
- A namespace-local fixture backend and one stable HTTP route.
- Two failure-free baseline windows with request, controller log, event, and recovery metadata.
- A project profile and candidate catalog prepared for later ChaosAtlas testing.

Excluded until the method is approved:

- PodKill, ContainerKill, NetworkChaos, HTTPChaos, DNSChaos, stress, or configuration fault injection.
- Production traffic, external DNS, public LoadBalancer exposure, TLS secrets, or real credentials.
- Knowledge-card promotion, weakness claims, RCA claims, or upstream issue submission.
- Automatic default-ingress changes in the existing cluster.

## Milestones

| Milestone | Target date | Status on 2026-08-25 | Exit condition |
|---|---:|---|---|
| M0 Scope and safety boundary | 2026-08-25 | complete | User agrees that this is deployment-only and isolated |
| M1 Read-only cluster preflight | 2026-08-25 | pending | Context, server version, Helm, CRDs, ingress classes, existing controllers, and residual resources recorded |
| M2 Immutable install bundle | 2026-08-26 | pending | Release, chart, values, rendered manifest, image digests, and SHA-256 manifest are frozen |
| M3 Static validation | 2026-08-26 | pending | Namespace-first and namespaced server-side dry-runs pass; cluster-scoped conflicts are explicitly reviewed |
| M4 Isolated deployment | 2026-08-27 | pending approval | Controller Pods Ready, Service reachable through the chosen local exposure path, no unrelated resources changed |
| M5 Fixture route and baseline | 2026-08-27 | pending | Independent HTTP oracle passes two failure-free windows and route/controller evidence is archived |
| M6 ChaosAtlas handoff profile | 2026-08-28 | pending | Profile validates, candidate families are catalogued as `pending`, and no runtime claim is created |
| M7 Method-ready checkpoint | 2026-08-29 | pending | User reviews the deployment evidence and separately authorizes any future injection canary |

## Execution Tasks

### Task 1: Read-only environment preflight

Record:

- Current Kubernetes context and cluster server version.
- Node readiness and available CPU/memory.
- Helm version and chart repository/OCI access.
- Existing `IngressClass`, NGINX controllers, admission webhooks, CRDs, Services, and namespaces.
- Existing `LoadBalancer`, `NodePort`, host-port, and ingress exposure conflicts.
- Chaos Mesh resource residuals and the target namespace state.

Required safety result:

```text
preflight.status = ready_for_install
mutation_performed = false
target_namespace = absent_or_owned_by_this_plan
unrelated_ingress_controller_conflict = reviewed
```

If the cluster already has an NGINX ingress controller, use a unique ingress class and do not replace or modify the existing default class.

### Task 2: Freeze source and installation provenance

Create an install bundle under:

```text
artifacts/nginx-kubernetes-ingress/
```

The bundle should contain:

- `source_manifest.json`: repository, release/tag, chart version, retrieval time, and source URL.
- `values.yaml`: only reviewed values; no credentials or private endpoints.
- `rendered.yaml`: Helm output.
- `image_digests.json`: every controller, admission, and fixture image digest.
- `sha256_manifest.json`: hashes for all deployment inputs.
- `README.md`: exact reproduction commands and known environment assumptions.

Pin the ingress class name, controller service exposure, replica count, readiness/liveness behavior, and admission policy explicitly. Do not rely on chart defaults for values that affect isolation or routing.

### Task 3: Render and validate without mutation

Run the following checks against the frozen bundle:

```powershell
helm lint <chart-or-oci-reference> --values artifacts/nginx-kubernetes-ingress/values.yaml
helm template chaosatlas-nginx-ingress <chart-or-oci-reference> `
  --namespace chaosatlas-nginx-ingress `
  --values artifacts/nginx-kubernetes-ingress/values.yaml `
  --output-dir .tmp-nginx-ingress-render
kubectl apply --dry-run=server -f artifacts/nginx-kubernetes-ingress/namespace.yaml
kubectl apply --dry-run=server -n chaosatlas-nginx-ingress `
  -f artifacts/nginx-kubernetes-ingress/rendered.yaml
```

The actual commands must be adjusted to the pinned chart packaging after M1; the plan does not authorize execution or apply. Namespace creation is validated first. Cluster-scoped objects are reviewed separately because they can affect other namespaces.

Expected result:

- YAML parses successfully.
- Selectors, service ports, ingress class, admission objects, and probes are internally consistent.
- No default ingress class is changed.
- No cluster-scoped object collides with an existing installation.
- Server-side dry-run passes or produces a recorded, reviewed block.

### Task 4: Deploy into the isolated namespace

This task requires a separate explicit live approval after M1-M3 pass.

Deployment order:

1. Create or adopt only the approved namespace.
2. Apply the reviewed cluster-scoped prerequisites, if required.
3. Install the Helm release with the frozen values.
4. Wait for controller Deployment/Pods and admission components to become Ready.
5. Confirm the controller Service and ingress class.
6. Record `kubectl get`, `describe`, events, and controller logs.

The deployment is successful only when:

```text
namespace = Active
controller_ready = true
admission_ready = true_or_explicitly_disabled
ingress_class_is_unique = true
unrelated_namespace_changes = none
chaos_residual = zero
```

### Task 5: Add a minimal independent fixture and business oracle

Use a small HTTP echo backend in a separate fixture namespace or an explicitly labeled fixture Deployment/Service. The route should:

- return a deterministic HTTP 200 response;
- expose a deterministic health endpoint;
- be reachable through the NGINX Ingress class;
- avoid external databases, credentials, and internet dependencies;
- have a cleanup owner recorded in the profile.

The first oracle should be:

```json
{
  "id": "nginx-ingress-fixture-route",
  "kind": "http",
  "service": "fixture-backend",
  "remote_port": 8080,
  "entrypoint": "/",
  "success_contract": "http_200_and_expected_body",
  "timeout_s": 5,
  "count": 10,
  "observation_window_s": 60,
  "probe_retry_interval_s": 2
}
```

Before any future fault injection, run two independent failure-free windows and store:

- request status and latency summary;
- controller and backend logs;
- Kubernetes events;
- route and endpoint identity;
- cleanup and residual scan;
- source and manifest hashes.

### Task 6: Prepare the ChaosAtlas project profile

Create a profile only after the deployment and fixture baseline are stable:

```text
artifacts/project_profiles/nginx-kubernetes-ingress/project_profile.json
artifacts/project_profiles/nginx-kubernetes-ingress/project_facts.json
```

The profile must identify:

- exact controller release and image digests;
- exact fixture revision and manifest roots;
- allowed namespace(s);
- unique ingress class;
- HTTP oracle;
- logs/events requirements;
- recovery deadline and cleanup owner;
- redaction policy.

Initial candidate catalog, all marked `pending` rather than executable:

| Candidate family | Target | Purpose |
|---|---|---|
| `pod_kill` | controller Pod | gateway availability and replacement recovery |
| `container_kill` | controller container | restart semantics versus Pod replacement |
| `network_delay` | controller-to-backend path | timeout and request propagation |
| `network_loss` | controller-to-backend path | error mapping, retry, and recovery |
| `backend_pod_kill` | fixture backend | upstream failure handling |
| `config_reload` | reviewed ingress config change | reload success/failure and route continuity |
| `replica_reduction` | controller Deployment | redundancy boundary, only after method supports structured deployment patches |

No candidate should enter runtime until the method's applicability, oracle, recovery, cleanup, and evidence contracts are explicitly frozen.

### Task 7: Handoff and future test gate

The handoff report must distinguish:

- deployment verified;
- route verified;
- baseline verified;
- mutation not performed;
- RCA not performed;
- knowledge not promoted.

Future testing starts with one approved canary, one fault family, one target, one oracle, and one isolated namespace. The first canary should not be selected solely by star count or upstream issue activity; it should be selected by the frozen candidate catalog and evidence budget.

## Rollback and Failure Handling

- If namespace-first dry-run fails, stop before apply and record `deployment_blocked`.
- If a cluster-scoped object collides with another controller, do not overwrite it; either switch to a namespaced-compatible installation or stop for review.
- If controller readiness fails, collect events/logs, uninstall only the owned Helm release, and verify the namespace and Chaos residual scans.
- If the fixture route is not reachable, classify it as `business_not_reachable`; do not proceed to fault injection.
- If cleanup leaves any owned resource, stop the handoff and repair cleanup before declaring deployment ready.

## Verification Checklist

- [ ] `helm lint` passes for the pinned values.
- [ ] Helm render is reproducible from the recorded source and values.
- [ ] Namespace-first server-side dry-run passes.
- [ ] Namespaced server-side dry-run passes.
- [ ] Cluster-scoped conflicts are reviewed.
- [ ] Controller and admission components are Ready.
- [ ] Unique ingress class is active without changing the cluster default.
- [ ] Fixture route returns the expected response.
- [ ] Two baseline windows pass.
- [ ] Logs, events, route identity, hashes, and cleanup evidence are archived.
- [ ] Project profile validation passes.
- [ ] No Chaos resources remain.
- [ ] No weakness, defense, RCA, or knowledge claim is emitted.

