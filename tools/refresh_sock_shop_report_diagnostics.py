"""Refresh Sock Shop diagnostic sidecars for already completed reports."""

from __future__ import annotations

import json
from pathlib import Path

from sock_shop_three_method import comparison_status, diagnostics


ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = (
    ROOT
    / "artifacts"
    / "experiments"
    / "chaosatlas_sockshop_three_method"
    / "runtime_results"
    / "sock-shop"
    / "teacher-minikube-three-method-r1"
)


def main() -> int:
    for name in ("chaosatlas-full.json", "chaosatlas-ablation.json"):
        path = REPORT_DIR / name
        report = json.loads(path.read_text(encoding="utf-8"))
        report["diagnostics"] = diagnostics(path, report["started_at"])
        report["comparison"] = comparison_status(report)
        path.write_text(
            json.dumps(report, indent=2, ensure_ascii=True) + "\n",
            encoding="utf-8",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
