# Issue 报告模板（证据链 → 可复现 issue）

> 用途：把「测试节点中心 + 运行时证据」的发现转成高质量 GitHub issue。
> 规则：只报「有运行时证据 + 可复现 + 与项目声明相关」的发现；环境问题（镜像拉取、网络）不报；基准/演示系统里"设计使然"的缺口不作 bug 报。
> 提交前核对：无 SECURITY.md 时走普通 issue；安全类发现先查项目安全渠道/缓冲期。

---

## Title

<!-- 一句话：<服务/路径> <现象>（<证据类型>） -->

## Summary

<!-- 3-5 句：问题是什么、影响谁、为什么值得修。避免主观评价，用事实陈述。 -->

## Environment

- Repository:
- Branch / commit pinned:
- Deployment (isolated lab):
- Chaos Mesh version:
- Image version (if applicable):

## Evidence

### 1. Static evidence
<!-- 代码位置 + 行号 + 关键片段（截图或代码块） -->

### 2. Runtime evidence
<!-- 注入配置（manifest）→ 基线/注入/恢复三阶段测量表 → 日志/事件摘录 -->

| Phase | Metric | Result |
|---|---|---|
| Baseline | ... | ... |
| Injected | ... | ... |
| Recovered | ... | ... |

## Reproduction

```bash
# 最小复现步骤（从 pin 的 commit 开始，含注入 manifest 与测量命令）
```

## Impact

<!-- 按严重度排序：级联面、数据/业务影响、恢复时间、与项目声明/文档的矛盾点 -->

## Suggested fix

<!-- 具体修复方向；若为设计权衡，说明为何建议调整或补充文档 -->

## Notes

- 研究用途说明（fault-injection methodology validation）
- 已知边界（未覆盖的路径、单次实验、环境差异）
