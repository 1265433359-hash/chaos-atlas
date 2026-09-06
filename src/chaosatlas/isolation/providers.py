"""Built-in Kubernetes and Minikube isolation providers."""

from __future__ import annotations

import json
import os
import re
import secrets
import shutil
import subprocess
import time
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit

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


def default_docker_runner(args: list[str], *, timeout: int = 60, input_text: str | None = None, env: dict[str, str] | None = None) -> tuple[int, str, str]:
    try:
        result = subprocess.run(["docker", *args], input=input_text, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, check=False, env=env)
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

    def _args(self, plan: dict[str, Any], args: list[str], lease: dict[str, Any] | None = None) -> list[str]:
        locator = (lease or {}).get("runtime_locator") if isinstance((lease or {}).get("runtime_locator"), dict) else {}
        context = str(locator.get("kube_context") or plan.get("kube_context") or "")
        return ["--context", context, *args] if context else list(args)

    def _run(self, plan: dict[str, Any], args: list[str], *, lease: dict[str, Any] | None = None, timeout: int = 60, input_text: str | None = None) -> tuple[int, str, str]:
        return self.runner(self._args(plan, args, lease), timeout=timeout, input_text=input_text)

    def _json(self, plan: dict[str, Any], args: list[str], *, lease: dict[str, Any] | None = None) -> tuple[dict[str, Any] | None, str | None]:
        code, stdout, stderr = self._run(plan, [*args, "-o", "json"], lease=lease)
        if code != 0:
            return None, (stderr or stdout).strip() or f"kubectl exit {code}"
        try:
            value = json.loads(stdout)
        except json.JSONDecodeError as exc:
            return None, f"invalid kubectl JSON: {exc}"
        return (value, None) if isinstance(value, dict) else (None, "kubectl response is not an object")

    def capture_runtime_locator(self, plan: dict[str, Any], _lease: dict[str, Any]) -> dict[str, Any]:
        value, error = self._json(plan, ["get", "namespace", "kube-system"])
        cluster_uid = str(((value or {}).get("metadata") or {}).get("uid") or "")
        if error or not cluster_uid:
            raise RuntimeError(f"cannot identify Kubernetes cluster: {error or 'kube-system UID missing'}")
        return {"provider": self.name, "kube_context": str(plan.get("kube_context") or ""), "cluster_uid": cluster_uid, "parent_lease_id": plan.get("parent_lease_id")}

    def _runtime_identity_error(self, plan: dict[str, Any], lease: dict[str, Any]) -> str | None:
        locator = lease.get("runtime_locator") if isinstance(lease.get("runtime_locator"), dict) else {}
        expected = str(locator.get("cluster_uid") or "")
        value, error = self._json(plan, ["get", "namespace", "kube-system"], lease=lease)
        actual = str(((value or {}).get("metadata") or {}).get("uid") or "")
        if error:
            return f"cluster_identity_unavailable:{error}"
        if not expected or actual != expected:
            return "cluster_identity_mismatch"
        return None

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
        identity_error = self._runtime_identity_error(plan, lease)
        if identity_error:
            raise RuntimeError(identity_error)
        if plan.get("mode") == "adopted-test-replica":
            namespace = str(plan["source_namespace"])
            value, error = self._json(plan, ["get", "namespace", namespace], lease=lease)
            if error or value is None:
                raise RuntimeError(error or "adopted namespace unavailable")
            mutate("register_resource", {"kind": "Namespace", "namespace": None, "name": namespace, "expected_uid": str((value.get("metadata") or {}).get("uid") or ""), "actual_uid": str((value.get("metadata") or {}).get("uid") or ""), "cleanup_policy": "release_only"})
            return
        namespace = str(lease.get("target_name") or "")
        labels = {str(k): str(v) for k, v in (lease.get("owner_labels") or {}).items()}
        mutate("register_resource", {"kind": "Namespace", "namespace": None, "name": namespace, "expected_uid": None, "actual_uid": None, "cleanup_policy": "delete"})
        manifest = self._namespace_manifest(namespace, labels)
        code, stdout, stderr = self._run(plan, ["apply", "-f", "-"], lease=lease, input_text=json.dumps(manifest))
        if code != 0:
            raise RuntimeError((stderr or stdout).strip() or "namespace apply failed")
        namespace_value, error = self._json(plan, ["get", "namespace", namespace], lease=lease)
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
            apply_resource = deepcopy(resource)
            if kind == "Secret":
                generated = apply_resource.pop("runtimeGenerate", {})
                keys = generated.get("keys") if isinstance(generated, dict) else []
                values = {str(key): secrets.token_urlsafe(32) for key in keys}
                templates = generated.get("templates") if isinstance(generated, dict) and isinstance(generated.get("templates"), dict) else {}
                for key, template in templates.items():
                    rendered = str(template)
                    for generated_key, generated_value in values.items():
                        rendered = rendered.replace("${" + generated_key + "}", generated_value)
                    values[str(key)] = rendered
                apply_resource["stringData"] = values
            code, stdout, stderr = self._run(plan, ["apply", "-f", "-"], lease=lease, input_text=json.dumps(apply_resource))
            if code != 0:
                raise RuntimeError((stderr or stdout).strip() or f"{kind}/{name} apply failed")
            value, error = self._json(plan, ["get", kind.lower(), name, "-n", namespace], lease=lease)
            if error or value is None:
                raise RuntimeError(error or f"{kind}/{name} unavailable after apply")
            mutate("update_resource_uid", {"kind": kind, "namespace": namespace, "name": name, "actual_uid": str((value.get("metadata") or {}).get("uid") or "")})
            annotations = (resource.get("metadata") or {}).get("annotations") or {}
            if kind == "Job" and annotations.get("chaosatlas.dev/wait-before-next") == "true":
                self._wait_for_job(plan, lease, namespace, name)

    def _wait_for_job(self, plan: dict[str, Any], lease: dict[str, Any], namespace: str, name: str) -> None:
        timeout_s = max(1, min(int(plan.get("ready_timeout_s") or 180), 600))
        deadline = time.monotonic() + timeout_s
        last_error = "Job has not completed"
        while True:
            value, error = self._json(plan, ["get", "job", name, "-n", namespace], lease=lease)
            status = (value or {}).get("status") or {}
            spec = (value or {}).get("spec") or {}
            completions = int(spec.get("completions") if spec.get("completions") is not None else 1)
            if not error and int(status.get("succeeded") or 0) >= completions:
                return
            if int(status.get("failed") or 0) > int(spec.get("backoffLimit") or 0):
                raise RuntimeError(f"Job/{name} exceeded its failure budget")
            last_error = error or "Job has not completed"
            if time.monotonic() >= deadline:
                raise RuntimeError(f"Job/{name} completion timeout: {last_error}")
            time.sleep(1)

    def verify_ready(self, plan: dict[str, Any], lease: dict[str, Any]) -> dict[str, Any]:
        namespace = str(plan.get("source_namespace") if plan.get("mode") == "adopted-test-replica" else lease.get("target_name") or "")
        timeout_s = max(1, min(int(plan.get("ready_timeout_s") or 180), 600))
        deadline = time.monotonic() + timeout_s
        expected_workloads = [
            {"kind": str(item.get("kind")), "name": str(item.get("name"))}
            for item in lease.get("resources") or []
            if item.get("kind") in {"Deployment", "StatefulSet", "Job"}
        ]
        expected_workloads.extend(
            {"kind": str(item.get("kind") or "Deployment"), "name": str(item.get("name") or "")}
            for item in plan.get("expected_workloads") or []
            if isinstance(item, dict) and item.get("name")
        )
        last: dict[str, Any] = {"namespace": False, "pod_count": 0, "all_pods_ready": False, "workloads": []}
        last_error = "namespace missing"
        while True:
            identity_error = self._runtime_identity_error(plan, lease)
            namespace_value, error = self._json(plan, ["get", "namespace", namespace], lease=lease) if not identity_error else (None, identity_error)
            if error or namespace_value is None:
                last_error = error or "namespace missing"
            else:
                if not expected_workloads and plan.get("mode") == "adopted-test-replica":
                    discovered, discovery_error = self._json(plan, ["get", "deployments,statefulsets", "-n", namespace], lease=lease)
                    if discovery_error:
                        last_error = discovery_error
                        if time.monotonic() >= deadline:
                            return {"status": "blocked", "checks": last, "errors": [last_error]}
                        time.sleep(1)
                        continue
                    expected_workloads = [
                        {"kind": str(item.get("kind") or ""), "name": str(((item.get("metadata") or {}).get("name")) or "")}
                        for item in (discovered or {}).get("items") or []
                        if isinstance(item, dict) and item.get("kind") in {"Deployment", "StatefulSet"} and (item.get("metadata") or {}).get("name")
                    ]
                pods, pod_error = self._json(plan, ["get", "pods", "-n", namespace], lease=lease)
                items = [item for item in (pods or {}).get("items") or [] if isinstance(item, dict)]
                active_pods = [item for item in items if str((item.get("status") or {}).get("phase") or "") != "Succeeded"]
                ready = bool(active_pods) and all(
                    str((item.get("status") or {}).get("phase") or "") == "Running"
                    and
                    not (item.get("metadata") or {}).get("deletionTimestamp")
                    and any(condition.get("type") == "Ready" and condition.get("status") == "True" for condition in (item.get("status") or {}).get("conditions") or [])
                    for item in active_pods
                )
                workload_checks = []
                workloads_ready = bool(expected_workloads)
                for expected in expected_workloads:
                    value, workload_error = self._json(plan, ["get", expected["kind"].lower(), expected["name"], "-n", namespace], lease=lease)
                    spec = (value or {}).get("spec") or {}
                    metadata = (value or {}).get("metadata") or {}
                    status = (value or {}).get("status") or {}
                    desired = int(spec.get("replicas") if spec.get("replicas") is not None else 1)
                    generation = int(metadata.get("generation") or 0)
                    observed = int(status.get("observedGeneration") or 0)
                    current_ready = (
                        not workload_error
                        and observed >= generation
                        and int(status.get("readyReplicas") or 0) >= desired
                        and int(status.get("availableReplicas") or status.get("currentReplicas") or 0) >= desired
                        and (expected["kind"] != "Deployment" or int(status.get("updatedReplicas") or 0) >= desired)
                    )
                    if expected["kind"] == "Job":
                        completions = int(spec.get("completions") if spec.get("completions") is not None else 1)
                        current_ready = not workload_error and int(status.get("succeeded") or 0) >= completions and int(status.get("failed") or 0) == 0
                    workload_checks.append({**expected, "desired": desired, "ready": current_ready, "error": workload_error})
                    workloads_ready = workloads_ready and current_ready
                last = {"namespace": True, "pod_count": len(items), "active_pod_count": len(active_pods), "all_pods_ready": ready, "workloads": workload_checks, "all_workloads_ready": workloads_ready}
                last_error = pod_error or ("" if ready and workloads_ready else "Pods or expected workloads are not Ready")
                if ready and workloads_ready and not pod_error:
                    return {"status": "verified", "checks": last, "errors": []}
            if time.monotonic() >= deadline:
                return {"status": "blocked", "checks": last, "errors": [last_error]}
            time.sleep(1)

    def cleanup(self, plan: dict[str, Any], lease: dict[str, Any]) -> dict[str, Any]:
        identity_error = self._runtime_identity_error(plan, lease)
        if identity_error:
            return {"status": "blocked", "reason": identity_error}
        if plan.get("mode") == "adopted-test-replica":
            return {"status": "released", "deleted": False, "reason": "adopted namespace is never deleted"}
        namespace = str(lease.get("target_name") or "")
        if not re.fullmatch(r"ca-l[12]-[a-z0-9-]+", namespace):
            return {"status": "blocked", "reason": "unsafe namespace identity"}
        expected = next((item for item in lease.get("resources") or [] if item.get("kind") == "Namespace" and item.get("name") == namespace), None)
        value, error = self._json(plan, ["get", "namespace", namespace], lease=lease)
        if _is_not_found(error):
            return {"status": "released", "deleted": False, "already_absent": True}
        metadata = (value or {}).get("metadata") or {}
        labels = metadata.get("labels") or {}
        if not expected or (expected.get("actual_uid") and str(metadata.get("uid") or "") != str(expected.get("actual_uid"))):
            return {"status": "blocked", "reason": "cleanup_blocked_identity_mismatch"}
        if labels.get("chaosatlas.dev/lease-id") != lease.get("lease_id") or labels.get("chaosatlas.dev/managed") != "true":
            return {"status": "blocked", "reason": "cleanup_blocked_ownership_mismatch"}
        code, stdout, stderr = self._run(plan, ["delete", "namespace", namespace, "--wait=false"], lease=lease)
        return {"status": "released" if code == 0 else "blocked", "deleted": code == 0, "reason": None if code == 0 else (stderr or stdout).strip()}

    def verify_absent(self, plan: dict[str, Any], lease: dict[str, Any]) -> dict[str, Any]:
        if plan.get("mode") == "adopted-test-replica":
            namespace = str(plan.get("source_namespace") or "")
            value, error = self._json(plan, ["get", "namespace", namespace], lease=lease)
            expected = next((item for item in lease.get("resources") or [] if item.get("cleanup_policy") == "release_only"), {})
            if not expected:
                return {"confirmed": True, "adoption_not_started": True, "errors": []}
            unchanged = value is not None and not error and str((value.get("metadata") or {}).get("uid") or "") == str(expected.get("actual_uid") or "")
            return {"confirmed": unchanged, "adopted_namespace_unchanged": unchanged, "errors": [] if unchanged else [error or "adopted namespace identity changed"]}
        namespace = str(lease.get("target_name") or "")
        last_error = ""
        for _ in range(30):
            value, error = self._json(plan, ["get", "namespace", namespace], lease=lease)
            if value is None and _is_not_found(error):
                return {"confirmed": True, "namespace_absent": True, "errors": []}
            last_error = error or "namespace still exists"
            time.sleep(0.5)
        return {"confirmed": False, "namespace_absent": False, "errors": [last_error]}


class MinikubeIsolationProvider:
    name = "minikube-l3"

    def __init__(self, *, root: str | Path, runner: Runner | None = None, docker_runner: Runner | None = None, cache_seed_root: str | Path | None = None) -> None:
        self.root = Path(root).expanduser().resolve()
        self.runner = runner or default_minikube_runner
        self.docker_runner = docker_runner or default_docker_runner
        self.cache_seed_root = Path(cache_seed_root).expanduser().resolve() if cache_seed_root else (Path.home() / ".minikube" / "cache" / "preloaded-tarball").resolve()

    def supports(self, plan: dict[str, Any]) -> bool:
        return plan.get("provider") == self.name and plan.get("effective_isolation") == "L3"

    def capture_runtime_locator(self, plan: dict[str, Any], _lease: dict[str, Any]) -> dict[str, Any]:
        return {
            "provider": self.name,
            "runtime_root": str(self.root),
            "driver": str(((plan.get("blueprint") or {}).get("driver")) or "docker"),
            "cni": str(((plan.get("blueprint") or {}).get("cni")) or ""),
        }

    def _root(self, lease: dict[str, Any]) -> Path:
        locator = lease.get("runtime_locator") if isinstance(lease.get("runtime_locator"), dict) else {}
        raw = str(locator.get("runtime_root") or "")
        if not raw:
            raise RuntimeError("Minikube runtime locator is missing")
        return Path(raw).expanduser().resolve()

    def _paths(self, lease: dict[str, Any]) -> tuple[Path, Path, Path, Path]:
        profile = str(lease.get("target_name") or "")
        root = self._root(lease)
        minikube_home = (root / "minikube").resolve()
        kubeconfig = (root / "kubeconfigs" / f"{lease['lease_id']}.config").resolve()
        profile_dir = (minikube_home / ".minikube" / "profiles" / profile).resolve()
        machine_dir = (minikube_home / ".minikube" / "machines" / profile).resolve()
        for value in (minikube_home, kubeconfig, profile_dir, machine_dir):
            if root not in value.parents:
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
            if self._root(lease) not in destination.parents:
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

    @staticmethod
    def _runtime_proxy_args(blueprint: dict[str, Any], runtime: str) -> list[str]:
        raw = blueprint.get("runtime_proxy")
        if raw in (None, {}):
            return []
        if runtime != "docker":
            raise RuntimeError("runtime_proxy requires the Minikube docker container runtime")
        if not isinstance(raw, dict) or set(raw) - {"HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY"}:
            raise RuntimeError("runtime_proxy only allows HTTP_PROXY, HTTPS_PROXY and NO_PROXY")
        args: list[str] = []
        for key in sorted(raw):
            value = raw[key]
            if not isinstance(value, str) or not value or len(value) > 512 or any(char in value for char in "\r\n\x00"):
                raise RuntimeError(f"runtime_proxy {key} is invalid")
            if key in {"HTTP_PROXY", "HTTPS_PROXY"}:
                parsed = urlsplit(value)
                if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
                    raise RuntimeError("runtime_proxy URLs must be http(s) origins and must not contain credentials")
                if parsed.path not in {"", "/"}:
                    raise RuntimeError("runtime_proxy URLs must not contain a path")
            elif not re.fullmatch(r"[A-Za-z0-9.*,:_/-]+", value):
                raise RuntimeError("runtime_proxy NO_PROXY contains unsupported characters")
            args.extend(["--docker-env", f"{key}={value}"])
        return args

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
        cni = str(((plan.get("blueprint") or {}).get("cni")) or "")
        if driver not in {"docker", "hyperv"} or runtime not in {"containerd", "docker"} or cni not in {"", "calico"}:
            raise RuntimeError("unsupported Minikube driver, container runtime or CNI")
        args = ["start", "--profile", profile, "--driver", driver, "--container-runtime", runtime, "--cpus", str(budget.get("cpu") or 2), "--memory", str(budget.get("memory") or "4096mb"), "--disk-size", str(budget.get("disk") or "10g")]
        args.extend(self._runtime_proxy_args(plan.get("blueprint") or {}, runtime))
        if cni:
            args.extend(["--cni", cni])
        code, stdout, stderr = self._run(args, lease)
        if code != 0:
            raise RuntimeError((stderr or stdout).strip() or "minikube start failed")
        preload = ((plan.get("blueprint") or {}).get("local_image_preload")) or []
        if not isinstance(preload, list) or len(preload) > 12 or any(not isinstance(image, str) or not re.fullmatch(r"[A-Za-z0-9._/:@-]{1,240}", image) for image in preload):
            raise RuntimeError("local_image_preload must contain safe image references")
        for image in preload:
            mutate("register_resource", {"kind": "ContainerImage", "namespace": None, "name": image, "expected_uid": None, "actual_uid": None, "cleanup_policy": "provider_delete"})
            code, stdout, stderr = self._run(["image", "load", "--profile", profile, image], lease)
            if code != 0:
                raise RuntimeError((stderr or stdout).strip() or f"Minikube image preload failed: {image}")
        mutate("update_profile", {"provider": "minikube", "name": profile, "state": "ready"})

    def verify_ready(self, plan: dict[str, Any], lease: dict[str, Any]) -> dict[str, Any]:
        profile = str(lease.get("target_name") or "")
        code, stdout, stderr = self._run(["status", "--profile", profile, "--output", "json"], lease, timeout=60)
        ready = code == 0 and stdout.lower().count("running") >= 2
        return {"status": "verified" if ready else "blocked", "checks": {"profile": profile, "status_running": ready}, "errors": [] if ready else [(stderr or stdout).strip() or "minikube is not Ready"]}

    def _profile_presence(self, lease: dict[str, Any]) -> dict[str, Any]:
        profile = str(lease.get("target_name") or "")
        list_code, list_out, list_err = self._run(["profile", "list", "--output", "json"], lease, timeout=60)
        if list_code != 0:
            return {"status": "unknown", "reason": (list_err or list_out).strip() or f"minikube profile list exit {list_code}"}
        try:
            inventory = json.loads(list_out or "{}")
        except json.JSONDecodeError as exc:
            return {"status": "unknown", "reason": f"invalid Minikube profile inventory JSON: {exc}"}
        profiles: set[str] = set()
        for item in inventory.get("valid") or inventory.get("profiles") or []:
            if isinstance(item, dict):
                profiles.add(str(item.get("Name") or item.get("name") or ""))
            elif isinstance(item, str):
                profiles.add(item)
        driver = str(((lease.get("runtime_locator") or {}).get("driver")) or "docker")
        container_present = False
        if driver == "docker":
            code, stdout, stderr = self.docker_runner(
                ["ps", "-a", "--filter", f"label=name.minikube.sigs.k8s.io={profile}", "--format", "{{.ID}}"],
                timeout=60,
            )
            if code != 0:
                return {"status": "unknown", "reason": (stderr or stdout).strip() or f"docker ps exit {code}"}
            container_present = bool(stdout.strip())
        present = profile in profiles or container_present
        return {"status": "present" if present else "absent", "profile_listed": profile in profiles, "container_present": container_present}

    def cleanup(self, plan: dict[str, Any], lease: dict[str, Any]) -> dict[str, Any]:
        profile = str(lease.get("target_name") or "")
        registered = any(item.get("name") == profile and item.get("provider") == "minikube" for item in lease.get("external_profiles") or [])
        if not registered or not re.fullmatch(r"ca-l3-[a-z0-9-]+", profile) or profile in {"minikube", "chaosatlas-apps"}:
            return {"status": "blocked", "reason": "cleanup_blocked_profile_identity"}
        presence = self._profile_presence(lease)
        if presence["status"] == "unknown":
            return {"status": "blocked", "reason": f"profile_presence_unknown:{presence['reason']}"}
        code, stdout, stderr = (0, "", "")
        if presence["status"] == "present":
            code, stdout, stderr = self._run(["delete", "--profile", profile], lease)
            if code != 0:
                after = self._profile_presence(lease)
                if after["status"] != "absent":
                    return {"status": "blocked", "reason": (stderr or stdout or after.get("reason") or "profile delete failed").strip()}
        for item in lease.get("resources") or []:
            if item.get("kind") != "ExternalPath" or item.get("cleanup_policy") != "delete_file":
                continue
            path = Path(str(item.get("name") or "")).resolve()
            if self._root(lease) not in path.parents:
                return {"status": "blocked", "reason": "cleanup_blocked_external_path"}
            if path.is_file() or path.is_symlink():
                path.unlink()
        return {"status": "released", "reason": None, "already_absent": presence["status"] == "absent"}

    def verify_absent(self, plan: dict[str, Any], lease: dict[str, Any]) -> dict[str, Any]:
        profile = str(lease.get("target_name") or "")
        presence = self._profile_presence(lease)
        _, kubeconfig, profile_dir, machine_dir = self._paths(lease)
        profile_absent = presence["status"] == "absent" and not profile_dir.exists() and not machine_dir.exists()
        kubeconfig_absent = not kubeconfig.exists()
        lease_files_absent = all(
            not Path(str(item.get("name") or "")).exists()
            for item in lease.get("resources") or []
            if item.get("kind") == "ExternalPath" and item.get("cleanup_policy") == "delete_file"
        )
        absent = profile_absent and kubeconfig_absent and lease_files_absent
        errors = []
        if presence["status"] == "unknown":
            errors.append(f"profile presence unknown: {presence.get('reason')}")
        if not profile_absent:
            errors.append("minikube profile or profile directory still exists")
        if not kubeconfig_absent:
            errors.append("lease kubeconfig still exists")
        if not lease_files_absent:
            errors.append("lease-owned external files still exist")
        return {"confirmed": absent, "profile_absent": profile_absent, "kubeconfig_absent": kubeconfig_absent, "lease_files_absent": lease_files_absent, "errors": errors}
