#!/usr/bin/env python3
"""Build the Hotel Reservation PRE-experiment knowledge snapshot (P2).

Provenance honesty:
  - contract / availability : STATIC-RECONSTRUCTED from canonical Hotel source
    intake (delimitrou/DeathStarBench @ 6ecb0970, hotelReservation/). Edges
    observed from source call graph; connection-level dial timeout 120s is
    explicitly marked connection-level, NOT a per-request contract.
  - SE / DP / JE : generic cross-project rule libraries. They contain evidence
    from OTHER projects (TT/OB/OTEL/Sock) but NO Hotel evidence — relative to
    Hotel they are experiment-pre. Marked pre_experiment_commit.
  - candidate_map : candidate pool is NOT yet constructed (frozen AFTER this
    snapshot per protocol). Left empty with an explicit note.

Compatible with validate_knowledge_snapshot() / snapshot_is_full_experiment_pre().
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from decision_engine import snapshot_is_full_experiment_pre

ROOT = Path(__file__).resolve().parents[1]
EXPERIMENTS = ROOT / "artifacts" / "experiments"
OUT = ROOT / "artifacts" / "experiments" / "heldout" / "hotel_knowledge_snapshot_pre.json"

HOTEL_COMMIT = "6ecb09706140f8730b5385c08f1386c654c3c526"
HOTEL_URL = "https://github.com/delimitrou/DeathStarBench (hotelReservation/)"

# --- contract: STATIC from Hotel source intake ---
CONTRACTS_STATIC = {
    "HOTEL-frontend->search": {
        "contract": "no_timeout",
        "loss_bounded": False,
        "source_sha256": "453d3efeeb27c28896434cd1e7fa18f1810678b82835be909094bc629fe7764c",
        "evidence": "STATIC: frontend server.go initSearchClient('srv-search') gRPC; no per-request timeout on downstream call. dialer/dialer.go Timeout=120s is CONNECTION-level (dial), not per-request.",
        "note": "gRPC edge without explicit per-request deadline; unprotected (delay 1:1, loss hang until client boundary).",
    },
    "HOTEL-frontend->profile": {
        "contract": "no_timeout",
        "loss_bounded": False,
        "source_sha256": "453d3efeeb27c28896434cd1e7fa18f1810678b82835be909094bc629fe7764c",
        "evidence": "STATIC: frontend server.go initProfileClient('srv-profile') gRPC; no per-request timeout.",
        "note": "unprotected gRPC edge.",
    },
    "HOTEL-frontend->recommendation": {
        "contract": "no_timeout",
        "loss_bounded": False,
        "source_sha256": "453d3efeeb27c28896434cd1e7fa18f1810678b82835be909094bc629fe7764c",
        "evidence": "STATIC: frontend server.go initRecommendationClient('srv-recommendation') gRPC; no per-request timeout.",
        "note": "unprotected gRPC edge.",
    },
    "HOTEL-search->geo": {
        "contract": "no_timeout",
        "loss_bounded": False,
        "source_sha256": "a5fcee43b546d323c9dac61c28d1d558677f82e5da3c642676c92a8dcd5e616d",
        "evidence": "STATIC: search service uses geo.GeoClient (geo proto); no per-request timeout.",
        "note": "unprotected gRPC edge (search -> geo).",
    },
    "HOTEL-search->rate": {
        "contract": "no_timeout",
        "loss_bounded": False,
        "source_sha256": "a5fcee43b546d323c9dac61c28d1d558677f82e5da3c642676c92a8dcd5e616d",
        "evidence": "STATIC: search service uses rate.RateClient (rate proto); no per-request timeout.",
        "note": "unprotected gRPC edge (search -> rate).",
    },
}

# --- availability: STATIC from compose only. Kubernetes is not verified yet. ---
AVAILABILITY_STATIC = {
    "HOTEL": {
        "FRONTEND": {"replicas": 1, "pdb": None, "hpa": None, "service": "FRONTEND", "static_prediction": "compose single-replica no-PDB -> kill = total outage"},
        "RESERVATION": {"replicas": 1, "pdb": None, "hpa": None, "service": "RESERVATION", "static_prediction": "compose single-replica no-PDB -> kill = total outage"},
        "RATE": {"replicas": 1, "pdb": None, "hpa": None, "service": "RATE", "static_prediction": "compose single-replica no-PDB -> kill = total outage"},
        "PROFILE": {"replicas": 1, "pdb": None, "hpa": None, "service": "PROFILE", "static_prediction": "compose single-replica no-PDB -> kill = total outage"},
        "GEO": {"replicas": 1, "pdb": None, "hpa": None, "service": "GEO", "static_prediction": "compose single-replica no-PDB -> kill = total outage"},
        "SEARCH": {"replicas": 1, "pdb": None, "hpa": None, "service": "SEARCH", "static_prediction": "compose single-replica no-PDB -> kill = total outage"},
        "RECOMMENDATION": {"replicas": 1, "pdb": None, "hpa": None, "service": "RECOMMENDATION", "static_prediction": "compose single-replica no-PDB -> kill = total outage"},
        "REVIEW": {"replicas": 1, "pdb": None, "hpa": None, "service": "REVIEW", "static_prediction": "compose single-replica no-PDB -> kill = total outage"},
        "ATTRACTIONS": {"replicas": 1, "pdb": None, "hpa": None, "service": "ATTRACTIONS", "static_prediction": "compose single-replica no-PDB -> kill = total outage"},
        "USER": {"replicas": 1, "pdb": None, "hpa": None, "service": "USER", "static_prediction": "compose single-replica no-PDB -> kill = total outage"},
    }
}

for _service, _profile in AVAILABILITY_STATIC["HOTEL"].items():
    _profile["deployment_scope"] = "docker-compose"
    _profile["kubernetes_status"] = (
        "unavailable" if _service in {"REVIEW", "ATTRACTIONS"} else "verified"
    )

HOTEL_SOURCE_FILES = [
    {
        "path": "hotelReservation/docker-compose.yml",
        "sha256": "988b3e3d4c0c01c5032f47d6ff69db56a8245966ddb7dcaaef1b726ff641bc12",
        "scope": "compose availability",
    },
    {
        "path": "hotelReservation/README.md",
        "sha256": "6696c99eb4f698efb76c4360cc74bcb2ed6db8cdab5959cd7166433030463346",
        "scope": "source/intake context",
    },
    {
        "path": "hotelReservation/go.mod",
        "sha256": "a5a886b6b67cea384f09f4497cc273b1d710dbe719d9904bd9258446fa38ce90",
        "scope": "source/intake context",
    },
    {
        "path": "hotelReservation/kubernetes/README.md",
        "sha256": "8c8c3a1fb1a9ad7bb41b1727545e4d4252e2b8a6c59b0be8e662a9692371ef53",
        "scope": "Kubernetes inventory context; deployment manifests are listed and hashed below",
    },
    {
        "path": "hotelReservation/services/frontend/server.go",
        "sha256": "453d3efeeb27c28896434cd1e7fa18f1810678b82835be909094bc629fe7764c",
        "scope": "contract evidence: frontend -> search/profile/recommendation gRPC clients",
    },
    {
        "path": "hotelReservation/services/search/server.go",
        "sha256": "a5fcee43b546d323c9dac61c28d1d558677f82e5da3c642676c92a8dcd5e616d",
        "scope": "contract evidence: search -> geo/rate gRPC clients",
    },
    {
        "path": "hotelReservation/dialer/dialer.go",
        "sha256": "fbf886d052dc4a5f3c66b548c866a2e21c76b00234ccbe6f13eb11f16d8b42ab",
        "scope": "dial timeout (connection-level 120s, NOT per-request)",
    },
    {
        "path": "hotelReservation/kubernetes/frontend/frontend-deployment.yaml",
        "sha256": "6431e87a0617cc652eba261858657e03d630902bc03b39c0ad5e1710c5d7320e",
        "scope": "k8s availability: replicas=1, no probe",
    },
    {
        "path": "hotelReservation/kubernetes/geo/geo-deployment.yaml",
        "sha256": "76d43ebab0cba27a6ea55894e49a0ea3a70ffc7eccc527e6485dbe69bbadf58d",
        "scope": "k8s availability: replicas=1, no probe",
    },
    {
        "path": "hotelReservation/kubernetes/profile/profile-deployment.yaml",
        "sha256": "94f045ab94463f46e194009119564d32b042528abaaf45dbc67b7337eb286ce7",
        "scope": "k8s availability: replicas=1, no probe",
    },
    {
        "path": "hotelReservation/kubernetes/rate/rate-deployment.yaml",
        "sha256": "83c53a11343459817b35d635ee1b0f9fba29f8366b31635e2855e608c5634161",
        "scope": "k8s availability: replicas=1, no probe",
    },
    {
        "path": "hotelReservation/kubernetes/reccomend/recommendation-deployment.yaml",
        "sha256": "b226b638173ebe555ad5692f88a1ba96fc5c3c877495cbea62c829a8fa336b09",
        "scope": "k8s availability: replicas=1, no probe",
    },
    {
        "path": "hotelReservation/kubernetes/reserve/reservation-deployment.yaml",
        "sha256": "07c2c934c89ca0fe100183c60cff16b148e1678779c5952e7b045d4697b1f784",
        "scope": "k8s availability: replicas=1, no probe",
    },
    {
        "path": "hotelReservation/kubernetes/search/search-deployment.yaml",
        "sha256": "503c1e3a20a77f9bf0cd527e6c5b927d01a5c467b7194cf15598a5e29c9d0e32",
        "scope": "k8s availability: replicas=1, no probe",
    },
    {
        "path": "hotelReservation/kubernetes/user/user-deployment.yaml",
        "sha256": "5083ed726ac8ef70801481d7230a10ae1e37fd032263ce09d084615cdad16ac9",
        "scope": "k8s availability: replicas=1, no probe",
    },
    {
        "path": "hotelReservation/kubernetes/consul/consul-deployment.yaml",
        "sha256": "e7a80f4c16aae22f8876c5a643a83c3f12b300c462e99d2bcfdd6a9e63b503bc",
        "scope": "k8s infra availability",
    },
    {
        "path": "hotelReservation/kubernetes/jaeger/jaeger-deployment.yaml",
        "sha256": "b3fcb1e4c54f1c49e81d29a0dd01fb95e3d6776d6a799e17c252e05e032fc584",
        "scope": "k8s infra availability (observability)",
    },
    {
        "path": "hotelReservation/kubernetes/frontend/frontend-service.yaml",
        "sha256": "b87b3b483c55ec25c465914ba4d480bbad16cfc3400372e21e2da7fdecbdddac",
        "scope": "k8s service (port)",
    },
    {
        "path": "hotelReservation/kubernetes/search/search-service.yaml",
        "sha256": "d5b7df4447ef9442db50d5498b339324d07945a18960e43bcb3758825fcc9c01",
        "scope": "k8s service (port)",
    },
    {
        "path": "hotelReservation/kubernetes/reserve/reservation-service.yaml",
        "sha256": "3c9d4cb87dd008cbaf416fd026cf9f9fd15ab0aae16a780716f26b27f23e32a6",
        "scope": "k8s service (port)",
    },
    {
        "path": "hotelReservation/kubernetes/rate/rate-service.yaml",
        "sha256": "4b9dec62d5f44315ef32776a836b7b933e601c912229a54adb1789444691cbe4",
        "scope": "k8s service (port)",
    },
    {
        "path": "hotelReservation/kubernetes/profile/profile-service.yaml",
        "sha256": "fee355765bc0a45c26e103e56b9834ce9905fe18a6abff1f9b8bf36f8baf3313",
        "scope": "k8s service (port)",
    },
    {
        "path": "hotelReservation/kubernetes/reccomend/recommendation-service.yaml",
        "sha256": "7e416a8534c2a11f2e6c83b54eb21fd493e35296212b94b592159af5ca85e999",
        "scope": "k8s service (port)",
    },
    {
        "path": "hotelReservation/kubernetes/user/user-service.yaml",
        "sha256": "dd8b7520fedca16c288ed04f45dbceb5799f5a0b58e235dcf925925cf84fba0c",
        "scope": "k8s service (port)",
    },
    {
        "path": "hotelReservation/kubernetes/geo/geo-service.yaml",
        "sha256": "079aa827442aa9d3634894803dc06d053f21b80ee9769b0ab63a1998252cd0d2",
        "scope": "k8s service (port)",
    },
    {
        "path": "hotelReservation/kubernetes/profile/mongodb-profile-deployment.yaml",
        "sha256": "ad1204612f32bbdcf821ed54537e69b1c8e02f267efafd5e410c2f49b6e7bb7c",
        "scope": "k8s infra (mongo)",
    },
    {
        "path": "hotelReservation/kubernetes/rate/mongodb-rate-deployment.yaml",
        "sha256": "88aadc23047d1de500e0cbe4119777cadc793d40df59d535dc1a991fe48cc285",
        "scope": "k8s infra (mongo)",
    },
    {
        "path": "hotelReservation/kubernetes/reserve/mongodb-reservation-deployment.yaml",
        "sha256": "e3f79812f6ee554f0103f13a08dbc8d62abe4ae1e0503197511418e79030b172",
        "scope": "k8s infra (mongo)",
    },
    {
        "path": "hotelReservation/kubernetes/geo/mongodb-geo-deployment.yaml",
        "sha256": "2ff8ab98bbafcda3a0df7f446b1d8ace350a48fa4af14767fa4f93c5c9ac03ad",
        "scope": "k8s infra (mongo)",
    },
    {
        "path": "hotelReservation/kubernetes/user/mongodb-user-deployment.yaml",
        "sha256": "1091ca5cfbb2fecd20c1b09e3b3151cb73dd6bffbb2268e638bc447a4da47f28",
        "scope": "k8s infra (mongo)",
    },
    {
        "path": "hotelReservation/kubernetes/profile/memcached-profile-deployment.yaml",
        "sha256": "3843f7ab932a9b0a17ca244b605b60a185cd79a7c11ccb573a0f9a9231c4236f",
        "scope": "k8s infra (memcached)",
    },
    {
        "path": "hotelReservation/kubernetes/rate/memcached-rate-deployment.yaml",
        "sha256": "e94e1d235286a6a1d30bf1f71ad11f614337ba434610e634cdba0baab4394696",
        "scope": "k8s infra (memcached)",
    },
    {
        "path": "hotelReservation/kubernetes/reserve/memcached-reservation-deployment.yaml",
        "sha256": "88a91ede19ad96cdd0863c6e964bb336e347106ac36d37190259b6054196a699",
        "scope": "k8s infra (memcached)",
    },
]

EXPECTED_KNOWLEDGE_SHA256 = {
    "artifacts/experiments/selection_experience.json": "f7280be785e34504fdcde76f81db027c32d5db6d572a2fc648c65eb347704fc1",
    "artifacts/experiments/defense_pattern_library.json": "afffb6ada45c947a3110dec6365152af8260358a45f7eb6e415926de70f557d8",
    "artifacts/experiments/judgment_experience.json": "7756d8d3beb0ea6a4644a3d2ecff117b09eabe62ad3e1d2a33aee61c2c6eead6",
}

# candidate_map is intentionally EMPTY: the candidate pool is frozen AFTER this
# snapshot per protocol (anti-contamination pipeline order). Populated in a
# later freeze step, never from results.
CANDIDATE_MAP_STATIC: dict[str, str] = {}


def _sha256(rel: str) -> str:
    import hashlib

    # rel is relative to repo root, e.g. "artifacts/experiments/selection_experience.json"
    path = ROOT / rel
    if not path.exists():
        return "unavailable"
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_current(rel: str) -> dict:
    expected = EXPECTED_KNOWLEDGE_SHA256.get(f"artifacts/experiments/{rel}")
    actual = _sha256(f"artifacts/experiments/{rel}")
    if expected is None or actual != expected:
        raise RuntimeError(
            f"knowledge source drift for {rel}: expected {expected}, got {actual}; "
            "refuse to rebuild a pre-experiment snapshot from live files"
        )
    return json.loads((EXPERIMENTS / rel).read_text(encoding="utf-8"))


def main() -> int:
    # SE/DP/JE: generic cross-project rule libraries. They carry evidence from
    # other projects but NO Hotel evidence -> experiment-pre relative to Hotel.
    se = _load_current("selection_experience.json")
    dp = _load_current("defense_pattern_library.json")
    je = _load_current("judgment_experience.json")

    snapshot = {
        "schema_version": 1,
        "status": "valid",
        "status_reason": (
            "五源 source_provenance 均已验证为 experiment-pre (contract/availability = "
            "static_reconstructed_pre_experiment; SE/DP/JE = pre_experiment_commit, 无 Hotel 证据)。"
            f"Stage A 关闭闸门: {len(HOTEL_SOURCE_FILES)} 个 provenance source files (含 "
            f"{sum(1 for item in HOTEL_SOURCE_FILES if item['path'].startswith('hotelReservation/kubernetes/') and item['path'] != 'hotelReservation/kubernetes/README.md')} 个 Kubernetes 文件) "
            "逐文件 SHA-256 已补齐 (无 unavailable); 8 个业务 Kubernetes deployment 逐文件核查 "
            "(replicas=1, 无 liveness/readiness probe, 无 PDB, 无 HPA); REVIEW/ATTRACTIONS 无 "
            "Kubernetes deployment，标记为 unavailable; provenance_completeness=complete; "
            "snapshot_is_full_experiment_pre=True -> status=valid。"
        ),
        "provenance": {
            "kind": "hotel_static_reconstructed",
            "source_commit": HOTEL_COMMIT,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "source_files": HOTEL_SOURCE_FILES,
            "sha256": {
                **{entry["path"]: entry["sha256"] for entry in HOTEL_SOURCE_FILES},
                **{rel: _sha256(rel) for rel in EXPECTED_KNOWLEDGE_SHA256},
            },
            "provenance_completeness": "complete",
            "note": (
                "contract/availability STATIC-RECONSTRUCTED from canonical Hotel source "
                f"@{HOTEL_COMMIT[:12]} (pre-experiment; no Hotel runtime evidence). "
                "Compose availability AND Kubernetes availability are scoped separately (Stage A2): "
                "compose single-replica; 8 Kubernetes business deployments replicas=1, no "
                "liveness/readiness probe, no PDB, no HPA; REVIEW/ATTRACTIONS have no Kubernetes "
                "deployment and are unavailable for Kubernetes-specific availability candidates. "
                "SE/DP/JE are generic cross-project "
                "rule libraries with NO Hotel evidence -> pre-experiment relative to Hotel. "
                "candidate_map intentionally empty (pool frozen after this snapshot per "
                "protocol). dialer 120s timeout is connection-level, NOT a per-request contract."
            ),
        },
        "contract": {
            "contracts": CONTRACTS_STATIC,
            "availability": AVAILABILITY_STATIC,
            "availability_kubernetes": {
                # Stage A2: 8 business deployments all replicas=1, no probe, no PDB, no HPA.
                # REVIEW/ATTRACTIONS run single-node images without a k8s deploy yaml.
                "HOTEL": {
                    "FRONTEND": {"replicas": 1, "pdb": None, "hpa": None, "liveness_probe": False, "readiness_probe": False, "manifest_sha256": "6431e87a0617cc652eba261858657e03d630902bc03b39c0ad5e1710c5d7320e"},
                    "GEO": {"replicas": 1, "pdb": None, "hpa": None, "liveness_probe": False, "readiness_probe": False, "manifest_sha256": "76d43ebab0cba27a6ea55894e49a0ea3a70ffc7eccc527e6485dbe69bbadf58d"},
                    "PROFILE": {"replicas": 1, "pdb": None, "hpa": None, "liveness_probe": False, "readiness_probe": False, "manifest_sha256": "94f045ab94463f46e194009119564d32b042528abaaf45dbc67b7337eb286ce7"},
                    "RATE": {"replicas": 1, "pdb": None, "hpa": None, "liveness_probe": False, "readiness_probe": False, "manifest_sha256": "83c53a11343459817b35d635ee1b0f9fba29f8366b31635e2855e608c5634161"},
                    "RECOMMENDATION": {"replicas": 1, "pdb": None, "hpa": None, "liveness_probe": False, "readiness_probe": False, "manifest_sha256": "b226b638173ebe555ad5692f88a1ba96fc5c3c877495cbea62c829a8fa336b09"},
                    "RESERVATION": {"replicas": 1, "pdb": None, "hpa": None, "liveness_probe": False, "readiness_probe": False, "manifest_sha256": "07c2c934c89ca0fe100183c60cff16b148e1678779c5952e7b045d4697b1f784"},
                    "SEARCH": {"replicas": 1, "pdb": None, "hpa": None, "liveness_probe": False, "readiness_probe": False, "manifest_sha256": "503c1e3a20a77f9bf0cd527e6c5b927d01a5c467b7194cf15598a5e29c9d0e32"},
                    "USER": {"replicas": 1, "pdb": None, "hpa": None, "liveness_probe": False, "readiness_probe": False, "manifest_sha256": "5083ed726ac8ef70801481d7230a10ae1e37fd032263ce09d084615cdad16ac9"},
                    "REVIEW": {"availability_status": "unavailable", "manifest_sha256": None, "manifest_note": "single-node image (hotel_reserv_review_single_node); no k8s deploy yaml present"},
                    "ATTRACTIONS": {"availability_status": "unavailable", "manifest_sha256": None, "manifest_note": "single-node image (hotel_reserv_attractions_single_node); no k8s deploy yaml present"},
                }
            },
            "candidate_map": CANDIDATE_MAP_STATIC,
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
    snapshot["full_pre"] = snapshot_is_full_experiment_pre(snapshot)
    OUT.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {OUT}")
    print("provenance:", snapshot["source_provenance"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
