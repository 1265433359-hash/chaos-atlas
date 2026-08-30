import json

from tools.kubernetes_lifecycle_executor import KubernetesLifecycleExecutor
from scripts.run_network_dns_http_matrix import build_summary, run_matrix


def _manifest():
    return {
        "apiVersion": "chaos-mesh.org/v1alpha1",
        "kind": "DNSChaos",
        "metadata": {"name": "atlas-dns-test", "namespace": "lab"},
        "spec": {
            "action": "error",
            "mode": "one",
            "patterns": ["catalogue"],
            "duration": "5s",
            "selector": {"namespaces": ["lab"], "labelSelectors": {"app": "web"}},
        },
    }


def _executor(tmp_path, cleanup_ok):
    return KubernetesLifecycleExecutor(
        root=tmp_path,
        namespace="lab",
        allowed_namespaces={"lab"},
        allow_live=True,
        oracle={"service": "web", "remote_port": 80, "entrypoint": "/"},
        hooks={
            "gate": lambda _manifest, _path: {
                "decision": "ready_for_injection",
                "checks": {"target_pods": []},
            },
            "probe": lambda _phase, _manifest: {
                "status": "pass",
                "samples": [{"status_code": 200}],
            },
            "apply": lambda _manifest: {"return_code": 0, "stdout": "", "stderr": ""},
            "wait_lifecycle": lambda _kind, _namespace, _name, _predicate: (True, {}, []),
            "delete": lambda _kind, _namespace, _name: {"absent_confirmed": cleanup_ok},
        },
    )


def test_live_executor_returns_valid_attestation_without_real_cluster(tmp_path):
    result = _executor(tmp_path, cleanup_ok=True).run(_manifest(), action_id="dns-valid")
    assert result["injection"]["confirmed"] is True
    assert result["recovery"]["confirmed"] is True
    assert result["cleanup"]["confirmed"] is True
    assert result["attestation"]["valid"] is True
    assert result["promotion_allowed"] is True


def test_cleanup_failure_cannot_be_promoted(tmp_path):
    result = _executor(tmp_path, cleanup_ok=False).run(_manifest(), action_id="dns-dirty")
    assert result["attestation"]["valid"] is False
    assert result["promotion_allowed"] is False


def test_matrix_summary_counts_only_cleanup_verified_results():
    summary = build_summary([
        {"fault_family": "network_delay", "status": "live_completed", "cleanup": "verified"},
        {"fault_family": "http_abort", "status": "environment_blocked", "cleanup": "blocked"},
    ])
    assert summary["executed"] == 1
    assert summary["cleanup_verified"] == 1
    assert summary["policy_feedback_eligible"] == 1


def test_batch_compatibility_exports_live_plan_builder():
    from tools.chaosatlas_batch import build_live_batch_plan

    assert callable(build_live_batch_plan)


def test_live_matrix_uses_profile_project_id(monkeypatch, tmp_path):
    profile = tmp_path / "profile.json"
    profile.write_text(json.dumps({"project_id": "demo-project"}), encoding="utf-8")

    def fake_run_live_batch(**_kwargs):
        return {"status": "completed", "results": [{"status": "live_completed", "cleanup_status": "verified"}]}

    monkeypatch.setattr("tools._legacy_chaosatlas_batch.run_live_batch", fake_run_live_batch)
    summary = run_matrix([profile], output=tmp_path / "out", mode="live", approve_live=True)

    assert summary["results"][0]["project_id"] == "demo-project"
