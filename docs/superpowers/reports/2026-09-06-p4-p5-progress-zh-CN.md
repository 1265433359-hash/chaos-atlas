# P4/P5 推进报告（审批前）

日期：2026-09-06。本文记录本轮代码、测试和真实只读证据；不是四项目真实业务验收，也不是 P5 完成证明。

## 已完成

### P4 统一生命周期接入

现有 `RunEngine` 的 Kubernetes 候选执行已接入同一 WorkflowOracle 生命周期：

`prepare_fixture → baseline → inject → observe → recover → collect_evidence → cleanup_fixture`

接入点位于 `tools/kubernetes_lifecycle_executor.py` 和 `src/chaosatlas/orchestration/engine.py`。
原有 `ProbeWorkflowOracle` 仍保持兼容；事务 Oracle 可通过同一 hooks 进入，不新增项目专用实验主链。
准备业务夹具失败会在注入前阻断；业务清理失败会降低最终 cleanup 结果；基线失败也会执行已准备夹具的清理。

`OracleBuilder.build_v3()` 现在提供结构化生成入口。它只接受受限 v3 JSON，所有请求、变量、所有权和清理字段仍由确定性验证器审查；任意 Python/shell/未声明请求会被拒绝。

`tests/test_kubernetes_lifecycle_workflow.py` 已验证调用顺序、注入前阻断和无重复清理。

### P5 可独立推进的只读能力盘点

通过 `CapabilityBootstrapper` 对真实 `chaosatlas-apps` 集群的四个 namespace 完成只读 32 核心 + 9 provisional 盘点：

| 项目 | namespace | 盘点状态 | 41 项状态分布 |
|---|---|---|---|
| Immich | `chaosatlas-immich` | verified | blocked 19 / canary_required 17 / inapplicable 5 |
| Medusa | `chaosatlas-medusa` | verified | blocked 19 / canary_required 17 / inapplicable 5 |
| Rocket.Chat | `chaosatlas-rocketchat` | verified | blocked 19 / canary_required 17 / inapplicable 5 |
| ERPNext | `chaosatlas-erpnext` | verified | blocked 19 / canary_required 17 / inapplicable 5 |

原始外置结果：
`%LOCALAPPDATA%/ChaosAtlas/runs/p5-static-coverage-20260906/<project>-41-capability-bootstrap.json`。

该结果只证明目标发现、运行时后端探测和能力门槛计算；`canary_required` 不等于已支持，`blocked` 也不等于应用缺陷。
本轮另收集了真实 Service UID、selector、端口、Pod UID、ready 状态和 imageID，只读 API 部署证据：
`%LOCALAPPDATA%/ChaosAtlas/runs/h3-readonly-20260906/api-deployment-evidence.json`。
报告明确标注固定版本 API 语义仍 unknown，避免把 Kubernetes 部署事实当作事务证据。

另外对每个真实 Service 做了临时本地端口转发，只发送固定 GET，保存状态码、响应大小、顶层键和 body hash：
`%LOCALAPPDATA%/ChaosAtlas/runs/h3-readonly-20260906/api-surface-evidence.json`。
观测结果为：Immich ping `200`、其 openapi 路径 `404`；Medusa regions/products 在无 key 时均 `400`；Rocket.Chat info `404`、settings.public `200`；ERPNext 两个候选路径 `404`。
这些结果只说明当前路径/认证组合的 HTTP 行为，不能证明接口不存在或业务能力不支持；原始业务响应没有落盘。

## 测试证据

全量测试：**452 passed**。原始输出：
`%LOCALAPPDATA%/ChaosAtlas/runs/p4-p5-20260906/full-tests.xml`。

新增覆盖包括：

- WorkflowOracle 生命周期顺序和失败边界；
- v3 事务会话的 exact ownership、fresh probe、响应丢失、强制恢复、跨会话项目门禁；
- LeaseRuntime 的集群/namespace/Service UID、selector 和 image digest 绑定；
- 精确 Secret 引用和认证 header 限制；
- 只读四项目部署证据采集。

## 仍未完成、不能越过的门

1. 四份 v3 最终事务契约尚未完成固定版本 API、权限、去重和异步删除证据；当前 v2 历史草稿不能直接执行。
2. 尚未按 2A/3A 初始化或验证四个项目的专用合成身份；不能读取或导出实际 Secret，也不能假定现有管理员凭据可用。
3. v3 真实 HTTP 入口仍有显式安全门，disposable 环境释放及 Medusa 未知 cart 的归宿尚未完成真实集成。
4. 因此尚未执行真实业务写入、响应丢失故障、Chaos Mesh 故障、进程强杀恢复或 P5 三次复现；也没有新的应用缺陷、Issue 或论文结论。
5. 综合仓库验收仍只有 `environment-reports` 卫生门失败。该目录已确认被 Dify 数据库挂载，本轮未移动、删除或修改规则掩盖。

## 下一步

先完成 H2/H3 剩余实现和四份最终 `validated` 契约，生成精确路径/文件哈希/语义哈希清单、API 证据和权限初始化报告；然后一次性提交给人工审核。
只有在获得对这些具体契约、范围、断言、补偿和清理规则的实际批准后，才执行 H4 真实业务验收，之后用同一 `RunEngine` 进入 P4 canary 和 P5 32+9 受控实验。
