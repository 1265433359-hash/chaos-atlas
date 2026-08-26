# ChaosAtlas Method Hardening Implementation Plan

> **For agentic workers:** Implement task-by-task with tests first and keep each artifact append-only.

**Goal:** Make the closed-loop method distinguish hypotheses, executable candidates, causal problems and knowledge, report comparable cross-project coverage, and provide a safe extension point for new fault families.

**Architecture:** Add a deterministic run-artifact normalizer that derives causal and issue identities without changing existing RCA claims. Add a read-only coverage report CLI that consumes completed artifacts and excludes invalid or blocked runs. Extend the candidate/executor contract registry so new methods are explicitly represented as pending until their executor, evidence, recovery and cleanup contracts are complete.

**Tech Stack:** Python 3, JSON artifacts, pytest, existing ChaosAtlas policy and lifecycle contracts.

---

### Task 1: Normalize problem identity

**Files:**
- Create: `tools/problem_identity.py`
- Test: `tools/tests/test_problem_identity.py`

- [complete] Write tests for stable issue identity, causal clustering across parameter changes, and rejection of incomplete lifecycle evidence.
- [complete] Run the focused tests and verify they fail because the module does not exist.
- [complete] Implement pure functions that read a run summary/RCA payload and return `eligible`, `causal_identity`, `causal_cluster_id`, and `issue_id`.
- [complete] Ensure issue identity excludes prompt wording and run IDs, while retaining project, target, fault domain, oracle and recovery contract.
- [complete] Run focused tests and the existing causal identity tests.

### Task 2: Build cross-project coverage report

**Files:**
- Create: `tools/coverage_report.py`
- Test: `tools/tests/test_coverage_report.py`

- [complete] Write tests using fixture run artifacts for project, family, valid execution, unique issue and blocked-run counts.
- [complete] Run focused tests to verify the expected failure.
- [complete] Implement a read-only recursive artifact scanner and deterministic report grouped by project and fault family.
- [complete] Exclude `environment_blocked`, `method_invalid`, incomplete attestation, unsupported results and unconfirmed RCA from confirmed-problem counts.
- [complete] Include both strict weakness-ID counts and causal issue counts so the report does not conflate methods with problems.
- [complete] Run focused tests and generate a report from current artifacts without modifying them.

### Task 3: Extend fault-family contract boundary

**Files:**
- Modify: `tools/nginx_candidate_contracts.py`
- Modify: `tools/tests/test_nginx_candidate_contracts.py`
- Create: `tools/fault_executor_registry.py`
- Test: `tools/tests/test_fault_executor_registry.py`

- [complete] Write tests proving every declared family has an executor status and that pending methods fail closed before live mutation.
- [complete] Run focused tests and verify the new registry tests fail.
- [complete] Implement a registry that maps the six ready families and four pending families to explicit statuses and required contracts.
- [complete] Keep `network_delay`, `backend_pod_kill`, `config_reload`, and `replica_reduction` non-executable until a real executor is registered.
- [complete] Run focused tests, all related policy/lifecycle tests, compileall, and a dry-run smoke check.

### Final Verification

- [complete] Run `pytest -q tools/tests/test_problem_identity.py tools/tests/test_coverage_report.py tools/tests/test_fault_executor_registry.py tools/tests/test_causal_identity.py tools/tests/test_nginx_candidate_contracts.py`.
- [complete] Run the full `tools/tests` suite with the repository-local basetemp directory.
- [complete] Confirm no artifact or formal knowledge root was overwritten and no live mutation occurred.
