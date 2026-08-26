# Phase 6 Productized Live Closed Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为现有 ChaosAtlas 单候选运行补齐统一的 Phase 6 执行契约、产物索引和审计汇总。

**Architecture:** 新增纯函数模块负责构造 execution contract、artifact index 和 phase6 audit；`run_closed_loop` 在创建 manifest 时写入 contract，在所有正常/阻断/异常出口写入最终 audit。现有 discovery、executor、RCA 和 promotion 实现保持不变。

**Tech Stack:** Python 3 标准库、JSON、pytest、现有 ChaosAtlas run contracts。

---

### Task 1: Add the audit helpers

**Files:**
- Create: `tools/phase6_audit.py`
- Test: `tools/tests/test_phase6_audit.py`

- [x] **Step 1: Write the four audit contract tests.**
- [x] **Step 2:** Run the RED test and verify collection fails because `tools.phase6_audit` is absent.
- [x] **Step 3:** Implement `build_execution_contract`, `build_artifact_index`, and `write_phase6_audit` with the Python standard library.
- [x] **Step 4:** Run the GREEN test and verify all four tests pass.

### Task 2: Integrate the contract into the main run

**Files:**
- Modify: `tools/chaosatlas.py`
- Test: `tools/tests/test_chaosatlas.py`

- [x] **Step 1:** Add the dry-run and live-preflight audit assertions to `tools/tests/test_chaosatlas.py`.
- [x] **Step 2:** Run the integration RED test and verify both assertions fail because the audit files are absent.
- [x] **Step 3:** Import the audit helpers, write `execution_contract.json`, and finalize audit on normal, blocked and exception paths.
- [x] **Step 4:** Run the integration tests and verify the complete `test_chaosatlas.py` file passes.

### Task 3: Verify three-project Phase 6 replay and static hygiene

**Files:**
- Modify: `progress.md`
- Modify: `task_plan.md`

- [x] **Step 1:** Run the Phase 6 focused suite; result `42 passed`.
- [x] **Step 2:** Run the three-project dry-run replay; all audits are `dry_run_ready` with non-empty artifact indexes.
- [x] **Step 3:** Run compileall and git diff check; both exited 0.
- [x] **Step 4:** Record the verified boundary and the isolated live canary in `progress.md` and `task_plan.md`.
