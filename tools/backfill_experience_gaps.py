"""Backfill knowledge-base gaps from real deployments (2026-08-09 audit).

Audit finding: defense_pattern_library contained only 3 unverified
absorbed_by_design entries (train-ticket) - none of the REAL defense
mechanisms measured this session were registered. Also, deployment-stage
lessons (probe pollution, image compat, port mismatch, OOM) were never
structured as transferable knowledge.

This script adds:
  defense_pattern_library:
    - DP-BOUNDED-TIMEOUT-FUTUREGET-001  (orders->payment/shipping 5s Future.get, source_verified=True)
  selection_experience (test-design/hygiene lessons from real YAML + deploy):
    - SE-TEST-HYGIENE-PROBE-001         (liveness probe timeout < injected latency -> SIGKILL escapes the injection)
    - SE-TEST-HYGIENE-IMAGECOMPAT-001   (mongo:latest 8.x breaks legacy drivers: OP_QUERY 352 -> pin 4.0)
    - SE-TEST-HYGIENE-PORTMISMATCH-001  (container listen port != svc targetPort -> silent connection refused)
    - SE-TEST-HYGIENE-OOM-001           (no resource limits -> OOM crash-loop; availability weakness, not probe)

AUDIT FIX (2026-08-09): an earlier revision added DP-REDUNDANCY-ABSENT-001
("single-replica no-PDB -> kill = total outage") to the defense-pattern
library. That violated the A1 audit principle (an ABSENT defense is NOT a
defense pattern - absence rules live in contract_inventory AVAILABILITY
static_prediction + decision_engine availability_hard_filter). The entry was
removed from the library; it is intentionally NOT re-added here.

All entries carry evidence from this session's real executions.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DP_PATH = ROOT / "artifacts" / "experiments" / "defense_pattern_library.json"
SE_PATH = ROOT / "artifacts" / "experiments" / "selection_experience.json"

DP_ADDITIONS = [
    {
        "pattern_id": "DP-BOUNDED-TIMEOUT-FUTUREGET-001",
        "defense_mechanism": "bounded_timeout",
        "source_verified": True,
        "source_note": "jar javap (Future.get + TimeoutException) + runtime TimeoutException at 5.07s",
        "evidence": {
            "project": "sock-shop",
            "candidate_id": "SOCK-ORDERS-PAYMENT-DELAY-2000",
            "mutation": "tc netem delay 2s/6s on payment veth (real-chain POST /orders)",
            "observation": "2s -> 201@4.15s (absorbed, RTT 4.0s); 6s -> 500@5.10s TimeoutException; direct curl -> 12s hang (position artifact)",
            "evidence_files": ["artifacts/sock-shop/sock_orders_future_get_verified.md"],
        },
        "inference": (
            "Future.get(timeout, SECONDS) async timeout (OrdersController.java:139/160, "
            "@Value ${http.timeout:5}) bounds BOTH delay and loss (loss_bounded): never an "
            "infinite hang. Invisible to direct port measurement - only business-chain entry "
            "reveals it."
        ),
    },
]

SE_ADDITIONS = [
    {
        "id": "SE-TEST-HYGIENE-PROBE-001",
        "rule": (
            "liveness/readiness probe timeout must exceed the injected latency, else the "
            "kubelet SIGKILLs the pod mid-experiment and the injection 'escapes' - the "
            "observed failure is probe self-kill, not the system's defense behavior. "
            "Check probe timeouts BEFORE designing delay injections (Sock Shop payment: "
            "1s probe killed pod on 2s+ injection; relaxed to 25s for clean experiments)."
        ),
        "dimensions": ["test_design"],
        "corpus_evidence": [],
        "experiment_evidence": [
            "SOCK-PAYMENT: 1s liveness + 2s delay -> pod SIGKILL (experiment polluted)",
            "OB probe-restart escape (1s probe vs 2s+ delay, prior session)",
        ],
        "counter_example": "probe timeout >= injected latency, or probes disabled, keeps the experiment valid",
        "transferable_to": "任何用延迟注入测试有探针的服务；先读 deployment 探针配置",
        "confidence": "high",
        "source": "Sock Shop payment 探针污染实测 + OB 探针重启逃逸(既有)",
        "evidence_count": 2,
    },
    {
        "id": "SE-TEST-HYGIENE-IMAGECOMPAT-001",
        "rule": (
            "DB image 'latest' (mongo 8.x) breaks legacy app drivers: 'Unsupported OP_QUERY "
            "command: find/insert (code 352)'. If an old Spring/Go app fails with 352, pin "
            "the DB to the era-appropriate major (mongo:4.0) rather than debugging the app."
        ),
        "dimensions": ["infrastructure"],
        "corpus_evidence": [],
        "experiment_evidence": [
            "carts-db mongo:latest -> carts 500 (OP_QUERY 352); mongo:4.0 -> 201",
            "orders-db mongo:latest -> orders insert 500 (OP_QUERY 352); mongo:4.0 -> 201",
        ],
        "counter_example": "modern driver / gRPC clients speak wire protocol v2+ (no OP_QUERY)",
        "transferable_to": "任何 'latest' DB 镜像 + 老微服务；先验证驱动兼容再排查应用",
        "confidence": "high",
        "source": "Sock Shop carts/orders-db 降级实测",
        "evidence_count": 2,
    },
    {
        "id": "SE-TEST-HYGIENE-PORTMISMATCH-001",
        "rule": (
            "Container listening port may differ from the Service targetPort in real YAML "
            "(front-end listens 8079, svc targetPort was 80 -> silent connection refused). "
            "Verify the container's actual listen port (netstat/ss) before blaming the mesh "
            "or the app - patch svc targetPort to the real port."
        ),
        "dimensions": ["infrastructure"],
        "corpus_evidence": [],
        "experiment_evidence": ["front-end: pod IP :80 refused; :8079 200; patched svc targetPort 8079 -> svc OK"],
        "counter_example": "container port == svc targetPort (most manifests)",
        "transferable_to": "任何 svc 连接拒绝先查 targetPort 一致性",
        "confidence": "high",
        "source": "Sock Shop front-end 8079/80 排查",
        "evidence_count": 1,
    },
    {
        "id": "SE-TEST-HYGIENE-OOM-001",
        "rule": (
            "Services without resource limits can OOM-crashloop independently of probes or "
            "injections (catalogue-db OOMKilled repeatedly). Distinguish infra OOM from "
            "probe/liveness issues before attributing it to the injected fault."
        ),
        "dimensions": ["infrastructure"],
        "corpus_evidence": [],
        "experiment_evidence": ["catalogue-db OOMKilled exit 137 crash-loop (no resource limits in deployment)"],
        "counter_example": "resources.limits set (survives normal load)",
        "transferable_to": "任何无 resources.limits 的服务；测前先查 limit",
        "confidence": "medium",
        "source": "Sock Shop catalogue-db OOM 观察",
        "evidence_count": 1,
    },
]


def merge_additions(path: Path, key: str, additions: list[dict]) -> None:
    doc = json.loads(path.read_text(encoding="utf-8"))
    existing = {e.get("id") or e.get("pattern_id") for e in doc.get(key, [])}
    added = 0
    for entry in additions:
        eid = entry.get("id") or entry.get("pattern_id")
        if eid in existing:
            print(f"  skip (exists): {eid}")
            continue
        doc.setdefault(key, []).append(entry)
        added += 1
    doc["generated_at"] = datetime.now(timezone.utc).isoformat()
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(f"{path.name}: +{added} entries (total {len(doc.get(key, []))})")


def main() -> int:
    print("defense_pattern_library:")
    merge_additions(DP_PATH, "patterns", DP_ADDITIONS)
    print("selection_experience:")
    merge_additions(SE_PATH, "entries", SE_ADDITIONS)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
