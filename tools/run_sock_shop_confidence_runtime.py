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


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9-]+", "-", value.lower()).strip("-")
    return slug[:48] or "hypothesis"


def _mutation_name(hypothesis: dict[str, Any]) -> str:
    raw = str(hypothesis.get("id") or hypothesis.get("hypothesis_id") or hypothesis.get("target_service") or "h")
    digest = hashlib.sha256(json.dumps(hypothesis, sort_keys=True).encode("utf-8")).hexdigest()[:8]
    return f"yc-{_slug(raw)}-{digest}"[:63]


def _kind_and_spec(hypothesis: dict[str, Any]) -> tuple[str | None, dict[str, Any], str | None]:
    category = hypothesis.get("category")
    action = str(hypothesis.get("action_or_target") or "").lower()
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
    document = {
        "apiVersion": "chaos-mesh.org/v1alpha1",
        "kind": kind,
        "metadata": {"name": name, "namespace": NAMESPACE},
        "spec": {
            "mode": "one",
            "selector": {"namespaces": [NAMESPACE], "labelSelectors": {"name": target}},
            **extra_spec,
        },
    }
    path = output_dir / "mutations" / f"{name}.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    content = yaml.safe_dump(document, sort_keys=False)
    if path.exists() and path.read_text(encoding="utf-8") != content:
        raise FileExistsError(f"refusing to overwrite existing mutation with different content: {path}")
    path.write_text(content, encoding="utf-8")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return {
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
) -> dict[str, Any]:
    started = time.monotonic()
    output_dir.mkdir(parents=True, exist_ok=True)
    prior_runtime_roots = prior_runtime_roots or []
    methods: dict[str, Any] = {}
    status = "completed"
    executed_units = 0
    for method, discovery in discoveries.items():
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
    args = parser.parse_args()
    plan = plan_confidence_runtime(
        _load_discoveries(args.discovery),
        args.output,
        execute=args.execute,
        prior_runtime_roots=args.prior_runtime_root,
        recovery_timeout=args.recovery_timeout,
    )
    print(json.dumps({"methods": list(plan["methods"]), "output": str(args.output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
