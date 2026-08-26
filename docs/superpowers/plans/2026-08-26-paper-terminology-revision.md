# 论文术语与学术表达修订 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 生成保留原始研究事实与版式结构的论文术语学术化修订版 DOCX。

**Architecture:** 以 `python-docx` 读取原稿并建立段落、表格和运行级文本替换流程。术语映射先作用于正文和表格，再对摘要、章节标题和关键词做定向润色，最后输出新文件并使用文档渲染器进行视觉验证。

**Tech Stack:** Python、python-docx、Bundled `render_docx.py`、PowerShell。

---

### Task 1: 建立术语映射与文本修订脚本

**Files:**
- Create: `tools/revise_paper_terminology.py`
- Input: `面向真实微服务项目的证据约束混沌测试方法.docx`
- Output: `面向真实微服务项目的证据约束混沌测试方法_术语学术化修订版.docx`

- [x] **Step 1: 读取全部段落与表格，按段落/单元格保留原有样式并在 run 级别替换文本。**
- [x] **Step 2: 应用确定性术语映射，包含中英文核心术语、大小写、连字符和专有名词写法。**
- [x] **Step 3: 对中文摘要、英文摘要、关键词及结论段落做局部学术化润色，不增删实验事实。**
- [x] **Step 4: 将结果保存为独立修订版，并输出替换统计和段落/表格计数。**

### Task 2: 结构与内容一致性检查

**Files:**
- Check: `面向真实微服务项目的证据约束混沌测试方法_术语学术化修订版.docx`

- [x] **Step 1: 检查段落、表格、章节标题、公式占位和参考文献数量与原稿一致。**
- [x] **Step 2: 检查关键数字（114、88、15、51、46、9、2、18、6）及项目名未被误改。**
- [x] **Step 3: 搜索残留的非规范术语、乱码替换风险和不一致大小写。**

### Task 3: 渲染与视觉验证

**Files:**
- Render: `qa/paper_revision_render/`

- [x] **Step 1: 使用 bundled `render_docx.py` 渲染修订版 DOCX，并使用工作区自带 Poppler 完成 PDF 到 PNG 转换。**
- [x] **Step 2: 检查全部 13 页 PNG，确认没有文字裁切、表格溢出、公式错位或缺字。**
- [x] **Step 3: 未发现可修复的结构性版式问题；已完成 OOXML、图片关系和表格形状检查，并与原稿对照确认页数一致。**

### Task 4: 交付

- [x] **Step 1: 保留原稿及 QA 中间文件，仅向用户交付修订版 DOCX。**
- [x] **Step 2: 在最终回复中说明术语统一、摘要/正文表达优化和验证结果。**
