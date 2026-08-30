# NetworkChaos Expansion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 `network_bandwidth`、`network_duplicate` 和 `network_corrupt` 接入真实 live scenario builder，并以证据门禁决定是否升级 catalog 状态。

**Architecture:** 复用现有 scenario compiler 和 `KubernetesLifecycleExecutor`，只在 live builder 中增加确定性参数和动作映射。catalog 在真实 canary 通过前保持 `planned`；所有结果必须经过独立业务 Oracle、恢复、清理和 attestation 校验。

**Tech Stack:** Python 3.12、PyYAML、Chaos Mesh NetworkChaos、pytest、kubectl。

---

### Task 1: Extend live scenario construction

**Files:**
- Modify: `tools/_legacy_chaosatlas.py`
- Test: `tests/test_extended_network_faults.py`

- [x] **Step 1: Write failing tests** for live scenario parameters and action mapping.
- [x] **Step 2: Run focused tests and confirm the unsupported-family failure.**
- [x] **Step 3: Add deterministic defaults:** bandwidth `rate=1mbps, limit=1000, buffer=1000`; duplicate/corrupt `20%`, correlation `100`.
- [x] **Step 4: Run focused tests and the existing lifecycle contract suite.**

### Task 2: Validate live canary contract

**Files:**
- Modify: `tests/test_network_dns_http_live_contract.py`
- Modify: `tools/fault_catalog.py` only after live evidence

- [x] **Step 1: Add hook tests asserting all three families produce valid attestations.**
- [x] **Step 2: Run tests and verify no cleanup failure can be promoted.**

### Task 3: Dry-run and authorized canaries

**Files:**
- Modify: `docs/ACCEPTANCE_32_FAULTS.md`
- Evidence: `.runs/acceptance-network-expansion-<project>-<fault>-20260827/`

- [x] **Step 1: Generate dry-run manifests for all three families on the three profiles.**
- [x] **Step 2: Run one canary per family in an authorized namespace after preflight.** (completed for Nginx, Sock Shop and Online Boutique)
- [x] **Step 3: Require `live_completed`, valid attestation, RCA output, recovery and verified cleanup.**
- [x] **Step 4: Keep catalog status `planned` for any family lacking complete evidence.**

### Task 4: Regression checkpoint

- [x] Run the full pytest suite and `git diff --check`.
- [x] Record evidence paths and remaining boundaries in the acceptance document.

## Execution error log

| Error | Attempts | Resolution |
| --- | ---: | --- |
| External archive profile write approval timed out | 1 | Resolved by using the already archived dependency path; no new root-level temporary directory was created |
