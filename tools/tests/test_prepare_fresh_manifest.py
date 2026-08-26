from __future__ import annotations

from pathlib import Path

import yaml

from tools.prepare_fresh_manifest import prepare_namespace_copy


def _source(tmp_path: Path) -> Path:
    source = tmp_path / "source.yaml"
    source.write_text(
        yaml.safe_dump_all(
            [
                {"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": "sock-shop-lab"}},
                {
                    "apiVersion": "apps/v1",
                    "kind": "Deployment",
                    "metadata": {"name": "front-end", "namespace": "sock-shop-lab"},
                    "spec": {"replicas": 1},
                },
                {
                    "apiVersion": "v1",
                    "kind": "Service",
                    "metadata": {"name": "front-end", "namespace": "sock-shop-lab"},
                },
            ],
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return source


def test_prepare_namespace_copy_is_immutable_and_auditable(tmp_path: Path) -> None:
    source = _source(tmp_path)
    original = source.read_bytes()
    output = tmp_path / "fresh"

    result = prepare_namespace_copy(
        source,
        output,
        source_namespace="sock-shop-lab",
        target_namespace="sock-shop-improvement-lab",
    )

    assert result["status"] == "prepared"
    assert result["source_sha256"]
    assert result["manifest_sha256"]
    assert source.read_bytes() == original
    documents = list(yaml.safe_load_all((output / "manifest.yaml").read_text(encoding="utf-8")))
    assert documents[0]["metadata"] == {"name": "sock-shop-improvement-lab"}
    assert all(
        document.get("kind") == "Namespace"
        or document.get("metadata", {}).get("namespace") == "sock-shop-improvement-lab"
        for document in documents
    )


def test_prepare_namespace_copy_rejects_wrong_source_namespace(tmp_path: Path) -> None:
    source = _source(tmp_path)
    output = tmp_path / "fresh"

    result = prepare_namespace_copy(
        source,
        output,
        source_namespace="other-lab",
        target_namespace="sock-shop-improvement-lab",
    )

    assert result["status"] == "blocked"
    assert "source namespace mismatch" in result["reason"]
    assert not output.exists()


def test_prepare_namespace_copy_rejects_nonempty_output(tmp_path: Path) -> None:
    source = _source(tmp_path)
    output = tmp_path / "fresh"
    output.mkdir()
    (output / "existing.txt").write_text("keep", encoding="utf-8")

    result = prepare_namespace_copy(
        source,
        output,
        source_namespace="sock-shop-lab",
        target_namespace="sock-shop-improvement-lab",
    )

    assert result["status"] == "blocked"
    assert "output copy must be fresh" in result["reason"]
    assert (output / "existing.txt").read_text(encoding="utf-8") == "keep"


def test_prepare_namespace_copy_can_remove_cluster_wide_node_ports(tmp_path: Path) -> None:
    source = _source(tmp_path)
    documents = list(yaml.safe_load_all(source.read_text(encoding="utf-8")))
    documents[-1]["spec"] = {
        "type": "NodePort",
        "ports": [{"port": 80, "targetPort": 80, "nodePort": 30011}],
    }
    source.write_text(yaml.safe_dump_all(documents, sort_keys=False), encoding="utf-8")
    output = tmp_path / "fresh"

    result = prepare_namespace_copy(
        source,
        output,
        source_namespace="sock-shop-lab",
        target_namespace="sock-shop-improvement-lab",
        strip_node_ports=True,
    )

    assert result["status"] == "prepared"
    assert result["node_port_rewrites"] == [{"kind": "Service", "name": "front-end"}]
    service = list(yaml.safe_load_all((output / "manifest.yaml").read_text(encoding="utf-8")))[-1]
    assert service["spec"]["type"] == "ClusterIP"
    assert "nodePort" not in service["spec"]["ports"][0]
