#!/usr/bin/env python3
"""Build the master run ledger (A3): merge the historical 83 lifecycle-complete
injections (execution/remediation/run_ledger.json) with the r2 24 attempts
(execution/remediation/r2_runs/*.json) into one auditable register.

Every record carries: project_id, method_id, status, source_file, and one of
the strict status classes. Derived/prediction/summary files are explicitly
excluded from independent-injection counts (they are listed as derived records).

r2 baseline-invalid attempts (7/24) are recorded explicitly as invalid_baseline.

Pure read + one new JSON/MD output; no cluster, no mutation of historical data.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "artifacts" / "experiments" / "execution" / "remediation" / "run_ledger.json"
R2_DIR = ROOT / "artifacts" / "experiments" / "execution" / "remediation" / "r2_runs"
OUT_JSON = ROOT / "artifacts" / "experiments" / "archive" / "run_ledger_master.json"
OUT_MD = ROOT / "artifacts" / "experiments" / "archive" / "run_ledger_master.md"

# --- project inference from filename ---
def project_of(fname: str) -> str:
    u = fname.lower()
    if re.search(r"(tt_|_tt_|tt-|station|basic|train)", u):
        return "TT"
    if "otel" in u:
        return "OTEL"
    if "sock" in u:
        return "SOCK"
    if re.search(r"(ob_|_ob_|ob-|checkout|payment|cart|email|productcatalog|currency|shipping|adservice)", u):
        return "OB"
    return "UNKNOWN"


# --- method inference ---
def method_of(fname: str) -> str:
    u = fname.lower()
    if u.startswith("m1_"):
        return "M1"
    if "pros_" in u or "prospective" in u:
        return "M1"
    if u.startswith("track_k_"):
        return "orchestration_track"
    if u.startswith("smoke_") or u.startswith("confirmation_") or u.startswith("deep_"):
        return "our_evidence_chain"
    if u.startswith("pilot_"):
        return "comparison_pilot"
    return "our_evidence_chain"


# --- r2 run status (from the run JSON fields) ---
def r2_status(r: dict) -> str:
    base = r.get("baseline") or {}
    work = r.get("workload") or {}
    b_ok = base.get("ok_count", 0)
    b_n = base.get("samples", 3)
    inj = r.get("injection_status")
    clean = r.get("cleanup_absent_confirmed")
    if not (inj in (True, "True", "true")):
        return "invalid_not_injected"
    if b_ok < b_n:
        return "invalid_baseline"
    if clean is not True:
        return "cleanup_failed"
    return "independent_injection" if "_confirm" not in r.get("source_file", "") else "confirmation_run"


def main() -> int:
    entries: list[dict] = []

    # 1. historical 83 lifecycle-complete injections
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    for e in ledger["entries"]:
        if e["category"] != "injection_complete":
            continue
        fname = e["file"]
        entries.append({
            "run_id": f"hist-{fname}",
            "source_file": f"artifacts/experiments/execution/{fname}",
            "project_id": project_of(fname),
            "method_id": method_of(fname),
            "status": "independent_injection",
            "independent_injection": True,
            "confirmation_run": False,
            "invalid_baseline": False,
            "invalid_not_injected": False,
            "cleanup_failed": False,
            "environment_blocked": False,
            "note": "historical lifecycle-complete injection (run_ledger.json)",
        })

    # 2. r2 24 attempts
    r2_files = sorted(R2_DIR.glob("*.json"))
    for p in r2_files:
        r = json.loads(p.read_text(encoding="utf-8"))
        r["source_file"] = p.name
        status = r2_status(r)
        entries.append({
            "run_id": f"r2-{p.name}",
            "source_file": f"artifacts/experiments/execution/remediation/r2_runs/{p.name}",
            "project_id": "OB",
            "method_id": "r2_execute_one",
            "status": status,
            "independent_injection": status == "independent_injection",
            "confirmation_run": status == "confirmation_run",
            "invalid_baseline": status == "invalid_baseline",
            "invalid_not_injected": status == "invalid_not_injected",
            "cleanup_failed": status == "cleanup_failed",
            "environment_blocked": False,
            "note": r.get("candidate_id", ""),
        })

    # 3. derived/prediction/summary files (explicitly NOT independent injections)
    derived: list[dict] = []
    for e in ledger["entries"]:
        if e["category"] in ("derived_classification", "prediction_ranking", "summary_evaluation", "other"):
            derived.append({
                "source_file": e["file"],
                "category": e["category"],
                "independent_injection": False,
            })

    counts = {}
    for e in entries:
        counts[e["status"]] = counts.get(e["status"], 0) + 1
    independent_total = sum(1 for e in entries if e["independent_injection"])
    confirmation_total = sum(1 for e in entries if e["confirmation_run"])

    master = {
        "schema_version": 1,
        "tool": "run_ledger_master",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "merge_sources": {
            "historical_83": "execution/remediation/run_ledger.json (injection_complete)",
            "r2_24": "execution/remediation/r2_runs/*.json",
        },
        "independent_injection_total": independent_total,
        "confirmation_run_total": confirmation_total,
        "invalid_baseline_total": counts.get("invalid_baseline", 0),
        "status_counts": counts,
        "reconciliation_note": (
            "83 historical lifecycle-complete injections + 24 r2 attempts = 107 total run records. "
            "Of the 24 r2 attempts, 7 have invalid_baseline (checkout service restarted mid-batch), "
            "leaving 17 valid r2 observations (8 candidates x first run + 9 confirmations). "
            "Derived/prediction/summary files are listed in 'derived_files' and are NEVER counted as injections."
        ),
        "r2_invalid_baseline_files": [e["source_file"] for e in entries if e["status"] == "invalid_baseline"],
        "entries": entries,
        "derived_files_count": len(derived),
        "derived_files": derived,
    }
    OUT_JSON.write_text(json.dumps(master, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    # Markdown
    lines = [
        "# 主实验台账（Master Run Ledger）",
        "",
        f"> 合并：历史 83 次 lifecycle-complete 注入 + r2 24 次尝试 = {len(entries)} 条运行记录",
        f"> 独立注入：**{independent_total}**（历史 83）+ r2 有效观测 17（8 首跑 + 9 确认）",
        f"> r2 无效基线：**{counts.get('invalid_baseline', 0)}/24**（checkout 服务批次中途重启）",
        "",
        "## 状态口径",
        "",
        "| 状态 | 数量 | 说明 |",
        "|---|---|---|",
    ]
    for s, n in sorted(counts.items()):
        lines.append(f"| {s} | {n} | 见 run_ledger_master.json |")
    lines += [
        "",
        "## 独立注入（historical 83）按项目",
        "",
        "| 项目 | 数量 |",
        "|---|---|",
    ]
    from collections import Counter
    proj_counts = Counter(e["project_id"] for e in entries if e["independent_injection"])
    for p, n in sorted(proj_counts.items()):
        lines.append(f"| {p} | {n} |")
    lines += [
        "",
        "## 派生文件（不计入独立实验）",
        "",
        f"derived/prediction/summary 共 {len(derived)} 个文件，详见 run_ledger_master.json `derived_files`。",
        "",
        "## r2 无效基线文件（显式记录）",
        "",
    ]
    for f in master["r2_invalid_baseline_files"]:
        lines.append(f"- `{f}`")
    lines.append("")
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(f"entries={len(entries)} independent={independent_total} confirmation={confirmation_total} "
          f"invalid_baseline={counts.get('invalid_baseline', 0)} derived={len(derived)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
