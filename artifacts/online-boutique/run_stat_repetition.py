#!/usr/bin/env python3
"""Statistical repetition: payment 2s delay NetworkChaos, 10 independent windows.

Each sample uses its own short injection window (20s) to avoid the probe-SIGKILL
restart (which would mix "injected latency" with "pod restarting") — sample once
right after AllInjected, then wait for window end, delete, and wait for recovery.
Outputs baseline and injected latency arrays with median/p95/mean/std.
"""
import json
import statistics
import subprocess
import sys
import time

NS = "online-boutique-lab"
CHAOS = "ob-payment-delay-stat"
MANIFEST = r"C:\APP\project\chaos\artifacts\online-boutique\chaos\payment-delay-stat.yaml"
CLIENT = r"C:\APP\project\chaos\artifacts\online-boutique\ob_client.py"
CHECKOUT = "localhost:35050"
CART = "localhost:37070"

CHAOS_YAML = """apiVersion: chaos-mesh.org/v1alpha1
kind: NetworkChaos
metadata:
  name: ob-payment-delay-stat
  namespace: online-boutique-lab
spec:
  action: delay
  mode: all
  selector:
    namespaces:
      - online-boutique-lab
    labelSelectors:
      app: paymentservice
  delay:
    latency: "2000ms"
    correlation: "100"
    jitter: "0ms"
  duration: "20s"
  direction: to
"""


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    return r.returncode, r.stdout, r.stderr


def place_order():
    """Return (latency_ms, outcome) for one PlaceOrder via ob_client."""
    r = subprocess.run(
        [sys.executable, CLIENT, CHECKOUT, CART, "1"],
        capture_output=True, text=True, timeout=60,
    )
    line = (r.stdout or "").strip().splitlines()[-1] if r.stdout else "no-output"
    # format: [0] ok oid=... tracking=... (1234.5ms)  or  [0] rpc_error ... (1234.5ms)
    import re
    m = re.search(r"\(([\d.]+)ms\)", line)
    lat = float(m.group(1)) if m else None
    outcome = "ok" if "ok oid" in line else ("error" if "rpc_error" in line else line)
    return lat, outcome


def wait_all_injected(timeout=40):
    t0 = time.time()
    while time.time() - t0 < timeout:
        r = subprocess.run(
            ["kubectl", "get", "networkchaos", CHAOS, "-n", NS,
             "-o", "jsonpath={.status.conditions[?(@.type==\"AllInjected\")].status}"],
            capture_output=True, text=True, timeout=30,
        )
        if r.stdout.strip() == "True":
            return True
        time.sleep(2)
    return False


def wait_payment_ready(timeout=120):
    t0 = time.time()
    while time.time() - t0 < timeout:
        r = subprocess.run(
            ["kubectl", "get", "pods", "-n", NS, "-l", "app=paymentservice",
             "-o", "jsonpath={.items[0].status.conditions[?(@.type==\"Ready\")].status}"],
            capture_output=True, text=True, timeout=30,
        )
        if r.stdout.strip() == "True":
            return True
        time.sleep(5)
    return False


def main():
    # --- baseline: 10 sequential orders, no injection ---
    print("=== BASELINE (10 orders, no injection) ===")
    baseline = []
    for i in range(10):
        lat, out = place_order()
        baseline.append(lat)
        print(f"  base[{i}] {lat}ms ({out})")
        time.sleep(0.5)

    # --- write chaos manifest ---
    with open(MANIFEST, "w", encoding="utf-8") as f:
        f.write(CHAOS_YAML)

    print("\n=== INJECTED (10 independent 20s windows, 2000ms delay) ===")
    injected = []
    for i in range(10):
        # wait payment ready from previous round
        if not wait_payment_ready():
            print(f"  round[{i}] payment not ready, skipping")
            injected.append(None)
            continue
        subprocess.run(["kubectl", "apply", "-f", MANIFEST], capture_output=True, text=True, timeout=60)
        if not wait_all_injected():
            print(f"  round[{i}] not injected")
            injected.append(None)
            subprocess.run(["kubectl", "delete", "-f", MANIFEST], capture_output=True, text=True, timeout=60)
            time.sleep(5)
            continue
        lat, out = place_order()  # sample during stable injection
        injected.append(lat)
        print(f"  inj[{i}] {lat}ms ({out})")
        # wait window end (20s duration), then delete
        time.sleep(22)
        subprocess.run(["kubectl", "delete", "-f", MANIFEST], capture_output=True, text=True, timeout=60)
        time.sleep(5)
        if not wait_payment_ready():
            print(f"  round[{i}] recovery slow")
        else:
            print(f"  round[{i}] recovered")
        time.sleep(2)

    # --- statistics ---
    def stats(arr):
        vals = [v for v in arr if v is not None]
        if not vals:
            return None
        vals_sorted = sorted(vals)
        n = len(vals_sorted)
        median = statistics.median(vals_sorted)
        p95 = vals_sorted[int(n * 0.95) - 1] if n > 1 else vals_sorted[-1]
        mean = statistics.mean(vals_sorted)
        std = statistics.stdev(vals_sorted) if n > 1 else 0.0
        return {"n": n, "median_ms": round(median, 1), "p95_ms": round(p95, 1),
                "mean_ms": round(mean, 1), "std_ms": round(std, 1)}

    result = {
        "baseline": baseline,
        "injected": injected,
        "baseline_stats": stats(baseline),
        "injected_stats": stats(injected),
    }
    print("\n=== RESULT ===")
    print(json.dumps(result, indent=2))
    with open(r"C:\APP\project\chaos\artifacts\online-boutique\stat_repetition_result.json", "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    print("saved: artifacts/online-boutique/stat_repetition_result.json")


if __name__ == "__main__":
    main()
