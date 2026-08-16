"""Post-hoc runtime adapter for the category-free Ablation discovery."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.run_sock_shop_confidence_runtime import plan_confidence_runtime


ACTION_CATEGORIES = {
    "pod-kill": "Pod disruption",
    "pod-failure": "Pod disruption",
    "container-kill": "Pod disruption",
    "delay": "Network degradation",
    "network-delay": "Network degradation",
    "loss": "Network degradation",
    "partition": "Network degradation",
    "cpu": "Resource pressure",
    "memory": "Resource pressure",
    "abort": "Protocol/HTTP fault",
    "http-abort": "Protocol/HTTP fault",
    "http-delay": "Protocol/HTTP fault",
    "dns": "Protocol/HTTP fault",
    "dns-error": "Protocol/HTTP fault",
    "scheduled-delay": "Composite/scheduled fault",
    "scheduled-pod-kill": "Composite/scheduled fault",
    "schedule": "Composite/scheduled fault",
}
ABLATION_METHODS = {"chaosatlas-ablation", "chaosatlas-ablation-yaml15"}


def infer_runtime_category(action: Any) -> str | None:
    normalized = str(action or "").strip().lower().replace("_", "-")
    return ACTION_CATEGORIES.get(normalized)


def _identity_token(value: Any) -> str:
    return "-".join(str(value or "unknown").strip().lower().replace("_", "-").split())


def _discovery_family_key(hypothesis: dict[str, Any]) -> str:
    return "|".join(
        (
            f"target={_identity_token(hypothesis.get('target_service'))}",
            f"action={_identity_token(hypothesis.get('action_or_target'))}",
            f"position={_identity_token(hypothesis.get('call_chain_position'))}",
        )
    )


def _deduplicate_yaml15_hypotheses(hypotheses: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for hypothesis in hypotheses:
        grouped.setdefault(_discovery_family_key(hypothesis), []).append(hypothesis)
    representatives = []
    for family_key, members in grouped.items():
        representative = dict(members[0])
        representative.update(
            {
                "discovery_family_key": family_key,
                "family_size": len(members),
                "family_members": [member.get("id") for member in members],
                "representative_selection_reason": "first_generation_in_normalized_discovery_family",
            }
        )
        representatives.append(representative)
    return representatives


def build_ablation_runtime_candidates(discovery_path: Path, output_dir: Path) -> dict[str, Any]:
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"refusing to overwrite non-empty output directory: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    source_bytes = discovery_path.read_bytes()
    source = json.loads(source_bytes.decode("utf-8"))
    method = source.get("method")
    if method not in ABLATION_METHODS:
        raise ValueError("source discovery is not the Ablation method")
    if source.get("status") != "completed" or not source.get("self_stop"):
        raise ValueError("Ablation discovery must be completed by self-stop before runtime compilation")

    source_hypotheses = list(source.get("hypotheses") or [])
    hypotheses = (
        _deduplicate_yaml15_hypotheses(source_hypotheses)
        if method == "chaosatlas-ablation-yaml15"
        else source_hypotheses
    )
    mapped = []
    blocked = []
    for order, hypothesis in enumerate(hypotheses):
        category = infer_runtime_category(hypothesis.get("action_or_target"))
        if category is None:
            blocked.append(
                {
                    "source_order": order,
                    "hypothesis_id": hypothesis.get("id"),
                    "reason": "posthoc_runtime_category_unmapped",
                }
            )
            continue
        mapped.append(
            {
                **hypothesis,
                "method": method,
                "category": category,
                "category_assignment": "posthoc_runtime_adapter",
                "source_order": order,
            }
        )

    posthoc_discovery = {
        **{key: value for key, value in source.items() if key != "hypotheses"},
        "hypotheses": mapped,
        "posthoc_runtime_adapter": {
            "classification_visible_to_discovery": method == "chaosatlas-ablation-yaml15",
            "classification_examples_visible_to_discovery": method == "chaosatlas-ablation-yaml15",
            "source_discovery": str(discovery_path),
            "source_discovery_sha256": hashlib.sha256(source_bytes).hexdigest(),
            "blocked": blocked,
            "deduplication": {
                "applied": method == "chaosatlas-ablation-yaml15",
                "fields": ["target_service", "action_or_target", "call_chain_position"],
                "representative": "first_generation_in_normalized_discovery_family",
                "runtime_outcomes_used": False,
            },
        },
    }
    posthoc_path = output_dir / "posthoc-runtime-discovery.json"
    posthoc_path.write_text(
        json.dumps(posthoc_discovery, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    runtime_plan = plan_confidence_runtime(
        {method: posthoc_discovery},
        output_dir=output_dir / "runtime",
        execute=False,
        replicates=2,
        prior_runtime_roots=[],
        fresh_only=True,
    )
    result = {
        "schema_version": "sock-shop-ablation-posthoc-runtime-v1",
        "method": method,
        "source_discovery": str(discovery_path),
        "source_discovery_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "source_hypotheses": len(source_hypotheses),
        "deduplicated_hypotheses": len(hypotheses),
        "duplicate_hypotheses": len(source_hypotheses) - len(hypotheses),
        "compiled_hypotheses": len(mapped),
        "blocked_hypotheses": len(blocked),
        "blocked": blocked,
        "runtime_plan": str(output_dir / "runtime" / "runtime_plan.json"),
        "runtime_plan_status": runtime_plan.get("status"),
        "human_review": "pending",
        "knowledge_base_updated": False,
    }
    (output_dir / "adapter-summary.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--discovery", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build_ablation_runtime_candidates(args.discovery, args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
