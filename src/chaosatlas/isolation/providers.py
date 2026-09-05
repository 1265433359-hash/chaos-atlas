"""Built-in Kubernetes and Minikube isolation providers."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable

from chaosatlas.isolation.blueprint import compile_blueprint, derive_l2_blueprint


Runner = Callable[..., tuple[int, str, str]]


def _is_not_found(error: str | None) -> bool:
    """Accept the spelling variants emitted by kubectl and test doubles."""
    normalized = re.sub(r"[^a-z]", "", str(error or "").lower())
    return "notfound" in normalized


def default_kubectl_runner(args: list[str], *, timeout: int = 60, input_text: str | None = None, env: dict[str, str] | None = None) -> tuple[int, str, str]:
    try:
        result = subprocess.run(["kubectl", *args], input=input_text, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, check=False, env=env)
        return result.returncode, result.stdout or "", result.stderr or ""
    except (OSError, subprocess.SubprocessError) as exc:
        return 124, "", f"{type(exc).__name__}: {exc}"


def default_minikube_runner(args: list[str], *, timeout: int = 900, input_text: str | None = None, env: dict[str, str] | None = None) -> tuple[int, str, str]:
    try:
        result = subprocess.run(["minikube", *args], input=input_text, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, check=False, env=env)
        return result.returncode, result.stdout or "", result.stderr or ""
    except (OSError, subprocess.SubprocessError) as exc:
        return 124, "", f"{type(exc).__name__}: {exc}"


class ProviderRegistry:
    def __init__(self, providers: list[Any] | None = None) -> None:
        self._providers: dict[str, Any] = {}
        for provider in providers or []:
            self.register(provider)

    def register(self, provider: Any) -> None:
        name = str(getattr(provider, "name", ""))
        if not name or name in self._providers:
            raise ValueError(f"invalid or duplicate isolation provider: {name}")
        self._providers[name] = provider

    def get(self, name: str) -> Any:
        try:
            return self._providers[name]
        except KeyError as exc:
            raise ValueError(f"unknown isolation provider: {name}") from exc


class KubernetesIsolationProvider:
    def __init__(self, *, name: str, level: str, runner: Runner | None = None) -> None:
        self.name = name
        self.level = level
        self.runner = runner or default_kubectl_runner

    def supports(self, plan: dict[str, Any]) -> bool:
        return plan.get("provider") == self.name and plan.get("effective_isolation") == self.level

    def _args(self, plan: dict[str, Any], args: list[str]) -> list[str]:
        context = str(plan.get("kube_context") or "")
        return ["--context", context, *args] if context else list(args)

    def _run(self, plan: dict[str, Any], args: list[str], *, timeout: int = 60, input_text: str | None = None) -> tuple[int, str, str]:
        return self.runner(self._args(plan, args), timeout=timeout, input_text=input_text)

    def _json(self, plan: dict[str, Any], args: list[str]) -> tuple[dict[str, Any] | None, str | None]:
        code, stdout, stderr = self._run(plan, [*args, "-o", "json"])
        if code != 0:
            return None, (stderr or stdout).strip() or f"kubectl exit {code}"
        try:
            value = json.loads(stdout)
        except json.JSONDecodeError as exc:
            return None, f"invalid kubectl JSON: {exc}"
        return (value, None) if isinstance(value, dict) else (None, "kubectl response is not an object")

    def preflight(self, plan: dict[str, Any]) -> list[str]:
        if plan.get("status") != "ready":
            return list(plan.get("blockers") or ["plan_not_ready"])
        if plan.get("effective_isolation") != self.level:
            return ["provider_isolation_level_mismatch"]
        if plan.get("mode") == "adopted-test-replica":
            _, error = self._json(plan, ["get", "namespace", str(plan.get("source_namespace") or "")])
            return [f"source_namespace_unavailable:{error}"] if error else []
        return []

    @staticmethod
    def _namespace_manifest(namespace: str, labels: dict[str, str]) -> dict[str, Any]:
        return {"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": namespace, "labels": labels}}

    @staticmethod
    def _guard_resources(namespace: str, labels: dict[str, str], budget: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            {"apiVersion": "v1", "kind": "ResourceQuota", "metadata": {"name": "chaosatlas-budget", "namespace": namespace, "labels": labels}, "spec": {"hard": {"requests.cpu": str(budget.get("cpu") or "2"), "requests.memory": str(budget.get("memory") or "2Gi"), "pods": str(budget.get("pods") or 20)}}},
            {"apiVersion": "v1", "kind": "LimitRange", "metadata": {"name": "chaosatlas-defaults", "namespace": namespace, "labels": labels}, "spec": {"limits": [{"type": "Container", "default": {"cpu": "500m", "memory": "512Mi"}, "defaultRequest": {"cpu": "10m", "memory": "16Mi"}}]}},
            {"apiVersion": "networking.k8s.io/v1", "kind": "NetworkPolicy", "metadata": {"name": "chaosatlas-boundary", "namespace": namespace, "labels": labels}, "spec": {"podSelector": {}, "policyTypes": ["Ingress", "Egress"], "ingress": [{"from": [{"namespaceSelector": {"matchLabels": {"kubernetes.io/metadata.name": namespace}}}]}], "egress": [{"to": [{"namespaceSelector": {"matchLabels": {"kubernetes.io/metadata.name": namespace}}}]}, {"to": [{"namespaceSelector": {"matchLabels": {"kubernetes.io/metadata.name": "kube-system"}}}], "ports": [{"protocol": "UDP", "port": 53}, {"protocol": "TCP", "port": 53}]}]}},
        ]

    def prepare(self, plan: dict[str, Any], lease: dict[str, Any], mutate: Callable[[str, dict[str, Any]], None]) -> None:
        if plan.get("mode") == "adopted-test-replica":
            namespace = str(plan["source_namespace"])
            value, error = self._json(plan, ["get", "namespace", namespace])
            if error or value is None:
                raise RuntimeError(error or "adopted namespace unavailable")
            mutate("register_resource", {"kind": "Namespace", "namespace": None, "name": namespace, "expected_uid": str((value.get("metadata") or {}).get("uid") or ""), "actual_uid": str((value.get("metadata") or {}).get("uid") or ""), "cleanup_policy": "release_only"})
            return
        namespace = str(lease.get("target_name") or "")
        labels = {str(k): str(v) for k, v in (lease.get("owner_labels") or {}).items()}
        mutate("register_resource", {"kind": "Namespace", "namespace": None, "name": namespace, "expected_uid": None, "actual_uid": None, "cleanup_policy": "delete"})
        manifest = self._namespace_manifest(namespace, labels)
        code, stdout, stderr = self._run(plan, ["apply", "-f", "-"], input_text=json.dumps(manifest))
        if code != 0:
            raise RuntimeError((stderr or stdout).strip() or "namespace apply failed")
        namespace_value, error = self._json(plan, ["get", "namespace", namespace])
        if error or namespace_value is None:
            raise RuntimeError(error or "created namespace unavailable")
        mutate("update_resource_uid", {"kind": "Namespace", "namespace": None, "name": namespace, "actual_uid": str((namespace_value.get("metadata") or {}).get("uid") or "")})

        blueprint = plan.get("blueprint") if isinstance(plan.get("blueprint"), dict) else None
        if blueprint is None and self.level == "L2":
            blueprint = derive_l2_blueprint(plan.get("target") or {}, str(plan.get("project_id") or "project"))
        if blueprint is None:
            raise RuntimeError("approved blueprint is required")
        resources = [*self._guard_resources(namespace, labels, plan.get("resource_budget") or {}), *compile_blueprint(blueprint, namespace=namespace, owner_labels=labels)]
        for resource in resources:
            kind = str(resource.get("kind") or "")
            name = str((resource.get("metadata") or {}).get("name") or "")
            mutate("register_resource", {"kind": kind, "namespace": namespace, "name": name, "expected_uid": None, "actual_uid": None, "cleanup_policy": "namespace"})
            code, stdout, stderr = self._run(plan, ["apply", "-f", "-"], input_text=json.dumps(resource))
            if code != 0:
                raise RuntimeError((stderr or stdout).strip() or f"{kind}/{name} apply failed")
            value, error = self._json(plan, ["get", kind.lower(), name, "-n", namespace])
            if error or value is None:
                raise RuntimeError(error or f"{kind}/{name} unavailable after apply")
            mutate("update_resource_uid", {"kind": kind, "namespace": namespace, "name": name, "actual_uid": str((value.get("metadata") or {}).get("uid") or "")})

    def verify_ready(self, plan: dict[str, Any], lease: dict[str, Any]) -> dict[str, Any]:
        namespace = str(plan.get("source_namespace") if plan.get("mode") == "adopted-test-replica" else lease.get("target_name") or "")
        timeout_s = max(1, min(int((plan.get("config") or {}).get("ready_timeout_s") or 180), 600))
        deadline = time.monotonic() + timeout_s
        last: dict[str, Any] = {"namespace": False, "pod_count": 0, "all_pods_ready": False}
        last_error = "namespace missing"
        while True:
            namespace_value, error = self._json(plan, ["get", "namespace", namespace])
            if error or namespace_value is None:
                last_error = error or "namespace missing"
            else:
                pods, pod_error = self._json(plan, ["get", "pods", "-n", namespace])
                items = [item for item in (pods or {}).get("items") or [] if isinstance(item, dict)]
                running = [item for item in items if str((item.get("status") or {}).get("phase") or "") == "Running"]
                failed = [item for item in items if str((item.get("status") or {}).get("phase") or "") == "Failed"]
                ready = bool(running) and not failed and all(
                    not (item.get("metadata") or {}).get("deletionTimestamp")
                    and any(condition.get("type") == "Ready" and condition.get("status") == "True" for condition in (item.get("status") or {}).get("conditions") or [])
                    for item in running
                )
                last = {"namespace": True, "pod_count": len(items), "all_pods_ready": ready}
                last_error = pod_error or ("" if ready else "no Ready workload Pods")
                if ready and not pod_error:
                    return {"status": "verified", "checks": last, "errors": []}
            if time.monotonic() >= deadline:
                return {"status": "blocked", "checks": last, "errors": [last_error]}
            time.sleep(1)

    def cleanup(self, plan: dict[str, Any], lease: dict[str, Any]) -> dict[str, Any]:
        if plan.get("mode") == "adopted-test-replica":
            return {"status": "released", "deleted": False, "reason": "adopted namespace is never deleted"}
        namespace = str(lease.get("target_name") or "")
        if not re.fullmatch(r"ca-l[12]-[a-z0-9-]+", namespace):
            return {"status": "blocked", "reason": "unsafe namespace identity"}
        expected = next((item for item in lease.get("resources") or [] if item.get("kind") == "Namespace" and item.get("name") == namespace), None)
        value, error = self._json(plan, ["get", "namespace", namespace])
        if _is_not_found(error):
            return {"status": "released", "deleted": False, "already_absent": True}
        metadata = (value or {}).get("metadata") or {}
        labels = metadata.get("labels") or {}
        if not expected or not expected.get("actual_uid") or str(metadata.get("uid") or "") != str(expected.get("actual_uid")):
            return {"status": "blocked", "reason": "cleanup_blocked_identity_mismatch"}
        if labels.get("chaosatlas.dev/lease-id") != lease.get("lease_id") or labels.get("chaosatlas.dev/managed") != "true":
            return {"status": "blocked", "reason": "cleanup_blocked_ownership_mismatch"}
        code, stdout, stderr = self._run(plan, ["delete", "namespace", namespace, "--wait=false"])
        return {"status": "released" if code == 0 else "blocked", "deleted": code == 0, "reason": None if code == 0 else (stderr or stdout).strip()}

    def verify_absent(self, plan: dict[str, Any], lease: dict[str, Any]) -> dict[str, Any]:
        if plan.get("mode") == "adopted-test-replica":
            namespace = str(plan.get("source_namespace") or "")
            value, error = self._json(plan, ["get", "namespace", namespace])
            expected = next((item for item in lease.get("resources") or [] if item.get("cleanup_policy") == "release_only"), {})
            if not expected:
                return {"confirmed": True, "adoption_not_started": True, "errors": []}
            unchanged = value is not None and not error and str((value.get("metadata") or {}).get("uid") or "") == str(expected.get("actual_uid") or "")
            return {"confirmed": unchanged, "adopted_namespace_unchanged": unchanged, "errors": [] if unchanged else [error or "adopted namespace identity changed"]}
        namespace = str(lease.get("target_name") or "")
        last_error = ""
        for _ in range(30):
            value, error = self._json(plan, ["get", "namespace", namespace])
            if value is None and _is_not_found(error):
                return {"confirmed": True, "namespace_absent": True, "errors": []}
            last_error = error or "namespace still exists"
            time.sleep(0.5)
        return {"confirmed": False, "namespace_absent": False, "errors": [last_error]}


class MinikubeIsolationProvider:
    name = "minikube-l3"

    def __init__(self, *, root: str | Path, runner: Runner | None = None, cache_seed_root: str | Path | None = None) -> None:
        self.root = Path(root).expanduser().resolve()
        self.runner = runner or default_minikube_runner
        self.cache_seed_root = Path(cache_seed_root).expanduser().resolve() if cache_seed_root else (Path.home() / ".minikube" / "cache" / "preloaded-tarball").resolve()

    def supports(self, plan: dict[str, Any]) -> bool:
        return plan.get("provider") == self.name and plan.get("effective_isolation") == "L3"

    def _paths(self, lease: dict[str, Any]) -> tuple[Path, Path, Path, Path]:
        profile = str(lease.get("target_name") or "")
        minikube_home = (self.root / "minikube").resolve()
        kubeconfig = (self.root / "kubeconfigs" / f"{lease['lease_id']}.config").resolve()
        profile_dir = (minikube_home / ".minikube" / "profiles" / profile).resolve()
        machine_dir = (minikube_home / ".minikube" / "machines" / profile).resolve()
        for value in (minikube_home, kubeconfig, profile_dir, machine_dir):
            if self.root not in value.parents:
                raise RuntimeError("unsafe Minikube runtime path")
        return minikube_home, kubeconfig, profile_dir, machine_dir

    def _env(self, lease: dict[str, Any], *, create: bool = True) -> dict[str, str]:
        values = dict(os.environ)
        minikube_home, kubeconfig, _, _ = self._paths(lease)
        values["MINIKUBE_HOME"] = str(minikube_home)
        values["KUBECONFIG"] = str(kubeconfig)
        if create:
            minikube_home.mkdir(parents=True, exist_ok=True)
            kubeconfig.parent.mkdir(parents=True, exist_ok=True)
        return values

    def _seed_public_cache(self, lease: dict[str, Any], mutate: Callable[[str, dict[str, Any]], None]) -> None:
        """Reuse only immutable public preload tarballs, never profiles or credentials."""
        if not self.cache_seed_root.is_dir():
            return
        minikube_home, _, _, _ = self._paths(lease)
        destination_root = (minikube_home / ".minikube" / "cache" / "preloaded-tarball").resolve()
        for source in sorted(self.cache_seed_root.glob("preloaded-images-k8s-*.tar.lz4")):
            if not source.is_file() or source.stat().st_size == 0:
                continue
            destination = (destination_root / source.name).resolve()
            if self.root not in destination.parents:
                raise RuntimeError("unsafe Minikube cache destination")
            mutate("register_resource", {"kind": "ExternalPath", "namespace": None, "name": str(destination), "expected_uid": None, "actual_uid": None, "cleanup_policy": "delete_file"})
            destination.parent.mkdir(parents=True, exist_ok=True)
            try:
                os.link(source, destination)
            except OSError:
                shutil.copy2(source, destination)

    def _run(self, args: list[str], lease: dict[str, Any], timeout: int = 900) -> tuple[int, str, str]:
        return self.runner(args, timeout=timeout, env=self._env(lease))

    def preflight(self, plan: dict[str, Any]) -> list[str]:
        if plan.get("status") != "ready" or plan.get("effective_isolation") != "L3":
            return list(plan.get("blockers") or ["provider_isolation_level_mismatch"])
        return []

    def prepare(self, plan: dict[str, Any], lease: dict[str, Any], mutate: Callable[[str, dict[str, Any]], None]) -> None:
        profile = str(lease.get("target_name") or "")
        if not re.fullmatch(r"ca-l3-[a-z0-9-]+", profile) or profile in {"minikube", "chaosatlas-apps"}:
            raise RuntimeError("unsafe Minikube profile identity")
        mutate("register_profile", {"provider": "minikube", "name": profile, "state": "planned"})
        _, kubeconfig, profile_dir, machine_dir = self._paths(lease)
        mutate("register_resource", {"kind": "ExternalPath", "namespace": None, "name": str(kubeconfig), "expected_uid": None, "actual_uid": None, "cleanup_policy": "delete_file"})
        mutate("register_resource", {"kind": "ExternalPath", "namespace": None, "name": str(profile_dir), "expected_uid": None, "actual_uid": None, "cleanup_policy": "provider_delete"})
        mutate("register_resource", {"kind": "ExternalPath", "namespace": None, "name": str(machine_dir), "expected_uid": None, "actual_uid": None, "cleanup_policy": "provider_delete"})
        self._seed_public_cache(lease, mutate)
        budget = plan.get("resource_budget") or {}
        driver = str(((plan.get("blueprint") or {}).get("driver")) or "docker")
        runtime = str(((plan.get("blueprint") or {}).get("container_runtime")) or "containerd")
        if driver not in {"docker", "hyperv"} or runtime not in {"containerd", "docker"}:
            raise RuntimeError("unsupported Minikube driver or container runtime")
        code, stdout, stderr = self._run(["start", "--profile", profile, "--driver", driver, "--container-runtime", runtime, "--cpus", str(budget.get("cpu") or 2), "--memory", str(budget.get("memory") or "4096mb"), "--disk-size", str(budget.get("disk") or "10g")], lease)
        if code != 0:
            raise RuntimeError((stderr or stdout).strip() or "minikube start failed")
        mutate("update_profile", {"provider": "minikube", "name": profile, "state": "ready"})

    def verify_ready(self, plan: dict[str, Any], lease: dict[str, Any]) -> dict[str, Any]:
        profile = str(lease.get("target_name") or "")
        code, stdout, stderr = self._run(["status", "--profile", profile, "--output", "json"], lease, timeout=60)
        ready = code == 0 and stdout.lower().count("running") >= 2
        return {"status": "verified" if ready else "blocked", "checks": {"profile": profile, "status_running": ready}, "errors": [] if ready else [(stderr or stdout).strip() or "minikube is not Ready"]}

    def cleanup(self, plan: dict[str, Any], lease: dict[str, Any]) -> dict[str, Any]:
        profile = str(lease.get("target_name") or "")
        registered = any(item.get("name") == profile and item.get("provider") == "minikube" for item in lease.get("external_profiles") or [])
        if not registered or not re.fullmatch(r"ca-l3-[a-z0-9-]+", profile) or profile in {"minikube", "chaosatlas-apps"}:
            return {"status": "blocked", "reason": "cleanup_blocked_profile_identity"}
        code, stdout, stderr = self._run(["delete", "--profile", profile], lease)
        if code != 0:
            status_code, status_out, status_err = self._run(["status", "--profile", profile, "--output", "json"], lease, timeout=60)
            if status_code == 0:
                return {"status": "blocked", "reason": (stderr or stdout or status_err or status_out).strip()}
        for item in lease.get("resources") or []:
            if item.get("kind") != "ExternalPath" or item.get("cleanup_policy") != "delete_file":
                continue
            path = Path(str(item.get("name") or "")).resolve()
            if self.root not in path.parents:
                return {"status": "blocked", "reason": "cleanup_blocked_external_path"}
            if path.is_file() or path.is_symlink():
                path.unlink()
        return {"status": "released", "reason": None, "already_absent": code != 0}

    def verify_absent(self, plan: dict[str, Any], lease: dict[str, Any]) -> dict[str, Any]:
        profile = str(lease.get("target_name") or "")
        code, stdout, stderr = self._run(["status", "--profile", profile, "--output", "json"], lease, timeout=60)
        _, kubeconfig, profile_dir, machine_dir = self._paths(lease)
        profile_absent = code != 0 and not profile_dir.exists() and not machine_dir.exists()
        kubeconfig_absent = not kubeconfig.exists()
        lease_files_absent = all(
            not Path(str(item.get("name") or "")).exists()
            for item in lease.get("resources") or []
            if item.get("kind") == "ExternalPath" and item.get("cleanup_policy") == "delete_file"
        )
        absent = profile_absent and kubeconfig_absent and lease_files_absent
        errors = []
        if not profile_absent:
            errors.append("minikube profile or profile directory still exists")
        if not kubeconfig_absent:
            errors.append("lease kubeconfig still exists")
        if not lease_files_absent:
            errors.append("lease-owned external files still exist")
        return {"confirmed": absent, "profile_absent": profile_absent, "kubeconfig_absent": kubeconfig_absent, "lease_files_absent": lease_files_absent, "errors": errors}
