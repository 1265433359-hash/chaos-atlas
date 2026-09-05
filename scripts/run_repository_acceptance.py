from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    from scripts.build_product_snapshot import build_snapshot
except ModuleNotFoundError:  # direct ``python scripts/...`` execution
    from build_product_snapshot import build_snapshot


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


def _run(name: str, command: list[str], cwd: Path, env: dict[str, str] | None = None) -> dict:
    completed = subprocess.run(command, cwd=cwd, text=True, capture_output=True, env=env)
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
    evidence_path = Path(evidence_root).resolve()
    temporary_root = tempfile.TemporaryDirectory(prefix="chaosatlas-acceptance-")
    temporary_path = Path(temporary_root.name)
    if product_root:
        product_path = resolve_product_root(root_path, product_root)
    else:
        product_path = build_snapshot(root_path, temporary_path / "product")
    subprocess_env = os.environ.copy()
    subprocess_env["PYTHONPYCACHEPREFIX"] = str(temporary_path / "pycache")
    checks = [
        _run("workspace-hygiene", [sys.executable, "scripts/check_workspace_hygiene.py", "--root", str(root_path)], root_path, subprocess_env),
        _run("compileall", [sys.executable, "-m", "compileall", "-q", "src", "cli", "scripts", "tests"], root_path, subprocess_env),
        _run(
            "architecture-contracts",
            [sys.executable, "-m", "pytest", "tests/test_repository_architecture.py", "-q", "-p", "no:cacheprovider", "--basetemp", str(temporary_path / "pytest")],
            root_path,
            subprocess_env,
        ),
        _run(
            "sock-shop-dry-run",
            [sys.executable, "-m", "chaosatlas", "run", "--profile", "projects/sock-shop/profile.json", "--mode", "dry-run", "--evidence-root", str(evidence_path / "sock-shop")],
            root_path,
            subprocess_env,
        ),
        _run(
            "online-boutique-dry-run",
            [sys.executable, "-m", "chaosatlas", "run", "--profile", "projects/online-boutique/profile.json", "--mode", "dry-run", "--evidence-root", str(evidence_path / "online-boutique")],
            root_path,
            subprocess_env,
        ),
        _run(
            "product-boundary",
            [sys.executable, "scripts/verify_product_boundary.py", "--root", str(product_path)],
            root_path,
            subprocess_env,
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
                    str(evidence_path),
                ],
                    root_path,
                    subprocess_env,
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
    temporary_root.cleanup()
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the ChaosAtlas repository acceptance suite.")
    parser.add_argument("--root", default=".")
    parser.add_argument("--evidence-root", help="external acceptance evidence directory")
    parser.add_argument("--product-root")
    parser.add_argument("--report", required=True)
    args = parser.parse_args(argv)
    if args.evidence_root:
        evidence_root = args.evidence_root
    else:
        try:
            from chaosatlas.workspace import default_run_output
        except ModuleNotFoundError:
            sys.path.insert(0, str(Path(args.root).resolve() / "src"))
            from chaosatlas.workspace import default_run_output
        evidence_root = default_run_output("repository-acceptance")
    result = run_acceptance(args.root, evidence_root, args.report, args.product_root)
    print(result["status"])
    return 0 if result["status"] == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
