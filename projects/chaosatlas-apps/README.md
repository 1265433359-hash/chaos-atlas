# ChaosAtlas four-application capability environment

This directory contains the sanitized, reproducible project inputs for the
Immich, Medusa, Rocket.Chat, and ERPNext capability-learning environment.

## Unified RunEngine profiles

| Application | Profile | Business Oracle |
|---|---|---|
| Immich | `immich/profile.json` | `GET /api/server/ping` through `immich-server:2283` |
| Medusa | `medusa/profile.json` | `GET /health` through `medusa-backend:9000` |
| Rocket.Chat | `rocketchat/profile.json` | `GET /health` through `rocketchat-rocketchat:80` |
| ERPNext | `erpnext/profile.json` | `GET /api/method/ping` through `erpnext:8080` |

The profiles use the generic Kubernetes adapter and registered HTTP Oracle.
They do not create application-specific execution pipelines. The frozen
offline facts used by dry-run live under
`tests/fixtures/chaosatlas_offline/<application>/project_facts.json`.

Run the phase-1 acceptance harness from the repository root:

```powershell
$output = Join-Path $env:LOCALAPPDATA 'ChaosAtlas\runs\four-app-phase1-<unique-run-id>'
./scripts/invoke_python.ps1 scripts/run_four_app_phase1.py `
  --output $output `
  --kube-context chaosatlas-apps
```

The harness performs read-only Kubernetes inventory and service probes, then
runs every profile through the unified `RunEngine` in dry-run mode. Raw output
stays below the external ChaosAtlas state directory. Dry-run artifacts are
planned evidence and cannot support runtime weakness, defense, or Issue claims.

Browser ingress is an independent environment check. A failed browser entry
does not invalidate a passing in-cluster service Oracle, but it must be fixed
before browser-driven workflow testing.

Start or rebuild the independent local gateway with:

```powershell
./scripts/start_chaosatlas_apps_gateway.ps1
```

The gateway configuration is generated below the external ChaosAtlas runtime
state directory. Its container joins the Minikube Docker network and does not
depend on Dify containers or ignored repository directories.

## Phase-2 live canary

Install the pinned Chaos Mesh release into the dedicated Minikube context:

```powershell
helm upgrade --install chaos-mesh chaos-mesh/chaos-mesh `
  --kube-context chaosatlas-apps `
  --namespace chaos-mesh `
  --create-namespace `
  --version 2.8.4 `
  --set chaosDaemon.runtime=containerd `
  --set chaosDaemon.socketPath=/run/containerd/containerd.sock `
  --set dashboard.create=false `
  --set dnsServer.create=false `
  --wait `
  --timeout 5m
```

The first live canary uses the unified `RunEngine`, one stable candidate alias,
and one `pod_kill` per application. Keep every output below a unique external
run directory and pass the explicit live approval switch:

```powershell
$output = Join-Path $env:LOCALAPPDATA 'ChaosAtlas\runs\four-app-phase2-<unique-run-id>\immich-pod-kill-r1'
./scripts/invoke_python.ps1 -m chaosatlas.cli run `
  --profile projects/chaosatlas-apps/immich/profile.json `
  --mode live `
  --candidate-id server:deployment:immich:immich-server:pod_kill `
  --kube-context chaosatlas-apps `
  --approve-live `
  --output $output
```

Replace the profile and stable candidate alias for the other applications.
One canary is capability evidence only. It must not be promoted to an
application finding or Issue until the reproduction and RCA gates pass.
