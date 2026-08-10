#!/usr/bin/env python3
"""Build ESHOP + SOCIALNET pre-experiment knowledge snapshots (Stage C).

Both snapshots reuse decision_engine.validate_knowledge_snapshot() and
snapshot_is_full_experiment_pre(); builders fail-closed on SE/DP/JE pinned SHA.

Provenance honesty:
  - ESHOP    : contract edges (WebApp->Catalog/Ordering etc) STATIC from
               eShop source @9b4f9434; NO k8s manifest -> availability sources
               unavailable -> provenance_completeness=partial -> snapshot
               status=blocked (availability cannot be reconstructed statically).
  - SOCIALNET: contract edges STATIC from socialNetwork/ source @6ecb0970;
               explicit 10s thrift timeout noted (protected candidates possible);
               helm-chart replicas/PDB NOT per-file verified -> availability
               unavailable -> blocked.
No runtime verdict / CE output / experiment result enters either snapshot.
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

ESHOP_COMMIT = "9b4f9434f46fdc5c1a6e9e936af2868340cdbc48"
SOCIALNET_COMMIT = "6ecb09706140f8730b5385c08f1386c654c3c526"

# Fail-closed pinned SHA for generic rule libraries.
PINNED_KNOWLEDGE_SHA = {
    "artifacts/experiments/selection_experience.json": "f7280be785e34504",
    "artifacts/experiments/defense_pattern_library.json": "afffb6ada45c947a",
    "artifacts/experiments/judgment_experience.json": "7756d8d3beb0ea6a",
}


def _sha256(rel: str) -> str:
    path = ROOT / rel
    if not path.exists():
        return "unavailable"
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_current(rel: str) -> dict:
    expected = PINNED_KNOWLEDGE_SHA.get(f"artifacts/experiments/{rel}")
    actual = _sha256(f"artifacts/experiments/{rel}")[:16]
    if expected is None or actual != expected:
        raise RuntimeError(
            f"FAIL-CLOSED: knowledge source drift for {rel}: expected {expected}, got {actual}"
        )
    return json.loads((EXPERIMENTS / rel).read_text(encoding="utf-8"))


def _build(project: str, commit: str, url: str, contracts: dict, avail_k8s, sha_files: dict,
           status: str, status_reason: str, completeness: str, out: Path) -> None:
    se = _load_current("selection_experience.json")
    dp = _load_current("defense_pattern_library.json")
    je = _load_current("judgment_experience.json")
    source_files = [
        {"path": p, "purpose": "contract/availability source", "sha256": s}
        for p, s in sha_files.items()
    ]
    snapshot = {
        "schema_version": 1,
        "status": status,
        "status_reason": status_reason,
        "provenance": {
            "kind": f"{project}_static_reconstructed",
            "source_commit": commit,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "source_files": source_files,
            "sha256": {**sha_files,
                       "selection_experience_live": _sha256("artifacts/experiments/selection_experience.json"),
                       "defense_pattern_library_live": _sha256("artifacts/experiments/defense_pattern_library.json"),
                       "judgment_experience_live": _sha256("artifacts/experiments/judgment_experience.json")},
            "provenance_completeness": completeness,
            "note": f"{project} STATIC-RECONSTRUCTED from {url} @{commit[:12]}; no runtime/CE/experiment evidence.",
        },
        "contract": {
            "contracts": contracts,
            "availability": {},
            "availability_kubernetes": avail_k8s,
            "candidate_map": {},
        },
        "selection_experience": se,
        "defense_pattern_library": dp,
        "judgment_experience": je,
        "source_provenance": {
            "contract": "static_reconstructed_pre_experiment",
            "availability": "static_reconstructed_pre_experiment" if avail_k8s else "unavailable",
            "selection_experience": "pre_experiment_commit",
            "defense_pattern_library": "pre_experiment_commit",
            "judgment_experience": "pre_experiment_commit",
        },
    }
    validate_knowledge_snapshot(snapshot)  # schema-compat gate
    full_pre = snapshot_is_full_experiment_pre(snapshot)
    snapshot["full_pre"] = full_pre
    out.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {out.name} | status={snapshot['status']} | completeness={completeness} | full_pre={full_pre}")
    return snapshot


def main() -> int:
    # ---------- ESHOP ----------
    eshop_contracts = {
        "ESHOP-webapp->catalog": {"contract": "no_timeout", "loss_bounded": False,
            "evidence": "STATIC WebApp/Extensions/Extensions.cs AddHttpClient<CatalogService>(BaseAddress catalog-api); no per-request timeout; no retry/circuit (grep 无命中)",
            "source_sha256": "d0009c09da7eb439964985e332e50d64d88f9ed317f6e254a279983655bac66a"},
        "ESHOP-webapp->ordering": {"contract": "no_timeout", "loss_bounded": False,
            "evidence": "STATIC WebApp/Extensions/Extensions.cs AddHttpClient<OrderingService>(BaseAddress ordering-api); no per-request timeout",
            "source_sha256": "d0009c09da7eb439964985e332e50d64d88f9ed317f6e254a279983655bac66a"},
    }
    eshop_sha = {
        "src/eShop.AppHost/Program.cs": "6c0e25977f2068211b776fc57fbb85898c3d6b576c99d3fb168d8dc2388fced7",
        "src/WebApp/Extensions/Extensions.cs": "d0009c09da7eb439964985e332e50d64d88f9ed317f6e254a279983655bac66a",
        "src/WebApp/Services/OrderingService.cs": "2e8578d1eda8e3ab7ce7e471d6e3d5447e4c80a1a0d1407af74734ce989932c2",
        "src/Basket.API/Grpc/BasketService.cs": "cb02d7b4fdf67553847490a0b5ab86614f17cb4c45e7ea53b515ab4fb193fdba",
        "src/eShop.ServiceDefaults/Extensions.cs": "61a80ad164411ba51026c5ea571ed3e5c9825186202302a1ff1464be76f8e442",
        "README.md": "3ef8cf674084750c4d5db6f9317226f8e0a6ebba932e0ee73c3f9060c2e41ae7",
    }
    _build(
        "ESHOP", ESHOP_COMMIT, "https://github.com/dotnet/eShop",
        eshop_contracts, {},
        eshop_sha,
        "blocked",
        "ESHOP 无 k8s manifest/docker-compose -> availability 来源 unavailable; provenance_completeness=partial; 五源含 unavailable -> 完整 frozen replay 不可声明。契约边(no_timeout)已静态确认。",
        "partial",
        HELDOUT / "eshop_knowledge_snapshot_pre.json",
    )

    # ---------- SOCIALNET ----------
    socialnet_contracts = {
        "SOCIALNET-composepost->poststorage": {"contract": "explicit_timeout", "loss_bounded": False,
            "evidence": "STATIC ComposePostService.cpp ClientPool<ThriftClient<PostStorageServiceClient>>; config/service-config.json post-storage-service timeout_ms=10000 (10s explicit thrift timeout)",
            "source_sha256": "ba0d2b08c0df94efcb8d53fd6f817a3259c028a75196adf9b9fa350601216211"},
        "SOCIALNET-composepost->usertimeline": {"contract": "explicit_timeout", "loss_bounded": False,
            "evidence": "STATIC ComposePostService.cpp ClientPool<UserTimelineServiceClient>; user-timeline-service timeout_ms=10000",
            "source_sha256": "ba0d2b08c0df94efcb8d53fd6f817a3259c028a75196adf9b9fa350601216211"},
        "SOCIALNET-composepost->text": {"contract": "explicit_timeout", "loss_bounded": False,
            "evidence": "STATIC ComposePostService.cpp ClientPool<TextServiceClient>; text-service timeout_ms=10000",
            "source_sha256": "ba0d2b08c0df94efcb8d53fd6f817a3259c028a75196adf9b9fa350601216211"},
        "SOCIALNET-composepost->user": {"contract": "explicit_timeout", "loss_bounded": False,
            "evidence": "STATIC ComposePostService.cpp ClientPool<UserServiceClient>; user-service timeout_ms=10000",
            "source_sha256": "ba0d2b08c0df94efcb8d53fd6f817a3259c028a75196adf9b9fa350601216211"},
        "SOCIALNET-composepost->media": {"contract": "explicit_timeout", "loss_bounded": False,
            "evidence": "STATIC ComposePostService.cpp ClientPool<MediaServiceClient>; media-service timeout_ms=10000",
            "source_sha256": "ba0d2b08c0df94efcb8d53fd6f817a3259c028a75196adf9b9fa350601216211"},
        "SOCIALNET-composepost->hometimeline": {"contract": "explicit_timeout", "loss_bounded": False,
            "evidence": "STATIC ComposePostService.cpp ClientPool<HomeTimelineServiceClient>; home-timeline-service timeout_ms=10000",
            "source_sha256": "ba0d2b08c0df94efcb8d53fd6f817a3259c028a75196adf9b9fa350601216211"},
        "SOCIALNET-composepost->uniqueid": {"contract": "explicit_timeout", "loss_bounded": False,
            "evidence": "STATIC ComposePostService.cpp ClientPool<UniqueIdServiceClient>; unique-id-service timeout_ms=10000",
            "source_sha256": "ba0d2b08c0df94efcb8d53fd6f817a3259c028a75196adf9b9fa350601216211"},
    }
    socialnet_sha = {
        "docker-compose.yml": "b2b3dec888d099a60101b8a3d1eae9bf71ef18ef64b557942048db905ec4d529",
        "social_network.thrift": "2a199791eb2c12ea8aa1ff259d0c0d98b89e67ed27868a4991a23d5cb4bdbaa2",
        "config/service-config.json": "783c9b76cc673f8f583b6fdc02a8f2272a9b183cad24c3edc94267458f689057",
        "src/ComposePostService/ComposePostService.cpp": "ba0d2b08c0df94efcb8d53fd6f817a3259c028a75196adf9b9fa350601216211",
        "shared_infra/tracing.h": "ec488043c28083fce487725ba3b1765470828407198d26edf58bf54e41290f42",
        "shared_infra/utils_thrift.h": "75702e79c4f42b23bf6921580aeabc57a39e1d2e51d9d0007b84745ad7b46953",
        "shared_infra/utils.h": "064b444be99f443f9041e60608f9453f8a8ccd7ce1e6e1fdb9fe05bef00f9db7",
    }
    _build(
        "SOCIALNET", SOCIALNET_COMMIT, "https://github.com/delimitrou/DeathStarBench (socialNetwork/)",
        socialnet_contracts, {},
        socialnet_sha,
        "blocked",
        "SOCIALNET helm-chart replicas/PDB/HPA 未逐文件核对 -> availability 来源 unavailable; provenance_completeness=partial。契约边已静态确认(含 10s 显式 thrift timeout -> protected 候选可构造)。共享 infra 标注 shared_infra_deathstarbench。",
        "partial",
        HELDOUT / "socialnet_knowledge_snapshot_pre.json",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
