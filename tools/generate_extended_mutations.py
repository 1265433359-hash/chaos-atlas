"""Generate extended candidate mutations for the sparse-ground-truth comparison.

Adds 8 concrete, executable NetworkChaos delay mutations to the shared pool
(12 core candidates -> 20), one per target service/edge. Each file follows the
existing `ob-productcatalog-delay-one.yaml` template (mode: one, direction: to,
bounded duration). The extended candidates are deliberately NOT executed yet:
they enlarge the candidate universe so known-positive density drops from 12/12
to 12/20, pushing the random baseline below its ceiling.
"""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "artifacts" / "experiments" / "execution" / "mutations_extended"

EXTENDED_MUTATIONS: list[dict[str, object]] = [
    {
        "file": "ob-checkout-delay-one.yaml",
        "candidate_id": "OB-CHECKOUT-DELAY-2000",
        "namespace": "online-boutique-lab",
        "app": "checkoutservice",
        "latency": "2000ms",
        "duration": "15s",
    },
    {
        "file": "ob-shipping-delay-one.yaml",
        "candidate_id": "OB-SHIPPING-DELAY-2000",
        "namespace": "online-boutique-lab",
        "app": "shippingservice",
        "latency": "2000ms",
        "duration": "15s",
    },
    {
        "file": "ob-cart-delay-one.yaml",
        "candidate_id": "OB-CART-DELAY-2000",
        "namespace": "online-boutique-lab",
        "app": "cartservice",
        "latency": "2000ms",
        "duration": "15s",
    },
    {
        "file": "otel-checkout-delay-one.yaml",
        "candidate_id": "OTEL-CHECKOUT-DELAY-2000",
        "namespace": "otel-demo-lab",
        "app": "checkout",
        "latency": "2000ms",
        "duration": "15s",
    },
    {
        "file": "otel-currency-delay-one.yaml",
        "candidate_id": "OTEL-CURRENCY-DELAY-2000",
        "namespace": "otel-demo-lab",
        "app": "currency",
        "latency": "2000ms",
        "duration": "15s",
    },
    {
        "file": "tt-order-delay-one.yaml",
        "candidate_id": "TT-ORDER-DELAY-2000",
        "namespace": "train-ticket-lab",
        "app": "ts-order-service",
        "latency": "2000ms",
        "duration": "20s",
    },
    {
        "file": "tt-basic-delay-500-one.yaml",
        "candidate_id": "TT-BASIC-DELAY-500",
        "namespace": "train-ticket-lab",
        "app": "ts-basic-service",
        "latency": "500ms",
        "duration": "20s",
    },
    {
        "file": "tt-station-delay-500-one.yaml",
        "candidate_id": "TT-STATION-DELAY-500",
        "namespace": "train-ticket-lab",
        "app": "ts-station-service",
        "latency": "500ms",
        "duration": "20s",
    },
]


def render(item: dict[str, object]) -> str:
    body = {
        "apiVersion": "chaos-mesh.org/v1alpha1",
        "kind": "NetworkChaos",
        "metadata": {
            "name": str(item["file"]).replace(".yaml", ""),
            "namespace": item["namespace"],
            "labels": {"chaos.extended": "candidate", "chaos.candidate-id": item["candidate_id"]},
        },
        "spec": {
            "action": "delay",
            "mode": "one",
            "selector": {
                "namespaces": [item["namespace"]],
                "labelSelectors": {"app": item["app"]},
            },
            "delay": {"latency": item["latency"], "correlation": "100", "jitter": "0ms"},
            "duration": item["duration"],
            "direction": "to",
        },
    }
    return yaml.safe_dump(body, sort_keys=False)


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for item in EXTENDED_MUTATIONS:
        path = OUTPUT_DIR / str(item["file"])
        path.write_text(render(item), encoding="utf-8", newline="\n")
        print(f"wrote {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
