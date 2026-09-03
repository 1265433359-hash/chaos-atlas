# IO、时间与 JVM 故障扩展设计

**日期：** 2026-09-03  
**项目：** ChaosAtlas  
**状态：** Approved design  
**首个真实目标：** Dify Kubernetes `1.17.0`

## 1. 目标

在不改变现有 8 个故障大类、32 个具体故障能力统计口径的前提下，增加三类可复用的扩展故障能力：

- `extension.io_delay`：测试目录或测试卷上的 IO 延迟；
- `extension.io_error`：测试目录或测试卷上的受控 IO 错误；
- `extension.time_offset`：单 Pod 或单容器的时间偏移；
- `extension.jvm_gc_pause`：明确 JVM 进程上的受控 GC/线程暂停。

扩展能力必须沿用现有的项目适配器、候选策略、LLM 决策、生命周期证据、RCA、恢复、清理和经验库闭环。扩展第一阶段不直接增加正式目录的能力数量；通过真实 canary 和独立复现后，才评估是否进入下一版 canonical catalog。

## 2. 范围与非目标

### 范围

1. 建立独立的 extension catalog、能力描述和身份规则。
2. 从项目 manifest 和运行事实中发现 volume、mount、进程、JVM 和时间敏感业务边。
3. 为每个扩展能力提供参数校验、适用性探测、编译、执行、观测、恢复、清理和 attestation。
4. 让 LLM 在合格的扩展候选中选择测试策略，并记录决策依据。
5. 在 Dify Kubernetes 上执行适用的低强度 canary；不适用的能力必须显式记录原因。
6. 其他项目只生成静态能力矩阵和只读探测结果，不进入真实注入。

### 非目标

- 不修改当前 32 个正式故障能力的语义或历史证据。
- 不在 Dify 上强行测试不存在的 JVM。
- 不触碰 PostgreSQL/Redis 真实数据目录、宿主机根目录、Node 时钟或共享控制面。
- 不把 YAML 编译成功、API apply 成功或 Pod Ready 当作业务故障已验证。
- 不因一次成功 canary 立即把扩展能力升级为全局正式能力。

## 3. 能力模型

故障目录采用三层模型：

```text
fault category
  -> canonical fault capability
      -> parameterized candidate
```

现有 8 个大类和 32 个具体能力继续作为正式目录。扩展能力使用 `extension.*` 命名空间，并拥有独立的 `extension_id`、参数域、风险等级、后端、资源作用域、能力要求和恢复契约。

扩展候选的严格身份至少包含：

```text
project_id
project_revision
extension_id
target_resource
fault_parameters
oracle_id
recovery_contract
```

同一因果簇中的不同强度参数可以共享 causal identity，但必须保留具体参数和执行证据，不能因簇聚合而丢失参数覆盖统计。

## 4. 四个扩展能力

| 能力 | 后端 | 资源作用域 | 最小参数 | 主要业务问题 |
| --- | --- | --- | --- | --- |
| `extension.io_delay` | IOChaos | volume/path | `path`, `latency_ms`, `percent`, `duration_s` | IO 变慢是否造成超时、任务堆积或降级 |
| `extension.io_error` | IOChaos | volume/path | `path`, `errno`, `percent`, `duration_s` | IO 错误是否被重试、降级或正确暴露 |
| `extension.time_offset` | TimeChaos | pod/container | `offset_ms`, `duration_s` | TTL、Token、超时、调度和时间戳是否异常 |
| `extension.jvm_gc_pause` | JVMChaos 或受控 JVM agent | process/JVM | `target_process`, `pause_ms`, `duration_s` | JVM 暂停是否导致失败、延迟或队列堆积 |

参数范围、CRD 字段和动作名称必须以当前集群 schema 的 `kubectl explain` 与 server-side dry-run 为准。编译器不得依赖未经验证的旧 YAML 示例。

## 5. 适配器与能力探测

项目适配器应在生成扩展候选前补充以下事实：

```text
resource_scope: service | pod | container | process | jvm | volume | pvc
mounts: [{container_path, volume_name, read_only}]
volumes: [{name, kind, claim_name, host_path}]
runtime: {language, process_name, pid_hint, jvm_present, jvm_version}
time_sensitive_edges: [timeout, ttl, certificate, scheduler, timestamp]
capabilities: {iochaos, timechaos, jvmchaos, writable_path, disposable_target}
```

每个扩展候选必须绑定唯一目标资源和业务 Oracle。适用性状态分为：

- `supported`：通过能力探测和安全门禁，可以进入 live 候选；
- `inapplicable`：项目缺少目标资源或运行时能力，不生成 live 候选；
- `blocked`：理论上适用，但当前集群、权限、隔离或 CRD 前置条件不满足。

首个 Dify profile 使用 `chaosatlas-dify` context 和 `dify-k8s-lab` namespace。其他项目只运行只读 inventory 和 schema 探测，并输出矩阵。

## 6. 安全与执行链路

统一生命周期如下：

```text
inventory
-> capability probe
-> candidate generation
-> LLM strategy selection
-> deterministic safety gate
-> compile
-> inject
-> observe
-> classify
-> recover
-> cleanup
-> attest
-> RCA
-> knowledge promotion
```

安全规则：

1. IO 目标必须是显式 allow-list 中的测试路径或测试卷；禁止 `/`、`/etc`、`/var/run`、容器运行时目录、未隔离 hostPath 和真实数据库数据路径。
2. IO 运行必须确认目标 Pod/容器唯一，注入状态必须由 IOChaos status/event 确认。
3. Time 只允许 Pod/容器级时间偏移；如果只能修改 Node 或集群全局时钟，返回 `blocked`。
4. JVM 必须确认真实 JVM、目标 PID、JDK/agent 能力和可恢复路径；无法恢复时只能销毁 disposable Pod/namespace。
5. 任何注入未确认、业务 Oracle 不稳定、恢复失败或清理未验证的运行不得进入 RCA 经验晋级。
6. 所有资源都必须带 ChaosAtlas owner/fault/run 标签，并在结束后执行全局残留扫描。

## 7. LLM 决策边界

LLM 负责：

- 在通过适用性和安全门禁的扩展候选中排序；
- 选择先测哪一个目标、哪一个强度和哪一个业务 Oracle；
- 根据历史经验卡片判断某些低价值或重复候选是否降权；
- 根据运行证据建议继续、升阶、转向其他因果簇或停止。

系统确定性控制器负责：

- 校验 LLM 输出是否引用合法候选；
- 拒绝越权 namespace、危险路径、超范围参数和未验证目标；
- 强制恢复、清理、attestation 和稳定复现门槛；
- 处理 LLM 不可用、输出无效或建议与证据冲突的 fallback。

因此，LLM 是策略核心决策者，但不是安全约束的最终绕过者。

## 8. 候选与停止策略

每个扩展因果簇先生成最低成本 baseline。只有出现异常、接近业务边界、或历史经验明确支持升阶时，才选择 medium/high/boundary 参数。

停止条件包括：

1. 当前因果簇已完成所需的基础覆盖，且后续候选的预期信息增益低；
2. 参数边界已明确，继续升阶只会重复相同结论；
3. 出现稳定异常后，当前参数变体已完成 `3/3` 有效复现；
4. 候选被判定为 `inapplicable` 或 `blocked`，且没有新的环境事实可以改变判断；
5. 恢复/清理失败触发该簇或项目批次的安全停止；
6. 自适应项目预算耗尽。

预算仍由通用自适应预算器按项目规模、工作负载数、适用因果簇数、参数层数和风险调整，不为所有项目使用固定数字。重复复现次数是证据门槛，不计入项目候选预算的语义。

报告必须分别统计：基础覆盖、参数覆盖、稳定复现覆盖、inapplicable、blocked 和停止原因。

## 9. Dify 首轮执行方案

Dify 首轮只在当前 Kubernetes 环境执行能力探测和适用 canary：

1. 对 `api`、`worker`、`plugin-daemon` 生成 volume/mount/runtime inventory；
2. 确认测试路径或测试卷，优先使用 disposable namespace 或专用测试挂载；
3. 执行低强度 `extension.io_delay`；
4. 通过 Chatflow Oracle、响应延迟、应用日志、队列/重试信号进行观测；
5. 清理并验证业务恢复；
6. 执行 `extension.io_error`，仅在存在安全测试路径和可验证错误观测时进入 live；
7. 执行 `extension.time_offset`，优先观察 `beat`/`worker` 调度、TTL、超时和 Chatflow 请求；
8. 探测 JVM；若没有真实 Java/JVM 进程，记录 `inapplicable`，不生成伪候选；若存在则执行低强度 `extension.jvm_gc_pause`。

Dify 的单一 Chatflow Oracle 可以判断请求成功、失败和延迟，但不能独立证明 IO 语义、调度语义或 JVM GC 语义。因此扩展执行器必须按能力增加专属观测证据。

## 10. 证据与经验晋级

每次扩展运行必须生成现有生命周期产物：

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

扩展结果只有在 baseline、注入确认、专属观测、恢复、清理、独立 Oracle 和 `comparison_eligible` 全部通过后，才可以进入 RCA。

RCA 经验卡片至少包含：

```text
extension_id
project_scope
target_resource
parameter_level
observed_signals
business_result
root_cause_confidence
recovery_result
cleanup_result
promotion_status
```

单次有效运行进入 `provisional`；同一因果身份完成两次独立复现后，才可进入 `local_reusable`。稳定异常仍要求该参数变体 `3/3`，不能用不同参数或不同目标混合凑数。

## 11. 实现与验收顺序

1. 增加 extension catalog、identity 和 capability matrix 数据模型；
2. 扩展 TESTNODE 与局部影响图；
3. 实现 IOChaos 编译、探测、执行、观测、恢复和清理；
4. 实现 TimeChaos 编译、探测、执行、时间敏感 Oracle 和恢复；
5. 实现 JVM 目标发现和受控 GC/线程暂停执行器；
6. 增加候选策略、LLM 决策审计和自适应停止的 extension 投影；
7. 完成单元、契约、离线 profile 和安全边界测试；
8. 在 Dify 上执行 dry-run、低强度 canary 和独立复现；
9. 为其他项目生成静态扩展能力矩阵；
10. 根据真实证据决定是否把扩展能力晋级到下一版正式目录。

完成定义不是“生成了四份 YAML”，而是适用能力具备可审计的 preflight、inject、observe、recover、cleanup、attestation、RCA 和独立复现证据；不适用能力则有明确、可复核的阻断原因。
