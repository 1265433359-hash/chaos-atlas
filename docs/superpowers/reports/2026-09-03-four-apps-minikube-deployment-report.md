# Four Applications Minikube Deployment Report

Date: 2026-09-03
Profile: chaosatlas-apps
Driver: Docker
Kubernetes: v1.35.1
Resources: 10 CPUs, 18 GiB RAM, 80 GiB disk

## Infrastructure

- Minikube profile is running.
- Ingress addon is enabled.
- Ingress controller is running.
- Windows hosts entries are present for:
  - immich.local
  - erpnext.local
  - medusa.local
  - rocketchat.local
- The local Dify Nginx gateway is configured on port 80 and reaches the Minikube Ingress NodePort.
- Credentials are stored only in `.secrets/chaosatlas-apps/credentials.env`.

## Application Status

| Application | Status | Evidence |
|---|---|---|
| Immich | Running | Server, PostgreSQL, and Valkey are Ready; server endpoint is present |
| Medusa | Running | Backend, worker, PostgreSQL, and Redis are Ready; migration Job completed |
| ERPNext | Running | MariaDB, Valkey, workers, web, scheduler, and socketio are Ready; Frappe and ERPNext are installed |
| Rocket.Chat | Running | MongoDB, NATS, and Rocket.Chat are Ready; Rocket.Chat reports `SERVER RUNNING` |

## Ingress

Ingress objects are applied for all four hosts:

- http://immich.local
- http://erpnext.local
- http://medusa.local
- http://rocketchat.local

The ERPNext Ingress backend was corrected from the nonexistent `erpnext-nginx`
Service to the chart Service `erpnext` on port 8080.

## Verification

The applications are deployed and started. The local gateway forwards the four
domains to the Minikube Ingress NodePort `31063` while preserving each original
Host header. The current non-elevated Windows shell could not update the
protected hosts file, so its existing entries still point at `192.168.58.2`.
To finish browser access, update those four entries to `127.0.0.1` from an
elevated PowerShell.

- `http://immich.local/`
- `http://erpnext.local/`
- `http://medusa.local/health`
- `http://rocketchat.local/health`

The gateway was verified with an explicit local DNS override: Immich 200,
ERPNext 200, Medusa root 404 and health 200, and Rocket.Chat root 200 and
health 200.

No PVC or Secret was deleted. MongoDB was upgraded through supported major
versions, and Rocket.Chat uses the URL-encoded MongoDB URI Secret.
