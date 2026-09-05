"""Namespace-scoped cleanup and residue attestation for Chaos Mesh resources."""

from __future__ import annotations

import json
from typing import Any, Callable, Iterable

from tools.run_chaos_experiment import run_kubectl


Runner = Callable[..., tuple[int, str, str]]
CHAOS_MESH_GROUP = "chaos-mesh.org"
OWNER_LABEL = "chaosatlas.dev/cleanup-owner"


def _run(
    runner: Runner,
    args: list[str],
    *,
    timeout: int = 30,
    kube_context: str | None = None,
) -> tuple[int, str, str]:
    try:
        return runner(args, timeout=timeout, kube_context=kube_context)
    except TypeError:
        return runner(args, timeout=timeout)


def _resource_types(
    runner: Runner,
    *,
    kube_context: str | None = None,
) -> tuple[list[str], str | None]:
    code, stdout, stderr = _run(
        runner,
        [
            "api-resources",
            f"--api-group={CHAOS_MESH_GROUP}",
            "--namespaced=true",
            "-o",
            "name",
        ],
        kube_context=kube_context,
    )
    if code != 0:
        return [], (stderr or stdout).strip() or f"kubectl api-resources exited {code}"
    values = []
    for line in stdout.splitlines():
        value = line.strip().split()[0] if line.strip() else ""
        if value and value not in values:
            values.append(value)
    return values, None


def _is_owned(
    item: dict[str, Any],
    *,
    owner: str,
    owned_pod_names: set[str],
) -> tuple[bool, str]:
    metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    labels = metadata.get("labels") if isinstance(metadata.get("labels"), dict) else {}
    if str(labels.get(OWNER_LABEL) or "") == owner:
        return True, "owner_label"
    references = metadata.get("ownerReferences") if isinstance(metadata.get("ownerReferences"), list) else []
    if any(
        isinstance(reference, dict)
        and str(reference.get("kind") or "") == "Pod"
        and str(reference.get("name") or "") in owned_pod_names
        for reference in references
    ):
        return True, "owned_target_pod"
    return False, "unowned"


def cleanup_namespace_chaos_resources(
    namespace: str,
    *,
    owner: str = "chaosatlas",
    owned_pod_names: Iterable[str] = (),
    runner: Runner | None = None,
    kube_context: str | None = None,
) -> dict[str, Any]:
    """Delete owned Chaos Mesh resources and verify namespace residue.

    Resources outside the explicit owner label or target-Pod ownership boundary
    are never deleted. They remain visible as unowned residue and fail the
    cleanup gate, so a shared namespace cannot be silently treated as clean.
    """
    namespace = str(namespace or "").strip()
    if not namespace:
        return {"schema_version": "chaosatlas-chaos-cleanup-v1", "status": "failed", "confirmed": False, "errors": ["namespace is required"]}
    runner = runner or run_kubectl
    pod_names = {str(value).strip() for value in owned_pod_names if str(value).strip()}
    resources, resource_error = _resource_types(runner, kube_context=kube_context)
    report: dict[str, Any] = {
        "schema_version": "chaosatlas-chaos-cleanup-v1",
        "namespace": namespace,
        "owner": owner,
        "scanned_resource_types": resources,
        "resources": [],
        "unowned_resources": [],
        "errors": [],
        "confirmed": False,
    }
    if resource_error:
        report["errors"].append(resource_error)
        report["status"] = "failed"
        return report

    for resource in resources:
        code, stdout, stderr = _run(
            runner,
            ["get", resource, "-n", namespace, "-o", "json"],
            kube_context=kube_context,
        )
        if code != 0:
            text = (stderr or stdout).strip()
            if "not found" in text.lower():
                continue
            report["errors"].append(f"{resource}: {text or f'kubectl get exited {code}'}")
            continue
        try:
            document = json.loads(stdout)
        except json.JSONDecodeError as exc:
            report["errors"].append(f"{resource}: invalid kubectl JSON: {exc}")
            continue
        for item in document.get("items") or []:
            if not isinstance(item, dict):
                continue
            metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
            name = str(metadata.get("name") or "")
            if not name:
                report["errors"].append(f"{resource}: resource has no metadata.name")
                continue
            owned, ownership = _is_owned(item, owner=owner, owned_pod_names=pod_names)
            record = {"resource": resource, "name": name, "ownership": ownership, "deleted": False, "verified_absent": False}
            if not owned:
                report["unowned_resources"].append(record)
                continue
            delete_code, delete_stdout, delete_stderr = _run(
                runner,
                ["delete", resource, name, "-n", namespace, "--ignore-not-found=true"],
                kube_context=kube_context,
            )
            record["delete"] = {"return_code": delete_code, "stdout": delete_stdout, "stderr": delete_stderr}
            record["deleted"] = delete_code == 0
            verify_code, verify_stdout, verify_stderr = _run(
                runner,
                ["get", resource, name, "-n", namespace, "-o", "json"],
                kube_context=kube_context,
            )
            verify_text = (verify_stderr or verify_stdout).strip()
            record["verified_absent"] = verify_code != 0 and "not found" in verify_text.lower()
            if not record["deleted"]:
                report["errors"].append(f"{resource}/{name}: delete failed: {verify_text or delete_stderr or delete_stdout}")
            if not record["verified_absent"]:
                report["errors"].append(f"{resource}/{name}: resource remains after cleanup")
            report["resources"].append(record)

    report["status"] = "verified" if not report["errors"] and not report["unowned_resources"] else "failed"
    report["confirmed"] = report["status"] == "verified"
    report["action_count"] = len(report["resources"])
    report["verified_action_count"] = sum(1 for item in report["resources"] if item.get("verified_absent"))
    report["residual_count"] = len(report["unowned_resources"]) + sum(
        1 for item in report["resources"] if not item.get("verified_absent")
    )
    return report
