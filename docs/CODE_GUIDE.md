# Code and Tool Guide

This guide is the code-comment index for the repository. Python modules carry
their detailed docstrings; this file records the intended ownership and side
effects so a future contributor can choose the correct entry point.

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

