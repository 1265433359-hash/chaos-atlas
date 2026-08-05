"""Classify runtime chaos evidence without making an automatic defense claim."""

from __future__ import annotations

import argparse
import json
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"JSON root is not an object: {path}")
    return value


def canonical_body(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return value.strip()
        return json.dumps(parsed, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def samples_from(value: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("requests", "request_samples_during_window", "samples"):
        candidate = value.get(key)
        if isinstance(candidate, list):
            samples: list[dict[str, Any]] = []
            for item in candidate:
                if not isinstance(item, dict):
                    continue
                status = item.get("status_code", item.get("status"))
                latency = item.get("latency_ms")
                samples.append(
                    {
                        "status_code": int(status) if isinstance(status, (int, float)) else None,
                        "latency_ms": float(latency) if isinstance(latency, (int, float)) else None,
                        "body": item.get("body"),
                        "error": item.get("error"),
                    }
                )
            if samples:
                return samples
    request_observation = value.get("request_observation")
    if isinstance(request_observation, dict):
        latency_value = request_observation.get("client_latency_ms", request_observation.get("latency_ms"))
        if isinstance(latency_value, dict):
            latency_value = latency_value.get("p50", latency_value.get("average"))
        status_value = request_observation.get("client_status_code")
        if status_value is None and request_observation.get("all_status_200") is True:
            status_value = 200
        return [
            {
                "status_code": status_value,
                "latency_ms": latency_value,
                "body": request_observation.get("body", request_observation.get("body_contract")),
                "error": request_observation.get("client_error"),
            }
        ]
    baseline_observation = value.get("baseline_observation")
    if isinstance(baseline_observation, dict):
        latencies = baseline_observation.get("latency_ms")
        statuses = baseline_observation.get("status_codes")
        if isinstance(latencies, list):
            return [
                {
                    "status_code": statuses[index] if isinstance(statuses, list) and index < len(statuses) else None,
                    "latency_ms": latency,
                    "body": baseline_observation.get("body_contract"),
                    "error": None,
                }
                for index, latency in enumerate(latencies)
            ]
    return []


def lifecycle_from(value: dict[str, Any]) -> dict[str, Any]:
    lifecycle = value.get("lifecycle")
    if isinstance(lifecycle, dict):
        return lifecycle
    chaos_status = value.get("chaos_status")
    if isinstance(chaos_status, dict):
        injected_count = int(chaos_status.get("injected_count", 0) or 0)
        recovered_count = int(chaos_status.get("recovered_count", 0) or 0)
        return {
            "injected": injected_count >= 1,
            "recovered": bool(chaos_status.get("all_recovered")) or recovered_count >= injected_count > 0,
            "injected_status": {"injected_count": injected_count},
            "recovered_status": {"recovered_count": recovered_count},
            "cleanup": value.get("cleanup") if isinstance(value.get("cleanup"), dict) else {},
        }
    return {}


def median_latency(samples: list[dict[str, Any]]) -> float | None:
    values = [sample["latency_ms"] for sample in samples if sample.get("latency_ms") is not None]
    return round(statistics.median(values), 3) if values else None


def cleanup_confirmed(cleanup: dict[str, Any]) -> bool | None:
    if not cleanup:
        return None
    if "resource_absent_after_delete" in cleanup:
        return bool(cleanup["resource_absent_after_delete"])
    if "active_networkchaos_remaining" in cleanup:
        return not bool(cleanup["active_networkchaos_remaining"])
    deleted_flags = [
        value
        for key, value in cleanup.items()
        if key.endswith("_resource_deleted") and isinstance(value, bool)
    ]
    if deleted_flags:
        return all(deleted_flags)
    return None


def baseline_contract(baseline: dict[str, Any] | None) -> tuple[float | None, set[int], set[str]]:
    if not baseline:
        return None, set(), set()
    samples = samples_from(baseline)
    statuses = {sample["status_code"] for sample in samples if sample.get("status_code") is not None}
    bodies = {
        body
        for body in (canonical_body(sample.get("body")) for sample in samples)
        if body is not None
    }
    return median_latency(samples), statuses, bodies


def classify(run: dict[str, Any], baseline: dict[str, Any] | None) -> dict[str, Any]:
    preflight = run.get("preflight") or {}
    lifecycle = lifecycle_from(run)
    requests = samples_from(run)
    baseline_median, baseline_statuses, baseline_bodies = baseline_contract(baseline)
    observed_median = median_latency(requests)
    labels: list[str] = []
    evidence_state = "unknown"
    classification = "unknown"

    if preflight.get("decision") == "blocked":
        blocker = ((preflight.get("checks") or {}).get("injector_prerequisite") or {}).get("blocker")
        labels.append(blocker or "preflight_blocked")
        classification = "platform_or_preflight_blocked"
        evidence_state = "no_defense_conclusion"
    elif preflight.get("decision") == "not_applicable":
        labels.append("not_applicable_target_or_schema")
        classification = "not_applicable"
        evidence_state = "no_defense_conclusion"
    elif not lifecycle.get("injected") or lifecycle.get("injected_status", {}).get("injected_count", 0) < 1:
        labels.append("injection_not_confirmed")
        classification = "invalid_not_injected"
        evidence_state = "no_effect_evidence"
    else:
        timeout_seen = any(
            sample.get("status_code") is None
            and "timed out" in str(sample.get("error") or "").lower()
            for sample in requests
        )
        server_error_seen = any(
            sample.get("status_code") is not None and sample["status_code"] >= 500 for sample in requests
        )
        if timeout_seen:
            labels.append("client_timeout_budget_exceeded")
            classification = "client_timeout_observed"
        elif server_error_seen:
            labels.append("server_error_propagated")
            classification = "server_error_observed"
        elif requests and all(
            sample.get("status_code") is not None and 200 <= sample["status_code"] < 300
            for sample in requests
        ):
            body_values = {
                body
                for body in (canonical_body(sample.get("body")) for sample in requests)
                if body is not None
            }
            status_preserved = not baseline_statuses or all(
                sample["status_code"] in baseline_statuses for sample in requests
            )
            body_preserved = not baseline_bodies or not body_values or body_values <= baseline_bodies
            if not status_preserved or not body_preserved:
                labels.append("response_contract_changed")
                classification = "response_contract_changed"
            else:
                classification = "response_observed"
                if baseline_median is not None and observed_median is not None:
                    delta = round(observed_median - baseline_median, 3)
                    ratio = round(observed_median / baseline_median, 3) if baseline_median else None
                    if delta >= 50 or (ratio is not None and ratio >= 1.5):
                        labels.append("latency_degradation")
                        classification = "response_preserved_latency_degradation"
        else:
            classification = "transport_or_observation_error"
            labels.append("request_observation_incomplete")
        evidence_state = "runtime_effect_observed"

    recovered = bool(lifecycle.get("recovered"))
    cleanup = lifecycle.get("cleanup") or {}
    if lifecycle.get("injected") and not recovered:
        labels.append("recovery_unconfirmed")
        evidence_state = "runtime_effect_without_recovery_confirmation"
    cleanup_state = cleanup_confirmed(cleanup)
    if lifecycle.get("injected") and cleanup_state is False:
        labels.append("cleanup_unconfirmed")

    confidence = "A" if lifecycle.get("injected") and recovered and requests and baseline else "B"
    interpretation = {
        "defense_claim": "not_derived",
        "reason": "The classifier records evidence state; defense requires the test-node graph, baseline, path evidence and outcome-specific reasoning.",
    }
    if classification == "response_preserved_latency_degradation":
        interpretation["result"] = "Functional response was preserved, but latency degraded relative to baseline. This is not proof of timeout or fallback defense."
    elif classification == "client_timeout_observed":
        interpretation["result"] = "The client timeout boundary was crossed after confirmed injection. Verify server-side completion, retry, fallback and cleanup separately."
    elif classification == "invalid_not_injected":
        interpretation["result"] = "The experiment cannot support a defense conclusion because the injector did not confirm an effect."
    elif classification == "platform_or_preflight_blocked":
        interpretation["result"] = "The platform or preflight gate blocked execution; this is not an application defense result."

    return {
        "schema_version": 1,
        "tool": "classify_runtime_result",
        "classified_at": datetime.now(timezone.utc).isoformat(),
        "run_report": run.get("mutation"),
        "baseline_report": None,
        "classification": classification,
        "evidence_state": evidence_state,
        "confidence": confidence,
        "root_cause_labels": sorted(set(labels)),
        "observations": {
            "request_count": len(requests),
            "observed_median_latency_ms": observed_median,
            "baseline_median_latency_ms": baseline_median,
            "latency_delta_ms": round(observed_median - baseline_median, 3)
            if observed_median is not None and baseline_median is not None
            else None,
            "injected": bool(lifecycle.get("injected")),
            "recovered": recovered,
            "cleanup_confirmed": cleanup_state,
        },
        "interpretation": interpretation,
        "evidence_refs": [
            value
            for value in [run.get("mutation"), run.get("apply"), run.get("lifecycle", {}).get("cleanup")]
            if value
        ],
    }


NON_EXECUTION_CLASSIFICATIONS = {
    "platform_or_preflight_blocked",
    "not_applicable",
    "invalid_not_injected",
    "apply_failed",
    "runner_error",
}


def exit_code_for_classification(classification: str) -> int:
    """Return one canonical process status for runner and offline CLI."""
    return 2 if classification in NON_EXECUTION_CLASSIFICATIONS else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True, help="runner or manually normalized runtime JSON")
    parser.add_argument("--baseline", type=Path, help="baseline JSON with samples/status/latency/body")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    run = load_json(args.run)
    baseline = load_json(args.baseline) if args.baseline else None
    result = classify(run, baseline)
    result["run_report"] = str(args.run).replace("\\", "/")
    result["baseline_report"] = str(args.baseline).replace("\\", "/") if args.baseline else None
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=True))
    return exit_code_for_classification(result["classification"])


if __name__ == "__main__":
    raise SystemExit(main())
