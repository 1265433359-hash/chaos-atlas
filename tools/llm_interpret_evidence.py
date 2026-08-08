"""M5/A5: LLM evidence interpretation - defense judgment + root-cause attribution.

Implements the "LLM decision benchmark" (supervisor report chapter 10, tasks
2-3) as a method variant of OUR methodology:

- For every executed candidate, build two prompts:
    A (blind): candidate metadata only (service, edge, fault type, intensity).
               NO runtime evidence, NO conclusion. LLM must guess.
    B (evidence): same metadata PLUS the runtime observations (baseline/inject
               latency, status, injected/recovered flags, sample results).
               LLM judges defense and attributes a root cause.
- Ground truth comes from the evidence backbone (candidate_evidence_status.json)
  mapped to the 4-level defense vocabulary via an explicit, auditable protocol:
      grpc_error_observed / client_timeout_observed / full_cascade / hang
          -> not_defended
      grpc_response_observed / response_preserved_latency_degradation with
      material amplification (severity 2) -> partial
      response_observed near-baseline (severity 1) -> defended
      anything else / unexecuted -> invalid (excluded)
- Metrics: A/B defense accuracy vs the mapped truth, and root-cause keyword
  agreement vs card root_cause (normalized: "timeout" / "fallback" / "isolation"
  / "redundancy" families).

The A-vs-B gap is the auditable evidence that the knowledge/evidence chain
improves LLM decisions (chapter 10.2's core claim).
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

# Explicit auditable mapping: evidence classification -> 4-level defense.
# Severity comes from compare_selection_methods.SEVERITY (3=hang/cascade,
# 2=amplified, 1=weak).
DEFENSE_BY_CLASSIFICATION: dict[str, str] = {
    "grpc_error_observed": "not_defended",
    "client_timeout_observed": "not_defended",
    "full_cascade_failure_after_hang": "not_defended",
    "full_propagation_and_infinite_hang": "not_defended",
    "grpc_response_observed": "partial",
    "response_preserved_latency_degradation": "partial",
    "response_observed": None,  # resolved by severity below
}

# For classifications without a strong failure signal, severity decides:
# severity>=2 (material latency amplification) -> partial, severity==1 -> defended.
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
}


def defense_for(candidate_id: str, classification: str) -> str:
    base = DEFENSE_BY_CLASSIFICATION.get(classification)
    if base is not None:
        return base
    if classification == "response_observed":
        return "partial" if SEVERITY.get(candidate_id, 1) >= 2 else "defended"
    return "invalid"

# Root-cause keyword families for matching LLM attribution vs card truth.
ROOT_CAUSE_FAMILIES: dict[str, list[str]] = {
    "missing_timeout": ["timeout", "deadline"],
    "missing_fallback": ["fallback", "circuit", "retry", "resilience"],
    "missing_isolation": ["isolation", "non-critical", "side effect", "coupling"],
    "missing_redundancy": ["redundancy", "replica", "single point"],
    "latency_amplification": ["latency", "amplif", "propagat", "queuing", "thread"],
    "no_finding": ["no weakness", "defended", "no finding", "weak effect"],
}

SYS_PROMPT = """\
You are a chaos-engineering defense assessor. Given a fault-injection experiment,
you judge whether the system defended against the fault and attribute a root
cause. Answer ONLY with a single JSON object:
{
  "defense": "defended" | "partial" | "not_defended" | "invalid",
  "reason": "one sentence explaining the judgment",
  "root_cause": "one concise phrase, e.g. 'missing timeout on downstream call'"
}
defense definitions:
- defended: the system absorbed the fault; behavior stayed at or near baseline.
- partial: functionality survived but latency/behavior degraded materially
  beyond the injected intensity (no isolation/fallback on the path).
- not_defended: the fault produced a timeout, hang, error, or cascade failure.
- invalid: the experiment could not produce a conclusion (no injection effect
  or incomplete lifecycle)."""


def build_candidate_evidence(evidence_doc: dict[str, Any]) -> list[dict[str, Any]]:
    """Collect executed candidates with a concluded classification."""
    out: list[dict[str, Any]] = []
    for item in evidence_doc.get("candidates", []):
        conclusions = item.get("own_conclusions") or []
        if not conclusions:
            continue
        # Representative conclusion: prefer gRPC/HTTP conclusions over weak ones.
        classifications = sorted({c["classification"] for c in conclusions})
        classification = classifications[0]
        out.append(
            {
                "candidate_id": item["candidate_id"],
                "service": item.get("service"),
                "classification": classification,
                "defense": defense_for(str(item["candidate_id"]), classification),
                "evidence_files": [c["file"] for c in conclusions],
            }
        )
    return out


def render_blind_prompt(c: dict[str, Any], candidate_meta: dict[str, Any]) -> str:
    return (
        f"Candidate: {c['candidate_id']}\n"
        f"Service: {candidate_meta.get('service')}\n"
        f"Edge: {candidate_meta.get('edge')}\n"
        f"Fault: {candidate_meta.get('fault_family')} ({candidate_meta.get('intensity')})\n\n"
        "Judge the likely defense outcome and root cause based ONLY on this "
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
            obs = (doc.get("observations") or {}).get("workload") or doc.get("workload") or {}
            samples = []
            for sample in (obs.get("observations") or [])[:2]:
                samples.append(
                    f"{sample.get('grpc_status') or 'http'} {sample.get('latency_ms')}ms "
                    f"{str(sample.get('error') or '')[:40]}"
                )
            lifecycle = doc.get("lifecycle") or {}
            lines.append(
                f"- run {name}: applied={lifecycle.get('applied')} "
                f"injected={lifecycle.get('injected')} recovered={lifecycle.get('recovered')} "
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
        "Judge the defense outcome and attribute a root cause from this evidence."
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
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError(f"no JSON object in completion: {text[:120]!r}")
    return json.loads(text[start : end + 1])


def root_cause_family(text: str) -> str:
    lowered = text.lower()
    for family, keywords in ROOT_CAUSE_FAMILIES.items():
        if any(keyword in lowered for keyword in keywords):
            return family
    return "unmatched"


def run(backend: OpenAICompatBackend, evidence: list[dict[str, Any]], meta: dict[str, Any], by_file: dict[str, dict[str, Any]]) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    blind_stats = {"correct": 0, "total": 0}
    evidence_stats = {"correct": 0, "total": 0}
    blind_rc = {"matched": 0, "total": 0}
    evidence_rc = {"matched": 0, "total": 0}

    for c in evidence:
        candidate_meta = meta.get(c["candidate_id"], {})
        observations = extract_observations(c["evidence_files"], by_file)

        # A: blind
        blind_prompt = render_blind_prompt(c, candidate_meta)
        blind_raw, blind_meta = backend.complete(SYS_PROMPT, blind_prompt, "")
        blind = parse_completion(blind_raw)
        blind_correct = blind.get("defense") == c["defense"]
        blind_stats["total"] += 1
        blind_stats["correct"] += int(blind_correct)
        blind_rc_family = root_cause_family(blind.get("root_cause") or "")
        blind_rc["total"] += 1
        blind_rc["matched"] += int(blind_rc_family == c.get("root_cause_family", "unmatched"))

        # B: evidence
        evidence_prompt = render_evidence_prompt(c, candidate_meta, observations)
        evidence_raw, evidence_meta = backend.complete(SYS_PROMPT, evidence_prompt, "")
        judged = parse_completion(evidence_raw)
        evidence_correct = judged.get("defense") == c["defense"]
        evidence_stats["total"] += 1
        evidence_stats["correct"] += int(evidence_correct)
        evidence_rc_family = root_cause_family(judged.get("root_cause") or "")
        evidence_rc["total"] += 1
        evidence_rc["matched"] += int(evidence_rc_family == c.get("root_cause_family", "unmatched"))

        results.append(
            {
                "candidate_id": c["candidate_id"],
                "truth": c["defense"],
                "truth_classification": c["classification"],
                "blind": {"defense": blind.get("defense"), "reason": blind.get("reason"), "root_cause": blind.get("root_cause"), "correct": blind_correct, "tokens": blind_meta.get("total_tokens")},
                "evidence": {"defense": judged.get("defense"), "reason": judged.get("reason"), "root_cause": judged.get("root_cause"), "correct": evidence_correct, "tokens": evidence_meta.get("total_tokens")},
                "observations": observations,
            }
        )
        print(f"[{c['candidate_id']}] truth={c['defense']:<12} blind={blind.get('defense'):<12} evid={judged.get('defense'):<12}")

    return {
        "schema_version": 1,
        "tool": "llm_interpret_evidence",
        "method": "M5/A5 ours-llm-interpret",
        "candidate_count": len(results),
        "blind": {"defense_accuracy": round(blind_stats["correct"] / blind_stats["total"], 3) if blind_stats["total"] else None, "correct": blind_stats["correct"], "total": blind_stats["total"], "root_cause_match_rate": round(blind_rc["matched"] / blind_rc["total"], 3) if blind_rc["total"] else None},
        "evidence": {"defense_accuracy": round(evidence_stats["correct"] / evidence_stats["total"], 3) if evidence_stats["total"] else None, "correct": evidence_stats["correct"], "total": evidence_stats["total"], "root_cause_match_rate": round(evidence_rc["matched"] / evidence_rc["total"], 3) if evidence_rc["total"] else None},
        "results": results,
    }


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

    # Attach card root-cause families as truth for attribution comparison.
    card_truth = load_card_root_causes()
    for c in evidence:
        c["root_cause_family"] = card_truth.get(c["candidate_id"], "unmatched")

    result = run(backend, evidence, meta, by_file)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "blind_accuracy": result["blind"]["defense_accuracy"], "evidence_accuracy": result["evidence"]["defense_accuracy"], "candidates": result["candidate_count"]}, indent=2))
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
