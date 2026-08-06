#!/usr/bin/env python3
"""Probe-restart escape verification: re-inject after restart.

Flow:
1. apply payment 2s delay (60s) -> wait AllInjected -> sample (expect ~2020ms)
2. wait for probe restart (restarts increments) -> wait new container Ready
3. sample (expect ~17ms: escaped injection)
4. delete chaos, re-apply same manifest (now targets NEW container)
5. wait AllInjected -> sample (expect ~2020ms again: injection works, system has no self-healing)
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


def payment_ready(timeout=120):
    t0 = time.time()
    while time.time() - t0 < timeout:
        rc, out, _ = run(["kubectl", "get", "pods", "-n", NS, "-l", "app=paymentservice",
                          "-o", "jsonpath={.items[0].status.containerStatuses[0].restartCount}"])
        if out.strip():
            return True
        time.sleep(5)
    return False


def all_injected(name, timeout=40):
    t0 = time.time()
    while time.time() - t0 < timeout:
        _, out, _ = run(["kubectl", "get", "networkchaos", name, "-n", NS,
                         "-o", "jsonpath={.status.conditions[?(@.type==\"AllInjected\")].status}"])
        if out.strip() == "True":
            return True
        time.sleep(2)
    return False


def sample(label):
    r = subprocess.run([sys.executable, CLIENT, CHECKOUT, CART, "1"],
                       capture_output=True, text=True, timeout=45)
    line = (r.stdout or "").strip().splitlines()[-1] if r.stdout else "no-output"
    m = re.search(r"\(([\d.]+)ms\)", line)
    lat = float(m.group(1)) if m else None
    out = "ok" if "ok oid" in line else ("rpc_error" if "rpc_error" in line else line)
    rest = payment_restarts()
    print(f"{label}: {lat}ms ({out}) restarts={rest}")
    return {"label": label, "latency_ms": lat, "outcome": out, "restarts": rest}


def main():
    result = []
    if not payment_ready():
        print("payment not ready"); return 1
    rest0 = payment_restarts()
    print(f"initial restarts={rest0}")

    # step 1: inject
    subprocess.run(["kubectl", "apply", "-f", MANIFEST], capture_output=True, text=True)
    if not all_injected("ob-payment-delay-ladder-2000"):
        print("not injected"); return 1
    result.append(sample("step1_injected"))

    # step 2: wait for probe restart
    t0 = time.time()
    while time.time() - t0 < 90:
        if payment_restarts() > rest0:
            print(f"  probe restart detected at t={time.time()-t0:.0f}s")
            break
        time.sleep(3)
    # wait new container ready (restart count stable for a while)
    time.sleep(20)
    result.append(sample("step2_after_restart"))

    # step 3: delete and re-inject
    subprocess.run(["kubectl", "delete", "-f", MANIFEST], capture_output=True, text=True)
    time.sleep(5)
    subprocess.run(["kubectl", "apply", "-f", MANIFEST], capture_output=True, text=True)
    if not all_injected("ob-payment-delay-ladder-2000"):
        print("re-inject not applied"); return 1
    result.append(sample("step3_reinjected"))

    # cleanup
    subprocess.run(["kubectl", "delete", "-f", MANIFEST], capture_output=True, text=True)
    time.sleep(3)
    with open(r"C:\APP\project\chaos\artifacts\online-boutique\reject_escape_result.json", "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    print(json.dumps(result, indent=2))
    print("saved: reject_escape_result.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
