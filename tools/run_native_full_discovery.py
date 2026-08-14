"""Run native-project-knowledge discovery and compile namespace-local mutations."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
METHOD_ID = "ChaosAtlas-native-full"
MODEL = "deepseek-v4-flash"
BASE_URL = "https://api.deepseek.com/v1"
DEFAULT_SEEDS = (1001, 1002, 1003)
FORBIDDEN_KEYS = {
    "candidate_id",
    "candidate_pool",
    "oracle_label",
    "prior_selection",
    "runtime_observation",
    "post_run_rca",
    "mutation_path",
    "shell_command",
    "kubectl_command",
}


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    ).hexdigest()


def _display_path(path: Path) -> str:
    resolved = Path(path).resolve()
    try:
        return str(resolved.relative_to(ROOT.resolve())).replace("\\", "/")
    except ValueError:
        return str(resolved).replace("\\", "/")


def build_messages(bundle: dict[str, Any]) -> tuple[str, str]:
    system = (
        "You are the ChaosAtlas native project discovery analyst. Use only the "
        "frozen project evidence and native project knowledge supplied below. "
        "Return JSON only with at most eight bounded hypotheses. Do not invent "
        "runtime observations, commands, mutation paths, candidate pools, or "
        "knowledge outside the supplied native project knowledge. Use exact "
        "topology node IDs and namespace-local fault parameters. Select hypotheses "
        "that can be compiled into PodChaos, NetworkChaos, or StressChaos. The "
        "canonical parameter keys are strict: network_delay uses integer latency_ms "
        "and duration_s; network_loss uses integer loss_percent and duration_s; "
        "container_cpu_stress uses integer workers, load_percent, and duration_s; "
        "pod_kill uses exactly {mode: one}. Do not copy legacy parameter names or "
        "string values from knowledge cards. If a knowledge card mentions a delay "
        "above 500ms, select a bounded canonical delay at most 500ms instead."
    )
    user = json.dumps(
        {
            "method_id": bundle.get("method_id"),
            "seed": bundle.get("seed"),
            "common_input": bundle.get("common_input"),
            "knowledge_view": bundle.get("knowledge_view"),
            "parameter_contract": {
                "pod_kill": {"mode": "one"},
                "network_delay": {
                    "latency_ms": "integer 1..500",
                    "duration_s": "integer 1..60",
                },
                "network_loss": {
                    "loss_percent": "integer 1..100",
                    "duration_s": "integer 1..60",
                },
                "container_cpu_stress": {
                    "workers": "integer 1..2",
                    "load_percent": "integer 1..80",
                    "duration_s": "integer 1..60",
                },
            },
            "output_schema": {
                "project_id": "exact project id",
                "project_commit": "exact 40 hex commit",
                "hypotheses": [
                    {
                        "hypothesis_id": "local-id",
                        "target": "exact topology node or source->target edge",
                        "target_kind": "service|dependency_edge",
                        "fault_family": "pod_kill|network_delay|network_loss|container_cpu_stress",
                        "parameters": {},
                        "hypothesis": "bounded claim",
                        "weakness_surface": "mechanism at risk",
                        "call_chain": [{"source": "node", "target": "node", "relation": "edge", "evidence_ref": "topology"}],
                        "expected_invariant": "business invariant",
                        "validation_plan": "baseline, inject, observe, recover, cleanup, washout",
                        "recovery_expectation": "expected recovery",
                    }
                ],
                "no_safe_hypothesis_reason": "required only when empty",
            },
        },
        indent=2,
        ensure_ascii=True,
    )
    return system, user


def _forbidden_paths(value: Any, path: str = "$") -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key in FORBIDDEN_KEYS:
                found.append(f"{path}.{key}")
            found.extend(_forbidden_paths(child, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(_forbidden_paths(child, f"{path}[{index}]"))
    return found


def parse_model_output(raw: str) -> dict[str, Any]:
    text = raw.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if fenced:
        text = fenced.group(1).strip()
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError("model output must be an object")
    forbidden = _forbidden_paths(value)
    if forbidden:
        raise ValueError(f"forbidden output fields: {forbidden}")
    hypotheses = value.get("hypotheses")
    if not isinstance(hypotheses, list) or len(hypotheses) > 8:
        raise ValueError("hypotheses must be a list of at most 8")
    return value


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def run_matrix(
    *,
    input_root: Path,
    profile_path: Path,
    output: Path,
    key_path: Path,
    project_id: str,
    seeds: Iterable[int] = DEFAULT_SEEDS,
    execute: bool = False,
    model: str = MODEL,
    base_url: str = BASE_URL,
) -> dict[str, Any]:
    profile = _load(profile_path)
    if profile.get("runtime_ready") is not True:
        raise ValueError("runtime profile is not ready")
    output = Path(output)
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"refusing non-empty discovery output: {output}")
    output.mkdir(parents=True, exist_ok=True)

    records: list[dict[str, Any]] = []
    for seed in tuple(seeds):
        bundle_path = Path(input_root) / "input_bundles" / project_id / f"seed-{seed}" / "chaosatlas-native-full.json"
        bundle = _load(bundle_path)
        if (bundle.get("project_id"), bundle.get("seed"), bundle.get("method_id")) != (project_id, seed, METHOD_ID):
            raise ValueError(f"native bundle identity mismatch: {bundle_path}")
        if bundle.get("projection_used") is not False or bundle.get("pollution_intentionally_not_excluded") is not True:
            raise ValueError(f"native scope flags invalid: {bundle_path}")
        system, user = build_messages(bundle)
        records.append(
            {
                "seed": seed,
                "bundle_path": _display_path(bundle_path),
                "bundle_sha256": hashlib.sha256(bundle_path.read_bytes()).hexdigest(),
                "request_sha256": hashlib.sha256((system + "\n" + user).encode()).hexdigest(),
                "bundle": bundle,
                "system": system,
                "user": user,
            }
        )
    (output / "preflight.json").write_text(
        json.dumps(
            {
                "status": "passed",
                "project_id": project_id,
                "method_id": METHOD_ID,
                "calls": len(records),
                "model": model,
                "base_url": base_url,
                "projection_used": False,
                "pollution_intentionally_not_excluded": True,
                "human_review": "pending",
                "knowledge_base_updated": False,
                "records": [
                    {key: row[key] for key in ("seed", "bundle_path", "bundle_sha256", "request_sha256")}
                    for row in records
                ],
            },
            indent=2,
            ensure_ascii=True,
        )
        + "\n",
        encoding="utf-8",
    )
    if not execute:
        return {"status": "preflight_passed", "calls": len(records)}

    key = key_path.read_text(encoding="utf-8").strip()
    if not key:
        raise ValueError("DeepSeek API key file is empty")
    sys.path.insert(0, str(ROOT / "tools"))
    from chaos_eater_adapter.llm_backend import OpenAICompatBackend
    from open_discovery_mutation_compiler import compile_payload
    from run_two_arm_real_project_discovery import build_discovery_handoff

    backend = OpenAICompatBackend(
        base_url=base_url,
        api_key=key,
        model=model,
        timeout=180,
        json_mode=True,
        temperature=0.2,
        max_output_tokens=4096,
        disable_thinking=True,
    )
    summary: list[dict[str, Any]] = []
    for record in records:
        run_dir = output / f"seed-{record['seed']}" / METHOD_ID.lower()
        run_dir.mkdir(parents=True, exist_ok=False)
        raw = ""
        try:
            raw, metadata = backend.complete(record["system"], record["user"], "")
            payload = parse_model_output(raw)
            handoff = build_discovery_handoff(record["bundle"], payload, profile)
            mutations = compile_payload(
                {"status": "valid", "accepted": handoff.get("selected_hypotheses", [])},
                record["bundle"]["common_input"]["topology"],
            )
            selected_count = len((handoff or {}).get("selected_hypotheses", []))
            generated_count = len((mutations or {}).get("generated", []))
            status = (
                "valid"
                if handoff.get("status") == "handoff_ready" and mutations.get("status") == "valid"
                and selected_count == 4 and generated_count == 4
                else "method_invalid"
            )
            error = None
        except Exception as exc:
            metadata, payload, handoff, mutations = {}, None, None, None
            status = "transport_failed" if isinstance(exc, (OSError, RuntimeError, TimeoutError)) else "method_invalid"
            error = f"{type(exc).__name__}: {exc}"
        (run_dir / "raw.redacted.txt").write_text(raw.replace(key, "[REDACTED]"), encoding="utf-8")
        for name, value in (("payload.json", payload), ("handoff.json", handoff), ("mutations.json", mutations)):
            (run_dir / name).write_text(json.dumps(value, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
        generated = (mutations or {}).get("generated", []) if mutations else []
        if generated:
            mutation_dir = run_dir / "mutations"
            mutation_dir.mkdir()
            for item in generated:
                stem = item["provenance"]["canonical_signature"][:12]
                (mutation_dir / f"{stem}.yaml").write_text(item["yaml"], encoding="utf-8")
                (mutation_dir / f"{stem}.provenance.json").write_text(
                    json.dumps(item["provenance"], indent=2, ensure_ascii=True) + "\n",
                    encoding="utf-8",
                )
        result = {
            "status": status,
            "error": error,
            "seed": record["seed"],
            "method_id": METHOD_ID,
            "model": model,
            "backend": metadata,
            "bundle_sha256": record["bundle_sha256"],
            "request_sha256": record["request_sha256"],
            "raw_sha256": hashlib.sha256(raw.encode()).hexdigest(),
            "selected_count": len((handoff or {}).get("selected_hypotheses", [])),
            "generated_mutations": len(generated),
            "projection_used": False,
            "pollution_intentionally_not_excluded": True,
            "human_review": "pending",
            "knowledge_base_updated": False,
        }
        (run_dir / "result.json").write_text(json.dumps(result, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
        summary.append(result)

    final = {
        "schema_version": "chaosatlas-native-full-discovery-v1",
        "status": "completed",
        "project_id": project_id,
        "method_id": METHOD_ID,
        "calls": len(summary),
        "valid": sum(item["status"] == "valid" for item in summary),
        "method_invalid": sum(item["status"] == "method_invalid" for item in summary),
        "transport_failed": sum(item["status"] == "transport_failed" for item in summary),
        "records": summary,
        "projection_used": False,
        "pollution_intentionally_not_excluded": True,
        "human_review": "pending",
        "knowledge_base_updated": False,
        "finished_at": datetime.now(timezone.utc).isoformat(),
    }
    (output / "summary.json").write_text(json.dumps(final, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return final


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-root", type=Path, required=True)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--api-key-file", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--seed", type=int, action="append")
    parser.add_argument("--model", default=MODEL)
    parser.add_argument("--base-url", default=BASE_URL)
    args = parser.parse_args()
    result = run_matrix(
        input_root=args.input_root,
        profile_path=args.profile,
        output=args.output,
        key_path=args.api_key_file,
        project_id=args.project_id,
        seeds=tuple(args.seed or DEFAULT_SEEDS),
        execute=args.execute,
        model=args.model,
        base_url=args.base_url,
    )
    print(json.dumps({key: result[key] for key in ("status", "calls")}, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
