"""Read-only preflight for a live ChaosAtlas project run."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


Runner = Callable[..., tuple[int, str, str]]
OracleRunner = Callable[[list[str], Path], tuple[int, str, str]]
CHAOS_RESOURCES = ("podchaos", "networkchaos", "stresschaos", "httpchaos", "dnschaos", "iochaos", "timechaos", "schedules", "workflows")
CHAOS_MESH_FAULTS = {
    "pod_kill", "backend_pod_kill", "container_kill", "stress_cpu", "stress_memory",
    "network_loss", "network_partition", "network_delay", "network_bandwidth",
    "network_duplicate", "network_corrupt", "dns_failure", "dns_delay",
    "http_delay", "http_abort", "http_status_error", "http_response_corrupt",
    "dependency_error", "connection_reset", "extension.io_delay", "extension.io_error",
    "extension.time_offset", "extension.jvm_gc_pause",
}


class KubernetesPreflight:
    """Perform only read operations and fail closed on unavailable evidence."""

    def __init__(
        self,
        *,
        profile: dict[str, Any],
        runner: Runner,
        kube_context: str | None = None,
        oracle_runner: OracleRunner | None = None,
    ) -> None:
        self.profile = profile
        self.runner = runner
        self.oracle_runner = oracle_runner or self._default_oracle_runner
        self.kube_context = str(kube_context).strip() if kube_context else None
        if self.kube_context and not re.fullmatch(r"[A-Za-z0-9_.:@/-]+", self.kube_context):
            raise ValueError("kube_context contains unsafe characters")

    def _command(self, command: list[str]) -> list[str]:
        return ["--context", self.kube_context, *command] if self.kube_context else list(command)

    def _run_json(self, args: list[str]) -> tuple[Any | None, str | None]:
        code, stdout, stderr = self.runner(self._command([*args, "-o", "json"]), timeout=30)
        if code != 0:
            return None, (stderr or stdout).strip() or f"kubectl exit {code}"
        try:
            return json.loads(stdout), None
        except json.JSONDecodeError as exc:
            return None, f"invalid JSON: {exc}"

    def _run_text(self, args: list[str]) -> tuple[str | None, str | None]:
        code, stdout, stderr = self.runner(self._command(args), timeout=30)
        if code != 0:
            return None, (stderr or stdout).strip() or f"kubectl exit {code}"
        return stdout.strip(), None

    def _namespace(self) -> str | None:
        namespaces = ((self.profile.get("namespace_policy") or {}).get("allowed_namespaces") or [])
        return str(namespaces[0]).strip() if len(namespaces) == 1 and str(namespaces[0]).strip() else None

    @staticmethod
    def _default_oracle_runner(command: list[str], cwd: Path) -> tuple[int, str, str]:
        try:
            completed = subprocess.run(
                command,
                cwd=str(cwd),
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            return 1, "", str(exc)
        return completed.returncode, completed.stdout or "", completed.stderr or ""

    def _grpc_client_dependency_error(self, oracle: dict[str, Any]) -> str | None:
        client_value = str(oracle.get("client") or "").strip()
        if not client_value:
            return "gRPC business oracle requires client"
        client_path = Path(client_value).expanduser().resolve()
        if not client_path.is_file():
            return f"gRPC client not found: {client_value}"
        command = [
            sys.executable,
            "-c",
            "import grpc; import demo_pb2; import demo_pb2_grpc",
        ]
        code, stdout, stderr = self.oracle_runner(command, client_path.parent)
        if code == 0:
            return None
        detail = (stderr or stdout).strip() or f"oracle dependency probe exited {code}"
        return f"gRPC client dependencies unavailable: {detail[-500:]}"

    def run(self) -> dict[str, Any]:
        namespace = self._namespace()
        checks: dict[str, Any] = {}
        errors: list[str] = []

        if self.kube_context:
            context, context_error = self.kube_context, None
        else:
            context, context_error = self._run_text(["config", "current-context"])
        checks["context"] = {"status": "pass" if context else "blocked", "value": context, "error": context_error}
        if not context:
            errors.append("kubectl current-context unavailable")

        if not namespace:
            checks["namespace"] = {"status": "blocked", "error": "exactly one allowed namespace is required"}
            errors.append("profile namespace policy is not a single namespace")
        else:
            namespace_obj, namespace_error = self._run_json(["get", "namespace", namespace])
            namespace_ok = namespace_obj is not None and namespace_error is None
            checks["namespace"] = {"status": "pass" if namespace_ok else "blocked", "name": namespace, "error": namespace_error}
            if not namespace_ok:
                errors.append(f"namespace unavailable: {namespace_error}")

        deployments, deployment_error = self._run_json(["get", "deployments", "-n", namespace or "", ]) if namespace else (None, "namespace unavailable")
        checks["deployments"] = {"status": "pass" if deployments is not None else "blocked", "count": len((deployments or {}).get("items") or []), "error": deployment_error}
        if deployments is None:
            errors.append(f"deployments unavailable: {deployment_error}")

        services, service_error = self._run_json(["get", "services", "-n", namespace or "", ]) if namespace else (None, "namespace unavailable")
        checks["services"] = {"status": "pass" if services is not None else "blocked", "count": len((services or {}).get("items") or []), "error": service_error}
        if services is None:
            errors.append(f"services unavailable: {service_error}")

        pods, pod_error = self._run_json(["get", "pods", "-n", namespace or "", ]) if namespace else (None, "namespace unavailable")
        checks["pods"] = {"status": "pass" if pods is not None else "blocked", "count": len((pods or {}).get("items") or []), "error": pod_error}
        if pods is None:
            errors.append(f"pods unavailable: {pod_error}")

        deployment_items = (deployments or {}).get("items") or [] if deployments is not None else []
        available_replicas = sum(
            max(
                int((item.get("status") or {}).get("availableReplicas") or 0),
                int((item.get("status") or {}).get("readyReplicas") or 0),
            )
            for item in deployment_items
            if isinstance(item, dict)
        )
        checks["workload_readiness"] = {
            "status": "pass" if deployment_items and available_replicas >= len(deployment_items) else "blocked",
            "deployment_count": len(deployment_items),
            "available_replicas": available_replicas,
        }
        if deployments is not None and (not deployment_items or available_replicas < len(deployment_items)):
            errors.append("workload deployments are not fully available")

        pod_items = (pods or {}).get("items") or [] if pods is not None else []
        running_pods = sum(1 for item in pod_items if isinstance(item, dict) and str((item.get("status") or {}).get("phase") or "") == "Running")
        checks["running_pods"] = {"status": "pass" if running_pods else "blocked", "count": running_pods}
        if pods is not None and not running_pods:
            errors.append("namespace has no running pods")

        oracle = (self.profile.get("business_oracles") or [{}])[0]
        oracle_configured = bool(oracle.get("entrypoint") and oracle.get("success_contract"))
        oracle_error = None if oracle_configured else "entrypoint and success_contract are required"
        if oracle_configured and str(oracle.get("kind") or "http").strip().lower() == "grpc":
            oracle_error = self._grpc_client_dependency_error(oracle)
            oracle_configured = oracle_error is None
        checks["business_oracle"] = {
            "status": "configured" if oracle_configured else "blocked",
            "id": oracle.get("id"),
            "entrypoint": oracle.get("entrypoint"),
            "success_contract": oracle.get("success_contract"),
            "error": oracle_error,
        }
        if not oracle_configured:
            errors.append(oracle_error or "business oracle contract is incomplete")

        events, events_error = self._run_json(["get", "events", "-n", namespace or "", ]) if namespace else (None, "namespace unavailable")
        checks["events"] = {"status": "pass" if events is not None else "blocked", "error": events_error}
        if events is None:
            errors.append(f"events unavailable: {events_error}")

        supported_faults = {
            str(name)
            for name, value in (self.profile.get("fault_support") or {}).items()
            if isinstance(value, dict) and str(value.get("status") or "").lower() in {"supported", "implemented"}
        }
        chaos_required = bool(supported_faults & CHAOS_MESH_FAULTS)
        residual: dict[str, Any] = {}
        if chaos_required:
            for resource in CHAOS_RESOURCES:
                value, error = self._run_json(["get", resource, "-n", namespace or "", ]) if namespace else (None, "namespace unavailable")
                if error and "not found" in error.lower():
                    value, error = {"items": []}, None
                if value is None:
                    residual[resource] = {"status": "blocked", "error": error}
                else:
                    items = value.get("items") or []
                    residual[resource] = {"status": "clean" if not items else "residual", "count": len(items), "names": [str((item.get("metadata") or {}).get("name")) for item in items]}
            residual_status = "blocked" if any(item.get("status") == "blocked" for item in residual.values()) else ("residual" if any(item.get("status") == "residual" for item in residual.values()) else "clean")
        else:
            residual = {resource: {"status": "not_required"} for resource in CHAOS_RESOURCES}
            residual_status = "not_required"
        residual_report = {"status": residual_status, "resources": residual}
        if residual_status not in {"clean", "not_required"}:
            errors.append(f"chaos residual gate: {residual_status}")

        return {
            "schema_version": "chaosatlas-runtime-preflight-v1",
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "project_id": self.profile.get("project_id"),
            "namespace": namespace,
            "status": "environment_blocked" if errors else "ready_for_injection",
            "checks": checks,
            "residual_resources": residual_report,
            "errors": errors,
            "read_only": True,
            "injection_performed": False,
        }
