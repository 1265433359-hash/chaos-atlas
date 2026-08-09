"""B1+B2: robustness of selection-method comparison.

B1 (no significance): bootstrap the severity-weighted recall over candidate
samples to get 95% CIs per method, and a bootstrap pairwise difference CI
between methods (M1 vs others) so 'who is better' has a statistical basis.

B2 (arbitrary severity weights): re-run the ranking under several weight
schemata (3/2/1, 5/2/1, 4/3/1, 3/1/0, 2/2/1) and report whether the method
ordering flips. If the ordering is stable across schemata, the weights are
not driving the conclusion.

Reads only committed registries; performs no injection.
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from typing import Any

import evidence_classification

ROOT = Path(__file__).resolve().parents[1]
EXECUTION_DIR = ROOT / "artifacts" / "experiments" / "execution"

METHOD_IDS = ("M0", "M1", "M3", "M4", "A0", "A1", "A2", "A3", "A4")

WEIGHT_SCHEMATA: list[tuple[str, dict[str, int]]] = [
    ("3-2-1", {"3": 3, "2": 2, "1": 1}),   # current
    ("5-2-1", {"3": 5, "2": 2, "1": 1}),   # severe faults heavier
    ("4-3-1", {"3": 4, "2": 3, "1": 1}),   # partial gaps closer to severe
    ("3-1-0", {"3": 3, "2": 1, "1": 0}),   # weak effects excluded
    ("2-2-1", {"3": 2, "2": 2, "1": 1}),   # severe==amplified
]


def load(registry_path: Path) -> dict[str, Any]:
    return json.loads(registry_path.read_text(encoding="utf-8"))


def severity_weights() -> dict[str, int]:
    from compare_selection_methods import SEVERITY

    return SEVERITY


def method_selections(registry: dict[str, Any]) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for method in registry.get("methods", []):
        method_id = str(method.get("id"))
        if method_id in METHOD_IDS:
            out[method_id] = {
                str((plan.get("execution") or {}).get("candidate_id"))
                for plan in (method.get("plans") or [])
            }
    return out


def weighted_recall(selected: set[str], known: set[str], sev: dict[str, int], weights: dict[str, int]) -> float:
    known_weight = sum(weights[str(sev[c])] for c in known)
    if not known_weight:
        return 0.0
    hit = sum(weights[str(sev[c])] for c in selected & known)
    return hit / known_weight


def bootstrap(selected: set[str], known: list[str], sev: dict[str, int], weights: dict[str, int],
              n_boot: int = 1000, seed: int = 7) -> dict[str, Any]:
    """Resample candidates with replacement; report mean and 95% CI of
    weighted recall. This estimates sampling variance of the metric over the
    candidate universe, not LLM temperature noise.

    Phase-6 remediation (findings #9): the denominator is computed PER SAMPLE
    (sum of weights over the drawn candidates), not a fixed overall-population
    weight. The old fixed denominator produced a biased CI whenever the sample
    weight differed from the population weight.
    """
    rng = random.Random(seed)
    known_set = set(known)
    values: list[float] = []
    for _ in range(n_boot):
        sample = [known[rng.randrange(len(known))] for _ in range(len(known))]
        sample_weight = sum(weights[str(sev[c])] for c in sample)
        if not sample_weight:
            continue
        hit = sum(weights[str(sev[c])] for c in sample if c in selected)
        values.append(hit / sample_weight)
    if not values:
        return {"mean": 0.0, "ci95": [0.0, 0.0]}
    values.sort()
    lo = values[int(0.025 * len(values))]
    hi = values[int(0.975 * len(values))]
    return {"mean": round(sum(values) / len(values), 3), "ci95": [round(lo, 3), round(hi, 3)]}


def pairwise_difference(sel_a: set[str], sel_b: set[str], known: list[str], sev: dict[str, int],
                        weights: dict[str, int], n_boot: int = 1000, seed: int = 7) -> dict[str, Any]:
    rng = random.Random(seed)
    diffs: list[float] = []
    for _ in range(n_boot):
        sample = [known[rng.randrange(len(known))] for _ in range(len(known))]
        sample_weight = sum(weights[str(sev[c])] for c in sample)
        if not sample_weight:
            continue
        a = sum(weights[str(sev[c])] for c in sample if c in sel_a) / sample_weight
        b = sum(weights[str(sev[c])] for c in sample if c in sel_b) / sample_weight
        diffs.append(a - b)
    if not diffs:
        return {"mean_diff": 0.0, "ci95": [0.0, 0.0], "significant_at_5pct": False}
    diffs.sort()
    ci = [round(diffs[int(0.025 * len(diffs))], 3), round(diffs[int(0.975 * len(diffs))], 3)]
    return {"mean_diff": round(sum(diffs) / len(diffs), 3), "ci95": ci,
            "significant_at_5pct": ci[0] > 0 or ci[1] < 0}


def classify_evidence_candidate(item: dict[str, Any]) -> str:
    """weakness | below_threshold | invalid | unclassified for one candidate.

    Round-2 finding #2: delegates to the SHARED evidence_classification module so
    the invalid-class set and weakness set are identical to compare_selection_methods.
    """
    return evidence_classification.classify_candidate(item)


def analyze(replicate: int, registry_path: Path | None, n_boot: int,
            sev: dict[str, int] | None = None) -> dict[str, Any]:
    registry = load(registry_path or EXECUTION_DIR / f"deep_matrix_registry_r{replicate}_m1.json")
    universe = set(registry.get("candidate_universe") or [])
    evidence = load(EXECUTION_DIR / "candidate_evidence_status.json")
    if sev is None:
        sev = severity_weights()
    # Phase-6 (findings #5/#9/#10) + round-3 P2-2: known candidates MUST come
    # from the SAME shared known set used by compare_selection_methods
    # (evidence_classification.known_candidate_ids), which checks
    # own_discovery_evidence AND drops only all-invalid candidates. Previously
    # this function iterated universe evidence on its own and only excluded
    # "invalid", so a discovery-less candidate would silently re-enter the
    # denominator and the two tools would diverge.
    candidates_by_id = {str(c.get("candidate_id")): c for c in evidence.get("candidates", [])}
    evidence_candidates = {
        str(c.get("candidate_id")): classify_evidence_candidate(c)
        for c in evidence.get("candidates", [])
    }
    known_shared = evidence_classification.known_candidate_ids(evidence)
    known_all = sorted(cid for cid in known_shared if cid in universe)
    known = [c for c in known_all if evidence_candidates.get(c) != "invalid"]
    known_set = set(known)
    invalid_in_universe = sorted(
        cid for cid in candidates_by_id
        if cid in universe and classify_evidence_candidate(candidates_by_id[cid]) == "invalid"
    )
    weakness_ids = sorted(c for c in known if evidence_candidates.get(c) == "weakness")
    below_threshold_ids = sorted(c for c in known if evidence_candidates.get(c) == "below_threshold")
    selections = method_selections(registry)

    schema_results: dict[str, dict[str, float]] = {}
    for name, weights in WEIGHT_SCHEMATA:
        schema_results[name] = {
            method_id: round(weighted_recall(sel, known_set, sev, weights), 3)
            for method_id, sel in selections.items()
        }

    base_weights = dict(WEIGHT_SCHEMATA[0][1])
    boots = {
        method_id: bootstrap(sel, known, sev, base_weights, n_boot)
        for method_id, sel in selections.items()
    }
    pairs = {}
    if "M1" in selections and "M3" in selections and "M4" in selections and "M0" in selections:
        for other in ("M3", "M4", "M0"):
            pairs[f"M1-vs-{other}"] = pairwise_difference(
                selections["M1"], selections[other], known, sev, base_weights, n_boot
            )

    # Rank stability across schemata.
    orders: dict[str, list[str]] = {
        name: sorted(selections, key=lambda m: -schema_results[name][m])
        for name in schema_results
    }
    first_schema = next(iter(orders))
    stable = all(orders[name] == orders[first_schema] for name in orders)

    return {
        "schema_version": 2,
        "tool": "selection_robustness",
        "replicate": replicate,
        "n_bootstrap": n_boot,
        "note": "bootstrap resamples candidates (sampling variance over the universe), not LLM temperature; denominator is per-sample (phase-6)",
        "universe": sorted(universe),
        "universe_size": len(universe),
        "known_classification": {
            "weakness": weakness_ids,
            "below_threshold": below_threshold_ids,
            "invalid": invalid_in_universe,
        },
        "known_count": len(known),
        "invalid_in_universe_count": len(invalid_in_universe),
        "severity_weights_schemata": {name: w for name, w in WEIGHT_SCHEMATA},
        "weighted_recall_by_schema": schema_results,
        "rank_order_by_schema": orders,
        "rank_order_stable_across_schemata": stable,
        "bootstrap_ci95_baseline_schema": boots,
        "pairwise_difference_ci95": pairs,
        "interpretation": (
            "A pairwise CI excluding 0 is a 5%-level significant difference (bootstrap). "
            "Rank-order stability across weight schemata guards B2 (weights not driving the conclusion). "
            "Do NOT over-interpret rank order: universe is small and partly selected by our own "
            "methodology (M4 lineage), so rankings are descriptive, not a superiority claim."
        ),
    }


def render_markdown(report: dict[str, Any]) -> str:
    kc = report["known_classification"]
    lines = [
        f"# Selection robustness — replicate {report['replicate']}",
        "",
        f"Universe: {report['universe_size']} candidates | known: {report['known_count']} "
        f"(weakness {len(kc['weakness'])}, below_threshold {len(kc['below_threshold'])}, "
        f"invalid-in-universe {report['invalid_in_universe_count']})",
        "",
        "## B1: bootstrap CI (baseline schema 3/2/1, n=1000, per-sample denominator)",
        "",
        "| Method | mean w-recall | 95% CI |",
        "|---|---:|---:|",
    ]
    for method_id, b in report["bootstrap_ci95_baseline_schema"].items():
        lines.append(f"| {method_id} | {b['mean']:.3f} | {b['ci95'][0]:.3f}–{b['ci95'][1]:.3f} |")
    lines.append("")
    lines.append("## B1: pairwise difference CI (M1 minus other)")
    lines.append("")
    lines.append("| Pair | mean diff | 95% CI | 5% significant |")
    lines.append("|---|---:|---:|---|")
    for pair, p in report["pairwise_difference_ci95"].items():
        lines.append(f"| {pair} | {p['mean_diff']:.3f} | {p['ci95'][0]:.3f}–{p['ci95'][1]:.3f} | {p['significant_at_5pct']} |")
    lines.append("")
    lines.append("## B2: weight-schema sensitivity")
    lines.append("")
    lines.append("| Schema | " + " | ".join(report["rank_order_by_schema"].keys()) + " |")
    lines.append("|---|" + "---|" * len(report["rank_order_by_schema"]))
    for schema, order in report["rank_order_by_schema"].items():
        lines.append(f"| {schema} | " + " > ".join(order) + " |")
    lines.append("")
    lines.append(f"**Rank order stable across schemata: {report['rank_order_stable_across_schemata']}**")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replicate", type=int, required=True)
    parser.add_argument("--registry", type=Path, default=None)
    parser.add_argument("--n-boot", type=int, default=1000)
    parser.add_argument("--output-json", type=Path, default=None)
    parser.add_argument("--output-md", type=Path, default=None)
    args = parser.parse_args()
    report = analyze(args.replicate, args.registry, args.n_boot)
    suffix = "ext" if args.registry else ""
    stem = f"selection_robustness_r{args.replicate}{'_' + suffix if suffix else ''}"
    out_json = args.output_json or EXECUTION_DIR / f"{stem}.json"
    out_md = args.output_md or EXECUTION_DIR / f"{stem}.md"
    out_json.write_text(json.dumps(report, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    out_md.write_text(render_markdown(report), encoding="utf-8")
    print(render_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
