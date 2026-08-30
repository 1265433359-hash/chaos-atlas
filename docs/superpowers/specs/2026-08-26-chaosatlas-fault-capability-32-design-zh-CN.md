# ChaosAtlas 32 类故障能力扩展设计

## 目标

将 ChaosAtlas 从当前 8 类真实可执行故障扩展为 32 个产品级故障意图。每个意图都必须能够在满足项目前置条件时完成发现、编译、受控注入、业务观测、恢复、清理、RCA 和知识回灌；不满足条件时必须明确标记为 `inapplicable` 或 `planned`，不能通过名称登记冒充可执行能力。

## 目录边界

32 个 ID 是稳定的产品级故障意图，原始 YAML 中的动作别名、参数变体和定时/并发组合归并到意图下，不单独扩大产品目录。目录字段固定为：

```text
fault_id, category, backend, target_kinds, parameters,
preflight, injection_confirmation, business_oracle,
recovery_contract, cleanup_contract, evidence_requirements,
risk_level, status
```

冻结的 32 类按四组组织：

1. `workload_resource`: pod_kill、container_kill、stress_cpu、stress_memory、disk_pressure、file_descriptor_exhaustion、process_exhaustion、replica_reduction；
2. `network_protocol`: network_loss、network_partition、network_delay、network_bandwidth、network_duplicate、network_corrupt、dns_failure、dns_delay；
3. `http_business`: http_delay、http_abort、http_status_error、http_response_corrupt、http_rate_limit、dependency_error、connection_reset、business_dependency_unreachable；
4. `configuration_release_platform`: config_reload、config_drift、env_misconfiguration、secret_rotation、rollout_pause、image_pull_failure、pod_unschedulable、api_server_delay；

存储、时间和节点/控制面动作作为上述意图的目标或执行后端扩展，不另行增加目录数量；如果某一类需要独立的证据和恢复语义，则在下一次目录版本中显式升级，而不是隐式增加别名。

## 架构

`fault_catalog.py` 是唯一目录源。每个 fault_id 通过能力注册表绑定一个专用执行器，执行器实现统一协议：

```text
compile -> preflight -> inject -> confirm -> observe -> recover -> cleanup
```

编排器只依赖协议，不依赖 Chaos Mesh、Kubernetes API 或 HTTP 客户端的具体实现。执行结果必须携带 `fault_id`、目标快照、动作参数、注入确认、业务 Oracle、恢复状态、清理验证和证据引用。候选策略只能选择 `status=implemented` 且通过项目支持矩阵和安全门禁的意图。

## 项目构建要求

每新增一类故障，同时交付：

- 目录条目和能力矩阵更新；
- 独立 compiler/executor 以及失败关闭逻辑；
- 单元测试、契约测试和离线执行测试；
- 至少一个项目 profile 的目标发现与适用性规则；
- `docs/` 中的使用说明、风险和恢复说明；
- Nginx、Sock Shop、Online Boutique 的支持状态；
- 运行报告、RCA 证据和知识卡样例。

## 分批实施

### 批次 1：目录与协议

冻结 32 个 ID，补齐状态、风险、前置条件和能力矩阵；将已实现的 8 类迁移到新目录，并为 planned 类型提供一致的失败关闭行为。

### 批次 2：HTTP/业务

实现 HTTPChaos/业务探针执行器，覆盖延迟、中止、错误码、响应异常、限流、依赖错误和连接重置。业务 Oracle 必须区分网关响应变化与真实业务失败。

### 批次 3：配置、发布、扩缩容和调度

实现 Kubernetes API 专用执行器，覆盖配置 reload、配置漂移、环境变量错误、Secret 轮换、发布暂停、镜像拉取失败、副本缩减和不可调度。每类必须保存原始对象并验证恢复后的就绪状态。

### 批次 4：网络、DNS、资源扩展

补齐带宽、重复包、损坏包、DNS 失败/延迟、磁盘压力、文件描述符和进程耗尽，并为高风险动作增加资源配额和超时保护。

### 批次 5：跨项目验收

在三个项目上执行逐类 canary 和矩阵回归，验证候选选择、停止效率、注入确认、RCA 准确性、清理安全性和知识回归收益。

## 安全和失败处理

- 默认 `dry-run`；真实执行必须显式 `live`、审批和 namespace allow-list；
- 基线失败时不注入；注入未确认时不进入 RCA；
- `environment_blocked`、`inapplicable`、`method_invalid` 不得晋级为 weakness；
- 恢复或清理未验证时，运行结果必须降级并阻止知识晋级；
- 所有执行器都必须支持超时、幂等清理和中断后的 resume。

## 验收指标

完成标准不是“目录出现 32 个名字”，而是：

1. 32 个 ID 都有明确状态和唯一执行契约；
2. 每个 `implemented` 类型至少在一个项目上完成真实注入、恢复、清理和 RCA；
3. 三个项目的支持矩阵、阻断原因和不可适用原因可审计；
4. 知识回灌后，下一轮候选质量或停止效率有可重复的改进；
5. 全量回归测试通过，且未引入现有 8 类能力的行为退化。

