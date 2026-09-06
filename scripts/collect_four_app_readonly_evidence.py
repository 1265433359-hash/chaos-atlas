"""Collect fixed-deployment, read-only evidence for the H3 review package.

This command never reads Secret data, creates identities, sends application
requests, or mutates Kubernetes resources. It records image digests, Service
identity/spec and ready Pod identities only.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any


APPS = ("immich", "medusa", "rocketchat", "erpnext")


def kubectl(context: str, args: list[str]) -> tuple[int, str, str]:
    try:
        value = subprocess.run(["kubectl", "--context", context, *args], capture_output=True,
                               text=True, encoding="utf-8", errors="replace", timeout=30, check=False)
        return value.returncode, value.stdout or "", value.stderr or ""
    except (OSError, subprocess.SubprocessError) as exc:
        return 124, "", f"{type(exc).__name__}: {exc}"


def query_json(context: str, args: list[str]) -> tuple[dict[str, Any] | None, str | None]:
    code, stdout, stderr = kubectl(context, [*args, "-o", "json"])
    if code:
        return None, (stderr or stdout).strip()[:1000] or f"kubectl exit {code}"
    try:
        value = json.loads(stdout)
    except json.JSONDecodeError:
        return None, "invalid JSON"
    return value if isinstance(value, dict) else None, None


def collect(root: Path, context: str, output: Path) -> dict[str, Any]:
    reports = []
    for app in APPS:
        profile_path = root / "projects" / "chaosatlas-apps" / app / "profile.json"
        profile = json.loads(profile_path.read_text(encoding="utf-8-sig"))
        namespace = str(profile["namespace_policy"]["allowed_namespaces"][0])
        service = str(profile["business_oracles"][0]["service"])
        service_doc, service_error = query_json(context, ["-n", namespace, "get", "service", service])
        pods_doc, pods_error = query_json(context, ["-n", namespace, "get", "pods"])
        service_meta = (service_doc or {}).get("metadata") or {}
        service_spec = (service_doc or {}).get("spec") or {}
        pods = []
        for pod in (pods_doc or {}).get("items") or []:
            meta = pod.get("metadata") or {}
            statuses = pod.get("status", {}).get("containerStatuses") or []
            pods.append({
                "name": meta.get("name"), "uid": meta.get("uid"), "phase": pod.get("status", {}).get("phase"),
                "ready": any(s.get("ready") is True for s in statuses),
                "images": sorted(str(s.get("imageID") or "") for s in statuses if s.get("imageID")),
            })
        source = {
            "profile_path": profile_path.relative_to(root).as_posix(),
            "profile_sha256": hashlib.sha256(profile_path.read_bytes()).hexdigest(),
            "declared_project_revision": profile.get("project_commit"),
            "declared_app_version": (profile.get("deployment_snapshot") or {}).get("app_version"),
            "declared_image": (profile.get("deployment_snapshot") or {}).get("primary_image"),
        }
        reports.append({
            "project_id": app, "namespace": namespace, "service": service,
            "service_uid": service_meta.get("uid"), "service_selector": service_spec.get("selector"),
            "service_ports": service_spec.get("ports"), "service_error": service_error,
            "pods": pods, "pods_error": pods_error, "source": source,
            "api_semantics": "unknown: fixed-version endpoint/request/permission evidence not collected by read-only Kubernetes inspection",
        })
    result = {
        "schema_version": "chaosatlas-four-app-readonly-evidence-v1", "claim_scope": "read_only_deployment_observation",
        "context": context, "collected_at": datetime.now(timezone.utc).isoformat(), "projects": reports,
        "writes_performed": False, "secrets_read": False, "identities_created": False,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    parser.add_argument("--context", default="chaosatlas-apps")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = collect(Path(args.root).resolve(), args.context, Path(args.output).resolve())
    print(json.dumps({"status": "collected", "projects": len(result["projects"]), "output": str(Path(args.output).resolve())}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
