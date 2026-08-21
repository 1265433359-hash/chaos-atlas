"""Run one bounded Sock Shop PodKill with synchronized business/Endpoint sampling."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import socket
import subprocess
import sys
import time
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

import yaml

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.sock_shop_disambiguation import summarize_disambiguation_timeline


NAMESPACE = "sock-shop-lab"
SERVICE = "front-end"
LOCAL_PORT = 18088
MAX_DURATION_S = 40.0
INTERVAL_S = 0.5


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _kubectl(args: list[str], *, input_text: str | None = None, timeout: int = 15) -> tuple[int, str, str]:
    completed = subprocess.run(
        ["kubectl", *args],
        input=input_text,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )
    return completed.returncode, completed.stdout or "", completed.stderr or ""


def _kubectl_json(args: list[str]) -> dict[str, Any]:
    code, stdout, stderr = _kubectl([*args, "-o", "json"])
    if code != 0:
        raise RuntimeError(f"kubectl {' '.join(args)} failed: {(stderr or stdout).strip() or code}")
    value = json.loads(stdout)
    if not isinstance(value, dict):
        raise RuntimeError(f"kubectl {' '.join(args)} returned a non-object JSON value")
    return value


def _wait_port(port: int, process: subprocess.Popen[str], timeout: float = 15.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("kubectl port-forward exited before becoming ready")
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return
        except OSError:
            time.sleep(0.2)
    raise RuntimeError("port-forward did not become ready")


def _business_sample() -> dict[str, Any]:
    observed_at = _now()
    try:
        with urlopen(f"http://127.0.0.1:{LOCAL_PORT}/", timeout=2.0) as response:
            body = response.read(256)
            return {"observed_at": observed_at, "status_code": response.status, "contract_ok": response.status == 200 and bool(body)}
    except (OSError, URLError, TimeoutError) as exc:
        return {"observed_at": observed_at, "status_code": None, "error": type(exc).__name__, "contract_ok": False}


def _capture_sample() -> dict[str, Any]:
    business = _business_sample()
    pods = _kubectl_json(["get", "pods", "-n", NAMESPACE, "-l", "name=front-end"])
    endpoints = _kubectl_json(["get", "endpoints", SERVICE, "-n", NAMESPACE])
    return {"observed_at": business["observed_at"], "business": business, "pods": pods, "endpoints": endpoints}


def run(output: Path) -> dict[str, Any]:
    output = Path(output)
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"output {output} is not empty")
    output.mkdir(parents=True, exist_ok=True)
    mutation = yaml.safe_load(Path("artifacts/sock-shop/pilot/front-end-podkill-r1/mutation.yaml").read_text(encoding="utf-8"))
    mutation["metadata"]["name"] = "chaosatlas-sock-shop-front-end-podkill-r2"
    mutation["metadata"]["labels"]["chaosatlas.dev/pilot"] = "sock-shop-front-end-podkill-r2"
    mutation_text = yaml.safe_dump(mutation, sort_keys=False, allow_unicode=False)
    (output / "mutation.yaml").write_text(mutation_text, encoding="utf-8")
    name = mutation["metadata"]["name"]
    port_forward = subprocess.Popen(
        ["kubectl", "port-forward", f"svc/{SERVICE}", f"{LOCAL_PORT}:80", "-n", NAMESPACE],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    apply_at = _now()
    samples: list[dict[str, Any]] = []
    cleanup_error: str | None = None
    before: dict[str, Any] = {}
    injection_status: dict[str, Any] = {}
    try:
        _wait_port(LOCAL_PORT, port_forward)
        before = {
            "captured_at": _now(),
            "pods": _kubectl_json(["get", "pods", "-n", NAMESPACE, "-l", "name=front-end"]),
            "endpoints": _kubectl_json(["get", "endpoints", SERVICE, "-n", NAMESPACE]),
        }
        (output / "before.json").write_text(json.dumps(before, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
        code, stdout, stderr = _kubectl(["apply", "-f", "-"], input_text=mutation_text)
        if code != 0:
            raise RuntimeError(f"PodChaos apply failed: {(stderr or stdout).strip() or code}")
        apply_at = _now()
        for _ in range(20):
            injection_status = _kubectl_json(["get", "podchaos", name, "-n", NAMESPACE])
            if any(
                isinstance(condition, dict)
                and condition.get("type") == "AllInjected"
                and condition.get("status") == "True"
                for condition in (injection_status.get("status") or {}).get("conditions", [])
            ):
                break
            time.sleep(0.5)
        else:
            raise RuntimeError("PodChaos injection was not confirmed within the bounded gate")
        deadline = time.monotonic() + MAX_DURATION_S
        with (output / "timeline.jsonl").open("w", encoding="utf-8") as stream:
            while time.monotonic() < deadline:
                sample = _capture_sample()
                samples.append(sample)
                stream.write(json.dumps(sample, ensure_ascii=True, sort_keys=True) + "\n")
                stream.flush()
                time.sleep(INTERVAL_S)
    finally:
        code, stdout, stderr = _kubectl(["delete", "podchaos", name, "-n", NAMESPACE, "--ignore-not-found=true"])
        if code != 0:
            cleanup_error = (stderr or stdout).strip() or f"kubectl delete returned {code}"
        for _ in range(20):
            code, _, _ = _kubectl(["get", "podchaos", name, "-n", NAMESPACE])
            if code != 0:
                break
            time.sleep(0.5)
        if port_forward.poll() is None:
            port_forward.terminate()
            try:
                port_forward.wait(timeout=5)
            except subprocess.TimeoutExpired:
                port_forward.kill()
        (output / "port-forward.txt").write_text(
            (port_forward.stdout.read() if port_forward.stdout else "") + (port_forward.stderr.read() if port_forward.stderr else ""),
            encoding="utf-8",
        )
    finished_at = _now()
    after = {"captured_at": finished_at, "pods": _kubectl_json(["get", "pods", "-n", NAMESPACE, "-l", "name=front-end"]), "endpoints": _kubectl_json(["get", "endpoints", SERVICE, "-n", NAMESPACE])}
    (output / "after.json").write_text(json.dumps(after, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    summary = summarize_disambiguation_timeline(pod_before=before["pods"], samples=samples)
    result = {
        "schema_version": "chaosatlas-sock-shop-disambiguation-runtime-v1",
        "round_id": "pilot-r3-disambiguation-r2",
        "namespace": NAMESPACE,
        "target": "deployment:front-end",
        "mutation_name": name,
        "window": {"start": apply_at, "end": finished_at},
        "injection_status": injection_status,
        "sample_count": len(samples),
        "summary": summary,
        "cleanup_error": cleanup_error,
        "residual_podchaos": _kubectl_json(["get", "podchaos", "-n", NAMESPACE]).get("items", []) if _kubectl(["get", "podchaos", "-n", NAMESPACE])[0] == 0 else [],
    }
    (output / "result.json").write_text(json.dumps(result, indent=2, ensure_ascii=True, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.output), indent=2, ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
