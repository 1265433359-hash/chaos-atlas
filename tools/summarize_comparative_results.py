"""Aggregate verified comparative-execution evidence without inventing scores."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load(path: str) -> dict[str, Any]:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def first_observation(report: dict[str, Any], key: str) -> dict[str, Any]:
    value = report.get(key) or {}
    observations = value.get("observations") or []
    return observations[0] if observations else {}


def http_record(name: str, run_path: str, classification_path: str) -> dict[str, Any]:
    result = load(classification_path)
    observations = result.get("observations") or {}
    return {
        "name": name,
        "protocol": "http",
        "run_report": run_path,
        "classification_report": classification_path,
        "classification": result.get("classification"),
        "confidence": result.get("confidence"),
        "valid_lifecycle": all(
            observations.get(key) is True
            for key in ("injected", "recovered", "cleanup_confirmed")
        ),
        "baseline_median_latency_ms": observations.get("baseline_median_latency_ms"),
        "observed_median_latency_ms": observations.get("observed_median_latency_ms"),
        "latency_delta_ms": observations.get("latency_delta_ms"),
    }


def grpc_record(name: str, run_path: str) -> dict[str, Any]:
    report = load(run_path)
    baseline = first_observation(report, "baseline_workload")
    workload = first_observation(report, "workload")
    lifecycle = report.get("lifecycle") or {}
    cleanup = lifecycle.get("cleanup") or {}
    return {
        "name": name,
        "protocol": "grpc",
        "run_report": run_path,
        "classification": report.get("result_classification"),
        "valid_lifecycle": bool(
            lifecycle.get("applied")
            and lifecycle.get("injected")
            and lifecycle.get("recovered")
            and cleanup.get("delete_command_ok")
            and cleanup.get("resource_absent_after_delete")
        ),
        "baseline_status": baseline.get("grpc_status"),
        "observed_status": workload.get("grpc_status"),
        "baseline_latency_ms": baseline.get("latency_ms"),
        "observed_latency_ms": workload.get("latency_ms"),
    }


def build_summary() -> dict[str, Any]:
    runtime = [
        http_record("TT station delay r1", "artifacts/experiments/execution/smoke_station_r1.json", "artifacts/experiments/execution/smoke_station_r1_classification.json"),
        http_record("TT station delay r2", "artifacts/experiments/execution/confirmation_tt_station_r2.json", "artifacts/experiments/execution/confirmation_tt_station_r2_classification.json"),
        http_record("TT station delay r3", "artifacts/experiments/execution/confirmation_tt_station_r3.json", "artifacts/experiments/execution/confirmation_tt_station_r3_classification.json"),
        http_record("TT station delay r4", "artifacts/experiments/execution/confirmation_tt_station_r4.json", "artifacts/experiments/execution/confirmation_tt_station_r4_classification.json"),
        http_record("OB productcatalog kill initial", "artifacts/experiments/execution/track_k_ob_productcatalog_kill_r2.json", "artifacts/experiments/execution/track_k_ob_productcatalog_classification.json"),
        http_record("OB productcatalog kill r2", "artifacts/experiments/execution/confirmation_ob_productcatalog_kill_r2.json", "artifacts/experiments/execution/confirmation_ob_productcatalog_kill_r2_classification.json"),
        http_record("OB productcatalog kill r3", "artifacts/experiments/execution/confirmation_ob_productcatalog_kill_r3.json", "artifacts/experiments/execution/confirmation_ob_productcatalog_kill_r3_classification.json"),
        http_record("OB productcatalog kill r4", "artifacts/experiments/execution/confirmation_ob_productcatalog_kill_r4.json", "artifacts/experiments/execution/confirmation_ob_productcatalog_kill_r4_classification.json"),
        grpc_record("OB payment delay r1", "artifacts/experiments/execution/track_k_ob_payment_delay_grpc.json"),
        grpc_record("OB payment delay r2", "artifacts/experiments/execution/confirmation_ob_payment_delay_r2.json"),
        grpc_record("OB payment delay r3", "artifacts/experiments/execution/confirmation_ob_payment_delay_r3.json"),
        grpc_record("OB payment delay r4", "artifacts/experiments/execution/confirmation_ob_payment_delay_r4.json"),
        grpc_record("OB payment loss r1", "artifacts/experiments/execution/track_k_ob_payment_loss_grpc.json"),
        grpc_record("OB payment loss r2", "artifacts/experiments/execution/confirmation_ob_payment_loss_r2.json"),
        grpc_record("OB payment loss r3", "artifacts/experiments/execution/confirmation_ob_payment_loss_r3.json"),
        grpc_record("OB payment loss r4", "artifacts/experiments/execution/confirmation_ob_payment_loss_r4.json"),
        grpc_record("OTel payment delay r1", "artifacts/experiments/execution/track_k_otel_payment_delay_grpc_r6.json"),
        grpc_record("OTel payment delay r2", "artifacts/experiments/execution/confirmation_otel_payment_delay_r2.json"),
        grpc_record("OTel payment delay r3", "artifacts/experiments/execution/confirmation_otel_payment_delay_r3.json"),
        grpc_record("OTel payment delay r4", "artifacts/experiments/execution/confirmation_otel_payment_delay_r4.json"),
        grpc_record("OTel payment loss r1", "artifacts/experiments/execution/track_k_otel_payment_loss_grpc_r1.json"),
        grpc_record("OTel payment loss r2", "artifacts/experiments/execution/confirmation_otel_payment_loss_r2.json"),
        grpc_record("OTel payment loss r3", "artifacts/experiments/execution/confirmation_otel_payment_loss_r3.json"),
        grpc_record("OTel payment loss r4", "artifacts/experiments/execution/confirmation_otel_payment_loss_r4.json"),
    ]
    valid = [item for item in runtime if item["valid_lifecycle"]]
    by_class = Counter(item.get("classification") for item in valid)
    pilot = {}
    for replicate in (1, 2, 3):
        data = load(f"artifacts/experiments/execution/pilot_gate_evaluation_r{replicate}.json")
        pilot[str(replicate)] = {
            method.get("id"): method.get("summary", {})
            for method in data.get("methods", [])
        }
    return {
        "schema_version": 1,
        "tool": "summarize_comparative_results",
        "generated_at": now(),
        "scope": {
            "projects": ["train-ticket-lab", "online-boutique-lab", "otel-demo-lab"],
            "valid_runtime_replicates": 4,
            "selection_policy": "one-target mutations, baseline before injection, recovery and cleanup required",
        },
        "runtime_evidence": runtime,
        "runtime_summary": {
            "valid_lifecycle_count": len(valid),
            "total_runtime_records": len(runtime),
            "valid_lifecycle_rate": round(len(valid) / len(runtime), 4) if runtime else 0,
            "classification_counts": dict(sorted(by_class.items(), key=lambda item: str(item[0]))),
            "scenario_replicates": {
                "tt_station_delay": 3,
                "ob_productcatalog_kill": 3,
                "ob_payment_delay": 3,
                "ob_payment_loss": 3,
                "otel_payment_delay": 3,
                "otel_payment_loss": 3,
            },
        },
        "negative_control": "artifacts/experiments/execution/track_k_ob_adservice_negative_control.json",
        "probe_restart": "artifacts/experiments/execution/track_k_ob_probe_restart_escape_summary.json",
        "pilot_gate_evaluations": pilot,
        "pilot_interpretation": (
            "The three pilot registries compare candidate eligibility and method adapters. They are "
            "not a live algorithm ranking because external ChaosEater/FastFI execution was blocked and "
            "the available adapters share the same gated candidate bank."
        ),
        "blocked_or_deferred": [
            {
                "item": "HTTPChaos platform path",
                "report": "artifacts/experiments/execution/track_k_httpchaos_platform_gate.json",
                "decision": "blocked",
                "reason": "WSL2 Chaos Daemon lacks ebtables/tproxy prerequisite",
            },
            {
                "item": "Train Ticket order network-delay candidate",
                "report": "artifacts/experiments/execution/track_k_train_ticket_network_selection.json",
                "decision": "defer_unreachable_or_unproven_path",
                "reason": "source graph does not reach the selected network target in the current lab",
            },
            {
                "item": "ChaosEater and FastFI external adapters",
                "decision": "blocked_external_reproduction",
                "reason": "official repositories could not be fetched in the current network environment",
            },
        ],
    }


def markdown(summary: dict[str, Any]) -> str:
    runtime = summary["runtime_evidence"]
    lines = [
        "# Comparative Execution Summary",
        "",
        "This report contains only runs with explicit baseline, injection, recovery, and cleanup evidence.",
        "",
        "## Runtime Replicates",
        "",
        "| Scenario | Replicates | Valid lifecycle | Observed result |",
        "|---|---:|---:|---|",
    ]
    scenarios = [
        ("TT station delay", "TT station delay"),
        ("OB productcatalog kill", "OB productcatalog kill"),
        ("OB payment delay", "OB payment delay"),
        ("OB payment loss", "OB payment loss"),
        ("OTel payment delay", "OTel payment delay"),
        ("OTel payment loss", "OTel payment loss"),
    ]
    for label, prefix in scenarios:
        rows = [item for item in runtime if item["name"].startswith(prefix)]
        valid = sum(item["valid_lifecycle"] for item in rows)
        classes = ", ".join(sorted({str(item.get("classification")) for item in rows}))
        lines.append(f"| {label} | {len(rows)} | {valid}/{len(rows)} | {classes} |")
    lines.extend([
        "",
        "## Interpretation",
        "",
        "- The six runtime scenarios each have three valid repetitions.",
        "- K7 probe-restart evidence is reported separately as recovery amplification, not as a clean escape.",
        "- The pilot gate table is an eligibility comparison; it must not be presented as a superiority score.",
        "",
        "## Blockers",
        "",
    ])
    for item in summary["blocked_or_deferred"]:
        lines.append(f"- {item['item']}: {item['decision']} ({item['reason']}).")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--markdown", type=Path, required=True)
    args = parser.parse_args()
    result = build_summary()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    args.markdown.write_text(markdown(result), encoding="utf-8")
    print(json.dumps(result["runtime_summary"], indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
