"""Build a secret-free index of deployment preflight decisions."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

try:
    from tools.p03_deployment_preflight import build as build_p03
    from tools.p06_deployment_preflight import build as build_p06
    from tools.p09_deployment_preflight import build as build_p09
except ModuleNotFoundError:
    from p03_deployment_preflight import build as build_p03
    from p06_deployment_preflight import build as build_p06
    from p09_deployment_preflight import build as build_p09

ROOT = Path(__file__).resolve().parents[1]
EXP = ROOT / "artifacts/experiments/chaosatlas_10_projects"


def build() -> dict:
    p01 = {
        "project_id": "P01",
        "status": "blocked",
        "root_reason": "no committed Compose/Kubernetes/Dockerfile application deployment at frozen eShop commit",
        "evidence": "artifacts/experiments/knowledge_ablation_bringup/ESHOP/feasibility_report.json",
    }
    records = [p01, build_p03(), build_p06(), build_p09()]
    return {
        "schema_version": "1.0",
        "kind": "chaosatlas_deployment_preflight_index",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "secret_free": True,
        "no_model_calls": True,
        "no_cluster_mutations": True,
        "records": records,
        "interpretation": "blocked means the frozen evidence cannot yet support a reproducible namespace-local runtime; it is not a method result or weakness finding",
    }


def main() -> int:
    out = EXP / "deployment_preflight_index.json"
    out.write_text(json.dumps(build(), indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
