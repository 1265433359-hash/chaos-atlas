# ChaosAtlas Repository Organization Design

## Goal

Make the repository understandable as a reusable product while preserving existing experiment evidence, historical paths, and reproducibility.

## Principles

1. Product code and tests are first-class tracked source.
2. Project profiles and authored experiment inputs are versioned and reviewable.
3. Runtime evidence is retained with provenance, but bulk/generated output is not automatically committed.
4. Local caches, credentials, environments, and upstream source copies never enter the main repository snapshot.
5. The first change is classification and policy, not a destructive directory migration.

## Logical Layers

- `tools/`: current implementation and compatibility entry points.
- `projects/`: project profiles, business oracles, and onboarding metadata.
- `experiments/`: authored scenarios, manifests, and protocol inputs.
- `artifacts/`: generated run evidence, RCA, acceptance, and knowledge outputs.
- `knowledge/`: reusable schemas, cards, promotion history, and regression intents.
- `reporting/`: human-review materials and issue drafts.
- `docs/`: architecture, operations, methods, research, and plans.
- `raw_yaml/`: read-only source snapshots with provenance.
- `governance/`: repository and data handling rules.
- `vendor/`: external source copies, excluded from product source.

## Migration Boundary

Existing files remain in place during this phase. New output should follow the logical layers; path moves require a separate migration with reference updates and a full regression pass.

## GitHub Boundary

The main branch should contain source, tests, profiles, authored inputs, documentation, governance, and selected evidence/reporting. Full logs, repeated runtime directories, local environments, credentials, caches, and external repositories stay local or move to archive/object storage referenced by a manifest and hash.

