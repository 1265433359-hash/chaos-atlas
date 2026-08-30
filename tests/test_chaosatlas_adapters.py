import json
from pathlib import Path

from tools.chaosatlas_adapters import FakeExecutor, OfflineProjectAdapter
from tools._legacy_chaosatlas import _find_candidate


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "chaosatlas_offline"


def _adapter(project: str) -> OfflineProjectAdapter:
    return OfflineProjectAdapter(
        FIXTURES / project / "project_facts.json",
        workspace_root=ROOT,
    )


def _profile(project: str) -> tuple[Path, dict]:
    path = FIXTURES / project / "project_profile.json"
    return path, json.loads(path.read_text(encoding="utf-8"))


def test_inventory_and_detection_are_static_only():
    adapter = _adapter("sock-shop")
    profile_path, profile = _profile("sock-shop")

    assert adapter.onboard(profile_path)["status"] == "ready_for_static_analysis"
    inventory = adapter.inventory(profile)
    detection = adapter.detect_server_deployment(inventory)

    assert inventory["services"]
    assert detection["status"] == "verified"
    assert detection["candidates"]
    assert all("runtime_verdict" not in item for item in detection["candidates"])


def test_p02_identity_comparison_is_case_normalized(tmp_path):
    adapter = _adapter("p02")
    profile_path, profile = _profile("p02")
    profile["project_id"] = "P02"
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(json.dumps(profile), encoding="utf-8")

    result = adapter.onboard(profile_path)

    assert result["status"] == "ready_for_static_analysis"


def test_onboard_accepts_windows_utf8_bom_profile(tmp_path):
    source_path, profile = _profile("sock-shop")
    profile_path = tmp_path / "profile.json"
    profile_path.write_bytes(b"\xef\xbb\xbf" + json.dumps(profile).encode("utf-8"))

    result = _adapter("sock-shop").onboard(profile_path)

    assert result["status"] == "ready_for_static_analysis"


def test_fake_executor_is_synthetic_and_cleanup_confirmed():
    result = FakeExecutor().run({"candidate_id": "server:demo:pod_kill"})

    assert result["claim_scope"] == "synthetic"
    assert result["runtime_verdict"] == "not_run"
    assert result["lifecycle"] == ["preflight", "baseline", "inject", "observe", "recover", "cleanup"]
    assert result["cleanup_confirmed"] is True


def test_runtime_candidate_accepts_stable_project_target_id():
    candidates = [
        {
            "candidate_id": "server:deployment:46f154f24e1db2da85adebbf:pod_kill",
            "target": "nginx-ingress",
            "fault_family": "pod_kill",
        }
    ]

    selected = _find_candidate(
        candidates,
        "server:deployment:nginx-kubernetes-ingress:nginx-ingress:pod_kill",
        project_id="nginx-kubernetes-ingress",
    )

    assert selected == candidates[0]
