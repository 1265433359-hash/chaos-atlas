#!/usr/bin/env python3
"""Loss statistical repetition: checkout->payment 100% loss, 5 independent windows.

Each window: apply loss chaos -> wait AllInjected -> sample PlaceOrder (records
hang time until client deadline 10s) -> wait window end -> delete -> recover.
Loss does NOT trigger probe restart (verified in experiment 3), so windows can
run back-to-back.  Outputs hang times to show "infinite hang until client
deadline" is a statistical fact, not a one-off.
"""
import json
import re
import statistics
import subprocess
import sys
import time

NS = "online-boutique-lab"
CLIENT = r"C:\APP\project\chaos\artifacts\online-boutique\ob_client.py"
CHECKOUT = "localhost:35050"
CART = "localhost:37070"
MANIFEST = r"C:\APP\project\chaos\artifacts\online-boutique\chaos\payment-loss-stat.yaml"

CHAOS_YAML = """apiVersion: chaos-mesh.org/v1alpha1
kind: NetworkChaos
metadata:
  name: ob-payment-loss-stat
  namespace: online-boutique-lab
spec:
  action: loss
  mode: all
  selector:
    namespaces:
      - online-boutique-lab
    labelSelectors:
      app: paymentservice
  loss:
    loss: "100"
    correlation: "100"
  duration: "25s"
  direction: to
"""


def run(cmd, timeout=60):
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return r.returncode, r.stdout, r.stderr


def all_injected(name, timeout=40):
    t0 = time.time()
    while time.time() - t0 < timeout:
        _, out, _ = run(["kubectl", "get", "networkchaos", name, "-n", NS,
                         "-o", "jsonpath={.status.conditions[?(@.type==\"AllInjected\")].status}"])
        if out.strip() == "True":
            return True
        time.sleep(2)
    return False


def sample():
    """PlaceOrder with client deadline 10s; returns (latency_or_none, outcome)."""
    r = subprocess.run([sys.executable, CLIENT, CHECKOUT, CART, "1"],
                       capture_output=True, text=True, timeout=60)
    line = (r.stdout or "").strip().splitlines()[-1] if r.stdout else "no-output"
    m = re.search(r"\(([\d.]+)ms\)", line)
    lat = float(m.group(1)) if m else None
    outcome = ("ok" if "ok oid" in line else
               "rpc_error" if "rpc_error" in line else
               "deadline" if "DEADLINE" in line.upper() else line)
    return lat, outcome


def main():
    # baseline
    print("=== BASELINE (3 orders) ===")
    base = []
    for i in range(3):
        lat, out = sample()
        base.append(lat)
        print(f"  base[{i}] {lat}ms ({out})")
        time.sleep(0.5)

    with open(MANIFEST, "w", encoding="utf-8") as f:
        f.write(CHAOS_YAML)

    print("\n=== LOSS INJECTED (5 windows, 100% loss) ===")
    hangs = []
    outcomes = []
    for i in range(5):
        subprocess.run(["kubectl", "apply", "-f", MANIFEST], capture_output=True, text=True, timeout=60)
        if not all_injected("ob-payment-loss-stat"):
            print(f"  win[{i}] NOT injected")
            subprocess.run(["kubectl", "delete", "-f", MANIFEST], capture_output=True, text=True, timeout=60)
            time.sleep(5)
            continue
        lat, out = sample()
        hangs.append(lat)
        outcomes.append(out)
        print(f"  win[{i}] hang={lat}ms outcome={out}")
        time.sleep(27)  # window end
        subprocess.run(["kubectl", "delete", "-f", MANIFEST], capture_output=True, text=True, timeout=60)
        time.sleep(6)

    # post-recovery check
    print("\n=== RECOVERY (3 orders) ===")
    rec = []
    for i in range(3):
        lat, out = sample()
        rec.append(lat)
        print(f"  rec[{i}] {lat}ms ({out})")
        time.sleep(0.5)

    result = {
        "baseline": base,
        "hang_times_ms": hangs,
        "outcomes": outcomes,
        "recovery": rec,
        "hang_stats": {
            "n": len(hangs),
            "median_ms": round(statistics.median([h for h in hangs if h is not None]), 1) if hangs else None,
            "min_ms": min([h for h in hangs if h is not None]) if hangs else None,
            "max_ms": max([h for h in hangs if h is not None]) if hangs else None,
        },
    }
    print("\n=== RESULT ===")
    print(json.dumps(result, indent=2))
    with open(r"C:\APP\project\chaos\artifacts\online-boutique\loss_stat_result.json", "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    print("saved: loss_stat_result.json")


if __name__ == "__main__":
    main()
