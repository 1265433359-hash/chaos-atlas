import json

from chaosatlas.orchestration.batch import enrich_batch_result_from_artifacts


def test_batch_projection_distinguishes_attempted_from_confirmed_injection(tmp_path):
    (tmp_path / "execute.json").write_text(json.dumps({
        "payload": {"phases": [{"faults": [{
            "injection_confirmed": False,
            "injection_confirmation": {"confirmed": False, "attempts": 2},
        }]}]},
    }), encoding="utf-8")

    result = enrich_batch_result_from_artifacts(
        {"status": "environment_blocked"}, tmp_path,
    )

    assert result["injection_confirmed"] is False
    assert result["injection_confirmation"] == [{"confirmed": False, "attempts": 2}]
