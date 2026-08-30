"""Deterministic metadata and cleanup attestation for isolated fault runs."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re
from typing import Any, Callable


HIGH_RISK = frozenset(
    {
        "disk_pressure",
        "file_descriptor_exhaustion",
        "process_exhaustion",
        "replica_reduction",
        "dns_failure",
        "http_abort",
        "dependency_error",
        "connection_reset",
        "business_dependency_unreachable",
        "http_rate_limit",
        "config_drift",
        "env_misconfiguration",
        "secret_rotation",
        "rollout_pause",
        "image_pull_failure",
        "pod_unschedulable",
        "api_server_delay",
    }
)


@dataclass(frozen=True)
class NamespaceLease:
    """Scope and lifecycle metadata for one isolated fault experiment."""

    namespace: str
    project: str
    fault_family: str
    seed: int
    disposable: bool

    @classmethod
    def for_fault(cls, fault_family: str, *, project: str, seed: int) -> "NamespaceLease":
        family = str(fault_family or "").strip()
        project_id = str(project or "").strip()
        if not family:
            raise ValueError("fault_family is required")
        if not project_id:
            raise ValueError("project is required")
        if isinstance(seed, bool) or not isinstance(seed, int):
            raise ValueError("seed must be an integer")
        digest = hashlib.sha256(f"{project_id}:{family}:{seed}".encode("utf-8")).hexdigest()[:12]
        return cls(
            namespace=f"chaosatlas-run-{digest}",
            project=project_id,
            fault_family=family,
            seed=seed,
            disposable=family in HIGH_RISK,
        )

    def cleanup_record(self, *, resources: list[str], owner: str) -> dict[str, object]:
        remaining = [str(item) for item in resources if str(item).strip()]
        owner_id = str(owner or "").strip()
        verified = owner_id == "chaosatlas" and not remaining
        return {
            "schema_version": "chaosatlas-isolated-cleanup-v1",
            "status": "verified" if verified else "blocked",
            "owner": owner_id,
            "namespace": self.namespace,
            "resources": remaining,
            "disposable": self.disposable,
        }


class DisposableNamespaceManager:
    """Create and tear down one owned namespace for a high-risk canary."""

    def __init__(
        self,
        *,
        project: str,
        fault_family: str,
        seed: int,
        runner: Callable[..., Any],
        kube_context: str | None = None,
    ) -> None:
        self.lease = NamespaceLease.for_fault(fault_family, project=project, seed=seed)
        self.runner = runner
        self.kube_context = str(kube_context).strip() if kube_context else None
        self.prepared = False

    def _run(self, args: list[str], timeout: int = 120) -> tuple[int, str, str]:
        command = ["--context", self.kube_context, *args] if self.kube_context else args
        try:
            value = self.runner(command, timeout=timeout)
        except TypeError:
            value = self.runner(command)
        if isinstance(value, tuple):
            code, stdout, stderr = value
            return int(code), str(stdout or ""), str(stderr or "")
        if isinstance(value, dict):
            return int(value.get("return_code", 1)), str(value.get("stdout") or ""), str(value.get("stderr") or "")
        raise TypeError("namespace runner must return a tuple or object")

    def prepare(self) -> dict[str, Any]:
        namespace = self.lease.namespace
        if not self.lease.disposable:
            return {"status": "environment_blocked", "namespace": namespace, "reason": "fault does not require a disposable namespace"}
        if not re.fullmatch(r"chaosatlas-run-[a-f0-9]{12}", namespace):
            return {"status": "environment_blocked", "namespace": namespace, "reason": "lease namespace does not match the owned prefix"}
        code, stdout, stderr = self._run(["create", "namespace", namespace])
        created = code == 0
        if not created and "already exists" not in stderr.lower() and "alreadyexists" not in stderr.lower():
            return {"status": "environment_blocked", "namespace": namespace, "reason": (stderr or stdout).strip() or f"namespace create exited {code}"}
        labels = [
            "chaosatlas.dev/owner=chaosatlas",
            f"chaosatlas.dev/project={self.lease.project}",
            f"chaosatlas.dev/fault-family={self.lease.fault_family}",
            f"chaosatlas.dev/seed={self.lease.seed}",
        ]
        label_code, label_stdout, label_stderr = self._run(["label", "namespace", namespace, *labels, "--overwrite"])
        if label_code != 0:
            return {"status": "environment_blocked", "namespace": namespace, "reason": (label_stderr or label_stdout).strip() or f"namespace label exited {label_code}"}
        self.prepared = True
        return {
            "status": "created" if created else "present",
            "namespace": namespace,
            "lease": {
                "project": self.lease.project,
                "fault_family": self.lease.fault_family,
                "seed": self.lease.seed,
                "disposable": self.lease.disposable,
            },
        }

    def destroy(self) -> dict[str, Any]:
        namespace = self.lease.namespace
        if not self.prepared:
            return {"status": "environment_blocked", "namespace": namespace, "reason": "namespace lease was not prepared"}
        code, stdout, stderr = self._run(["delete", "namespace", namespace, "--wait=true", "--timeout=120s"])
        if code != 0 and "not found" not in stderr.lower() and "notfound" not in stderr.lower():
            return {"status": "blocked", "namespace": namespace, "reason": (stderr or stdout).strip() or f"namespace delete exited {code}"}
        verify_code, verify_stdout, verify_stderr = self._run(["get", "namespace", namespace])
        gone = verify_code != 0 and ("not found" in verify_stderr.lower() or "notfound" in verify_stderr.lower())
        return {
            "status": "verified" if gone else "blocked",
            "namespace": namespace,
            "delete": {"return_code": code, "stdout": stdout, "stderr": stderr},
            "verification": {"return_code": verify_code, "stdout": verify_stdout, "stderr": verify_stderr},
            "reason": None if gone else "namespace still exists after deletion",
        }
