"""Produce a deterministic, path-only repository classification report.

The inventory intentionally does not open file contents. It is safe to run before
selective staging because it reports names, sizes, Git state, and policy classes
without exposing credentials or private file contents.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from collections import Counter
from pathlib import Path
from typing import Iterable


SCHEMA_VERSION = "chaosatlas-repository-inventory-v1"


def _normal(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix() if path != root else "."


def classify_path(relative: str, is_dir: bool = False) -> str:
    """Classify a relative path using stable, path-only policy rules."""
    value = relative.replace("\\", "/")
    while value.startswith("./"):
        value = value[2:]
    parts = value.split("/") if value else []
    name = parts[-1] if parts else value
    if parts and (
        parts[0] == ".tmp"
        or parts[0].startswith((".tmp-", ".pytest-tmp-", ".venv-"))
        or parts[0] in {".pytest-tmp2", ".venv"}
    ):
        return "local_generated"
    if parts and parts[0] in {".git", ".planning", ".pytest_cache", ".secrets", ".email-notify-outbox"}:
        return "local_state"
    if parts and parts[0] == ".pytest-cache-disabled":
        return "local_state"
    if name.endswith((".kubeconfig", ".pem", ".key", ".p12", ".pfx", ".jks")):
        return "never_commit"
    if name in {"kubeconfig", "credentials.json", "credentials.yaml", "credentials.yml"}:
        return "never_commit"
    if parts and parts[0] == "tools" and len(parts) > 1 and parts[1] == "bin":
        return "external_source"
    if parts and parts[0] in {"tools", "src"}:
        return "mainline_source"
    if parts and parts[0] in {"projects", "governance"}:
        return "mainline_metadata"
    if parts and parts[0] in {"docs", "reporting"}:
        return "reviewed_documentation"
    if parts and parts[0] in {"experiments", "raw_yaml"}:
        return "experiment_input"
    if parts and parts[0] == "analysis_outputs":
        return "generated_evidence"
    if parts and parts[0] == "artifacts":
        if any(part == "source" or part.startswith("sources") for part in parts):
            return "external_source"
        return "generated_evidence"
    if parts and parts[0] == "vendor":
        return "external_source"
    if len(parts) == 1 and name in {
        ".gitattributes",
        ".gitignore",
        "AGENTS.md",
        "pytest.ini",
    }:
        return "mainline_metadata"
    if len(parts) == 1 and name in {
        "README.md",
        "REMEDIATION_REPORT.md",
        "findings.md",
        "progress.md",
        "task_plan.md",
    }:
        return "reviewed_documentation"
    if len(parts) == 1 and name.endswith(".docx"):
        return "reviewed_documentation"
    if name.startswith(".tmp-") or name.startswith(".pytest-tmp-"):
        return "local_generated"
    if name in {".venv", ".venv-otel-runtime", ".pytest_cache"}:
        return "local_state"
    return "uncategorized"


def _git_paths(root: Path) -> tuple[set[str], set[str]]:
    try:
        tracked_raw = subprocess.check_output(
            ["git", "-C", str(root), "ls-files"], text=True, stderr=subprocess.DEVNULL
        )
        status_raw = subprocess.check_output(
            ["git", "-C", str(root), "status", "--porcelain=v1", "-uall"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.CalledProcessError):
        return set(), set()
    tracked = {line.strip().replace("\\", "/") for line in tracked_raw.splitlines() if line.strip()}
    changed: set[str] = set()
    for line in status_raw.splitlines():
        if len(line) >= 4:
            changed.add(line[3:].replace("\\", "/"))
    return tracked, changed


def build_inventory(root: Path) -> dict:
    root = root.resolve()
    tracked, changed = _git_paths(root)
    records: list[dict] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or ".git" in path.parts:
            continue
        relative = _normal(path, root)
        category = classify_path(relative)
        records.append(
            {
                "path": relative,
                "bytes": path.stat().st_size,
                "category": category,
                "tracked": relative in tracked,
                "changed": relative in changed,
            }
        )
    category_counts = Counter(record["category"] for record in records)
    byte_counts: Counter[str] = Counter()
    for record in records:
        byte_counts[record["category"]] += record["bytes"]
    return {
        "schema_version": SCHEMA_VERSION,
        "root": str(root),
        "file_count": len(records),
        "category_counts": dict(sorted(category_counts.items())),
        "category_bytes": dict(sorted(byte_counts.items())),
        "tracked_file_count": sum(1 for record in records if record["tracked"]),
        "changed_file_count": sum(1 for record in records if record["changed"]),
        "records": records,
    }


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    report = build_inventory(args.root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("schema_version", "file_count", "tracked_file_count", "changed_file_count", "category_counts")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
