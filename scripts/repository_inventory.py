from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Iterable

IGNORED_DIR_NAMES = {
    ".git",
    ".venv",
    ".venv-otel-runtime",
    ".pytest_cache",
    ".email-notify-outbox",
    ".planning",
    ".runs",
    ".secrets",
    ".pytest-cache-disabled",
    "__pycache__",
    ".worktrees",
    ".migration",
    "ChaosAtlas-evidence",
    "ChaosAtlas-evidence-v2",
    "environment-reports",
    "node_modules",
    "runtime",
}

SENSITIVE_NAMES = {
    "kubeconfig",
    "config",
    "credentials.json",
    "credentials.yaml",
    "credentials.yml",
}
SENSITIVE_SUFFIXES = {".pem", ".key", ".p12", ".pfx", ".jks"}


def _sha256(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    resolved = str(path.resolve())
    if os.name == "nt" and not resolved.startswith("\\\\?\\"):
        resolved = "\\\\?\\" + resolved
    with open(resolved, "rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def _category(relative: str) -> str:
    first = relative.split("/", 1)[0].lower()
    if first in {"src", "cli"}:
        return "product_code"
    if first in {"tools"}:
        return "legacy_tooling"
    if first in {"tests", "qa"}:
        return "tests"
    if first in {"docs", "governance"}:
        return "documentation"
    if first in {"projects", "examples"}:
        return "project_input"
    if first in {"artifacts", "raw_yaml", "analysis_outputs", "reporting"}:
        return "evidence"
    if first in {".tmp", ".pytest-tmp"} or first.startswith(".tmp-"):
        return "runtime_state"
    if first in {"benchmark", "upstream", "external-sources"}:
        return "external_source"
    if relative.endswith((".yaml", ".yml")) and ("raw_yaml/" in relative or relative.startswith("raw_yaml/")):
        return "raw_input"
    return "unknown"


def _is_sensitive(path: Path) -> bool:
    name = path.name.lower()
    return name in SENSITIVE_NAMES or path.suffix.lower() in SENSITIVE_SUFFIXES or "kubeconfig" in name


def _iter_files(root: Path) -> Iterable[Path]:
    for current, dirs, files in os.walk(root):
        dirs[:] = sorted(
            name
            for name in dirs
            if name not in IGNORED_DIR_NAMES
            and not name.startswith(".pytest-tmp-")
            and not name.startswith(".tmp-")
        )
        for name in sorted(files):
            path = Path(current) / name
            if path.is_file():
                yield path


def build_inventory(root: str | Path, output: str | Path | None = None) -> dict:
    root_path = Path(root).resolve()
    files = []
    counts: dict[str, int] = {}
    for path in _iter_files(root_path):
        relative = path.relative_to(root_path).as_posix()
        category = _category(relative)
        entry = {
            "path": relative,
            "category": category,
            "size": path.stat().st_size,
            "sha256": _sha256(path),
            "sensitive": _is_sensitive(path),
        }
        files.append(entry)
        counts[category] = counts.get(category, 0) + 1
    inventory = {
        "schema_version": 1,
        "root": str(root_path),
        "files": files,
        "summary": {"files": len(files), "by_category": counts},
    }
    if output is not None:
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(inventory, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return inventory


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a deterministic ChaosAtlas repository inventory.")
    parser.add_argument("--root", default=".")
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    build_inventory(args.root, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
