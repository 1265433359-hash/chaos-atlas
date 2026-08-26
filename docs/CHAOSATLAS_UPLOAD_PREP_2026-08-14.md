# ChaosAtlas Git 上传准备清单

日期：2026-08-14
分支：`remediation/2026-08-09-review`
当前本地 HEAD：以 `git log -1 --oneline` 为准
远端基线：`origin/remediation/2026-08-09-review` at `2da22c4`
本地领先远端：6 commits
准备状态：`prepared_for_push_not_pushed`

## 1. 本次整理目标

本次整理的目标不是继续跑实验，而是把当前 ChaosAtlas 阶段成果整理成可上传前复核的仓库状态：

1. 明确三真实项目实验的阶段结论和证据边界。
2. 把“原始项目完整能力”和“同候选池选择能力”整理成可直接汇报的 Word 报告。
3. 把本地临时验证目录从上传候选中排除。
4. 形成一个清楚的 Git 上传前清单，避免 `git add .` 误收临时目录、缓存或敏感信息。

## 2. 已有本地提交

本地分支已经领先远端 6 个提交：

| Commit | 含义 |
|---|---|
| `9ad9b67` | 记录 native ChaosAtlas Sock Shop RCA |
| `bbfb5c4` | 添加同候选池公平对比证据 |
| `a8e3a0e` | 归档真实项目阶段总结 |
| `2b0e03a` | 记录已经手动提交的上游 issue |
| `f4242b9` | 添加弱点结果矩阵分析 |
| 当前 HEAD | 整理项目上传准备、归档报告、工具/测试和上传清单 |

这些提交尚未推送到远端。

## 3. 本次新增/整理的上传候选

| 路径 | 类型 | 上传理由 |
|---|---|---|
| `.gitignore` | 忽略规则 | 增加 `/.tmp-*/`，排除本地临时验证目录。 |
| `docs/ARCHIVE_MAP.md` | 归档索引 | 增加 Word 报告和上传准备清单入口。 |
| `docs/CHAOSATLAS_UPLOAD_PREP_2026-08-14.md` | 上传准备清单 | 记录本地提交状态、纳入/排除策略和验证边界。 |
| `docs/ChaosAtlas_three_project_experiment_report_2026-08-14.md` | 报告源稿 | UTF-8 Markdown 源稿，方便后续修改 Word 报告。 |
| `docs/ChaosAtlas_three_project_experiment_report_2026-08-14.docx` | 汇报文档 | 已排版的中文 Word 报告，解释三项目选择、两组实验步骤、结果与百分比。 |
| `task_plan.md` / `findings.md` / `progress.md` | 会话归档 | 记录本阶段整理和上传准备上下文，便于新会话恢复。 |

## 4. 不应直接上传的本地内容

| 类型 | 当前处理 |
|---|---|
| `.tmp-*` 临时验证目录 | 已通过 `.gitignore` 排除。 |
| `.pytest_cache/`、`.pytest-tmp-*` | 已由既有规则排除。 |
| 本地恢复的完整上游源码树 | 已由既有 `sources_restored*` 规则排除。 |
| 环境文件、密钥、令牌 | 已由既有 `.env*` 规则排除；本次报告不包含密钥或令牌字符串。 |
| 未经筛选的 runtime 大目录 | 不使用 `git add .`；只按归档清单选择性纳入。 |

## 5. 当前推荐上传口径

建议把论文/汇报可读层与大体量 runtime 证据分层处理：

1. 先上传代码、测试、索引、阶段总结、Word 报告和必要的小型 manifest。
2. 大体量 runtime 结果目录仅上传已经进入正式证据链且没有敏感信息的冻结批次。
3. DeepSeek 选择记录、原始日志、拓扑/业务 oracle 证据属于实验 payload，推送前需要明确确认其出境边界。
4. 继续保持 `human_review=pending` 和 `knowledge_base_updated=false`，人工审核前不把 pending 根因写入知识库。

## 6. 上传前验证项

| 验证项 | 状态 |
|---|---|
| Word 报告结构 QA | 通过：DOCX 可解析，中文正常，关键百分比和边界标记存在。 |
| Word PNG 视觉渲染 | 未完成：本机没有 LibreOffice；Microsoft Word 后台导出 PDF 超时。 |
| 临时目录污染 | 已处理：`.tmp-*` 新增忽略规则。 |
| 敏感字符串扫描 | 通过：暂存集合 70 个文件，严格规则 0 命中；宽松规则唯一命中为 `tokens=MAX_OUTPUT_TOKENS` 代码变量假阳性。 |
| 代码回归测试 | 通过：focused regression `118 passed`，仅有既有 `.pytest_cache` 权限 warning。 |
| Git 本地提交 | 已完成：当前 HEAD 为 `Archive project upload preparation`。 |
| Git 推送 | 未执行；等待用户确认。 |

## 7. 最终上传前禁止动作

- 不执行 `git add .`。
- 不推送包含未筛选运行日志、模型 payload 或密钥路径的内容。
- 不删除或回滚用户已有实验产物。
- 不把 pending 审核自动写入知识库。
- 不把 Word 渲染未完成说成视觉 QA 已通过。
