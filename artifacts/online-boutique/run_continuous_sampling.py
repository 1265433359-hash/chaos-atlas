#!/usr/bin/env python3
"""Continuous sampling inside one 60s injection window (payment 2s delay).

Samples PlaceOrder every 3s, recording latency/outcome and payment pod
restart count, to capture the full dynamic: latency propagation -> probe
restart (connection refused) -> recovery -> re-injection.  Client deadline
reduced to 8s so the script keeps cadence even when the call hangs.
"""
import json
import re
import subprocess
import sys
import time

NS = "online-boutique-lab"
CLIENT = r"C:\APP\project\chaos\artifacts\online-boutique\ob_client.py"
CHECKOUT = "localhost:35050"
CART = "localhost:37070"
MANIFEST = r"C:\APP\project\chaos\artifacts\online-boutique\chaos\payment-delay-2000.yaml"

# use client deadline 8s (override via env) to keep sampling cadence
import os
os.environ["OB_CLIENT_DEADLINE"] = "8"


def run(cmd, timeout=60):
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return r.returncode, r.stdout, r.stderr


def payment_restarts():
    _, out, _ = run(["kubectl", "get", "pods", "-n", NS, "-l", "app=paymentservice",
                     "-o", "jsonpath={.items[0].status.containerStatuses[0].restartCount}"])
    try:
        return int(out.strip())
    except ValueError:
        return None


def sample():
    r = subprocess.run([sys.executable, CLIENT, CHECKOUT, CART, "1"],
                       capture_output=True, text=True, timeout=45)
    line = (r.stdout or "").strip().splitlines()[-1] if r.stdout else "no-output"
    m = re.search(r"\(([\d.]+)ms\)", line)
    lat = float(m.group(1)) if m else None
    outcome = ("ok" if "ok oid" in line else
               "rpc_error" if "rpc_error" in line else
               "deadline" if "DEADLINE" in line.upper() else line)
    return lat, outcome


def main():
    # baseline snapshot
    b_lat, b_out = sample()
    b_rest = payment_restarts()
    print(f"t=-5s baseline: {b_lat}ms ({b_out}) restarts={b_rest}")

    subprocess.run(["kubectl", "apply", "-f", MANIFEST], capture_output=True, text=True)
    # wait injected
    t0 = time.time()
    while time.time() - t0 < 40:
        _, out, _ = run(["kubectl", "get", "networkchaos", "ob-payment-delay-ladder-2000",
                         "-n", NS, "-o", "jsonpath={.status.conditions[?(@.type==\"AllInjected\")].status}"])
        if out.strip() == "True":
            break
        time.sleep(2)

    print("t=0s injection applied")
    samples = []
    t = 0
    while t < 75:  # 60s window + margin
        lat, outcome = sample()
        rest = payment_restarts()
        samples.append({"t_s": t, "latency_ms": lat, "outcome": outcome, "restarts": rest})
        print(f"t={t:3d}s  {str(lat):>10}ms  {outcome:16s}  restarts={rest}")
        time.sleep(3)
        t += 3

    # post window
    time.sleep(10)
    lat, outcome = sample()
    rest = payment_restarts()
    samples.append({"t_s": 85, "latency_ms": lat, "outcome": outcome, "restarts": rest})
    print(f"t={85:3d}s  {str(lat):>10}ms  {outcome:16s}  restarts={rest}")

    result = {"samples": samples, "baseline": {"latency_ms": b_lat, "outcome": b_out, "restarts": b_rest}}
    with open(r"C:\APP\project\chaos\artifacts\online-boutique\continuous_sampling_result.json", "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    print("saved: continuous_sampling_result.json")


if __name__ == "__main__":
    main()
