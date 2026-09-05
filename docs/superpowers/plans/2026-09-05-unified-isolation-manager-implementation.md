# Unified IsolationManager 实施计划

## 目标

实现已批准的统一 L1/L2/L3 隔离生命周期，不执行故障，不接入 OracleBuilder 或 RunEngine live。

## 任务顺序

1. [x] 冻结 `IsolationPlan`、`EnvironmentLease`、`IsolationAudit` schema、状态机、摘要与校验测试。
2. [x] 实现 41 项隔离规划、只升不降、L1 adopted/ephemeral、L2 sandbox、L3 Minikube 选择。
3. [x] 实现仓库外原子 LeaseStore、并发限制、TTL、损坏 lease fail-closed。
4. [x] 实现 ProviderRegistry 和 IsolationManager 的 prepare/ready/release/recover/reap 状态机。
5. [x] 实现 Kubernetes L1/L2 Provider、安全蓝图编译、所有权/UID 删除门禁和幂等清理。
6. [x] 实现 L3 Minikube Provider、独立外置 home/kubeconfig、精确 profile 删除和缺失证明。
7. [x] 增加 `chaosatlas isolation` CLI、四项目 L1 声明、外置产物与回归测试。
8. [x] 依次完成 L1 adopted、L1 ephemeral、L2、L3 真实无故障生命周期验收并生成中文报告。

提交前全量测试和产品边界检查通过。仓库卫生检查单独报告了一个早于本次实现、且正被 Dify
容器 bind mount 使用的 `environment-reports/` 目录；为避免破坏运行中的 Dify，本次不移动该目录。

## 验证

```powershell
./scripts/invoke_python.ps1 -m pytest -q
./scripts/invoke_python.ps1 scripts/run_repository_acceptance.py --root . --evidence-root <external> --report <external-report>
./scripts/invoke_python.ps1 scripts/check_workspace_hygiene.py --root .
git diff --check
```

真实生命周期若因本机容量无法完成 L3，必须记录 `blocked_environment_capacity`，不得用 mock 替代。
