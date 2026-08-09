"""Contract inventory: extract SYSTEM-declared contracts (not runner params).

A2 audit fix: contract judgment used runner parameters (request_timeout 5s/8s)
as if they were system SLAs. The truth is that runner timeouts are the TEST
CLIENT's budget, never the system's promise. This inventory records the
SOURCE-level contract for each edge (explicit timeout/deadline in code or
config), and it is the ONLY basis for the contract dimension in judgment.

Fields per edge:
- contract: "explicit_timeout" | "no_timeout" | "unknown" (source not checked)
- evidence: source file/line or config key
- client_budget: what the test client imposed (for provenance, NOT a contract)
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
INVENTORY_PATH = ROOT / "artifacts" / "experiments" / "contract_inventory.json"

# Source-verified contract facts (2026-08-09, A2 audit).
# client_budget is recorded for provenance only and must never be treated as
# a system contract.
CONTRACTS: dict[str, dict[str, Any]] = {
    "OB-checkout->payment": {
        "contract": "no_timeout",
        "evidence": "online-boutique/src/checkoutservice/main.go:369 chargeCard -> PaymentService.Charge(ctx) no WithTimeout/WithDeadline; card KB-OB-CHECKOUT-PAYMENT-DELAY-001 confirms",
        "client_budget": {"source": "ob_client.py run_one timeout_s=10", "value_s": 10.0},
        "note": "10s hang is client budget exhaustion, NOT system contract violation; the weakness is the ABSENCE of a system timeout",
    },
    "OB-checkout->cart": {
        "contract": "no_timeout",
        "evidence": "checkout cart read without per-call deadline (same file); cart delay -> 12s client timeout x3",
        "client_budget": {"source": "ob_client.py run_one timeout_s=10", "value_s": 10.0},
        "note": "client process error at ~12s (connect+read); system has no cart timeout",
    },
    "OB-checkout->productcatalog": {
        "contract": "no_timeout",
        "evidence": "checkoutservice/main.go:161 context.WithTimeout(ctx, 3s) is CONNECTION-LEVEL (otlptracegrpc collector setup), NOT per-request protection; chargeProduct call uses PlaceOrder ctx without deadline (2026-08-09 source re-verification)",
        "client_budget": {"source": "ob_client.py run_one timeout_s=10", "value_s": 10.0},
        "note": "REVISED 2026-08-09: previously mislabeled explicit_timeout; the 3s WithTimeout only guards connection setup, productcatalog calls are unprotected",
    },
    "OB-frontend->adservice": {
        "contract": "explicit_timeout",
        "evidence": "online-boutique/src/frontend/rpc.go:120 getAd -> context.WithTimeout(ctx, time.Millisecond*100) on GetAds per-request",
        "client_budget": {"source": "ob_client.py run_one timeout_s=10", "value_s": 10.0},
        "note": "100ms per-request timeout is a REAL system defense: adservice delay beyond 100ms is absorbed by the frontend timeout (protected edge for mixed-pool experiment)",
    },
    "OTel-checkout->payment": {
        "contract": "unknown",
        "evidence": "OTel demo source not in workspace; not source-verified (honest gap)",
        "client_budget": {"source": "otel_client.py", "value_s": 12.0},
        "note": "10s DEADLINE_EXCEEDED observed; contract status unknown pending source check",
    },
    "OTel-checkout->email": {
        "contract": "unknown",
        "evidence": "OTel demo source not in workspace; not source-verified (honest gap)",
        "client_budget": {"source": "otel_client.py", "value_s": 12.0},
        "note": "email delay -> 4.9-5.3s, loss -> 10s hang; contract status unknown",
    },
    "TT-basic->station": {
        "contract": "no_timeout",
        "evidence": "ts-basic-service application.yml: no timeout config; single synchronous call",
        "client_budget": {"source": "run_chaos_experiment --request-timeout", "value_s": 5.0},
        "note": "no system timeout; 500ms/100ms delay -> 1:1 response (no amplification) is NOT contract-protected, it is below-threshold behavior",
    },
    "TT-client->station": {
        "contract": "no_timeout",
        "evidence": "ts-station-service application.yml: no timeout config",
        "client_budget": {"source": "run_chaos_experiment --request-timeout", "value_s": 5.0},
        "note": "2000ms injection -> 4017ms response with HTTP 200: no system contract violated, but no protection either (potential risk, JE-CONTRACT-002)",
    },
    "TT-client->order": {
        "contract": "no_timeout",
        "evidence": "ts-order-service application.yml: no timeout config",
        "client_budget": {"source": "run_chaos_experiment --request-timeout", "value_s": 8.0},
        "note": "order query delay -> ~4s response, no system timeout",
    },
}

# Runner parameter to candidate edges (provenance only).
CANDIDATE_TO_EDGE: dict[str, str] = {
    "OB-PAYMENT-DELAY-2000": "OB-checkout->payment",
    "OB-PAYMENT-LOSS-100": "OB-checkout->payment",
    "OB-CART-DELAY-2000": "OB-checkout->cart",
    "OB-PRODUCTCATALOG-DELAY-500": "OB-checkout->productcatalog",
    "OB-PRODUCTCATALOG-KILL": "OB-checkout->productcatalog",
    "OB-FRONTEND-ADSERVICE-DELAY-2000": "OB-frontend->adservice",
    "OB-FRONTEND-ADSERVICE-DELAY-500": "OB-frontend->adservice",
    "OB-FRONTEND-ADSERVICE-LOSS-100": "OB-frontend->adservice",
    "OTEL-PAYMENT-DELAY-2000": "OTel-checkout->payment",
    "OTEL-PAYMENT-LOSS-100": "OTel-checkout->payment",
    "OTEL-EMAIL-DELAY-2000": "OTel-checkout->email",
    "OTEL-EMAIL-LOSS-100": "OTel-checkout->email",
    "TT-STATION-DELAY-100": "TT-client->station",
    "TT-STATION-DELAY-2000": "TT-client->station",
    "TT-STATION-DELAY-500": "TT-client->station",
    "TT-BASIC-DELAY-100": "TT-basic->station",
    "TT-BASIC-DELAY-500": "TT-basic->station",
    "TT-ORDER-DELAY-2000": "TT-client->order",
}


def contract_for_candidate(candidate_id: str) -> dict[str, Any] | None:
    edge = CANDIDATE_TO_EDGE.get(candidate_id)
    if not edge:
        return None
    contract = CONTRACTS.get(edge)
    if not contract:
        return None
    return {"candidate_id": candidate_id, "edge": edge, **contract}


def build() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "tool": "contract_inventory",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "principle": (
            "Runner/request timeouts are the TEST CLIENT's budget, never a "
            "system contract. Only source/config-declared deadlines count for "
            "contract-violation judgment (A2 audit). 'unknown' means source not checked."
        ),
        "contracts": CONTRACTS,
        "candidate_map": CANDIDATE_TO_EDGE,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=INVENTORY_PATH)
    parser.add_argument("--show", type=str, help="candidate id to show contract for")
    args = parser.parse_args()
    if args.show:
        print(json.dumps(contract_for_candidate(args.show), indent=2, ensure_ascii=True))
        return 0
    doc = build()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(doc, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "edges": len(CONTRACTS)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
