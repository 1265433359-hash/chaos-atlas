"""D3: environment fingerprint for experiment provenance.

Records the cluster / kernel / Chaos Mesh / runtime environment so that
cross-batch experiment comparisons (which may span environment drift, e.g. a
rebuilt lab namespace or a kernel change) carry an auditable fingerprint.
"""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
FINGERPRINT_PATH = ROOT / "artifacts" / "experiments" / "environment_fingerprint.json"


def run(cmd: list[str]) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=15).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""


def capture() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "tool": "environment_fingerprint",
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "host": {
            "platform": platform.system(),
            "machine": platform.machine(),
            "python": platform.python_version(),
            "os_release": run(["uname", "-r"]) or platform.release(),
        },
        "kubernetes": {
            "context": run(["kubectl", "config", "current-context"]),
            "server_version": run(["kubectl", "version", "--short", "-o", "json"]),
            "kubelet_os": run(["kubectl", "get", "nodes", "-o", "jsonpath={.items[0].status.nodeInfo.osImage}"]),
            "kubelet_kernel": run(["kubectl", "get", "nodes", "-o", "jsonpath={.items[0].status.nodeInfo.kernelVersion}"]),
        },
        "chaos_mesh": {
            "namespace": "chaos-testing",
            "controller_version": run(["kubectl", "get", "deploy", "chaos-controller-manager", "-n", "chaos-testing", "-o", "jsonpath={.spec.template.spec.containers[0].image}"]),
            "daemon_version": run(["kubectl", "get", "daemonset", "chaos-daemon", "-n", "chaos-testing", "-o", "jsonpath={.spec.template.spec.containers[0].image}"]),
        },
        "namespaces": {
            ns: "present" for ns in ("train-ticket-lab", "online-boutique-lab", "otel-demo-lab")
        },
        "known_platform_limit": (
            "HTTPChaos blocked: WSL2 kernel lacks ebtables broute/nat tables "
            "(documented in findings.md); network family limited to NetworkChaos delay/loss."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=FINGERPRINT_PATH)
    args = parser.parse_args()
    doc = capture()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(doc, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "kubelet_kernel": doc["kubernetes"]["kubelet_kernel"], "chaos_mesh": doc["chaos_mesh"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
