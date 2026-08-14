# Archive Map

本文件是项目归档的“注释层”：说明每类文件为什么存在、能支持什么结论、
以及新增实验时应该把证据放在哪里。它不替代具体运行报告。

## Evidence Ownership

| Evidence type | Canonical location | Meaning |
|---|---|---|
| Original input | `raw_yaml/<Kind>/<sha>.yaml` | Immutable source input; retain path and hash |
| Static inventory/slice | `artifacts/<project>/*slices*`, `yaml_inventory.csv` | Parsed fields, selector matches, source candidates, hypotheses |
| Runtime execution | `artifacts/<project>/runtime/` or `artifacts/experiments/execution/` | Baseline, injection, observation, recovery, cleanup, and classification |
| Knowledge card | `artifacts/<project>/knowledge_base/` | Searchable, versioned summary with next evidence and boundaries |
| Human interpretation | `artifacts/<project>/*.md`, `reporting/` | Paper narrative, issue draft, limitation, or review status |
| Protocol/ablation | `artifacts/experiments/` | Frozen prompts, pools, snapshots, ledgers, and analysis outputs |
| Session memory | `task_plan.md`, `findings.md`, `progress.md` | Decisions and discoveries; not a substitute for run evidence |

## Project-Level Review Snapshots

| Snapshot | Scope | Use |
|---|---|---|
| `docs/CHAOSATLAS_PROJECT_ARCHIVE_2026-08-13.md` | 2026-08-13 project-stage archive | Broad project status, P09/P02/Sock Shop history, queue and evidence boundaries |
| `docs/CHAOSATLAS_STAGE_SUMMARY_2026-08-14.md` | 2026-08-14 project-stage summary | Current method scope, real-project evidence, ten-project boundary, paper narrative, and next-stage tasks |
| `docs/CHAOSATLAS_REAL_PROJECT_REVIEW_2026-08-14.md` | Online Boutique, OpenTelemetry Demo, Sock Shop | Native-full vs ablation end-to-end capability and same-candidate-pool selection capability; includes `[CONFIRMED]`, `[PENDING]`, `[BOUNDARY]`, `[DO-NOT-CLAIM]` labels |
| `docs/ChaosAtlas_three_project_experiment_report_2026-08-14.docx` | Word report for the two key three-project comparisons | Human-facing report explaining project choice, original full-vs-ablation workflow, same-pool selection workflow, results, percentages, and interpretation boundaries |
| `docs/CHAOSATLAS_UPLOAD_PREP_2026-08-14.md` | Git upload preparation checklist | Current local commit state, included/excluded paths, verification commands, sensitive-data boundary, and push readiness |

## Required Provenance

Every new result should record, directly or through a linked manifest:

1. upstream repository and commit;
2. input YAML path and SHA-256;
3. environment fingerprint and isolated namespace;
4. mutation parameters, target selector, workload/oracle, seed, and time budget;
5. baseline, active effect, recovery, cleanup, and source/runtime references;
6. status, confidence, limitations, and the next evidence needed.

If one field is unknown, write `unknown` or `pending` and explain why. Never
replace missing evidence with a confident prose summary.

## Status Rules

Use the following vocabulary consistently:

| Status | Allowed use |
|---|---|
| `candidate` | Static candidate selected for review; no runtime claim |
| `pending` | A required gate or evidence item is not complete |
| `confirmed_static` | Static source/manifest mapping only |
| `confirmed_runtime` | Runtime path and injection/effect were observed |
| `validated_runtime` | Runtime result plus knowledge-card schema validation |
| `blocked_by_platform_prerequisite` | Fair execution prevented by kernel/controller/bring-up prerequisite |
| `not_reachable` | Workload or business path cannot currently be reached |
| `closed_runtime_boundary_no_reinjection` | A bounded boundary is established; selector must stop repeating it |

`blocked_by_platform_prerequisite` and `not_reachable` are useful findings but
are not evidence that the application defended itself.

## Naming and Pairing

- Keep a stable card ID across JSON and Markdown, for example
  `KB-TT-NETWORK-STATION-DELAY-001`.
- Put machine-readable data in JSON/CSV and cite it from Markdown reports.
- Pair each runtime result with its classification and cleanup evidence.
- Keep generated snapshots immutable once they enter a frozen ablation arm.
- Put issue drafts in `reporting/<project>/issues/`; record submission state in
  `reporting/tracking.md` and `reporting/submission_index.md`.

## New Run Checklist

- [ ] Copy the input and hash it; do not edit `raw_yaml/` in place.
- [ ] Verify the applicability gate before creating a mutation.
- [ ] Capture a baseline with the same oracle, timeout, and concurrency.
- [ ] Use one fault family and one target per run unless a protocol explicitly defines a multi-fault arm.
- [ ] Wait for actual injection (`injectedCount >= 1`) before measuring effect.
- [ ] Capture recovery and resource cleanup, not only the business response.
- [ ] Classify platform blocked, invalid, unknown, protected, and weakness outcomes separately.
- [ ] Update or create a card only with linked evidence and a next-evidence list.
- [ ] Run the knowledge-base validator and add the result to the ledger.

## Paper Citation Boundary

Static matches support statements such as “the selector maps to this
Deployment.” They do not support “the request executed this function.” Runtime
logs and traces support execution claims. A client timeout does not prove that
the server stopped; a server completion log after the timeout is a distinct
result. Production SLO and defense claims require an operator-defined budget or
an explicit source contract.

## Retention and Cleanup Boundary

Keep experiment evidence, formal protocol inputs, machine-readable ledgers,
knowledge cards, raw YAML, logs, and planning summaries. Temporary agent
prompts, ad-hoc execution instructions, and test caches are not evidence and
may be removed after the decision is recorded in `docs/ARCHIVE_CLEANUP.md`.
Do not remove files under `artifacts/experiments/knowledge_ablation_prompts/`:
those prompts are frozen inputs for the ablation protocol, not disposable chat
drafts.
