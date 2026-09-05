# Four Applications on Minikube Deployment Design

**Date:** 2026-09-03
**Status:** Approved design, pending implementation

## Goal

Install and start Immich, ERPNext, Medusa, and Rocket.Chat on a new local
Minikube profile. The deployment is for local validation and ChaosAtlas
experimentation, not production use.

## Architecture

Use one new Minikube profile named `chaosatlas-apps`. Existing Minikube
profiles and workloads must remain untouched.

Create one namespace per application:

- `chaosatlas-immich`
- `chaosatlas-erpnext`
- `chaosatlas-medusa`
- `chaosatlas-rocketchat`

Enable the Minikube Ingress addon. Route fixed local hostnames to the
application services:

- `immich.local`
- `erpnext.local`
- `medusa.local`
- `rocketchat.local`

The Windows hosts file will map these names to the new profile's Minikube IP.
No public DNS or TLS is required.

Use official application charts or manifests when available. Medusa will use
an official starter application generated locally, packaged as a repository
Docker image, and deployed through a small repository-owned Helm chart.

## Resources and Storage

Create the profile with:

- 10 virtual CPUs
- 18 GiB memory
- 80 GiB disk
- Docker driver

Run every application as a single replica with bounded resource requests and
limits. Start Immich without its Machine Learning component to keep the
18 GiB lab budget viable.

Use independent persistent volume claims for application data and databases.
Install a lightweight RWX provisioner for ERPNext site files because its
components need shared writable storage. Use local RWO storage for databases,
Redis, MongoDB, and Immich media where shared access is not required.

The deployment must not put production credentials or tokens in tracked files.
Generate local credentials into `.secrets/chaosatlas-apps/`, add that path to
`.gitignore`, and expose only the path and non-secret access instructions in
the completion summary.

## Application Components

### Immich

Deploy the server, PostgreSQL, Redis, and media storage. Keep Machine Learning
disabled for the first local run. Use the chart's supported health endpoint
and wait for database, Redis, server, and Ingress readiness.

### ERPNext

Deploy the ERPNext chart with MariaDB, Redis, workers, scheduler, and the
shared sites volume. Use one replica for each required component and keep
resource limits conservative.

### Medusa

Generate an official default starter project. Build its backend/admin/worker
image locally and load it into the `chaosatlas-apps` Minikube image store.
Deploy PostgreSQL, Redis, backend, admin, and worker. Do not add a storefront
or custom business data in this task.

### Rocket.Chat

Deploy Rocket.Chat with its MongoDB replica-set dependency and persistent
storage. Keep the deployment single-replica and use the application's
supported information or health endpoint for validation.

## Deployment Sequence

1. Preflight Docker, Minikube, kubectl, Helm, available disk, and profile
   name.
2. Create the `chaosatlas-apps` profile if it does not exist.
3. Enable Ingress and install the RWX storage dependency.
4. Create the four namespaces and generated secrets.
5. Deploy and validate dependencies and applications one namespace at a time:
   Immich, ERPNext, Medusa, then Rocket.Chat.
6. Apply Ingress resources and update the local hosts mapping.
7. Run the complete cross-application validation.

Helm releases and Kubernetes resources created by this task must use stable
names and labels so that status, cleanup, and future ChaosAtlas profiles can
identify their ownership.

## Failure Handling

Wait for each release with an explicit timeout. On a failure, collect
namespace-scoped Pod, Event, PVC, and Helm status, then stop before touching
the next application. Only the current failed release may be rolled back.
Never delete an existing Minikube profile, namespace, or release that was not
created by this task.

If the 18 GiB profile reaches memory pressure, reduce the current component's
resource limit or pause the next deployment. Do not silently change the
profile size or erase persistent data.

## Verification

The deployment is successful only when all of the following pass:

- The `chaosatlas-apps` profile is running.
- All four namespaces exist and contain no unexpected system resources.
- Required Pods are Ready.
- Required PVCs are Bound.
- All Helm releases report deployed status.
- Each local hostname resolves to the profile's Minikube IP.
- Each Ingress returns an expected HTTP response.
- Immich, ERPNext, Medusa Admin/API, and Rocket.Chat can be opened locally.
- A redacted deployment report records versions, image references, resource
  settings, health results, and any warnings.

The report must not contain passwords, API keys, tokens, authorization
headers, or private keys.

## Scope Boundaries

This task does not configure public DNS, TLS, backups, high availability,
production-grade replicas, external object storage, custom Medusa storefront
code, or Chaos Mesh fault injection. Those are separate follow-up tasks.
