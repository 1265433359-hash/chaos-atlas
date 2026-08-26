"""Read-only Kubernetes events and logs evidence collection.

The collector owns command construction, namespace allow-listing and evidence
artifact hashing. It never infers an RCA verdict from a command failure.
"""

from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
from typing import Any, Callable

from tools.evidence_collectors import collect_file_evidence, collect_unavailable_evidence
from tools.rca_loop import _contains_sensitive_value


Runner = Callable[..., tuple[int, str, str]]


def _default_runner(args: list[str], timeout: int = 30, input_text: str | None = None) -> tuple[int, str, str]:
    try:
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
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 124, "", str(exc)


def _safe_stem(value: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value)).strip("-")
    if not stem:
        raise ValueError("evidence_id must produce a safe filename")
    return stem


class KubernetesEvidenceCollector:
    """Collect immutable command output into the shared evidence contract."""

    def __init__(
        self,
        *,
        root: Path,
        allowed_namespaces: set[str],
        runner: Runner | None = None,
        timeout: int = 30,
        kube_context: str | None = None,
    ) -> None:
        self.root = Path(root)
        self.allowed_namespaces = {str(item).strip() for item in allowed_namespaces if str(item).strip()}
        self.runner = runner or _default_runner
        self.timeout = timeout
        self.kube_context = str(kube_context).strip() if kube_context else None

    def _command(self, command: list[str]) -> list[str]:
        if not self.kube_context:
            return list(command)
        if not re.fullmatch(r"[A-Za-z0-9_.:@/-]+", self.kube_context):
            raise ValueError("kube_context contains unsafe characters")
        return ["--context", self.kube_context, *command]

    def _guard_namespace(self, namespace: str) -> str:
        namespace = str(namespace or "").strip()
        if not namespace or namespace not in self.allowed_namespaces:
            raise ValueError(f"namespace is outside the allow-list: {namespace!r}")
        return namespace

    def _capture(
        self,
        *,
        evidence_id: str,
        kind: str,
        claim_scope: str,
        relative_path: str,
        command: list[str],
        interpretation: str,
        satisfies: list[str],
        window: dict[str, str] | None,
    ) -> dict[str, Any]:
        command = self._command(command)
        code, stdout, stderr = self.runner(command, timeout=self.timeout)
        relative_path = relative_path.replace("\\", "/")
        path = self.root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        if code != 0:
            if _contains_sensitive_value(stderr):
                raise ValueError("Kubernetes error output contains sensitive values")
            path.write_text(
                json.dumps({"command": command, "returncode": code, "stderr": stderr}, ensure_ascii=True) + "\n",
                encoding="utf-8",
            )
            return collect_unavailable_evidence(
                root=self.root,
                source_ref=relative_path,
                evidence_id=evidence_id,
                kind=kind,
                claim_scope=claim_scope,
                reason=f"kubectl_failed:{code}",
                window=window,
            )
        if _contains_sensitive_value(stdout) or _contains_sensitive_value(stderr):
            raise ValueError("Kubernetes output contains sensitive values")
        path.write_text(stdout, encoding="utf-8")
        return collect_file_evidence(
            root=self.root,
            source_ref=relative_path,
            evidence_id=evidence_id,
            kind=kind,
            claim_scope=claim_scope,
            interpretation=interpretation,
            polarity="supports",
            satisfies=satisfies,
            window=window,
        )

    def _capture_projected_json(
        self,
        *,
        evidence_id: str,
        kind: str,
        claim_scope: str,
        relative_path: str,
        command: list[str],
        interpretation: str,
        satisfies: list[str],
        project: Callable[[dict[str, Any]], dict[str, Any]],
        window: dict[str, str] | None,
    ) -> dict[str, Any]:
        """Capture only an allow-listed projection of a Kubernetes object."""
        command = self._command(command)
        code, stdout, stderr = self.runner(command, timeout=self.timeout)
        relative_path = relative_path.replace("\\", "/")
        path = self.root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        if code != 0:
            if _contains_sensitive_value(stderr):
                raise ValueError("Kubernetes error output contains sensitive values")
            path.write_text(
                json.dumps({"command": command, "returncode": code, "stderr": stderr}, ensure_ascii=True) + "\n",
                encoding="utf-8",
            )
            return collect_unavailable_evidence(
                root=self.root,
                source_ref=relative_path,
                evidence_id=evidence_id,
                kind=kind,
                claim_scope=claim_scope,
                reason=f"kubectl_failed:{code}",
                window=window,
            )
        try:
            value = json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise ValueError("Kubernetes JSON response is invalid") from exc
        if not isinstance(value, dict):
            raise ValueError("Kubernetes JSON response must be an object")
        projected = project(value)
        serialized = json.dumps(projected, ensure_ascii=True, indent=2) + "\n"
        if _contains_sensitive_value(serialized):
            raise ValueError("projected Kubernetes facts contain sensitive values")
        path.write_text(serialized, encoding="utf-8")
        return collect_file_evidence(
            root=self.root,
            source_ref=relative_path,
            evidence_id=evidence_id,
            kind=kind,
            claim_scope=claim_scope,
            interpretation=interpretation,
            polarity="supports",
            satisfies=satisfies,
            window=window,
        )

    @staticmethod
    def _project_deployment(value: dict[str, Any]) -> dict[str, Any]:
        metadata = value.get("metadata") if isinstance(value.get("metadata"), dict) else {}
        spec = value.get("spec") if isinstance(value.get("spec"), dict) else {}
        status = value.get("status") if isinstance(value.get("status"), dict) else {}
        selector = spec.get("selector") if isinstance(spec.get("selector"), dict) else {}
        template = spec.get("template") if isinstance(spec.get("template"), dict) else {}
        template_metadata = template.get("metadata") if isinstance(template.get("metadata"), dict) else {}
        template_spec = template.get("spec") if isinstance(template.get("spec"), dict) else {}
        containers = []
        for container in template_spec.get("containers") or []:
            if not isinstance(container, dict):
                continue
            containers.append({key: container.get(key) for key in ("name", "image", "ports", "resources", "livenessProbe", "readinessProbe") if key in container})
        return {
            "kind": value.get("kind"),
            "metadata": {key: metadata.get(key) for key in ("name", "namespace", "labels", "generation") if key in metadata},
            "spec": {"replicas": spec.get("replicas"), "selector": selector, "template_labels": template_metadata.get("labels"), "containers": containers},
            "status": {key: status.get(key) for key in ("replicas", "readyReplicas", "availableReplicas", "updatedReplicas", "conditions") if key in status},
        }

    @staticmethod
    def _project_service(value: dict[str, Any]) -> dict[str, Any]:
        metadata = value.get("metadata") if isinstance(value.get("metadata"), dict) else {}
        spec = value.get("spec") if isinstance(value.get("spec"), dict) else {}
        status = value.get("status") if isinstance(value.get("status"), dict) else {}
        return {
            "kind": value.get("kind"),
            "metadata": {key: metadata.get(key) for key in ("name", "namespace", "labels") if key in metadata},
            "spec": {key: spec.get(key) for key in ("type", "selector", "ports", "clusterIP") if key in spec},
            "status": {key: status.get(key) for key in ("loadBalancer") if key in status},
        }

    @staticmethod
    def _project_pods(value: dict[str, Any]) -> dict[str, Any]:
        projected_items = []
        for pod in value.get("items") or []:
            if not isinstance(pod, dict):
                continue
            metadata = pod.get("metadata") if isinstance(pod.get("metadata"), dict) else {}
            status = pod.get("status") if isinstance(pod.get("status"), dict) else {}
            projected_items.append({
                "metadata": {key: metadata.get(key) for key in ("name", "namespace", "labels", "ownerReferences") if key in metadata},
                "status": {key: status.get(key) for key in ("phase", "conditions", "containerStatuses") if key in status},
            })
        return {"kind": value.get("kind"), "items": projected_items}

    def collect_events(
        self,
        *,
        namespace: str,
        claim_scope: str,
        evidence_id: str,
        involved_object_name: str | None = None,
        window: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        namespace = self._guard_namespace(namespace)
        command = ["get", "events", "-n", namespace]
        if involved_object_name is not None:
            name = str(involved_object_name).strip()
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.-]*", name):
                raise ValueError("involved_object_name must be a safe Kubernetes resource name")
            command.extend(["--field-selector", f"involvedObject.name={name}"])
        command.extend(["-o", "json"])
        return self._capture(
            evidence_id=evidence_id,
            kind="kubernetes_event",
            claim_scope=claim_scope,
            relative_path=f"runtime/kubernetes/events/{_safe_stem(evidence_id)}.json",
            command=command,
            interpretation="Kubernetes events captured for the bounded RCA window",
            satisfies=["kubernetes_event_window"],
            window=window,
        )

    def collect_logs(
        self,
        *,
        namespace: str,
        workload: str,
        claim_scope: str,
        evidence_id: str,
        since: str = "2m",
        window: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        namespace = self._guard_namespace(namespace)
        workload = str(workload or "").strip()
        if not re.fullmatch(r"(?:deployment|statefulset|daemonset|pod)/[A-Za-z0-9][A-Za-z0-9.-]*", workload):
            raise ValueError("workload must be a safe Kubernetes workload reference")
        if not re.fullmatch(r"[0-9]+[smhd]", str(since)):
            raise ValueError("since must be a bounded duration such as 2m")
        return self._capture(
            evidence_id=evidence_id,
            kind="runtime_log",
            claim_scope=claim_scope,
            relative_path=f"runtime/kubernetes/logs/{_safe_stem(evidence_id)}.log",
            command=["logs", workload, "-n", namespace, f"--since={since}"],
            interpretation="Kubernetes workload logs captured for the bounded RCA window",
            satisfies=["runtime_logs_window"],
            window=window,
        )

    def collect_deployment_facts(
        self,
        *,
        namespace: str,
        deployment: str,
        claim_scope: str,
        evidence_id: str,
        window: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        namespace = self._guard_namespace(namespace)
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.-]*", str(deployment)):
            raise ValueError("deployment must be a safe Kubernetes resource name")
        return self._capture_projected_json(
            evidence_id=evidence_id,
            kind="manifest",
            claim_scope=claim_scope,
            relative_path=f"runtime/kubernetes/deployments/{_safe_stem(evidence_id)}.json",
            command=["get", "deployment", str(deployment), "-n", namespace, "-o", "json"],
            interpretation="Deployment facts captured for the bounded evidence plan",
            satisfies=["deployment_identity"],
            project=self._project_deployment,
            window=window,
        )

    def collect_service_facts(
        self,
        *,
        namespace: str,
        service: str,
        claim_scope: str,
        evidence_id: str,
        window: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        namespace = self._guard_namespace(namespace)
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.-]*", str(service)):
            raise ValueError("service must be a safe Kubernetes resource name")
        return self._capture_projected_json(
            evidence_id=evidence_id,
            kind="config",
            claim_scope=claim_scope,
            relative_path=f"runtime/kubernetes/services/{_safe_stem(evidence_id)}.json",
            command=["get", "service", str(service), "-n", namespace, "-o", "json"],
            interpretation="Service facts captured for the bounded evidence plan",
            satisfies=["service_selector"],
            project=self._project_service,
            window=window,
        )

    def collect_pod_state(
        self,
        *,
        namespace: str,
        selector: dict[str, str],
        claim_scope: str,
        evidence_id: str,
        window: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        namespace = self._guard_namespace(namespace)
        if not isinstance(selector, dict) or not selector:
            raise ValueError("pod selector must be a non-empty object")
        labels: list[str] = []
        label_key_pattern = r"(?:[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?/)?[A-Za-z0-9](?:[A-Za-z0-9_.-]*[A-Za-z0-9])?"
        for key, value in sorted(selector.items()):
            if not re.fullmatch(label_key_pattern, str(key)) or not re.fullmatch(r"[A-Za-z0-9_.-]+", str(value)):
                raise ValueError("pod selector contains an unsafe label")
            labels.append(f"{key}={value}")
        return self._capture_projected_json(
            evidence_id=evidence_id,
            kind="config",
            claim_scope=claim_scope,
            relative_path=f"runtime/kubernetes/pods/{_safe_stem(evidence_id)}.json",
            command=["get", "pods", "-n", namespace, "-l", ",".join(labels), "-o", "json"],
            interpretation="Pod state captured for the bounded evidence plan",
            satisfies=["ready_pods"],
            project=self._project_pods,
            window=window,
        )
