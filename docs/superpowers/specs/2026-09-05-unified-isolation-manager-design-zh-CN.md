# 统一可插拔 IsolationManager 设计

日期：2026-09-05

项目：ChaosAtlas

状态：待书面审核

上位设计：`2026-09-05-new-project-full-capability-bootstrap-design-zh-CN.md`

## 1. 目标

本子项目交付统一、可插拔的混合隔离环境管理器，使 ChaosAtlas 能把能力矩阵中的隔离要求转换为
可执行、可审计、可恢复的 L1/L2/L3 环境生命周期。它只负责“在哪里安全地测试”，不执行故障、
不生成业务 Oracle，也不建立第二条实验流水线。

完成后，新项目通过同一公共契约获得：

- L1 完整应用测试副本或已有专用测试副本租约；
- L2 一次性最小目标 sandbox；
- L3 一次性 Minikube 控制面；
- 外置、持久化、无秘密的环境 lease；
- 正常、失败、中断和重复清理路径上的零残留验证。

## 2. 非目标

- 本子项目不执行 41 项中的任何故障。
- 不实现 OracleBuilder、事务数据初始化或应用业务流程。
- 不把隔离管理器直接接入 RunEngine；该接入属于子项目四。
- 不复制生产或用户数据，不快照真实 PVC，不导出 Kubernetes Secret 值。
- 不为 Immich、ERPNext、Medusa、Rocket.Chat 分别建立隔离执行管线。
- 不自动降低能力矩阵要求的隔离等级。
- 不在清理时删除缺少 ChaosAtlas 所有权证明的资源。

## 3. 方案选择

采用统一 `IsolationManager` 加 Provider 注册表：

```text
capability record + target facts + project profile
                       |
                       v
               IsolationPlanner
                       |
                       v
                 IsolationPlan
                       |
                       v
               IsolationManager
              /        |         \
             v         v          v
       L1 Provider  L2 Provider  L3 Provider
             \         |          /
                       v
               EnvironmentLease
                       |
                       v
          Ready / cleanup / absence audit
```

不采用三套独立脚本，因为它们会复制状态机、清理和证据逻辑；不采用四应用专用适配器，因为它们
不能迁移到新项目；本阶段也不引入 Terraform、Argo Workflows 等外部控制面，以免将本地研究环境
变成新的部署前置。

## 4. 组件与职责

### 4.1 IsolationPlanner

输入一个目标级能力记录、目标节点和项目 profile，输出只读 `IsolationPlan`。规划器必须：

1. 读取 `required_isolation`，只允许保持或提升 L1/L2/L3，不允许降低；
2. 验证目标、namespace、项目 revision、风险、恢复和清理要求；
3. 选择 Provider 及模式；
4. 计算稳定计划摘要；
5. 在缺少蓝图、配额、运行工具或安全替换时返回结构化 `blocked`。

`stress_memory` 在目标没有可靠 memory limit、不是专用副本或节点余量未知时提升为 L2。
`api_server_delay` 固定为 L3。LLM 提议的隔离等级只能被规划器提升或拒绝。

### 4.2 IsolationManager

IsolationManager 是唯一生命周期协调器。公共操作为：

```text
plan(request) -> IsolationPlan
prepare(plan) -> EnvironmentLease
verify_ready(lease) -> IsolationAudit
release(lease) -> IsolationAudit
recover(lease_id) -> IsolationAudit
reap_expired(now) -> list[IsolationAudit]
```

`prepare()` 在任何资源创建前持久化 lease，然后调用 Provider。Provider 每创建一个资源，都先把
期望身份写入 lease，再写集群，成功后补记实际 UID。`release()` 在 `finally` 路径运行，必须幂等。
如果进程中断，`recover()` 根据外置 lease 和资源 UID 恢复清理；重启后不得依赖内存状态。

### 4.3 Provider 注册表

Provider 通过固定协议注册：

```text
name
supports(plan)
preflight(plan)
prepare(plan, lease_writer)
verify_ready(lease)
cleanup(lease)
verify_absent(lease)
```

内置三个 Provider，测试可以注入 FakeProvider。Provider 不能直接写证据文件，只能返回 JSON-safe
结果；IsolationManager 负责原子持久化、状态迁移和审计。

### 4.4 ProcessRunner 与 KubernetesRunner

所有外部操作通过注入的 runner 执行，不在业务类中散落 `subprocess`。runner 记录脱敏的命令类型、
退出码和持续时间，但不得记录 Secret 值或完整环境变量。

Kubernetes runner 使用 argv，不使用 shell 字符串。允许写操作仅限 lease 中已批准且带所有权标签的
唯一 namespace；L3 runner 仅允许操作 lease 中生成的唯一 Minikube profile。

## 5. 稳定契约

### 5.1 IsolationPlan

Schema：`chaosatlas-isolation-plan-v1`

```text
plan_id
project_id
project_revision
capability_id
target_id
requested_isolation
effective_isolation
provider
mode
source_namespace
target_namespace_or_profile
resource_budget
blueprint_ref
synthetic_data_only
forbidden_source_kinds
required_checks
plan_sha256
status
blockers
```

`plan_id` 由稳定输入摘要生成；实际运行使用独立 `lease_id`，避免同一计划的多次运行共享资源。

### 5.2 EnvironmentLease

Schema：`chaosatlas-environment-lease-v1`

```text
lease_id
plan_id
project_id
provider
isolation_level
state
created_at
expires_at
owner_labels
resources[{kind, namespace, name, expected_uid, actual_uid, cleanup_policy}]
external_profiles[{provider, name, state}]
cleanup_attempts
last_error
lease_sha256
```

合法状态转换为：

```text
planned -> preparing -> ready -> releasing -> released
                    \-> prepare_failed -> releasing
ready/releasing -> cleanup_failed -> releasing
planned/preparing/ready -> expired -> releasing
```

终态只有 `released`。`cleanup_failed` 不是成功终态，并阻塞同项目后续 live 环境创建，直至恢复清理
或人工审核。

### 5.3 IsolationAudit

Schema：`chaosatlas-isolation-audit-v1`

记录 preflight、Ready、资源身份、清理尝试、资源缺失证明、namespace/profile 缺失证明和错误。
只有所有本次创建资源均确认不存在，状态才能为 `cleanup_verified`。

## 6. L1 Provider

L1 支持两种模式。

### 6.1 adopted-test-replica

用于已经明确是专用、无真实用户数据的完整测试副本，例如当前四个 `chaosatlas-*` namespace。
Provider 验证 namespace、profile 声明、所有目标 Ready、无禁止的外部数据端点后建立“非拥有租约”。
释放租约只删除外置 lease，不删除被接管 namespace。任何未满足“专用测试副本”证明的 namespace
不得被接管。

### 6.2 ephemeral-app-clone

用于按批准蓝图创建完整应用副本。蓝图可以引用：

- 仓库内已审查的脱敏 manifest bundle；
- 固定版本 Helm chart 与仓库内非秘密 values；
- profile 中声明的合成数据初始化器引用。

Provider 创建唯一 namespace，并先创建 ResourceQuota、LimitRange 和 NetworkPolicy，再创建工作负载。
Secret 值只能由外置秘密提供器在运行时注入，不写入 plan、lease、日志或证据。PVC 必须是新建空卷，
禁止从源 namespace 克隆或快照。

如果蓝图引用真实 PVC、hostPath、特权容器、hostNetwork、宿主 PID/IPC 或未批准外部端点，规划阶段
直接阻塞。

## 7. L2 Provider

L2 创建唯一 namespace，只部署目标工作负载、最小依赖和机制探针。

默认自动派生器从目标节点保留镜像、命令、端口和资源限制，并移除或拒绝：

- `envFrom`、源 Secret/ConfigMap 引用和 ServiceAccount；
- PVC、hostPath、hostNetwork、hostPID、hostIPC；
- privileged、危险 capabilities 和不受限 host port；
- 指向非 allow-list 外部域名的配置；
- 未知 admission sidecar 和写宿主机的 initContainer。

派生器提供安全替换：

- 新建测试 Secret，值在运行时随机生成且不落盘；
- `emptyDir` 或新建 disposable PVC；
- profile 声明的测试数据库、测试队列和 mock 依赖；
- `/chaosatlas-test` 专用 IO 目录；
- 受控 JVM、Queue、ConnectionPool、Runtime Agent sidecar。

如果移除配置后目标不能 Ready，Provider 返回 `blocked_missing_sandbox_blueprint`，不猜测业务配置。
项目可以提供薄 `sandbox_blueprint` 补足启动参数，但仍经过同一安全编译器。

## 8. L3 Provider

L3 为每个 lease 创建唯一 Minikube profile：`ca-l3-<project>-<lease-suffix>`。Provider 使用外置的
独立 `KUBECONFIG` 和 Minikube home，限制 CPU、内存、磁盘及 driver，并验证不会复用当前
`chaosatlas-apps` profile。

生命周期为：

```text
minikube start -> context/UID 检查 -> Ready -> lease ready
minikube delete --profile exact-name -> profile list absence -> directory absence
```

清理命令只能接受 lease 中的精确 profile 名，禁止 glob、默认 profile、当前项目 profile和用户已有
profile。创建失败也必须尝试精确删除。L3 本子项目只验证空集群生命周期，不部署或注入控制面故障。

## 9. 所有权与删除安全

所有本次创建的 Kubernetes 对象必须包含：

```text
chaosatlas.dev/managed=true
chaosatlas.dev/lease-id=<lease_id>
chaosatlas.dev/project=<project_id>
```

清理前同时验证 kind、namespace、name、lease 标签和实际 UID。UID 不一致时判定
`cleanup_blocked_identity_mismatch`，不得删除。namespace 只能使用 `ca-l1-` 或 `ca-l2-` 前缀，且必须
与 lease 精确一致。禁止清理 `default`、`kube-*`、源 namespace 和 adopted namespace。

L1/L2 优先删除整个自有 namespace，再确认 namespace NotFound。若 namespace 终止超时，只记录诊断，
不自动移除 finalizer。L3 只删除精确 profile，不递归删除宽泛目录。

## 10. Lease、TTL 与并发

lease 位于外置状态目录：

```text
%LOCALAPPDATA%\ChaosAtlas\isolation\leases\<lease_id>.json
%LOCALAPPDATA%\ChaosAtlas\isolation\audits\<lease_id>\*.json
```

写入采用临时文件加原子替换。每个项目默认只允许一个 active lease；L3 全机只允许一个 active lease。
默认 TTL 为 60 分钟，profile 可缩短但不可超过 4 小时。`reap_expired()` 仅处理自己目录内、schema
有效且所有权证明完整的过期 lease。

并发冲突、lease 损坏或 cleanup_failed 都 fail-closed。lease 文件损坏时不根据资源名前缀猜测删除，
只产生人工审核报告。

## 11. CLI 与外置产物

公共 CLI 增加 `chaosatlas isolation`：

```text
chaosatlas isolation plan
chaosatlas isolation prepare --approve-isolation
chaosatlas isolation status
chaosatlas isolation release
chaosatlas isolation recover
chaosatlas isolation reap-expired
```

`plan` 只读；所有创建与清理操作要求显式动作、精确 plan/lease ID 和专用批准开关。输出目录必须在
仓库外且为空。CLI 只调用 IsolationManager，不包含 Provider 专用逻辑，因此以后接入 RunEngine 时
不会形成第二条实验主链。

CLI 不接受故障参数，不执行 apply Chaos 资源，不执行 Oracle。删除动作不使用模糊名称。

## 12. 错误处理

- preflight 失败：不创建资源，plan/lease 标记 blocked；
- prepare 部分失败：持久化已创建身份，立即进入 releasing；
- Ready 超时：保存事件摘要，清理并验证 absence；
- 进程中断：下次 `recover` 或 `reap-expired` 从 lease 继续；
- cleanup 超时：状态为 cleanup_failed，保留 lease 和诊断；
- UID/标签不一致：停止删除并要求人工审核；
- runner 异常：结构化失败，不把未知状态当成资源不存在；
- adopted namespace：任何 release/recover 都不得删除集群资源。

失败产物不得包含完整 Secret、环境变量、Cookie、Token、密码或业务响应正文。

## 13. 测试与真实验收

### 13.1 自动化测试

1. 规划器覆盖全部 41 项默认映射及只升不降规则；
2. plan、lease、audit schema、摘要与状态机测试；
3. Provider 注册、未知 Provider 和错误隔离；
4. L1 adopted/ephemeral、L2 自动派生/蓝图、L3 精确 profile 生命周期；
5. 创建前 lease 持久化、每个资源 UID 回写和崩溃恢复；
6. 正常、部分失败、Ready 超时、中断、重复 cleanup、UID 不一致；
7. 禁止 source Secret/PVC、hostPath、特权、危险 namespace 和宽泛删除；
8. runner 命令白名单和 shell-free argv；
9. 外置输出、敏感模式扫描和仓库卫生；
10. 现有 32+9 bootstrap、RunEngine dry-run/live characterization 全部回归通过。

### 13.2 真实生命周期验收

- L1：对一个当前四项目专用测试副本建立 adopted lease，验证 Ready，release 后确认 namespace 与 UID
  完全未变；再对最小批准蓝图完成一次 ephemeral namespace 创建和零残留清理；
- L2：创建一次性最小目标、测试 Secret、emptyDir/disposable PVC 和配额，验证 Ready，清理后确认
  namespace NotFound；
- L3：创建唯一空 Minikube profile，验证独立 context Ready，精确删除并确认 profile 与外置目录缺失；
- 每级都追加一次“模拟 Provider runner 调用失败”的自动化验收，证明 finally 清理；
- 所有外置产物敏感扫描命中为 0，仓库内新增运行文件为 0；
- 验收前后当前 `chaosatlas-apps` context、四项目 namespace、工作负载 UID 和重启次数不变。

真实验收不执行故障。若本机资源不足以创建 L3，结果必须为 `blocked_environment_capacity`，不得用
mock 冒充真实通过；子项目验收状态相应为 partial，不能进入 RunEngine 接入阶段。

## 14. 交付物

- `src/chaosatlas/isolation/` 下的 contracts、planner、manager、lease store、provider registry；
- L1 Kubernetes、L2 Kubernetes 和 L3 Minikube Provider；
- 安全蓝图编译器与 L2 自动派生器；
- `chaosatlas isolation` 公共 CLI；
- 自动化测试和三层真实生命周期验收；
- 外置原始 lease/audit；
- 中文正式验收报告；
- 独立提交并推送到 `main`。

## 15. 完成定义

1. 同一 IsolationManager 管理 L1/L2/L3，不存在应用专用生命周期旁路；
2. 计划不能降低能力矩阵要求的隔离等级；
3. 真实 Secret、PVC、用户数据和不安全宿主配置不能进入隔离环境；
4. 所有创建对象在写集群前已写 lease，且回写实际 UID；
5. 正常、失败、中断和重复清理均得到确定结果；
6. 只有 UID 与所有权匹配的精确资源可以删除；
7. L1/L2/L3 各有一个真实生命周期及零残留证据；
8. 外置产物无敏感信息，仓库卫生和全量回归通过；
9. 本子项目不注入故障、不实现 Oracle、不接入 RunEngine；
10. 书面报告明确哪些 blocked 能力因此被解锁为 E1，不能把环境准备等同于故障支持。
