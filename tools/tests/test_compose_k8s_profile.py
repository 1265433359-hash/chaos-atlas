from __future__ import annotations

import json
from pathlib import Path

import yaml

from tools.generate_compose_k8s_profile import generate


def test_generate_compose_profile_is_namespace_local_and_static() -> None:
    compose = {
        "services": {
            "api": {
                "image": "example/api@sha256:" + "a" * 64,
                "ports": [{"target": 8080, "published": "18080"}],
                "healthcheck": {"test": ["CMD", "curl", "-f", "http://localhost:8080/health"]},
                "deploy": {"resources": {"limits": {"memory": "256M"}}},
            },
            "worker": {
                "image": "example/worker@sha256:" + "b" * 64,
                "depends_on": {"api": {"condition": "service_healthy"}},
            },
        }
    }
    docs = generate(compose, "chaosatlas-test", {})
    assert len(docs) == 4
    assert docs[0]["kind"] == "Namespace"
    assert all(doc["metadata"].get("namespace") == "chaosatlas-test" for doc in docs[1:])
    api = next(doc for doc in docs if doc.get("kind") == "Deployment" and doc["metadata"]["name"] == "api")
    container = api["spec"]["template"]["spec"]["containers"][0]
    assert container["livenessProbe"]["exec"]["command"] == ["curl", "-f", "http://localhost:8080/health"]
    assert api["metadata"]["annotations"]["chaosatlas.io/static-only"] == "true"
    assert "chaosatlas.io/depends-on" in next(doc for doc in docs if doc.get("kind") == "Deployment" and doc["metadata"]["name"] == "worker")["metadata"]["annotations"]
    rendered = "---\n".join(yaml.safe_dump(doc, sort_keys=False) for doc in docs)
    assert "&id" not in rendered and "*id" not in rendered
    assert json.loads(json.dumps(docs)) == docs
