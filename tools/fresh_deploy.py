"""Namespace-scoped fresh deployment adapter for improvement retests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

import yaml


Runner = Callable[[list[str]], dict[str, Any]]


class FreshDeploymentAdapter:
    """Validate and optionally apply a manifest copy with explicit approval."""

    def __init__(
        self,
        *,
        namespace: str,
        allowed_namespaces: set[str],
        runner: Runner,
        allow_live: bool = False,
    ) -> None:
        self.namespace = str(namespace).strip()
        self.allowed_namespaces = {str(value).strip() for value in allowed_namespaces}
        self.runner = runner
        self.allow_live = bool(allow_live)

    def _manifest_paths(self, source_root: Path) -> list[Path]:
        root = Path(source_root)
        if not root.is_dir() or root.is_symlink():
            raise ValueError("fresh deployment source must be a real directory")
        paths = sorted(
            [*root.rglob("*.yaml"), *root.rglob("*.yml")],
            key=lambda path: str(path).replace("\\", "/"),
        )
        if not paths:
            raise ValueError("fresh deployment source contains no YAML manifests")
        return paths

    def _validate_manifest(self, path: Path) -> None:
        documents = list(yaml.safe_load_all(path.read_text(encoding="utf-8")))
        for document in documents:
            if document is None:
                continue
            if not isinstance(document, dict):
                raise ValueError(f"manifest document is not an object: {path}")
            metadata = document.get("metadata") or {}
            declared = str(metadata.get("namespace") or self.namespace).strip()
            if declared != self.namespace:
                raise ValueError(f"manifest namespace mismatch: {path}")

    def _dry_run(self, paths: list[Path]) -> dict[str, Any]:
        if self.namespace not in self.allowed_namespaces:
            return {"status": "deployment_blocked", "reason": "namespace is outside allow-list", "live_mutation": False}
        results: list[dict[str, Any]] = []
        for path in paths:
            self._validate_manifest(path)
            result = self.runner(["apply", "--namespace", self.namespace, "--dry-run=server", "-f", str(path)])
            results.append({"path": str(path), "result": result})
            if int(result.get("return_code", 1)) != 0:
                return {
                    "status": "deployment_blocked",
                    "reason": str(result.get("stderr") or "server-side dry-run failed"),
                    "live_mutation": False,
                    "dry_run": results,
                }
        return {"status": "dry_run_ready", "live_mutation": False, "dry_run": results}

    def deploy(self, source_root: Path) -> dict[str, Any]:
        try:
            paths = self._manifest_paths(Path(source_root))
            return self._dry_run(paths)
        except (OSError, ValueError, yaml.YAMLError, json.JSONDecodeError) as exc:
            return {"status": "deployment_blocked", "reason": str(exc), "live_mutation": False}

    def apply_live(self, source_root: Path) -> dict[str, Any]:
        if not self.allow_live:
            return {"status": "deployment_blocked", "reason": "explicit live approval is required", "live_mutation": False}
        dry_run = self.deploy(source_root)
        if dry_run.get("status") != "dry_run_ready":
            return dry_run
        paths = self._manifest_paths(Path(source_root))
        applied: list[dict[str, Any]] = []
        for path in paths:
            result = self.runner(["apply", "--namespace", self.namespace, "-f", str(path)])
            applied.append({"path": str(path), "result": result})
            if int(result.get("return_code", 1)) != 0:
                return {"status": "deployment_blocked", "reason": str(result.get("stderr") or "apply failed"), "live_mutation": True, "dry_run": dry_run, "applied": applied}
        return {"status": "deployed", "live_mutation": True, "dry_run": dry_run, "applied": applied}

    def cleanup(self, source_root: Path) -> dict[str, Any]:
        if not self.allow_live:
            return {"status": "deployment_blocked", "reason": "explicit live approval is required", "live_mutation": False}
        try:
            paths = self._manifest_paths(Path(source_root))
            deleted: list[dict[str, Any]] = []
            for path in paths:
                result = self.runner(["delete", "--namespace", self.namespace, "-f", str(path)])
                deleted.append({"path": str(path), "result": result})
                if int(result.get("return_code", 1)) != 0:
                    return {"status": "deployment_blocked", "reason": str(result.get("stderr") or "delete failed"), "live_mutation": True, "deleted": deleted}
            return {"status": "cleanup_verified", "live_mutation": True, "deleted": deleted}
        except (OSError, ValueError, yaml.YAMLError, json.JSONDecodeError) as exc:
            return {"status": "deployment_blocked", "reason": str(exc), "live_mutation": True}
