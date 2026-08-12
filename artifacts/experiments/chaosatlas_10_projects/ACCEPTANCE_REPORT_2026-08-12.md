# ChaosAtlas 10-Project Preparation Acceptance

Date: 2026-08-12

## Acceptance result

Preparation is **partially accepted**. The protocol, leakage gate, source-backed
input bundles, P02 pilot evidence, statistics tooling, and official ChaosEater
compatibility audit are present and regression-tested. The 10-project main
experiment is not yet runnable.

## Work-package status

| Area | Result | Evidence |
|---|---|---|
| Exact source restoration | P09 restored; P03/P06 blocked incomplete | `sources_restored/RESTORATION_MANIFEST.md` |
| P09 reduced profile | Blocked before YAML generation | `runtime_profiles/P09/profile_preflight.json` |
| Image provenance | Blocked; no verified core digests | `runtime_profiles/P09/image-digests.json` |
| P09 oracle | Local mock passes; API health not running | `runtime_profiles/P09/server-side-dry-run.json` and `mock_workflow_oracle.py` |
| Official ChaosEater audit | Complete, read-only | `chaoseater_official_audit.json` |
| Statistics analyzer | Complete; report explicitly says 1/10 projects observed | `analysis_outputs/chaosatlas_statistics/statistics.json` |
| Leakage/ablation input gate | Pass: 30 KB/noKB pairs | `validate_chaosatlas_experiment.py` output |
| Regression | Pass: 290 tests, 5 subtests | session test run |

## Runtime and result boundary

- P02 has `execution_ready=true` for deployment/injection preparation, but
  `method_result_eligible=false` because the independent formal oracle and
  approved main-track LLM call gate are not complete.
- The P02 runtime summary is a real supplementary pilot result. It is not a
  10-project comparison and cannot support a cross-project KB ablation claim.
- P03/P06/P09 and the remaining projects are environment-blocked or
  out-of-domain. These are not method failures.
- No DeepSeek key was read and no new API request was sent during acceptance.
- No Docker Desktop action and no cluster mutation was performed during
  acceptance.

## Blocking conditions before formal calls

1. At least one project must pass namespace-local deployment, health, baseline,
   deterministic oracle, recovery, cleanup, and immutable image gates.
2. The P09 profile needs verified image digests and a successful server-side
   dry-run before any apply.
3. The consent record must contain an explicit monetary ceiling and the exact
   call/retry/token plan.
4. Formal reporting must retain project-level clustering and exclude blocked
   projects from method-yield denominators.
