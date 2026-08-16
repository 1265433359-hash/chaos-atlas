# Code and Tool Guide

This guide is the code-comment index for the repository. Python modules carry
their detailed docstrings; this file records the intended ownership and side
effects so a future contributor can choose the correct entry point.

## Current Paper-Mainline Entry Points

The current evidence path is intentionally split by responsibility:

| Stage | Entry points | Boundary |
|---|---|---|
| Raw corpus and five-category projection | `yaml_confidence_categories.py`, `yaml_confidence_stopping.py` | Static counts and stopping parameters; no runtime weakness claim |
| Full discovery | `run_sock_shop_confidence_discovery.py` | Category-scoped knowledge/confidence discovery; emits hypotheses only |
| Ablation discovery | `run_sock_shop_ablation_discovery.py` | Independent LLM self-stop; YAML15 exposes only frozen category examples |
| Hypothesis compilation | `open_discovery_compiler.py`, `open_discovery_mutation_compiler.py` | Fail-closed JSON/YAML compilation; no cluster mutation |
| Applicability gate | `runtime_applicability_gate.py` | Read-only namespace, target, CRD, workload, and platform checks |
| Runtime lifecycle | `run_chaos_experiment.py`, `run_sock_shop_two_arm.py` | Baseline, injection, observation, recovery, cleanup, washout |
| Result interpretation | `classify_runtime_result.py` | Evidence classification; does not auto-create knowledge cards |

The authoritative narrative and evidence boundary are in
`docs/CHAOSATLAS_PAPER_MAINLINE.md`; the current Sock Shop machine-backed
review is in `docs/SOCK_SHOP_THREE_METHOD_STAGE_REVIEW_2026-08-16.md`.
Same-pool, preselected-candidate, superseded Ablation, early pilot, and
`ChaosEater-adapter` paths remain available for audit but are not current
mainline entry points.

## Read-Only and Build Tools

| Tool | Purpose | Writes |
|---|---|---|
| `build_yaml_test_catalog.py` | Parse raw YAML and create inventory/catalog artifacts | `artifacts/train-ticket/` catalog files |
| `refine_train_ticket_slices.py` | Enrich static slices with source candidates and graph edges | refined slice artifacts |
| `build_train_ticket_service_graph.py` | Build cross-service static mapping | service graph artifacts |
| `project_registry.py` | Normalize project, service, and fault identifiers | none |
| `environment_fingerprint.py` | Record tool, cluster, and source provenance | fingerprint JSON when invoked |

## Selection and Decision Tools

| Tool | Purpose | Safety boundary |
|---|---|---|
| `select_chaos_candidates.py` | Rank YAML/test-node candidates from static and learned evidence | Ranking is not runtime proof |
| `decision_engine.py` | Apply auditable selection/defense/judgment rules | Frozen snapshots must not fall back to live knowledge |
| `query_knowledge_base.py` | Search cards and experience libraries | Read-only |
| `compare_selection_methods.py` | Compare method-level selections under a fixed pool | Preserve method-neutral candidate IDs |

## Runtime and Classification Tools

| Tool | Purpose | Required evidence |
|---|---|---|
| `runtime_applicability_gate.py` | Fail closed before an invalid or unsafe injection | namespace, selector, target, workload, and platform checks |
| `run_chaos_experiment.py` | Execute one bounded Chaos Mesh mutation lifecycle | injected, observed, recovered, cleaned |
| `run_stress_with_cgroup.py` | Run CPU stress with cgroup-v2 sampling | pressure counters and parent cleanup |
| `classify_runtime_result.py` | Normalize runner outcomes into comparable classes | baseline, response, latency, logs/resources, recovery |
| `run_stat_repeats.py` | Repeat a fixed experiment configuration | fixed warm-up, sample window, seed, and stopping rule |

Runtime modules are intentionally conservative: an unconfirmed injection is
not waited through as if it were an active fault, and cleanup failures are
reported rather than hidden.

## Knowledge and Reporting Tools

| Tool | Purpose |
|---|---|
| `validate_knowledge_base.py` | Validate card/index schema, source references, graphs, next evidence, and sensitive-value warnings |
| `knowledge_updater.py` | Backfill linked experiment evidence into SE/DP/JE libraries with an audit log |
| `package_report_evidence.py` | Produce a SHA-256 manifest for a report package |
| `issue_tracker.py` | Track issue drafts and submission states; it never submits remotely |

When adding a new module, start with a module docstring that states the paper
role, inputs, outputs, and side effects. Add a focused regression test under
`tools/tests/` for each new gate or classification branch.

## Open-discovery execution path

| Tool | Purpose | Side effect |
|---|---|---|
| `open_discovery_compiler.py` | Validate model hypotheses and produce canonical fault intents | JSON only; never executes kubectl |
| `open_discovery_mutation_compiler.py` | Resolve an accepted intent to a bounded PodChaos, NetworkChaos, or StressChaos manifest | Writes YAML and provenance; never calls kubectl |
| `runtime_applicability_gate.py` | Verify that the generated selector and Chaos Mesh environment are safe and applicable | Read-only kubectl checks |
| `run_chaos_experiment.py` | Apply, observe, recover, and remove one approved mutation | Calls kubectl only after the gate returns `ready_for_injection` |

The open path is therefore:

```text
model JSON -> open_discovery_compiler -> canonical intent
           -> open_discovery_mutation_compiler -> YAML + provenance
           -> runtime_applicability_gate -> run_chaos_experiment
```

The mutation compiler fails closed for configuration nodes, empty selectors,
missing workload mappings, namespace mismatches, unsupported edge/fault pairs,
and signature mismatches. Compose targets require an explicit runtime mapping
to a Kubernetes workload before they can produce YAML.
