from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.run_sock_shop_two_arm import NAMESPACE, TARGETS


TIMING_FIELDS = [
    "generation_seconds",
    "compile_seconds",
    "gate_seconds",
    "runtime_seconds",
    "washout_seconds",
    "total_wall_clock_seconds",
]


# These routes were checked against the frozen Sock Shop services on
# 2026-08-15.  HTTPChaos selects the target Pod, so front-end uses its Pod
# port (8079), not the Service port (80).  The wildcard suffixes cover the
# concrete resource IDs used by the real call chain.
SOCK_SHOP_HTTP_ROUTES: dict[str, dict[str, Any]] = {
    "front-end": {
        "port": 8079,
        "path": "*",
        "source": "sock-shop-call-chain:front-end-golden-journeys-live-probe",
    },
    "carts": {
        "port": 80,
        "path": "/carts*",
        "source": "sock-shop-call-chain:front-end->carts",
    },
    "catalogue": {
        "port": 80,
        "path": "/catalogue*",
        "source": "sock-shop-call-chain:front-end->catalogue",
    },
    "orders": {
        "port": 80,
        "path": "/orders*",
        "source": "sock-shop-call-chain:front-end->orders",
    },
    "payment": {
        "port": 80,
        "path": "/paymentAuth*",
        "source": "sock-shop-call-chain:orders->payment",
    },
    "shipping": {
        "port": 80,
        "path": "/shipping*",
        "source": "sock-shop-call-chain:orders->shipping",
    },
    "user": {
        "port": 80,
        "path": "/login*",
        "source": "sock-shop-call-chain:front-end->user",
    },
    "queue-master": {
        "port": 80,
        "path": "/",
        "source": "sock-shop-supporting-service:live-probe-root",
    },
}

HTTP_NON_BUSINESS_TARGETS = {
    "carts-db",
    "catalogue-db",
    "orders-db",
    "rabbitmq",
    "session-db",
    "user-db",
}

SOCK_SHOP_DNS_SUFFIX = ".chaosatlas-sock-shop.svc.cluster.local"

# DNSChaos selects the Pod that issues the lookup.  The fault target is the
# downstream service name, so keep the source and destination explicit.
SOCK_SHOP_DNS_ROUTES: dict[str, dict[str, Any]] = {
    "front-end": {
        "selector": "front-end",
        "patterns": [
            f"carts{SOCK_SHOP_DNS_SUFFIX}",
            f"catalogue{SOCK_SHOP_DNS_SUFFIX}",
        ],
        "source": "sock-shop-call-chain:front-end->carts,catalogue",
    },
    "carts": {
        "selector": "front-end",
        "patterns": [f"carts{SOCK_SHOP_DNS_SUFFIX}"],
        "source": "sock-shop-call-chain:front-end->carts",
    },
    "catalogue": {
        "selector": "front-end",
        "patterns": [f"catalogue{SOCK_SHOP_DNS_SUFFIX}"],
        "source": "sock-shop-call-chain:front-end->catalogue",
    },
    "orders": {
        "selector": "front-end",
        "patterns": [f"orders{SOCK_SHOP_DNS_SUFFIX}"],
        "source": "sock-shop-call-chain:front-end->orders",
    },
    "payment": {
        "selector": "orders",
        "patterns": [f"payment{SOCK_SHOP_DNS_SUFFIX}"],
        "source": "sock-shop-call-chain:orders->payment",
    },
    "shipping": {
        "selector": "orders",
        "patterns": [f"shipping{SOCK_SHOP_DNS_SUFFIX}"],
        "source": "sock-shop-call-chain:orders->shipping",
    },
    "user": {
        "selector": "front-end",
        "patterns": [f"user{SOCK_SHOP_DNS_SUFFIX}"],
        "source": "sock-shop-call-chain:front-end->user",
    },
    "queue-master": {
        "selector": "queue-master",
        "patterns": [f"rabbitmq{SOCK_SHOP_DNS_SUFFIX}"],
        "source": "sock-shop-call-chain:queue-master->rabbitmq",
    },
}


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9-]+", "-", value.lower()).strip("-")
    return slug[:48] or "hypothesis"


def _mutation_name(hypothesis: dict[str, Any]) -> str:
    raw = str(hypothesis.get("id") or hypothesis.get("hypothesis_id") or hypothesis.get("target_service") or "h")
    digest = hashlib.sha256(json.dumps(hypothesis, sort_keys=True).encode("utf-8")).hexdigest()[:8]
    return f"yc-{_slug(raw)}-{digest}"[:63]


def _http_route(target: str) -> tuple[dict[str, Any] | None, str | None]:
    route = SOCK_SHOP_HTTP_ROUTES.get(target)
    if route is not None:
        return dict(route), None
    if target in HTTP_NON_BUSINESS_TARGETS:
        return None, f"http_target_not_applicable:{target}"
    return None, f"http_target_route_unknown:{target}"


def _kind_and_spec(hypothesis: dict[str, Any]) -> tuple[str | None, dict[str, Any], str | None]:
    category = hypothesis.get("category")
    action = str(hypothesis.get("action_or_target") or "").lower()
    target = str(hypothesis.get("target_service") or "")
    if category == "Pod disruption":
        return "PodChaos", {"action": "pod-kill"}, None
    if category == "Network degradation":
        if action in {"delay", "network_delay"}:
            return "NetworkChaos", {"action": "delay", "duration": "30s", "delay": {"latency": "500ms", "correlation": "100", "jitter": "0ms"}}, None
        if action in {"loss", "network_loss"}:
            return "NetworkChaos", {"action": "loss", "duration": "30s", "loss": {"loss": "50", "correlation": "100"}}, None
        if action == "partition":
            return "NetworkChaos", {"action": "partition", "duration": "30s", "direction": "to"}, None
        return None, {}, "unsupported_network_action"
    if category == "Resource pressure":
        if action in {"memory", "stress_memory"}:
            return "StressChaos", {"duration": "30s", "stressors": {"memory": {"workers": 1, "size": "256MB"}}}, None
        return "StressChaos", {"duration": "30s", "stressors": {"cpu": {"workers": 1, "load": 50}}}, None
    if category == "Protocol/HTTP fault":
        route, route_error = _http_route(target)
        if route_error:
            return None, {}, route_error
        if action in {"abort", "http_abort"}:
            return "HTTPChaos", {
                "target": "Response",
                "abort": True,
                "port": route["port"],
                "path": route["path"],
                "duration": "30s",
            }, None
        if action in {"delay", "http_delay"}:
            return "HTTPChaos", {
                "target": "Request",
                "delay": "500ms",
                "port": route["port"],
                "path": route["path"],
                "duration": "30s",
            }, None
        if action in {"dns", "dns_error"}:
            route = SOCK_SHOP_DNS_ROUTES.get(target)
            if route is None:
                return None, {}, f"dns_target_route_unknown:{target}"
            return "DNSChaos", {
                "action": "error",
                "patterns": list(route["patterns"]),
                "duration": "30s",
            }, None
        return None, {}, "unsupported_protocol_action"
    if category == "Composite/scheduled fault":
        if action in {"scheduled-delay", "scheduled-pod-kill", "schedule"}:
            return "Schedule", {
                "type": "PodChaos",
                "schedule": "@every 30s",
                "concurrencyPolicy": "Forbid",
                "historyLimit": 1,
                "podChaos": {
                    "action": "pod-kill",
                    "mode": "one",
                    "duration": "10s",
                },
            }, None
        return None, {}, "unsupported_composite_action"
    return None, {}, "runner_unsupported_category"


def _is_runtime_candidate(hypothesis: dict[str, Any]) -> bool:
    target = str(hypothesis.get("target_service") or "")
    _kind, _extra_spec, reason = _kind_and_spec(hypothesis)
    return reason is None and target in TARGETS


def compile_hypothesis_to_mutation(hypothesis: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    target = str(hypothesis.get("target_service") or "")
    kind, extra_spec, reason = _kind_and_spec(hypothesis)
    if reason:
        return {
            "hypothesis_id": hypothesis.get("id") or hypothesis.get("hypothesis_id"),
            "target_service": target,
            "kind": None,
            "path": None,
            "sha256": None,
            "gate": {"status": "failed", "reason": reason},
            "method": hypothesis.get("method"),
            "category": hypothesis.get("category"),
        }
    if target not in TARGETS:
        return {
            "hypothesis_id": hypothesis.get("id") or hypothesis.get("hypothesis_id"),
            "target_service": target,
            "kind": kind,
            "path": None,
            "sha256": None,
            "gate": {"status": "failed", "reason": "target_not_in_sock_shop_profile"},
            "method": hypothesis.get("method"),
            "category": hypothesis.get("category"),
        }

    name = _mutation_name(hypothesis)
    selector_target = target
    if kind == "DNSChaos":
        selector_target = str(SOCK_SHOP_DNS_ROUTES[target]["selector"])
    selector = {"namespaces": [NAMESPACE], "labelSelectors": {"name": selector_target}}
    if kind == "Schedule":
        nested = dict(extra_spec["podChaos"])
        nested["selector"] = selector
        spec = {key: value for key, value in extra_spec.items() if key != "podChaos"}
        spec["podChaos"] = nested
    else:
        spec = {
            "mode": "one",
            "selector": selector,
            **extra_spec,
        }
    document = {
        "apiVersion": "chaos-mesh.org/v1alpha1",
        "kind": kind,
        "metadata": {"name": name, "namespace": NAMESPACE},
        "spec": spec,
    }
    path = output_dir / "mutations" / f"{name}.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    content = yaml.safe_dump(document, sort_keys=False)
    if path.exists() and path.read_text(encoding="utf-8") != content:
        raise FileExistsError(f"refusing to overwrite existing mutation with different content: {path}")
    path.write_text(content, encoding="utf-8")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    result = {
        "hypothesis_id": hypothesis.get("id") or hypothesis.get("hypothesis_id") or name,
        "target_service": target,
        "kind": kind,
        "name": name,
        "path": str(path),
        "sha256": digest,
        "gate": {"status": "passed", "reason": "static_compiled"},
        "method": hypothesis.get("method"),
        "category": hypothesis.get("category"),
        "hypothesis": hypothesis,
    }
    if kind == "HTTPChaos":
        route, route_error = _http_route(target)
        if route_error or route is None:
            raise ValueError(route_error or "http route resolution failed")
        result["http_route"] = route
    if kind == "DNSChaos":
        result["dns_route"] = SOCK_SHOP_DNS_ROUTES[target]
    return result


def build_runtime_invocation(
    candidate: dict[str, Any],
    report_path: Path,
    execute: bool,
    *,
    replicate: int,
    seed: int = 0,
    recovery_timeout: float = 180,
) -> dict[str, Any]:
    command = [
        sys.executable,
        str(Path(__file__).resolve().parent / "run_sock_shop_two_arm.py"),
        str(candidate["path"]),
        "--report",
        str(report_path),
        "--arm",
        str(candidate.get("method") or "unknown"),
        "--seed",
        str(seed),
        "--hypothesis-id",
        str(candidate.get("hypothesis_id") or candidate.get("name")),
        "--replicate",
        str(replicate),
        "--recovery-timeout",
        str(recovery_timeout),
    ]
    result: dict[str, Any] = {
        "command": command,
        "report_path": str(report_path),
        "execute_requested": execute,
        "executed": False,
    }
    if execute:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        completed = subprocess.run(command, cwd=Path(__file__).resolve().parents[1], check=False)
        result.update({"executed": True, "return_code": completed.returncode})
    return result


def _completed_report(path: Path) -> bool:
    if not path.is_file():
        return False
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    return value.get("status") == "completed"


def _find_prior_completed_report(
    prior_runtime_roots: list[Path],
    method: str,
    report_name: str,
) -> Path | None:
    for root in prior_runtime_roots:
        candidate = root / "methods" / method / "runtime_reports" / report_name
        if _completed_report(candidate):
            return candidate
    return None


def plan_confidence_runtime(
    discoveries: dict[str, dict[str, Any]],
    output_dir: Path,
    *,
    execute: bool = False,
    replicates: int = 2,
    prior_runtime_roots: list[Path] | None = None,
    recovery_timeout: float = 180,
    fresh_only: bool = False,
) -> dict[str, Any]:
    started = time.monotonic()
    if fresh_only and prior_runtime_roots:
        raise ValueError("fresh-only runtime planning forbids prior-runtime roots")
    if fresh_only and output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"fresh-only runtime output must be empty: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    prior_runtime_roots = prior_runtime_roots or []
    methods: dict[str, Any] = {}
    status = "completed"
    executed_units = 0
    for method, discovery in discoveries.items():
        if discovery.get("status") == "confidence_incomplete":
            raise ValueError(f"confidence-incomplete discovery cannot enter runtime: {method}")
        method_dir = output_dir / "methods" / method
        candidates = []
        hypotheses = list(discovery.get("hypotheses", []))
        planned_runtime_candidates = sum(
            1 for hypothesis in hypotheses if _is_runtime_candidate(hypothesis)
        )
        processed_runtime_candidates = 0
        processed_gate_failed = 0
        for hypothesis in hypotheses:
            hypothesis = {**hypothesis, "method": method}
            compiled = compile_hypothesis_to_mutation(hypothesis, method_dir)
            if compiled["gate"]["status"] == "passed":
                processed_runtime_candidates += 1
                compiled["runtime_invocations"] = []
                for replicate in range(1, replicates + 1):
                    report_path = method_dir / "runtime_reports" / f"{compiled['hypothesis_id']}-rep-{replicate}.json"
                    prior_report = _find_prior_completed_report(
                        prior_runtime_roots,
                        method,
                        report_path.name,
                    )
                    if prior_report is not None:
                        report_path.parent.mkdir(parents=True, exist_ok=True)
                        if not report_path.exists():
                            shutil.copy2(prior_report, report_path)
                        invocation = {
                            "command": [],
                            "report_path": str(report_path),
                            "execute_requested": execute,
                            "executed": False,
                            "skipped_completed": True,
                            "source_report": str(prior_report),
                        }
                        compiled["runtime_invocations"].append(invocation)
                        continue
                    invocation = build_runtime_invocation(
                        compiled,
                        report_path,
                        execute=execute,
                        replicate=replicate,
                        recovery_timeout=recovery_timeout,
                    )
                    compiled["runtime_invocations"].append(invocation)
                    if execute:
                        executed_units += 1
                        if invocation.get("return_code") not in (0, None):
                            status = "stopped_on_failure"
                            break
            else:
                processed_gate_failed += 1
                compiled["runtime_invocations"] = []
            candidates.append(compiled)
            if status == "stopped_on_failure":
                break
        methods[method] = {
            "generated_hypotheses": len(hypotheses),
            "runtime_candidates": planned_runtime_candidates,
            "gate_failed": len(hypotheses) - planned_runtime_candidates,
            "processed_runtime_candidates": processed_runtime_candidates,
            "processed_gate_failed": processed_gate_failed,
            "unprocessed_hypotheses": len(hypotheses) - len(candidates),
            "candidates": candidates,
        }
        if status == "stopped_on_failure":
            break

    plan = {
        "experiment": "sock_shop_yaml_confidence",
        "status": status,
        "executed_units": executed_units,
        "methods": methods,
        "timing_fields": TIMING_FIELDS,
        "recovery_timeout_seconds": recovery_timeout,
        "timing": {
            "compile_seconds": round(time.monotonic() - started, 3),
            "gate_seconds": 0.0,
            "runtime_seconds": None if not execute else 0.0,
            "washout_seconds": None if not execute else 0.0,
            "total_wall_clock_seconds": round(time.monotonic() - started, 3),
        },
        "human_review": "pending",
        "knowledge_base_updated": False,
    }
    (output_dir / "runtime_plan.json").write_text(
        json.dumps(plan, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return plan


def _load_discoveries(paths: list[Path]) -> dict[str, dict[str, Any]]:
    discoveries = {}
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        discoveries[payload["method"]] = payload
    return discoveries


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--discovery", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--prior-runtime-root", type=Path, action="append")
    parser.add_argument("--recovery-timeout", type=float, default=180)
    parser.add_argument("--fresh-only", action="store_true")
    args = parser.parse_args()
    plan = plan_confidence_runtime(
        _load_discoveries(args.discovery),
        args.output,
        execute=args.execute,
        prior_runtime_roots=args.prior_runtime_root,
        recovery_timeout=args.recovery_timeout,
        fresh_only=args.fresh_only,
    )
    print(json.dumps({"methods": list(plan["methods"]), "output": str(args.output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
