"""Extended candidate pool for sparse-ground-truth comparison.

20 candidates = the 12 core candidates (with executed conclusions) plus 8 new,
concrete, executable delay mutations that have NOT been executed. The new
candidates carry no static graph/local/yaml scores (score 0), so score-driven
methods (M3/M4/A0-A4) cannot rank them ahead of the scored candidates — this
makes their "invisibility" to unknown candidates an explicit, auditable
property of the comparison rather than an accident of the pool design.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from generate_deep_comparison_matrix import CORE_CANDIDATES

ROOT = Path(__file__).resolve().parents[1]
EXT_MUTATIONS_DIR = ROOT / "artifacts" / "experiments" / "execution" / "mutations_extended"

EXTENDED_CANDIDATES: list[dict[str, Any]] = [
    {
        "candidate_id": "OB-CHECKOUT-DELAY-2000",
        "project_id": "online-boutique",
        "workload_id": "place-order",
        "service": "checkoutservice",
        "edge": "checkout->payment/shipping",
        "fault_family": "latency",
        "intensity": "2000ms",
        "duration": "15s",
        "mutation": "artifacts/experiments/execution/mutations_extended/ob-checkout-delay-one.yaml",
        "preclassified": None,
        "scores": {"graph": 0, "local": 0, "yaml": 0},
        "invariant": "checkout workflow stays within its deadline under delay",
        "root_cause": "unbounded latency propagation inside checkout workflow",
    },
    {
        "candidate_id": "OB-SHIPPING-DELAY-2000",
        "project_id": "online-boutique",
        "workload_id": "place-order",
        "service": "shippingservice",
        "edge": "checkout->shipping",
        "fault_family": "latency",
        "intensity": "2000ms",
        "duration": "15s",
        "mutation": "artifacts/experiments/execution/mutations_extended/ob-shipping-delay-one.yaml",
        "preclassified": None,
        "scores": {"graph": 0, "local": 0, "yaml": 0},
        "invariant": "shipping quote remains bounded without blocking checkout",
        "root_cause": "shipping latency propagates to the order path",
    },
    {
        "candidate_id": "OB-CART-DELAY-2000",
        "project_id": "online-boutique",
        "workload_id": "place-order",
        "service": "cartservice",
        "edge": "checkout->cart",
        "fault_family": "latency",
        "intensity": "2000ms",
        "duration": "15s",
        "mutation": "artifacts/experiments/execution/mutations_extended/ob-cart-delay-one.yaml",
        "preclassified": None,
        "scores": {"graph": 0, "local": 0, "yaml": 0},
        "invariant": "cart access remains bounded during checkout",
        "root_cause": "cart latency propagates into the checkout flow",
    },
    {
        "candidate_id": "OTEL-CHECKOUT-DELAY-2000",
        "project_id": "otel-demo",
        "workload_id": "place-order",
        "service": "checkout",
        "edge": "client->checkout",
        "fault_family": "latency",
        "intensity": "2000ms",
        "duration": "15s",
        "mutation": "artifacts/experiments/execution/mutations_extended/otel-checkout-delay-one.yaml",
        "preclassified": None,
        "scores": {"graph": 0, "local": 0, "yaml": 0},
        "invariant": "OTel checkout stays within its payment deadline",
        "root_cause": "checkout-side latency blocks the whole order workflow",
    },
    {
        "candidate_id": "OTEL-CURRENCY-DELAY-2000",
        "project_id": "otel-demo",
        "workload_id": "place-order",
        "service": "currency",
        "edge": "checkout->currency",
        "fault_family": "latency",
        "intensity": "2000ms",
        "duration": "15s",
        "mutation": "artifacts/experiments/execution/mutations_extended/otel-currency-delay-one.yaml",
        "preclassified": None,
        "scores": {"graph": 0, "local": 0, "yaml": 0},
        "invariant": "currency conversion remains bounded without stalling checkout",
        "root_cause": "currency latency propagates through the checkout flow",
    },
    {
        "candidate_id": "TT-ORDER-DELAY-2000",
        "project_id": "train-ticket",
        "workload_id": "order-query",
        "service": "ts-order-service",
        "edge": "client->order",
        "fault_family": "latency",
        "intensity": "2000ms",
        "duration": "20s",
        "mutation": "artifacts/experiments/execution/mutations_extended/tt-order-delay-one.yaml",
        "preclassified": None,
        "scores": {"graph": 0, "local": 0, "yaml": 0},
        "invariant": "order query stays within its registered deadline",
        "root_cause": "order-service latency without bounded fallback",
    },
    {
        "candidate_id": "TT-BASIC-DELAY-500",
        "project_id": "train-ticket",
        "workload_id": "basic-to-station",
        "service": "ts-basic-service",
        "edge": "basic->station",
        "fault_family": "latency",
        "intensity": "500ms",
        "duration": "20s",
        "mutation": "artifacts/experiments/execution/mutations_extended/tt-basic-delay-500-one.yaml",
        "preclassified": None,
        "scores": {"graph": 0, "local": 0, "yaml": 0},
        "invariant": "basic query remains successful within the client deadline",
        "root_cause": "downstream latency propagates without a bounded fallback",
    },
    {
        "candidate_id": "TT-STATION-DELAY-500",
        "project_id": "train-ticket",
        "workload_id": "station-lookup",
        "service": "ts-station-service",
        "edge": "client->station",
        "fault_family": "latency",
        "intensity": "500ms",
        "duration": "20s",
        "mutation": "artifacts/experiments/execution/mutations_extended/tt-station-delay-500-one.yaml",
        "preclassified": None,
        "scores": {"graph": 0, "local": 0, "yaml": 0},
        "invariant": "station lookup preserves its response contract under delay",
        "root_cause": "station latency without bounded timeout at the boundary",
    },
]


def extended_candidate_pool() -> list[dict[str, Any]]:
    return [dict(item) for item in CORE_CANDIDATES] + [dict(item) for item in EXTENDED_CANDIDATES]
