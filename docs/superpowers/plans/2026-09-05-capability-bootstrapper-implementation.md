# CapabilityBootstrapper 子项目一实施计划

## 目标

实现一个只读的新项目能力启动器。它复用现有 Kubernetes inventory、32 项核心目录和 9 项
扩展目录，为每个目标资源生成完整、确定性、可审计的能力矩阵；不执行故障、不创建资源、不修改
项目 profile 中的支持声明。

本计划只覆盖总设计中的子项目一“41 项能力自动发现”。隔离环境、OracleBuilder、RunEngine
live 接入和四项目故障注入分别属于后续子项目，不得提前混入本次实现。

## 完成定义

1. 公共 CLI 可以对一个或多个 profile 执行只读 capability bootstrap。
2. 每个项目的聚合矩阵包含且只包含 32 个核心 ID 和 9 个扩展 ID。
3. 目标级记录包含目标、状态、原因码、隔离等级、证据等级、前置条件、Oracle 和恢复契约信息。
4. 无适用目标的能力仍有一条项目级 `target_id=null` 记录，不能从覆盖率中消失。
5. 旧状态 `blocked_by_platform_prerequisite` 和 `not_reachable` 被归一为 `blocked`，原始状态保留。
6. 发现阶段最高只能产生 E1；E2 及以上只能从通过验证的外置运行证据索引导入。
7. 输出位于仓库外，并明确记录 `read_only=true`、`injection_performed=false`。
8. 四项目实跑生成完整矩阵，运行前后无 Chaos Mesh 新资源和仓库内生成文件。

## 设计约束

- `src/chaosatlas/capabilities` 拥有新的公共能力启动契约。
- 现有 `tools/fault_catalog.py` 和 `tools/extension_fault_catalog.py` 在本子项目中保持目录权威，不迁移 ID。
- `KubernetesProjectAdapter` 继续拥有 Kubernetes inventory 和 TESTNODE 构建，不在 bootstrapper 中复制解析逻辑。
- `CapabilityBootstrapper` 只组合纯评估器和注入的只读 runner，不直接调用 `subprocess`。
- 项目级状态聚合优先级固定为：`supported`、`canary_required`、`blocked`、`unsupported`、`inapplicable`。
- profile 中的 `supported` 声明不能单独把证据等级提升到 E2；结构化运行证据是唯一晋级依据。
- 不生成 live candidate YAML，不调用 apply、patch、delete、exec、scale 或 rollout。

## 计划任务

### 任务 1：冻结能力记录和状态契约

**新增文件**

- `src/chaosatlas/capabilities/__init__.py`
- `src/chaosatlas/capabilities/contracts.py`
- `tests/test_capability_contracts.py`

**测试先行**

1. 写失败测试，覆盖 32+9 目录 ID 不重不漏。
2. 写失败测试，验证旧状态归一：
   - `blocked_by_platform_prerequisite -> blocked`
   - `not_reachable -> blocked`
   - 其他五个新状态保持不变。
3. 写失败测试，验证项目聚合优先级与 `target_id=null` 占位记录。
4. 写失败测试，验证 E0-E4 排序、未知等级拒绝和发现阶段不得自行产生 E2+。
5. 写失败测试，验证能力记录必填字段和 `catalog_scope`。

**实现**

- 定义合法状态、旧状态映射、证据等级和隔离等级。
- 实现 `normalize_capability_status()`、`aggregate_capability_status()`、
  `validate_capability_record()` 和目录完整性检查。
- 使用 JSON-safe 字典作为边界格式，内部辅助类型不得改变现有工具的序列化方式。

**验证命令**

```powershell
./scripts/invoke_python.ps1 -m pytest tests/test_capability_contracts.py -q
```

**提交建议**

`feat: add capability bootstrap contracts`

### 任务 2：从 inventory 独立构建目标节点

**修改文件**

- `tools/kubernetes_project_adapter.py`
- `tests/test_kubernetes_project_adapter.py`

**测试先行**

1. 证明节点发现不依赖 `supported_fault_families`。
2. 覆盖 Deployment、StatefulSet 和 DaemonSet。
3. 覆盖无 Service 的 Worker、调度器和后台任务。
4. 验证依赖边、PVC、HPA、PDB、容器、挂载和扩展事实仍被保留。
5. 验证 Secret 和 ConfigMap 的值永不进入节点或矩阵。

**实现**

- 从 `detect_server_deployment()` 提取纯节点构建边界，例如
  `build_capability_nodes(inventory)`。
- 原候选生成继续调用该边界，保持现有 candidate ID 和 live 行为不变。
- bootstrapper 只消费节点，不触发基于 profile 白名单的候选生成。

**验证命令**

```powershell
./scripts/invoke_python.ps1 -m pytest tests/test_kubernetes_project_adapter.py -q
```

**提交建议**

`refactor: expose read-only capability nodes`

### 任务 3：实现 32 项核心目标评估器

**新增文件**

- `src/chaosatlas/capabilities/core_assessment.py`
- `tests/test_core_capability_assessment.py`

**测试先行**

1. 对一个普通 HTTP Deployment 生成完整 32 项项目聚合评估，目标矩阵只包含资源作用域匹配的记录。
2. 验证全局 `implemented` 不会自动变成项目 `supported`。
3. 验证具有唯一目标、后端前置和恢复契约的未验证能力进入 `canary_required/E1`。
4. 验证缺少容器、Service、依赖边、测试 Secret、测试存储或一次性目标时返回结构化原因。
5. 验证真实 PVC 和非 disposable 目标上的磁盘/耗尽故障为 `blocked`。
6. 验证 `api_server_delay` 始终要求 L3。
7. 验证现有 profile 的显式 `inapplicable`、`blocked` 和 `unsupported` 边界被保留。

**实现**

- 为 32 个 ID 建立确定性的目标需求和默认 L1/L2/L3 映射。
- 将“目录已实现”“目标适用”“环境具备”“项目已验证”分成不同字段。
- 输出稳定 `reason_code`，正文 `reason` 只用于人读，不参与身份计算。

**验证命令**

```powershell
./scripts/invoke_python.ps1 -m pytest tests/test_core_capability_assessment.py -q
```

**提交建议**

`feat: assess core faults per target`

### 任务 4：规范化 9 项扩展评估

**修改文件**

- `tools/extension_capability.py`
- `tools/extension_runtime_probe.py`
- `tools/runtime_applicability_gate.py`
- `tests/test_extension_faults.py`
- `tests/test_extension_runtime_probe.py`

**新增文件**

- `src/chaosatlas/capabilities/extension_assessment.py`
- `tests/test_extension_capability_assessment.py`

**测试先行**

1. 每个项目聚合恰好包含 9 个扩展 ID，不因依赖边追加而重复同一身份。
2. 工作负载目标评估 7 个非依赖扩展；两类依赖故障按 edge target 生成独立记录，无依赖边时保留 `target_id=null` 项目记录。
3. IO、时间、JVM、队列、连接池和 runtime pause 保留现有 fail-closed 规则。
4. Chaos Mesh 同时支持 `chaos-testing` 与 `chaos-mesh` 命名空间发现。
5. 运行探测错误转成 `blocked`，不得抛出后伪装为 `inapplicable`。

**实现**

- 将现有 extension candidate 生成和完整矩阵生成分开；矩阵评估全部 9 项，candidate 仍只包含合格项。
- 合并目标静态事实与集群只读 probe，不让 profile 声明覆盖实际缺失的 CRD/Agent。
- 使用与核心矩阵相同的状态、隔离和证据字段。

**验证命令**

```powershell
./scripts/invoke_python.ps1 -m pytest tests/test_extension_faults.py tests/test_extension_runtime_probe.py tests/test_extension_capability_assessment.py -q
```

**提交建议**

`feat: normalize provisional extension discovery`

### 任务 5：实现外置证据索引读取

**新增文件**

- `src/chaosatlas/capabilities/evidence.py`
- `tests/test_capability_evidence_index.py`
- `tests/fixtures/capability_evidence/`

**测试先行**

1. `live_completed + attestation.valid + cleanup=verified` 晋级 E2。
2. 预注入失败、cleanup 未验证或 attestation 无效不得晋级。
3. 同一因果身份三次独立有效复现晋级 E3，不同参数或不同目标不能凑数。
4. 缺少明确版本对照时不得生成 E4。
5. 证据文件损坏、路径不存在或 schema 未知时记录 warning，不中断整个项目发现。
6. profile 的自由文本 reason 不得作为 E2+ 证据。

**实现**

- 只读索引 `batch_summary.json`、`summary.json`、`finding_report.json`、
  `cleanup_report.json` 和运行 manifest。
- 以项目 revision、目标、故障 ID、参数和 Oracle 组成严格因果身份。
- 返回最强合法证据等级及证据引用，不复制原始响应正文。

**验证命令**

```powershell
./scripts/invoke_python.ps1 -m pytest tests/test_capability_evidence_index.py -q
```

**提交建议**

`feat: derive capability grades from runtime evidence`

### 任务 6：组合 CapabilityBootstrapper

**新增文件**

- `src/chaosatlas/capabilities/bootstrap.py`
- `tests/test_capability_bootstrapper.py`

**测试先行**

1. 一个 profile 输出完整 32 核心和 9 扩展项目聚合项。
2. 多工作负载输出稳定 target matrix，排序不依赖 kubectl 返回顺序。
3. 无目标能力仍出现在项目覆盖中。
4. E0/E1 发现结果与可选外置 E2+ 证据正确合并。
5. 所有输出明确 `read_only=true`、`injection_performed=false`。
6. runner 调用白名单只允许 `get`、`api-resources`、`explain`、`version` 等只读命令。
7. 任意写动词都会让测试失败。
8. 输入相同且忽略 `checked_at` 后，输出哈希稳定。

**实现**

- `CapabilityBootstrapper` 接受 profile、adapter、runtime probe 和 evidence index 依赖。
- 输出 `chaosatlas-capability-bootstrap-v1`，包含环境摘要、目标、核心矩阵、扩展矩阵、41 项聚合、
  warnings、输入摘要和输出摘要。
- 对单个 target 探测失败局部降级，不丢弃其他 target；profile 或 inventory 无效时项目级失败。

**验证命令**

```powershell
./scripts/invoke_python.ps1 -m pytest tests/test_capability_bootstrapper.py -q
```

**提交建议**

`feat: add read-only capability bootstrapper`

### 任务 7：增加公共 CLI

**修改文件**

- `src/chaosatlas/cli.py`
- `tests/test_chaosatlas_cli.py`
- `projects/chaosatlas-apps/README.md`

**测试先行**

1. 新增 `capabilities` 子命令，支持重复 `--profile`。
2. 输出目录默认为外置 ChaosAtlas state root，也允许显式外置目录。
3. 非空输出目录 fail-closed，防止覆盖历史证据。
4. 命令没有 `--approve-live`，也不接受任何 live/injection 参数。
5. 多项目输出独立 JSON 和一个 aggregate summary。
6. 任一项目 profile 无效时总状态为 `partial`，已完成项目结果仍保留。

**目标命令**

```powershell
$runId = Get-Date -Format 'yyyyMMdd-HHmmss'
$output = Join-Path $env:LOCALAPPDATA "ChaosAtlas\runs\four-app-capability-bootstrap-$runId"
./scripts/invoke_python.ps1 -m chaosatlas.cli capabilities `
  --profile projects/chaosatlas-apps/immich/profile.json `
  --profile projects/chaosatlas-apps/medusa/profile.json `
  --profile projects/chaosatlas-apps/rocketchat/profile.json `
  --profile projects/chaosatlas-apps/erpnext/profile.json `
  --kube-context chaosatlas-apps `
  --evidence-root $env:LOCALAPPDATA\ChaosAtlas\runs\four-app-phase2-20260905 `
  --output $output
```

**提交建议**

`feat: expose capability discovery CLI`

### 任务 8：四项目只读验收与正式报告

**新增文件**

- `tests/test_four_app_capability_bootstrap.py`
- `docs/superpowers/reports/2026-09-05-four-app-capability-bootstrap-report-zh-CN.md`

**验收步骤**

1. 运行四 profile 的离线契约测试，确认每个项目 32+9 ID 完整。
2. 记录运行前四 namespace 的 Chaos Mesh 全资源残留和工作负载 UID。
3. 通过公共 CLI 执行一次真实只读 bootstrap，产物写到唯一外置目录。
4. 记录运行后残留和 UID，确认没有创建、替换、重启或删除资源。
5. 扫描输出，确认不含 Secret、Token、Cookie、密码和 Kubernetes Secret data。
6. 报告每项目/目标的 `canary_required`、`blocked`、`inapplicable`、已有 E2 和前置条件缺口。

**最终验证命令**

```powershell
$runId = Get-Date -Format 'yyyyMMdd-HHmmss'
$acceptanceRoot = Join-Path $env:LOCALAPPDATA "ChaosAtlas\runs\repository-acceptance-capability-bootstrap-$runId"
./scripts/invoke_python.ps1 -m pytest -q
./scripts/invoke_python.ps1 scripts/run_repository_acceptance.py `
  --root . `
  --evidence-root (Join-Path $acceptanceRoot 'evidence') `
  --report (Join-Path $acceptanceRoot 'repository-acceptance.json')
./scripts/invoke_python.ps1 scripts/check_workspace_hygiene.py --root .
git diff --check
```

**提交建议**

`feat: complete four-app capability discovery`

## 失败与回滚策略

- 所有实现提交保持小步、可独立测试；失败时修复前一提交，不通过旁路脚本绕过。
- bootstrapper 没有写集群能力，因此不需要资源回滚；输出失败只留下外置诊断目录。
- adapter 重构必须通过现有 candidate ID、dry-run 和 live characterization tests，任何 ID 变化都视为回归。
- 证据索引无法读取时降级为 E0/E1 并记录 warning，绝不根据文字描述猜测 E2+。
- 四项目验收发现集群状态变化时立即判定失败，并调查只读边界，不进入子项目二。

## 子项目一最终产物

- 一个公共 `CapabilityBootstrapper` API；
- 一个只读 `chaosatlas capabilities` CLI；
- 32+9 统一聚合与目标级能力矩阵；
- 旧状态兼容和 E0-E4 证据读取边界；
- 四项目外置原始矩阵；
- 一份中文正式验收报告；
- 全量自动化与仓库验收结果。
