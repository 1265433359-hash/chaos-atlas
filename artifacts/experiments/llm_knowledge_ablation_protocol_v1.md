# LLM Knowledge-Base Ablation Protocol v1

Status: DRAFT. This document is an execution handoff for DeepSeek and is not frozen until the human reviewer approves the pre-registration checklist.

Purpose: quantify the causal contribution of the knowledge base to LLM test-node selection. This is a supplementary ablation track. It does not replace the main C-J comparison of Ours, ChaosEater, and Random, and it must not be merged into a single score with that comparison.

## 1. Research Questions

RQ1. Does a frozen project-independent knowledge base improve LLM selection over an otherwise identical blind LLM?

RQ2. Does a frozen project-specific pre-experiment snapshot provide additional benefit beyond generic knowledge?

RQ3. Does knowledge reduce protected-candidate waste, invalid experiments, and analysis cost while preserving or improving confirmed weakness discovery?

Primary hypotheses:

- H1: `LLM-full-pre` has Weakness@K no lower than `LLM-blind`.
- H2: `LLM-generic` has Weakness@K no lower than `LLM-blind`.
- H3: `LLM-full-pre` has Protected-waste@K no higher than `LLM-blind`.
- H4: `LLM-full-pre` improves at least one pre-registered evidence endpoint (RCA accuracy, evidence completeness, invalid-rate, or confirmed issue yield).

Do not claim that H1-H4 prove superiority over ChaosEater. They isolate the value of knowledge for the LLM decision component.

## 2. Experimental Arms

All arms must use the same model family/version, endpoint, prompt template, output schema, candidate pool, candidate ordering permutations, temperature, max output tokens, timeout, and selection budget.

| arm_id | Information provided to the LLM | Claim supported |
|---|---|---|
| `LLM-blind` | Project intake/source summary, method-neutral candidate descriptors, and generic task definition. No knowledge cards or project contract labels. | Blind baseline |
| `LLM-generic` | Everything in `LLM-blind` plus generic SE/DP/JE rules, evidence rules, and cross-project fault semantics. The knowledge supplement contains no project-specific service facts, results, or target-pool outcomes. | Generic knowledge value |
| `LLM-full-pre` | Everything in `LLM-generic` plus the project-specific snapshot reconstructed before this experiment. The snapshot may contain static contract facts and source provenance, but no post-selection runtime result or final candidate verdict. | Full pre-experiment knowledge value |

Do not expose explicit `weakness`, `protected`, `invalid`, `environment_blocked`, or `root_cause` verdicts for the current candidate pool. If a snapshot contains such fields, create a redacted LLM view and keep the original only for audit. A separate oracle-assisted arm would answer a different question and must not enter the main ablation result.

The deterministic `Ours-full-pre` and `Ours-generic` arms from the main protocol are reported separately. They are not substitutes for these three LLM arms.

## 3. Unit of Analysis and Scope

The unit of analysis is one `project x candidate_pool x arm x seed` selection. Candidates are nested within projects; candidates are not independent projects.

Use the current held-out protocol budgets:

- Pilot: 24 candidates per project, K=8.
- Formal: 48 candidates per project, K=10.
- LLM selection seeds: 3 pre-registered seeds per arm.
- Each selected candidate: at most 2 valid confirmation runs.

At least 3 comparable independent project families are required for a cross-project claim. SOCIALNET and MEDIA from the same DeathStarBench repository must not be treated as fully independent project families without an explicit clustering decision.

## 4. Required Pre-Experiment Snapshots

DeepSeek must create and hash the following before any LLM selection or injection:

1. `project_commit_manifest.json`: canonical URL, commit, branch/tag, source path outside the repository, and per-file SHA-256 values.
2. `knowledge_snapshot_manifest.json`: snapshot IDs, source provenance, creation time, allowed fields, redacted fields, and SHA-256 values.
3. `candidate_pool_<project>_<pilot|formal>.json`: method-neutral candidate IDs, fault family, target, workload, mutation reference, and static evidence references.
4. `prompt_manifest.json`: prompt template hash, system/developer/user sections, model identifier, endpoint, temperature, max tokens, timeout, and seed list.
5. `leakage_audit.json`: forbidden terms, forbidden fields, scan results for each arm, and reviewer decision.

The candidate pool must be frozen before any arm sees it. Candidate IDs and ordering must be method-neutral. Truth labels are stored in a separate oracle file and are not included in any LLM input.

## 5. Candidate-Pool Construction

Construct the pool using pre-registered neutral rules, not LLM output or prior pilot results.

The formal pool should contain, where supported by the project:

- 16 protected candidates;
- 16 unprotected candidates;
- 16 unknown candidates;
- balanced delay, loss, and kill families.

If a project cannot support a fault family, mark that family `unavailable`; do not borrow candidates from another project or silently rebalance after seeing results. Record the actual composition and the reason for any deviation.

Each candidate record must include:

```json
{
  "candidate_id": "stable-id",
  "project_id": "ESHOP",
  "workload_id": "documented-workload",
  "target": "service-or-edge",
  "fault_family": "delay|loss|kill",
  "fault_parameters": {},
  "mutation_path": "frozen-path-or-null",
  "static_evidence_refs": [],
  "information_tier": ["I0", "I1-local", "I2"],
  "oracle_label": "stored-out-of-band"
}
```

Do not include `oracle_label` in the LLM bundle.

## 6. LLM Selection Procedure

For each project, arm, and seed:

1. Load the frozen arm-specific input bundle.
2. Apply the pre-registered candidate-order permutation for that seed.
3. Ask the LLM to rank candidates and return exactly K selected IDs plus a short rationale for each.
4. Parse the output with a strict schema validator.
5. Record duplicate IDs, unknown IDs, missing IDs, invalid JSON, token counts, latency, and retries.
6. Freeze the selected set and raw response before any execution starts.

Retries are allowed only for transport failure and must use the same seed and exact same prompt. Do not retry an invalid reasoning output with a changed prompt. Count parser-invalid outputs as an LLM decision failure.

The LLM must not receive runtime logs, previous method rankings, oracle labels, post-hoc issue drafts, or the output of another arm.

## 7. Execution and Independent Truth Evaluation

After all arms have completed selection:

1. Freeze all selected sets and hashes.
2. Execute selected candidates using the common runner, isolated namespace, single target (`mode: one`), bounded duration, baseline, injection, observation, recovery, and cleanup.
3. Run no method-specific mutation or code modification.
4. Perform an independent oracle pass over the full candidate pool after selection. The oracle result must not be written back into any selection snapshot.
5. Any candidate classified as a confirmed weakness requires at least two consistent valid runs. A single valid run is insufficient for the primary weakness count.
6. Classify platform or environment failures separately from method-invalid selections.

An unselected candidate can be counted as a missed weakness only if it has independent oracle evidence. Without full-pool oracle coverage, report discovery precision only and do not claim recall or leakage reduction.

## 8. Outcome Definitions

`confirmed_weakness`: at least two valid runs with the pre-registered weakness oracle and complete evidence chain.

`protected`: an independent static/runtime contract or availability oracle confirms the relevant defense.

`unknown`: evidence is insufficient to classify protected or unprotected before execution.

`method_invalid`: the selected candidate is schema-invalid, duplicate, unreachable, non-injecting, or missing a valid workload path, excluding platform-blocked environment conditions.

`environment_blocked`: bring-up, baseline, controller, kernel, or observation prerequisites prevent fair execution. This is reported separately and is never converted into a method win or loss.

`unique_issue`: a confirmed root cause/service-edge issue after deduplicating repeated manifestations of the same mechanism.

## 9. Metrics

Primary metric:

- `Weakness@K`: number of selected candidates independently confirmed as weaknesses.

Secondary metrics, reported separately:

- `Protected-waste@K = protected_selected / K`.
- `Recall@K = confirmed_weakness_selected / confirmed_weakness_in_pool`.
- `Invalid-rate = method_invalid_selected / K`.
- `Evidence-completeness`: fraction of executed candidates with baseline, injection, observation, recovery, cleanup, source mapping, and runtime evidence.
- `RCA-accuracy`: fraction of confirmed findings whose service/edge/root-cause mapping matches independent adjudication.
- `Unique-issue-yield`: unique confirmed issues per K selected candidates.
- `Cost-per-issue`: LLM cost, execution count, elapsed time, and human analysis minutes divided by unique confirmed issues.

Never add these metrics into an unweighted total score.

## 10. Statistical Analysis

For each project and seed, calculate paired differences using the same candidate pool and seed permutation:

```text
delta_weakness_full_vs_blind = Weakness@K(full-pre) - Weakness@K(blind)
delta_weakness_generic_vs_blind = Weakness@K(generic) - Weakness@K(blind)
delta_waste_full_vs_blind = Protected-waste@K(full-pre) - Protected-waste@K(blind)
```

Report every seed-level value, project-level median, and project-level paired difference. For cross-project inference, resample project families, not candidates, using clustered bootstrap or paired permutation. Do not use candidate count as the sample size for a cross-project claim.

Pre-register the following decision rule:

- Knowledge benefit is supported only if the lower bound of the project-clustered 95% interval for `LLM-full-pre - LLM-blind` on Weakness@K is at least 0, the corresponding waste difference is not positive, and at least one evidence endpoint improves in the pre-registered direction.
- A cross-project claim requires at least 3 comparable project families and a project-clustered 95% interval for the primary paired difference that does not cross 0.
- If the interval crosses 0, report the direction and uncertainty; do not claim superiority.

With fewer than 3 project families, report replication/descriptive results only.

## 11. Cost Accounting

Record separately:

- input and output tokens;
- number of model calls and transport retries;
- selection wall-clock time;
- candidate execution count and confirmation count;
- environment recovery time;
- human review and RCA minutes;
- failed or blocked setup time.

Do not hide the larger context cost of `LLM-full-pre`. Report both raw discovery metrics and cost-normalized discovery metrics.

## 12. Required Artifacts

DeepSeek must produce, without overwriting prior evidence:

- `llm_knowledge_ablation_protocol_v1.md`;
- `knowledge_ablation_snapshots/<project>/...`;
- `knowledge_ablation_candidates/<project>/{pilot,formal}.json`;
- `knowledge_ablation_prompts/<project>/{blind,generic,full-pre}/...`;
- `knowledge_ablation_selections/<project>/<arm>/seed-*.json`;
- `knowledge_ablation_execution/<project>/...`;
- `knowledge_ablation_oracle/<project>/...`;
- `knowledge_ablation_analysis/{seed,project,cross_project}.json`;
- `knowledge_ablation_claim_evidence_matrix.md`;
- `knowledge_ablation_run_ledger.jsonl`.

Every result file must include `protocol_sha256`, `candidate_pool_sha256`, `snapshot_sha256`, `prompt_sha256`, `method`, `project`, `seed`, and `status`.

## 13. Human Review Gates

DeepSeek must stop and request review at each gate:

Gate 0: project commits, source hashes, and project boundaries are complete.

Gate 1: leakage audit passes and arm-specific snapshots are frozen.

Gate 2: candidate pool is balanced, method-neutral, and frozen; no truth labels are exposed.

Gate 3: pilot outputs are schema-valid and no arm sees forbidden input.

Gate 4: pilot environment and baseline gates pass; otherwise mark the affected arm/project blocked.

Gate 5: formal results are collected without changing K, seeds, prompts, budgets, or scoring.

Gate 6: statistical analysis and claim-evidence matrix are complete before any paper wording is drafted.

## 14. Stop Conditions and Prohibited Actions

Stop immediately if any of the following occurs:

- a selection input contains current-pool oracle labels or post-hoc runtime outcomes;
- candidate IDs or candidate composition change after an arm has selected;
- prompts, model versions, temperature, K, seed, or scoring rules change without an amendment;
- CE or another arm is removed after seeing its ranking;
- a platform-blocked run is counted as a method failure or win;
- a selected candidate has no independent workload or injection evidence;
- results are written back into a knowledge snapshot used by a later arm;
- the same candidate is silently deduplicated across arms in cost accounting.

## 15. Review Checklist for the Main Agent

Before accepting DeepSeek output, verify:

- [ ] Three arm definitions are present and differ only in knowledge visibility.
- [ ] All snapshots and prompts have hashes and provenance.
- [ ] Candidate truth labels are out-of-band during selection.
- [ ] Candidate pool and K are identical across arms.
- [ ] Seeds and candidate-order permutations are pre-registered.
- [ ] Runtime runner, observation oracle, and confirmation rule are shared.
- [ ] Environment blocked is separate from method invalid.
- [ ] Full-pool oracle exists before recall or missed-weakness claims.
- [ ] Metrics are not collapsed into a weighted total.
- [ ] Cross-project inference clusters by project family.
- [ ] No claim exceeds the number of comparable projects.
- [ ] Raw LLM outputs, token cost, retries, and human time are archived.

## 16. Permitted Final Wording

If the preregistered endpoints pass:

> Under the frozen candidate pool and common execution protocol, adding pre-experiment knowledge to the LLM was associated with no lower confirmed weakness discovery and lower or equal protected-candidate waste than the blind LLM across the comparable project families tested.

If the endpoints do not pass:

> The experiment did not establish a reliable benefit of the knowledge base for LLM candidate selection under the tested protocol; observed per-project differences are reported descriptively.

Do not write “the knowledge base makes the LLM generally better” or “the full method is superior to ChaosEater” from this ablation alone.
