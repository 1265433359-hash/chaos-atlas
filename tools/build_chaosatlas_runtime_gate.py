"""Build the secret-free runtime gate record for the ChaosAtlas ten-project study.

This records what is known before any model call. It deliberately does not run
kubectl, read credentials, build images, or change the cluster.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts/experiments/chaosatlas_10_projects"


PROJECTS = {
    "P01": ("environment_blocked", "aspire_apphost", "No committed Compose/Kubernetes manifest; Aspire-to-kind normalization is still required.", "HTTP eShop browse/cart/order transaction"),
    "P02": ("runtime_gate_passed_no_mutation", "docker_compose_microservices", None, "Gateway health plus pet/owner/visit CRUD request"),
    "P03": ("environment_blocked", "saleor_dev_compose", "Frozen worktree Compose references absent .devcontainer env files; a non-secret env profile is required.", "GraphQL health plus deterministic catalog query"),
    "P04": ("out_of_domain", "source_monorepo", "Frozen commit has no reproducible deployment entry suitable for the bounded kind budget.", "Medusa API health and catalog read, not run"),
    "P05": ("environment_blocked", "official_docker_compose", "Server/ML image tags are mutable and the resource profile is not frozen for CPU-only execution.", "Server health plus deterministic library read"),
    "P06": ("environment_blocked", "docker_compose_api", "The root Compose file is a dependency matrix; the Directus application image still needs a frozen source build and license review.", "REST health plus schema/items read"),
    "P07": ("environment_blocked", "docker_compose_collaboration", "The Compose file provides only Postgres/Redis; the Outline application needs a reproducible local build/profile.", "HTTP health plus deterministic document read"),
    "P08": ("environment_blocked", "docker_compose_or_helm", "The single-node profile uses mutable appsmith-ce:release and has not passed the resource pilot.", "Server health plus deterministic API request"),
    "P09": ("environment_blocked", "official_docker_compose_multi_service", "A local deterministic mock model profile and namespace manifest are not yet runtime-validated.", "API readiness plus local mock workflow"),
    "P10": ("environment_blocked", "built_quarkus_server", "A source-built image or immutable digest is required; the frozen tree alone is not an executable server image.", "Keycloak readiness plus local client token flow"),
}


def build() -> dict:
    now = datetime.now(timezone.utc).isoformat()
    projects = {}
    for project_id, (status, profile, blocker, workload) in PROJECTS.items():
        projects[project_id] = {
            "gate_status": status,
            "deployment_profile": profile,
            "blocker": blocker,
            "workload_contract": workload,
            "namespace": f"chaosatlas-{project_id.lower()}",
            "baseline": ({"status": "pass", "evidence": "runtime_profiles/P02/baseline_gateway_valid_2026-08-12.json"} if project_id == "P02" else {"status": "not_run_blocked", "evidence": None}),
            "health": ({"status": "pass", "evidence": "runtime_profiles/P02/runtime_gate_2026-08-12.json"} if project_id == "P02" else {"status": "not_run_blocked", "evidence": None}),
            "recovery": ({"status": "pass", "evidence": "runtime_profiles/P02/business_oracles_valid_2026-08-12.json"} if project_id == "P02" else {"status": "not_run_blocked", "evidence": None}),
            "cleanup": ({"status": "pass", "evidence": "runtime_profiles/P02/runtime_gate_2026-08-12.json"} if project_id == "P02" else {"status": "not_run_blocked", "evidence": None}),
            "independent_oracle": {"status": "template_pending_runtime_evidence", "labels_allowed": ["weakness", "protected", "unverifiable", "unsupported", "environment_blocked"]},
            "execution_ready": project_id == "P02",
            "method_result_eligible": False,
        }
    return {
        "schema_version": "1.0",
        "generated_at": now,
        "study": "ChaosAtlas three-arm real-project comparison",
        "secret_free": True,
        "cluster_preflight": {
            "status": "pass_read_only",
            "context": "kind-chaos-kind",
            "node": "chaos-kind-control-plane",
            "node_status": "Ready",
            "kubernetes_version": "v1.36.1",
            "chaos_mesh_crds": ["PodChaos", "NetworkChaos", "StressChaos"],
            "heldout_namespace_observed": "heldout-socialnet-lab Active",
            "mutation_performed": False,
        },
        "projects": projects,
        "summary": {
            "in_scope": 10,
            "execution_ready": 1,
            "method_result_eligible": 0,
            "environment_blocked": sum(v[0] == "environment_blocked" for v in PROJECTS.values()),
            "out_of_domain": sum(v[0] == "out_of_domain" for v in PROJECTS.values()),
            "deepseek_allowed": False,
            "reason": "P02 has deployment, health, baseline, recovery, and cleanup evidence; it remains method_result_eligible=false until the independent oracle and formal call gate are complete.",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=OUT / "runtime_gate_matrix.json")
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(build(), indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
