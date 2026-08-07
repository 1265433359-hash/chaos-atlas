# 混沌测试对比方法与复现计划

## 目标

识别与本项目“真实 Chaos YAML -> 测试节点局部 CFG/DFG -> 运行时适用性门禁 -> 证据绑定判定 -> 知识库反馈”最接近的方法，判断 ChaosEater 的相似度，并设计可公平执行的复现与对比实验。

## 阶段

| 阶段 | 状态 | 交付物 |
|---|---|---|
| 1. 理解本项目方法与现有证据 | complete | 方法边界、三个案例项目、现有运行证据摘要 |
| 2. 阅读用户给定 PDF 与扩展版 | complete | 短版/扩展版身份核验、ChaosEater 方法与局限 |
| 3. 检索并核验相近方法 | complete | 2026-08-06 方法清单、可复现性分级 |
| 4. 设计公平对比协议 | complete | 基线、消融、指标、问题去重规则、统计方案 |
| 5. 形成复现路线 | complete | ChaosEater/FastFI/Cast-style/Graph-only 分阶段路线 |
| 6. 输出研究报告 | complete | `artifacts/papers/chaos_testing_comparison_and_reproduction_plan.md` |
| 7. 最终一致性检查 | complete | 已检查论文身份、方法结论、本地交付物和环境前置条件 |

## 决策

- 主外部基线优先采用 ChaosEater 和 FastFI；前者最相似，后者最适合验证“能否以更少实验发现更多独立问题”。
- Cast 是最强概念近邻，但未发现公开实现，因此只能标为 `Cast-style reimplementation`，不能宣称复现原系统。
- SequenceFI 是重要的时序故障对照，但当前未发现公开代码，放入第二阶段扩展。
- 使用同一项目、同一 commit、同一工作负载、同一故障预算和同一判定器；不允许各方法使用不同 Oracle 后直接比较“发现问题数”。
- “更多问题”必须按独立根因机制去重，并同时满足可达、已注入、因果、可重复、业务影响和证据完整条件。

## 已遇到错误

| 错误 | 尝试 | 处理 |
|---|---:|---|
| 论文检索接口返回 HTTP 404 | 2 | 改用 arXiv 官方页面和作者项目页核验 |
| PDF 中文/星号路径在 Python stdin 中被错误编码 | 1 | 先复制到 ASCII 工作区路径再解析 |
| GitHub 页面被浏览器 URL 安全策略阻止 | 1 | 不绕过；仅使用 arXiv 正文公开的仓库链接和作者项目页 |
| 当前受限会话无法读取 Docker/Kubernetes 用户配置 | 1 | 记录为沙箱限制，不据此判断真实环境不可用 |
| 当前 PATH 未找到 kind/helm/skaffold | 1 | 在复现前置检查中明确列为待安装/待暴露工具 |
