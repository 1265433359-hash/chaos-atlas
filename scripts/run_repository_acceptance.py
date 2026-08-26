from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def acceptance_status(checks: list[dict]) -> str:
    if not checks:
        return "failed"
    passed = sum(1 for check in checks if check.get("ok"))
    if passed == len(checks):
        return "success"
    if passed:
        return "partial"
    return "failed"


def resolve_product_root(root: str | Path, product_root: str | Path | None = None) -> Path:
    root_path = Path(root).resolve()
    if product_root:
        return Path(product_root).resolve()
    return root_path


def _run(name: str, command: list[str], cwd: Path) -> dict:
    completed = subprocess.run(command, cwd=cwd, text=True, capture_output=True)
    return {
        "name": name,
        "ok": completed.returncode == 0,
        "returncode": completed.returncode,
        "stdout": completed.stdout[-4000:],
        "stderr": completed.stderr[-4000:],
    }


def run_acceptance(
    root: str | Path,
    evidence_root: str | Path,
    report: str | Path,
    product_root: str | Path | None = None,
) -> dict:
    root_path = Path(root).resolve()
    product_path = resolve_product_root(root_path, product_root)
    checks = [
        _run("compileall", [sys.executable, "-m", "compileall", "-q", "src", "cli", "scripts", "tests"], root_path),
        _run(
            "architecture-contracts",
            [sys.executable, "-m", "pytest", "tests/test_repository_architecture.py", "-q", "-p", "no:cacheprovider", "--basetemp", ".tmp-acceptance"],
            root_path,
        ),
        _run(
            "sock-shop-dry-run",
            [sys.executable, "-m", "chaosatlas", "run", "--profile", "projects/sock-shop/profile.json", "--mode", "dry-run", "--evidence-root", str(evidence_root)],
            root_path,
        ),
        _run(
            "online-boutique-dry-run",
            [sys.executable, "-m", "chaosatlas", "run", "--profile", "projects/online-boutique/profile.json", "--mode", "dry-run", "--evidence-root", str(evidence_root)],
            root_path,
        ),
        _run(
            "product-boundary",
            [sys.executable, "scripts/verify_product_boundary.py", "--root", str(product_path)],
            root_path,
        ),
    ]
    manifest = root_path / ".migration" / "evidence-migration-v2.json"
    if manifest.exists():
        checks.append(
            _run(
                "evidence-hashes",
                [
                    sys.executable,
                    "scripts/verify_evidence_archive.py",
                    "--manifest",
                    str(manifest),
                    "--evidence-root",
                    str(evidence_root),
                ],
                root_path,
            )
        )
    result = {
        "schema_version": 1,
        "status": acceptance_status(checks),
        "checks": checks,
    }
    output = Path(report)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the ChaosAtlas repository acceptance suite.")
    parser.add_argument("--root", default=".")
    parser.add_argument("--evidence-root", default="ChaosAtlas-evidence-v2")
    parser.add_argument("--product-root")
    parser.add_argument("--report", required=True)
    args = parser.parse_args(argv)
    result = run_acceptance(args.root, args.evidence_root, args.report, args.product_root)
    print(result["status"])
    return 0 if result["status"] == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
