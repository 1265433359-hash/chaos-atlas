"""Build a clean, offline LLM-selection-only ablation package.

This tool deliberately does not call an LLM or touch Kubernetes. It derives a
new versioned input bundle from the previously frozen Gate 0-2 bundles while
removing fields that are forbidden in any LLM input, including mutation_path.
The original bundles and pools are never overwritten.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT / "artifacts" / "experiments" / "knowledge_ablation_prompts"
OUT_ROOT = ROOT / "artifacts" / "experiments" / "knowledge_ablation_selection_only"
PROTOCOL = ROOT / "artifacts" / "experiments" / "llm_knowledge_ablation_selection_only_protocol_v1.md"

PROJECT_ARMS = {
    "ESHOP": ("blind", "generic", "partial-pre"),
    "SOCIALNET": ("blind", "generic", "full-pre"),
}
PHASES = ("pilot", "formal")
SEEDS = {"pilot": (1001, 1002, 1003), "formal": (2001, 2002, 2003)}
FORBIDDEN_FIELDS = {
    "oracle_label",
    "static_evidence_refs",
    "candidate_protection_classification",
    "classification",
    "verdict",
    "quota_compliance",
    "evidence_cases",
    "evidence_files",
    "evidence_count",
    "corpus_evidence",
    "experiment_evidence",
    "mutation_path",
}
FORBIDDEN_TERMS = (
    "oracle_label",
    "stored-out-of-band",
    "candidate_protection_classification",
    "environment_blocked",
    "final_verdict",
    "quota_compliance",
    "root_cause",
    "mutation_path",
)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def dump_json(value: Any) -> str:
    return json.dumps(value, indent=2, ensure_ascii=True) + "\n"


def clean_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: clean_value(item)
            for key, item in value.items()
            if key not in FORBIDDEN_FIELDS
        }
    if isinstance(value, list):
        return [clean_value(item) for item in value]
    return value


def count_forbidden_fields(value: Any, path: str = "$") -> list[str]:
    hits: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if key in FORBIDDEN_FIELDS:
                hits.append(f"{path}.{key}")
            hits.extend(count_forbidden_fields(item, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            hits.extend(count_forbidden_fields(item, f"{path}[{index}]"))
    return hits


def render_prompt(bundle: dict[str, Any], system_template: str) -> str:
    sections = bundle["sections"]
    k = bundle["selection_budget_k"]
    system = system_template.replace("{k}", str(k))
    user_parts = [
        "PROJECT UNDER TEST - INTAKE SUMMARY",
        dump_json(sections["project_intake_summary"]),
        f"CANDIDATE POOL ({len(sections['candidate_descriptors'])} candidates, in the order given)",
        dump_json(sections["candidate_descriptors"]),
    ]
    if sections.get("knowledge") is not None:
        user_parts.extend(["KNOWLEDGE SUPPLEMENT", dump_json(sections["knowledge"])])
    user_parts.extend([
        "TASK",
        f"Rank exactly {k} distinct candidates from the pool, from most to least likely "
        "to expose a confirmed weakness, and return a single JSON object with a "
        "selected array containing candidate_id, rank, and rationale.",
    ])
    return system.rstrip() + "\n\n===== USER =====\n" + "\n".join(user_parts) + "\n"


def build() -> dict[str, Any]:
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    file_hashes: dict[str, str] = {}
    audits: list[dict[str, Any]] = []
    system_template = (
        "You are a senior chaos-engineering analyst in a candidate-selection study. "
        "Select exactly {k} distinct candidates from the supplied frozen pool. "
        "Use only candidate IDs in the pool, rank them, and provide a short rationale. "
        "Return one JSON object with selected entries containing candidate_id, rank, rationale."
    )

    for project, arms in PROJECT_ARMS.items():
        source_manifest = load_json(SOURCE_ROOT / project / "prompt_manifest.json")
        for arm_dir in arms:
            for phase in PHASES:
                source_bundle_path = SOURCE_ROOT / project / arm_dir / phase / "bundle.json"
                source_seed = SEEDS[phase][0]
                source_prompt_path = SOURCE_ROOT / project / arm_dir / phase / f"seed-{source_seed}.prompt.txt"
                source_bundle = load_json(source_bundle_path)
                clean_bundle = clean_value(source_bundle)
                clean_bundle["selection_only"] = True
                clean_bundle["source_bundle_sha256"] = sha256_file(source_bundle_path)
                rel_dir = Path(project) / arm_dir / phase
                out_dir = OUT_ROOT / rel_dir
                out_dir.mkdir(parents=True, exist_ok=True)
                bundle_path = out_dir / "bundle.json"
                bundle_path.write_text(dump_json(clean_bundle), encoding="utf-8")
                file_hashes[str(bundle_path.relative_to(ROOT)).replace("\\", "/")] = sha256_file(bundle_path)

                source_prompt = source_prompt_path.read_text(encoding="utf-8")
                system = source_prompt.split("===== USER =====", 1)[0].strip()
                prompt = render_prompt(clean_bundle, system)
                prompt_hashes: dict[str, str] = {}
                order_hashes: dict[str, str] = {}
                for seed in SEEDS[phase]:
                    permutation = source_manifest["candidate_order_permutations"][phase][str(seed)]
                    descriptors = clean_bundle["sections"]["candidate_descriptors"]
                    if len(permutation) != len(descriptors) or sorted(permutation) != list(range(len(descriptors))):
                        raise ValueError(f"invalid candidate permutation for {project}/{phase}/{seed}")
                    seed_bundle = dict(clean_bundle)
                    seed_sections = dict(clean_bundle["sections"])
                    seed_sections["candidate_descriptors"] = [descriptors[index] for index in permutation]
                    seed_bundle["sections"] = seed_sections
                    ordered_ids = [item["candidate_id"] for item in seed_sections["candidate_descriptors"]]
                    prompt_path = out_dir / f"seed-{seed}.prompt.txt"
                    seed_prompt = render_prompt(seed_bundle, system)
                    prompt_path.write_text(seed_prompt, encoding="utf-8")
                    rel = str(prompt_path.relative_to(ROOT)).replace("\\", "/")
                    prompt_hashes[str(seed)] = sha256_file(prompt_path)
                    order_hashes[str(seed)] = sha256_bytes(dump_json(ordered_ids).encode("utf-8"))
                    file_hashes[rel] = prompt_hashes[str(seed)]

                text = dump_json(clean_bundle) + "\n".join(
                    (out_dir / f"seed-{seed}.prompt.txt").read_text(encoding="utf-8")
                    for seed in SEEDS[phase]
                )
                term_hits = sorted({term for term in FORBIDDEN_TERMS if re.search(re.escape(term), text)})
                field_hits = count_forbidden_fields(clean_bundle)
                audits.append({
                    "project": project,
                    "arm": clean_bundle["arm_id"],
                    "phase": phase,
                    "pass": not term_hits and not field_hits,
                    "forbidden_term_hits": term_hits,
                    "forbidden_field_hits": field_hits,
                    "removed_fields": sorted(FORBIDDEN_FIELDS),
                    "bundle_sha256": sha256_file(bundle_path),
                    "prompt_sha256": prompt_hashes,
                    "candidate_order_sha256": order_hashes,
                })

    manifest = {
        "schema_version": 1,
        "kind": "selection_only_llm_input_manifest",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "protocol": str(PROTOCOL.relative_to(ROOT)).replace("\\", "/"),
        "projects": PROJECT_ARMS,
        "phases": PHASES,
        "seeds": SEEDS,
        "no_llm_called": True,
        "no_runtime_execution": True,
        "files": file_hashes,
        "leakage_audit": audits,
    }
    manifest_path = OUT_ROOT / "selection_only_manifest.json"
    manifest_path.write_text(dump_json(manifest), encoding="utf-8")
    return manifest


if __name__ == "__main__":
    result = build()
    failed = [item for item in result["leakage_audit"] if not item["pass"]]
    print(json.dumps({"files": len(result["files"]), "audits": len(result["leakage_audit"]), "failed": failed}, indent=2))
    raise SystemExit(1 if failed else 0)
