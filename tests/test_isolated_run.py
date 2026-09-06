import json
from pathlib import Path

import pytest

from chaosatlas.orchestration.engine import RunEngine, RunRequest
from chaosatlas.orchestration.isolated_run import resolve_isolation_profile, run_isolated_live


def _profile(tmp_path: Path, *, blueprint_ref: str = "blueprint.json") -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "blueprint.json").write_text(
        json.dumps({"resources": [{"apiVersion": "apps/v1", "kind": "Deployment", "metadata": {"name": "web"}, "spec": {}}]}),
        encoding="utf-8",
    )
    profile = {
        "schema_version": "chaosatlas-project-profile-v1",
        "project_id": "demo",
        "project_commit": "a" * 64,
        "namespace_policy": {"allowed_namespaces": ["source"], "isolation_required": True},
        "isolation": {
            "synthetic_data_only": True,
            "l2": {"mode": "ephemeral-target", "blueprint_ref": blueprint_ref},
            "fault_routes": {"image_pull_failure": {"level": "L2", "backend": "kubernetes_api"}},
        },
        "business_oracles": [{"kind": "http", "service": "web", "remote_port": 8080, "entrypoint": "/health", "expected_status": 200}],
        "fault_defaults": {"image_pull_failure": {"image": "chaosatlas.invalid/not-found:test"}},
    }
    path = tmp_path / "profile.json"
    path.write_text(json.dumps(profile), encoding="utf-8")
    return path


class FakeManager:
    def __init__(self, *, cleanup_state: str = "released") -> None:
        self.cleanup_state = cleanup_state
        self.released: list[str] = []

    def prepare(self, plan, *, ttl_minutes):
        assert plan["status"] == "ready"
        assert ttl_minutes == 30
        return {
            "lease_id": "lease-1234567890abcdef",
            "state": "ready",
            "target_name": "ca-l2-demo-1234567890",
            "provider": "kubernetes-l2",
            "runtime_locator": {"kube_context": "test-context"},
        }

    def release(self, lease_id):
        self.released.append(lease_id)
        return {
            "lease_id": lease_id,
            "state": self.cleanup_state,
            "target_name": "ca-l2-demo-1234567890",
        }


def test_resolve_isolation_profile_loads_bounded_blueprint(tmp_path):
    profile, route = resolve_isolation_profile(_profile(tmp_path), "image_pull_failure")

    assert profile["isolation"]["l2"]["blueprint"]["resources"][0]["metadata"]["name"] == "web"
    assert route["level"] == "L2"
    assert len(route["blueprint_sha256"]) == 64


def test_resolve_isolation_profile_rejects_path_escape(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    outside = tmp_path / "outside.json"
    outside.write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="escapes"):
        resolve_isolation_profile(_profile(project, blueprint_ref="../outside.json"), "image_pull_failure")


def test_isolated_live_binds_ready_lease_and_always_releases(tmp_path):
    manager = FakeManager()
    observed = {}

    def execute(profile_path, output_root, context):
        runtime = json.loads(profile_path.read_text(encoding="utf-8"))
        observed.update({"profile": runtime, "output": output_root, "context": context})
        return {"status": "completed", "executed_count": 1, "completed_count": 1}

    result = run_isolated_live(
        profile_path=_profile(tmp_path / "project"),
        output_root=tmp_path / "run",
        fault_id="image_pull_failure",
        ttl_minutes=30,
        execute=execute,
        manager=manager,
    )

    assert result["status"] == "completed"
    assert result["isolation"]["status"] == "verified"
    assert result["isolation"]["cleanup_state"] == "released"
    assert manager.released == ["lease-1234567890abcdef"]
    assert observed["context"] == "test-context"
    assert observed["profile"]["namespace_policy"]["allowed_namespaces"] == ["ca-l2-demo-1234567890"]
    assert observed["profile"]["runtime_contract"]["supported_fault_families"] == ["image_pull_failure"]
    assert "blueprint" not in observed["profile"]["isolation"]["l2"]


def test_isolated_live_marks_cleanup_failure_partial(tmp_path):
    manager = FakeManager(cleanup_state="cleanup_failed")
    result = run_isolated_live(
        profile_path=_profile(tmp_path / "project"),
        output_root=tmp_path / "run",
        fault_id="image_pull_failure",
        ttl_minutes=30,
        execute=lambda *_: {"status": "completed", "executed_count": 1},
        manager=manager,
    )

    assert result["status"] == "partial"
    assert result["isolation"]["cleanup_state"] == "cleanup_failed"


def test_run_request_requires_explicit_isolation_approval():
    request = RunRequest(
        profile_path=Path("profile.json"),
        output_root=Path("run"),
        mode="live",
        approve_live=True,
        isolation_fault="image_pull_failure",
    )
    assert request.approve_isolation is False

    with pytest.raises(ValueError, match="exactly one candidate"):
        RunRequest(
            profile_path=Path("profile.json"),
            output_root=Path("run"),
            mode="live",
            isolation_fault="image_pull_failure",
            approve_isolation=True,
            all_candidates=True,
        )


def test_run_engine_does_not_prepare_isolation_without_live_approval(tmp_path):
    result = RunEngine().run(RunRequest(
        profile_path=_profile(tmp_path / "project"),
        output_root=tmp_path / "run",
        mode="live",
        isolation_fault="image_pull_failure",
        approve_isolation=True,
    ))

    assert result == {
        "status": "environment_blocked",
        "reason": "approve_live_required",
        "injection_performed": False,
    }
    assert not (tmp_path / "run").exists()
