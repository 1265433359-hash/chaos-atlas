from __future__ import annotations

import json
from pathlib import Path

from tools.prepare_project_gates import (
    build_project_preparation,
    choose_output_dir,
)


def test_choose_output_dir_never_overwrites_nonempty_directory(tmp_path: Path) -> None:
    existing = tmp_path / "P08-r2"
    existing.mkdir()
    (existing / "old.json").write_text("old\n", encoding="utf-8")

    selected = choose_output_dir(tmp_path, "P08-r2")

    assert selected.name == "P08-r3"
    assert (existing / "old.json").read_text(encoding="utf-8") == "old\n"


def test_p03_preparation_remains_blocked_after_source_restore_until_runtime_gates_pass(tmp_path: Path) -> None:
    result = build_project_preparation("P03", tmp_path / "P03-r2")

    assert result["gate_status"] == "blocked"
    assert result["runtime_apply_allowed"] is False
    assert "source_restore_incomplete" not in result["blocked_reasons"]
    assert "deterministic_oracle_unverified" in result["blocked_reasons"]
    assert "immutable_image_provenance_missing" in result["blocked_reasons"]
    assert "resource_limits_unverified" in result["blocked_reasons"]
    assert result["oracle_contract"]["status"] == "contract_only"


def test_p03_preparation_marks_missing_required_file_as_source_incomplete(tmp_path: Path) -> None:
    source = tmp_path / "sources_restored_r2" / "P03"
    for relative in (
        "Dockerfile",
        ".worktree-container/docker-compose.yml",
        ".devcontainer/docker-compose.yml",
        "socket.yml",
        ".devcontainer/common.env",
        ".devcontainer/backend.env",
        "pyproject.toml",
        "uv.lock",
    ):
        path = source / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("placeholder\n", encoding="utf-8")
    # manage.py is intentionally absent: source completeness must include
    # required application files, not only deployment assets.
    (source / ".worktree-container/docker-compose.yml").write_text(
        "services:\n  saleor:\n    image: saleor@sha256:" + "a" * 64 + "\n",
        encoding="utf-8",
    )

    result = build_project_preparation("P03", tmp_path / "P03-r2", source_root=source)

    assert result["source"]["source_status"] == "incomplete"
    assert "source_restore_incomplete" in result["blocked_reasons"]


def test_p08_preparation_keeps_runtime_blocked_without_immutable_image_and_oracle(
    tmp_path: Path,
) -> None:
    source = tmp_path / "sources_restored_r2" / "P08"
    (source / "deploy" / "docker").mkdir(parents=True)
    (source / "deploy" / "docker" / "docker-compose.yml").write_text(
        "services:\n"
        "  appsmith:\n"
        "    image: index.docker.io/appsmith/appsmith-ce:release\n",
        encoding="utf-8",
    )

    result = build_project_preparation(
        "P08",
        tmp_path / "P08-r3",
        source_root=source,
    )

    assert result["gate_status"] == "blocked"
    assert result["runtime_apply_allowed"] is False
    assert "immutable_image_provenance_missing" in result["blocked_reasons"]
    assert "deterministic_oracle_unverified" in result["blocked_reasons"]
    assert result["static_gates"]["namespace_local"]["status"] == "pass"
