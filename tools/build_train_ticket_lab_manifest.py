"""Extract the minimal Train Ticket service slice for an isolated lab namespace."""

from __future__ import annotations

import argparse
from pathlib import Path

import yaml


def load_documents(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        return [doc for doc in yaml.safe_load_all(handle) if isinstance(doc, dict)]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--deployments",
        type=Path,
        default=Path("train-ticket/deployment/kubernetes-manifests/quickstart-k8s/yamls/deploy.yaml.sample"),
    )
    parser.add_argument(
        "--services",
        type=Path,
        default=Path("train-ticket/deployment/kubernetes-manifests/quickstart-k8s/yamls/svc.yaml"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/train-ticket/runtime/train-ticket-lab-services.yaml"),
    )
    parser.add_argument(
        "--selected",
        default="ts-order-service,ts-station-service",
        help="comma-separated Deployment/Service names to extract",
    )
    args = parser.parse_args()

    selected = {name.strip() for name in args.selected.split(",") if name.strip()}
    if not selected:
        raise SystemExit("--selected must contain at least one resource name")
    documents = []
    for path in (args.deployments, args.services):
        for document in load_documents(path):
            name = document.get("metadata", {}).get("name")
            if name in selected:
                documents.append(document)

    found = {doc["metadata"]["name"] for doc in documents}
    missing = sorted(selected - found)
    if missing:
        raise SystemExit(f"missing expected resources: {', '.join(missing)}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="\n") as handle:
        yaml.safe_dump_all(documents, handle, sort_keys=False, explicit_start=True)
    print(f"wrote {len(documents)} resources to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
