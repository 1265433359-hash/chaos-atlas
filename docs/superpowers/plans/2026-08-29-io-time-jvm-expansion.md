# IOChaos、TimeChaos、JVMChaos 扩展实施计划

## 目标

在不破坏当前 32 类产品目录和既有运行协议的前提下，为 ChaosAtlas 增加三类基础设施故障的可发现、可编译、可受控注入、可观测、可恢复和可审计能力：

- IOChaos：文件/目录 IO 延迟和 IO 错误；
- TimeChaos：Pod 级时间偏移；
- JVMChaos：Java 进程级 JVM 故障，首批只覆盖可验证的 GC/线程暂停语义。

第一阶段采用 `extension` 命名空间中的临时意图，不立即修改“32 类”冻结目录。每个意图必须先在隔离环境完成至少一次有效 canary；通过第二次独立复现后，才评估是否进入下一版 canonical catalog。

## 现状和约束

当前可复用的边界：

- `tools/compile_scenario_node.py` 已负责 scenario 到 manifest/native mutation 的编译；
- `tools/fault_catalog.py`、`tools/fault_capability_registry.py` 已提供故障目录和执行器注册；
- `tools/runtime_applicability_gate.py` 已识别 `IOChaos`、`TimeChaos` 资源残留；
- 运行链已固定为 preflight、baseline、inject、observe、classify、RCA、recover、cleanup、attest；
- 四个目标项目中，Sock Shop、Online Boutique、OpenTelemetry Demo 已有正式 profile；Train Ticket 当前有 artifacts 和历史运行材料，但需要补齐 `projects/train-ticket/profile.json` 才能进入统一矩阵。

## 一期意图和参数

一期先实现四个最小可验证意图，避免将一个原生 kind 的所有参数变体直接膨胀成大量类别：

| 临时意图 | 原生后端 | 必要参数 | 目标 | 业务问题 |
| --- | --- | --- | --- | --- |
| `extension.io_delay` | IOChaos | `path`、`latency_ms`、`percent`、`duration_s` | 容器内受控目录或测试挂载 | IO 变慢是否造成请求超时、任务堆积或降级失败 |
| `extension.io_error` | IOChaos | `path`、`errno`、`percent`、`duration_s` | 非系统目录、优先测试卷 | IO 错误是否被正确重试、降级或暴露 |
| `extension.time_offset` | TimeChaos | `offset_ms`、`duration_s` | 单 Pod 或单容器 | 超时、TTL、Token、定时任务和消息时间是否出现异常 |
| `extension.jvm_gc_pause` | JVMChaos/受控 JVM agent | `target_process`、`pause_ms`、`duration_s` | 明确的 Java/JVM 进程 | GC/线程暂停是否导致请求失败、队列积压或错误传播 |

参数范围、CRD 字段和 JVM 动作名称必须以当前 Chaos Mesh CRD 的 `kubectl explain`/server-side dry-run 结果为准；编译器不能凭旧 YAML 猜测字段。

## 总体架构

保留原有主链路：

```text
项目 manifest、源码和运行事实
  -> 扩展 TESTNODE
  -> 资源层局部影响图
  -> extension candidate
  -> applicability/safety gate
  -> compiler
  -> executor
  -> business oracle
  -> recovery/cleanup
  -> attestation/RCA/knowledge
```

### TESTNODE 扩展

在不改变旧字段含义的前提下增加：

```text
resource_scope: service | pod | container | process | jvm | volume | pvc
mounts: [{container_path, volume_name, read_only}]
volumes: [{name, kind, claim_name, host_path}]
runtime: {language, process_name, pid_hint, jvm_present, jvm_version}
time_sensitive_edges: [timeout, ttl, certificate, scheduler, timestamp]
capabilities: {iochaos, timechaos, jvmchaos, writable_path, disposable_target}
```

### 局部影响图扩展

现有的 `service -> caller -> downstream -> oracle` 图增加以下边：

```text
service -> pod -> container -> process/JVM
container -> mount -> volume/PVC
pod -> node
business operation -> timeout/TTL/certificate/scheduler
fault -> resource -> oracle
```

图只描述当前测试节点相关的局部路径，不声称完整还原整个集群。候选必须能够回答“故障作用在哪个资源上、沿哪条业务路径传播、由哪个 Oracle 判断”。

## 分阶段实施

### 阶段 0：项目画像和环境基线

1. 为 Sock Shop、Online Boutique、OpenTelemetry Demo 重新生成资源清单，记录容器、挂载、PVC、镜像语言、进程和探针。
2. 为 Train Ticket 创建正式 profile，冻结 namespace、commit/image provenance、业务入口、恢复期限和敏感信息策略；复用 Station 双 Oracle 和已有业务路径材料。
3. 对四个项目运行只读能力探测：Chaos Mesh CRD 版本、IOChaos/TimeChaos/JVMChaos schema、daemon 能力、容器工具、Pod 是否允许时间/文件操作。
4. 为每个项目输出 `supported`、`inapplicable` 或 `planned`，不得因目录存在而自动进入 live 候选。

交付：四份 profile、资源/挂载/JVM inventory、扩展能力矩阵、能力探测报告。

### 阶段 1：统一数据模型和候选生成

1. 扩展 deployment/test-node 构建逻辑，生成 volume/process/JVM/time-sensitive 节点和边。
2. 在候选 schema 中加入 `resource_scope`、`capability_requirements`、`oracle_id`、`recovery_contract`、`risk_level`。
3. 增加 extension namespace 的身份和签名规则，确保参数变化不会误合并为同一严格 family。
4. 候选策略只选择通过项目矩阵和安全 gate 的 extension 意图。

建议修改或新增文件：

- `tools/build_deployment_capability_pool.py`
- `tools/deployment_capability.py`
- `tools/compile_scenario_node.py`
- `tools/fault_matrix.py`
- `tools/extension_fault_catalog.py`（新增，暂不改 32 类 catalog）

### 阶段 2：IOChaos 编译器和执行器

1. 先实现 `io_delay`，再实现 `io_error`；每个动作使用独立参数校验和 manifest builder。
2. 预检必须确认：目标 Pod/容器唯一、路径位于 allow-list、路径不是 `/`、`/etc`、`/var/run`、容器运行时目录或未隔离 hostPath，写入范围和持续时间在预算内。
3. 优先使用一次性 namespace 和测试挂载；共享 namespace 中只允许只读 dry-run。
4. 注入确认必须读取 IOChaos status/event，而不是只看 API apply 成功。
5. 观测至少包含：业务请求成功率、P95/P99 延迟、应用错误日志、重试/队列指标和文件操作证据。
6. 恢复先删除 IOChaos，再确认目标路径可访问、业务 Oracle 连续成功，最后做全局残留扫描。

安全边界：首批禁止数据库真实数据目录、宿主机根目录和跨 namespace 目标；任何 cleanup 未验证的运行不得写入知识库。

### 阶段 3：TimeChaos 编译器和执行器

1. 首批只支持 Pod 级时间偏移，不修改 Node 或集群时钟。
2. 预检确认目标工作负载可重启、业务 Oracle 能区分真实业务时间和测试时间、偏移在固定范围内，并没有证书/支付等不可逆副作用。
3. 参数采用有限阶梯，例如小偏移、接近 timeout 的偏移和超过 TTL 的偏移；每次只改变一个时间维度。
4. 观测拆分为：请求 deadline、Token/证书有效期、缓存/TTL、定时任务、消息时间戳五类证据，不能只用 Pod Ready。
5. 恢复删除 TimeChaos 后，等待目标 Pod 时间回到基线并执行连续业务探针；必要时重启 disposable Pod，不能重启共享节点。

首批建议项目：Train Ticket、Airflow 类时间敏感项目（当前四个项目中优先 Train Ticket）；Sock Shop/Online Boutique/OTel 先做静态候选和小偏移防御 canary。

### 阶段 4：JVMChaos 编译器和执行器

1. 先从四个项目 inventory 中筛选真实 JVM 目标；没有 JVM 的项目明确记录 `inapplicable`。
2. 首批只覆盖 GC/线程暂停语义。JVM agent、进程权限、JDK 版本和容器 PID namespace 必须在 preflight 中确认。
3. 不允许通过模糊的“Java 服务”标签生成候选，必须绑定 `deployment -> container -> pid/process -> JVM`。
4. 观测包括业务成功率、响应延迟、GC pause、堆使用、线程池队列和应用日志；Trace 只能作旁证。
5. 恢复需要停止 agent/fault、确认 JVM 指标回落和业务连续成功；JVM 无法安全恢复时，必须销毁 disposable Pod/namespace 并标记环境阻断。

首批项目建议：Train Ticket；如果 OpenTelemetry Demo inventory 发现 Java 服务，再加入该项目。Sock Shop、Online Boutique 只有发现真实 JVM 目标后才可进入候选。

### 阶段 5：四项目 canary 和晋级

执行顺序：

1. Train Ticket：先做 `io_delay`、`time_offset`、`jvm_gc_pause`；
2. Sock Shop：做 IO 静态候选和低强度 IO canary；
3. Online Boutique：做 IO/Time 防御 canary，JVM 按 inventory 决定；
4. OpenTelemetry Demo：利用多语言业务链做 IO/Time 传播观测，JVM 按 inventory 决定。

每个意图至少完成：一次 dry-run、一次 live canary、一次独立复现。进入项目 `supported` 的条件是完整生命周期和有效 attestation；进入 `local_reusable` 的条件是两次同身份复现。业务保持成功时记为 `protected/bounded`，不能写成 weakness。

## 统一恢复和清理契约

每次运行必须产出：

```text
run_manifest.json
preflight.json
compile.json
execute.json
finding_report.json
rca_report.json
recovery_report.json
cleanup_report.json
phase6_audit.json
```

强制条件：

- baseline、injection confirmation、observation、recovery、cleanup、independent oracle 全部存在；
- 资源只允许出现在 profile allow-list namespace；
- 删除故障资源后必须扫描 IOChaos/TimeChaos/JVM 相关残留和临时文件；
- 任何平台阻断、权限不足、工具缺失或目标不适用都不能晋级为业务弱点。

## 测试计划

单元测试：

- 参数边界、路径 allow-list、namespace 越界、JVM target 缺失；
- 每个意图编译到正确 manifest/backend；
- extension identity、scenario hash 和 family 去重；
- profile 缺少能力时返回 `inapplicable`/`planned`。

契约测试：

- executor 生命周期阶段和 attestation 字段完整；
- 注入未确认时不进入 observe/RCA；
- recovery/cleanup 失败时禁止知识晋级；
- Secret、路径、进程参数和 JVM 启动信息脱敏。

离线项目测试：

- 四个项目各生成一份扩展 TESTNODE 和局部影响图；
- 对每类意图生成 accepted、inapplicable、blocked 三种样例；
- 验证现有 32 类测试和行为不退化。

真实验收指标：

- `live_completed` 比例；
- 注入确认成功率；
- 业务 Oracle 观测完整率；
- 恢复和清理成功率；
- 环境阻断率与误报为 weakness 的次数，目标为 0；
- 两次独立复现的一致性。

## 风险和停止条件

- IO 目标无法证明是 disposable/test path：停止，不注入；
- TimeChaos 只能修改 Node/全局时钟：停止，保持 planned；
- JVM 无法确认 PID/JDK/agent 或无法可靠恢复：停止，标记 inapplicable；
- 连续两次 cleanup 失败、出现跨 namespace 资源或 Oracle 不稳定：停止该项目批次；
- Train Ticket profile、镜像 provenance 或业务 Oracle 未冻结：不得进入 live。

## 预期交付物

```text
docs/superpowers/plans/2026-08-29-io-time-jvm-expansion.md
projects/train-ticket/profile.json
tools/extension_fault_catalog.py
tools/extension_fault_compiler.py
tools/extension_fault_executor.py
tools/resource_impact_graph.py
tests/test_extension_fault_catalog.py
tests/test_extension_fault_compiler.py
tests/test_extension_fault_executor.py
artifacts/<project>/extension-capability-matrix.json
artifacts/<project>/extension-test-node-graph.json
artifacts/<project>/extension-canary/
```

## 完成定义

本计划不以“生成了 YAML”作为完成。只有当三类故障在适用项目上都具备可审计的 compiler、preflight、inject、observe、recover、cleanup 和独立复现证据，才能把对应意图从 extension 晋级为正式产品能力；没有 JVM 的项目不因缺少 JVMChaos 而判定方法失败，而应记录为项目级 `inapplicable`。
