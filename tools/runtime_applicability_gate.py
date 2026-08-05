"""Read-only runtime applicability gate for Train Ticket chaos mutations."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError as exc:  # pragma: no cover
    raise SystemExit("PyYAML is required") from exc


RESOURCE_BY_KIND = {
    "HTTPChaos": "httpchaos",
    "StressChaos": "stresschaos",
    "NetworkChaos": "networkchaos",
    "PodChaos": "podchaos",
    "IOChaos": "iochaos",
    "TimeChaos": "timechaos",
}

# Runtime injection is intentionally scoped to the isolated Train Ticket lab.
# This is a policy boundary, not a generator convention: hand-written YAML must
# receive the same decision as generated candidates.
ALLOWED_NAMESPACE = "train-ticket-lab"
ALLOWED_MODES = {"one"}


def run_kubectl(args: list[str], timeout: int = 20) -> tuple[int, str, str]:
    completed = subprocess.run(
        ["kubectl", *args],
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return completed.returncode, completed.stdout, completed.stderr


def kubectl_json(args: list[str]) -> tuple[Any | None, str | None]:
    code, stdout, stderr = run_kubectl([*args, "-o", "json"])
    if code != 0:
        return None, (stderr or stdout).strip()
    try:
        return json.loads(stdout), None
    except json.JSONDecodeError as exc:
        return None, f"invalid kubectl JSON: {exc}"


def ready_condition(obj: dict[str, Any]) -> bool:
    return any(
        condition.get("type") == "Ready" and condition.get("status") == "True"
        for condition in obj.get("status", {}).get("conditions", [])
    )


def selector_string(labels: dict[str, Any]) -> str:
    return ",".join(f"{key}={value}" for key, value in sorted(labels.items()))


def target_pods(namespaces: list[str], labels: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    pods: list[dict[str, Any]] = []
    errors: list[str] = []
    selector = selector_string(labels)
    for namespace in namespaces:
        args = ["get", "pods", "-n", namespace]
        if selector:
            args.extend(["-l", selector])
        data, error = kubectl_json(args)
        if error:
            errors.append(f"{namespace}: {error}")
            continue
        pods.extend(data.get("items", []))
    return pods, errors


def ports_for_pod(pod: dict[str, Any]) -> set[int]:
    ports: set[int] = set()
    for container in pod.get("spec", {}).get("containers", []):
        for port in container.get("ports", []):
            value = port.get("containerPort")
            if isinstance(value, int):
                ports.add(value)
    return ports


def chaos_components() -> tuple[dict[str, Any], list[str]]:
    data, error = kubectl_json(["get", "pods", "-n", "chaos-testing"])
    if error:
        return {"ready": False, "controller_pods": [], "daemon_pods": []}, [error]
    controllers: list[dict[str, Any]] = []
    daemons: list[dict[str, Any]] = []
    for pod in data.get("items", []):
        name = pod.get("metadata", {}).get("name", "")
        labels = pod.get("metadata", {}).get("labels", {})
        component = labels.get("app.kubernetes.io/component", "")
        if "controller-manager" in component or name.startswith("chaos-controller-manager"):
            controllers.append(pod)
        if "daemon" in component or name.startswith("chaos-daemon"):
            daemons.append(pod)
    ready = bool(controllers) and bool(daemons) and all(
        ready_condition(pod) for pod in [*controllers, *daemons]
    )
    return {
        "ready": ready,
        "controller_pods": [pod["metadata"]["name"] for pod in controllers],
        "daemon_pods": [pod["metadata"]["name"] for pod in daemons],
    }, []


def daemon_prerequisite(kind: str, daemon_names: list[str]) -> dict[str, Any]:
    result: dict[str, Any] = {
        "status": "pass",
        "evidence": "Chaos Mesh controller and daemon Pods are Ready.",
    }
    if kind != "HTTPChaos":
        return result

    log_fragments: list[str] = []
    successful_logs = 0
    for daemon in daemon_names:
        code, stdout, stderr = run_kubectl(
            ["logs", "-n", "chaos-testing", daemon, "--since=24h", "--tail=1000"],
            timeout=30,
        )
        if code == 0:
            log_fragments.append(stdout)
            successful_logs += 1
        elif stderr:
            log_fragments.append(stderr)
    combined = "\n".join(log_fragments)
    if re.search(r"ebtables.*not found|Module ebtables not found", combined, re.IGNORECASE):
        result.update(
            status="blocked",
            evidence="Chaos Daemon reported that the WSL2 kernel lacks ebtables.",
            blocker="platform_instrumentation_prerequisite_missing",
        )
    else:
        # Absence of an error is not proof that HTTPChaos can install its
        # transparent-proxy rules. Require an explicit positive signal and
        # fail closed when logs are unavailable or inconclusive.
        positive_tproxy = re.search(
            r"(?:tproxy|ebtables).*(?:ready|available|enabled|supported|loaded|success|ok)",
            combined,
            re.IGNORECASE,
        )
        if successful_logs and positive_tproxy:
            result.update(
                status="pass",
                evidence="Chaos Daemon logs contain positive tproxy/ebtables readiness evidence.",
            )
        else:
            result.update(
                status="blocked",
                evidence="No positive tproxy/ebtables readiness evidence was obtained from Chaos Daemon logs.",
                blocker="http_tproxy_positive_evidence_missing",
            )
    return result


def check_mutation(path: Path) -> dict[str, Any]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return {"mutation": str(path), "decision": "blocked", "errors": ["YAML root is not a mapping"]}

    kind = raw.get("kind")
    metadata = raw.get("metadata") or {}
    spec = raw.get("spec") or {}
    namespace = metadata.get("namespace")
    selector = spec.get("selector") or {}
    labels = selector.get("labelSelectors") or {}
    raw_namespaces = selector.get("namespaces")
    namespaces = raw_namespaces if isinstance(raw_namespaces, list) else ([namespace] if namespace else [])
    errors: list[str] = []
    checks: dict[str, Any] = {}

    requested_mode = spec.get("mode")
    namespace_ok = namespace == ALLOWED_NAMESPACE
    selector_namespaces_ok = (
        isinstance(namespaces, list)
        and bool(namespaces)
        and all(value == ALLOWED_NAMESPACE for value in namespaces)
    )
    mode_ok = requested_mode in ALLOWED_MODES
    checks["scope_guard"] = {
        "allowed_namespace": ALLOWED_NAMESPACE,
        "metadata_namespace_ok": namespace_ok,
        "selector_namespaces_ok": selector_namespaces_ok,
        "requested_namespaces": namespaces,
        "requested_mode": requested_mode,
        "allowed_modes": sorted(ALLOWED_MODES),
        "mode_ok": mode_ok,
    }
    if not namespace_ok:
        errors.append(f"mutation namespace must be {ALLOWED_NAMESPACE}")
    if not selector_namespaces_ok:
        errors.append(f"selector namespaces must be limited to {ALLOWED_NAMESPACE}")
    if not mode_ok:
        errors.append("mutation mode must be 'one'; high-blast-radius modes including 'all' are forbidden")

    checks["yaml_shape"] = bool(
        raw.get("apiVersion")
        and kind in RESOURCE_BY_KIND
        and metadata.get("name")
        and namespace
        and isinstance(spec, dict)
    )
    if not checks["yaml_shape"]:
        errors.append("missing apiVersion/kind/metadata.name/metadata.namespace/spec or unsupported kind")

    resource = RESOURCE_BY_KIND.get(kind)
    crd_name = f"{resource}.chaos-mesh.org" if resource else ""
    if crd_name:
        code, stdout, stderr = run_kubectl(["get", "crd", crd_name])
        checks["crd_exists"] = code == 0
        if code != 0:
            errors.append((stderr or stdout).strip())
    else:
        checks["crd_exists"] = False

    components, component_errors = chaos_components()
    checks["chaos_components_ready"] = components["ready"]
    if component_errors:
        errors.extend(component_errors)

    pods, pod_errors = target_pods(namespaces, labels if isinstance(labels, dict) else {})
    errors.extend(pod_errors)
    checks["selector_matches"] = bool(pods)
    checks["target_pods"] = [
        {
            "namespace": pod.get("metadata", {}).get("namespace"),
            "name": pod.get("metadata", {}).get("name"),
            "ready": ready_condition(pod),
            "restarts": sum(
                int(container.get("restartCount", 0))
                for container in pod.get("status", {}).get("containerStatuses", [])
            ),
            "ports": sorted(ports_for_pod(pod)),
        }
        for pod in pods
    ]
    checks["target_pods_ready"] = bool(pods) and all(ready_condition(pod) for pod in pods)

    requested_port = spec.get("port")
    if requested_port is None:
        checks["target_port_exists"] = True
    else:
        try:
            port_number = int(requested_port)
        except (TypeError, ValueError):
            port_number = None
        checks["target_port_exists"] = bool(
            port_number is not None and pods and all(port_number in ports_for_pod(pod) for pod in pods)
        )

    resource_code, _, resource_error = run_kubectl(
        ["get", resource or "unknown", metadata.get("name", ""), "-n", namespace]
    )
    checks["mutation_name_available"] = resource_code != 0
    if resource_code == 0:
        errors.append(f"mutation already exists: {namespace}/{metadata.get('name')}")

    injector = daemon_prerequisite(kind, components.get("daemon_pods", []))
    checks["injector_prerequisite"] = injector

    hard_checks = [
        namespace_ok,
        selector_namespaces_ok,
        mode_ok,
        checks["yaml_shape"],
        checks["crd_exists"],
        checks["chaos_components_ready"],
        checks["selector_matches"],
        checks["target_pods_ready"],
        checks["target_port_exists"],
        checks["mutation_name_available"],
        injector["status"] == "pass",
    ]
    if not namespace_ok or not selector_namespaces_ok or not mode_ok:
        decision = "blocked"
    elif not checks["yaml_shape"] or not checks["crd_exists"] or not checks["chaos_components_ready"]:
        decision = "blocked"
    elif injector["status"] == "blocked":
        decision = "blocked"
        errors.append(injector.get("blocker", "injector prerequisite blocked"))
    elif not all(hard_checks):
        decision = "not_applicable"
    else:
        decision = "ready_for_injection"

    return {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "mutation": str(path).replace("\\", "/"),
        "kind": kind,
        "namespace": namespace,
        "name": metadata.get("name"),
        "selector": {"namespaces": namespaces, "labelSelectors": labels},
        "decision": decision,
        "checks": checks,
        "errors": [error for error in errors if error],
        "interpretation": {
            "selected_is_not_injected": True,
            "defense_conclusion_allowed": decision == "ready_for_injection",
        },
        "resource_error": resource_error if resource_code != 0 else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mutations", nargs="+", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    results = [check_mutation(path) for path in args.mutations]
    report = {
        "schema_version": 1,
        "tool": "runtime_applicability_gate",
        "results": results,
        "summary": {
            "ready_for_injection": sum(result["decision"] == "ready_for_injection" for result in results),
            "blocked": sum(result["decision"] == "blocked" for result in results),
            "not_applicable": sum(result["decision"] == "not_applicable" for result in results),
        },
    }
    output = json.dumps(report, indent=2, ensure_ascii=True) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(output, encoding="utf-8")
    print(output, end="")
    return 0 if report["summary"]["blocked"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
