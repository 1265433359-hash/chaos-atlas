# ChaosAtlas Repository Organization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Classify the mixed ChaosAtlas repository, document safe handling rules, add a reproducible inventory command, and prepare a selective GitHub commit without deleting or moving experiment data.

**Architecture:** Keep current source paths stable for this phase. Add documentation and a read-only inventory utility that classifies paths by lifecycle and reports tracked/untracked size and sensitive-file exclusions. Expand `.gitignore` only for machine-local state and generated temporary output.

**Tech Stack:** Python 3 standard library, Markdown, Git, PowerShell verification.

---

### Task 1: Record the repository map and cleanup policy

**Files:**
- Create: `docs/REPOSITORY_MAP.md`
- Create: `docs/REPOSITORY_CLEANUP_POLICY.md`

- [ ] **Step 1: Write the repository map**

Document the target logical tree, map current directories to categories, and list the mainline entry points.

- [ ] **Step 2: Write the cleanup policy**

Define tracked, curated-evidence, local-only, archive, and never-commit classes. State that no current artifact is deleted or moved by this change.

### Task 2: Add a deterministic read-only inventory tool

**Files:**
- Create: `tools/repository_inventory.py`
- Create: `tools/tests/test_repository_inventory.py`

- [ ] **Step 1: Write failing tests**

Cover category classification, stable ordering, byte/file counts, and sensitive-name detection without reading file contents.

- [ ] **Step 2: Implement the CLI**

Provide `python tools/repository_inventory.py --root . --output <path>`; emit JSON with schema version, category counts, tracked/untracked counts, and excluded local patterns.

- [ ] **Step 3: Run focused tests**

Run `pytest tools/tests/test_repository_inventory.py -q --basetemp .pytest-tmp-repository-inventory` and require all tests to pass.

### Task 3: Harden local-only ignore rules

**Files:**
- Modify: `.gitignore`

- [ ] **Step 1: Add only explicit machine-local patterns**

Ignore notification outbox, local virtual environments, root caches, and generated inventory output. Do not ignore source, tests, curated reports, or raw input snapshots.

- [ ] **Step 2: Verify existing tracked files are unaffected**

Run `git check-ignore -v` for representative temporary and mainline paths and inspect `git status --short`.

### Task 4: Generate and review the inventory

**Files:**
- Generate local-only: `.tmp-repository-inventory.json`
- Update: `progress.md`, `findings.md`, `task_plan.md`

- [ ] **Step 1: Run the inventory**

Generate the report without reading credential contents and record counts and category boundaries.

- [ ] **Step 2: Review sensitive and large-file candidates**

Use filename/path checks and Git object size checks; do not print secrets or full private files.

### Task 5: Validate and selectively commit

**Files:**
- Selectively stage only documentation, inventory tool/tests, ignore rules, and required plan updates.

- [ ] **Step 1: Run focused and full verification**

Run the inventory tests, `python -m compileall -q tools`, and the full `tools/tests` suite with a repository-local basetemp.

- [ ] **Step 2: Review staged file list**

Use `git diff --cached --stat` and `git diff --cached --name-only`; confirm no credentials, environments, caches, or bulk runtime artifacts are staged.

- [ ] **Step 3: Create a normal commit**

Commit with message `docs: define repository organization and inventory policy`.

- [ ] **Step 4: Push the current branch**

Run `git push origin remediation/2026-08-09-review`. If HTTPS credentials fail, preserve the local commit and report the exact authentication blocker without rewriting history.

