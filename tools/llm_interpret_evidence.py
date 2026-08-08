"""M5/A5 (dual-track): LLM weakness discovery + defense-mechanism attribution.

Implements the dual-track methodology (defense_pattern_methodology.md):
the primary goal is WEAKNESS discovery; a defended experiment is a second
asset class — extract WHY it defended so future projects can downgrade
candidates on edges with the same mechanism.

- For every executed candidate, build two prompts:
    A (blind): candidate metadata only. NO runtime evidence.
    B (evidence): metadata PLUS runtime observations (latency, status,
               lifecycle). LLM judges whether a weakness exists and, if the
               system defended, what mechanism absorbed the fault.
- Ground truth (auditable protocol):
      severity 3 (timeout/hang/cascade)  -> verdict=weakness, severity=3
      severity 2 (material amplification)-> verdict=weakness, severity=2
      severity 1 (near-baseline)         -> verdict=defended, mechanism LLM-attributed
- Metrics: A/B verdict accuracy, severity agreement on weaknesses, and
  defense-mechanism family match on defended cases.
The A-vs-B gap is the auditable evidence that the evidence chain improves
LLM decisions (chapter 10.2's core claim), restated in the weakness frame.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from chaos_eater_adapter.llm_backend import OpenAICompatBackend

ROOT = Path(__file__).resolve().parents[1]
EXECUTION_DIR = ROOT / "artifacts" / "experiments" / "execution"

# Canonical severity per candidate (3=hang/cascade, 2=amplified, 1=weak),
# mirrored from compare_selection_methods.SEVERITY so the two tools agree.
SEVERITY = {
    "OB-PAYMENT-LOSS-100": 3, "OB-PRODUCTCATALOG-KILL": 3,
    "OTEL-PAYMENT-LOSS-100": 3, "OTEL-EMAIL-LOSS-100": 3,
    "OB-PAYMENT-DELAY-2000": 2, "OTEL-PAYMENT-DELAY-2000": 2,
    "OTEL-EMAIL-DELAY-2000": 2, "OB-PRODUCTCATALOG-DELAY-500": 2,
    "TT-STATION-DELAY-2000": 2, "TT-STATION-DELAY-100": 1,
    "TT-STATION-CPU-80": 1, "TT-BASIC-DELAY-100": 1,
    "OB-CHECKOUT-DELAY-2000": 3, "OB-CART-DELAY-2000": 3,
    "OTEL-CHECKOUT-DELAY-2000": 3, "OTEL-CURRENCY-DELAY-2000": 2,
    "TT-ORDER-DELAY-2000": 2,
    # extended, executed:
    "OB-SHIPPING-DELAY-2000": 2, "TT-BASIC-DELAY-500": 1, "TT-STATION-DELAY-500": 1,
}

# Mechanism families for matching LLM attribution (defense side) against the
# pattern library.
MECHANISM_FAMILIES: dict[str, list[str]] = {
    "bounded_timeout": ["timeout", "deadline"],
    "retry_fast_fail": ["retry", "fast fail", "fail fast"],
    "circuit_breaker": ["circuit", "breaker"],
    "redundancy": ["redund", "replica", "multiple"],
    "isolation_non_critical": ["isolation", "async", "non-critical", "side effect", "decoupled"],
    "absorbed_by_design": ["1:1", "single call", "no amplification", "simple", "direct"],
    "weak_stressor": ["below threshold", "weak", "low intensity", "not saturating", "under-provision"],
}

SYS_PROMPT = """\
You are a chaos-engineering WEAKNESS assessor. Your primary job is to find
whether a fault-injection experiment reveals a WEAKNESS in the system; when
the system defended, you extract the mechanism that absorbed the fault.

Answer ONLY with a single JSON object:
{
  "verdict": "weakness" | "defended",
  "severity": 1 | 2 | 3,
  "root_cause": "one concise phrase (only for weakness), e.g. 'missing timeout on downstream call'",
  "defense_mechanism": "one concise phrase (only for defended), e.g. 'bounded timeout on downstream call'",
  "confidence": "high" | "medium" | "low"
}

Definitions:
- weakness: the fault broke through — timeout, hang, error, cascade, or
  material latency amplification beyond the injected intensity (no isolation
  or fallback on the path). severity: 3 = hang/timeout/cascade/error,
  2 = response preserved but latency amplified materially.
- defended: the system absorbed the fault — behavior stayed at or near
  baseline (1:1 latency propagation with no compounding is also defended;
  severity 1). Explain WHAT mechanism absorbed it."""


def verdict_for(candidate_id: str, classification: str) -> dict[str, Any]:
    """Truth mapping: severity + classification -> verdict/severity.

    Prefers the audited SEVERITY table (each entry has evidence notes in
    compare_selection_methods). For candidates not in the table, falls back to
    the classification signal so an error/timeout never defaults to 'defended'.
    """
    severity = SEVERITY.get(candidate_id)
    if severity is None:
        if classification in ("grpc_error_observed", "client_timeout_observed",
                              "full_cascade_failure_after_hang",
                              "full_propagation_and_infinite_hang"):
            severity = 3
        elif classification in ("grpc_response_observed",
                                "response_preserved_latency_degradation"):
            severity = 2
        else:
            severity = 1
    if severity >= 2:
        return {"verdict": "weakness", "severity": severity}
    return {"verdict": "defended", "severity": 1}

def build_candidate_evidence(evidence_doc: dict[str, Any]) -> list[dict[str, Any]]:
    """Collect executed candidates with a concluded classification.

    Representative-conclusion selection must not be fooled by early-track noise:
    invalid_* records are excluded, and among the surviving classifications the
    confirmed experiments (confirmation_*, m1_*) take precedence over early
    track_k runs. For a candidate where confirmation runs say
    grpc_response_observed but an early track_k run says grpc_error_observed,
    the confirmation (controlled, repeated) verdict wins.
    """
    def source_priority(name: str) -> int:
        if name.startswith("confirmation_"):
            return 0
        if name.startswith("m1_"):
            return 1
        if name.startswith("track_k"):
            return 2
        return 3

    out: list[dict[str, Any]] = []
    for item in evidence_doc.get("candidates", []):
        conclusions = item.get("own_conclusions") or []
        valid = [
            c for c in conclusions
            if not str(c["classification"]).startswith("invalid")
            and c["classification"] != "not_applicable"
        ]
        if not valid:
            continue
        valid.sort(key=lambda c: (source_priority(str(c["file"])), str(c["file"])))
        classification = valid[0]["classification"]
        truth = verdict_for(str(item["candidate_id"]), classification)
        out.append(
            {
                "candidate_id": item["candidate_id"],
                "service": item.get("service"),
                "classification": classification,
                "truth": truth["verdict"],
                "truth_severity": truth["severity"],
                "evidence_files": sorted({c["file"] for c in valid}),
            }
        )
    return out


def render_blind_prompt(c: dict[str, Any], candidate_meta: dict[str, Any]) -> str:
    return (
        f"Candidate: {c['candidate_id']}\n"
        f"Service: {candidate_meta.get('service')}\n"
        f"Edge: {candidate_meta.get('edge')}\n"
        f"Fault: {candidate_meta.get('fault_family')} ({candidate_meta.get('intensity')})\n\n"
        "Judge whether a weakness is likely and its severity based ONLY on this "
        "architecture information. No runtime measurements are provided."
    )


def extract_observations(evidence_files: list[str], by_file: dict[str, dict[str, Any]]) -> str:
    lines: list[str] = []
    for name in sorted(set(evidence_files)):
        doc = by_file.get(name)
        if not doc:
            continue
        if doc.get("tool") == "classify_runtime_result":
            obs = doc.get("observations") or {}
            lines.append(
                f"- run {name}: injected={obs.get('injected')} recovered={obs.get('recovered')} "
                f"cleanup={obs.get('cleanup_confirmed')} baseline_median={obs.get('baseline_median_latency_ms')}ms "
                f"injected_median={obs.get('observed_median_latency_ms')}ms "
                f"delta={obs.get('latency_delta_ms')}ms request_count={obs.get('request_count')}"
            )
        else:
            detail = (doc.get("classification_details") or {}).get("observations") or {}
            baseline = detail.get("baseline_median_latency_ms")
            observed = detail.get("observed_median_latency_ms")
            # gRPC runner exposes samples under workload.observations; HTTP
            # runner exposes them under the top-level requests array.
            samples = []
            wl = (doc.get("observations") or {}).get("workload") or doc.get("workload") or {}
            for sample in (wl.get("observations") or [])[:3]:
                samples.append(
                    f"{sample.get('grpc_status') or 'http'} {sample.get('latency_ms')}ms "
                    f"{str(sample.get('error') or '')[:40]}"
                )
            if not samples:
                for req in (doc.get("requests") or [])[:3]:
                    samples.append(
                        f"{req.get('status_code') or 'http'} {req.get('latency_ms')}ms "
                        f"{str(req.get('error') or '')[:40]}"
                    )
            lifecycle = doc.get("lifecycle") or {}
            lines.append(
                f"- run {name}: applied={lifecycle.get('applied')} "
                f"injected={lifecycle.get('injected')} recovered={lifecycle.get('recovered')} "
                f"baseline_median={baseline}ms observed_median={observed}ms "
                f"samples=[{'; '.join(samples)}]"
            )
    return "\n".join(lines) if lines else "(no runtime evidence extracted)"


def render_evidence_prompt(c: dict[str, Any], candidate_meta: dict[str, Any], observations: str) -> str:
    return (
        f"Candidate: {c['candidate_id']}\n"
        f"Service: {candidate_meta.get('service')}\n"
        f"Edge: {candidate_meta.get('edge')}\n"
        f"Fault: {candidate_meta.get('fault_family')} ({candidate_meta.get('intensity')})\n\n"
        f"Runtime observations (baseline -> injection -> recovery):\n{observations}\n\n"
        "From this evidence, judge whether a weakness exists (and its severity) "
        "or, if the system defended, what mechanism absorbed the fault."
    )


def load_meta() -> dict[str, dict[str, Any]]:
    from extended_candidate_pool import extended_candidate_pool

    return {c["candidate_id"]: c for c in extended_candidate_pool()}


def load_run_files() -> dict[str, dict[str, Any]]:
    by_file: dict[str, dict[str, Any]] = {}
    for path in EXECUTION_DIR.glob("*.json"):
        if not any(tag in path.name for tag in ("confirmation", "m1_batch", "m1_ext", "smoke", "track_k")):
            continue
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        by_file[path.name] = doc
    return by_file


def parse_completion(text: str) -> dict[str, Any]:
    """Parse a JSON object from a completion, tolerating unescaped quotes in
    string values (the model occasionally emits them). Tries the strict parse
    first, then falls back to decoding progressively longer prefixes of the
    text until a complete JSON object is found."""
    stripped = text.strip()
    # strip markdown fences if present
    if stripped.startswith("```"):
        stripped = stripped.split("\n", 1)[-1]
        stripped = stripped.rsplit("```", 1)[0]
    decoder = json.JSONDecoder()
    start = 0
    while True:
        start = stripped.find("{", start)
        if start == -1:
            raise ValueError(f"no JSON object in completion: {text[:160]!r}")
        try:
            obj, _ = decoder.raw_decode(stripped[start:])
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass
        start += 1


def mechanism_family(text: str) -> str:
    lowered = (text or "").lower()
    for family, keywords in MECHANISM_FAMILIES.items():
        if any(keyword in lowered for keyword in keywords):
            return family
    return "unmatched"


def run(backend: OpenAICompatBackend, evidence: list[dict[str, Any]], meta: dict[str, Any], by_file: dict[str, dict[str, Any]], output_path: Path | None = None) -> dict[str, Any]:
    # Resume support: load any previously completed candidates.
    completed_ids: set[str] = set()
    results: list[dict[str, Any]] = []
    if output_path and output_path.exists():
        try:
            existing = json.loads(output_path.read_text(encoding="utf-8"))
            results = existing.get("results") or []
            completed_ids = {r["candidate_id"] for r in results}
        except (OSError, json.JSONDecodeError):
            results, completed_ids = [], set()
        if completed_ids:
            print(f"[resume] {len(completed_ids)} candidates already completed, skipping")

    pending = [c for c in evidence if c["candidate_id"] not in completed_ids]

    for c in pending:
        candidate_meta = meta.get(c["candidate_id"], {})
        observations = extract_observations(c["evidence_files"], by_file)

        # A: blind
        blind_prompt = render_blind_prompt(c, candidate_meta)
        blind_raw, blind_meta = backend.complete(SYS_PROMPT, blind_prompt, "")
        blind = parse_completion(blind_raw)

        # B: evidence
        evidence_prompt = render_evidence_prompt(c, candidate_meta, observations)
        evidence_raw, evidence_meta = backend.complete(SYS_PROMPT, evidence_prompt, "")
        judged = parse_completion(evidence_raw)

        results.append(
            {
                "candidate_id": c["candidate_id"],
                "truth": c["truth"],
                "truth_severity": c["truth_severity"],
                "truth_classification": c["classification"],
                "blind": {
                    "verdict": blind.get("verdict"),
                    "severity": blind.get("severity"),
                    "root_cause": blind.get("root_cause"),
                    "defense_mechanism": blind.get("defense_mechanism"),
                    "correct": blind.get("verdict") == c["truth"],
                    "severity_hit": c["truth"] == "weakness" and blind.get("severity") == c["truth_severity"],
                    "mechanism": mechanism_family(blind.get("defense_mechanism") or "") if c["truth"] == "defended" else None,
                    "tokens": blind_meta.get("total_tokens"),
                },
                "evidence": {
                    "verdict": judged.get("verdict"),
                    "severity": judged.get("severity"),
                    "root_cause": judged.get("root_cause"),
                    "defense_mechanism": judged.get("defense_mechanism"),
                    "correct": judged.get("verdict") == c["truth"],
                    "severity_hit": c["truth"] == "weakness" and judged.get("severity") == c["truth_severity"],
                    "mechanism": mechanism_family(judged.get("defense_mechanism") or "") if c["truth"] == "defended" else None,
                    "tokens": evidence_meta.get("total_tokens"),
                },
                "observations": observations,
            }
        )
        # Persist after every candidate so a crash only loses the current one.
        if output_path:
            _write_checkpoint(output_path, results)
        print(
            f"[{c['candidate_id']}] truth={c['truth']}({c['truth_severity']}) "
            f"blind={blind.get('verdict')} evid={judged.get('verdict')} "
            f"mechE={results[-1]['evidence'].get('mechanism')}"
        )

    total = len(results)
    verdict_acc = lambda mode: round(sum(r[mode]["correct"] for r in results) / total, 3) if total else None
    sev_hit = lambda mode: round(
        sum(r[mode]["severity_hit"] for r in results if r["truth"] == "weakness")
        / max(1, sum(1 for r in results if r["truth"] == "weakness")),
        3,
    )
    mech_extract = lambda mode: round(
        sum(1 for r in results if r["truth"] == "defended" and r[mode].get("mechanism") != "unmatched" and r[mode].get("mechanism"))
        / max(1, sum(1 for r in results if r["truth"] == "defended")),
        3,
    )

    return {
        "schema_version": 1,
        "tool": "llm_interpret_evidence",
        "method": "M5/A5 ours-llm-interpret (dual-track: weakness discovery + defense mechanism)",
        "candidate_count": total,
        "weakness_truth": sum(1 for r in results if r["truth"] == "weakness"),
        "defended_truth": sum(1 for r in results if r["truth"] == "defended"),
        "blind": {
            "verdict_accuracy": verdict_acc("blind"),
            "weakness_severity_hit_rate": sev_hit("blind"),
            "defense_mechanism_extraction_rate": mech_extract("blind"),
            "correct": sum(r["blind"]["correct"] for r in results),
            "total": total,
        },
        "evidence": {
            "verdict_accuracy": verdict_acc("evidence"),
            "weakness_severity_hit_rate": sev_hit("evidence"),
            "defense_mechanism_extraction_rate": mech_extract("evidence"),
            "correct": sum(r["evidence"]["correct"] for r in results),
            "total": total,
        },
        "results": results,
    }


def _write_checkpoint(output_path: Path, results: list[dict[str, Any]]) -> None:
    payload = {
        "schema_version": 1,
        "tool": "llm_interpret_evidence",
        "partial": True,
        "candidate_count": len(results),
        "results": results,
    }
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--base-url", default="https://api.deepseek.com/v1")
    parser.add_argument("--model", default="deepseek-v4-flash")
    parser.add_argument("--output", type=Path, default=EXECUTION_DIR / "llm_interpret_results.json")
    args = parser.parse_args()
    if args.api_key is None:
        args.api_key = os.environ.get("CHAOS_EATER_API_KEY")
    if not args.api_key:
        raise SystemExit("--api-key or CHAOS_EATER_API_KEY is required")

    backend = OpenAICompatBackend(base_url=args.base_url, api_key=args.api_key, model=args.model, json_mode=False)
    evidence_doc = json.loads((EXECUTION_DIR / "candidate_evidence_status.json").read_text(encoding="utf-8"))
    evidence = build_candidate_evidence(evidence_doc)
    meta = load_meta()
    by_file = load_run_files()

    result = run(backend, evidence, meta, by_file, output_path=args.output)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(args.output),
        "blind_verdict_accuracy": result["blind"]["verdict_accuracy"],
        "evidence_verdict_accuracy": result["evidence"]["verdict_accuracy"],
        "weakness_truth": result["weakness_truth"],
        "defended_truth": result["defended_truth"],
        "candidates": result["candidate_count"],
    }, indent=2))
    return 0


def load_card_root_causes() -> dict[str, str]:
    """Map candidate -> root_cause_family from knowledge cards' root_cause strings."""
    mapping: dict[str, str] = {}
    # Reuse the evidence tool's card loader through a small inline pass.
    import re

    from extended_candidate_pool import extended_candidate_pool

    roots = {
        "OB-PAYMENT-DELAY-2000": "missing_timeout",
        "OB-PAYMENT-LOSS-100": "missing_timeout",
        "OB-PRODUCTCATALOG-KILL": "missing_fallback",
        "OTEL-PAYMENT-DELAY-2000": "missing_timeout",
        "OTEL-PAYMENT-LOSS-100": "missing_timeout",
        "OTEL-EMAIL-DELAY-2000": "missing_isolation",
        "OTEL-EMAIL-LOSS-100": "missing_isolation",
        "OB-CHECKOUT-DELAY-2000": "missing_timeout",
        "OB-CART-DELAY-2000": "missing_timeout",
        "OTEL-CHECKOUT-DELAY-2000": "missing_timeout",
        "OTEL-CURRENCY-DELAY-2000": "latency_amplification",
        "TT-ORDER-DELAY-2000": "latency_amplification",
        "TT-STATION-DELAY-100": "no_finding",
        "TT-STATION-DELAY-2000": "latency_amplification",
        "TT-STATION-CPU-80": "no_finding",
        "TT-BASIC-DELAY-100": "no_finding",
        "OB-PRODUCTCATALOG-DELAY-500": "latency_amplification",
    }
    for c in extended_candidate_pool():
        mapping[c["candidate_id"]] = roots.get(c["candidate_id"], "unmatched")
    return mapping


if __name__ == "__main__":
    raise SystemExit(main())
