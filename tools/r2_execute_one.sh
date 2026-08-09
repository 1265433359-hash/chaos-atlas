#!/usr/bin/env bash
# r2 unified execution (port-forward variant): baseline -> inject -> workload ->
# recover -> cleanup for ONE candidate. Reuses the verified ob_client gRPC
# path through port-forward (same as run_grpc_chaos_experiment) but does NOT
# depend on the gate's hardcoded chaos-testing namespace.
#
# Usage (inside WSL, KUBECONFIG set):
#   r2_execute_one.sh <candidate_id> <app-label> <mutation.yaml> <out.json>
#   e.g.
#   r2_execute_one.sh OB-CURRENCY-LOSS-100 currencyservice \
#     /mnt/c/APP/project/chaos/artifacts/experiments/execution/remediation/r2_mutations/ob-currency-loss-one.yaml \
#     /mnt/c/APP/project/chaos/artifacts/experiments/execution/remediation/r2_runs/OB-CURRENCY-LOSS-100.json

set -u
CID="${1:?candidate id}"
APP="${2:?app label}"
MUT="${3:?mutation yaml}"
OUT="${4:?output json}"
NS="online-boutique-lab"
CHECKOUT_SVC="checkoutservice"
CART_SVC="cartservice"
CLIENT="/mnt/c/APP/project/chaos/artifacts/online-boutique/ob_client.py"
WORK=$(mktemp -d)

log(){ echo "[$(date +%H:%M:%S)] $*"; }

# port-forward helper (PIDs)
kubectl port-forward -n "$NS" "svc/$CHECKOUT_SVC" 15050:5050 >/dev/null 2>&1 &
PF1=$!
kubectl port-forward -n "$NS" "svc/$CART_SVC" 17070:7070 >/dev/null 2>&1 &
PF2=$!
sleep 3

cleanup_pf(){ kill "$PF1" "$PF2" 2>/dev/null; wait "$PF1" "$PF2" 2>/dev/null; }
trap cleanup_pf EXIT

run_client(){
  # $1 count; $2 timeout
  cd /mnt/c/APP/project/chaos/tools && python3 - "$CLIENT" "$1" "$2" <<'PYEOF'
import json, subprocess, sys
client, count, tmo = sys.argv[1], int(sys.argv[2]), float(sys.argv[3])
r = subprocess.run(["python3", client, "127.0.0.1:15050", "127.0.0.1:17070", str(count)],
                   capture_output=True, text=True, timeout=tmo+10)
obs = []
for line in (r.stdout or "").splitlines():
    if line.startswith("["):
        idx, rest = line[1:].split("]", 1)
        rest = rest.strip()
        if rest.startswith("ok oid="):
            parts = rest.split()
            lat = None
            for p in parts:
                if p.endswith("ms)"):
                    lat = float(p.rstrip("ms)").lstrip("("))
            obs.append({"grpc_status": "OK", "latency_ms": lat, "result": rest})
        else:
            obs.append({"grpc_status": "ERROR", "error": rest[:120], "result": rest[:120]})
print(json.dumps({"return_code": r.returncode, "elapsed_ms": None, "observations": obs,
                  "stdout": (r.stdout or "")[:300], "stderr": (r.stderr or "")[:200]}))
PYEOF
}

# --- baseline ---
log "baseline: 3 calls"
BASE=$(run_client 3 12.0)

# --- inject ---
log "apply $MUT"
kubectl apply -f "$MUT" 2>&1 | tail -1
sleep 4

# verify injected via chaos status
INJ_STATUS=$(kubectl get networkchaos "$(basename "$MUT" .yaml)" -n "$NS" -o jsonpath='{.status.conditions[?(@.type=="AllInjected")].status}' 2>/dev/null)
log "injected status: ${INJ_STATUS:-unknown}"

# --- workload under injection ---
log "workload: 3 calls"
WORKLOAD=$(run_client 3 15.0)

# --- recovery wait ---
log "wait recovery"
sleep 5

# --- cleanup (absence-confirmed) ---
NAME=$(basename "$MUT" .yaml)
kubectl delete networkchaos "$NAME" -n "$NS" --ignore-not-found=true >/dev/null 2>&1
sleep 3
VERIFY=$(kubectl get networkchaos "$NAME" -n "$NS" 2>&1)
if echo "$VERIFY" | grep -q "not found"; then CLEAN="absent"; else CLEAN="still-present"; fi
log "cleanup: $CLEAN"

cleanup_pf
trap - EXIT

# --- aggregate ---
python3 - "$CID" "$APP" "$BASE" "$WORKLOAD" "$CLEAN" "$INJ_STATUS" "$OUT" <<'PYEOF'
import json, sys, time
cid, app, base_s, work_s, clean, inj, out = sys.argv[1:8]
base = json.loads(base_s) if base_s.strip() else {}
work = json.loads(work_s) if work_s.strip() else {}
def summary(d):
    obs = d.get("observations") or []
    ok = [o for o in obs if o.get("grpc_status") == "OK"]
    err = [o for o in obs if o.get("grpc_status") == "ERROR"]
    lats = [o.get("latency_ms") for o in ok if o.get("latency_ms")]
    stderr = (d.get("stderr") or "")
    return {
        "samples": len(obs),
        "ok_count": len(ok),
        "error_count": len(err),
        "errors": [e.get("error", "")[:80] for e in err][:5],
        "median_latency_ms": round(sorted(lats)[len(lats)//2], 1) if lats else None,
        "max_latency_ms": max(lats) if lats else None,
        "client_return_code": d.get("return_code"),
        "client_stderr_hint": (stderr[:120] if stderr else None),
        "client_hung": len(obs) == 0 and d.get("return_code") != 0,
    }
report = {
    "candidate_id": cid,
    "app": app,
    "tool": "r2_execute_one",
    "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "mutation": f"remediation/r2_mutations/{cid.lower()}-{app}.yaml",
    "injection_status": inj or "unknown",
    "baseline": summary(base),
    "workload": summary(work),
    "cleanup": clean,
    "cleanup_absent_confirmed": clean == "absent",
    "result_classification": "TBD_BLIND",
}
json.dump(report, open(out, "w"), indent=2, ensure_ascii=False)
print(json.dumps({"baseline": report["baseline"], "workload": report["workload"], "injected": report["injection_status"], "cleanup": clean}, indent=2))
PYEOF
rm -rf "$WORK"
log "done -> $OUT"
