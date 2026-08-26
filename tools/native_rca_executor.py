"""Explicitly gated Kubernetes executor for native RCA actions."""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any, Callable

from tools.kubernetes_evidence import KubernetesEvidenceCollector, Runner, _default_runner
from tools.rca_loop import _contains_sensitive_value


class NativeRCAExecutor:
    """Execute only schema-bounded native actions in one approved namespace."""

    def __init__(
        self,
        *,
        root: Path,
        namespace: str,
        allowed_namespaces: set[str],
        runner: Runner | None = None,
        allow_live: bool = False,
        collector: KubernetesEvidenceCollector | None = None,
    ) -> None:
        self.root = Path(root)
        self.namespace = str(namespace or "").strip()
        self.allowed_namespaces = {str(item).strip() for item in allowed_namespaces if str(item).strip()}
        self.runner = runner or _default_runner
        self.allow_live = bool(allow_live)
        self.collector = collector or KubernetesEvidenceCollector(
            root=self.root,
            allowed_namespaces=self.allowed_namespaces,
            runner=self.runner,
        )

    def _guard_action(self, action: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        if self.namespace not in self.allowed_namespaces:
            errors.append("executor namespace is outside the allow-list")
        if str(action.get("namespace") or "") != self.namespace:
            errors.append("action namespace does not match executor namespace")
        if not str(action.get("action_id") or ""):
            errors.append("action_id is required")
        if not str(action.get("target_scope") or ""):
            errors.append("target_scope is required")
        return errors

    @staticmethod
    def _deployment_target(target_scope: str) -> tuple[str, str] | None:
        match = re.fullmatch(r"(deployment|statefulset|daemonset|service|pod):([A-Za-z0-9][A-Za-z0-9.-]*)", target_scope)
        return (match.group(1), match.group(2)) if match else None

    def _config_lookup(self, action: dict[str, Any]) -> dict[str, Any]:
        target = self._deployment_target(str(action.get("target_scope") or ""))
        if target is None:
            return {"status": "method_invalid", "errors": ["target_scope must be resource:name"], "evidence": []}
        resource, name = target
        command = ["get", resource, name, "-n", self.namespace, "-o", "json"]
        evidence = self.collector._capture(
            evidence_id=f"EV-{action['action_id']}-CONFIG",
            kind="config",
            claim_scope=str(action["target_scope"]),
            relative_path=f"runtime/kubernetes/config/{action['action_id']}.json",
            command=command,
            interpretation="Kubernetes deployment facts captured from the approved namespace",
            satisfies=list(action.get("satisfies") or ["static_manifest_replica_facts"]),
            window=action.get("window"),
        )
        if evidence.get("polarity") == "unavailable":
            return {"status": "environment_blocked", "errors": ["kubectl get did not return deployment facts"], "evidence": [evidence]}
        return {"status": "observed", "outcome_status": "observed", "evidence": [evidence]}

    def _fault_injection(self, action: dict[str, Any]) -> dict[str, Any]:
        manifest = action.get("mutation_manifest")
        if not isinstance(manifest, dict):
            return {"status": "environment_blocked", "errors": ["mutation_manifest is required"], "evidence": []}
        metadata = manifest.get("metadata") or {}
        kind = str(manifest.get("kind") or "")
        if kind not in {"PodChaos", "NetworkChaos", "StressChaos"}:
            return {"status": "method_invalid", "errors": ["unsupported mutation kind"], "evidence": []}
        if str(metadata.get("namespace") or "") != self.namespace:
            return {"status": "environment_blocked", "errors": ["mutation namespace is outside the allow-list"], "evidence": []}
        if not self.allow_live:
            return {"status": "environment_blocked", "errors": ["explicit live approval is required"], "evidence": []}
        serialized = json.dumps(manifest, ensure_ascii=True, sort_keys=True)
        if _contains_sensitive_value(serialized):
            return {"status": "method_invalid", "errors": ["mutation manifest contains sensitive values"], "evidence": []}
        code, stdout, stderr = self.runner(
            ["apply", "--server-side", "--field-manager", "chaosatlas", "-f", "-"],
            timeout=30,
            input_text=serialized,
        )
        if code != 0:
            return {"status": "environment_blocked", "errors": [f"kubectl apply failed: {(stderr or stdout).strip() or code}"], "evidence": []}
        return {
            "status": "observed",
            "outcome_status": "injection_requested",
            "injection_confirmed": False,
            "errors": ["injection confirmation requires a separate observation collector"],
            "evidence": [],
        }

    def _log_lookup(self, action: dict[str, Any]) -> dict[str, Any]:
        workload = str(action.get("workload") or "").strip()
        if not workload:
            target = self._deployment_target(str(action.get("target_scope") or ""))
            workload = f"{target[0]}/{target[1]}" if target and target[0] in {"deployment", "statefulset", "daemonset", "pod"} else ""
        if not workload:
            return {"status": "method_invalid", "errors": ["workload is required for log_lookup"], "evidence": []}
        evidence = self.collector.collect_logs(
            namespace=self.namespace,
            workload=workload,
            claim_scope=str(action["target_scope"]),
            evidence_id=f"EV-{action['action_id']}-LOG",
            since=str(action.get("since") or "2m"),
            window=action.get("window"),
        )
        return {
            "status": "observed" if evidence.get("polarity") != "unavailable" else "environment_blocked",
            "outcome_status": "observed",
            "evidence": [evidence],
        }

    def _event_lookup(self, action: dict[str, Any]) -> dict[str, Any]:
        evidence = self.collector.collect_events(
            namespace=self.namespace,
            claim_scope=str(action["target_scope"]),
            evidence_id=f"EV-{action['action_id']}-EVENT",
            window=action.get("window"),
        )
        return {
            "status": "observed" if evidence.get("polarity") != "unavailable" else "environment_blocked",
            "outcome_status": "observed",
            "evidence": [evidence],
        }

    def __call__(self, action: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(action, dict):
            return {"status": "method_invalid", "errors": ["action must be an object"], "evidence": []}
        errors = self._guard_action(action)
        if errors:
            return {"status": "environment_blocked", "errors": errors, "evidence": []}
        kind = str(action.get("kind") or "")
        if kind == "config_lookup":
            return self._config_lookup(action)
        if kind == "log_lookup":
            return self._log_lookup(action)
        if kind == "event_lookup":
            return self._event_lookup(action)
        if kind == "native_fault_injection":
            return self._fault_injection(action)
        return {"status": "method_invalid", "errors": [f"unsupported native action kind: {kind}"], "evidence": []}
