# SOCIALNET — Environment Feasibility Report (2026-08-10)

> Status: **environment_blocked** — minimal bring-up could not complete a stable
> baseline. Deployment artifacts exist and a service subset was deployed, but
> Service-DNS/baseline/observation prerequisites failed. No LLM was called; no
> formal candidate injection was executed.

## 1. Deployment manifest availability

**Available.** At frozen commit `6ecb0970` of `DeathStarBench socialNetwork/`
(`/root/heldout_src/socialnet/socialNetwork`):

- `docker-compose*.yml` (4 variants)
- `helm-chart/socialnetwork` (28 sub-charts; replicas/probes/PDB/HPA verified in
  snapshot — Stage C2)
- Per-service Dockerfiles
- App image `deathstarbench/social-network-microservices:latest` was pulled and
  loaded into the kind node (`kind load`, CRI-visible, test-run `Succeeded`)

## 2. Minimal bring-up — what was done (bounded, no formal injection)

| step | result |
|---|---|
| kind cluster recovery | dockerd started (`--iptables=false`), kind cluster recreated, node Ready |
| chaos-mesh install | 23 CRDs; controller-manager 3/3 Running, chaos-daemon Running; **dashboard CrashLoopBackOff; chaos-dns-server not Ready** |
| namespace | `heldout-socialnet-lab` created |
| image provisioning | all SOCIALNET images (app + mongo 4.4.6 + memcached 1.6.7 + redis 6.2.4 + openresty-thrift + jaeger + media-frontend) pushed to local registry `172.18.0.1:5000`; node pulls via hosts.toml |
| deploy subset | post-storage-service + post-storage-mongodb + post-storage-memcached + jaeger deployed; pods Running (1/1) |

## 3. Selector verification — **MISMATCH (18 of 30 frozen YAMLs)**

The chart's pod labels are `app: <name>-service` (e.g. `app=post-storage-service`),
but the **frozen delay/loss mutation YAMLs use short selectors**:

| frozen selector (`app:`) | actual pod label | candidates affected |
|---|---|---|
| `post-storage` | `post-storage-service` | 4 (2×delay + 2×loss) |
| `home-timeline` | `home-timeline-service` | 2 |
| `media` | `media-service` | 2 |
| `text` | `text-service` | 2 |
| `unique-id` | `unique-id-service` | 2 |
| `user` | `user-service` | 2 |
| `user-timeline` | `user-timeline-service` | 2 |
| `social-graph` | `social-graph-service` | 2 |

- **12 kill YAMLs use `-service` names and MATCH** (e.g. `app: post-storage-service`).
- **18 delay/loss YAMLs MISMATCH** (would target zero pods → `method_invalid` /
  non-injecting under Chaos Mesh).
- Frozen candidate pools and mutation YAMLs were **NOT modified** (hashes
  unchanged). This is a recorded defect of the frozen mutation mapping, not a
  runtime fix.

## 4. Baseline — **NOT established (environment_blocked)**

Two consecutive baseline connectivity attempts to `post-storage-service:9090`
failed:

1. DNS resolution failed: CoreDNS pods are crash-looping
   (`plugin/ready: Plugins not ready: "kubernetes"`, 4 restarts) because
   **cluster Service-DNS is broken**: dockerd was started with
   `--iptables=false` (required because the WSL2 kernel lacks the
   `MASQUERADE`/`nf_nat_masquerade` modules), so kube-proxy could not program
   ClusterIP NAT; `KUBE-SERVICES` chain absent, `ClusterIP 10.96.0.1:443`
   unreachable.
2. Direct pod-IP connect to `10.244.0.31:9090` was **refused**: the
   post-storage-service container is stuck retrying the Jaeger tracer
   (`tracing.h:77 SetUpTracer ... retrying`) and never opens the thrift
   listener on 9090. The jaeger service was then deployed, but the service DNS
   dependency (blocked by #1) prevents the app from resolving `jaeger:6831`.

| check | result | classification |
|---|---|---|
| deployment manifest | available | — |
| minimal bring-up | pods Running but app listener never opens | `environment_blocked` |
| namespace/service reachable | no (CoreDNS broken) | `environment_blocked` |
| baseline x2 | failed (no listener) | `baseline_unstable` (env cause: DNS) |
| delay/loss injection | not performed | `injection_unavailable` |
| observation chain | not available (no baseline) | `observation_unavailable` |
| recovery / cleanup | not testable | `recovery_failed` (n/a) |

## 5. Classification

- **`environment_blocked`** for the SOCIALNET execution line: bring-up could not
  establish a stable baseline. Per protocol §14 / instructions, environment
  blocked is **never** a method win or loss and is reported separately.
- **`selector_mismatch`** is a separate recorded defect: 18/30 frozen delay/loss
  YAMLs would select zero pods. This must be fixed (regenerated mutation mapping
  or deployment label alignment) **before any injection**, and requires a note in
  the amendment.

## 6. Gate 3 eligibility

**Not eligible until**: (a) cluster Service DNS is repaired (requires kernel
MASQUERADE support or a working proxy mode) and CoreDNS is Ready; (b) the app
listener opens and two consecutive baselines pass; (c) the 18 selector
mismatches are resolved; (d) observation (Jaeger) chain is verified.

## 7. Frozen artifacts — untouched

- `knowledge_ablation_candidates/SOCIALNET/{pilot,formal}.json` hashes unchanged
  (`10c06fbe…`, `614eab5f…`)
- 30 mutation YAMLs unchanged (static-only; no runtime verification)
- No LLM selection; no Chaos injection; no oracle pass.

## 8. Cost estimate per candidate (projected, blocked)

Until baseline/injection work, per-candidate execution cost cannot be measured.
Once unblocked: ~1 min baseline + 30 s injection + observation + recovery per
run, ≤2 confirmation runs per candidate, plus bring-up amortization. These are
estimates, not measured values.
