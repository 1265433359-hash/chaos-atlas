"""Fail-closed, side-effect-free runtime readiness evaluation."""

from __future__ import annotations

from typing import Any


PROJECT_NAMESPACES = {
    "online-boutique": "chaosatlas-online-boutique",
    "opentelemetry-demo": "chaosatlas-otel",
    "sock-shop": "chaosatlas-sock-shop",
}


def _passed(facts: dict[str, Any], key: str, expected: str) -> bool:
    return facts.get(key) == expected


def sock_shop_cluster_facts(
    health: dict[str, Any], baseline_windows: list[list[dict[str, Any]]], rehearsal: dict[str, Any]
) -> dict[str, Any]:
    """Normalize deployment-gate evidence into the fail-closed profile inputs."""
    successes = [sum(item.get("pass") is True for item in window) for window in baseline_windows]
    passed_windows = sum(bool(window) and all(item.get("pass") is True for item in window) for window in baseline_windows)
    cleanup = rehearsal.get("cleanup") or {}
    recovery = rehearsal.get("recovery") or {}
    washout = rehearsal.get("washout") or {}
    residuals = cleanup.get("residual_resources") or []
    scan_errors = cleanup.get("global_scan_errors") or []
    healthy_deployments = (
        health.get("node_ready") is True
        and health.get("namespace") == PROJECT_NAMESPACES["sock-shop"]
        and health.get("deployments_total", 0) > 0
        and health.get("deployments_available") == health.get("deployments_total")
    )
    washout_successes = sum(item.get("pass") is True for item in washout.get("journeys") or [])
    return {
        **health,
        "deployments_healthy": healthy_deployments,
        "baseline_windows": {"passed": passed_windows, "successes": successes},
        "recovery_rehearsal": "passed" if rehearsal.get("status") == "completed" and recovery.get("recovered") is True else "failed",
        "cleanup": "passed" if cleanup.get("absent_confirmed") is True and not residuals and not scan_errors else "failed",
        "global_residual_scan": "clear" if not residuals and not scan_errors else "blocked",
        "washout": {"stable": washout.get("stable") is True, "successes": washout_successes},
    }


def evaluate_runtime_profile(manifest: dict[str, Any], cluster_facts: dict[str, Any]) -> dict[str, Any]:
    project_id = str(manifest.get("project_id", ""))
    blocked: list[str] = []
    if manifest.get("namespace") != PROJECT_NAMESPACES.get(project_id):
        blocked.append("namespace_not_allowed_for_project")
    if manifest.get("static_gate", {}).get("status") != "passed":
        blocked.extend(str(item) for item in manifest.get("static_gate", {}).get("blocked_reasons", []) or ["static_gate_blocked"])
    if manifest.get("image_provenance", {}).get("all_immutable") is not True:
        blocked.append("immutable_image_provenance_missing")
    oracle = manifest.get("oracle_contract") or {}
    if not oracle.get("workflow") or not oracle.get("success"):
        blocked.append("business_oracle_incomplete")
    if not _passed(cluster_facts, "server_side_dry_run", "passed"):
        blocked.append("server_side_dry_run_not_passed")
    if (cluster_facts.get("baseline_windows") or {}).get("passed", 0) < 2:
        blocked.append("two_failure_free_baselines_missing")
    if not _passed(cluster_facts, "recovery_rehearsal", "passed"):
        blocked.append("recovery_rehearsal_not_passed")
    if not _passed(cluster_facts, "cleanup", "passed"):
        blocked.append("cleanup_rehearsal_not_passed")
    if cluster_facts.get("global_residual_scan") != "clear":
        blocked.append("global_chaos_residuals_present")
    if (cluster_facts.get("washout") or {}).get("stable") is not True:
        blocked.append("stable_washout_missing")
    blocked = sorted(set(blocked))
    return {
        "schema_version": "chaosatlas-two-arm-runtime-profile-v1",
        "project_id": project_id,
        "namespace": manifest.get("namespace"),
        "status": "runtime_ready" if not blocked else "blocked",
        "runtime_ready": not blocked,
        "blocked_reasons": blocked,
        "cluster_facts": cluster_facts,
        "human_review": "pending",
        "knowledge_base_updated": False,
    }
