# Held-out Protocol v1.2 (Parallel Amendment)

Status: `draft_ready_for_approval`
Coexists with: `heldout_protocol_v1_1`
Execution status: not started

## Why v1.2 exists

Protocol v1.1 remains unchanged and requires every project to independently satisfy `protected >= 16`, `unprotected >= 16`, `unknown >= 16`, and `legal_total >= 48`. Hotel, SOCIALNET, and TeaStore do not satisfy those per-project quotas. v1.2 is a separate, explicitly pre-registered estimand for this feasibility limitation; it is not a silent relaxation and its results cannot be put into the v1.1 denominator.

## Eligibility

At least three independent held-out projects are required. Each project must pass reproducible deployment, observability, delay, loss, and kill gates and contribute at least eight legal candidates. A blocked project is reported as blocked, not silently deleted from a claimed win.

The pooled universe, recomputed by `tools/check_heldout_v12_feasibility.py`, must contain at least:

```text
protected >= 16
unprotected >= 16
unknown >= 16
legal_total >= 48
```

The current read-only feasibility audit over Hotel, SOCIALNET, and TeaStore is `16/35/32/83`. It is not yet the v1.2 execution pool. Project is the statistical cluster and projects receive equal weight, so SOCIALNET's larger static pool does not receive more inferential weight.

## Class support

A protection class must occur in at least two projects to support an inferential class-specific claim. Otherwise it is `descriptive_only`. The current protected class is supplied by SOCIALNET alone and therefore cannot be used as a v1.2 superiority endpoint.

## Methods and budgets

The five method IDs remain `Ours-full-pre`, `Ours-generic`, `ChaosEater-official`, `ChaosEater-adapter`, and `Random`. Equal-information and realistic end-to-end lines remain separate. Pilot uses `K=8`; formal uses `K=10`. Decision-engine methods use one deterministic selection replicate, LLM methods use three declared seeds, and Random uses twenty seeds. Each selected candidate may have at most two confirmation runs; `Weakness@K` counts candidates, not confirmations.

## Endpoints and inference

Primary endpoint: `Weakness@K`. Secondary endpoints remain separate: protected waste, estimated missed weakness, lifecycle evidence completeness, RCA anchoring, traceability, and cost per valid discovery. No equal-weight composite score is allowed.

For each project, compute the paired method-minus-CE score. Aggregate with equal project weight and project-clustered bootstrap/permutation 95% CIs. Candidates inside a project are not independent samples. A single project is descriptive only.

## Superiority rule

Ours-full-pre must not be worse than CE-official on `Weakness@K`, must beat CE on at least one pre-registered non-descriptive evidence endpoint, must have a project-level paired-difference CI that excludes zero for the claimed endpoint, and must not have higher protected waste. CE `environment_blocked` is not a win and remains non-comparable for that project. Any positive claim is limited to the v1.2 pooled project-stratified protocol.

## Gates and prohibitions

Freeze this amendment first. Then recompute feasibility, generate a fresh v1.2 candidate registry without result-derived filtering, freeze methods/runner/seeds/blindness/cleanup/analysis, run pilot gates, and only then run formal execution. Do not lower quotas, copy or pad candidates, use historical results for filtering, count load generators as business targets, confuse connection timeout with request timeout, or call retry/circuit without bounded timeout protected.

No v1.2 candidate pool, deployment, injection, pilot, or formal run has started.
