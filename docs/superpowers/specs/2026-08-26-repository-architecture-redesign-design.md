# ChaosAtlas Repository Architecture Redesign

## 1. Goal

Restructure the local ChaosAtlas workspace and the GitHub product repository so that product code, project onboarding, experiment definitions, runtime evidence, external source trees, and machine-local state have separate lifecycle boundaries.

The result must keep the existing closed-loop capability usable through one command while making the product repository independently readable, testable, and publishable.

## 2. Scope

### In scope

- Reorganize the product code currently concentrated under `tools/`.
- Separate experiment inputs, runtime evidence, reports, and external sources into a dedicated evidence archive repository.
- Preserve a compatibility path for existing `tools/chaosatlas.py` and supported experiment commands during migration.
- Define a stable run manifest, evidence layout, provenance links, and resume behavior.
- Publish a clean product branch as the GitHub `main` product line after verification.
- Preserve the current legacy branch as a read-only rollback reference until archive integrity is accepted.

### Out of scope

- Rewriting the closed-loop algorithm, candidate policy, stop policy, RCA method, or executor behavior.
- Re-running Kubernetes experiments as part of directory migration.
- Deleting historical evidence before it has been copied and hash-verified.
- Automatically force-pushing or deleting remote branches.
- Moving secrets, kubeconfigs, virtual environments, or machine-local state into either repository.

## 3. Target repositories

### Product repository: `ChaosAtlas`

```text
ChaosAtlas/
├─ src/chaosatlas/
│  ├─ orchestration/       # one-command closed-loop orchestration
│  ├─ adapters/             # Kubernetes, native, and server deployment detection
│  ├─ policies/             # candidate, ranking, stop, and feedback policies
│  ├─ contracts/            # profile, evidence, RCA, and knowledge contracts
│  ├─ knowledge/            # retrieval, validation, promotion, and regression intents
│  ├─ runtime/              # baseline, injection, observation, recovery, cleanup
│  └─ reporting/            # summaries, coverage, issue drafts, and acceptance reports
├─ cli/                     # installed `chaosatlas` command
├─ projects/                # versioned project profiles and sanitized onboarding inputs
├─ tests/
│  ├─ unit/
│  ├─ contract/
│  ├─ integration/
│  └─ fixtures/
├─ docs/
├─ scripts/                 # thin wrappers, checks, and migration utilities
├─ examples/
├─ pyproject.toml
└─ README.md
```

The product repository contains no bulk runtime evidence, upstream source checkout, kubeconfig, credential, virtual environment, or machine-local state.

### Evidence repository: `ChaosAtlas-evidence`

```text
ChaosAtlas-evidence/
├─ projects/
├─ experiment-manifests/
├─ inputs/
├─ runs/
├─ reports/
├─ knowledge-snapshots/
├─ external-sources/
└─ README.md
```

The archive repository is the source of truth for historical experiment inputs, runtime evidence, RCA artifacts, generated reports, and external project snapshots. Its expected remote name is `chaos-atlas-evidence`; the remote URL is configured before the publication phase.

## 4. Product code boundaries

The current `tools/` modules are moved by responsibility, not by historical filename:

- `chaosatlas.py`, `chaosatlas_batch.py`, `run_closed_loop.py`, and lifecycle orchestration move to `src/chaosatlas/orchestration/`.
- Kubernetes project adapters, lifecycle executors, native executors, NGINX contracts, and executor registry move to `src/chaosatlas/adapters/`.
- Candidate generation, hypothesis registration, ranking, stop, feedback, and registry signal modules move to `src/chaosatlas/policies/`.
- Profile, evidence, RCA, recovery, feedback, and experiment schemas move to `src/chaosatlas/contracts/`.
- Knowledge retrieval, migration audit, weakness promotion, and knowledge updater modules move to `src/chaosatlas/knowledge/`.
- Evidence collectors, applicability gates, runtime state handling, recovery, and cleanup coordination move to `src/chaosatlas/runtime/`.
- Problem identity, coverage, acceptance, issue, and summary generators move to `src/chaosatlas/reporting/`.

`tools/` remains temporarily as a compatibility layer. Each retained entry point is a thin wrapper that imports the new package and has no independent business logic. One-time experiment runners are retained only when they are supported product workflows; historical runners and their inputs move to the evidence repository.

## 5. Data flow and run contract

The logical flow remains:

```text
project profile
  -> read-only onboarding and full portrait
  -> architecture/config/dependency/runtime hypotheses
  -> value ranking and stop budget
  -> guarded execution
  -> evidence, RCA, recovery, cleanup
  -> outcome classification
  -> knowledge validation and promotion
  -> regression intents
```

Each invocation writes to one immutable run directory:

```text
runs/<project>/<run-id>/
├─ manifest.json
├─ checkpoints/
├─ inventory/
├─ hypotheses/
├─ selection/
├─ lifecycle/
├─ evidence/
├─ rca/
├─ cleanup/
├─ knowledge/
├─ regression/
└─ summary.md
```

`manifest.json` records:

- product commit and profile version;
- project, namespace, and cluster-context summary;
- candidate and stop policy identifiers and budget;
- candidate decisions and per-round statuses;
- executor, Oracle, recovery, and cleanup contracts;
- relative artifact paths and SHA-256 values;
- whether Kubernetes mutation, LLM calls, or formal knowledge writes occurred.

Knowledge cards reference archive `run-id` and artifact hashes rather than copying raw evidence into the product repository. A run can be resumed only from its own checkpoints, and a completed candidate is never injected again during resume.

## 6. Compatibility and configuration

- Existing `python tools/chaosatlas.py run ...` remains valid during the migration window.
- New installation exposes a `chaosatlas` CLI that uses the same orchestration contracts.
- The evidence root is configurable and defaults to the sibling `ChaosAtlas-evidence` directory.
- Compatibility wrappers emit a deprecation notice only after the new CLI has passed the three-project offline replay gate.
- Path references use project/run IDs and manifest-relative paths; no consumer relies on a historical absolute path.

## 7. Safety and rollback

Migration proceeds in an isolated worktree and in this order:

1. Snapshot current Git refs and generate a complete inventory with source class, size, and SHA-256.
2. Copy evidence and external sources to the archive repository and verify counts and hashes.
3. Build the curated product tree and preserve compatibility wrappers.
4. Run structural, behavioral, security, and archive-integrity verification.
5. Push the evidence repository, then push the clean product branch.
6. Set the verified product branch as the GitHub default only after review.

The current legacy branch is frozen as `archive/legacy-2026-08-26` and remains the rollback reference. No destructive delete, force-push, or branch removal is performed by default. Any later history rewrite or repository replacement requires a separate explicit approval.

The migration fails closed when a file is unclassified, a hash differs, a path reference is broken, a credential-like file is encountered, or archive completeness cannot be proven. Historical `blocked`, `unsupported`, and `cleanup_failed` results remain evidence and cannot be promoted to knowledge by migration.

## 8. Verification and acceptance

### Product verification

- Compile all new package and CLI modules.
- Run the full migrated test suite.
- Verify CLI help, dry-run, resume, and error exit codes.
- Replay Sock Shop, Online Boutique, and P02 through the same offline orchestrator.
- Verify old and new CLI paths produce equivalent dry-run contracts.

### Archive verification

- Compare pre- and post-migration inventory counts.
- Verify SHA-256 for all tracked evidence and all selected untracked evidence.
- Validate every run manifest and its referenced paths.
- Randomly restore runs from manifest and verify input, evidence, RCA, and knowledge links.
- Resume a fixture run and prove completed candidates are not repeated.

### Security and repository-boundary verification

- Confirm product Git tracking excludes artifacts, raw YAML bulk inputs, credentials, kubeconfigs, virtual environments, and local state.
- Run sensitive-pattern and path-reference scans.
- Confirm default commands do not call an LLM or mutate Kubernetes.
- Run `git diff --check` and repository hygiene checks.

### Remote verification

- Product branch contains only allowed product directories and documentation.
- Evidence repository can be cloned and independently validated.
- Product README links to archive and reproduction entry points.
- Legacy branch remains available and matches the recorded rollback ref.
- Remote branch pointers match the publication manifest.

The redesign is accepted only when the product repository runs independently, the evidence repository is auditable, the one-command workflow remains available, no historical evidence is lost, and no sensitive local data is published.

## 9. Phased implementation

- Phase 1: isolated worktree, inventory, backup refs, and archive migration tooling.
- Phase 2: package the product core and add compatibility wrappers.
- Phase 3: migrate project profiles, fixtures, supported runners, and documentation.
- Phase 4: migrate evidence and external sources; validate manifests and hashes.
- Phase 5: publish evidence repository and clean product branch; perform remote review.
- Phase 6: run full verification and document the final operating model.
