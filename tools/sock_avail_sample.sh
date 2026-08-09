#!/usr/bin/env bash
# Availability-track experiment runner: baseline -> PodChaos kill -> recovery curve.
#
# Dual-track method (availability_defense_design.md): same judgment template as
# the contract track, applied to the deployment-availability layer.
#   static evidence : manifest (replicas/pdb/probes) via contract_inventory
#   runtime evidence: per-500ms Ready-pod samples -> availability curve + recovery time
#
# Usage (inside WSL, KUBECONFIG set):
#   sock_avail_sample.sh <service-label> <baseline_s> <recovery_timeout_s> <out.json>
# Example:
#   sock_avail_sample.sh front-end 3 60 /mnt/c/APP/project/chaos/artifacts/sock-shop/avail_frontend_kill.json

set -u
SVC_LABEL="${1:?service label (deployment name)}"
BASE_S="${2:-3}"
RECOVER_TMO="${3:-90}"
OUT="${4:-/tmp/avail_out.json}"

NS="sock-shop-lab"
SAMPLE_MS=500
WORK=$(mktemp -d)
CURVE="$WORK/curve.tsv"     # epoch_ms<TAB>ready<TAB>phase
LOG="$WORK/events.log"

log(){ echo "[$(date +%H:%M:%S)] $*" | tee -a "$LOG"; }

sample_loop(){
  # $1 = stop file path; $2 = curve file
  while [ ! -f "$1" ]; do
    READY=$(kubectl get pod -n "$NS" -l name="$SVC_LABEL" --field-selector=status.phase=Running \
      -o jsonpath='{range .items[*]}{.status.containerStatuses[0].ready}{"\n"}{end}' 2>/dev/null \
      | grep -c "^true" || true)
    PHASE=$(kubectl get pod -n "$NS" -l name="$SVC_LABEL" -o jsonpath='{.items[0].status.phase}' 2>/dev/null || echo "None")
    echo -e "$(date +%s)\t${READY:-0}\t${PHASE:-None}" >> "$2"
    sleep 0.5
  done
}

start_pod_name(){ kubectl get pod -n "$NS" -l name="$SVC_LABEL" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null; }

STOP="$WORK/stop"
log "target=$SVC_LABEL baseline=${BASE_S}s sample=${SAMPLE_MS}ms"
log "baseline: $(start_pod_name) $(kubectl get pod -n "$NS" -l name="$SVC_LABEL" -o jsonpath='{.status.podIP}' 2>/dev/null)"

sample_loop "$STOP" "$CURVE" &
SAMPLER=$!
sleep "$BASE_S"

# --- inject: PodChaos kill ---
OLD_POD=$(start_pod_name)
CH_META=$(kubectl apply -f - <<EOF
apiVersion: chaos-mesh.org/v1alpha1
kind: PodChaos
metadata:
  name: avail-kill-$SVC_LABEL
  namespace: $NS
spec:
  action: pod-kill
  mode: one
  selector:
    namespaces: ['$NS']
    labelSelectors:
      name: $SVC_LABEL
  duration: '30s'
EOF
)
log "injected PodChaos kill on $OLD_POD"
log "$CH_META"

# --- wait for recovery (Ready count back to 1) ---
RECOVER_AT=""
for i in $(seq 1 $((RECOVER_TMO * 2))); do
  sleep 0.5
  CUR=$(kubectl get pod -n "$NS" -l name="$SVC_LABEL" --field-selector=status.phase=Running \
    -o jsonpath='{range .items[*]}{.status.containerStatuses[0].ready}{"\n"}{end}' 2>/dev/null \
    | grep -c "^true" || true)
  # new pod fully Ready -> recovered
  NEW_POD=$(kubectl get pod -n "$NS" -l name="$SVC_LABEL" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
  if [ "${CUR:-0}" -ge 1 ] && [ -n "$NEW_POD" ] && [ "$NEW_POD" != "$OLD_POD" ]; then
    RECOVER_AT="$(date +%s)"
    log "recovered: new pod $NEW_POD ready (ready_count=$CUR)"
    break
  fi
done

# stop sampler, collect tail curve
touch "$STOP"; wait "$SAMPLER" 2>/dev/null
kubectl delete podchaos avail-kill-$SVC_LABEL -n "$NS" 2>/dev/null
sleep 1

# --- summarize ---
python3 - "$CURVE" "$BASE_S" "$RECOVER_AT" "$OUT" "$OLD_POD" "$SVC_LABEL" <<'PYEOF'
import csv, json, sys, time
curve, base_s, recover_ms, out, old_pod, svc = sys.argv[1:7]
recover_ms = int(recover_ms) if recover_ms else None
rows = []
with open(curve) as f:
    for line in f:
        line = line.strip()
        if not line: continue
        p = line.split("\t")
        if len(p) < 3: continue
        rows.append({"t_ms": int(p[0]), "ready": int(p[1] or 0), "phase": p[2]})
if not rows:
    print(json.dumps({"error": "empty curve"})); sys.exit(1)
t0 = rows[0]["t_ms"]
curve = [{"rel_s": round(r["t_ms"]-t0, 2), "ready": r["ready"], "phase": r["phase"]} for r in rows]
baseline_samples = [r for r in curve if r["rel_s"] <= float(base_s) + 0.2]
outage = [r for r in curve if r["ready"] == 0]
outage_s = (outage[-1]["rel_s"] - outage[0]["rel_s"]) if len(outage) >= 2 else (0 if outage else None)
recovery_s = round(recover_ms - t0, 2) if recover_ms else None
min_avail = min((r["ready"] for r in curve), default=1)
max_avail = max((r["ready"] for r in curve), default=1)
result = {
  "track": "availability",
  "service": svc,
  "old_pod": old_pod,
  "injection": "PodChaos pod-kill (mode=one)",
  "baseline_s": float(base_s),
  "samples_total": len(curve),
  "min_ready": min_avail,
  "max_ready": max_avail,
  "outage_detected": min_avail == 0,
  "outage_window_s": outage_s,
  "recovered_s": recovery_s,
  "recovery_delta_from_kill_s": round(recovery_s - float(base_s), 2) if recovery_s else None,
  "verdict": "weakness (no redundancy: single replica, total outage on kill)" if min_avail == 0 else "defended (redundant or self-healed within window)",
  "curve": curve,
}
with open(out, "w") as f:
    json.dump(result, f, indent=2)
print(json.dumps({k: v for k, v in result.items() if k != "curve"}, indent=2))
PYEOF
rm -rf "$WORK"
