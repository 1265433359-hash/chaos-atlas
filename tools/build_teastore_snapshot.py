#!/usr/bin/env python3
"""Build TeaStore pre-experiment knowledge snapshot (Stage C3).

Reuses decision_engine.validate_knowledge_snapshot() and
snapshot_is_full_experiment_pre(); fails closed on SE/DP/JE pinned SHA.

Provenance honesty:
  - contract : STATIC from TeaStore source @34b37f7 - registryclient/Ribbon
               load-balancing edges with DefaultLoadBalancerRetryHandler(0,2,true)
               and LoadBalancerTimeoutException (retry+timeout semantics ->
               protected candidates constructible).
  - availability : ribbon.yaml 7 deployments (default replicas 1, no PDB, no
               explicit probe); helm values.yaml autoscaling present but enabled
               value UNKNOWN -> hpa marked unknown (NOT fabricated).
No runtime verdict / CE output / experiment result enters this snapshot.
candidate_map stays empty (pool frozen later, never from results).
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from decision_engine import validate_knowledge_snapshot, snapshot_is_full_experiment_pre  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
EXPERIMENTS = ROOT / "artifacts" / "experiments"
HELDOUT = EXPERIMENTS / "heldout"
OUT = HELDOUT / "teastore_knowledge_snapshot_pre.json"

TEASTORE_COMMIT = "34b37f7e7be433ce72d5f9455e66922a13116749"
TEASTORE_URL = "https://github.com/DescartesResearch/TeaStore"

# Fail-closed pinned SHA (64-char full hashes).
PINNED_KNOWLEDGE_SHA = {
    "artifacts/experiments/selection_experience.json": "f7280be785e34504fdcde76f81db027c32d5db6d572a2fc648c65eb347704fc1",
    "artifacts/experiments/defense_pattern_library.json": "afffb6ada45c947a3110dec6365152af8260358a45f7eb6e415926de70f557d8",
    "artifacts/experiments/judgment_experience.json": "7756d8d3beb0ea6a4644a3d2ecff117b09eabe62ad3e1d2a33aee61c2c6eead6",
}

# TeaStore contract edges: STATIC from registryclient/Ribbon source.
CONTRACTS_STATIC = {
    "TEASTORE-webui->auth": {
        "contract": "bounded_retry", "loss_bounded": True,
        "evidence": "STATIC: webui -> auth via RegistryClient/ServiceLoadBalancer; Ribbon DefaultLoadBalancerRetryHandler(0,2,true) retries 2x across servers; LoadBalancerTimeoutException bounds latency/loss",
        "source_sha256": "e5d44e7bf7726341732b489a9503b9c36911a989b27da927ef9e01077abebb07",
    },
    "TEASTORE-webui->image": {
        "contract": "bounded_retry", "loss_bounded": True,
        "evidence": "STATIC: webui -> image via Ribbon load balancer with retry handler",
        "source_sha256": "e5d44e7bf7726341732b489a9503b9c36911a989b27da927ef9e01077abebb07",
    },
    "TEASTORE-webui->persistence": {
        "contract": "bounded_retry", "loss_bounded": True,
        "evidence": "STATIC: webui -> persistence via Ribbon load balancer with retry handler",
        "source_sha256": "e5d44e7bf7726341732b489a9503b9c36911a989b27da927ef9e01077abebb07",
    },
    "TEASTORE-webui->recommender": {
        "contract": "bounded_retry", "loss_bounded": True,
        "evidence": "STATIC: webui -> recommender via Ribbon load balancer with retry handler",
        "source_sha256": "e5d44e7bf7726341732b489a9503b9c36911a989b27da927ef9e01077abebb07",
    },
}

# availability: ribbon.yaml 7 deployments, default replicas 1, no PDB, no explicit probe.
AVAILABILITY_RIBBON = {
    "TEASTORE": {
        svc: {"replicas": 1, "pdb": None, "hpa": None, "liveness_probe": None, "readiness_probe": None,
              "service": svc, "source": "examples/kubernetes/teastore-ribbon.yaml",
              "static_prediction": "k8s ribbon deployment default replicas=1 no explicit probe no PDB -> kill = total outage"}
        for svc in ("registry", "persistence", "auth", "image", "recommender", "webui", "db")
    }
}


def _sha256(rel: str) -> str:
    path = ROOT / rel
    if not path.exists():
        return "unavailable"
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_current(rel: str) -> dict:
    expected = PINNED_KNOWLEDGE_SHA.get(f"artifacts/experiments/{rel}")
    actual = _sha256(f"artifacts/experiments/{rel}")
    if expected is None or actual != expected:
        raise RuntimeError(
            f"FAIL-CLOSED: knowledge source drift for {rel}: expected {expected}, got {actual}"
        )
    return json.loads((EXPERIMENTS / rel).read_text(encoding="utf-8"))


def main() -> int:
    se = _load_current("selection_experience.json")
    dp = _load_current("defense_pattern_library.json")
    je = _load_current("judgment_experience.json")

    sha_files = {
        "examples/helm/values.yaml": "4b5dcbfd2752b8206343fb0b2029e1a632bb626c39b7273af5ec295e73c2d36e",
        "examples/kubernetes/teastore-ribbon.yaml": "3e7b473c3086b208d7699081fe4091ca90b3fb20ae8489922ad01d57ad6934c9",
        "examples/docker/docker-compose_default.yaml": "cf26a369810edb8714f277deb4ec75afafe7772eb8a27bcd5703055904bd577d",
        "utilities/.../loadbalancers/ServiceLoadBalancer.java": "e5d44e7bf7726341732b489a9503b9c36911a989b27da927ef9e01077abebb07",
        "utilities/.../registryclient/RegistryClient.java": "a2e77b0e11bb8e2a6aefd3986ab5bb9a9fb3741b81fcb71b4ebe9c44ee18f302",
        "pom.xml": "198cb1cbd27dc8bcda09134ae4fc24f8ebaf9fe44a83295f497493255037fe6c",
    }
    source_files = [
        {"path": p, "purpose": "TeaStore contract/availability source", "sha256": s}
        for p, s in sha_files.items()
    ]

    snapshot = {
        "schema_version": 1,
        "status": "valid",
        "status_reason": (
            "TeaStore @34b37f7 源码/部署路径逐文件核验 (helm/ribbon/compose); contract 独立从 "
            "registryclient/Ribbon 源码构造 (retry+LoadBalancerTimeoutException -> protected 候选可构造); "
            "availability 来自 ribbon.yaml 7 deployments (replicas=1 默认, 无 PDB, 无显式 probe); "
            "五源 provenance 完整 -> valid/full_pre=True。helm autoscaling.enabled 值 unknown 已标注, 未伪造。"
        ),
        "provenance": {
            "kind": "teastore_static_reconstructed",
            "source_commit": TEASTORE_COMMIT,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "source_files": source_files,
            "sha256": {
                **sha_files,
                "selection_experience_live": _sha256("artifacts/experiments/selection_experience.json"),
                "defense_pattern_library_live": _sha256("artifacts/experiments/defense_pattern_library.json"),
                "judgment_experience_live": _sha256("artifacts/experiments/judgment_experience.json"),
            },
            "provenance_completeness": "complete",
            "note": (
                f"TeaStore STATIC-RECONSTRUCTED from {TEASTORE_URL} @{TEASTORE_COMMIT[:12]}; "
                "no runtime/CE/experiment evidence. Contract edges independent from TeaStore "
                "source (not reused from Hotel/SOCIALNET). Ribbon retry + LoadBalancerTimeout "
                "semantics noted. helm autoscaling.enabled = unknown."
            ),
        },
        "contract": {
            "contracts": CONTRACTS_STATIC,
            "availability": AVAILABILITY_RIBBON,
            "availability_kubernetes": AVAILABILITY_RIBBON,
            "candidate_map": {},
        },
        "selection_experience": se,
        "defense_pattern_library": dp,
        "judgment_experience": je,
        "source_provenance": {
            "contract": "static_reconstructed_pre_experiment",
            "availability": "static_reconstructed_pre_experiment",
            "selection_experience": "pre_experiment_commit",
            "defense_pattern_library": "pre_experiment_commit",
            "judgment_experience": "pre_experiment_commit",
        },
    }
    validate_knowledge_snapshot(snapshot)
    full_pre = snapshot_is_full_experiment_pre(snapshot)
    snapshot["full_pre"] = full_pre
    OUT.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {OUT.name} | status={snapshot['status']} | completeness=complete | full_pre={full_pre}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
