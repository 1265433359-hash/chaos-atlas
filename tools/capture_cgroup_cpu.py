"""Capture cgroup-v2 CPU counters from a selected Kubernetes Pod."""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def run(args: list[str], timeout: int = 15) -> tuple[int, str, str]:
    completed = subprocess.run(
        ["kubectl", *args],
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return completed.returncode, completed.stdout, completed.stderr


def choose_pod(namespace: str, selector: str) -> str:
    code, stdout, stderr = run(["get", "pods", "-n", namespace, "-l", selector, "-o", "json"])
    if code != 0:
        raise RuntimeError((stderr or stdout).strip())
    data = json.loads(stdout)
    pods = data.get("items", [])
    if not pods:
        raise RuntimeError(f"no Pod matched {namespace}/{selector}")
    ready = [pod for pod in pods if any(
        condition.get("type") == "Ready" and condition.get("status") == "True"
        for condition in pod.get("status", {}).get("conditions", [])
    )]
    if len(ready) > 1:
        raise RuntimeError(
            f"selector matched multiple Ready Pods in {namespace}: "
            + ", ".join(pod.get("metadata", {}).get("name", "<unknown>") for pod in ready)
        )
    return (ready or pods)[0]["metadata"]["name"]


def capture(namespace: str, pod: str, container: str | None) -> dict[str, Any]:
    command = ["sh", "-c", "cat /sys/fs/cgroup/cpu.stat; echo __CPU_MAX__; cat /sys/fs/cgroup/cpu.max"]
    args = ["exec", "-n", namespace, pod]
    if container:
        args.extend(["-c", container])
    args.extend(["--", *command])
    code, stdout, stderr = run(args)
    if code != 0:
        return {"error": (stderr or stdout).strip(), "pod": pod}
    before, _, cpu_max = stdout.partition("__CPU_MAX__")
    counters: dict[str, int] = {}
    for line in before.splitlines():
        key, separator, value = line.strip().partition(" ")
        if separator and value.isdigit():
            counters[key] = int(value)
    return {
        "pod": pod,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "cpu_stat": counters,
        "cpu_max": cpu_max.strip(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--namespace", required=True)
    parser.add_argument("--selector", required=True)
    parser.add_argument("--container")
    parser.add_argument("--samples", type=int, default=1)
    parser.add_argument("--interval", type=float, default=2.0)
    parser.add_argument("--phase", default="unknown")
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    samples: list[dict[str, Any]] = []
    for index in range(max(1, args.samples)):
        try:
            pod = choose_pod(args.namespace, args.selector)
            sample = capture(args.namespace, pod, args.container)
        except (RuntimeError, json.JSONDecodeError) as exc:
            sample = {"error": str(exc)}
        sample["phase"] = args.phase
        sample["sample"] = index + 1
        samples.append(sample)
        if index + 1 < max(1, args.samples):
            time.sleep(max(0.1, args.interval))

    report = {
        "schema_version": 1,
        "tool": "capture_cgroup_cpu",
        "namespace": args.namespace,
        "selector": args.selector,
        "phase": args.phase,
        "samples": samples,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=True))
    return 0 if not any("error" in sample for sample in samples) else 2


if __name__ == "__main__":
    raise SystemExit(main())
