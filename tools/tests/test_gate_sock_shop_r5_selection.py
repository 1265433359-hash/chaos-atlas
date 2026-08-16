import hashlib
import json

import yaml

from tools.gate_sock_shop_r5_selection import gate_selection


def test_selection_gate_verifies_hash_dry_run_and_applicability(tmp_path, monkeypatch):
    mutation = tmp_path / "mutation.yaml"
    mutation.write_text(
        yaml.safe_dump(
            {
                "apiVersion": "chaos-mesh.org/v1alpha1",
                "kind": "PodChaos",
                "metadata": {"name": "selected", "namespace": "chaosatlas-sock-shop"},
                "spec": {
                    "action": "pod-kill",
                    "mode": "one",
                    "selector": {
                        "namespaces": ["chaosatlas-sock-shop"],
                        "labelSelectors": {"name": "front-end"},
                    },
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    digest = hashlib.sha256(mutation.read_bytes()).hexdigest()
    manifest = tmp_path / "selection.json"
    manifest.write_text(
        json.dumps(
            {
                "groups": {
                    "overlap_high_confidence": [
                        {"mutation_path": str(mutation), "mutation_sha256": digest}
                    ],
                    "ablation_only_random": [],
                }
            }
        ),
        encoding="utf-8",
    )

    class Completed:
        returncode = 0
        stdout = "podchaos.chaos-mesh.org/selected configured (server dry run)"
        stderr = ""

    monkeypatch.setattr("tools.gate_sock_shop_r5_selection.subprocess.run", lambda *_a, **_k: Completed())
    monkeypatch.setattr(
        "tools.gate_sock_shop_r5_selection.check_mutation",
        lambda _path: {"decision": "ready_for_injection", "errors": []},
    )

    report = gate_selection(manifest, tmp_path / "gate.json")

    assert report["status"] == "passed"
    assert report["summary"] == {"selected": 1, "dry_run_passed": 1, "ready_for_injection": 1, "blocked": 0}
    assert report["human_review"] == "pending"


def test_selection_gate_blocks_hash_mismatch_before_kubectl(tmp_path, monkeypatch):
    mutation = tmp_path / "mutation.yaml"
    mutation.write_text("kind: PodChaos\n", encoding="utf-8")
    manifest = tmp_path / "selection.json"
    manifest.write_text(
        json.dumps(
            {
                "groups": {
                    "overlap_high_confidence": [],
                    "ablation_only_random": [
                        {"mutation_path": str(mutation), "mutation_sha256": "0" * 64}
                    ],
                }
            }
        ),
        encoding="utf-8",
    )
    calls = []
    monkeypatch.setattr("tools.gate_sock_shop_r5_selection.subprocess.run", lambda *_a, **_k: calls.append(True))

    report = gate_selection(manifest, tmp_path / "gate.json")

    assert report["status"] == "blocked"
    assert report["summary"]["blocked"] == 1
    assert not calls
