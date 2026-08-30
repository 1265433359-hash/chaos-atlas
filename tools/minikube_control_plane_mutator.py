"""Guarded control-plane network mutator for disposable Minikube profiles."""

from __future__ import annotations

import json
import subprocess
from typing import Any, Callable


Runner = Callable[..., tuple[int, str, str]]


class MinikubeControlPlaneMutator:
    """Apply and restore API-server delay on an owned disposable profile."""

    def __init__(self, *, profile: str, context: str, runner: Runner | None = None, disposable: bool) -> None:
        self.profile = str(profile or "").strip()
        self.context = str(context or "").strip()
        self.runner = runner or self._subprocess_runner
        self.disposable = bool(disposable)

    def _run(self, args: list[str], timeout: int = 30) -> tuple[int, str, str]:
        try:
            return self.runner(args, timeout=timeout)
        except TypeError:
            return self.runner(args)

    @staticmethod
    def _subprocess_runner(args: list[str], timeout: int = 30) -> tuple[int, str, str]:
        completed = subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)
        return completed.returncode, completed.stdout, completed.stderr

    def _blocked(self, reason: str) -> dict[str, Any]:
        return {
            "status": "environment_blocked",
            "injection_confirmed": False,
            "cleanup_confirmed": False,
            "errors": [reason],
        }

    def _container_id(self) -> tuple[str | None, str | None]:
        code, stdout, stderr = self._run(["docker", "ps", "--filter", f"name={self.profile}", "--format", "{{.ID}}"])
        if code != 0:
            return None, (stderr or stdout).strip() or "docker ps failed"
        ids = [line.strip() for line in stdout.splitlines() if line.strip()]
        if len(ids) != 1:
            return None, f"expected one control-plane container, found {len(ids)}"
        return ids[0], None

    def __call__(
        self,
        *,
        latency_ms: int,
        manifest: dict[str, Any],
        probe: Callable[[str], dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        if not self.disposable or not self.profile.startswith("chaosatlas-"):
            return self._blocked("disposable control-plane profile is required")
        if isinstance(latency_ms, bool) or not isinstance(latency_ms, int) or not 1 <= latency_ms <= 300_000:
            return self._blocked("latency_ms must be in [1, 300000]")
        if not self.context or not isinstance(manifest, dict):
            return self._blocked("control-plane context and manifest are required")
        container, error = self._container_id()
        if not container:
            return self._blocked(error or "control-plane container unavailable")
        code, snapshot, stderr = self._run(["docker", "exec", container, "tc", "qdisc", "show", "dev", "eth0"])
        if code != 0:
            return self._blocked((stderr or snapshot).strip() or "tc qdisc snapshot failed")
        snapshot_text = snapshot.strip()
        if snapshot_text and not all(token in snapshot_text for token in ("qdisc", "noqueue")):
            return self._blocked("unsupported non-default control-plane qdisc")
        apply_code, apply_out, apply_err = self._run(
            ["docker", "exec", container, "tc", "qdisc", "replace", "dev", "eth0", "root", "netem", "delay", f"{latency_ms}ms"]
        )
        if apply_code != 0:
            return self._blocked((apply_err or apply_out).strip() or "tc netem apply failed")
        observation: dict[str, Any] | None = None
        probe_error: str | None = None
        if probe is not None:
            try:
                observation = probe("observe")
            except Exception as exc:
                probe_error = f"business observation probe failed: {type(exc).__name__}: {exc}"
        restore_code, restore_out, restore_err = self._run(
            ["docker", "exec", container, "tc", "qdisc", "del", "dev", "eth0", "root"]
        )
        restored = restore_code == 0 or "no such file" in (restore_err or "").lower()
        health_code, health_out, health_err = self._run(["kubectl", "--context", self.context, "get", "--raw=/readyz"])
        healthy = health_code == 0 and "ok" in (health_out or "").lower()
        if not restored or not healthy:
            return {
                "status": "cleanup_unverified",
                "injection_confirmed": True,
                "cleanup_confirmed": False,
                "snapshot": snapshot_text,
                "errors": [
                    *([] if restored else [(restore_err or restore_out).strip() or "qdisc restore failed"]),
                    *([] if healthy else [(health_err or health_out).strip() or "API server health check failed"]),
                    *([probe_error] if probe_error else []),
                ],
                "observation": observation,
                "recovery": {"confirmed": healthy, "health": {"return_code": health_code, "stdout": health_out, "stderr": health_err}},
                "cleanup": {"confirmed": False, "verified": False, "qdisc_restored": restored},
            }
        if probe_error:
            return {
                "status": "method_invalid",
                "injection_confirmed": True,
                "cleanup_confirmed": True,
                "snapshot": snapshot_text,
                "observation": observation,
                "recovery": {"confirmed": True, "health": {"return_code": health_code, "stdout": health_out, "stderr": health_err}},
                "cleanup": {"confirmed": True, "verified": True, "qdisc_restored": restored},
                "errors": [probe_error],
            }
        return {
            "status": "executed",
            "injection_confirmed": True,
            "cleanup_confirmed": True,
            "snapshot": snapshot_text,
            "observation": observation,
            "recovery": {"confirmed": True, "health": {"return_code": health_code, "stdout": health_out, "stderr": health_err}},
            "cleanup": {"confirmed": True, "verified": True, "qdisc_restored": restored},
            "restore": {"return_code": restore_code, "stdout": restore_out, "stderr": restore_err},
            "health": {"return_code": health_code, "stdout": health_out, "stderr": health_err},
            "manifest_sha256": _manifest_hash(manifest),
            "errors": [],
        }


def _manifest_hash(manifest: dict[str, Any]) -> str:
    import hashlib

    return hashlib.sha256(json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
