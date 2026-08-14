# ChaosAtlas-full-v2 泛化知识投影设计

## 目标

构建一个项目无关的 `ChaosAtlas-full-v2` 知识投影，将已经验证的测试节点经验、调用链位置、故障适用条件、正面与负面运行时证据以及历史支持统计，抽象成可泛化规则。

投影不得向 LLM 暴露原始 YAML、项目专属目标、可执行 mutation、待审核发现或敏感信息。

## 范围

投影使用现有的项目知识卡和结构化图资产：

- Online Boutique 知识卡
- OpenTelemetry Demo 知识卡
- Train Ticket 知识卡
- Train Ticket 测试节点目录
- Train Ticket 服务图和调用切片图
- 只有在证据状态明确时，才允许使用 Sock Shop 的冻结静态知识

原始 YAML 仅作为离线数据源，不能复制到投影中。

项目级运行时报告仍然是证据来源，但不直接作为 LLM prompt 内容。

## 总体架构

投影构建器分为四个阶段：

1. **规范化**

   将不同项目中的字段映射到统一角色本体：

   ```text
   entrypoint
   workload
   controller_path
   synchronous_downstream_call
   async_queue
   state_store
   dependency_edge
   business_outcome
   observation
   recovery
   ```

2. **经验抽取**

   从知识卡、测试节点和调用图中抽取：

   - 测试节点规则
   - 调用链模式
   - 故障适用条件
   - 业务结果分类
   - 证据边界

3. **跨项目聚合**

   将相同的抽象模式跨知识卡、跨项目合并，保留：

   - 支持次数
   - 独立来源数量
   - 正面结果数量
   - 负面结果数量
   - 运行时验证数量
   - 阻塞数量
   - 置信度

4. **清洗与冻结**

   生成只面向 LLM 的安全投影。以下内容必须被拒绝：

   - 具体项目名
   - 具体服务名
   - Pod 名和 label selector
   - 源代码路径
   - candidate ID
   - mutation 路径
   - 原始 RCA 文本
   - API key、token 和其它敏感信息
   - pending 或未审核证据

LLM 使用的投影和本地审计 manifest 分离：

- LLM 投影只保存抽象规则和不可逆的来源哈希
- 本地 manifest 保存详细来源、卡片编号和审计信息
- 详细来源不进入 prompt

## v2 投影结构

```json
{
  "schema_version": "chaosatlas-generic-knowledge-projection-v2",
  "test_node_rules": [],
  "call_chain_rules": [],
  "fault_applicability_rules": [],
  "outcome_taxonomy": [],
  "negative_evidence": [],
  "evidence_boundaries": [],
  "provenance": {
    "source_card_count": 0,
    "source_hashes": [],
    "projection_policy": "abstract roles and bounded applicability only"
  },
  "human_review": "pending",
  "knowledge_base_updated": false,
  "projection_sha256": "..."
}
```

每条规则都必须使用抽象角色和条件。

例如：

```text
同步下游调用
且没有 timeout 证据
且注入有界网络延迟
→ 可能出现延迟退化、客户端超时、传输失败或业务响应保持
```

这条规则不能包含具体的 `checkoutservice`、`paymentservice` 或某个项目中的 Pod 名。

## 测试节点经验规则

测试节点规则描述什么故障适合什么抽象节点：

```json
{
  "when": {
    "target_role": "workload",
    "replica_class": "single_replica",
    "protocol_class": "rpc"
  },
  "fault": "pod_kill",
  "evidence": "runtime_observed"
}
```

规则可以表达：

- 单副本或多副本
- workload、同步下游调用或状态依赖
- RPC、HTTP、消息队列等协议类别
- 故障方向
- `mode=one` 或 `mode=all`
- 有界持续时间和参数范围

## 调用链规则

调用链不能保留项目服务名，而应保存角色路径和结构特征：

```json
{
  "path": [
    "entrypoint",
    "workload",
    "synchronous_downstream_call",
    "business_outcome"
  ],
  "properties": {
    "critical_path": true,
    "fanout": "single_or_repeated",
    "async_boundary": false,
    "stateful_dependency": false
  }
}
```

需要覆盖的调用链结构包括：

- 入口 → 工作负载 → 同步下游 → 业务结果
- 工作负载 → 异步队列 → 消费者
- 工作负载 → 状态存储
- 多下游扇出
- 重复同步调用
- 关键路径和非关键路径
- 故障节点位于入口、核心服务、下游调用还是状态依赖

## 故障适用条件

故障适用规则描述什么时候应该尝试某类故障：

```json
{
  "fault": "network_delay",
  "applies_to": "synchronous_downstream_call",
  "conditions": {
    "timeout_evidence": "absent",
    "retry_evidence": "unknown",
    "direction": "to"
  },
  "expected_surfaces": [
    "latency_degradation",
    "client_timeout",
    "transport_failure"
  ],
  "validation": "validate_business_oracle_and_latency_boundary"
}
```

这类规则不能声称已经证明了 Eureka、缓存、重试、注册或其它内部机制。

## 结果分类和负面证据

结果必须规范化，不能保留类似 `station_success_response...` 的项目化标签。

统一结果分类建议包括：

```text
business_response_preserved
latency_degradation
client_timeout
server_completion_after_client_timeout
transport_failure
grpc_error
cascade_failure
no_business_impact_observed
platform_blocked
observation_incomplete
```

同时保留正面和负面证据：

```json
{
  "rule": "network_delay_on_synchronous_call",
  "positive_outcomes": [
    "latency_degradation",
    "client_timeout",
    "transport_failure"
  ],
  "negative_outcomes": [
    "business_response_preserved"
  ],
  "boundary": "business_oracle_must_be_checked_after_injection"
}
```

这样 LLM 能够知道某类故障可能造成业务失败，也可能只造成延迟退化。

## 证据策略

只有以下证据状态可以支持正向运行时规则：

```text
runtime_observed
runtime_verified
verified
```

以下内容不能直接创建运行时适用规则：

- static-only
- pending
- candidate
- runtime_injection_blocked
- platform_blocked

这些内容最多只能进入明确的证据边界或阻塞规则。

投影必须同时保留：

- 已观察到的业务弱点
- 已观察到的业务保持
- 延迟退化
- 实验无效或平台阻塞
- 未能证明的内部机制

## 泛化要求

- 项目和服务名称必须映射为抽象角色
- 故障操作必须归一到有限故障分类
- 结果标签必须归一到通用分类
- 调用链规则必须记录角色路径、关键路径、扇出、同步/异步边界和状态依赖位置
- 聚合结果必须记录支持数量和结果数量，但不能暴露来源项目名称
- 每条正向规则至少需要一个运行时验证来源
- 高置信度规则需要重复验证或多个独立来源支持
- 构建过程必须确定性执行
- 必须生成 canonical SHA-256
- `human_review` 必须保持 `pending`
- `knowledge_base_updated` 必须保持 `false`

## 验证要求

实现必须测试以下行为：

1. 项目专属知识卡能够转换为角色规则，且不泄漏目标名称
2. 能够抽取同步和异步调用链模式
3. 能够合并正面和负面结果证据
4. pending 和平台阻塞证据不会进入运行时正向规则
5. 项目化结果标签能够被规范化
6. 投影哈希和来源计数是确定性的
7. 禁止字段和敏感信息扫描能够通过
8. full-v1、full-v2、ablation 的 common input 保持字节级一致
9. 规则能通过 leave-one-project-out 泛化检查

在使用 v2 进行新实验前，必须通过：

- 静态污染扫描
- 敏感信息扫描
- 规则覆盖率检查
- 调用链抽象检查
- leave-one-project-out 泛化审查

## 非目标

- 不把原始 YAML 发送给 DeepSeek
- 不自动更新知识库
- 不覆盖或重跑已有正式实验结果
- 没有直接证据时，不推断具体内部根因
- 不修改 Docker、Minikube 或 Chaos Mesh
