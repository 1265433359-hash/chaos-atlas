# ChaosAtlas 32 类故障执行与验收设计

## 目标

将 ChaosAtlas 从“已冻结 32 类故障目录和部分真实执行器”推进到可审计的 32 类故障测试能力。每个故障必须经过统一的预检、基线、注入、观测、分类、RCA、恢复、清理和知识处理链路；任何缺少真实证据的类型继续保持 `planned`。

## 当前基线

当前已具备真实执行器的 canonical fault ID 为：

```text
pod_kill
container_kill
stress_cpu
stress_memory
network_loss
network_partition
network_delay
```

32 类目录、项目 profile、候选生成、业务 Oracle、RCA、恢复、清理和知识草稿链路已经存在。Nginx、Sock Shop、Online Boutique 已完成若干网络、容器和资源类 canary，但尚未完成 32 类的真实验收。

## 统一执行协议

每个 executor 实现同一生命周期，编排器只依赖协议，不依赖底层故障后端：

```text
preflight(candidate, environment)
baseline(candidate, oracle)
inject(candidate)
observe(candidate, oracle, evidence_window)
classify(evidence)
rca(evidence, hypothesis)
recover(candidate)
cleanup(candidate)
attest(evidence)
```

每个阶段必须写入带 schema、时间戳、candidate ID、project commit、namespace 和 hash 的证据。`attest` 只有在以下字段全部为真时才允许进入知识更新：

```text
baseline
injection
observation
recovery
cleanup
independent_oracle
comparison_eligible
```

## Executor 后端

### Chaos Mesh 后端

用于 Pod、容器、CPU、内存、网络、DNS 和 HTTP 故障。执行器负责生成受 owner 标签约束的资源，等待注入确认，读取事件和状态，并在恢复后确认资源不存在。

### Kubernetes API 后端

用于副本数、配置、发布和调度故障。所有变更必须保存原始对象 hash 和恢复补丁；恢复必须验证对象回到基线，不允许依赖重新部署作为默认清理手段。

### Native sandbox 后端

用于文件描述符耗尽、进程耗尽、HTTP 限流和 API Server 延迟等不能由单个 Chaos Mesh CRD 安全表达的故障。该后端只能在 disposable namespace 或 disposable cluster 工作，并限制系统调用、资源上限和持续时间。

## 分批实施顺序

### 批次一：网络、DNS、HTTP

```text
network_bandwidth
network_duplicate
network_corrupt
dns_failure
dns_delay
http_delay
http_abort
http_status_error
http_response_corrupt
http_rate_limit
dependency_error
connection_reset
business_dependency_unreachable
```

已有编译器的类型先补真实执行、业务 Oracle、恢复、清理和 RCA；没有合适业务 Oracle 的类型必须先扩展 profile，而不是降低证据标准。

### 批次二：资源和扩缩容

```text
disk_pressure
file_descriptor_exhaustion
process_exhaustion
replica_reduction
```

文件描述符和进程耗尽默认使用 Native sandbox；单副本服务的扩缩容测试必须在隔离 namespace 中执行。

### 批次三：配置和发布

```text
config_reload
config_drift
env_misconfiguration
secret_rotation
rollout_pause
image_pull_failure
```

所有配置和发布变更都必须保存可逆变更记录。涉及 Secret、镜像拉取或发布控制器的测试只允许使用临时环境中的测试凭据和测试镜像。

### 批次四：平台高风险

```text
pod_unschedulable
api_server_delay
```

这两类默认不进入现有共享 Minikube。`pod_unschedulable` 使用临时节点池或 disposable cluster；`api_server_delay` 只能在 disposable cluster 中执行，并且必须保留集群销毁前的审计包。

## 环境隔离与安全门禁

- 低风险故障可以在现有测试 namespace 中运行，但仍要求显式 kube context、namespace allow-list、owner 标签和批次预算。
- 高风险故障必须申请临时环境租约，租约包含 project、fault family、seed、开始时间、最大持续时间和清理策略。
- 所有 live 运行必须显式 `--approve-live`；禁止默认使用当前上下文进行注入。
- preflight 失败、业务基线失败、namespace 不匹配、候选不在冻结分母中时不得注入。
- 清理失败、恢复失败或证据不完整时，结果只能是 `environment_blocked`、`method_invalid` 或 `incomplete`，不能更新知识状态。
- 不在运行产物中保存 kubeconfig、Secret、Token、私钥或未脱敏的授权头。

## 知识和 RCA 晋级规则

### 防御成功

业务 Oracle 在注入期间保持成功，但有明确的注入确认和机制证据时，记录为防御成功。该结果进入防御知识卡，不得误写成弱点。

### 业务退化

业务 Oracle 在注入期间出现超时、非预期状态码、错误响应、成功率下降或关键内容缺失，且基线、注入、观测、恢复和清理均完整时，记录为 `availability_degraded`。

### 弱点晋级

一次完整运行只产生 `candidate` 或 `provisional` 知识。相同 project commit、目标、故障族、参数域和因果身份必须在两次独立运行中复现，才可晋级 `local_reusable`。任何身份冲突或防御结果都不得覆盖已有知识卡。

## 项目验收矩阵

每个项目的矩阵按以下状态记录：

```text
supported      profile 声明且已具备真实执行契约
planned        目录存在但执行器或证据契约未完成
inapplicable   全局能力存在但项目不适用
```

一个故障进入项目的 `supported` 不代表已经发现弱点，只代表该项目可以安全执行并产生完整生命周期证据。最终报告必须分别统计：真实执行次数、confirmed RCA、bounded 防御、环境阻断、方法无效、清理失败和知识晋级数。

## 完成定义

32 类目标完成必须同时满足：

1. 每个适用故障有明确 executor、参数 schema、业务 Oracle、恢复和清理契约。
2. 每个适用故障至少完成一次真实 canary；高风险故障使用隔离环境。
3. 每轮都有完整 lifecycle attestation 和可验证证据 hash。
4. RCA 能区分业务退化、防御成功、平台阻断和方法无效。
5. 发现的弱点完成第二次独立复现后才写入可复用知识。
6. 所有测试环境在验收结束时通过残留资源检查。
7. `docs/ACCEPTANCE_32_FAULTS.md`、故障矩阵和运行索引与真实证据一致。

## 交付产物

```text
32_fault_capability_matrix.json
32_fault_runtime_results.jsonl
32_fault_rca_report.json
32_fault_knowledge_index.json
32_fault_cleanup_audit.json
```

每个运行目录还必须保留 `run_manifest.json`、`preflight.json`、`execute.json`、`finding_report.json`、`rca_report.json`、`cleanup_report.json` 和 `phase6_audit.json`。

## 实施检查点

1. 统一 executor 接口和生命周期测试通过。
2. 批次一在三个项目及必要的临时环境完成 canary。
3. 批次二、三、四按风险等级完成隔离验收。
4. 新候选和停止策略在 guarded 模式下逐轮选择，并只回灌完整、清理验证通过的反馈。
5. 全部矩阵、RCA、知识和清理审计通过最终一致性检查。
