"""Read-only runtime applicability gate for isolated project chaos mutations."""

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

try:
    from project_onboarding import result_contract_from_gate
except ImportError:  # pragma: no cover - supports package imports
    from tools.project_onboarding import result_contract_from_gate


RESOURCE_BY_KIND = {
    "HTTPChaos": "httpchaos",
    "DNSChaos": "dnschaos",
    "StressChaos": "stresschaos",
    "NetworkChaos": "networkchaos",
    "PodChaos": "podchaos",
    "IOChaos": "iochaos",
    "TimeChaos": "timechaos",
    "JVMChaos": "jvmchaos",
    "Schedule": "schedules",
    "Workflow": "workflows",
}

# Runtime injection is intentionally scoped to isolated lab namespaces. This is
# a policy boundary, not a generator convention: hand-written YAML must receive
# the same decision as generated candidates.
# Keep both historical lab namespaces and the current revisioned runtime
# namespace explicitly listed. This remains a closed allowlist: no arbitrary
# namespace can pass the runtime injection gate.
ALLOWED_NAMESPACE = "train-ticket-lab"
ALLOWED_NAMESPACES = {
    "train-ticket-lab",
    "online-boutique-lab",
    "otel-demo-lab",
    "sock-shop-lab",
    "chaosatlas-online-boutique",
    "chaosatlas-otel",
    "chaosatlas-sock-shop",
}
ALLOWED_MODES = {"one"}


def _call_with_optional_context(function: Any, *args: Any, kube_context: str | None = None, **kwargs: Any) -> Any:
    """Preserve compatibility with older test doubles and adapters.

    An omitted context means the caller is using the active kubeconfig. In
    that case, do not add a ``kube_context=None`` keyword: older injected
    runners intentionally expose only the historical argument list.
    """
    if kube_context is None or not str(kube_context).strip():
        return function(*args, **kwargs)
    return function(*args, kube_context=kube_context, **kwargs)


def validate_scenario_phase(phase: dict[str, Any], *, namespace: str, deployment_nodes: dict[str, dict[str, Any]]) -> list[str]:
    """Pure preflight for a scenario phase before querying the cluster."""
    errors: list[str] = []
    if not isinstance(phase, dict):
        return ["phase must be an object"]
    if phase.get("mode") not in {"ordered", "concurrent"}:
        errors.append("phase mode must be ordered or concurrent")
    targets = phase.get("target_node_ids")
    if not isinstance(targets, list) or not targets:
        errors.append("phase target_node_ids required")
    for target in targets or []:
        node = deployment_nodes.get(str(target))
        if not node:
            errors.append(f"unknown deployment target: {target}")
        elif str(node.get("namespace")) != namespace:
            errors.append(f"cross-namespace deployment target: {target}")
    faults = phase.get("faults")
    if not isinstance(faults, list) or not faults:
        errors.append("phase faults required")
    if phase.get("mode") == "concurrent" and len(faults or []) < 2 and not phase.get("allow_single_target"):
        errors.append("concurrent phase requires multiple faults")
    return errors


def _contextual_args(args: list[str], kube_context: str | None) -> list[str]:
    context = str(kube_context or "").strip()
    if not context:
        return list(args)
    if not re.fullmatch(r"[A-Za-z0-9_.:@/-]+", context):
        raise ValueError("kube_context contains unsafe characters")
    return ["--context", context, *args]


def run_kubectl(args: list[str], timeout: int = 20, kube_context: str | None = None) -> tuple[int, str, str]:
    try:
        completed = subprocess.run(
            ["kubectl", *_contextual_args(args, kube_context)],
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return completed.returncode, completed.stdout, completed.stderr
    except subprocess.TimeoutExpired as exc:
        # Structured timeout: mirror kubectl's 124 exit-code convention so the
        # caller can fail closed instead of raising a raw traceback.
        out = exc.stdout if isinstance(exc.stdout, str) else ""
        err = exc.stderr if isinstance(exc.stderr, str) else ""
        return 124, out, err or "kubectl command timed out"
    except OSError as exc:
        # kubectl binary missing, pipe error, etc.: explicit non-zero result.
        return 1, "", f"kubectl invocation failed: {type(exc).__name__}: {exc}"


def kubectl_json(args: list[str], kube_context: str | None = None) -> tuple[Any | None, str | None]:
    code, stdout, stderr = _call_with_optional_context(
        run_kubectl, [*args, "-o", "json"], kube_context=kube_context
    )
    if code != 0:
        return None, (stderr or stdout).strip()
    try:
        return json.loads(stdout), None
    except json.JSONDecodeError as exc:
        return None, f"invalid kubectl JSON: {exc}"


def ready_condition(obj: dict[str, Any]) -> bool:
    return not obj.get("metadata", {}).get("deletionTimestamp") and any(
        condition.get("type") == "Ready" and condition.get("status") == "True"
        for condition in obj.get("status", {}).get("conditions", [])
    )


def selector_string(labels: dict[str, Any]) -> str:
    return ",".join(f"{key}={value}" for key, value in sorted(labels.items()))


def _kubectl_not_found(error: str | None) -> bool:
    """True only for an explicit kubectl NotFound (never timeout/RBAC/API)."""
    if not error:
        return False
    lowered = error.lower()
    return "not found" in lowered and "forbidden" not in lowered and "timed out" not in lowered


def _is_empty_selector(labels: dict[str, Any] | None) -> bool:
    """A mutation with an empty labelSelectors degrades to a whole-namespace
    query (target no longer deterministic). This is a safety boundary: reject."""
    return not labels or len(labels) == 0


def effective_chaos_spec(kind: str, spec: dict[str, Any]) -> dict[str, Any]:
    """Return the nested fault spec used by Schedule/Workflow resources."""
    if kind == "Schedule":
        nested_key = {
            "PodChaos": "podChaos",
            "NetworkChaos": "networkChaos",
            "StressChaos": "stressChaos",
            "HTTPChaos": "httpChaos",
            "DNSChaos": "dnsChaos",
            "JVMChaos": "jvmChaos",
        }.get(str(spec.get("type") or ""))
        nested = spec.get(nested_key) if nested_key else None
        return nested if isinstance(nested, dict) else {}
    if kind == "Workflow":
        for template in spec.get("templates") or []:
            if not isinstance(template, dict):
                continue
            nested_key = {
                "PodChaos": "podChaos",
                "NetworkChaos": "networkChaos",
                "StressChaos": "stressChaos",
                "HTTPChaos": "httpChaos",
                "DNSChaos": "dnsChaos",
                "JVMChaos": "jvmChaos",
            }.get(str(template.get("templateType") or ""))
            nested = template.get(nested_key) if nested_key else None
            if isinstance(nested, dict):
                return nested
    return spec


def target_pods(namespaces: list[str], labels: dict[str, Any], kube_context: str | None = None) -> tuple[list[dict[str, Any]], list[str]]:
    pods: list[dict[str, Any]] = []
    errors: list[str] = []
    selector = selector_string(labels)
    for namespace in namespaces:
        args = ["get", "pods", "-n", namespace]
        if selector:
            args.extend(["-l", selector])
        data, error = kubectl_json(args, kube_context=kube_context)
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


def chaos_components(kube_context: str | None = None) -> tuple[dict[str, Any], list[str]]:
    data, error = kubectl_json(["get", "pods", "-n", "chaos-testing"], kube_context=kube_context)
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
    gate_result = {
        "ready": ready,
        "controller_pods": [pod["metadata"]["name"] for pod in controllers],
        "daemon_pods": [pod["metadata"]["name"] for pod in daemons],
    }, []
    return gate_result


def daemon_prerequisite(kind: str, daemon_names: list[str], kube_context: str | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "status": "pass",
        "evidence": "Chaos Mesh controller and daemon Pods are Ready.",
    }
    if kind != "HTTPChaos":
        return result

    log_fragments: list[str] = []
    successful_logs = 0
    for daemon in daemon_names:
        code, stdout, stderr = _call_with_optional_context(
            run_kubectl,
            ["logs", "-n", "chaos-testing", daemon, "--since=24h", "--tail=1000"],
            timeout=30,
            kube_context=kube_context,
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
        # fail closed when logs are unavailable or inconclusive. Signals are
        # matched per line and lines containing negation words are rejected,
        # so phrases like "tproxy not supported" or "ebtables unavailable"
        # can never satisfy the positive-evidence check.
        positive_signal = re.compile(
            r"\b(?:tproxy|ebtables)\b.*\b(?:ready|available|enabled|supported|loaded|success|ok)\b",
            re.IGNORECASE,
        )
        negation_signal = re.compile(
            r"\b(?:not|no|unavailable|unsupported|disabled|missing|failed|error|cannot|can't|unable|without)\b",
            re.IGNORECASE,
        )
        has_positive_evidence = any(
            positive_signal.search(line) and not negation_signal.search(line)
            for line in combined.splitlines()
            if line.strip()
        )
        if successful_logs and has_positive_evidence:
            result.update(
                status="pass",
                evidence="Chaos Daemon logs contain positive tproxy/ebtables readiness evidence.",
                evidence_source="daemon_logs",
            )
        else:
            probe_script = (
                "ebtables -t broute -L >/dev/null 2>&1 && "
                "ebtables -t nat -L >/dev/null 2>&1 && "
                "modprobe -n ebtables >/dev/null 2>&1 && "
                "modprobe -n xt_TPROXY >/dev/null 2>&1 && "
                "iptables -t mangle -S >/dev/null 2>&1 && "
                "printf HTTPCHAOS_CAPABILITY_OK"
            )
            probe_results = []
            for daemon in daemon_names:
                code, stdout, stderr = _call_with_optional_context(
                    run_kubectl,
                    ["exec", "-n", "chaos-testing", daemon, "--", "sh", "-c", probe_script],
                    timeout=30,
                    kube_context=kube_context,
                )
                probe_results.append(
                    {
                        "daemon": daemon,
                        "passed": code == 0 and "HTTPCHAOS_CAPABILITY_OK" in stdout,
                        "error": stderr.strip() if code != 0 else "",
                    }
                )
            all_probes_passed = bool(probe_results) and all(item["passed"] for item in probe_results)
            if all_probes_passed:
                result.update(
                    status="pass",
                    evidence="All Chaos Daemon Pods passed the read-only HTTPChaos capability probe.",
                    evidence_source="read_only_daemon_capability_probe",
                    capability_probes=probe_results,
                )
            else:
                result.update(
                    status="blocked",
                    evidence=(
                        "No positive tproxy/ebtables readiness evidence was obtained from Chaos Daemon logs, "
                        "and the read-only capability probe did not pass on every daemon."
                    ),
                    blocker="http_tproxy_positive_evidence_missing",
                    capability_probes=probe_results,
                )
    return result


def _check_mutation_impl(path: Path, *, allowed_namespaces: set[str] | None = None, kube_context: str | None = None) -> dict[str, Any]:
    policy_namespaces = {
        str(item).strip() for item in (allowed_namespaces or ALLOWED_NAMESPACES) if str(item).strip()
    }
    if not policy_namespaces:
        policy_namespaces = set(ALLOWED_NAMESPACES)
    policy_namespace = sorted(policy_namespaces)[0]
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        return {
            "mutation": str(path).replace("\\", "/"),
            "kind": None,
            "namespace": None,
            "name": None,
            "decision": "blocked",
            "checks": {},
            "errors": [f"mutation YAML is not parseable: {exc}"],
            "interpretation": {
                "selected_is_not_injected": True,
                "defense_conclusion_allowed": False,
            },
        }
    if not isinstance(raw, dict):
        return {"mutation": str(path), "decision": "blocked", "errors": ["YAML root is not a mapping"]}

    kind = raw.get("kind")
    metadata = raw.get("metadata") or {}
    spec = raw.get("spec") or {}
    if not isinstance(metadata, dict):
        metadata = {}
    if not isinstance(spec, dict):
        spec = {}
    spec = effective_chaos_spec(str(kind or ""), spec)
    if "selector" not in spec and (
        isinstance(spec.get("namespaces"), list) or isinstance(spec.get("labelSelectors"), dict)
    ):
        spec = {
            **spec,
            "selector": {
                "namespaces": spec.get("namespaces") or [],
                "labelSelectors": spec.get("labelSelectors") or {},
            },
        }
    namespace = metadata.get("namespace")
    selector = spec.get("selector") or {}
    if not isinstance(selector, dict):
        selector = {}
    labels = selector.get("labelSelectors") or {}
    raw_namespaces = selector.get("namespaces")
    namespaces = raw_namespaces if isinstance(raw_namespaces, list) else ([namespace] if namespace else [])
    errors: list[str] = []
    checks: dict[str, Any] = {}

    requested_mode = spec.get("mode")
    namespace_ok = namespace in policy_namespaces
    selector_namespaces_ok = (
        isinstance(namespaces, list)
        and bool(namespaces)
        and all(value in policy_namespaces for value in namespaces)
    )
    mode_ok = requested_mode in ALLOWED_MODES
    # Phase-2 remediation (findings #2): an empty labelSelectors would degrade
    # the target query to the whole namespace, making the experiment target
    # non-deterministic. Reject it as a hard safety boundary.
    selector_labels_ok = not _is_empty_selector(labels if isinstance(labels, dict) else None)
    checks["scope_guard"] = {
        "allowed_namespace": policy_namespace,
        "allowed_namespaces": sorted(policy_namespaces),
        "metadata_namespace_ok": namespace_ok,
        "selector_namespaces_ok": selector_namespaces_ok,
        "selector_labels_ok": selector_labels_ok,
        "requested_namespaces": namespaces,
        "requested_mode": requested_mode,
        "allowed_modes": sorted(ALLOWED_MODES),
        "mode_ok": mode_ok,
    }
    if not namespace_ok:
        errors.append(f"mutation namespace must be one of {sorted(policy_namespaces)}")
    if not selector_namespaces_ok:
        errors.append(f"selector namespaces must be limited to {sorted(policy_namespaces)}")
    if not selector_labels_ok:
        errors.append("selector labelSelectors must be non-empty; empty selector degrades to a whole-namespace target")
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
        code, stdout, stderr = _call_with_optional_context(
            run_kubectl, ["get", "crd", crd_name], kube_context=kube_context
        )
        checks["crd_exists"] = code == 0
        if code != 0:
            errors.append((stderr or stdout).strip())
    else:
        checks["crd_exists"] = False

    components, component_errors = _call_with_optional_context(
        chaos_components, kube_context=kube_context
    )
    checks["chaos_components_ready"] = components["ready"]
    if component_errors:
        errors.extend(component_errors)

    # Phase-2 remediation (findings #2): never issue a whole-namespace pod query
    # for an empty selector - the gate is read-only but must not perform a
    # broad-scope lookup, and the target would be non-deterministic anyway.
    # The scope_guard error already records the rejection.
    if selector_labels_ok:
        pods, pod_errors = _call_with_optional_context(
            target_pods,
            namespaces,
            labels if isinstance(labels, dict) else {},
            kube_context=kube_context,
        )
        errors.extend(pod_errors)
    else:
        pods, pod_errors = [], []
    checks["selector_matches"] = bool(pods)
    checks["target_pods"] = [
        {
            "namespace": pod.get("metadata", {}).get("namespace"),
            "name": pod.get("metadata", {}).get("name"),
            # Round-3 P2-3: record the Pod UID so a PodChaos recovery can verify
            # that the killed identity was actually replaced (a same-UID Ready
            # Pod would mean the old one was never gone, i.e. no replacement).
            "uid": pod.get("metadata", {}).get("uid"),
            "terminating": bool(pod.get("metadata", {}).get("deletionTimestamp")),
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
        if not checks["target_port_exists"]:
            errors.append(f"target_port_missing:{requested_port}")

    resource_args = ["get", resource or "unknown", str(metadata.get("name") or "")]
    if namespace:
        resource_args.extend(["-n", str(namespace)])
    resource_code, _, resource_error = _call_with_optional_context(
        run_kubectl, resource_args, kube_context=kube_context
    )
    # Phase-2 remediation (findings #2): a mutation name is "available" ONLY when
    # kubectl reports an explicit NotFound. A timeout (124) or RBAC/API error means
    # the existence is UNKNOWN — the gate must fail closed (never treat unknown as
    # available and allow a duplicate/blocked injection).
    if resource_code == 0:
        name_status = "exists"
    elif _kubectl_not_found(resource_error):
        name_status = "available"
    elif resource_code == 124:
        name_status = "unknown_timeout"
    else:
        name_status = "unknown_error"
    checks["mutation_name_available"] = name_status == "available"
    checks["mutation_name_status"] = name_status
    checks["mutation_name_error"] = (resource_error or "").strip()
    if resource_code == 0:
        errors.append(f"mutation already exists: {namespace}/{metadata.get('name')}")
    elif name_status.startswith("unknown"):
        errors.append(
            f"mutation name lookup is {name_status}; cannot confirm availability, failing closed: {resource_error}".strip()
        )

    injector = _call_with_optional_context(
        daemon_prerequisite,
        kind,
        components.get("daemon_pods", []),
        kube_context=kube_context,
    )
    checks["injector_prerequisite"] = injector

    hard_checks = [
        namespace_ok,
        selector_namespaces_ok,
        selector_labels_ok,
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
    if not namespace_ok or not selector_namespaces_ok or not selector_labels_ok or not mode_ok:
        decision = "blocked"
    elif checks.get("mutation_name_status") in ("unknown_timeout", "unknown_error", "exists"):
        # Phase-2: a name-lookup failure (timeout/RBAC) or an existing resource
        # must yield a structured BLOCKED, not not_applicable - we cannot
        # confirm the injection is safe to run.
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
    gate_result["result_contract"] = result_contract_from_gate(gate_result)
    return gate_result


def check_mutation(path: Path, *, allowed_namespaces: set[str] | None = None, kube_context: str | None = None) -> dict[str, Any]:
    """Public entry: never raises on real-world kubectl exceptions.

    ``_check_mutation_impl`` already benefits from ``run_kubectl`` swallowing
    ``TimeoutExpired``/``OSError``; this wrapper is a final fail-closed guard so
    an unexpected exception still yields ``decision="blocked"`` instead of a
    traceback (which would otherwise abort the whole candidate pipeline).
    """
    try:
        return _check_mutation_impl(path, allowed_namespaces=allowed_namespaces, kube_context=kube_context)
    except Exception as exc:  # noqa: BLE001 - the gate must fail closed
        policy_namespaces = sorted(
            {
                str(item).strip()
                for item in (allowed_namespaces or ALLOWED_NAMESPACES)
                if str(item).strip()
            }
            or ALLOWED_NAMESPACES
        )
        failure = f"unexpected gate failure: {type(exc).__name__}: {exc}"
        return {
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "mutation": str(path).replace("\\", "/"),
            "kind": None,
            "namespace": None,
            "name": None,
            "selector": None,
            "decision": "blocked",
            "checks": {
                "scope_guard": {
                    "allowed_namespace": policy_namespaces[0],
                    "allowed_namespaces": policy_namespaces,
                    "metadata_namespace_ok": False,
                    "selector_namespaces_ok": False,
                    "selector_labels_ok": False,
                    "requested_namespaces": [],
                    "requested_mode": None,
                    "allowed_modes": sorted(ALLOWED_MODES),
                    "mode_ok": False,
                },
                "yaml_shape": False,
                "crd_exists": False,
                "chaos_components_ready": False,
                "selector_matches": False,
                "target_pods": [],
                "target_pods_ready": False,
                "target_port_exists": False,
                "mutation_name_available": False,
                "mutation_name_status": "unknown_error",
                "mutation_name_error": failure,
                "injector_prerequisite": {
                    "status": "blocked",
                    "evidence": "Gate terminated before all runtime checks completed.",
                    "blocker": "unexpected_gate_failure",
                },
            },
            "errors": [failure],
            "interpretation": {
                "selected_is_not_injected": True,
                "defense_conclusion_allowed": False,
            },
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
