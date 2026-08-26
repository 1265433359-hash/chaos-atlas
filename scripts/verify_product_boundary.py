from __future__ import annotations

import argparse
from pathlib import Path

FORBIDDEN_PREFIXES = ("artifacts/", "raw_yaml/", ".venv/", ".tmp-", ".pytest-tmp-")
FORBIDDEN_NAMES = {"kubeconfig", "credentials.json", "credentials.yaml", "credentials.yml"}
FORBIDDEN_SUFFIXES = {".pem", ".key", ".p12", ".pfx", ".jks"}
MAX_PRODUCT_FILE_SIZE = 25 * 1024 * 1024


def find_violations(root: str | Path) -> list[str]:
    root_path = Path(root).resolve()
    violations: list[str] = []
    for path in root_path.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(root_path).as_posix()
        if relative.startswith((".git/", ".worktrees/", ".migration/", "ChaosAtlas-evidence/")):
            continue
        name = path.name.lower()
        if any(relative.startswith(prefix) for prefix in FORBIDDEN_PREFIXES):
            violations.append(f"forbidden path: {relative}")
        if name in FORBIDDEN_NAMES or path.suffix.lower() in FORBIDDEN_SUFFIXES or "kubeconfig" in name:
            violations.append(f"sensitive path: {relative}")
        if path.stat().st_size > MAX_PRODUCT_FILE_SIZE and not relative.startswith(("docs/",)):
            violations.append(f"oversized file: {relative}")
    return violations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check product repository boundaries.")
    parser.add_argument("--root", default=".")
    args = parser.parse_args(argv)
    violations = find_violations(args.root)
    for violation in violations:
        print(violation)
    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
