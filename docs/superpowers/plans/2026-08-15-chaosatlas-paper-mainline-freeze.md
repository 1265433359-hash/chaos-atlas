# ChaosAtlas Paper Mainline Freeze Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the confirmed real-project capability narrative the repository's paper-facing mainline while logically freezing obsolete comparison tracks without moving evidence files.

**Architecture:** Add one canonical mainline summary and classify existing reports through the archive map and experiment catalog. Update repository entry points to link to the canonical summary and explicitly exclude same-pool and adapter results from the mainline. Preserve all artifact paths and current user changes.

**Tech Stack:** Markdown documentation, existing artifact indexes, PowerShell read-only checks, `rg` consistency checks.

---

### Task 1: Add the canonical paper-mainline summary

**Files:**
- Create: `docs/CHAOSATLAS_PAPER_MAINLINE.md`

- [ ] **Step 1: Record the four-stage research narrative**

Write the initial architecture, three-project validation, Sock Shop full-vs-ablation improvement stage, and future official ChaosEater comparison as separate sections.

- [ ] **Step 2: Record the current Sock Shop headline with denominator boundaries**

State the user-confirmed `114/70/10` full-method and `12/2` ablation headline, while requiring machine-readable ledgers to define exact execution, repeat, and review fields.

- [ ] **Step 3: Add paper claim rules and excluded tracks**

Explicitly exclude same-pool/preselected data from the mainline and keep pending review/root-cause boundaries visible.

### Task 2: Update repository entry points

**Files:**
- Modify: `README.md`
- Modify: `docs/PROJECT_SUMMARY.md`
- Modify: `docs/EXPERIMENT_CATALOG.md`

- [ ] **Step 1: Link the canonical mainline from the README**

Make the four-stage narrative the first paper-preparation entry point.

- [ ] **Step 2: Replace stale active-track language in the project summary**

Describe the three-project validation and Sock Shop ablation as the active paper path; move same-pool and unfinished official ChaosEater wording into frozen/future boundaries.

- [ ] **Step 3: Split the experiment catalog into mainline and frozen tracks**

Keep historical rows and paths, but label them as frozen supplementary material so they cannot be mistaken for current mainline measurements.

### Task 3: Make archive classification explicit

**Files:**
- Modify: `docs/ARCHIVE_MAP.md`
- Modify: `docs/ARCHIVE_CLEANUP.md`

- [ ] **Step 1: Define mainline/frozen/future status vocabulary**

Add a three-way classification that preserves paths and distinguishes paper use from audit retention.

- [ ] **Step 2: Add no-move/no-delete rules for experiment evidence**

Document that freezing is logical and that runtime artifacts, hashes, prompts, and ledgers remain at their original locations.

### Task 4: Verify narrative consistency

**Files:**
- Read-only checks across `README.md`, `docs/`, `reporting/`, and relevant experiment reports.

- [ ] **Step 1: Search for same-pool claims in paper-facing entry points**

Confirm that any remaining same-pool numbers are marked frozen and are not presented as the mainline result.

- [ ] **Step 2: Search for completed ChaosEater claims**

Confirm that official full ChaosEater remains future work and adapter material is not called the official method.

- [ ] **Step 3: Check the working tree**

Confirm only the intended documentation files changed and all pre-existing user artifacts remain untouched.
