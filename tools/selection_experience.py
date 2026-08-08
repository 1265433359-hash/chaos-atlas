"""Selection experience: abstract 'where to test first' from real-world corpus.

The fourth knowledge asset (project-owner direction: "the project starts by
abstracting chaos-engineer experience from real YAML" — this layer was
missing). Judgment experience answers "is this symptom a weakness (after the
result)"; SELECTION experience answers "which candidates deserve testing
first (before injecting)".

Each entry combines TWO independent evidence sources:
- corpus_evidence: frequency of the test node in 1,935 real Chaos Mesh YAMLs
  (test_node_catalog.json) — what real chaos engineers actually inject;
- experiment_evidence: candidates from OUR 20 executed cases that confirmed
  a weakness (severity >= 2) in that family — where injecting really pays.

This turns the LLM's 'domain prior' (the reason M1's blind picks hit 5/5)
into an auditable, reusable, corpus+experiment-backed asset — so a new
project can pick candidates WITHOUT the LLM.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
EXPERIENCE_PATH = ROOT / "artifacts" / "experiments" / "selection_experience.json"
CATALOG_PATH = ROOT / "artifacts" / "train-ticket" / "test_node_catalog.json"

# Corpus facts (test_node_catalog.json, 1,935 real YAMLs).
CORPUS_FACTS: dict[str, dict[str, Any]] = {
    "network_delay": {"node": "network_delay", "document_count": 213, "kind": "NetworkChaos"},
    "network_loss": {"node": "network_loss", "document_count": 57, "kind": "NetworkChaos"},
    "network_partition": {"node": "network_partition", "document_count": 99, "kind": "NetworkChaos"},
    "pod_kill": {"node": "pod_pod-kill", "document_count": 220, "kind": "PodChaos"},
    "stress_cpu": {"node": "stress_cpu", "document_count": 230, "kind": "StressChaos"},
    "stress_memory": {"node": "stress_memory", "document_count": 142, "kind": "StressChaos"},
    "time_offset": {"node": "time_offset", "document_count": 119, "kind": "TimeChaos"},
    "http_delay": {"node": "http_delay", "document_count": 59, "kind": "HTTPChaos"},
}

SEED_ENTRIES: list[dict[str, Any]] = [
    {
        "id": "SE-NETWORK-FAMILY-001",
        "rule": "优先在网络故障家族上找弱点：真实语料里 NetworkChaos 是最常注入的类型（delay 213/loss 57/partition 99 docs），且我们实验里 13/14 个确认弱点来自网络故障——网络是最可能的弱点藏身处。",
        "dimensions": ["fault_family"],
        "corpus_evidence": [CORPUS_FACTS["network_delay"], CORPUS_FACTS["network_loss"], CORPUS_FACTS["network_partition"]],
        "experiment_evidence": [
            "OB-PAYMENT-DELAY-2000 (sev2)", "OB-PAYMENT-LOSS-100 (sev3)",
            "OTEL-PAYMENT-DELAY-2000 (sev2)", "OTEL-PAYMENT-LOSS-100 (sev3)",
            "OTEL-EMAIL-LOSS-100 (sev3)", "OB-CHECKOUT-DELAY-2000 (sev3)",
        ],
        "counter_example": "HTTPChaos 语料 183 docs 但平台 blocked 未测；不能断言 HTTP 家族同样易爆（未实证）",
        "transferable_to": "任意微服务系统：网络故障（延迟/丢包/分区）优先于 CPU/内存等资源类",
        "confidence": "high",
        "source": "语料频次 + 20 候选实验反推（13/14 weakness 为网络故障）",
    },
    {
        "id": "SE-LOSS-STRONGEST-001",
        "rule": "100% 丢包（loss）是打穿无超时同步调用的最稳手段：我们注入的所有 loss（payment/email/checkout）100% 挂死到客户端 deadline（severity 3）；真实语料 network_loss 57 docs。",
        "dimensions": ["fault_intensity"],
        "corpus_evidence": [CORPUS_FACTS["network_loss"]],
        "experiment_evidence": [
            "OB-PAYMENT-LOSS-100 (10s hang)", "OTEL-PAYMENT-LOSS-100 (10s hang)",
            "OTEL-EMAIL-LOSS-100 (10s hang)", "OB-CART-DELAY-2000 (12s client timeout)",
        ],
        "counter_example": "有超时/重试保护的下游，loss 可能被兜住（如 OB productcatalog 3s timeout 对 delay 有效；对 loss 是否有效未测）",
        "transferable_to": "发现'无超时'类弱点时，loss 是最短路径",
        "confidence": "high",
        "source": "全部 loss 实验 100% 挂死（severity 3）+ 语料 network_loss",
    },
    {
        "id": "SE-CORE-CHAIN-001",
        "rule": "结算/支付/下单等核心同步链路的调用最常缺超时：OB payment/cart/checkout 与 OTel checkout 全在核心链路挂死（sev2-3）；这些边是最高价值优先测试目标。",
        "dimensions": ["business_path"],
        "corpus_evidence": [],
        "experiment_evidence": [
            "OB-PAYMENT-DELAY/LOSS", "OB-CART-DELAY-2000", "OB-CHECKOUT-DELAY-2000",
            "OTEL-CHECKOUT-DELAY-2000", "OTEL-PAYMENT-DELAY/LOSS",
        ],
        "counter_example": "核心链路若已配置超时（OB productcatalog 3s timeout）则不爆——先查契约清单",
        "transferable_to": "电商/交易类微服务：支付、购物车、结算服务优先",
        "confidence": "high",
        "source": "核心链路 5+ 候选确认弱点 + 契约清单（无超时）",
    },
    {
        "id": "SE-SIDEEFFECT-COUPLING-001",
        "rule": "email/通知这类旁路依赖在真实项目里常被同步耦合：OTel 与 OB 的 email 都同步阻塞主流程（10s 挂死/5s 延迟放大）；新项目优先查旁路依赖是否同步耦合主流程。",
        "dimensions": ["business_path"],
        "corpus_evidence": [],
        "experiment_evidence": [
            "OTEL-EMAIL-LOSS-100 (10s hang)", "OTEL-EMAIL-DELAY-2000 (4.9s block)",
            "KB-OB-CHECKOUT-EMAIL-FAILURE-001",
        ],
        "counter_example": "旁路正确隔离（异步/独立预算）则不构成弱点——需源码确认调用方式",
        "transferable_to": "任意微服务：email/通知/日志/分析类旁路依赖",
        "confidence": "medium",
        "source": "OTel/OB email 双项目复现 + 判定经验 JE-COUPLING-001",
    },
    {
        "id": "SE-CROSSPROJECT-REPLICATION-001",
        "rule": "在 A 项目确认的弱点模式，优先到 B 项目同名服务/边复测：payment 无超时在 OB 和 OTel 都验证挂死；email 耦合同理——跨项目复现是低成本高收益的选择策略。",
        "dimensions": ["transferability"],
        "corpus_evidence": [],
        "experiment_evidence": [
            "OB-PAYMENT-LOSS-100 vs OTEL-PAYMENT-LOSS-100（都 10s 挂死）",
            "OB email vs OTel email（都阻塞主流程）",
        ],
        "counter_example": "B 项目的同名服务可能有不同实现（如 OB catalog 有 3s timeout 而 OTel catalog 无）——复测前查契约",
        "transferable_to": "多项目对比/迁移",
        "confidence": "medium",
        "source": "payment/email 双项目复现证据",
    },
]


def load(path: Path = EXPERIENCE_PATH) -> dict[str, Any]:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"schema_version": 1, "entries": []}


def save(doc: dict[str, Any], path: Path = EXPERIENCE_PATH) -> None:
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def seed(path: Path = EXPERIENCE_PATH) -> dict[str, Any]:
    """Seed entries; SEED_ENTRIES provides the static/revised fields, but
    runtime LEARNING fields (evidence_count, experiment_evidence additions,
    counter_examples, contested, adjudicated, confidence after upgrades) are
    preserved from the existing entry. This is what keeps backfill learning
    from being erased by a re-seed (e.g. by tests)."""
    doc = load(path)
    by_id = {e["id"]: e for e in doc.get("entries", [])}
    # Runtime fields that must survive a re-seed.
    runtime_fields = (
        "evidence_count", "counter_examples", "contested", "contested_reason",
        "adjudicated", "adjudication_note", "experiment_evidence",
    )
    for entry in SEED_ENTRIES:
        prev = by_id.get(entry["id"], {})
        merged = {**entry}
        for field in runtime_fields:
            if field in prev:
                merged[field] = prev[field]
        # confidence: runtime (backfill upgrades, adjudication demotions) is
        # evidence-driven and takes precedence over the static seed value.
        if prev.get("confidence"):
            merged["confidence"] = prev["confidence"]
        by_id[entry["id"]] = merged
    doc["entries"] = [by_id[eid] for eid in sorted(by_id)]
    save(doc, path)
    return doc


def validate(doc: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    seen: set[str] = set()
    for entry in doc.get("entries", []):
        entry_id = entry.get("id")
        if not entry_id:
            errors.append("entry missing id")
            continue
        if entry_id in seen:
            errors.append(f"duplicate id: {entry_id}")
        seen.add(entry_id)
        for field in ("rule", "corpus_evidence", "experiment_evidence", "counter_example", "transferable_to"):
            if field not in entry:
                errors.append(f"{entry_id}: missing {field}")
        if not entry.get("corpus_evidence") and not entry.get("experiment_evidence"):
            errors.append(f"{entry_id}: no corpus OR experiment evidence (rules must be evidence-backed)")
    return errors


def query(doc: dict[str, Any], dimension: str | None = None, text: str | None = None) -> list[dict[str, Any]]:
    entries = doc.get("entries", [])
    if dimension:
        entries = [e for e in entries if dimension in e.get("dimensions", [])]
    if text:
        tokens = text.lower().split()
        entries = [
            e for e in entries
            if all(
                tok in " ".join(
                    str(v) for v in (e.get("rule"), e.get("id"), e.get("experiment_evidence", []))
                ).lower()
                for tok in tokens
            )
        ]
    return entries


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", action="store_true")
    parser.add_argument("--validate", action="store_true")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--dimension", default=None)
    parser.add_argument("--query", default=None)
    args = parser.parse_args()
    if args.seed:
        doc = seed()
        print(json.dumps({"seeded": len(doc.get("entries", [])), "path": str(EXPERIENCE_PATH)}, indent=2))
        return 0
    if args.validate:
        doc = load()
        errors = validate(doc)
        print(json.dumps({"valid": not errors, "errors": errors}, indent=2, ensure_ascii=True))
        return 1 if errors else 0
    if args.list or args.dimension or args.query:
        doc = load()
        entries = query(doc, args.dimension, args.query)
        print(json.dumps(entries, indent=2, ensure_ascii=True))
        return 0
    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
