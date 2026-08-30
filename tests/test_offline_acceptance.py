from pathlib import Path

import pytest

from tools.chaosatlas_orchestrator import run_closed_loop


ROOT = Path(__file__).resolve().parents[1]
PROFILE_PATHS = {
    "sock-shop": ROOT / "projects" / "sock-shop" / "profile.json",
    "online-boutique": ROOT / "projects" / "online-boutique" / "profile.json",
    "nginx-kubernetes-ingress": ROOT / "projects" / "nginx-kubernetes-ingress" / "profile.json",
    "p02": ROOT / "tests" / "fixtures" / "chaosatlas_offline" / "p02" / "project_profile.json",
}


@pytest.mark.parametrize("project", sorted(PROFILE_PATHS))
def test_fixture_dry_run_is_ready(tmp_path, project):
    result = run_closed_loop(
        profile_path=PROFILE_PATHS[project],
        output_root=tmp_path / project,
        mode="dry-run",
        seed=1001,
    )

    assert result["status"] == "dry_run_ready"
    assert result["runtime_claims"] == []
    assert result["candidate_count"] > 0
