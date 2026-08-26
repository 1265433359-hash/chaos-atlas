# ChaosAtlas Repository Architecture Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task with verification checkpoints.

**Goal:** Turn the current mixed ChaosAtlas checkout into a clean, independently runnable product tree while preserving historical experiments in a separately auditable evidence tree and keeping the existing CLI compatible.

**Architecture:** Product runtime code moves behind a `src/chaosatlas` package with thin compatibility wrappers under `tools/`. Versioned project profiles and fixtures remain in the product repository; generated runs, raw YAML, artifacts, reports, and external source snapshots are copied to an evidence tree with a manifest and SHA-256 inventory. A deterministic migration script and repository-boundary checks make the split repeatable and fail closed.

**Tech Stack:** Python 3.11+, `pathlib`, `hashlib`, `json`, `pytest`, PowerShell/Git.

---

### Task 1: Freeze the baseline and build the migration inventory

**Files:**
- Create: `scripts/repository_inventory.py`
- Create: `scripts/migration_manifest.py`
- Create: `docs/repository-migration/README.md`
- Create: `docs/repository-migration/migration-policy.json`
- Modify: `.gitignore`

- [ ] **Step 1: Add ignored migration working directories**

Add these exact entries to `.gitignore`:

```gitignore
.worktrees/
.migration/
ChaosAtlas-evidence/
```

- [ ] **Step 2: Write deterministic inventory helpers**

`scripts/repository_inventory.py` must expose `build_inventory(root, output)` and record relative path, category, size, SHA-256, tracked state, and a `sensitive` flag for each file. Categories must distinguish product code, tests, docs, project inputs, evidence, raw YAML, external source, runtime state, and unknown.

- [ ] **Step 3: Write the migration manifest generator**

`scripts/migration_manifest.py` must load the inventory and emit `migration-manifest.json` with source root, destination evidence root, counts by category, and every selected file. It must refuse to continue when a sensitive file is selected or a file has an unknown category.

- [ ] **Step 4: Run the baseline inventory**

Run:

```powershell
python scripts/repository_inventory.py --root . --output .migration/baseline-inventory.json
python scripts/migration_manifest.py --root . --inventory .migration/baseline-inventory.json --output .migration/migration-manifest.json
```

Expected: both commands exit 0; the manifest reports the current dirty files but selects no secrets, kubeconfig, virtual environments, or `.tmp-*` state for the product tree.

- [ ] **Step 5: Verify the inventory contract**

Run:

```powershell
python -m pytest tools/tests/test_repository_inventory.py -q
```

Expected: existing inventory tests pass and the new JSON files parse successfully.

### Task 2: Create the product package and compatibility layer

**Files:**
- Create: `src/chaosatlas/__init__.py`
- Create: `src/chaosatlas/orchestration/__init__.py`
- Create: `src/chaosatlas/adapters/__init__.py`
- Create: `src/chaosatlas/policies/__init__.py`
- Create: `src/chaosatlas/contracts/__init__.py`
- Create: `src/chaosatlas/knowledge/__init__.py`
- Create: `src/chaosatlas/runtime/__init__.py`
- Create: `src/chaosatlas/reporting/__init__.py`
- Create: `src/chaosatlas/_legacy.py`
- Create: `cli/chaosatlas.py`
- Create: `pyproject.toml`
- Modify: `tools/chaosatlas.py`
- Modify: `tools/run_closed_loop.py`
- Modify: `tools/chaosatlas_batch.py`

- [ ] **Step 1: Add package metadata and import path**

Configure a setuptools package named `chaosatlas` with a console script:

```toml
[project.scripts]
chaosatlas = "chaosatlas.cli:main"
```

- [ ] **Step 2: Add stable package namespaces**

Each namespace must be importable without importing Kubernetes clients or calling an LLM. `src/chaosatlas/__init__.py` must expose `__version__` only.

- [ ] **Step 3: Add legacy loader**

`src/chaosatlas/_legacy.py` must load a legacy module by absolute path, preserve `sys.argv`, and return its `main()` result. It must never copy secrets or alter the current working directory.

- [ ] **Step 4: Add the new CLI**

`src/chaosatlas/cli.py` must support:

```text
chaosatlas --help
chaosatlas run --profile PATH --mode dry-run [--evidence-root PATH]
chaosatlas inventory --profile PATH --output PATH
chaosatlas migrate --root PATH --evidence-root PATH --dry-run
```

The default `run` mode is dry-run and must not mutate Kubernetes or call an LLM.

- [ ] **Step 5: Convert old entry points to wrappers**

Each supported legacy file must contain only a short import-and-delegate wrapper to the new CLI or legacy loader. Existing command-line arguments must remain accepted.

- [ ] **Step 6: Verify package and compatibility imports**

Run:

```powershell
python -m compileall src cli tools/chaosatlas.py tools/run_closed_loop.py tools/chaosatlas_batch.py
python -m chaosatlas --help
python tools/chaosatlas.py --help
```

Expected: all commands exit 0 and both CLIs show the same supported command surface.

### Task 3: Move supported project profiles, fixtures, and documentation

**Files:**
- Create: `projects/`
- Create: `tests/fixtures/`
- Create: `docs/operations/`
- Create: `scripts/verify_product_boundary.py`
- Modify: `README.md`
- Modify: `.gitignore`

- [ ] **Step 1: Copy supported profiles**

Copy only versioned, secret-free profiles for Sock Shop, Online Boutique, OpenTelemetry Demo, P02, P03, P06, P08, P09, and NGINX Ingress into `projects/<project-id>/profile.json`. Preserve source path and SHA-256 in the migration manifest.

- [ ] **Step 2: Copy offline fixtures**

Copy `tools/tests/fixtures/chaosatlas_offline/` into `tests/fixtures/chaosatlas_offline/` and update tests to resolve fixtures from the new path first, with a temporary fallback to the old path.

- [ ] **Step 3: Add the product README**

Document one-command dry-run usage, live-mode safety gates, evidence-root configuration, compatibility commands, and the link/contract for `ChaosAtlas-evidence`.

- [ ] **Step 4: Add product-boundary checks**

`scripts/verify_product_boundary.py` must fail if product paths contain `artifacts/`, `raw_yaml/`, `.venv/`, kubeconfig names, private-key extensions, or files larger than 25 MiB unless explicitly allow-listed.

- [ ] **Step 5: Run product-boundary checks**

Run:

```powershell
python scripts/verify_product_boundary.py --root .
python -m pytest tools/tests -q --disable-warnings --maxfail=1
```

Expected: the boundary checker reports current legacy evidence as migration candidates, not product files; tests either pass or identify pre-existing failures without changing runtime behavior.

### Task 4: Build the evidence archive and verify hashes

**Files:**
- Create: `scripts/migrate_evidence.py`
- Create: `scripts/verify_evidence_archive.py`
- Create: `ChaosAtlas-evidence/README.md`
- Create: `.migration/evidence-migration.json`

- [ ] **Step 1: Define evidence selection**

Select tracked and explicitly listed untracked evidence categories: `artifacts/`, `raw_yaml/`, `analysis_outputs/`, `reporting/`, experiment manifests, generated reports, and external source snapshots. Exclude credentials, kubeconfig, virtual environments, `.tmp-*`, caches, and local diagnostics unless explicitly listed.

- [ ] **Step 2: Copy evidence without deleting source files**

`migrate_evidence.py` must copy files to:

```text
ChaosAtlas-evidence/
projects/
experiment-manifests/
inputs/
runs/
reports/
knowledge-snapshots/
external-sources/
```

Every copied file must retain source-relative path metadata and SHA-256. The first run must be dry-run; deletion is not implemented by this script.

- [ ] **Step 3: Normalize run manifests**

For every recognized run directory, emit `manifest.json` with project, run ID, source commit, policy IDs, executor, relative artifact paths, and hashes. If a run cannot be normalized, mark it `unclassified` and fail verification rather than guessing.

- [ ] **Step 4: Verify archive completeness**

Run:

```powershell
python scripts/migrate_evidence.py --root . --evidence-root ChaosAtlas-evidence --manifest .migration/evidence-migration.json --dry-run
python scripts/migrate_evidence.py --root . --evidence-root ChaosAtlas-evidence --manifest .migration/evidence-migration.json
python scripts/verify_evidence_archive.py --root . --evidence-root ChaosAtlas-evidence --manifest .migration/evidence-migration.json
```

Expected: source and destination selected-file counts match; all SHA-256 values match; no sensitive file is copied; unclassified files are reported and cause a non-zero exit.

### Task 5: Publish clean product and evidence refs without history rewriting

**Files:**
- Create: `docs/repository-migration/release-manifest.json`
- Create: `docs/repository-migration/remote-publish-checklist.md`
- Modify: `docs/repository-migration/README.md`

- [ ] **Step 1: Create local release refs**

Create local branches `archive/legacy-2026-08-26`, `codex/repository-architecture-redesign`, and a clean product release branch from the verified product tree. Do not force-push or delete any existing branch.

- [ ] **Step 2: Generate release manifest**

Record source branch, product commit, evidence manifest SHA-256, test commands, and remote target names in `release-manifest.json`.

- [ ] **Step 3: Check remote permissions**

Run:

```powershell
git ls-remote origin
git push --dry-run origin HEAD:refs/heads/codex/repository-architecture-redesign
```

If push is denied, keep the local refs and report the exact blocker; do not rewrite history or claim remote publication.

- [ ] **Step 4: Publish only after verification**

Push the product release branch and the evidence repository branch only after Tasks 1-4 pass. The existing `main` branch remains unchanged until the user explicitly approves switching the default branch.

### Task 6: Final end-to-end verification and handoff

**Files:**
- Create: `docs/repository-migration/final-verification.md`
- Create: `scripts/run_repository_acceptance.py`
- Modify: `.planning/repository-architecture-redesign/task_plan.md`
- Modify: `.planning/repository-architecture-redesign/progress.md`
- Modify: `.planning/repository-architecture-redesign/findings.md`

- [ ] **Step 1: Verify all package imports and CLI modes**

Run:

```powershell
python -m compileall src cli tools
python -m chaosatlas --help
python -m chaosatlas run --profile projects/sock-shop/profile.json --mode dry-run --evidence-root ChaosAtlas-evidence
python -m chaosatlas run --profile projects/online-boutique/profile.json --mode dry-run --evidence-root ChaosAtlas-evidence
```

- [ ] **Step 2: Verify replay and resume contracts**

Run the existing checkpoint, policy, RCA, knowledge, and cleanup contract tests plus a fixture replay. Confirm completed candidates are not injected twice.

- [ ] **Step 3: Run repository acceptance**

`run_repository_acceptance.py` must execute boundary, manifest, hash, CLI, and test checks and emit a machine-readable report with `success`, `partial`, `failed`, or `blocked`.

- [ ] **Step 4: Review Git diff and hygiene**

Run:

```powershell
git diff --check
git status --short
git ls-files | Select-String '(^|/)(artifacts|raw_yaml|\.venv|\.tmp-)'
```

Expected: product release files contain no forbidden evidence/state paths; any remaining legacy paths are explicitly documented as archive candidates.

- [ ] **Step 5: Record final state**

Update the persistent plan files with exact counts, test results, release refs, remote push status, and any blocked publication step. Only mark a stage complete when its verification command has passed.

