"""Judgment experience: abstract real-world chaos-engineering judgment rules.

Third knowledge asset (see judgment_experience_methodology.md). While
severity is a symptom-level, reproducible rule, real chaos engineers judge
"what a symptom MEANS in business context". These entries encode that
intuition as reusable, transferable rules, each backed by at least one real
case from this project AND a counter-example that bounds the rule.

Query by dimension or severity_adjustment so a new project can ask "how do I
judge a symptom like X" and get case-backed rules.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
EXPERIENCE_PATH = ROOT / "artifacts" / "experiments" / "judgment_experience.json"

DIMENSIONS = ("business_path", "contract", "recovery", "observability", "risk")
ADJUSTMENTS = ("upgrade", "confirm", "downgrade", "n_a")

SEED_ENTRIES: list[dict[str, Any]] = [
    {
        "id": "JE-COUPLING-001",
        "rule": "旁路/非关键依赖（email/通知/日志）同步阻塞主流程并挂到客户端超时 = 架构级耦合缺陷（severity 3 且判定价值最高），因为暴露的是依赖隔离缺失而非单个缺超时。",
        "dimensions": ["business_path"],
        "severity_adjustment": "upgrade",
        "evidence_cases": [
            "OTEL-EMAIL-LOSS-100: email 100% 丢包 -> PlaceOrder 10s DEADLINE_EXCEEDED x3",
            "KB-OB-CHECKOUT-EMAIL-FAILURE-001: OB email 故障阻塞下单",
        ],
        "counter_example": "独立旁路故障不影响主流程（若隔离正确）则不构成该缺陷",
        "transferable_to": "任意微服务系统：优先查 email/通知/日志/分析这类旁路依赖是否同步耦合主流程",
        "confidence": "high",
        "source": "本项目案例反推 + 混沌工程实践（非关键依赖耦合是最常见架构反模式）",
    },
    {
        "id": "JE-CONTRACT-001",
        "rule": "系统源码/配置声明的契约（WithTimeout/gRPC deadline/SLO）违约 = 明确漏洞；但测试客户端自设的 timeout 是测量预算，永远不是系统契约——挂到客户端 deadline 暴露的是'系统缺超时'，判定依据不同（A2 修正）。",
        "dimensions": ["contract"],
        "severity_adjustment": "confirm",
        "evidence_cases": [
            "OB-PAYMENT-LOSS-100: chargeCard 无 WithTimeout（main.go:369，系统无契约）；10s 挂死是 ob_client 10s 预算耗尽 → 弱点是'系统缺超时'而非'违约'",
            "OB-CART-DELAY-2000: 12s 客户端超时 x3，cart 读无 deadline",
            "TT 系: 无超时配置（application.yml），延迟放大无违约但无保护",
        ],
        "counter_example": "有系统级 timeout 且注入后仍违约（若存在）才是契约违约；TT-BASIC-500 1:1 无放大未触任何预算",
        "transferable_to": "判定前必须查 contract_inventory.json 区分系统契约 vs 客户端预算",
        "confidence": "high",
        "source": "A2 审计 + 源码核查（OB chargeCard 无 WithTimeout）",
    },
    {
        "id": "JE-CONTRACT-002",
        "rule": "系统无契约（无 SLO/无显式 deadline，见 contract_inventory）的延迟放大 ≠ 自动漏洞；应查是否有降级/兜底，无兜底则判'潜在风险'而非'确定漏洞'。runner 的 request_timeout 不算契约。",
        "dimensions": ["contract"],
        "severity_adjustment": "downgrade",
        "evidence_cases": [
            "TT-STATION-DELAY-2000: 2s 注入 -> 4s 响应，HTTP 200；系统无超时配置（潜在风险）",
            "TT-ORDER-DELAY-2000: 2s -> 4s HTTP 200（同上）",
        ],
        "counter_example": "有 SLO/预算声明的路径放大即违约（升级为确定漏洞）",
        "transferable_to": "无显式 SLO 的内部服务间调用",
        "confidence": "medium",
        "source": "A2 审计：TT 系 application.yml 无超时配置；runner timeout 5s/8s 为测试参数",
    },
    {
        "id": "JE-RECOVERY-001",
        "rule": "注入停止后系统不自动恢复（或恢复超时） = 严重度升级，无论原始症状强弱——恢复能力缺失是独立弱点。",
        "dimensions": ["recovery"],
        "severity_adjustment": "upgrade",
        "evidence_cases": [
            "K7 探针重启：paymentservice 重启后 Ready 超时 + 业务连接拒绝（probe_restart_recovery_timeout）",
        ],
        "counter_example": "注入后恢复正常（TT 系、OB/OTel 所有延迟/loss 注入后 cleanup 恢复基线）不触发升级",
        "transferable_to": "所有注入实验都应显式检查恢复是否自动完成",
        "confidence": "high",
        "source": "本项目探针重启逃逸机制研究",
    },
    {
        "id": "JE-OBSERVABILITY-001",
        "rule": "故障被追踪系统完整记录（trace/事件可见）但无自动告警 = 部分弱点（可诊断、不可预警）；'故障发生时无法被看见'本身是弱点，即使功能正常。",
        "dimensions": ["observability"],
        "severity_adjustment": "confirm",
        "evidence_cases": [
            "OTel payment: Jaeger 完整捕获注入窗口（payment span 4462ms + error event）但无 auto-alert",
        ],
        "counter_example": "故障完全不可见（无 trace 无日志）则严重度更高（完全黑洞）",
        "transferable_to": "任何带 Jaeger/链路追踪但缺告警链路的系统",
        "confidence": "medium",
        "source": "OTel 可观测性缺口研究",
    },
    {
        "id": "JE-RISK-001",
        "rule": "高概率现实故障（支付商超时/网络分区/丢包）暴露的弱点，排序价值高于低概率极端场景——风险 = 概率 × 影响，概率是排序依据而非判定依据。",
        "dimensions": ["risk"],
        "severity_adjustment": "n_a",
        "evidence_cases": [
            "所有 payment/email loss 场景（支付商超时是常态事件）",
            "TT-STATION-CPU-80: 单 worker 80% CPU 是低概率弱压场景 -> 排序靠后",
        ],
        "counter_example": "低概率高影响（如全部节点同时宕机）在特殊系统（银行）中仍需升级",
        "transferable_to": "候选排序/优先级，不改判定本身",
        "confidence": "medium",
        "source": "风险矩阵实践 + 本项目 CPU 弱影响观察",
    },
]

# A3/D2 enrichment: source-verification status (rules must be grounded in
# source/config, not just observation) + English rule for bilingual retrieval.
_ENRICH: dict[str, dict[str, Any]] = {
    "JE-COUPLING-001": {
        "source_verified": False,
        "source_note": "observation-inferred from OTEL-EMAIL-LOSS + OB email card; source check of checkout->email call pending",
        "en_rule": "A non-critical dependency (email/notification/log) synchronously blocking the primary flow and hanging to the client deadline = architecture-level coupling defect (severity 3+, highest value): it reveals missing dependency isolation, not a single missing timeout.",
    },
    "JE-CONTRACT-001": {
        "source_verified": True,
        "source_note": "OB chargeCard no WithTimeout confirmed at online-boutique/src/checkoutservice/main.go:369; TT application.yml no timeout config",
        "en_rule": "A violation of a SOURCE-DECLARED contract (WithTimeout/gRPC deadline/SLO) is a clear vulnerability; but a test-client's own timeout is a measurement budget, never a system contract - hanging to the client deadline reveals the system LACKS a timeout, a different finding (A2 fix).",
    },
    "JE-CONTRACT-002": {
        "source_verified": True,
        "source_note": "TT station/basic/order application.yml have no timeout config (verified); runner request_timeout is a test parameter",
        "en_rule": "Latency amplification with no system contract (no SLO/explicit deadline, see contract_inventory) is NOT automatically a vulnerability; check for degradation/fallback first - without it, classify as 'potential risk', not 'confirmed vulnerability'. The runner's request_timeout is not a contract.",
    },
    "JE-RECOVERY-001": {
        "source_verified": False,
        "source_note": "behavior-observed (K7 probe-restart recovery timeout); mechanism root not source-checked",
        "en_rule": "Failure to auto-recover after injection stops (or recovery timeout) upgrades severity regardless of symptom strength - missing recovery capability is an independent weakness.",
    },
    "JE-OBSERVABILITY-001": {
        "source_verified": False,
        "source_note": "observed via Jaeger capture (OTel payment); alert configuration not source-checked",
        "en_rule": "A fault fully captured by tracing (visible events) but without auto-alert = partial weakness (diagnosable, not alertable); 'cannot be seen at fault time' is itself a weakness even if functionality is normal.",
    },
    "JE-RISK-001": {
        "source_verified": True,
        "source_note": "derived from executed experiments; probability assignment is practitioner judgment, flagged",
        "en_rule": "Weaknesses exposed by high-probability real events (payment-provider timeout/network partition/packet loss) rank above low-probability extreme scenarios - risk = probability x impact; probability ranks, it does not judge.",
    },
}


def load(path: Path = EXPERIENCE_PATH) -> dict[str, Any]:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"schema_version": 1, "entries": []}


def save(doc: dict[str, Any], path: Path = EXPERIENCE_PATH) -> None:
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def seed(path: Path = EXPERIENCE_PATH) -> dict[str, Any]:
    """Seed entries; SEED_ENTRIES is the authoritative definition, so existing
    entries with the same id are replaced (they may have been revised, e.g. by
    an audit fix). A3/D2 enrichment (source_verified, en_rule) is merged in."""
    doc = load(path)
    by_id = {e["id"]: e for e in doc.get("entries", [])}
    for entry in SEED_ENTRIES:
        by_id[entry["id"]] = {**entry, **_ENRICH.get(entry["id"], {})}
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
        for field in ("rule", "dimensions", "severity_adjustment", "evidence_cases", "counter_example"):
            if not entry.get(field):
                errors.append(f"{entry_id}: missing {field}")
        if not entry.get("evidence_cases"):
            errors.append(f"{entry_id}: no evidence case (rules must be case-backed)")
        if entry.get("severity_adjustment") not in ADJUSTMENTS:
            errors.append(f"{entry_id}: bad severity_adjustment {entry.get('severity_adjustment')}")
        for dim in entry.get("dimensions", []):
            if dim not in DIMENSIONS:
                errors.append(f"{entry_id}: bad dimension {dim}")
    return errors


def query(doc: dict[str, Any], dimension: str | None = None, adjustment: str | None = None) -> list[dict[str, Any]]:
    entries = doc.get("entries", [])
    if dimension:
        entries = [e for e in entries if dimension in e.get("dimensions", [])]
    if adjustment:
        entries = [e for e in entries if e.get("severity_adjustment") == adjustment]
    return entries


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", action="store_true", help="seed entries (idempotent)")
    parser.add_argument("--validate", action="store_true", help="validate entries")
    parser.add_argument("--list", action="store_true", help="list all entries")
    parser.add_argument("--dimension", choices=DIMENSIONS, default=None)
    parser.add_argument("--adjustment", choices=ADJUSTMENTS, default=None)
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
    if args.list or args.dimension or args.adjustment:
        doc = load()
        entries = query(doc, args.dimension, args.adjustment)
        print(json.dumps(entries, indent=2, ensure_ascii=True))
        return 0
    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
