# Train Ticket Test-Node Catalog

This directory contains the first static, evidence-labelled catalog for the selected Train Ticket project.

## Scope

- YAML corpus: 1,935 files under `raw_yaml/`.
- Train Ticket subset: 54 files with `metadata.namespace: train-ticket`.
- Project revision: `FudanSELab/train-ticket` at commit `313886e99befb94be6cd45f085c98e0019f59829`.
- No deployment or chaos injection was performed to create these artifacts.

## Files

- `yaml_inventory.csv`: one row per YAML, SHA-256, parsed identity, spec keys, test nodes, risk flags and semantic shape issues.
- `test_node_catalog.json`: corpus-wide test-node frequency, kind distribution and co-occurrence pairs.
- `train_ticket_test_slices.json`: one static slice per Train Ticket YAML, including selector-to-Deployment/Service matches, source-module and function candidates, and evidence status.
- `train_ticket_test_slices_refined.json`: source-level candidate functions, static call edges, control/data signals, and expanded Workflow leaf slices.
- `refined_report.md`: human-readable report with example local slice and Workflow blast-radius analysis.
- `train_ticket_service_graph.json` and `train_ticket_test_slices_graph.json`: static cross-service candidates and test-node slices with downstream calls.
- `service_graph_report.md`: explanation of static service-call evidence and runtime verification gap.
- `summary.json`: machine-readable counts for this run.
- `paper_prep_stage_summary.md`: evidence-backed stage summary, conservative paper claims, limitations and next-stage acceptance criteria.

## Initial observations

- Top corpus test nodes: `stress_cpu` (230), `pod_pod-kill` (220), `network_delay` (213), `stress_memory` (142), `network_partition` (99).
- Train Ticket test nodes: `http_replace_response` (15), `network_delay` (15), `http_delay` (14), `stress_cpu` (8), `http_abort` (1), plus one Workflow with composite templates.
- All 1,935 documents are YAML top-level mappings. 34 files have semantic shape warnings, including non-string metadata, selector values, duration/action values, or invalid HTTP target shapes.
- Static selector-to-Deployment matching is available for most service-targeted samples. Function candidates are source-level candidates only; runtime reachability and trace edges remain pending.
- Static mapping coverage: 53/54 samples have a selector-to-Deployment/Service match; 49/54 have production source-function candidates. The one unmapped sample is the composite `Workflow`, which needs template expansion before target mapping.

## Evidence labels

- `static_manifest_match`: selector matches a Deployment/Service label in repository manifests.
- `static_source_candidate`: a function/module was found by source scan; this is not proof of runtime reachability.
- `pending_runtime_baseline`: no live baseline or trace has been captured.
- `unverified`: no reliable static mapping was found.
