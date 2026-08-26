# P03/P06 Runtime Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce auditable, namespace-local P03 and P06 runtime profiles that are ready for server-side dry-run once their actual application images are available, without claiming runtime readiness from static metadata alone.

**Architecture:** Add a small fail-closed profile builder that consumes explicit image digests and a selected dependency profile, then emits Kubernetes YAML plus gate evidence into a new revisioned directory. P03 uses Saleor plus Postgres and Valkey; P06 uses Directus plus one Postgres profile. The builder rejects mutable images, missing resource bounds, missing oracle contracts, forbidden services, and non-local namespaces.

**Tech Stack:** Python, pytest, PyYAML, Kubernetes Deployment/Service manifests, SHA-256 evidence.

---

### Task 1: Lock the readiness contract with tests

**Files:**
- Create: `tools/tests/test_p03_p06_runtime_profiles.py`

- [ ] **Step 1: Write failing tests** for immutable image validation, namespace-local manifests, resource bounds, and project-specific service selections.
- [ ] **Step 2: Run the focused tests** and confirm they fail because the builder does not exist.

### Task 2: Implement the bounded profile builder

**Files:**
- Create: `tools/prepare_p03_p06_runtime_profiles.py`

- [ ] **Step 1: Implement explicit project specifications** for P03/P06, including source commit/tree evidence, selected services, health endpoints, read-only business oracles, and resource requests/limits.
- [ ] **Step 2: Require every emitted image reference to use `@sha256:` and reject mutable tags.
- [ ] **Step 3: Emit revisioned profile artifacts without overwriting non-empty directories.
- [ ] **Step 4: Run focused tests and the static gate tests.

### Task 3: Generate and inspect new preparation evidence

**Files:**
- Create: `artifacts/experiments/chaosatlas_10_projects/runtime_profiles/P03-r4/`
- Create: `artifacts/experiments/chaosatlas_10_projects/runtime_profiles/P06-r4/`

- [ ] **Step 1: Generate profiles using only verified image digests or fail closed with a precise missing-image reason.
- [ ] **Step 2: Validate emitted YAML structurally and scan for secrets and forbidden namespaces/services.
- [ ] **Step 3: Keep server-side dry-run marked pending until an authorized cluster command is executed.

### Task 4: Review repository state

- [ ] **Step 1: Confirm only the new builder, tests, plan, and generated P03/P06 evidence are selected for any future commit.
- [ ] **Step 2: Report whether each project is dry-run-ready or still blocked on an external prerequisite.
