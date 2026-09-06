"""Run one guarded HTTPChaos canary and emit reusable runtime evidence.

The canary is intentionally small: one existing synthetic application
namespace, one health endpoint, one mutation, and the shared Kubernetes
lifecycle executor.  A runtime backend is promoted only when the lifecycle
attestation *and* the expected HTTP effect are both present.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from chaosatlas.workspace import runs_root
from tools.kubernetes_lifecycle_executor import KubernetesLifecycleExecutor


HTTP_FAULTS = {
    "http_delay",
    "http_abort",
    "http_status_error",
    "http_response_corrupt",
    "dependency_error",
    "connection_reset",
}


def _manifest(*, fault: str, namespace: str, name: str, selector: dict[str, str], port: int, path: str) -> dict[str, Any]:
    if fault not in HTTP_FAULTS:
        raise ValueError(f"unsupported HTTPChaos canary fault: {fault}")
    spec: dict[str, Any] = {
        "mode": "one",
        "selector": {"namespaces": [namespace], "labelSelectors": selector},
        "port": port,
        "path": path,
        "duration": "15s",
    }
    if fault == "http_delay":
        spec["delay"] = "500ms"
    elif fault in {"http_status_error", "dependency_error"}:
        spec["replace"] = {"code": 503}
    elif fault == "http_response_corrupt":
        spec["replace"] = {"body": "chaosatlas-response-corrupted"}
    else:
        spec["abort"] = True
    return {
        "apiVersion": "chaos-mesh.org/v1alpha1",
        "kind": "HTTPChaos",
        "metadata": {"name": name, "namespace": namespace, "labels": {"chaosatlas.dev/owner": "chaosatlas", "chaosatlas.dev/purpose": "runtime-canary"}},
        "spec": spec,
    }


def _effect(fault: str, result: dict[str, Any]) -> dict[str, Any]:
    observation = result.get("observation") if isinstance(result.get("observation"), dict) else {}
    samples = [item for item in observation.get("samples") or [] if isinstance(item, dict)]
    if fault == "http_delay":
        confirmed = any(float(item.get("latency_ms") or 0) >= 400 for item in samples)
    elif fault in {"http_status_error", "dependency_error"}:
        confirmed = any(int(item.get("status_code") or 0) == 503 for item in samples)
    elif fault == "http_response_corrupt":
        confirmed = any("chaosatlas-response-corrupted" in str(item.get("body") or "") for item in samples)
    else:
        confirmed = any(item.get("status_code") is None or item.get("error") for item in samples)
    return {"confirmed": confirmed, "fault": fault, "sample_count": len(samples), "samples": samples}


def run_canary(*, output: Path, context: str, namespace: str, service: str, remote_port: int, path: str, fault: str, approve_live: bool) -> dict[str, Any]:
    if not approve_live:
        raise ValueError("--approve-live is required for a live canary")
    root = output.expanduser().resolve()
    external = runs_root().resolve()
    if root != external and external not in root.parents:
        raise ValueError(f"output must be under external runs root: {external}")
    root.mkdir(parents=True, exist_ok=True)
    action_id = f"http-{fault}-runtime-canary"
    manifest = _manifest(
        fault=fault,
        namespace=namespace,
        name=action_id,
        selector={"app.kubernetes.io/name": service},
        port=remote_port,
        path=path,
    )
    oracle = {
        "kind": "http",
        "service": service,
        "remote_port": remote_port,
        "entrypoint": path,
        "expected_status": 200,
        "expected_body": "OK" if service == "medusa-backend" else None,
        "count": 1,
        "baseline_retry_window_s": 15,
        "observation_window_s": 20,
        "probe_retry_interval_s": 1,
        "timeout_s": 5,
        "local_port": 18900,
    }
    executor = KubernetesLifecycleExecutor(
        root=root,
        namespace=namespace,
        allowed_namespaces={namespace},
        allow_live=True,
        oracle=oracle,
        kube_context=context,
        injection_timeout=30,
        recovery_timeout=60,
        poll_interval=0.5,
    )
    result = executor.run(manifest, action_id=action_id)
    effect = _effect(fault, result)
    canary = {
        "fault_id": fault,
        "target": f"{namespace}/{service}:{remote_port}{path}",
        "result": result,
        "attestation": result.get("attestation") or {"valid": False},
        "effect": effect,
    }
    (root / "canary.json").write_text(json.dumps(canary, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    evidence = {
        "schema_version": "chaosatlas-httpchaos-runtime-evidence-v1",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "kube_context": context,
        "canaries": [{"fault_id": fault, "target": canary["target"], "attestation": canary["attestation"], "effect": effect}],
        "httpchaos_runtime_verified": bool((canary["attestation"] or {}).get("valid") is True and effect["confirmed"] is True),
        "injection_performed": bool((result.get("injection") or {}).get("applied")),
        "read_only_discovery": False,
    }
    (root / "httpchaos-runtime-evidence.json").write_text(json.dumps(evidence, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return {"status": "verified" if evidence["httpchaos_runtime_verified"] else str(result.get("status") or "blocked"), "output": str(root), "fault": fault, "attestation_valid": bool((canary["attestation"] or {}).get("valid")), "effect_confirmed": effect["confirmed"], "injection_performed": evidence["injection_performed"]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--context", default="chaosatlas-apps")
    parser.add_argument("--namespace", default="chaosatlas-medusa")
    parser.add_argument("--service", default="medusa-backend")
    parser.add_argument("--remote-port", type=int, default=9000)
    parser.add_argument("--path", default="/health")
    parser.add_argument("--fault", choices=sorted(HTTP_FAULTS), default="http_status_error")
    parser.add_argument("--approve-live", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = run_canary(output=args.output, context=args.context, namespace=args.namespace, service=args.service, remote_port=args.remote_port, path=args.path, fault=args.fault, approve_live=args.approve_live)
    except (OSError, ValueError, RuntimeError) as exc:
        print(json.dumps({"status": "blocked", "reason": f"{type(exc).__name__}: {exc}"}, ensure_ascii=True))
        return 2
    print(json.dumps(result, ensure_ascii=True))
    return 0 if result["status"] == "verified" else 2


if __name__ == "__main__":
    raise SystemExit(main())
