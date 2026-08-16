"""Build the frozen five-category YAML15 primer for Sock Shop Ablation."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import yaml

from tools.yaml_confidence_categories import load_yaml_feature_rows


CATEGORY_ORDER = (
    "Pod disruption",
    "Network degradation",
    "Resource pressure",
    "Protocol/HTTP fault",
    "Composite/scheduled fault",
)
SIGNATURE_FIELDS = (
    "kind",
    "action_or_target",
    "mode",
    "selector_shape",
    "duration_bucket",
    "intensity_bucket",
)


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _signature(row: dict[str, Any]) -> tuple[str, ...]:
    return tuple(str(row.get(field, "unknown")) for field in SIGNATURE_FIELDS)


def _hamming(left: tuple[str, ...], right: tuple[str, ...]) -> int:
    return sum(first != second for first, second in zip(left, right))


def _select_three(rows: list[dict[str, Any]]) -> list[tuple[dict[str, Any], str]]:
    by_signature: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_signature[_signature(row)].append(row)
    for members in by_signature.values():
        members.sort(key=lambda item: str(item["path"]).replace("\\", "/"))

    ranked_signatures = sorted(by_signature, key=lambda item: (-len(by_signature[item]), item))
    if len(rows) < 3:
        raise ValueError("each YAML15 category must contain at least three valid YAML documents")

    selected: list[tuple[dict[str, Any], str]] = []
    first_signature = ranked_signatures[0]
    selected.append((by_signature[first_signature][0], "highest_frequency_signature"))

    if len(ranked_signatures) > 1:
        second_signature = ranked_signatures[1]
        selected.append((by_signature[second_signature][0], "second_highest_uncovered_signature"))
    else:
        selected.append((by_signature[first_signature][1], "same_signature_additional_real_example"))

    selected_paths = {str(item["path"]) for item, _ in selected}
    selected_signatures = [_signature(item) for item, _ in selected]
    frequencies = Counter(_signature(row) for row in rows)
    remaining = [row for row in rows if str(row["path"]) not in selected_paths]
    third = sorted(
        remaining,
        key=lambda row: (
            -min(_hamming(_signature(row), chosen) for chosen in selected_signatures),
            -frequencies[_signature(row)],
            _signature(row),
            str(row["path"]).replace("\\", "/"),
        ),
    )[0]
    selected.append((third, "maximum_signature_distance"))
    return selected


def _redact_document(document: dict[str, Any]) -> dict[str, Any]:
    endpoint_keys = {"path", "url", "host", "hostname", "domainName", "externalName"}
    generic_label_keys = ("app", "component", "role", "tier")

    def redact(value: Any, key: str | None = None, parent: str | None = None) -> Any:
        if isinstance(value, dict):
            result: dict[str, Any] = {}
            for child_key, child_value in value.items():
                if parent == "metadata" and child_key == "name":
                    result[child_key] = "yaml15-example"
                elif parent == "metadata" and child_key == "namespace":
                    result[child_key] = "target-namespace"
                elif child_key == "namespaces" and isinstance(child_value, list):
                    result[child_key] = ["target-namespace"]
                elif child_key in {"labelSelectors", "labels", "matchLabels"} and isinstance(child_value, dict):
                    result[child_key] = {
                        generic_label_keys[index] if index < len(generic_label_keys) else f"label-{index + 1}": "target-workload"
                        for index, _label in enumerate(sorted(child_value))
                    }
                elif child_key in endpoint_keys:
                    if child_key == "path":
                        result[child_key] = "/example"
                    elif child_key == "url":
                        result[child_key] = "https://example.invalid/health"
                    else:
                        result[child_key] = "example.invalid"
                elif child_key in {"patterns", "dnsPatterns"} and isinstance(child_value, list):
                    result[child_key] = ["example.invalid"]
                else:
                    result[child_key] = redact(child_value, child_key, child_key)
            return result
        if isinstance(value, list):
            return [redact(item, key, parent) for item in value]
        return value

    return redact(document)


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def build_yaml15_manifest(raw_yaml_root: Path, output_dir: Path) -> dict[str, Any]:
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"refusing to overwrite non-empty output directory: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)

    rows = [
        row
        for row in load_yaml_feature_rows(raw_yaml_root)
        if row.get("category") in CATEGORY_ORDER and row.get("parse_error") is None
    ]
    by_category: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_category[str(row["category"])].append(row)

    categories: dict[str, list[dict[str, Any]]] = {}
    prompt_examples: list[dict[str, str]] = []
    fingerprint_items: list[dict[str, str]] = []
    sequence = 0
    for category in CATEGORY_ORDER:
        category_rows = sorted(by_category[category], key=lambda item: str(item["path"]).replace("\\", "/"))
        examples: list[dict[str, Any]] = []
        for row, reason in _select_three(category_rows):
            sequence += 1
            source = Path(str(row["path"]))
            if not source.is_absolute():
                source = source.resolve()
            source_bytes = source.read_bytes()
            document = yaml.safe_load(source_bytes.decode("utf-8"))
            if not isinstance(document, dict):
                raise ValueError(f"selected YAML is not a mapping: {source}")
            redacted_document = _redact_document(document)
            redacted_text = yaml.safe_dump(redacted_document, sort_keys=False, allow_unicode=False)
            redacted_path = Path("examples") / f"{sequence:02d}-{_slug(category)}.yaml"
            destination = output_dir / redacted_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(redacted_text, encoding="utf-8", newline="\n")

            source_relative = source.relative_to(raw_yaml_root.resolve()).as_posix()
            example = {
                "order": sequence,
                "category": category,
                "source_path": source_relative,
                "source_sha256": hashlib.sha256(source_bytes).hexdigest(),
                "redacted_path": redacted_path.as_posix(),
                "redacted_sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
                "features": {field: row.get(field) for field in SIGNATURE_FIELDS},
                "selection_reason": reason,
            }
            examples.append(example)
            prompt_examples.append({"category": category, "yaml": redacted_text})
            fingerprint_items.append(
                {
                    "category": category,
                    "source_path": source_relative,
                    "source_sha256": example["source_sha256"],
                    "redacted_sha256": example["redacted_sha256"],
                }
            )
        categories[category] = examples

    prompt = {
        "schema_version": "sock-shop-ablation-yaml15-prompt-v1",
        "labeled_yaml_examples": prompt_examples,
    }
    prompt_path = output_dir / "yaml15-prompt.json"
    prompt_path.write_text(json.dumps(prompt, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    manifest = {
        "schema_version": "sock-shop-ablation-yaml15-manifest-v1",
        "total_examples": len(fingerprint_items),
        "category_order": list(CATEGORY_ORDER),
        "selection_policy": {
            "version": "frequency-two-plus-max-hamming-v1",
            "signature_fields": list(SIGNATURE_FIELDS),
            "runtime_outcomes_used": False,
            "full_results_used": False,
        },
        "selection_fingerprint_sha256": _canonical_hash(fingerprint_items),
        "prompt_path": prompt_path.name,
        "prompt_sha256": hashlib.sha256(prompt_path.read_bytes()).hexdigest(),
        "categories": categories,
        "human_review": "pending",
        "knowledge_base_updated": False,
    }
    (output_dir / "yaml15-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-yaml", type=Path, default=Path("raw_yaml"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build_yaml15_manifest(args.raw_yaml, args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
