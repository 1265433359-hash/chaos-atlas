from __future__ import annotations

import json

from tools.run_native_full_discovery import build_messages


def test_native_prompt_exposes_static_candidate_space_and_forbids_verdicts():
    bundle = {
        "project_id": "demo",
        "seed": 1001,
        "method_id": "ChaosAtlas-native-full",
        "common_input": {
            "topology": {"nodes": [], "edges": []},
            "candidate_space": [{"candidate_id": "deployment:api", "target_kind": "deployment", "status": "eligible"}],
            "coverage_denominator": {"candidate_count": 1, "evidence_status": "static_only"},
        },
        "knowledge_view": {"projection_used": False, "cards": []},
    }
    system, user = build_messages(bundle)
    assert "runtime verdict" in system
    payload = json.loads(user)
    assert payload["common_input"]["candidate_space"][0]["target_kind"] == "deployment"
    assert payload["common_input"]["coverage_denominator"]["evidence_status"] == "static_only"

