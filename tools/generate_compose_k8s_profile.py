"""Generate a conservative namespace-local Kubernetes profile from Compose JSON.

The output is static and dry-run-only. It does not pull images, call kubectl,
or modify the source repository. Image provenance and runtime health remain
separate gates.
"""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]


def quantity(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, int):
        return str(value)
    return str(value)


def probe(test: list[Any] | None) -> dict[str, Any] | None:
    if not test or len(test) < 2:
        return None
    command = [str(item) for item in test[1:]]
    if test[0] == "CMD-SHELL":
        command = ["/bin/sh", "-c", " ".join(command)]
    return {"exec": {"command": command}}


def generate(compose: dict[str, Any], namespace: str, image_overrides: dict[str, str]) -> list[dict[str, Any]]:
    resources: list[dict[str, Any]] = [
        {
            "apiVersion": "v1",
            "kind": "Namespace",
            "metadata": {"name": namespace, "labels": {"chaosatlas.study": "chaosatlas-10-projects"}},
        }
    ]
    services = compose.get("services") or {}
    for service_name, service in sorted(services.items()):
        image = image_overrides.get(service_name) or service.get("image")
        if not image:
            raise ValueError(f"service {service_name} has no image; provide an explicit override")
        labels = {
            "app.kubernetes.io/part-of": "chaosatlas-p02",
            "app.kubernetes.io/name": service_name,
            "chaosatlas.io/source": "compose-static-normalization",
        }
        container: dict[str, Any] = {"name": service_name, "image": image, "imagePullPolicy": "IfNotPresent"}
        ports = service.get("ports") or []
        container_ports: list[dict[str, Any]] = []
        service_ports: list[dict[str, Any]] = []
        for port in ports:
            target = port.get("target")
            published = port.get("published") or target
            if target is None:
                continue
            port_name = f"p{target}"[:15]
            container_ports.append({"name": port_name, "containerPort": int(target)})
            service_ports.append({"name": port_name, "port": int(published), "targetPort": port_name})
        if container_ports:
            container["ports"] = container_ports
        health = service.get("healthcheck") or {}
        if health.get("test"):
            container["livenessProbe"] = probe(health["test"])
            if health.get("interval"):
                container["livenessProbe"]["periodSeconds"] = max(1, int(str(health["interval"]).rstrip("s")))
            if health.get("timeout"):
                container["livenessProbe"]["timeoutSeconds"] = max(1, int(str(health["timeout"]).rstrip("s")))
            if health.get("retries"):
                container["livenessProbe"]["failureThreshold"] = int(health["retries"])
        limits = ((service.get("deploy") or {}).get("resources") or {}).get("limits") or {}
        if limits:
            container["resources"] = {"limits": {k: quantity(v) for k, v in limits.items() if quantity(v) is not None}}
        annotations: dict[str, str] = {"chaosatlas.io/static-only": "true"}
        depends_on = service.get("depends_on") or {}
        if depends_on:
            annotations["chaosatlas.io/depends-on"] = ",".join(sorted(str(item) for item in depends_on))
        resources.append(
            {
                "apiVersion": "apps/v1",
                "kind": "Deployment",
                "metadata": {"name": service_name, "namespace": namespace, "labels": labels, "annotations": annotations},
                "spec": {
                    "replicas": int(service.get("scale") or 1),
                    "selector": {"matchLabels": {"app.kubernetes.io/name": service_name, "app.kubernetes.io/part-of": "chaosatlas-p02"}},
                    "strategy": {"type": "Recreate"},
                    "template": {"metadata": {"labels": copy.deepcopy(labels)}, "spec": {"containers": [container]}},
                },
            }
        )
        if service_ports:
            resources.append(
                {
                    "apiVersion": "v1",
                    "kind": "Service",
                    "metadata": {"name": service_name, "namespace": namespace, "labels": labels},
                    "spec": {"type": "ClusterIP", "selector": {"app.kubernetes.io/name": service_name, "app.kubernetes.io/part-of": "chaosatlas-p02"}, "ports": service_ports},
                }
            )
    return resources


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--compose-json", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--namespace", default="chaosatlas-p02")
    parser.add_argument("--image-override", action="append", default=[], metavar="SERVICE=IMAGE")
    args = parser.parse_args()
    overrides: dict[str, str] = {}
    for value in args.image_override:
        service, separator, image = value.partition("=")
        if not separator or not service or not image:
            raise SystemExit(f"invalid --image-override: {value}")
        overrides[service] = image
    compose = json.loads(args.compose_json.read_text(encoding="utf-8-sig"))
    docs = generate(compose, args.namespace, overrides)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    output = args.output_dir / "static-profile.yaml"
    output.write_text("---\n".join(yaml.safe_dump(doc, sort_keys=False) for doc in docs), encoding="utf-8")
    manifest = {
        "schema_version": "1.0",
        "project_id": "P02",
        "namespace": args.namespace,
        "status": "static_profile_generated_dry_run_only",
        "source": str(args.compose_json).replace("\\", "/"),
        "resource_count": len(docs),
        "image_overrides": overrides,
        "runtime_apply_allowed": False,
        "remaining_gates": ["immutable image digest provenance", "kubectl server dry-run review", "namespace health", "baseline/recovery/cleanup"],
    }
    (args.output_dir / "profile_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "resource_count": len(docs), "status": manifest["status"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
