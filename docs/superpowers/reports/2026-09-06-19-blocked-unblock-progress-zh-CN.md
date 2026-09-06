# 四项目 19 项 blocked 解锁推进记录

日期：2026-09-06

## 结论

本轮没有把任何项目能力直接改写为 `supported`。新增了统一的外部 runtime evidence 接口，并执行了真实 canary；当前矩阵仍保持证据约束。

## 已实现

- `probe_runtime_backends` 支持读取外部 `httpchaos-runtime-evidence.json`。
- 只有同一 Kubernetes context、生命周期 attestation 有效且故障效果被业务样本确认时，`httpchaos_runtime_verified` 才会变为 true。
- `chaosatlas capabilities` 新增 `--runtime-evidence`，可把真实 canary 证据接入统一 capability bootstrap；缺失、schema 错误或 context 不匹配均保持 false。
- 新增 `scripts/run_httpchaos_runtime_canary.py`，复用统一 `KubernetesLifecycleExecutor`，生成 namespace/selector/mode 受限的 HTTPChaos canary 和可审查证据。
- `run_api_server_delay_disposable.py` 支持本地镜像、期望响应体和容器 command/args，便于在无外网时进行真实 disposable control-plane 验收。

## 已测试

`tests/test_capability_runtime_probe.py`、`tests/test_httpchaos_runtime_canary.py` 和 disposable canary 测试共 9 项通过。修改前后的完整仓库测试需在提交前再次执行。

## 真实证据

### HTTPChaos（Medusa）

证据目录：`%LOCALAPPDATA%/ChaosAtlas/runs/httpchaos-medusa-canary-20260906-b`

- CRD、Chaos Mesh controller/daemon、目标 Pod、selector、端口均通过；
- Chaos Daemon 的 tproxy/ebtables 正向探针失败，原因是 `http_tproxy_positive_evidence_missing`；
- 未执行 `kubectl apply` 注入，`injection_performed=false`；
- 因此 6 项 HTTPChaos 仍为 blocked，不能用 CRD 存在替代运行证据。

### API Server delay（disposable Minikube）

证据目录：`%LOCALAPPDATA%/ChaosAtlas/runs/api-delay-canary-20260906-d`

- disposable Minikube 启动、busybox canary 部署、基线、API 网络延迟、恢复、qdisc 清理和 profile 删除均有真实记录；
- 底层 `live-*.json` attestation 为 valid，观察到延迟样本约 300--395 ms；
- 统一 RunEngine 在写入机制证据阶段报缺失文件并最终给出 `method_invalid`，所以本轮不将 `api_server_delay` 解锁；
- 该错误应作为 RunEngine 证据收集缺陷修复后重新验收。

## 当前仍 blocked 的主要原因

1. HTTPChaos 6 项：需要同 context 的 tproxy/ebtables 正向注入证据；
2. native HTTP 2 项：四项目没有已验证的 native HTTP 控制契约；
3. native resource 3 项：没有项目级隔离资源 Agent；
4. Secret rotation、image pull failure、pod unschedulable：缺少项目级 disposable target；
5. extension time/queue/pool/runtime：缺少对应 disposable Agent 或控制契约；
6. API Server delay：需要修复统一 RunEngine 机制证据收集后重新跑 disposable canary。

## 证据边界

本报告区分“代码接口已实现”“测试通过”“真实运行证据存在”。未满足完整生命周期、业务效果和清理证明的能力继续保持 blocked；本轮没有使用模拟结果解锁矩阵。
