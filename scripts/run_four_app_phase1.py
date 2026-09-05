"""Run the four-application phase-1 readiness check through the unified engine.

The command is read-only with respect to Kubernetes. It writes dry-run evidence
and a sanitized readiness matrix below the external ChaosAtlas state root.
"""

from __future__ import annotations

import argparse
import json
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from chaosatlas.orchestration.engine import RunEngine, RunRequest
from chaosatlas.workspace import default_run_output, is_within, runs_root
from tools.project_onboarding import validate_project_profile


APP_ORDER = ("immich", "medusa", "rocketchat", "erpnext")


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def _kubectl_json(context: str, namespace: str, resource: str) -> dict[str, Any]:
    command = [
        "kubectl",
        "--context",
        context,
        "get",
        resource,
        "-n",
        namespace,
        "-o",
        "json",
    ]
    completed = subprocess.run(command, capture_output=True, text=True, timeout=45, check=False)
    if completed.returncode != 0:
        reason = (completed.stderr or completed.stdout).strip()
        raise RuntimeError(reason or f"kubectl exited {completed.returncode}")
    value = json.loads(completed.stdout)
    if not isinstance(value, dict):
        raise ValueError(f"kubectl {resource} response is not an object")
    return value


def collect_workload_readiness(context: str, namespace: str) -> dict[str, Any]:
    workloads: list[dict[str, Any]] = []
    errors: list[str] = []
    for resource, kind in (("deployments", "Deployment"), ("statefulsets", "StatefulSet")):
        try:
            value = _kubectl_json(context, namespace, resource)
        except (OSError, RuntimeError, ValueError, json.JSONDecodeError, subprocess.TimeoutExpired) as exc:
            errors.append(f"{resource}: {type(exc).__name__}: {exc}")
            continue
        for item in value.get("items") or []:
            if not isinstance(item, dict):
                continue
            metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
            spec = item.get("spec") if isinstance(item.get("spec"), dict) else {}
            status = item.get("status") if isinstance(item.get("status"), dict) else {}
            desired = int(spec.get("replicas") or 0)
            ready = int(status.get("readyReplicas") or 0)
            workloads.append(
                {
                    "kind": kind,
                    "name": str(metadata.get("name") or ""),
                    "desired_replicas": desired,
                    "ready_replicas": ready,
                    "ready": ready == desired and desired > 0,
                }
            )
    return {
        "status": "pass" if workloads and not errors and all(item["ready"] for item in workloads) else "blocked",
        "workloads": workloads,
        "errors": errors,
    }


def _free_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _wait_for_port(process: subprocess.Popen[str], port: int, timeout_s: float = 15) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if process.poll() is not None:
            stderr = process.stderr.read().strip() if process.stderr else ""
            raise RuntimeError(stderr or f"kubectl port-forward exited {process.returncode}")
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.25):
                return
        except OSError:
            time.sleep(0.2)
    raise TimeoutError("kubectl port-forward did not become ready")


def _direct_http_probe(url: str, *, headers: dict[str, str], timeout_s: float) -> tuple[int, str, float]:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    request = urllib.request.Request(url, headers=headers, method="GET")
    started = time.monotonic()
    try:
        with opener.open(request, timeout=timeout_s) as response:
            body = response.read(4096).decode("utf-8", errors="replace")
            return int(response.status), body, round((time.monotonic() - started) * 1000, 3)
    except urllib.error.HTTPError as exc:
        body = exc.read(4096).decode("utf-8", errors="replace")
        return int(exc.code), body, round((time.monotonic() - started) * 1000, 3)


def probe_service_oracle(profile: dict[str, Any], context: str) -> dict[str, Any]:
    namespace = str(profile["namespace_policy"]["allowed_namespaces"][0])
    oracle = profile["business_oracles"][0]
    local_port = _free_local_port()
    command = [
        "kubectl",
        "--context",
        context,
        "-n",
        namespace,
        "port-forward",
        f"svc/{oracle['service']}",
        f"{local_port}:{int(oracle['remote_port'])}",
    ]
    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        creationflags=creation_flags,
    )
    try:
        _wait_for_port(process, local_port)
        url = f"http://127.0.0.1:{local_port}{oracle['entrypoint']}"
        headers = {str(key): str(value) for key, value in (oracle.get("request_headers") or {}).items()}
        status_code, body, latency_ms = _direct_http_probe(
            url,
            headers=headers,
            timeout_s=float(oracle.get("timeout_s") or 10),
        )
        expected_status = int(oracle.get("expected_status") or 200)
        expected_body = str(oracle.get("expected_body") or "")
        passed = status_code == expected_status and (not expected_body or expected_body in body)
        return {
            "status": "pass" if passed else "fail",
            "oracle_id": str(oracle.get("id") or ""),
            "service": str(oracle.get("service") or ""),
            "entrypoint": str(oracle.get("entrypoint") or ""),
            "status_code": status_code,
            "expected_status": expected_status,
            "body_contract_satisfied": not expected_body or expected_body in body,
            "latency_ms": latency_ms,
        }
    except (OSError, RuntimeError, TimeoutError, urllib.error.URLError) as exc:
        return {
            "status": "blocked",
            "oracle_id": str(oracle.get("id") or ""),
            "service": str(oracle.get("service") or ""),
            "entrypoint": str(oracle.get("entrypoint") or ""),
            "reason": f"{type(exc).__name__}: {exc}",
        }
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


def probe_browser_entry(profile: dict[str, Any]) -> dict[str, Any]:
    oracle = profile["business_oracles"][0]
    headers = {str(key): str(value) for key, value in (oracle.get("request_headers") or {}).items()}
    hostname = headers.get("Host") or f"{profile['project_id']}.local"
    url = f"http://{hostname}{oracle['entrypoint']}"
    try:
        status_code, _body, latency_ms = _direct_http_probe(url, headers=headers, timeout_s=3)
        expected_status = int(oracle.get("expected_status") or 200)
        return {
            "status": "pass" if status_code == expected_status else "fail",
            "url": url,
            "status_code": status_code,
            "latency_ms": latency_ms,
        }
    except (OSError, urllib.error.URLError) as exc:
        return {"status": "blocked", "url": url, "reason": f"{type(exc).__name__}: {exc}"}


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Four-application phase-1 readiness matrix",
        "",
        f"- checked_at: `{report['checked_at']}`",
        f"- kube_context: `{report['kube_context']}`",
        f"- status: `{report['status']}`",
        "- browser entry is reported separately and does not change unified RunEngine readiness.",
        "",
        "| Application | Profile | Workloads | Oracle | Dry-run | Browser entry | Phase 2 | Selected candidate |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for item in report["applications"]:
        lines.append(
            "| {project_id} | {profile} | {workloads} | {oracle} | {dry_run} | {browser} | {phase2} | `{candidate}` |".format(
                project_id=item["project_id"],
                profile="valid" if item["profile_valid"] else "invalid",
                workloads=item["workload_readiness"]["status"],
                oracle=item["service_oracle"]["status"],
                dry_run=item["dry_run"]["status"],
                browser=item["browser_entry"]["status"],
                phase2="ready" if item["ready_for_phase2"] else "blocked",
                candidate=(item["dry_run"].get("selected_candidate_ids") or [""])[0],
            )
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- `ready_for_phase2` requires a valid profile, Ready Kubernetes workloads, a passing service Oracle, and `dry_run_ready` from the unified RunEngine.",
            "- Dry-run artifacts are planned evidence only and cannot support application weakness or defense claims.",
            "- Transactional workflow Oracles and live fault evidence remain phase-2 work.",
            "",
        ]
    )
    return "\n".join(lines)


def run_phase1(*, output_root: Path, kube_context: str) -> dict[str, Any]:
    output_root = Path(output_root).expanduser().resolve()
    if not is_within(output_root, runs_root()):
        raise ValueError(f"output must stay below external runs root: {runs_root()}")
    if output_root.exists() and any(output_root.iterdir()):
        raise FileExistsError(f"refusing non-empty output: {output_root}")
    output_root.mkdir(parents=True, exist_ok=True)

    applications: list[dict[str, Any]] = []
    for app in APP_ORDER:
        profile_path = ROOT / "projects" / "chaosatlas-apps" / app / "profile.json"
        profile = _load_json(profile_path)
        validation = validate_project_profile(profile)
        namespace = str((profile.get("namespace_policy") or {}).get("allowed_namespaces", [""])[0])
        workloads = collect_workload_readiness(kube_context, namespace)
        service_oracle = probe_service_oracle(profile, kube_context)
        browser_entry = probe_browser_entry(profile)
        dry_run = RunEngine().run(
            RunRequest(
                profile_path=profile_path,
                output_root=output_root / f"{app}-dry-run",
                mode="dry-run",
            )
        )
        ready = bool(
            validation["valid"]
            and workloads["status"] == "pass"
            and service_oracle["status"] == "pass"
            and dry_run.get("status") == "dry_run_ready"
        )
        applications.append(
            {
                "project_id": app,
                "profile": str(profile_path.relative_to(ROOT)).replace("\\", "/"),
                "profile_valid": bool(validation["valid"]),
                "profile_errors": list(validation.get("errors") or []),
                "workload_readiness": workloads,
                "service_oracle": service_oracle,
                "browser_entry": browser_entry,
                "dry_run": {
                    key: dry_run.get(key)
                    for key in (
                        "status",
                        "run_id",
                        "candidate_count",
                        "selected_candidate_ids",
                        "claim_scope",
                        "runtime_claims",
                        "error",
                    )
                },
                "ready_for_phase2": ready,
            }
        )

    phase2_ready = all(item["ready_for_phase2"] for item in applications)
    browser_ready = all(item["browser_entry"]["status"] == "pass" for item in applications)
    report = {
        "schema_version": "chaosatlas-four-app-phase1-readiness-v1",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "kube_context": kube_context,
        "status": "ready" if phase2_ready and browser_ready else "ready_with_entrypoint_blocker" if phase2_ready else "blocked",
        "phase2_ready_count": sum(1 for item in applications if item["ready_for_phase2"]),
        "browser_ready_count": sum(1 for item in applications if item["browser_entry"]["status"] == "pass"),
        "applications": applications,
    }
    (output_root / "readiness.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output_root / "readiness.md").write_text(render_markdown(report), encoding="utf-8", newline="\n")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=default_run_output("four-app-phase1"))
    parser.add_argument("--kube-context", default="chaosatlas-apps")
    args = parser.parse_args()
    try:
        report = run_phase1(output_root=args.output, kube_context=args.kube_context)
    except (FileExistsError, OSError, RuntimeError, ValueError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)}, ensure_ascii=False))
        return 2
    print(
        json.dumps(
            {
                "status": report["status"],
                "phase2_ready_count": report["phase2_ready_count"],
                "browser_ready_count": report["browser_ready_count"],
                "output": str(Path(args.output).resolve()),
            },
            ensure_ascii=False,
        )
    )
    return 0 if report["phase2_ready_count"] == len(APP_ORDER) else 2


if __name__ == "__main__":
    raise SystemExit(main())
