#!/usr/bin/env python3
"""Timeout boundary ladder: payment delay 1s/2s/3s/5s.

For each level: apply chaos -> wait AllInjected -> sample PlaceOrder -> wait
window end -> delete -> wait payment Ready.  Records outcome (ok with latency /
rpc_error / deadline), probe restart events, and whether the client timed out.
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
CHAOS_DIR = r"C:\APP\project\chaos\artifacts\online-boutique\chaos"

LEVELS = [
    ("1000", "1000ms"),
    ("2000", "2000ms"),
    ("3000", "3000ms"),
    ("5000", "5000ms"),
]


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


def payment_ready(timeout=120):
    t0 = time.time()
    while time.time() - t0 < timeout:
        _, out, _ = run(["kubectl", "get", "pods", "-n", NS, "-l", "app=paymentservice",
                         "-o", "jsonpath={.items[0].status.containerStatuses[0].restartCount}"])
        if out.strip():
            return True
        time.sleep(5)
    return False


def sample():
    r = subprocess.run([sys.executable, CLIENT, CHECKOUT, CART, "1"],
                       capture_output=True, text=True, timeout=60)
    line = (r.stdout or "").strip().splitlines()[-1] if r.stdout else "no-output"
    m = re.search(r"\(([\d.]+)ms\)", line)
    lat = float(m.group(1)) if m else None
    outcome = ("ok" if "ok oid" in line else
               "rpc_error" if "rpc_error" in line else "timeout" if "timed out" in line else line)
    return lat, outcome


def main():
    results = []
    for label, lat_ms in LEVELS:
        chaos_name = f"ob-payment-delay-ladder-{label}"
        manifest = f"{CHAOS_DIR}/payment-delay-{label}.yaml"
        print(f"\n=== LADDER {lat_ms} ===")
        if not payment_ready():
            print("  payment not ready, skip"); results.append({"level": lat_ms, "skip": True}); continue
        before_restart, _, _ = run(["kubectl", "get", "pods", "-n", NS, "-l", "app=paymentservice",
                                    "-o", "jsonpath={.items[0].status.containerStatuses[0].restartCount}"])
        subprocess.run(["kubectl", "apply", "-f", manifest], capture_output=True, text=True)
        if not all_injected(chaos_name):
            print("  NOT INJECTED"); subprocess.run(["kubectl", "delete", "-f", manifest], capture_output=True, text=True)
            results.append({"level": lat_ms, "injected": False}); time.sleep(5); continue
        lat, outcome = sample()
        after_restart, _, _ = run(["kubectl", "get", "pods", "-n", NS, "-l", "app=paymentservice",
                                   "-o", "jsonpath={.items[0].status.containerStatuses[0].restartCount}"])
        print(f"  PlaceOrder: {lat}ms ({outcome}) | restarts {before_restart}->{after_restart}")
        results.append({
            "level": lat_ms,
            "latency_ms": lat,
            "outcome": outcome,
            "probe_restart": before_restart != after_restart,
        })
        time.sleep(28)  # wait window end
        subprocess.run(["kubectl", "delete", "-f", manifest], capture_output=True, text=True)
        t0 = time.time()
        while time.time() - t0 < 120:
            rc, out, _ = run(["kubectl", "get", "pods", "-n", NS, "-l", "app=paymentservice",
                              "-o", "jsonpath={.items[0].status.containerStatuses[0].restartCount}"])
            if out.strip():
                break
            time.sleep(5)
        time.sleep(3)

    print("\n=== LADDER RESULT ===")
    print(json.dumps(results, indent=2))
    with open(r"C:\APP\project\chaos\artifacts\online-boutique\delay_ladder_result.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print("saved: delay_ladder_result.json")


if __name__ == "__main__":
    main()
