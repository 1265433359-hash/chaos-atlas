"""Generate r2 mutation YAML files (pure static, no cluster).

Reads prospective_pool_r2.json (18 candidates) and writes one NetworkChaos YAML
per candidate into artifacts/experiments/execution/remediation/r2_mutations/.
Frozen names/selectors follow the r2 pool's `app` label and namespace.

Notes:
  - mode=all matches existing OB/OTEL mutations (r2 pool labelSelectors single app).
  - duration=30s, direction=to for delay; loss uses the same shape with loss 100%.
  - This is the frozen pre-registration mutation set; it does NOT run anything.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ROOT = Path(__file__).resolve().parents[1]
POOL_PATH = ROOT / "artifacts" / "experiments" / "execution" / "prospective_pool_r2.json"
OUT_DIR = ROOT / "artifacts" / "experiments" / "execution" / "remediation" / "r2_mutations"


def build_yaml(c: dict) -> str:
    cid = c["candidate_id"]
    app = c["app"]
    ns = c["namespace"]
    fault = c["fault"]
    name = c["mutation"].replace(".yaml", "")
    if fault == "loss":
        action = "loss"
        effect = '  loss:\n    loss: "100"\n'
    else:
        action = "delay"
        effect = '  delay:\n    latency: "2000ms"\n    correlation: "100"\n    jitter: "0ms"\n'
    return f"""apiVersion: chaos-mesh.org/v1alpha1
kind: NetworkChaos
metadata:
  name: {name}
  namespace: {ns}
  labels:
    chaos.candidate-id: {cid}
spec:
  action: {action}
  mode: one
  selector:
    namespaces:
      - {ns}
    labelSelectors:
      app: {app}
{effect}  duration: 30s
  direction: to
"""


def main() -> int:
    doc = json.loads(POOL_PATH.read_text(encoding="utf-8"))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    written = []
    for c in doc["candidates"]:
        target = OUT_DIR / c["mutation"]
        # overwrite only within the frozen r2 directory; never touch existing dirs
        target.write_text(build_yaml(c), encoding="utf-8")
        written.append(c["mutation"])
    print(f"wrote {len(written)} mutations to {OUT_DIR}")
    for m in written:
        print(" ", m)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
