"""Bounded Docker Compose runtime adapter for Dify E2E canaries."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.error import URLError
from urllib.request import Request, urlopen

from tools.fault_executor import validate_attestation


Runner = Callable[[list[str], int], tuple[int, str, str]]
_SAFE_SERVICE = re.compile(r"^[a-z][a-z0-9_-]{0,62}$")
_SECRET_ASSIGNMENT = re.compile(
    r"(?i)(password|passwd|secret|token|api[_-]?key|authorization|private[_-]?key)"
    r"\s*[:=]\s*[^\s,;]+"
)
_SECRET_WORD = re.compile(r"(?i)(password|passwd|secret|token|api[_-]?key|authorization|private[_-]?key)")


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def redact_text(value: str) -> str:
    """Redact common secret assignments before data enters evidence."""
    return _SECRET_ASSIGNMENT.sub(lambda match: f"{match.group(1)}=<redacted>", str(value or ""))


def _redacted_log_tail(value: str, limit: int = 80) -> str:
    lines = []
    for line in str(value or "").splitlines()[-limit:]:
        if _SECRET_WORD.search(line) and not _SECRET_ASSIGNMENT.search(line):
            lines.append("<redacted log line>")
        else:
            lines.append(redact_text(line))
    return "\n".join(lines)


def _default_runner(args: list[str], timeout: int = 30) -> tuple[int, str, str]:
    try:
        completed = subprocess.run(
            ["docker", "compose", *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 124, "", str(exc)
    return completed.returncode, completed.stdout or "", completed.stderr or ""


def _json_lines(value: str) -> list[dict[str, Any]]:
    text = str(value or "").strip()
    if not text:
        return []
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        parsed = None
    if isinstance(parsed, list):
        return [item for item in parsed if isinstance(item, dict)]
    if isinstance(parsed, dict):
        return [parsed]
    rows: list[dict[str, Any]] = []
    for line in text.splitlines():
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            rows.append(item)
    return rows


def _container_row(row: dict[str, Any]) -> dict[str, Any]:
    service = str(row.get("Service") or row.get("service") or "")
    return {
        "service": service,
        "container": str(row.get("Name") or row.get("name") or ""),
        "container_id": str(row.get("ID") or row.get("id") or ""),
        "image": str(row.get("Image") or row.get("image") or ""),
        "state": str(row.get("State") or row.get("state") or "").lower(),
        "health": str(row.get("Health") or row.get("health") or "").lower(),
        "status": redact_text(str(row.get("Status") or row.get("status") or "")),
    }


class DockerComposeAdapter:
    """Execute one-service-at-a-time, reversible Compose fault canaries."""

    def __init__(
        self,
        *,
        compose_dir: Path,
        compose_file: str,
        project_name: str | None = None,
        allowed_services: set[str],
        runner: Runner | None = None,
        external_base_url: str = "http://localhost",
        expected_compose_sha256: str | None = None,
    ) -> None:
        self.compose_dir = Path(compose_dir).resolve()
        self.compose_file = str(compose_file)
        self.project_name = str(project_name or "").strip()
        self.allowed_services = {str(item) for item in allowed_services}
        self.runner = runner or _default_runner
        self.external_base_url = external_base_url.rstrip("/")
        self.expected_compose_sha256 = str(expected_compose_sha256 or "").strip().lower()
        if not self.allowed_services or not all(_SAFE_SERVICE.fullmatch(item) for item in self.allowed_services):
            raise ValueError("allowed_services must contain safe Compose service names")
        compose_path = Path(self.compose_file)
        if not self.compose_file or compose_path.is_absolute() or ".." in compose_path.parts:
            raise ValueError("compose_file must be a relative path")

    def _args(self, *args: str) -> list[str]:
        prefix = ["--project-directory", str(self.compose_dir), "-f", str(self.compose_dir / self.compose_file)]
        if self.project_name:
            prefix.extend(["-p", self.project_name])
        return [*prefix, *args]

    def _run(self, *args: str, timeout: int = 30) -> tuple[int, str, str]:
        return self.runner(self._args(*args), timeout)

    def _ps(self) -> list[dict[str, Any]]:
        code, stdout, stderr = self._run("ps", "--all", "--format", "json")
        if code != 0:
            raise RuntimeError(redact_text(stderr or stdout or f"docker compose ps failed: {code}"))
        return _json_lines(stdout)

    def preflight(self) -> dict[str, Any]:
        compose_path = (self.compose_dir / self.compose_file).resolve()
        if not self.compose_dir.is_dir() or not compose_path.is_file() or self.compose_dir not in compose_path.parents:
            return {"status": "environment_blocked", "errors": ["compose directory or file is unavailable"]}
        actual_sha256 = hashlib.sha256(compose_path.read_bytes()).hexdigest()
        hash_errors = []
        if self.expected_compose_sha256 and actual_sha256 != self.expected_compose_sha256:
            hash_errors.append("compose file sha256 does not match the profile")
        code, stdout, stderr = self._run("config", "--services")
        declared = [line.strip() for line in stdout.splitlines() if line.strip()]
        errors = [] if code == 0 else [redact_text(stderr or stdout or f"docker compose config failed: {code}")]
        errors.extend(hash_errors)
        errors.extend(f"profile service is not declared: {item}" for item in sorted(self.allowed_services - set(declared)))
        return {
            "status": "ready_for_injection" if not errors else "environment_blocked",
            "compose_dir": str(self.compose_dir),
            "compose_file": self.compose_file,
            "project_name": self.project_name or None,
            "compose_sha256": actual_sha256,
            "allowed_services": sorted(self.allowed_services),
            "declared_services": declared,
            "errors": errors,
        }

    def inventory(self) -> dict[str, Any]:
        rows = [_container_row(row) for row in self._ps()]
        targets = [row for row in rows if row["service"] in self.allowed_services]
        return {
            "schema_version": "chaosatlas-compose-inventory-v1",
            "status": "verified",
            "targets": targets,
            "all_containers": rows,
        }

    def _service_row(self, service: str) -> dict[str, Any] | None:
        return next((row for row in self.inventory()["targets"] if row["service"] == service), None)

    def _url_oracle(self, path: str) -> dict[str, Any]:
        url = f"{self.external_base_url}{path}"
        try:
            request = Request(url, headers={"User-Agent": "ChaosAtlas-Dify-Canary/1"})
            with urlopen(request, timeout=5) as response:
                body = response.read(2048).decode("utf-8", errors="replace")
                return {"status": "pass" if 200 <= response.status < 300 else "fail", "http_status": response.status, "body": redact_text(body)}
        except (OSError, URLError) as exc:
            return {"status": "fail", "http_status": None, "body": "", "error": redact_text(str(exc))}

    def _exec_oracle(self, service: str, port: int, path: str) -> dict[str, Any]:
        code, stdout, stderr = self._run("exec", "-T", service, "curl", "-fsS", f"http://localhost:{port}{path}", timeout=15)
        body = stdout.strip()
        parsed: Any = None
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            pass
        healthy = code == 0 and (
            (parsed.get("status") == "ok" if isinstance(parsed, dict) else False)
            or body.strip().strip('"') == "ok"
        )
        return {"status": "pass" if healthy else "fail", "http_status": 200 if healthy else None, "body": redact_text(body), "error": redact_text(stderr) if not healthy else ""}

    def probe(self, service: str) -> dict[str, Any]:
        if service == "api":
            return {"service": service, "oracle": self._exec_oracle("api", 5001, "/health"), "external": self._url_oracle("/")}
        if service == "nginx":
            return {"service": service, "oracle": self._url_oracle("/")}
        if service == "sandbox":
            return {"service": service, "oracle": self._exec_oracle("sandbox", 8194, "/health")}
        if service == "local_sandbox":
            return {"service": service, "oracle": self._exec_oracle("local_sandbox", 5004, "/healthz")}
        if service == "redis":
            code, stdout, stderr = self._run("exec", "-T", "redis", "sh", "-c", "redis-cli -a \"$REDISCLI_AUTH\" ping", timeout=15)
            return {"service": service, "oracle": {"status": "pass" if code == 0 and stdout.strip() == "PONG" else "fail", "body": redact_text(stdout), "error": redact_text(stderr)}}
        row = self._service_row(service)
        running = bool(row and row.get("state") == "running")
        return {"service": service, "oracle": {"status": "pass" if running else "fail", "running": running, "status_text": row.get("status", "") if row else "missing"}}

    @staticmethod
    def _probe_passed(probe: dict[str, Any]) -> bool:
        oracle = probe.get("oracle") if isinstance(probe, dict) else None
        return isinstance(oracle, dict) and oracle.get("status") == "pass"

    def _wait_for_recovery(self, service: str, timeout_s: float, interval_s: float, stable_checks: int) -> dict[str, Any]:
        deadline = time.monotonic() + max(0.1, timeout_s)
        samples: list[dict[str, Any]] = []
        stable = 0
        while time.monotonic() <= deadline:
            sample = {"observed_at": now(), **self.probe(service)}
            samples.append(sample)
            if self._probe_passed(sample):
                stable += 1
                if stable >= stable_checks:
                    return {"status": "pass", "samples": samples, "stable_checks": stable_checks}
            else:
                stable = 0
            time.sleep(max(0.1, interval_s))
        return {"status": "fail", "samples": samples, "stable_checks": stable_checks}

    def _logs(self, service: str) -> dict[str, Any]:
        code, stdout, stderr = self._run("logs", "--no-color", "--tail", "100", service, timeout=30)
        raw = stdout if code == 0 else stderr or stdout
        redacted = _redacted_log_tail(raw)
        return {"return_code": code, "sha256": hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest(), "tail": redacted}

    def run_service_canary(self, service: str, *, recovery_timeout_s: float = 180, stable_checks: int = 3) -> dict[str, Any]:
        if service not in self.allowed_services:
            return {"status": "method_invalid", "errors": [f"service is outside allowlist: {service}"]}
        before = self.inventory()
        baseline = {"status": "pass", "samples": []}
        for _ in range(3):
            sample = {"observed_at": now(), **self.probe(service)}
            baseline["samples"].append(sample)
            if not self._probe_passed(sample):
                return {"status": "environment_blocked", "errors": [f"baseline oracle failed for {service}"], "before": before, "baseline": baseline}
            time.sleep(1)

        injection: dict[str, Any] = {"service": service, "requested_at": now(), "confirmed": False}
        effect: dict[str, Any] = {}
        recovery: dict[str, Any] = {"status": "not_run", "samples": []}
        cleanup: dict[str, Any] = {"status": "failed", "confirmed": False}
        restored = False
        try:
            code, stdout, stderr = self._run("kill", service, timeout=30)
            injection.update({"return_code": code, "stdout": redact_text(stdout), "stderr": redact_text(stderr), "confirmed": code == 0})
            if code != 0:
                return {"status": "environment_blocked", "errors": [f"docker compose kill failed for {service}"], "before": before, "baseline": baseline, "injection": injection}
            effect_probe = self.probe(service)
            effect = {"observed_at": now(), **effect_probe, "status": "degraded" if not self._probe_passed(effect_probe) else "response_observed"}
            up_code, up_stdout, up_stderr = self._run("up", "-d", service, timeout=120)
            injection["restore_command"] = {"return_code": up_code, "stdout": redact_text(up_stdout), "stderr": redact_text(up_stderr)}
            restored = up_code == 0
            if restored:
                recovery = self._wait_for_recovery(service, recovery_timeout_s, 2, stable_checks)
            after = self.inventory()
            original_services = {row["service"] for row in before["all_containers"]}
            final_services = {row["service"] for row in after["all_containers"]}
            cleanup_ok = restored and recovery["status"] == "pass" and original_services == final_services
            cleanup = {"status": "verified" if cleanup_ok else "failed", "confirmed": cleanup_ok, "service_healthy": recovery["status"] == "pass", "service_set_unchanged": original_services == final_services, "remaining_fault_resources": []}
            attestation_payload = {
                "baseline": baseline["status"] == "pass",
                "injection": injection["confirmed"],
                "observation": bool(effect),
                "recovery": recovery["status"] == "pass",
                "cleanup": cleanup["confirmed"],
                "independent_oracle": recovery["status"] == "pass",
                "comparison_eligible": bool(injection["confirmed"] and recovery["status"] == "pass" and cleanup["confirmed"]),
            }
            attestation = {"valid": validate_attestation(attestation_payload).valid, **attestation_payload}
            return {
                "schema_version": "chaosatlas-compose-canary-v1",
                "status": "live_completed" if attestation["valid"] else "recovery_timeout",
                "service": service,
                "fault_family": "container_kill",
                "before": before,
                "baseline": baseline,
                "injection": injection,
                "observation": effect,
                "recovery": recovery,
                "after": after,
                "cleanup": cleanup,
                "logs": self._logs(service),
                "attestation": attestation,
                "classification": "availability_degraded" if effect.get("status") == "degraded" else "response_observed",
            }
        finally:
            if not restored:
                self._run("up", "-d", service, timeout=120)
