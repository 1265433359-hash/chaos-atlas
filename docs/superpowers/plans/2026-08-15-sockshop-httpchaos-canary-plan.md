# Sock Shop HTTPChaos Canary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用一轮可清理、可审计的真实 canary 判断当前 Minikube 是否支持 HTTPChaos，并重新界定 28 个 HTTP family 的可执行范围。

**Architecture:** 先冻结当前平台只读能力证据，再生成一个只针对 `catalogue:80 /catalogue` 的最小 HTTPChaos。复用 Sock Shop runner 的 baseline、observation、recovery、cleanup、washout 和 diagnostics；canary 后独立检查全局残留，不修改 Chaos Mesh 安装。

**Tech Stack:** Python 3、PyYAML、kubectl、Chaos Mesh 2.8.3、现有 `tools/run_sock_shop_two_arm.py`。

---

### Task 1: 冻结预检与 Canary YAML

**Files:**
- Create: `artifacts/experiments/chaosatlas_sockshop_httpchaos_canary_2026-08-15-r1/platform-preflight.json`
- Create: `artifacts/experiments/chaosatlas_sockshop_httpchaos_canary_2026-08-15-r1/catalogue-response-abort.yaml`

- [ ] 记录 context、node kernel、Sock Shop Ready 状态、全局残留、ebtables broute/nat、xt_TPROXY 和 mangle 探针退出码。
- [ ] 生成 namespace 固定为 `chaosatlas-sock-shop`、selector 固定为 `name=catalogue`、端口 80、路径 `/catalogue` 的 Response abort YAML。
- [ ] 计算 YAML SHA-256，并确认 server-side dry-run 通过。

### Task 2: 执行单轮 Canary

**Files:**
- Create: `artifacts/experiments/chaosatlas_sockshop_httpchaos_canary_2026-08-15-r1/rep-1.json`
- Create: `artifacts/experiments/chaosatlas_sockshop_httpchaos_canary_2026-08-15-r1/rep-1.diagnostics/`

- [ ] 使用 `tools/run_sock_shop_two_arm.py` 执行 replicate 1，recovery timeout 240 秒。
- [ ] 验证报告 status、baseline、injection、recovery、cleanup、washout 和 mutation/diagnostics SHA-256。
- [ ] 如果 runner 非零退出或报告证据不完整，停止后续 HTTPChaos。

### Task 3: 独立清理与平台判定

**Files:**
- Create: `artifacts/experiments/chaosatlas_sockshop_httpchaos_canary_2026-08-15-r1/final-cluster-check.json`
- Create: `artifacts/experiments/chaosatlas_sockshop_httpchaos_canary_2026-08-15-r1/REVIEW.zh-CN.md`

- [ ] 检查 Sock Shop 14 个 Deployment Ready、Pod Running，并确认全局 Chaos 资源为空。
- [ ] 只有真实 injected、可观察业务影响、恢复、清理和 washout 全部成立时，判定 `httpchaos_runtime_capable=true`。
- [ ] 报告历史内核失败、当前能力探针和 canary 结果的差异；保持人工审核待定且不更新知识库。

### Task 4: 决定剩余批次

**Files:**
- Create: `artifacts/experiments/chaosatlas_sockshop_httpchaos_canary_2026-08-15-r1/http-family-applicability.json`

- [ ] 将 28 个 family 分为 `ready_for_semantic_path_gate`、`not_applicable_non_http_protocol` 和 `platform_blocked`。
- [ ] 对 ready 候选绑定真实服务端口和路径；禁止统一使用 `/catalogue`。
- [ ] Canary 成功后再进入每个 mutation 两次的正式批次；Canary 失败时继续执行剩余 DNSChaos、Schedule 和 StressChaos，不强行注入 HTTPChaos。
