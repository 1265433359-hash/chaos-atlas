"""Verify restored project source trees and write offline provenance evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

from tools.prepare_project_gates import PROJECTS, ROOT


def sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        return str(path)


def _git(source_root: Path, *args: str) -> str:
    safe = source_root.resolve().as_posix()
    result = subprocess.run(
        ["git", "-c", f"safe.directory={safe}", *args],
        cwd=source_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def read_git_state(source_root: Path) -> tuple[str, str, int]:
    commit = _git(source_root, "rev-parse", "HEAD")
    tree = _git(source_root, "rev-parse", "HEAD^{tree}")
    file_count_text = _git(source_root, "ls-tree", "-r", "--name-only", "HEAD")
    file_count = 0 if not file_count_text else len(file_count_text.splitlines())
    return commit, tree, file_count


def build_source_report(
    *,
    project_id: str,
    source_root: Path,
    expected_commit: str,
    expected_tree: str,
    expected_file_count: int,
    deployment_assets: list[str],
    git_commit: str,
    git_tree: str,
    git_file_count: int,
) -> dict[str, Any]:
    assets_present = {name: (source_root / name).is_file() for name in deployment_assets}
    asset_hashes = {name: sha256(source_root / name) for name in deployment_assets}
    reasons: list[str] = []
    if git_commit != expected_commit:
        reasons.append("commit_mismatch")
    if git_tree != expected_tree:
        reasons.append("tree_mismatch")
    if git_file_count != expected_file_count:
        reasons.append("file_count_mismatch")
    if not all(assets_present.values()):
        reasons.append("missing_deployment_assets")

    return {
        "schema_version": "1.0",
        "project_id": project_id,
        "source_root": _display_path(source_root),
        "expected_commit": expected_commit,
        "actual_commit": git_commit,
        "commit_verified": git_commit == expected_commit,
        "expected_tree_sha": expected_tree,
        "actual_tree_sha": git_tree,
        "tree_sha_verified": git_tree == expected_tree,
        "expected_git_file_count": expected_file_count,
        "actual_git_file_count": git_file_count,
        "file_count_verified": git_file_count == expected_file_count,
        "deployment_assets_present": assets_present,
        "deployment_asset_sha256": asset_hashes,
        "source_restore_status": "complete" if not reasons else "blocked",
        "blocked_reasons": reasons,
        "runtime_apply_allowed": False,
        "runtime_apply_note": "source verification only; runtime remains gated by static profile, dry-run, and namespace approval",
    }


def _manifest_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# {report['project_id']} Source Restoration Manifest",
        "",
        f"- source_root: `{report['source_root']}`",
        f"- source_restore_status: `{report['source_restore_status']}`",
        f"- expected_commit: `{report['expected_commit']}`",
        f"- actual_commit: `{report['actual_commit']}`",
        f"- expected_tree_sha: `{report['expected_tree_sha']}`",
        f"- actual_tree_sha: `{report['actual_tree_sha']}`",
        f"- expected_git_file_count: `{report['expected_git_file_count']}`",
        f"- actual_git_file_count: `{report['actual_git_file_count']}`",
        f"- runtime_apply_allowed: `{str(report['runtime_apply_allowed']).lower()}`",
        "",
        "## Deployment Asset SHA-256",
        "",
    ]
    for name, digest in report["deployment_asset_sha256"].items():
        lines.append(f"- `{name}`: `{digest}`")
    if report["blocked_reasons"]:
        lines.extend(["", "## Blocked Reasons", ""])
        lines.extend(f"- `{reason}`" for reason in report["blocked_reasons"])
    lines.append("")
    return "\n".join(lines)


def write_source_evidence(output_dir: Path, report: dict[str, Any]) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    gate_path = output_dir / "source-restore-gate.json"
    manifest_path = output_dir / "RESTORATION_MANIFEST.md"
    gate_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest_path.write_text(_manifest_markdown(report), encoding="utf-8")
    return [gate_path, manifest_path]


def verify_project(project_id: str, source_root: Path, output_dir: Path) -> dict[str, Any]:
    meta = PROJECTS[project_id]
    commit, tree, file_count = read_git_state(source_root)
    report = build_source_report(
        project_id=project_id,
        source_root=source_root,
        expected_commit=meta["commit"],
        expected_tree=meta["tree"],
        expected_file_count=meta["file_count"],
        deployment_assets=meta["deployment_assets"],
        git_commit=commit,
        git_tree=tree,
        git_file_count=file_count,
    )
    write_source_evidence(output_dir, report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("projects", nargs="+", choices=sorted(PROJECTS))
    parser.add_argument(
        "--sources-parent",
        type=Path,
        default=ROOT / "artifacts/experiments/chaosatlas_10_projects/sources_restored_r2",
    )
    parser.add_argument(
        "--profiles-parent",
        type=Path,
        default=ROOT / "artifacts/experiments/chaosatlas_10_projects/runtime_profiles",
    )
    args = parser.parse_args()

    results = []
    for project_id in args.projects:
        result = verify_project(
            project_id,
            args.sources_parent / project_id,
            args.profiles_parent / f"{project_id}-r2",
        )
        results.append(result)
    print(json.dumps(results, indent=2, sort_keys=True))
    return 0 if all(item["source_restore_status"] == "complete" for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
