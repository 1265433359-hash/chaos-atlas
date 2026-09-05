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
