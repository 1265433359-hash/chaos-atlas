# Dify Kubernetes Issue Drafts

这些文档是基于 ChaosAtlas 对 Dify Kubernetes 的实际故障测试整理的 GitHub Issue 草稿。

项目关系：ChaosAtlas 是我们的测试工具项目；Dify 是被测项目。

## Test Summary

完整的中文测试归档见：

`reporting/dify-kubernetes/DIFY_TEST_SUMMARY.md`

当前提交状态：

| Finding | Status |
|---|---|
| Plugin daemon restart exposes `400 invalid_param` | 已由用户提交；公开 URL 待补录 |
| Single API replica exposes transient HTTP 502 during restart | 已提交：[#41624](https://github.com/langgenius/dify/issues/41624) |
| API network degradation causes PostgreSQL timeout and HTTP 500 | 已存在：[#41626](https://github.com/langgenius/dify/issues/41626)，不重复提交 |
| Helm Chart metadata and default replica observations | 按要求暂不提交 |

## 提交范围

| 文件 | 建议目标仓库 | 类型 |
|---|---|---|
| `dify-api-single-replica-single-point-of-failure.md` | Dify 项目或 Dify 部署配置 | 被测系统可用性/部署问题 |
| `dify-api-transient-errors-during-restart.md` | Dify 项目或 Dify 部署配置 | 被测系统故障切换问题 |
| `dify-api-network-bandwidth-degradation.md` | Dify 项目 | 被测系统网络降级问题 |
| `chaosatlas-cleanup-leaks-chaos-mesh-child-resources.md` | ChaosAtlas（我们的项目） | 测试框架问题 |
| `chaosatlas-recovery-attestation-control-plane-delay.md` | ChaosAtlas（我们的项目） | 测试框架问题 |
| `chaosatlas-verdict-remains-observation-pending.md` | ChaosAtlas（我们的项目） | 报告/数据契约问题 |
| `chaosatlas-32-fault-capability-coverage-gap.md` | ChaosAtlas（我们的项目） | 测试能力增强 |

## Archived English Drafts and References

The following English drafts and references are archived from the Dify tests.
Check the Test Summary above before creating a new issue, because some findings
have already been submitted or intentionally deferred.

| File | Suggested title | Suggested target |
|---|---|---|
| `dify-api-single-replica-single-point-of-failure-en.md` | Dify API Becomes Unavailable When Its Only Kubernetes Replica Is Lost | Dify or the relevant Kubernetes deployment repository |
| `dify-api-transient-errors-during-restart-en.md` | Dify API Returns Transient HTTP 502 Responses During Pod or Container Restarts | Dify or the relevant Kubernetes deployment repository |
| `dify-api-network-bandwidth-degradation-en.md` | Dify API Returns HTTP 500 and Multi-Second Latency Under Bandwidth Degradation | Dify |
| `dify-plugin-daemon-invalid-param-during-restart-en.md` | Plugin daemon restart exposes transient failures as HTTP 400 invalid_param | Dify |
| `dify-plugin-daemon-single-replica-chatflow-outage-en.md` | Single plugin-daemon replica causes full Chatflow outage during pod replacement | Dify or its Kubernetes deployment configuration |
| `dify-helm-version-metadata-mismatch-en.md` | Helm chart appVersion label remains 1.16.1 when deploying Dify 1.17.0 images | Dify Helm chart |

Issue submission page: `https://github.com/langgenius/dify/issues/new/choose`

## Evidence Handling

The full experiment evidence for the historical 60-hypothesis run is stored locally under:

`C:\APP\project\chaos-atlas\.runs\dify-k8s-repeated-coverage-60hypotheses-verified-20260901`

The issue drafts intentionally use trial identifiers rather than local Windows paths. A local path is not accessible to Dify maintainers and should not be pasted into a public Issue as if it were a link.

When submitting, keep the summarized measurements in the Issue. If maintainers request supporting artifacts, provide a redacted archive or a public artifact link containing only the relevant final `live_completed` attempts. Do not upload the entire `.runs` directory without reviewing logs, endpoints, identifiers, and possible credentials.

历史固定预算运行摘要：60 个唯一假设、每个 3 次、共 180 次 trial，覆盖 17 类可执行故障；
自动化回归测试 `165 passed`。证据目录为：
`C:\APP\project\chaos-atlas\.runs\dify-k8s-repeated-coverage-60hypotheses-verified-20260901`

提交前请将本地证据路径替换为 GitHub 可访问的附件、压缩包或 CI artifact 链接。

## Current Run

The current evidence run is:

`C:\APP\project\chaos-atlas\.runs\dify-k8s-llm-policy-guarded-20260902-r2`

The final adaptive run recorded 140 adaptive actions, 169 unique hypotheses,
162/170 baseline coverage, 4/160 parameter coverage, and 15 stable anomaly
candidates. It generated 10 promoted knowledge-base records. The Plugin daemon
restart finding was submitted by the user, the single-API-replica finding is
tracked by #41624, and the network degradation finding is tracked by #41626.
Helm Chart-related observations remain excluded from submission.
