from pathlib import Path

from tools._legacy_chaosatlas import run_closed_loop


class _BlockedLiveAdapter:
    def inventory(self):
        return {"status": "environment_blocked", "errors": ["api server unavailable"]}


def test_live_inventory_block_is_reported_as_environment_blocked(tmp_path: Path):
    result = run_closed_loop(
        profile_path=Path("projects/nginx-kubernetes-ingress/profile.json"),
        output_root=tmp_path / "run",
        mode="live",
        approve_live=True,
        live_adapter=_BlockedLiveAdapter(),
    )

    assert result["status"] == "environment_blocked"
    assert "api server unavailable" in result["error"]
