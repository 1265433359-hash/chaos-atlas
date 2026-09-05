# 新项目完整能力启动与四项目全量实验设计

**日期：** 2026-09-05

**项目：** ChaosAtlas

**状态：** 已完成交互设计，待书面规格复核
**目标项目：** Immich、Medusa、Rocket.Chat、ERPNext

## 1. 背景与口径

ChaosAtlas 当前包含两个相互独立的能力目录：

- 32 个正式核心故障能力，由 `tools/fault_catalog.py` 定义；
- 9 个 provisional 扩展故障能力，由 `tools/extension_fault_catalog.py` 定义。

因此，新项目启动器必须评估 `32 + 9 = 41` 个故障意图。旧文档中的“32+6”表示较早阶段的
6 个扩展能力；当前目录又增加了队列积压、连接池耗尽和通用运行时暂停三项。论文、报告和产品
输出统一使用“32 个核心能力 + 9 个 provisional 扩展能力”，不得表述为“41 个正式支持能力”。

四个目标项目当前都已通过统一 `RunEngine` 完成一次业务入口 `pod_kill`：baseline、注入、
观察、替换恢复、清理和 attestation 均有效，证据等级为 E2。该结果证明统一方法主链可运行，
不证明其余 40 项能力已经获得项目级支持，也不证明依赖组件上的 `pod_kill` 已完成验证。

## 2. 设计目标

1. 面对新项目时，自动评估全部 41 个故障意图，而不是先人工填写支持列表。
2. 对每个“故障 × 目标资源”给出可复核的适用性、阻断原因、隔离等级和证据等级。
3. 在一个统一 `RunEngine` 内完成候选选择、安全门、注入、观察、恢复、清理、RCA 和学习。
4. 使用混合隔离，在不接触真实用户数据的前提下最大化真实应用能力覆盖。
5. 由 LLM 提出事务 Oracle 和实验策略，首次人工审核后由确定性执行器重放。
6. 为论文输出可比较的覆盖数据，为稳定异常生成证据充分的 Issue 草稿。
7. 对不适用或环境阻断的能力给出正式结果，而不是伪造 live 成功。

## 3. 非目标

- 本阶段不进行消融实验。
- 不在现有用户数据、生产账号或不可恢复存储上执行故障。
- 不要求每个项目实际注入全部 41 项；真实不存在的目标必须标记 `inapplicable`。
- 不允许 LLM 绕过 namespace、参数、隔离、恢复或清理门禁。
- 不为四个项目复制四套执行流水线。
- 不因一次 canary 就生成上游缺陷结论。

## 4. 总体架构

```text
project source + deployment + runtime
                  |
                  v
        CapabilityBootstrapper
                  |
                  v
      target-scoped 32+9 matrix
                  |
                  v
          IsolationPlanner
        /         |          \
       v          v           v
   L1 app      L2 target    L3 cluster
   clone       sandbox      sandbox
        \         |          /
                  v
             OracleBuilder
                  |
                  v
              RunEngine
                  |
                  v
       evidence / RCA / learning
                  |
                  v
        reproduction + Issue gate
```

### 4.1 CapabilityBootstrapper

启动器只读收集项目代码、部署清单和运行环境事实，识别：

- Deployment、StatefulSet、DaemonSet、Job、Service 和 Ingress；
- 入口服务、Worker、调度器、数据库、缓存、队列和对象存储；
- Service selector、显式依赖、端口、协议和业务边；
- 副本、HPA、PDB、PVC、卷、挂载路径、ConfigMap 和 Secret；
- 容器语言、进程、JVM、Shell、资源工具和可写测试路径；
- Chaos Mesh CRD、daemon、内核、网络、IO、时间和控制面能力；
- 可恢复方式、一次性目标资格和所需隔离等级。

启动器不得执行 apply、patch、delete、exec 写操作或故障注入。

### 4.2 IsolationPlanner

隔离规划器根据故障风险、目标资源和前置能力选择 L1、L2 或 L3。它输出计划，不自行降低隔离
等级。实际环境由统一隔离管理器创建、登记 lease、验证 Ready，并在 finally 路径销毁。

### 4.3 OracleBuilder

OracleBuilder 使用代码、OpenAPI、页面信息和运行事实生成事务 Oracle 草稿。草稿通过确定性
schema、安全和清理检查后，由人工首次审核。审核通过的契约按项目版本冻结，RunEngine 以后只
执行冻结契约；项目版本或 API 契约改变时必须重新审核。

### 4.4 RunEngine

现有 `RunEngine` 是唯一执行入口。CapabilityBootstrapper、IsolationPlanner 和
OracleBuilder 都通过稳定契约向它提供输入，不建立旁路批处理器。历史专用脚本逐步降级为调用
统一入口的薄封装或迁移工具。

## 5. 能力状态与证据等级

能力状态和证据强度必须分开存储。

### 5.1 能力状态

- `inapplicable`：项目不存在相应资源或语义，例如非 JVM 项目的 JVM pause。
- `blocked`：理论适用，但缺少 CRD、内核、权限、Agent、隔离或恢复条件。
- `canary_required`：静态事实和只读探测通过，等待首次真实 canary。
- `supported`：至少一次完整 live 生命周期验证通过。
- `unsupported`：当前执行器或方法不能表达该故障，且不是临时环境问题。

现有 `blocked_by_platform_prerequisite` 和 `not_reachable` 在读取时兼容，写入新版矩阵时归一为
`blocked`，同时保留结构化 `reason_code`，避免丢失原因。

### 5.2 证据等级

- E0：只有静态代码或清单证据；
- E1：运行环境和安全前置探测通过；
- E2：一次真实 canary 完成完整生命周期；
- E3：相同因果身份、相同关键参数完成三次独立有效复现；
- E4：跨版本或跨环境复现通过。

`supported` 不等于 Issue 可提交。异常至少达到 E3，且 RCA、对照实验、恢复、清理和脱敏门均
通过后，才能生成 Issue 草稿。

### 5.3 目标级矩阵记录

每条能力记录至少包含：

```text
project_id
project_revision
target_id
target_kind
fault_id
catalog_scope: core | extension
capability_status
evidence_grade
risk_level
required_isolation
prerequisites
reason_code
reason
candidate_eligible
oracle_ids
recovery_contract_id
evidence_refs
```

项目级统计由目标级记录聚合，不允许用一个项目布尔值掩盖不同工作负载的差异。

## 6. 混合隔离设计

### 6.1 L1：完整应用副本 namespace

适用于具有明确恢复契约的 Pod、容器、有限 CPU/内存、网络、DNS、HTTP、扩缩容、普通配置和
发布故障。L1 使用完整应用副本、合成数据和测试账号，不复用真实数据库或对象存储。

### 6.2 L2：一次性目标 sandbox

适用于磁盘、文件描述符、进程耗尽、IO、时间、Secret、镜像、调度、JVM、队列、连接池和运行
时暂停。L2 优先使用真实应用镜像，但替换为测试数据库、测试队列、测试 PVC、测试 Secret 和
受控 Agent。数据库真实数据目录、hostPath、容器运行时路径和系统目录永远禁止成为 IO 目标。

### 6.3 L3：一次性 Minikube

适用于 `api_server_delay` 及任何可能影响节点或控制面的实验。每次运行创建带唯一 ID 的
Minikube profile，实验完成或失败后都必须销毁，并用外部控制器确认 profile 不存在。

### 6.4 数据保护

- 默认禁止复制真实用户数据；
- 只使用合成数据和测试账号；
- 凭据、授权码和 Token 位于仓库外；
- 事务 Oracle 必须定义幂等清理动作；
- 复用任何现有数据都需要单独人工授权；
- 证据只保存脱敏请求摘要、响应摘要和哈希，不保存完整敏感正文。

## 7. 41 项能力的默认隔离映射

### 7.1 32 个核心能力

- L1：`pod_kill`、`container_kill`、`stress_cpu`、受限 `stress_memory`、
  `replica_reduction`、六类 NetworkChaos、两类 DNS、六类 HTTPChaos、
  `config_reload`、`config_drift`、`env_misconfiguration`、`rollout_pause`。
- L2：`disk_pressure`、`file_descriptor_exhaustion`、`process_exhaustion`、
  `http_rate_limit`、`business_dependency_unreachable`、`secret_rotation`、
  `image_pull_failure`、`pod_unschedulable`。
- L3：`api_server_delay`。

`stress_memory` 如果容器没有可靠 limit、目标不是应用副本或节点余量不足，自动提升到 L2。
任何 HTTPChaos 在缺少 tproxy/ebtables 正向证据时标记 `blocked`。

### 7.2 9 个 provisional 扩展能力

- L1：`extension.dependency_delay`、`extension.dependency_unreachable`；
- L2：`extension.io_delay`、`extension.io_error`、`extension.time_offset`、
  `extension.jvm_gc_pause`、`extension.queue_backlog`、
  `extension.connection_pool_exhaustion`、`extension.runtime_pause`。

扩展能力继续与核心 32 项分开统计，直到单独的晋级决策改变目录版本。

## 8. Oracle 设计

### 8.1 三层 Oracle

1. 基础 Oracle：Ready、端口、HTTP 或 gRPC 健康，只证明服务存活；
2. 事务 Oracle：创建、读取、更新或校验业务对象，再清理测试数据；
3. 机制 Oracle：证明故障实际作用在预期机制，例如延迟、错误率、队列深度、连接占用或 JVM
   pause。

普通 canary 至少需要基础和事务 Oracle。高风险、依赖和扩展故障还必须具有机制 Oracle。

### 8.2 LLM 辅助、人工首次审核、确定性重放

LLM 可以生成候选步骤、断言、清理动作和风险说明，但生成物只是草稿。确定性检查器必须拒绝：

- 未声明的域名、Service、方法或路径；
- 无清理动作的写操作；
- 删除非本次运行创建对象的步骤；
- 明文密钥、Cookie、Token 或密码；
- 未限制数量的列表、上传或创建操作；
- 支付、邮件、外部通知或其他不可逆外部副作用。

人工首次批准后生成带项目版本、schema 版本和内容摘要的 Oracle 契约。运行时不再次让 LLM 改写
步骤；LLM 只能在已批准 Oracle 与合格候选之间做策略选择。

### 8.3 四项目首批事务 Oracle

- Immich：上传一张合成小图，查询元数据，下载并校验哈希，删除资产；
- Medusa：创建测试购物车，加入固定测试商品，读取并校验总价，使购物车失效或删除；
- Rocket.Chat：创建测试房间，发送和查询带 run ID 的消息，删除房间；
- ERPNext：创建测试 ToDo 或无财务影响的草稿对象，查询、更新并删除。

所有资源名包含 run ID；清理既在正常路径执行，也在 finally 路径按 run ID 扫描。

## 9. LLM 与确定性控制器边界

LLM 负责：

- 从合法候选中按信息增益排序；
- 选择目标、低/中/高参数级别和已批准 Oracle；
- 根据历史证据建议重复、升阶、转向或停止；
- 聚合跨项目异常模式，形成 RCA 和 Issue 草稿建议。

确定性控制器负责：

- 候选身份、参数范围、namespace、路径和隔离等级校验；
- baseline、注入确认、恢复、清理和 attestation；
- 实验预算、三次复现门槛和知识晋级；
- LLM 无效、不可用或越界时的 fail-closed fallback。

## 10. 自适应执行策略

1. 对所有 41 项生成静态目标级矩阵，保证目录覆盖完整。
2. 只对 `canary_required` 生成 live 候选。
3. 每个因果簇先运行最低风险、最低强度参数。
4. 结果远离业务边界且信息增益低时停止该簇。
5. 接近边界时进入 medium；有异常证据时才进入 high/boundary。
6. 异常候选固定因果身份和关键参数，执行三次独立复现。
7. 恢复或清理失败立即停止当前项目批次。
8. `blocked` 和 `inapplicable` 计入覆盖统计，但不伪装为运行成功。

完整能力的含义是每项都有确定结论，不是执行所有目标、参数和排列组合。

## 11. 错误处理和强制停止

以下任一条件发生时停止后续注入，优先恢复和清理：

- baseline 不稳定；
- 实际目标或影响范围与计划不一致；
- 注入无法确认；
- 恢复超过 deadline；
- Chaos Mesh、临时对象、数据或 namespace 存在残留；
- 测试数据无法自动删除；
- Docker、集群、节点或磁盘进入不健康状态；
- Oracle 产物疑似包含敏感信息。

失败结果必须保存到外置证据目录，并记录阶段、原因、是否发生注入、恢复动作和残留审计。预注入
失败不得计入有效复现次数。

## 12. 证据和 Issue 门

每次运行继续生成统一生命周期产物，并增加：

```text
capability_matrix.json
isolation_plan.json
environment_lease.json
oracle_contract_ref.json
runtime_results.jsonl
coverage_summary.json
```

运行证据和生成配置默认位于 `%LOCALAPPDATA%\ChaosAtlas`，仓库只保存 schema、脱敏 profile、
批准的 Oracle 定义、规格和正式汇总报告。

Issue 草稿要求：异常达到 E3、RCA 通过、对照排除预期行为、影响描述有证据、最小复现可执行、
恢复和清理全部通过、敏感信息扫描通过。Issue 始终只生成草稿，必须人工审核后才可提交。

## 13. 五个子项目

### 13.1 子项目一：41 项能力自动发现

交付 CapabilityBootstrapper、目标级矩阵 schema、状态归一、核心与扩展目录合并视图、只读环境
探测和四项目静态矩阵。验收要求每个项目完整包含 32 个核心 ID 和 9 个扩展 ID，每条记录有目标
或明确的无目标原因，执行副作用为零。

### 13.2 子项目二：混合隔离环境管理器

交付 L1/L2/L3 规划、环境 lease、应用副本、一次性目标、一次性 Minikube、外置配置和 finally
销毁验证。验收覆盖正常完成、执行失败、进程中断和重复清理。

### 13.3 子项目三：OracleBuilder

交付 Oracle 草稿 schema、LLM 生成接口、确定性安全检查、人工批准状态、版本冻结和重放器；先为
四项目各完成一个事务 Oracle。未经批准的写操作必须不可执行。

### 13.4 子项目四：RunEngine 统一接入

将能力矩阵、隔离计划和 Oracle 契约接入现有 `RunEngine`，补充 E0-E4、自适应参数选择和停止
策略。公共 CLI 是唯一入口，旧脚本不得保留独立执行逻辑。

### 13.5 子项目五：四项目完整能力实验

按 Immich、Medusa、Rocket.Chat、ERPNext 顺序完成静态覆盖、低风险 canary、高风险隔离
canary、异常三次复现、RCA、知识草稿、Issue 草稿和横向论文数据集。本阶段不做消融实验。

## 14. 实施与提交顺序

严格按以下顺序推进，每个子项目独立设计细化、实现、验收和提交：

```text
1. 能力发现
2. 隔离环境
3. OracleBuilder
4. RunEngine 接入
5. 四项目实验
```

前一子项目未通过验收，不进入后一子项目。任何阶段发现统一引擎已有接口不足，应修改公共契约，
不得为单个项目增加旁路流水线。

## 15. 总体验收标准

1. 四项目均生成完整的目标级 32+9 矩阵，ID 不重不漏。
2. 每条能力都有状态、原因、隔离等级、证据等级和 Oracle/恢复要求。
3. L1、L2、L3 都经过至少一个真实生命周期验收和零残留验证。
4. 四个事务 Oracle 均能创建、断言、清理，并在失败路径完成补偿清理。
5. 所有 live 运行都经过统一 `RunEngine`，不存在第二套执行主链。
6. LLM 输出无法突破候选、参数、隔离、恢复和清理门禁。
7. E2、E3、E4 可从不可变证据计算，不靠人工填写。
8. 阻断和不适用结果进入论文覆盖数据，但不进入成功率或漏洞统计。
9. 只有满足 Issue 门的异常才生成脱敏草稿。
10. 全量测试、架构契约、仓库卫生检查和外置证据检查全部通过。
