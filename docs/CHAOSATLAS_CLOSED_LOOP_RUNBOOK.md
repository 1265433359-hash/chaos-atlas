# ChaosAtlas Closed-Loop Runbook

This runbook enables the evidence-driven experiment policy without changing
the existing ChaosEater arm, no-KB arm, compiler, runtime gates, or cleanup
ownership.

## Rollout

1. Run a static preflight. It creates the frozen candidate denominator and
   rejects runtime feedback in static inputs:

```powershell
$env:PYTHONPATH='.'
python tools/run_native_full_discovery.py `
  --input-root <input-root> `
  --profile <runtime-profile.json> `
  --output <output-dir> `
  --project-id <project-id> `
  --api-key-file <key-file> `
  --policy-mode legacy
```

2. Run `shadow` on a frozen project. The policy chooses one candidate per
   round, but legacy execution remains in force. The controller writes the
   policy choice, stop decision, and legacy-vs-policy difference to the
   append-only ledger; no policy choice changes the mutation yet.

   When a validated project portrait and hypothesis registry are available,
   `run_live_batch` also derives a bounded runtime-only registry signal. Static
   architecture, configuration, dependency, and defense hypotheses are never
   executable. Inspect `registry-policy-input.json` and
   `registry-policy-decisions.jsonl`; a missing or invalid signal is recorded
   as a fallback and does not bypass the existing gates.

3. Run `guarded` only after the shadow gate passes. Each round executes one
   selected candidate, reads the child finding/RCA/cleanup artifacts, feeds
   back only a complete and cleanup-verified result, then evaluates the next
   stop/selection decision. `--policy-budget N` is the batch-level round
   bound unless `--max-candidates` supplies an explicit bound. Existing
   compiler, selector, recovery, and runtime applicability gates still decide
   whether execution is admissible.

4. Make `default` explicit only after the canary has zero safety regressions,
   zero out-of-denominator selections, no increase in invalid classifications,
   and non-inferior confirmed-weakness yield at the same budget.

## Artifacts

- `coverage_denominator/seed-*.json`: static-only candidate universe.
- `policy-state/seed-*.json`: mutable state for one project and seed.
- `policy-decisions.jsonl`: append-only selection and stop decisions.
- `policy-feedback.jsonl`: deterministic child classifications and feedback
  eligibility; blocked, method-invalid, or dirty children are recorded but do
  not update the posterior.
- `registry-policy-input.json`: advisory registry signal, allowed runtime IDs,
  bounded priority bonuses, and its input hash.
- `registry-policy-decisions.jsonl`: per-round legacy selection, registry
  selection, actual execution selection, fallback reason, and stop result.
- `seed-*/.../policy-decision.json`: per-run decision copy.
- runtime classifier output: deterministic classification and evidence.

State updates are applied offline after the runtime classifier completes:

```powershell
$env:PYTHONPATH='.'
python -c "from pathlib import Path; import json; from tools.experiment_policy_feedback import ingest_runtime_result, write_policy_state; p=Path('<policy-state.json>'); s=json.loads(p.read_text()); s=ingest_runtime_result(s, Path('<classified-result.json>')); write_policy_state(s, p)"
```

The result must identify the same project/commit, policy input hash,
candidate, and frozen canonical signature. A mismatch is rejected.

For offline evaluation, pass the same result and decision to
`tools.policy_calibration.record_policy_outcome`. The resulting
`policy-calibration.json` is a metrics artifact only; it cannot select a
blocked candidate or promote knowledge.

## Knowledge promotion

The policy state is project-local. It is not a prompt knowledge source. Use
the existing `feedback_protocol.build_feedback_card` and
`build_next_kb` flow after human review. `knowledge_updater` may attach only
the stable policy evidence reference (candidate/cluster/result hashes); raw
runtime observations, mutation paths, and verdicts remain in the audit card.

## Productized batch run

The deterministic product path can run Oracle-covered candidates in isolated
child directories:

```powershell
$env:PYTHONPATH='.'
python tools/chaosatlas.py run `
  --profile <runtime-profile.json> `
  --mode live `
  --output <batch-output> `
  --kube-context minikube `
  --all-candidates `
  --max-candidates 2 `
  --approve-live
```

For an offline registry-only audit, use the unified runner without any live
flags:

```powershell
python tools/chaosatlas.py run `
  --profile <runtime-profile.json> `
  --mode dry-run `
  --output <dry-run-output> `
  --registry-shadow
```

The batch root contains `batch_manifest.json`, `batch_plan.json`,
`batch_state.jsonl`, `policy-decisions.jsonl`, `policy-feedback.jsonl`,
`policy-state.json`, `runs/<candidate>/`, and `batch_summary.json`. The
manifest freezes the profile hash, explicit context, namespace, candidate-pool
hash, policy input hash, and approval contract. The summary also reports the
round count, stop reason, and feedback count. A cleanup failure prevents that
child from counting as a successful finding or policy update.

## Runtime weakness promotion

Defense evidence and weakness evidence use separate promotion gates. After two
independent runs reproduce the same runtime weakness, promote only the bounded
weakness evidence:

```powershell
python tools/weakness_promotion_stage.py `
  --history-root <weakness-history-root> `
  --output <promotion-output> `
  --knowledge-write-root <knowledge-root>
```

The gate requires `availability_degraded`, a confirmed RCA, valid lifecycle
attestation, verified cleanup, matching project revision and causal identity,
and distinct run artifacts. A successful run writes a
`chaosatlas-weakness-knowledge-v1` card with `knowledge_status=local_reusable`
plus `reproduce` and `guard` regression intents. A defense result, contradiction,
or identity mismatch writes `knowledge_conflict.json` and never overwrites an
existing card.

The card is read-only input to the next candidate/RCA pass. It can raise the
priority of the same target and fault family and carry its required diagnostics;
it does not itself assert a new runtime verdict or authorize a mutation.

Use `--resume` only with the same profile, context, namespace, candidate set,
and approval contract:

```powershell
python tools/chaosatlas.py run `
  --profile <runtime-profile.json> `
  --mode live `
  --output <batch-output> `
  --kube-context minikube `
  --all-candidates `
  --resume
```

Resume skips children already recorded as `cleanup_verified` or
`preflight_blocked`. It refuses any
batch whose immutable inputs changed or whose state shows that a child crossed
the live mutation boundary without completing the original run.

## Stop and rollback

Repetition alone never stops a causal cluster. Stop records use
`resolved`, `decision_irrelevant`, `blocked`, `low_expected_value`, or the
explicit orchestration guard `budget_exhausted`.
Intensity ladders should move toward a verified boundary; binary search is
disabled for non-monotonic behavior.

Rollback is one configuration change:

```text
--policy-mode legacy
```

Retain policy state, decisions, and feedback artifacts for diagnosis. Rollback
does not replace the existing runtime cleanup and recovery procedure.

All replay and shadow checks are offline. Do not provide cluster credentials,
mutation commands, or runtime observations to the discovery prompt.
