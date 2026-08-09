#!/usr/bin/env python3
"""Build the Sock Shop independent-track ledger (P1).

Sock Shop evidence is heterogeneous and must NOT be folded into the ordinary
run_ledger_master numbers (which are TT/OB/OTEL historical + OB r2). This
ledger records, separately:
  - 8 contract / real-chain edge-verdict records (sock_shop_verdicts.json)
  - 5 availability pod-kill records (avail_*_kill.json)
Each entry carries project_id, method_id, status, source_file, measurement_track,
evidence_type, and a flag for what kind of record it is (edge_verdict vs
service_kill vs not-a-runner-run). Unknown fields are 'unknown', never guessed.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERDICTS = ROOT / "artifacts" / "sock-shop" / "sock_shop_verdicts.json"
AVAIL_DIR = ROOT / "artifacts" / "sock-shop"
OUT_JSON = ROOT / "artifacts" / "experiments" / "archive" / "sock_track_ledger.json"
OUT_MD = ROOT / "artifacts" / "experiments" / "archive" / "sock_track_ledger.md"

# method_id for Sock evidence: real-chain measurement is our evidence chain;
# availability kill sampling is the availability measurement runner.
METHOD_BY_TRACK = {
    "real_chain": "our_evidence_chain",
    "availability": "measurement-availability",
    "direct": "our_evidence_chain",
}


def main() -> int:
    entries: list[dict] = []

    # 1. 8 contract/real-chain edge verdicts
    v = json.loads(VERDICTS.read_text(encoding="utf-8"))
    for c in v["candidates"]:
        cid = c["candidate_id"]
        meas = c.get("measurement", "unknown")
        track = "real_chain" if "real-chain" in meas or "POST /orders" in meas else ("direct" if meas == "direct" else "unknown")
        entries.append({
            "record_id": f"sock-edge-{cid}",
            "candidate_id": cid,
            "project_id": "SOCK",
            "method_id": METHOD_BY_TRACK.get(track, "unknown"),
            "status": "edge_verdict",
            "source_file": "artifacts/sock-shop/sock_shop_verdicts.json",
            "measurement_track": track,
            "evidence_type": "edge_verdict",
            "record_kind": "edge_verdict (not a runner run)",
            "verdict": c.get("verdict", "unknown"),
            "severity": c.get("severity"),
            "note": "contract-layer verdict: orders->payment/shipping defended via 5s Future.get (real-chain); front-end->carts/catalogue weakness (direct)",
        })

    # 2. 5 availability pod-kill records
    kill_files = sorted(AVAIL_DIR.glob("avail_*_kill.json"))
    for p in kill_files:
        doc = json.loads(p.read_text(encoding="utf-8"))
        svc = doc.get("service", p.name.replace("avail_", "").replace("_kill.json", ""))
        entries.append({
            "record_id": f"sock-avail-{svc}",
            "candidate_id": f"SOCK-{svc.upper()}-KILL-1",
            "project_id": "SOCK",
            "method_id": "measurement-availability",
            "status": doc.get("verdict", "unknown").split(" ")[0].lower() if doc.get("verdict") else "unknown",
            "source_file": f"artifacts/sock-shop/{p.name}",
            "measurement_track": "availability",
            "evidence_type": "service_kill",
            "record_kind": "service_kill (availability sampling, not a runner run)",
            "outage_window_s": doc.get("outage_window_s"),
            "min_ready": doc.get("min_ready"),
            "verdict": doc.get("verdict", "unknown"),
            "note": f"PodChaos pod-kill on {svc}; single-replica no-PDB -> total outage (AD-REDUNDANCY-001)",
        })

    result = {
        "schema_version": 1,
        "tool": "sock_track_ledger",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "counts": {
            "edge_verdict_records": sum(1 for e in entries if e["evidence_type"] == "edge_verdict"),
            "service_kill_records": sum(1 for e in entries if e["evidence_type"] == "service_kill"),
            "total": len(entries),
        },
        "separation_note": (
            "These 13 records are Sock Shop independent-track evidence. They are NOT part of "
            "run_ledger_master's 107 ordinary run records (TT/OB/OTEL historical + OB r2). "
            "Do not sum them into 107/91/83 figures."
        ),
        "entries": entries,
    }
    OUT_JSON.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    md = [
        "# Sock Shop 独立轨道台账",
        "",
        "> Sock Shop 证据异构，**不并入 run_ledger_master 的 107 条普通 run**。",
        "> 13 条独立证据：8 条契约/真实链路边判定 + 5 条 availability pod-kill。",
        "",
        "## 计数",
        "",
        "| 类型 | 数量 |",
        "|---|---|",
        f"| 契约/真实链路边判定 | {result['counts']['edge_verdict_records']} |",
        f"| availability pod-kill | {result['counts']['service_kill_records']} |",
        f"| 合计（独立轨道） | {result['counts']['total']} |",
        "",
        "## 普通 run records（对照，不混入）",
        "",
        "```",
        "普通 run records: 107（TT/OB/OTEL 历史 + OB r2）",
        "Sock Shop independent track evidence: 单独统计，不并入 107",
        "```",
        "",
        "## 明细",
        "",
        "| record_id | candidate | track | kind | verdict | source |",
        "|---|---|---|---|---|---|",
    ]
    for e in entries:
        md.append(f"| {e['record_id']} | {e['candidate_id']} | {e['measurement_track']} | {e['record_kind']} | {e['verdict']} | `{e['source_file'].split('/')[-1]}` |")
    OUT_MD.write_text("\n".join(md) + "\n", encoding="utf-8")
    print(json.dumps(result["counts"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
