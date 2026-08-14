from pathlib import Path

import pytest
import yaml

from tools.prepare_sock_shop_two_arm import build_sock_shop_manifest


SOURCE_COMMIT = "9dff06fae4981921caec6a62393a6ebfce4b3e3f"


def test_sock_shop_manifest_is_namespace_local_immutable_and_freezes_authenticated_order_oracle(tmp_path: Path) -> None:
    source = tmp_path / "complete-demo.yaml"
    source.write_text(
        """---
apiVersion: v1
kind: Namespace
metadata:
  name: sock-shop
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: front-end
  namespace: sock-shop
spec:
  replicas: 1
  selector:
    matchLabels: {name: front-end}
  template:
    metadata:
      labels: {name: front-end}
    spec:
      containers:
      - name: front-end
        image: example/front-end:v1
---
apiVersion: v1
kind: Service
metadata:
  name: front-end
  namespace: sock-shop
spec:
  type: NodePort
  ports:
  - port: 80
    targetPort: 8079
    nodePort: 30001
  selector: {name: front-end}
""",
        encoding="utf-8",
    )
    manifest = build_sock_shop_manifest(
        source,
        source_commit=SOURCE_COMMIT,
        image_overrides={"example/front-end:v1": "example/front-end@sha256:" + "a" * 64},
    )
    assert manifest["static_gate"]["status"] == "passed"
    assert manifest["namespace"] == "chaosatlas-sock-shop"
    assert manifest["image_provenance"]["all_immutable"] is True
    assert [step["path"] for step in manifest["oracle_contract"]["steps"]] == ["/", "/catalogue", "/login", "/orders"]
    assert manifest["oracle_contract"]["steps"][-1]["success_status"] == 201
    docs = list(yaml.safe_load_all(manifest["deployable_manifest"]))
    assert all(doc.get("metadata", {}).get("namespace") == "chaosatlas-sock-shop" for doc in docs if doc.get("kind") != "Namespace")
    service = next(doc for doc in docs if doc.get("kind") == "Service")
    assert service["spec"].get("type") == "ClusterIP"
    assert "nodePort" not in service["spec"]["ports"][0]


def test_sock_shop_manifest_rejects_unversioned_mongo_resolved_to_an_unverified_digest(tmp_path: Path) -> None:
    source = tmp_path / "complete-demo.yaml"
    source.write_text(
        """---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-db
  namespace: sock-shop
spec:
  selector:
    matchLabels: {name: orders-db}
  template:
    metadata:
      labels: {name: orders-db}
    spec:
      containers:
      - name: orders-db
        image: mongo
""",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="verified Mongo compatibility image"):
        build_sock_shop_manifest(
            source,
            source_commit=SOURCE_COMMIT,
            image_overrides={"mongo": "mongo@sha256:" + "f" * 64},
        )
