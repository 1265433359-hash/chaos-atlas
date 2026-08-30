# ChaosAtlas Paper Academic Normalization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create an academically normalized DOCX revision while preserving the existing paper structure, formulas, figures, tables, and experimental counts.

**Architecture:** Use a focused `python-docx` transformation script that reads the current end-to-end revision, applies indexed paragraph and table-cell replacements, and saves a new output file. Verify the resulting text programmatically, inspect embedded figures, and run DOCX rendering with a fallback structural audit if the renderer is unavailable.

**Tech Stack:** Bundled Python runtime, `python-docx`, OOXML/DOCX renderer, PowerShell verification.

---

### Task 1: Implement terminology and claim normalization

**Files:**
- Create: `scripts/normalize_paper_academic.py`
- Read: `面向真实微服务项目的证据约束混沌测试方法-端到端修订版.docx`
- Create: `面向真实微服务项目的证据约束混沌测试方法-学术规范版.docx`

- [ ] Apply the approved terminology hierarchy: “稳定复现的业务韧性问题族” for repeated business-oracle failures; “业务韧性缺陷族” only where evidence is confirmed; “故障类型/故障类别/故障族” at their respective levels.
- [ ] Replace colloquial or ambiguous wording with “适用性门禁”“两次独立重复运行”“残留影响排除窗口（washout window）”“可复现且可追溯”.
- [ ] Soften unsupported causal claims and reframe Full/Ablation and ChaosEater comparison boundaries without changing numbers.
- [ ] Update result tables and Issue wording consistently.

### Task 2: Run structural and textual verification

**Files:**
- Read: `面向真实微服务项目的证据约束混沌测试方法-学术规范版.docx`

- [ ] Extract paragraphs and tables with UTF-8 output and assert prohibited primary terms are absent from body text.
- [ ] Assert required terms and count values remain present.
- [ ] Assert formulas, images, comments, and tracked-change counts are unchanged unless intentionally documented.

### Task 3: Render and inspect the deliverable

**Files:**
- Output QA directory: `.academic_review_render/`

- [ ] Run the packaged DOCX renderer with the bundled Python runtime.
- [ ] If PDF conversion is unavailable, use LibreOffice or structural fallback and report the limitation.
- [ ] Inspect all generated pages or embedded figures for clipping, overlap, and table-label ambiguity.
