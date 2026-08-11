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
               Helm availability is verified for the recorded service targets;
               three discovered contract edges remain excluded until their source
               files receive individual SHA-256 values.
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

# Fail-closed pinned SHA for generic rule libraries. Full hashes are required;
# short prefixes are not sufficient provenance for a frozen snapshot.
PINNED_KNOWLEDGE_SHA = {
    "artifacts/experiments/selection_experience.json": "f7280be785e34504fdcde76f81db027c32d5db6d572a2fc648c65eb347704fc1",
    "artifacts/experiments/defense_pattern_library.json": "afffb6ada45c947a3110dec6365152af8260358a45f7eb6e415926de70f557d8",
    "artifacts/experiments/judgment_experience.json": "7756d8d3beb0ea6a4644a3d2ecff117b09eabe62ad3e1d2a33aee61c2c6eead6",
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


def _build(project: str, commit: str, url: str, contracts: dict, avail_k8s,
           availability_scope: dict, sha_files: dict, status: str,
           status_reason: str, completeness: str, out: Path,
           unverified_contract_edges: list[str] | None = None) -> None:
    se = _load_current("selection_experience.json")
    dp = _load_current("defense_pattern_library.json")
    je = _load_current("judgment_experience.json")
    source_files = [
        {"path": p, "purpose": "contract/availability source", "sha256": s}
        for p, s in sha_files.items()
    ]
    contract_block = {
        "contracts": contracts,
        "availability": {},
        "availability_kubernetes": avail_k8s,
        "candidate_map": {},
    }
    if unverified_contract_edges:
        contract_block["unverified_contract_edges"] = unverified_contract_edges
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
        "contract": contract_block,
        "availability_scope": availability_scope,
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
        {"compose": "unavailable", "kubernetes": "unavailable", "deployment_target": "unknown"},
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
        "SOCIALNET-hometimeline->poststorage": {"contract": "explicit_timeout", "loss_bounded": False,
            "evidence": "STATIC HomeTimelineService.cpp ClientPool<ThriftClient<PostStorageServiceClient>>; timeout from config (per-service timeout_ms)",
            "source_sha256": "6252e351a177eccb5ef7917e8ef4eecbe591d110c2c1919b9079104e64f28915"},
        "SOCIALNET-hometimeline->socialgraph": {"contract": "explicit_timeout", "loss_bounded": False,
            "evidence": "STATIC HomeTimelineService.cpp ClientPool<ThriftClient<SocialGraphServiceClient>>; timeout from config",
            "source_sha256": "6252e351a177eccb5ef7917e8ef4eecbe591d110c2c1919b9079104e64f28915"},
    }
    socialnet_unverified_edges = [
        "SOCIALNET-usertimeline->poststorage",
        "SOCIALNET-user->socialgraph",
        "SOCIALNET-socialgraph->user",
    ]
    # SOCIALNET kubernetes availability (Stage C2 helm audit):
    # 28 sub-charts, each with deployment.yaml+service.yaml; global replicas=1,
    # hpa.enabled=false, NO PDB, business services have NO liveness/readiness
    # probe (values.yaml:77-79 probes belong to redis-cluster disabled config).
    # -> kill candidates constructible (PodChaos targets complete).
    socialnet_avail_k8s = {
        "SOCIALNET": {
            svc: {"replicas": 1, "pdb": None, "hpa": None, "liveness_probe": False, "readiness_probe": False,
                  "service": svc, "helm_chart": f"charts/{svc}/", "static_prediction": "k8s helm replicas=1 no-probe no-PDB -> kill = total outage"}
            for svc in (
                "compose-post-service", "post-storage-service", "user-timeline-service",
                "text-service", "user-service", "media-service", "home-timeline-service",
                "social-graph-service", "unique-id-service", "user-mention-service",
                "url-shorten-service", "nginx-thrift",
            )
        }
    }
    socialnet_sha = {
        "docker-compose.yml": "b2b3dec888d099a60101b8a3d1eae9bf71ef18ef64b557942048db905ec4d529",
        "social_network.thrift": "2a199791eb2c12ea8aa1ff259d0c0d98b89e67ed27868a4991a23d5cb4bdbaa2",
        "config/service-config.json": "783c9b76cc673f8f583b6fdc02a8f2272a9b183cad24c3edc94267458f689057",
        "src/ComposePostService/ComposePostService.cpp": "ba0d2b08c0df94efcb8d53fd6f817a3259c028a75196adf9b9fa350601216211",
        "src/HomeTimelineService/HomeTimelineService.cpp": "6252e351a177eccb5ef7917e8ef4eecbe591d110c2c1919b9079104e64f28915",
        # helm chart values.yaml (Stage C2 audit)
        "helm-chart/socialnetwork/charts/compose-post-service/values.yaml": "7703c14575f6101abf11dcfac09ef70e39100907b2986045d633d6c3e45f74da",
        "helm-chart/socialnetwork/charts/post-storage-service/values.yaml": "1da39c7df85b5a45aa6b38e510ab533d05e34495659c35d0775c8ac729ceb611",
        "helm-chart/socialnetwork/charts/user-timeline-service/values.yaml": "8206b55ee86802e7253589b2517aa0acf79f107d8da4ca6c29710f9e09eb9cc7",
        "helm-chart/socialnetwork/charts/text-service/values.yaml": "969007aaf5bd2f9e35162409b0d952b67972f3bad9a463c31c20142d3108c240",
        "helm-chart/socialnetwork/charts/user-service/values.yaml": "eaec5394b9667fbfe24921f673cf9b3fb3e43533d920700d32a601d683673847",
        "helm-chart/socialnetwork/charts/media-service/values.yaml": "b4d187f116debd0412b817f6c8522f1f78994f1626224302f867d8cf6d00408b",
        "helm-chart/socialnetwork/charts/home-timeline-service/values.yaml": "ea89e74089e5c7e80436799ba06d80e76e8c3f6d0436e79e0904c165badcf035",
        "helm-chart/socialnetwork/charts/social-graph-service/values.yaml": "fd803a50463d51146252a7a766b3055a599e7e3940718d05752c6657dd351bb5",
        "helm-chart/socialnetwork/charts/unique-id-service/values.yaml": "7b8eef720816ddf8ea0934965fa706e80607eec01dbef46275a67f5a9dd25827",
        "helm-chart/socialnetwork/charts/user-mention-service/values.yaml": "d95e176e672e83bbca27afcc6ee699d3fb3c8e07de773184242ef5febefc3dae",
        "helm-chart/socialnetwork/charts/url-shorten-service/values.yaml": "bc507696e5c69eeed0ddd2fca46820ab99108d086824268219d3d71732308b08",
        "helm-chart/socialnetwork/charts/nginx-thrift/values.yaml": "825177312373385f539ea933c0388e47e14c8cd231e06e916e45fe6669b5dcbf",
        "shared_infra/tracing.h": "ec488043c28083fce487725ba3b1765470828407198d26edf58bf54e41290f42",
        "shared_infra/utils_thrift.h": "75702e79c4f42b23bf6921580aeabc57a39e1d2e51d9d0007b84745ad7b46953",
        "shared_infra/utils.h": "064b444be99f443f9041e60608f9453f8a8ccd7ce1e6e1fdb9fe05bef00f9db7",
    }
    _build(
        "SOCIALNET", SOCIALNET_COMMIT, "https://github.com/delimitrou/DeathStarBench (socialNetwork/)",
        socialnet_contracts, socialnet_avail_k8s,
        {"compose": "verified", "kubernetes": "verified", "deployment_target": "helm_chart"},
        socialnet_sha,
        "valid",
        "Stage C2: helm-chart 28 sub-charts 逐文件核查 - 每服务 deployment+service 模板, replicas=1(global), hpa.enabled=false, 无 PDB, 业务服务无 liveness/readiness probe (values.yaml:77-79 属 redis-cluster disabled 配置)。kill 候选可构造(PodChaos 目标完整)。9 条 contract 边具有完整源码 SHA (ComposePost 7 + HomeTimeline 2);另 3 条边已发现但因源码 SHA 未完成而排除出可执行 contract。availability 来源完整 -> provenance complete -> full_pre=True。共享 infra 标注 shared_infra_deathstarbench。",
        "complete",
        HELDOUT / "socialnet_knowledge_snapshot_pre.json",
        unverified_contract_edges=socialnet_unverified_edges,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
