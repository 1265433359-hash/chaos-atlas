"""Execute one Sock Shop mutation with the paper lifecycle contract.

The runner owns the business oracle and the full baseline -> injection ->
observation -> recovery -> cleanup -> washout sequence.  It is deliberately
namespace-local and records pending human review instead of promoting a
runtime symptom into the knowledge base.
"""

from __future__ import annotations

import argparse
import base64
import http.cookiejar
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import HTTPCookieProcessor, Request, build_opener, urlopen

import yaml

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from run_chaos_experiment import (  # noqa: E402
    check_mutation,
    delete_resource,
    lifecycle_snapshot,
    kubectl_json,
    now,
    run_kubectl,
    start_port_forward,
    stop_process,
    wait_for_lifecycle,
    wait_for_port,
    wait_for_target_ready,
)


NAMESPACE = "chaosatlas-sock-shop"
TARGETS = {
    "carts", "carts-db", "catalogue", "catalogue-db", "front-end", "orders", "orders-db",
    "payment", "queue-master", "rabbitmq", "session-db", "shipping", "user", "user-db",
}
STEPS = (("front-end", "/"), ("catalogue", "/catalogue"), ("login", "/login"), ("orders", "/orders"))
CHAOS_RESOURCES = ("podchaos", "networkchaos", "stresschaos", "httpchaos", "dnschaos", "schedules", "workflows")
EXPECTED_STATUS = {"front-end": 200, "catalogue": 200, "login": 200, "orders": 201}
DEMO_LOGIN = base64.b64encode(b"user:password").decode("ascii")
WINDOWS_PATH_SAFE_LIMIT = 240


def oracle_passes(samples: list[dict[str, Any]]) -> bool:
    required = set(EXPECTED_STATUS)
    return (
        {str(item.get("step")) for item in samples} == required
        and all(item.get("status_code") == EXPECTED_STATUS.get(str(item.get("step"))) and item.get("contract_ok") is True for item in samples)
    )


def contract_ok(step: str, body: str) -> bool:
    if step == "front-end":
        return bool(body.strip()) and "<html" in body.lower()
    if step == "login":
        return body.strip() == "Cookie is set"
    try:
        value = json.loads(body)
    except json.JSONDecodeError:
        return False
    return isinstance(value, list) if step == "catalogue" else isinstance(value, (list, dict))


def classify_observation(journeys: list[dict[str, Any]]) -> str:
    if not journeys:
        return "observation_incomplete"
    return "no_business_impact_observed" if all(item.get("pass") is True for item in journeys) else "weakness_observed"


def validate_mutation(document: dict[str, Any]) -> dict[str, Any]:
    metadata = document.get("metadata") or {}
    spec = document.get("spec") or {}
    kind = document.get("kind")
    effective_spec = spec
    if kind == "Schedule":
        if spec.get("type") != "PodChaos" or not isinstance(spec.get("podChaos"), dict):
            return {"status": "blocked", "errors": ["Schedule must wrap a PodChaos template"]}
        effective_spec = spec["podChaos"]
    selector = effective_spec.get("selector") or {}
    labels = selector.get("labelSelectors") or {}
    errors: list[str] = []
    if kind not in {"PodChaos", "NetworkChaos", "StressChaos", "HTTPChaos", "DNSChaos", "Schedule"}:
        errors.append("unsupported chaos kind")
    if metadata.get("namespace") != NAMESPACE or selector.get("namespaces") != [NAMESPACE]:
        errors.append("namespace is not exact")
    if set(labels) != {"name"} or labels.get("name") not in TARGETS:
        errors.append("selector target is not an allowed Sock Shop workload")
    if effective_spec.get("mode") != "one":
        errors.append("mode must be one")
    if kind in {"PodChaos", "Schedule"} and effective_spec.get("action") != "pod-kill":
        errors.append("PodChaos action must be pod-kill")
    if kind == "HTTPChaos" and effective_spec.get("target") not in {"Request", "Response"}:
        errors.append("HTTPChaos target must be Request or Response")
    return {"status": "passed" if not errors else "blocked", "errors": errors}


def global_residuals() -> tuple[list[dict[str, str]], list[str]]:
    residuals: list[dict[str, str]] = []
    errors: list[str] = []
    for resource in CHAOS_RESOURCES:
        data, error = kubectl_json(["get", resource, "-A"])
        if error:
            errors.append(error)
            continue
        for item in data.get("items", []):
            metadata = item.get("metadata") or {}
            residuals.append({"kind": str(item.get("kind", resource)), "namespace": str(metadata.get("namespace", "")), "name": str(metadata.get("name", ""))})
    return residuals, errors


def schedule_child_names(schedule: dict[str, Any], children: list[dict[str, Any]]) -> list[str]:
    """Return PodChaos children owned by one Schedule, in stable name order."""
    schedule_uid = str((schedule.get("metadata") or {}).get("uid") or "")
    if not schedule_uid:
        return []
    names: list[str] = []
    for child in children:
        metadata = child.get("metadata") or {}
        owner_references = metadata.get("ownerReferences") or []
        if any(
            isinstance(owner, dict)
            and owner.get("kind") == "Schedule"
            and str(owner.get("uid") or "") == schedule_uid
            for owner in owner_references
        ):
            name = metadata.get("name")
            if name:
                names.append(str(name))
    return sorted(set(names))


def _schedule_children(namespace: str, schedule_name: str) -> tuple[dict[str, Any] | None, list[dict[str, Any]], list[str]]:
    schedule, schedule_error = kubectl_json(["get", "schedules", schedule_name, "-n", namespace])
    errors: list[str] = []
    if schedule is None:
        if schedule_error and "not found" not in schedule_error.lower():
            errors.append(schedule_error)
        return None, [], errors
    children_data, children_error = kubectl_json(["get", "podchaos", "-n", namespace, "-o", "json"])
    if children_data is None:
        if children_error:
            errors.append(children_error)
        return schedule, [], errors
    children = [item for item in children_data.get("items", []) if isinstance(item, dict)]
    names = set(schedule_child_names(schedule, children))
    selected = [item for item in children if str((item.get("metadata") or {}).get("name") or "") in names]
    return schedule, selected, errors


def wait_for_scheduled_lifecycle(
    namespace: str,
    schedule_name: str,
    predicate: str,
    timeout: float,
    interval: float,
) -> tuple[bool, dict[str, Any], list[str]]:
    """Observe the generated PodChaos, because Schedule has no fault lifecycle of its own."""
    deadline = time.monotonic() + max(0.1, timeout)
    errors: list[str] = []
    last: dict[str, Any] = {"schedule_name": schedule_name, "children": []}
    while time.monotonic() <= deadline:
        schedule, children, poll_errors = _schedule_children(namespace, schedule_name)
        errors.extend(poll_errors)
        last = {
            "schedule_name": schedule_name,
            "schedule_uid": (schedule.get("metadata") or {}).get("uid") if schedule else None,
            "children": [],
        }
        for child in children:
            metadata = child.get("metadata") or {}
            child_name = str(metadata.get("name") or "")
            snapshot = lifecycle_snapshot(child)
            last["children"].append({"name": child_name, "lifecycle": snapshot})
            injected = snapshot.get("injected_count", 0) >= 1
            recovered = injected and (
                snapshot.get("all_recovered")
                or snapshot.get("recovered_count", 0) >= snapshot.get("injected_count", 0)
            )
            if (predicate == "injected" and injected) or (predicate == "recovered" and recovered):
                last["selected_child"] = child_name
                last["selected_lifecycle"] = snapshot
                return True, last, errors
        time.sleep(max(0.1, interval))
    return False, last, errors


def delete_schedule_with_children(namespace: str, schedule_name: str, known_children: list[str] | None = None) -> dict[str, Any]:
    """Delete a Schedule and any generated PodChaos children, verifying both."""
    _schedule, children, errors = _schedule_children(namespace, schedule_name)
    child_names = sorted(set(known_children or []) | {str((item.get("metadata") or {}).get("name")) for item in children})
    parent_cleanup = delete_resource("Schedule", namespace, schedule_name)
    child_cleanup = [delete_resource("PodChaos", namespace, name) for name in child_names if name and name != "None"]
    absent = bool(parent_cleanup.get("absent_confirmed")) and all(item.get("absent_confirmed") for item in child_cleanup)
    return {
        "absent_confirmed": absent,
        "schedule": parent_cleanup,
        "children": child_cleanup,
        "known_child_names": child_names,
        "errors": errors,
    }


def request_step(port: int, step: str, path: str, timeout: float = 15, *, opener: Any | None = None) -> dict[str, Any]:
    started = time.monotonic()
    try:
        request = Request(f"http://127.0.0.1:{port}{path}")
        if step == "login":
            request.add_header("Authorization", f"Basic {DEMO_LOGIN}")
        client = opener or urlopen
        with client(request, timeout=timeout) as response:
            body = response.read(1_000_000).decode("utf-8", errors="replace")
            ok = response.status == EXPECTED_STATUS[step] and contract_ok(step, body)
            return {"step": step, "path": path, "status_code": response.status, "latency_ms": round((time.monotonic() - started) * 1000, 3), "body_sha256": hashlib.sha256(body.encode()).hexdigest(), "contract_ok": contract_ok(step, body), "pass": ok, "error": None}
    except (HTTPError, URLError, OSError, TimeoutError) as exc:
        return {"step": step, "path": path, "status_code": getattr(exc, "code", None), "latency_ms": round((time.monotonic() - started) * 1000, 3), "body_sha256": None, "contract_ok": False, "pass": False, "error": str(exc)}


def diagnostics_directory(report_path: Path) -> Path:
    directory = report_path.parent / f"{report_path.stem}.diagnostics"
    # report_path is often relative when launched by the batch planner.  Windows
    # enforces the absolute path length, so the safety check must include cwd.
    if len(str((directory / "front-end.log").resolve())) < WINDOWS_PATH_SAFE_LIMIT:
        return directory
    digest = hashlib.sha256(str(report_path).encode("utf-8")).hexdigest()[:12]
    short_directory = report_path.parent.parent / f"d-{digest}"
    if len(str((short_directory / "front-end.log").resolve())) >= WINDOWS_PATH_SAFE_LIMIT:
        return Path.cwd() / f"d-{digest}"
    return short_directory


def run_journey(port: int = 18081) -> dict[str, Any]:
    opener = build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar())).open
    samples = [request_step(port, step, path, opener=opener) for step, path in STEPS]
    return {"pass": oracle_passes(samples), "samples": samples}


def consecutive_successes(journeys: list[dict[str, Any]]) -> int:
    count = 0
    for journey in journeys:
        count = count + 1 if journey.get("pass") is True else 0
    return count


def is_local_port_forward_failure(journey: dict[str, Any]) -> bool:
    samples = journey.get("samples")
    if not isinstance(samples, list) or not samples or journey.get("pass") is True:
        return False
    return all(
        sample.get("status_code") is None
        and isinstance(sample.get("error"), str)
        and ("WinError 10061" in sample["error"] or "connection refused" in sample["error"].lower())
        for sample in samples
    )


def capture_diagnostics(report_path: Path, selector: str) -> dict[str, Any]:
    directory = diagnostics_directory(report_path)
    directory.mkdir(parents=True, exist_ok=True)
    commands = {
        "front-end.log": ["logs", "-n", NAMESPACE, "deployment/front-end", "--tail=500"],
        "catalogue.log": ["logs", "-n", NAMESPACE, "deployment/catalogue", "--tail=500"],
        "orders.log": ["logs", "-n", NAMESPACE, "deployment/orders", "--tail=500"],
        "target.log": ["logs", "-n", NAMESPACE, "-l", selector, "--tail=500"],
        "events.json": ["get", "events", "-n", NAMESPACE, "-o", "json"],
    }
    files: list[dict[str, Any]] = []
    for filename, command in commands.items():
        code, out, err = run_kubectl(command, timeout=60)
        path = directory / filename
        content = out if code == 0 else json.dumps({"status": "unavailable", "stderr": err, "stdout": out}) + "\n"
        path.write_text(content, encoding="utf-8")
        files.append({"path": str(path).replace("\\", "/"), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "return_code": code})
    trace = directory / "zipkin.json"
    trace.write_text(json.dumps({"status": "unavailable", "reason": "frozen Sock Shop input has no trace backend"}, indent=2) + "\n", encoding="utf-8")
    files.append({"path": str(trace).replace("\\", "/"), "sha256": hashlib.sha256(trace.read_bytes()).hexdigest(), "return_code": 0})
    return {"status": "captured", "files": files}


def run_one(mutation: Path, report_path: Path, arm: str, seed: int, hypothesis_id: str, replicate: int, *, baseline_count: int = 5, recovery_timeout: float = 180, washout_seconds: float = 60, washout_successes: int = 10, washout_timeout: float = 180) -> dict[str, Any]:
    if report_path.exists():
        raise FileExistsError(report_path)
    report: dict[str, Any] = {"schema_version": "sock-shop-two-arm-lifecycle-v1", "project_id": "sock-shop", "namespace": NAMESPACE, "arm": arm, "seed": seed, "mutation_id": hypothesis_id, "replicate": replicate, "mutation": {"path": str(mutation).replace("\\", "/"), "sha256": hashlib.sha256(mutation.read_bytes()).hexdigest()}, "baseline": {"pass": False}, "injection": {"applied": False, "injected": False}, "observation": {}, "recovery": {"recovered": False}, "cleanup": {"absent_confirmed": False, "residual_resources": []}, "washout": {"stable": False}, "diagnostics": {"status": "pending"}, "human_review": "pending", "knowledge_base_updated": False, "status": "running", "errors": [], "started_at": now()}
    process: subprocess.Popen[str] | None = None
    kind = name = None
    applied = False
    selector_query = ""
    schedule_children: list[str] = []
    try:
        document = yaml.safe_load(mutation.read_text(encoding="utf-8"))
        report["mutation_gate"] = validate_mutation(document)
        if report["mutation_gate"]["status"] != "passed":
            raise RuntimeError("Sock Shop mutation validation blocked")
        preflight = check_mutation(mutation)
        report["preflight"] = preflight
        if preflight.get("decision") != "ready_for_injection":
            raise RuntimeError(f"runtime applicability gate: {preflight.get('decision')}")
        kind, name = preflight["kind"], preflight["name"]
        effective_spec = document.get("spec") or {}
        if document.get("kind") == "Schedule":
            effective_spec = effective_spec.get("podChaos") or {}
        labels = (effective_spec.get("selector") or {}).get("labelSelectors") or {}
        selector_query = ",".join(f"{key}={value}" for key, value in sorted(labels.items()))
        process = start_port_forward(NAMESPACE, "front-end", 18081, 80)
        wait_for_port("127.0.0.1", 18081, process, 30)
        # Establish a failure-free oracle immediately before injection.  A
        # failed baseline invalidates the mutation result rather than becoming
        # evidence of a weakness.
        baseline = [run_journey() for _ in range(baseline_count)]
        report["baseline"] = {"pass": len(baseline) == baseline_count and all(item["pass"] for item in baseline), "journeys": baseline, "successes_required": baseline_count}
        if not report["baseline"]["pass"]:
            raise RuntimeError("Sock Shop baseline was not failure-free")
        # Apply only after static and runtime gates pass; the lifecycle report
        # must distinguish an accepted YAML from an actually injected fault.
        code, out, err = run_kubectl(["apply", "-f", str(mutation)])
        report["injection"]["apply"] = {"return_code": code, "stdout": out.strip(), "stderr": err.strip()}
        if code != 0:
            raise RuntimeError("Chaos apply failed")
        applied = True
        report["injection"]["applied"] = True
        # Scheduled faults create child Chaos resources.  Remove parent and
        # child objects together before judging recovery or washout.
        if kind == "Schedule":
            injected, lifecycle, errors = wait_for_scheduled_lifecycle(NAMESPACE, name, "injected", 90, 0.5)
            schedule_children = [str(lifecycle.get("selected_child"))] if lifecycle.get("selected_child") else []
        else:
            injected, lifecycle, errors = wait_for_lifecycle(kind, NAMESPACE, name, "injected", 90, 0.5)
        report["injection"].update({"injected": injected, "lifecycle": lifecycle})
        report["errors"].extend(errors)
        if not injected:
            raise RuntimeError("injection not confirmed")
        observed = [run_journey() for _ in range(baseline_count)]
        report["observation"] = {"journeys": observed, "classification": classify_observation(observed)}
        targets = ((preflight.get("checks") or {}).get("target_pods") or [])
        if kind == "Schedule":
            cleanup = delete_schedule_with_children(NAMESPACE, name, schedule_children)
            applied = False
            residuals, residual_errors = global_residuals()
            report["cleanup"] = {**cleanup, "residual_resources": residuals, "global_scan_errors": residual_errors}
            if not cleanup.get("absent_confirmed") or residuals or residual_errors:
                raise RuntimeError("cleanup/global residual gate failed")

        # PodKill recovery is verified through replacement Pod identity and
        # readiness; other kinds use the Chaos Mesh recovered lifecycle state.
        if kind in {"PodChaos", "Schedule"}:
            pre_uids = {str(item.get("uid")) for item in targets if item.get("uid")}
            recovered, state, errors = wait_for_target_ready(NAMESPACE, {"labelSelectors": labels}, 240, 1, expected_pod_count=len(targets) or None, pre_kill_uids=pre_uids)
        else:
            recovered, state, errors = wait_for_lifecycle(kind, NAMESPACE, name, "recovered", 180, 1)
        report["recovery"].update({"resource_recovered": recovered, "state": state})
        report["errors"].extend(errors)
        if kind != "Schedule":
            cleanup = delete_resource(kind, NAMESPACE, name)
            applied = False
            residuals, residual_errors = global_residuals()
            report["cleanup"] = {**cleanup, "residual_resources": residuals, "global_scan_errors": residual_errors}
            if not cleanup.get("absent_confirmed") or residuals or residual_errors:
                raise RuntimeError("cleanup/global residual gate failed")
        # PodKill can replace the Pod selected by the service port-forward, and
        # NetworkChaos can terminate the forwarding path itself. Rebind only
        # after the Chaos resource is gone so recovery is judged on a clean path.
        def rebind_port_forward() -> None:
            nonlocal process
            stop_process(process)
            process = start_port_forward(NAMESPACE, "front-end", 18081, 80)
            wait_for_port("127.0.0.1", 18081, process, 30)
            report["recovery"]["port_forward_rebinds"] = int(report["recovery"].get("port_forward_rebinds", 0)) + 1

        def ensure_port_forward_alive() -> None:
            poll = getattr(process, "poll", None)
            if process is None or (callable(poll) and poll() is not None):
                rebind_port_forward()

        if recovered:
            rebind_port_forward()
            report["recovery"]["port_forward_restarted"] = True
        recovery_journeys: list[dict[str, Any]] = []
        report["recovery"]["successes_required"] = baseline_count
        report["recovery"]["timeout_seconds"] = recovery_timeout
        deadline = time.monotonic() + recovery_timeout
        while time.monotonic() < deadline and consecutive_successes(recovery_journeys) < baseline_count:
            ensure_port_forward_alive()
            journey = run_journey()
            recovery_journeys.append(journey)
            if is_local_port_forward_failure(journey):
                rebind_port_forward()
            time.sleep(2)
        report["recovery"].update({"journeys": recovery_journeys, "recovered": bool(recovered and consecutive_successes(recovery_journeys) >= baseline_count)})
        if not report["recovery"]["recovered"]:
            raise RuntimeError("business recovery failed")
        # Washout is a separate stability window: recovery proves the fault
        # ended, while washout proves no residual fault or stale port-forward
        # continues to affect the next mutation.
        washout_started = time.monotonic()
        journeys: list[dict[str, Any]] = []
        report["washout"] = {
            "stable": False,
            "journeys": journeys,
            "elapsed_seconds": 0.0,
            "successes_required": washout_successes,
            "consecutive_successes": 0,
        }
        while time.monotonic() - washout_started < washout_timeout:
            ensure_port_forward_alive()
            journey = run_journey()
            journeys.append(journey)
            if is_local_port_forward_failure(journey):
                rebind_port_forward()
            elapsed = time.monotonic() - washout_started
            report["washout"].update(
                {
                    "elapsed_seconds": round(elapsed, 3),
                    "consecutive_successes": consecutive_successes(journeys),
                }
            )
            if elapsed >= washout_seconds and consecutive_successes(journeys) >= washout_successes:
                report["washout"]["stable"] = True
                break
            time.sleep(3)
        if not report["washout"].get("stable"):
            raise RuntimeError("washout failed")
        target_ready, target_state, target_ready_errors = wait_for_target_ready(
            NAMESPACE,
            {"labelSelectors": labels},
            recovery_timeout,
            1,
            expected_pod_count=len(targets) or None,
        )
        report["washout"].update(
            {
                "target_ready": target_ready,
                "target_state": target_state,
                "target_ready_errors": target_ready_errors,
            }
        )
        report["errors"].extend(target_ready_errors)
        if not target_ready:
            raise RuntimeError("target readiness recovery failed")
        report["diagnostics"] = capture_diagnostics(report_path, selector_query)
        report["status"] = "completed"
    except Exception as exc:
        report["errors"].append(f"{type(exc).__name__}: {exc}")
        report["status"] = "failed"
    finally:
        if applied and kind and name:
            cleanup = delete_schedule_with_children(NAMESPACE, name, schedule_children) if kind == "Schedule" else delete_resource(kind, NAMESPACE, name)
            residuals, residual_errors = global_residuals()
            report["cleanup"] = {**cleanup, "residual_resources": residuals, "global_scan_errors": residual_errors}
        if report["diagnostics"].get("status") == "pending" and selector_query:
            try:
                report["diagnostics"] = capture_diagnostics(report_path, selector_query)
            except Exception as exc:
                report["diagnostics"] = {
                    "status": "unavailable",
                    "error": f"{type(exc).__name__}: {exc}",
                }
        report["port_forward"] = stop_process(process)
        report["finished_at"] = now()
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mutation", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--arm", required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--hypothesis-id", required=True)
    parser.add_argument("--replicate", type=int, required=True)
    parser.add_argument("--recovery-timeout", type=float, default=180)
    args = parser.parse_args()
    result = run_one(
        args.mutation,
        args.report,
        args.arm,
        args.seed,
        args.hypothesis_id,
        args.replicate,
        recovery_timeout=args.recovery_timeout,
    )
    print(json.dumps({"status": result["status"], "classification": (result.get("observation") or {}).get("classification"), "errors": result["errors"]}))
    return 0 if result["status"] == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
