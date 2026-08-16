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

## Current Archive Checkpoint

The current repository checkpoint is organized around one paper-mainline
document and one machine-backed Sock Shop review. Use these in order:

1. `docs/CHAOSATLAS_PAPER_MAINLINE.md` for what belongs in the paper;
2. `docs/PROJECT_SUMMARY.md` for the repository-wide handoff;
3. `docs/SOCK_SHOP_THREE_METHOD_STAGE_REVIEW_2026-08-16.md` for current Full,
   YAML15 Ablation, and ChaosEater stage evidence;
4. `docs/EXPERIMENT_CATALOG.md` for experiment-by-experiment evidence paths;
5. `docs/ARCHIVE_MAP.md` for retention, provenance, and status rules.

The current Sock Shop headline is `Full: 15 stable weakness families` and
`YAML15 Ablation: 9 stable weakness families`, both pending human review. The
official ChaosEater native replay is a separately labeled measurement-layer
reference, not a same-layer superiority comparison.

## Project-Level Review Snapshots

| Snapshot | Scope | Use |
|---|---|---|
| `docs/CHAOSATLAS_PAPER_MAINLINE.md` | Confirmed four-stage paper narrative | Canonical mainline, evidence boundary, and frozen-track classification |
| `docs/CHAOSATLAS_PROJECT_ARCHIVE_2026-08-13.md` | 2026-08-13 project-stage archive | Historical P09/P02/Sock Shop status, queue and evidence boundaries |
| `docs/CHAOSATLAS_STAGE_SUMMARY_2026-08-14.md` | 2026-08-14 project-stage summary | Current method scope, real-project evidence, ten-project boundary, paper narrative, and next-stage tasks |
| `docs/CHAOSATLAS_REAL_PROJECT_REVIEW_2026-08-14.md` | Online Boutique, OpenTelemetry Demo, Sock Shop | Native-full vs ablation end-to-end capability and same-candidate-pool selection capability; includes `[CONFIRMED]`, `[PENDING]`, `[BOUNDARY]`, `[DO-NOT-CLAIM]` labels |
| `docs/SOCK_SHOP_THREE_METHOD_STAGE_REVIEW_2026-08-16.md` | Current Sock Shop Full/YAML15/ChaosEater stage | Current machine-backed headline and measurement-layer boundary; `human_review=pending` |
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

## Paper-Mainline Classification

This classification is independent of runtime result labels and controls whether
an artifact can be used in the current paper narrative:

| Paper status | Meaning | Current use |
|---|---|---|
| `mainline` | Current real-project capability evidence under the confirmed research story | May support the paper after its review state and machine ledger are cited |
| `frozen_historical` | Superseded, preselected, same-pool, adapter, or old pilot material | Retain for audit and reproducibility; do not include in current mainline statistics |
| `future_work` | Planned experiment not yet completed, such as a same-layer three-method comparison or new project queue | Describe as a next step, never as completed evidence |

The current mainline is: initial ChaosAtlas architecture; Online Boutique,
OpenTelemetry Demo and Train Ticket real-project issue discovery; Sock Shop
improved-method Full-versus-YAML15-Ablation discovery and runtime evidence; and
the official ChaosEater native replay as a separately labeled measurement-layer
reference. Same-pool/preselected-candidate tracks, the superseded Ablation,
early pilots and `ChaosEater-adapter` are `frozen_historical`. A same-layer,
machine-ledgered three-method comparison remains `future_work`.

## Naming and Pairing

- Keep a stable card ID across JSON and Markdown, for example
  `KB-TT-NETWORK-STATION-DELAY-001`.
- Put machine-readable data in JSON/CSV and cite it from Markdown reports.
- Pair each runtime result with its classification and cleanup evidence.
- Keep generated snapshots immutable once they enter a frozen ablation arm.
- Put issue drafts in `reporting/<project>/issues/`; record submission state in
  `reporting/tracking.md` and `reporting/submission_index.md`.

## Logical Freeze Rule

Freezing is metadata-only. Do not move, rename, delete, or rewrite the original
experiment directories when changing their paper status. Preserve all paths,
hashes, prompts, ledgers, reports, and diagnostic files so existing evidence
links remain valid. Add the status to an index or human-readable summary and
link the artifact from the canonical mainline document when needed.

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
