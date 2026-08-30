# Project Onboarding

Phase 0 defines the contract for bringing a deployed project into ChaosAtlas.
It does not deploy workloads or run a chaos experiment. It checks that the
project has enough identity, isolation, business-oracle and cleanup information
for later phases.

## Check A Profile Schema

```powershell
python tools/project_onboarding.py --profile projects/sock-shop/profile.json --workspace-root .
```

The command checks the profile schema and declared manifest/source paths. A
successful static result is `ready_for_static_analysis`; `runtime` remains
`not_checked` until a later runtime preflight is explicitly run.

Required profile facts are:

- fixed project revision and relative manifest/source roots;
- isolated, non-system namespaces;
- at least one repeatable business oracle;
- logs and Kubernetes events (Trace is optional);
- positive recovery deadline, business-probe requirement and cleanup policy;
- redaction policy for secret-like fields.

## Check B Knowledge Cards

```powershell
python tools/validate_knowledge_base.py `
  --root <knowledge-root> `
  --profile projects/sock-shop/profile.json
```

The knowledge validator can validate cards and the onboarding profile in one
report. A valid profile does not make any runtime or defense claim.

## Unified Offline Closed Loop

The first unified entry point is a deterministic offline rehearsal:

```powershell
python tools/chaosatlas.py run `
  --profile projects/sock-shop/profile.json `
  --mode dry-run `
  --output .runs/sock-shop/<run-id>
```

The stage order is fixed:

```text
onboard
-> inventory
-> server deployment detection
-> TestNode/candidate mapping
-> experience retrieval
-> advisory hypotheses
-> applicability gate
-> baseline
-> synthetic execution and observation
-> deterministic classification
-> RCA
-> knowledge draft
-> regression intent
```

Server deployment detection is the platform-neutral ChaosAtlas capability for
building Deployment/Service/Pod, selector, replica, probe, recovery, cleanup,
business-oracle and candidate-space facts. It is not a CE API and does not
require CE to run. CE and native Kubernetes/Chaos Mesh execution are future
adapters behind the same lifecycle contract.

The dry-run command writes stage artifacts, `checkpoint.json`, and a summary.
Its synthetic executor deliberately cannot produce a runtime `weakness`,
`defended`, or confirmed RCA/knowledge claim. Use `--resume` to continue an
incomplete offline run after its input snapshot is verified.

The command also accepts `--seed` and `--knowledge-root`. Knowledge cards are
read-only and can change candidate ranking or advisory hypotheses, but cannot
change the candidate set or final verdict.

## Live Adapter Boundary

The offline milestone intentionally rejects `--mode live`; it never dispatches
to the legacy runner. A future native or CE adapter must implement the same
`preflight -> baseline -> inject -> observe -> recover -> cleanup` lifecycle
and return evidence through the same classifier and RCA gates. Runtime
connection details belong in the project adapter and must not include
credentials in the profile.

```json
{
  "id": "sock-shop-homepage",
  "kind": "http",
  "service": "front-end",
  "remote_port": 80,
  "entrypoint": "/",
  "success_contract": "http_200"
}
```

The future live command will require an explicit approval and namespace allowlist:

```powershell
python tools/chaosatlas.py run `
  --profile <project-profile-with-runtime-oracle>.json `
  --mode live `
  --output .runs/<project>/<run-id>
```

When implemented, live mode will execute only namespace-local candidates and
own baseline, injection confirmation, business observation, recovery, and
cleanup. Missing `service`/`remote_port`, missing approval, platform blocking,
business unreachable observation, or unconfirmed injection must fail closed.

## Result Contract

Every gate/classifier result uses one of the following claim states:

```text
method_invalid | environment_blocked | target_not_found |
business_not_reachable | injection_not_confirmed | effect_unobserved |
response_preserved | degraded | weakness | recovery_timeout | defended
```

`response_preserved` is deliberately not `defended`. A defense claim requires
confirmed injection, independent business evidence, confirmed recovery and
confirmed cleanup. Blocked, unreachable and unconfirmed-injection outcomes
cannot be promoted to a defense or weakness claim.
