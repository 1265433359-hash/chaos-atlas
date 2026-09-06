"""Run api_server_delay against an owned disposable Minikube profile."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

from scripts.runtime_env import runtime_env
from chaosatlas.workspace import runs_root


def _owned_name(value: str, label: str, prefix: str) -> str:
    value = str(value or "").strip()
    if not value.startswith(prefix) or len(value) > 63:
        raise ValueError(f"{label} must start with {prefix!r} and be at most 63 characters")
    return value


def build_plan(*, repo: Path, profile: str, namespace: str, output: Path, image: str) -> list[dict[str, Any]]:
    """Build the explicit command plan; no command mutates an unowned target."""
    profile = _owned_name(profile, "profile", "chaosatlas-")
    namespace = _owned_name(namespace, "namespace", "chaosatlas-run-")
    repo = repo.resolve()
    output = output.resolve()
    external_runs_root = runs_root().resolve()
    if output != external_runs_root and external_runs_root not in output.parents:
        raise ValueError(f"output must be under external runs root: {external_runs_root}")
    image = str(image or "").strip()
    if not image:
        raise ValueError("image is required")
    manifest = output / "resource-canary.yaml"
    generated_profile = output / "profile.json"
    run_output = output / "run"
    context = profile
    return [
        {"name": "start", "command": ["minikube", "start", "-p", profile, "--driver=docker", "--cpus=2", "--memory=4096", "--kubernetes-version=v1.35.1"]},
        {"name": "load-image", "command": ["minikube", "-p", profile, "image", "load", image]},
        {"name": "apply-fixture", "command": ["kubectl", "--context", context, "apply", "-f", str(manifest)]},
        {"name": "rollout", "command": ["kubectl", "--context", context, "-n", namespace, "rollout", "status", "deployment/resource-canary", "--timeout=180s"]},
        {"name": "run", "command": [sys.executable, str(repo / "tools" / "chaosatlas.py"), "run", "--profile", str(generated_profile), "--mode", "live", "--approve-live", "--kube-context", context, "--output", str(run_output), "--seed", "20260828"]},
        {"name": "delete", "command": ["minikube", "delete", "-p", profile], "always": True},
    ]


def _fixture(namespace: str, image: str, *, command: list[str] | None = None, args: list[str] | None = None) -> str:
    command_yaml = "" if not command else "\n          command:\n" + "".join(f"            - {json.dumps(item)}\n" for item in command)
    args_yaml = "" if not args else "\n          args:\n" + "".join(f"            - {json.dumps(item)}\n" for item in args)
    return f'''apiVersion: v1
kind: Namespace
metadata:
  name: {namespace}
  labels:
    chaosatlas.dev/owner: chaosatlas
    chaosatlas.dev/purpose: api-server-delay-canary
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: resource-canary
  namespace: {namespace}
  labels:
    app: resource-canary
spec:
  replicas: 1
  selector:
    matchLabels:
      app: resource-canary
  template:
    metadata:
      labels:
        app: resource-canary
    spec:
      containers:
        - name: canary
          image: {image}
          imagePullPolicy: IfNotPresent
{command_yaml}{args_yaml}
          ports:
            - name: http
              containerPort: 8080
          readinessProbe:
            httpGet:
              path: /
              port: 8080
            initialDelaySeconds: 1
            periodSeconds: 2
---
apiVersion: v1
kind: Service
metadata:
  name: resource-canary
  namespace: {namespace}
spec:
  selector:
    app: resource-canary
  ports:
    - name: http
      port: 80
      targetPort: 8080
'''


def _profile(namespace: str, profile: str, *, expected_body: str = "chaosatlas-resource-canary") -> dict[str, Any]:
    return {
        "schema_version": "chaosatlas-project-profile-v1",
        "project_id": "resource-canary-api-delay",
        "project_commit": "0" * 40,
        "revision_kind": "fixture",
        "source": {"manifest_roots": ["workloads/resource-canary"], "source_roots": ["workloads/resource-canary"]},
        "namespace_policy": {"allowed_namespaces": [namespace], "isolation_required": True, "disposable_cluster": True, "cluster_profile": profile},
        "business_oracles": [{"id": "resource-canary-http", "kind": "http", "service": "resource-canary", "remote_port": 80, "entrypoint": "/", "success_contract": "http_200_and_expected_body", "expected_status": 200, "expected_body": expected_body, "timeout_s": 5, "count": 3, "baseline_retry_window_s": 15, "observation_window_s": 30, "probe_retry_interval_s": 1}],
        "observability": {"logs": {"enabled": True}, "events": {"enabled": True}},
        "recovery": {"deadline_s": 120, "require_business_probe": True, "require_cleanup": True},
        "cleanup": {"owner": "chaosatlas", "must_be_empty": True},
        "sensitive_data_policy": {"allow_redacted_placeholders": True, "redact_fields": ["password", "secret", "token", "authorization", "private_key"]},
        "fault_support": {"api_server_delay": {"status": "supported", "reason": "owned disposable control-plane canary"}},
        "fault_defaults": {"api_server_delay": {"latency_ms": 100}},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--profile", default="chaosatlas-api-delay-20260828")
    parser.add_argument("--namespace", default="chaosatlas-run-api-delay")
    parser.add_argument("--image", default="chaosatlas/resource-canary:20260827")
    parser.add_argument("--expected-body", default="chaosatlas-resource-canary")
    parser.add_argument("--command", action="append", help="optional container command entry; repeat for multiple entries")
    parser.add_argument("--args", dest="container_args", action="append", help="optional container argument; repeat for multiple entries")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--approve-live", action="store_true")
    args = parser.parse_args(argv)
    if not args.approve_live:
        parser.error("--approve-live is required for control-plane mutation")
    repo = args.repo.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    plan = build_plan(repo=repo, profile=args.profile, namespace=args.namespace, output=output, image=args.image)
    (output / "resource-canary.yaml").write_text(_fixture(args.namespace, args.image, command=args.command, args=args.container_args), encoding="utf-8")
    (output / "profile.json").write_text(json.dumps(_profile(args.namespace, args.profile, expected_body=args.expected_body), indent=2) + "\n", encoding="utf-8")
    exit_codes: dict[str, int] = {}
    failed = False
    for item in plan:
        if failed and not item.get("always"):
            continue
        print("+", " ".join(item["command"]))
        code = subprocess.run(item["command"], cwd=str(repo), check=False, env=runtime_env()).returncode
        exit_codes[item["name"]] = code
        if code != 0 and not item.get("always"):
            failed = True
    (output / "lifecycle-exit-codes.json").write_text(json.dumps(exit_codes, indent=2) + "\n", encoding="utf-8")
    return 0 if not failed and exit_codes.get("delete") == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
