"""Run Dify Kubernetes canaries with the real Chatflow API as the oracle.

The application key is read from a local file and used only in memory. Reports
contain status, latency, and response-shape facts, never the key or answer text.
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

from tools.dify_chatflow_oracle import DifyChatflowOracle
from tools.kubernetes_lifecycle_executor import KubernetesLifecycleExecutor


NAMESPACE = "dify-k8s-lab"
CONTEXT = "chaosatlas-dify"
PROXY_SERVICE = "dify-k8s"
PROXY_REMOTE_PORT = 80
PROXY_LOCAL_PORT = 18081


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _manifest(name: str, labels: dict[str, str], fault_family: str, container: str) -> dict[str, Any]:
    spec: dict[str, Any] = {
        "selector": {"namespaces": [NAMESPACE], "labelSelectors": labels},
        "action": "pod-kill" if fault_family == "pod_kill" else "container-kill",
        "mode": "one",
        "duration": "30s",
    }
    if fault_family == "container_kill":
        spec["containerNames"] = [container]
    return {
        "apiVersion": "chaos-mesh.org/v1alpha1",
        "kind": "PodChaos",
        "metadata": {
            "name": name,
            "namespace": NAMESPACE,
            "labels": {"chaosatlas.dev/cleanup-owner": "chaosatlas"},
        },
        "spec": spec,
    }


def _targets() -> list[dict[str, Any]]:
    common = {
        "app.kubernetes.io/instance": "dify-k8s",
        "app.kubernetes.io/name": "dify",
    }
    return [
        {"id": "api", "labels": {**common, "component": "api"}, "container": "api"},
        {"id": "worker", "labels": {**common, "component": "worker"}, "container": "worker"},
        {
            "id": "redis",
            "labels": {
                "app.kubernetes.io/instance": "dify-k8s",
                "app.kubernetes.io/name": "redis",
                "app.kubernetes.io/component": "master",
            },
            "container": "redis",
        },
        {
            "id": "postgresql",
            "labels": {
                "app.kubernetes.io/instance": "dify-k8s",
                "app.kubernetes.io/name": "postgresql",
                "app.kubernetes.io/component": "primary",
            },
            "container": "postgresql",
        },
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--key-file", type=Path, default=Path(r"C:\APP\project\Dify_APIkey.txt"))
    parser.add_argument("--fault-family", choices=["pod_kill", "container_kill"], default="pod_kill")
    parser.add_argument("--only", action="append", choices=["api", "worker", "redis", "postgresql"])
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    try:
        oracle = DifyChatflowOracle(
            api_key_file=args.key_file,
            namespace=NAMESPACE,
            service=PROXY_SERVICE,
            remote_port=PROXY_REMOTE_PORT,
            local_port=PROXY_LOCAL_PORT,
            kube_context=CONTEXT,
        )
    except (OSError, ValueError) as exc:
        print(json.dumps({"status": "failed", "error": type(exc).__name__}))
        return 2

    selected = set(args.only or [item["id"] for item in _targets()])
    results: list[dict[str, Any]] = []
    for target in _targets():
        if target["id"] not in selected:
            continue
        resource_family = args.fault_family.replace("_", "-")
        action_id = f"chat-{target['id']}-{resource_family}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        root = output / target["id"]
        executor = KubernetesLifecycleExecutor(
            root=root,
            namespace=NAMESPACE,
            allowed_namespaces={NAMESPACE},
            allow_live=True,
            oracle={"kind": "dify_chatflow", "service": PROXY_SERVICE, "remote_port": PROXY_REMOTE_PORT},
            hooks={"probe": oracle},
            poll_interval=0.5,
            injection_timeout=45.0,
            recovery_timeout=180.0,
            kube_context=CONTEXT,
        )
        print(f"[start] {target['id']} action={action_id}", flush=True)
        try:
            result = executor.run(
                _manifest(action_id, target["labels"], args.fault_family, target["container"]),
                action_id=action_id,
            )
            item = {
                "target": target["id"],
                "action_id": action_id,
                "status": result.get("status"),
                "outcome_status": result.get("outcome_status"),
                "attestation": result.get("attestation"),
                "errors": result.get("errors") or [],
                "result_file": str(root / "runtime" / f"{action_id}.json"),
            }
        except Exception as exc:
            item = {
                "target": target["id"],
                "action_id": action_id,
                "status": "runner_error",
                "errors": [f"{type(exc).__name__}: {exc}"],
            }
        results.append(item)
        print(json.dumps(item, ensure_ascii=True), flush=True)

    passed = [
        item for item in results
        if item.get("status") == "executed"
        and (item.get("attestation") or {}).get("valid") is True
    ]
    summary = {
        "schema_version": "chaosatlas-dify-k8s-chat-canaries-v1",
        "status": "passed" if len(passed) == len(results) else "failed",
        "started_at": _now(),
        "context": CONTEXT,
        "namespace": NAMESPACE,
        "fault_family": args.fault_family,
        "targets": results,
        "passed": len(passed),
        "total": len(results),
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": summary["status"], "passed": len(passed), "total": len(results)}), flush=True)
    return 0 if summary["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
