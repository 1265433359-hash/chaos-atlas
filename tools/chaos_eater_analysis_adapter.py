"""ChaosEater analysis-phase adapter: faithful prompt extraction + real-data run.

Extracts ChaosEater's AnalysisAgent (commit 47c4e44): SYS_ANALYZE_RESULT +
USER_ANALYZE_RESULT prompts and the AnalysisReport schema, without the full
docker-compose/langchain stack. Inputs are constructed from OUR real
experiment data in ChaosEater's own to_str formats:
- system_overview: k8s-style candidate overview + source-verified contracts
- hypothesis_overview: the candidate's predicted invariant/root cause
- experiment_plan_summary: injection plan (fault/intensity/duration)
- experiment_result: the ACTUAL runtime observations (baseline/inject/recover)

Output: an AnalysisReport (free-text) from the same LLM family. We then
compare ChaosEater's attributed root cause vs OUR evidence-chain root cause
(knowledge-card root_cause + source line) to demonstrate verifiability.
"""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any

from chaos_eater_adapter.llm_backend import OpenAICompatBackend

ROOT = Path(__file__).resolve().parents[1]
EXECUTION_DIR = ROOT / "artifacts" / "experiments" / "execution"

# Faithful extraction from chaos_eater/analysis/llm_agents/analysis_agent.py.
SYS_ANALYZE_RESULT = """\
You are a helpful AI assistant for Chaos Engineering.
Given K8s manifests for a network system, its hypothesis, the overview of a Chaos-Engineering experiment, and the experimental results, you will analyze the experimental results.
Always keep the following rules:
- Analyze step by step why the test(s) failed, based on the system configurations (manifests) and the flow of the experiment.
- Specify the cause while mentioning the corresponding system configurations and the corresponding phenomena in the Chaos-Engineering experiment.
- The analysis report here will be used for reconfiguring the system later to avoid the failures and improve resiliency. Therefore, make carefully the report rich in insights so that it will be helpful at that time.
- When providing insights and reconfiguration recommendations, limit them to areas related to the failed test.
- Respond with a single JSON object: {"report": "your full analysis report"}"""

USER_ANALYZE_RESULT = """\
# Here is the overview of my system:
{system_overview}

# Here is the hypothesis for my system:
{hypothesis_overview}

# Here is the overview of my Chaos-Engineering experiment to verify the hypothesis:
{experiment_plan_summary}

# The experiment's results are as follows:
{experiment_result}

Now, please analyze the results and provide an analysis report rich in insights."""


def load_run_files() -> dict[str, dict[str, Any]]:
    by_file: dict[str, dict[str, Any]] = {}
    for path in EXECUTION_DIR.glob("*.json"):
        if not any(tag in path.name for tag in ("confirmation", "m1_batch", "m1_ext", "smoke", "track_k", "pros_")):
            continue
        try:
            by_file[path.name] = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
    return by_file


def candidate_meta(candidate_id: str) -> dict[str, Any]:
    from extended_candidate_pool import extended_candidate_pool

    for c in extended_candidate_pool():
        if c["candidate_id"] == candidate_id:
            return c
    return {}


def contract_text(candidate_id: str, edge: str) -> str:
    inv = json.loads((ROOT / "artifacts" / "experiments" / "contract_inventory.json").read_text(encoding="utf-8"))
    contracts = inv.get("contracts", {})
    cand_map = inv.get("candidate_map", {})
    key = cand_map.get(candidate_id) or edge
    c = contracts.get(key)
    if not c:
        return f"- {edge}: contract unknown (not source-checked)"
    return f"- {edge}: contract={c['contract']} ({c.get('evidence', '')[:100]})"


def experiment_result_str(candidate_id: str, files: list[str], by_file: dict[str, dict[str, Any]]) -> str:
    """Build ChaosExperimentResult.to_str-like text from real run files."""
    lines = ["Passed unittests:"]
    failed = []
    passed_found = False
    for name in sorted(files):
        doc = by_file.get(name)
        if not doc:
            continue
        classification = doc.get("result_classification") or (doc.get("classification_details") or {}).get("classification")
        lifecycle = doc.get("lifecycle") or {}
        detail = (doc.get("classification_details") or {}).get("observations") or {}
        observed = detail.get("observed_median_latency_ms")
        baseline = detail.get("baseline_median_latency_ms")
        # gRPC runner samples
        wl = (doc.get("observations") or {}).get("workload") or doc.get("workload") or {}
        samples = []
        for s in (wl.get("observations") or [])[:2]:
            samples.append(f"{s.get('grpc_status') or 'http'} {s.get('latency_ms')}ms {str(s.get('error') or '')[:40]}")
        if not samples:
            for r in (doc.get("requests") or [])[:2]:
                samples.append(f"{r.get('status_code') or 'http'} {r.get('latency_ms')}ms {str(r.get('error') or '')[:40]}")
        log = (
            f"injected={lifecycle.get('injected')} recovered={lifecycle.get('recovered')} "
            f"baseline={baseline}ms observed={observed}ms samples=[{'; '.join(samples)}] "
            f"classification={classification}"
        )
        if classification in ("grpc_error_observed", "client_timeout_observed", "runner_error") or "timeout" in str(classification).lower():
            failed.append((name, log))
        else:
            passed_found = True
            lines.append(f"- {name}: {log}")
    lines.append("Failed unittests:")
    if not failed:
        lines.append("- (none)")
    for name, log in failed:
        lines.append(f"- {name}\n```log\n{log[:500]}\n```")
    return "\n".join(lines)


def build_prompts(candidate_id: str, by_file: dict[str, dict[str, Any]]) -> dict[str, str]:
    meta = candidate_meta(candidate_id)
    edge = meta.get("edge", "")
    system_overview = (
        f"The system is a microservices demo. Candidate under test: {candidate_id}\n"
        f"- service: {meta.get('service')}, edge: {edge}\n"
        f"- fault: {meta.get('fault_family')} intensity {meta.get('intensity')} duration {meta.get('duration')}\n"
        f"- mutation: {meta.get('mutation', '')}\n"
        f"Source-verified contracts:\n{contract_text(candidate_id, edge)}"
    )
    hypothesis_overview = (
        f"Hypothesis: {meta.get('invariant', '')}\n"
        f"Predicted root cause if it fails: {meta.get('root_cause', '')}"
    )
    experiment_plan_summary = (
        f"Experiment plan: NetworkChaos {meta.get('fault_family')} "
        f"({meta.get('intensity')}) on {meta.get('service')}, duration {meta.get('duration')}, "
        "baseline before injection, recovery + cleanup after."
    )
    # evidence files for this candidate
    evidence_doc = json.loads((EXECUTION_DIR / "candidate_evidence_status.json").read_text(encoding="utf-8"))
    files = []
    for item in evidence_doc.get("candidates", []):
        if item["candidate_id"] == candidate_id:
            files = [c["file"] for c in item.get("own_conclusions", [])]
            break
    experiment_result = experiment_result_str(candidate_id, files, by_file)
    return {
        "system_overview": system_overview,
        "hypothesis_overview": hypothesis_overview,
        "experiment_plan_summary": experiment_plan_summary,
        "experiment_result": experiment_result,
    }


def parse_report(text: str) -> str:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end <= start:
        # tolerate plain text fallback
        return text.strip()
    try:
        obj = json.loads(text[start : end + 1])
        if isinstance(obj, dict) and "report" in obj:
            return str(obj["report"])
    except json.JSONDecodeError:
        pass
    return text.strip()


def extract_cause(report: str) -> str:
    """Best-effort root-cause sentence for comparison (first cause-like line)."""
    for line in report.splitlines():
        if any(k in line.lower() for k in ("cause", "root", "reason", "because", "due to", "fail")):
            return line.strip()[:160]
    return report.strip()[:160]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", nargs="+", default=None,
                        help="candidate ids to analyze; default = all 15 weakness candidates")
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--base-url", default="https://api.deepseek.com/v1")
    parser.add_argument("--model", default="deepseek-v4-flash")
    parser.add_argument("--output", type=Path, default=EXECUTION_DIR / "chaos_eater_analysis_results.json")
    args = parser.parse_args()
    if args.api_key is None:
        args.api_key = os.environ.get("CHAOS_EATER_API_KEY")
    if not args.api_key:
        raise SystemExit("--api-key or CHAOS_EATER_API_KEY is required")

    from compare_selection_methods import SEVERITY

    weakness = [c for c, s in SEVERITY.items() if s >= 2]
    candidates = args.candidates or weakness
    by_file = load_run_files()
    backend = OpenAICompatBackend(base_url=args.base_url, api_key=args.api_key, model=args.model, json_mode=False)

    results: list[dict[str, Any]] = []
    for candidate_id in candidates:
        prompts = build_prompts(candidate_id, by_file)
        user_prompt = USER_ANALYZE_RESULT.format(**prompts)
        raw, meta = backend.complete(SYS_ANALYZE_RESULT, user_prompt, "")
        report = parse_report(raw)
        results.append({
            "candidate_id": candidate_id,
            "chaos_eater_report": report,
            "chaos_eater_cause": extract_cause(report),
            "tokens": meta.get("total_tokens"),
        })
        print(f"[{candidate_id}] cause: {extract_cause(report)[:80]}")

    args.output.write_text(json.dumps({
        "schema_version": 1,
        "tool": "chaos_eater_analysis_adapter",
        "model": args.model,
        "source": "AnalysisAgent (commit 47c4e44) prompt extraction, real experiment inputs",
        "results": results,
    }, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "analyzed": len(results)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
