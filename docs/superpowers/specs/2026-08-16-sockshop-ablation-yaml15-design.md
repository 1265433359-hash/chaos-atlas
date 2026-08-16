# Sock Shop Ablation YAML15 实验设计

## 目标

在不改变既有 ChaosAtlas Full 方法和既有 Full runtime 证据的前提下，重做 Sock Shop Ablation。新版 Ablation 在 discovery 前获得按五类明确标注的 15 个真实 Chaos YAML 示例，用于补齐基本故障语法和动作认知；它仍不得获得知识库、历史弱点、Sock Shop 调用链证据、Full 假设、Full 置信度或 Full 停止轨迹。

实验臂名称固定为 `chaosatlas-ablation-yaml15`。旧 `chaosatlas-ablation` 结果保留为历史结果，但不与新版分母叠加。

## YAML15 冻结输入

五个类别各选择 3 份，共 15 份：

1. Pod disruption
2. Network degradation
3. Resource pressure
4. Protocol/HTTP fault
5. Composite/scheduled fault

每类选择过程只使用 `raw_yaml/` 的静态特征，不使用 Sock Shop runtime 结果、弱点标签、人工偏好或 Full 的选择结果。确定性规则为：

1. 在特征签名 `kind + action_or_target + mode + selector_shape + duration_bucket + intensity_bucket` 上选频率最高的代表；
2. 从未覆盖的特征签名中选频率最高的第二代表；
3. 从剩余有效样本中选择与前两个签名汉明距离最大者；距离相同时按签名频率降序、路径升序决定。

只选择可由 YAML 解析器读取、顶层为 mapping、类别与 `kind` 一致的文件。每个样本保存原路径、原 SHA-256、静态特征、选择理由、去敏文本和去敏文本 SHA-256。

去敏只替换 `metadata.name`、`metadata.namespace`、selector 中的具体 namespace/label 值以及明显的源项目标识；保留 kind、action、mode、duration、故障参数、调度结构和字段层次。任何疑似密钥、token、凭据或外部 endpoint 命中均阻断批次。

## Ablation 输入边界

允许输入：

- YAML15 的类别标签和去敏 YAML；
- Sock Shop namespace、服务清单和业务 oracle；
- 基础 runtime 安全约束；
- 已生成的本臂历史假设，用于避免重复。

禁止输入：

- Full 的 114 个 family、生成顺序、置信度和停止轨迹；
- 知识库、历史弱点和 runtime outcome；
- Sock Shop 调用链投影及项目特定边证据；
- YAML 类别统计、频率、lift、置信区间和类别配额。

模型逐次输出一个抽象假设，字段保持 `id`、`target_service`、`action_or_target`、`call_chain_position`、`call_chain_position_source`、`motifs`、`rationale`。Ablation 的 `call_chain_position_source` 只能为 `model_inference` 或 `unknown`，不得声明为已验证证据。

## 停止与预算

- 模型自主判断是否还有新的有价值假设；自主停止时返回 `stop=true`、`stop_reason=self_stop`。
- 不提供置信度，不设类别配额，不提供 Full 停止轨迹。
- 硬上限使用冻结的 Full discovery wall-clock；计时覆盖所有模型调用、重试和 YAML15 prompt 传输。
- 达到硬上限时标记 `time_cap_hit=true`，保留已生成假设，不伪装成自主停止。
- 记录模型、seed、调用数、prompt/completion/total token、总时间、输入 hash 和协议 hash。

## 编译、Gate 与 Runtime

YAML15 只用于 discovery。模型仍输出抽象 IR，随后复用公共 runtime compiler、静态适用性 gate、runner、业务 oracle、cleanup 和 washout。不得让 Ablation 手写 YAML 后与 Full 的编译结果比较。

本臂先独立去重，保留每个 family 的原始成员、代表选择理由和 strict/family identity。所有通过 gate 的唯一 family 各执行两次；gate 阻断项不补抽，单独统计。两次均完成生命周期且均触发业务 oracle 失败才记为稳定弱点；一次触发记为不稳定，零次触发记为未观察到弱点。

每轮必须确认 baseline 无污染、注入成功、恢复、Chaos 资源删除、cleanup absent、washout stable，并检查全局 Chaos 资源无残留。审核保持 `human_review=pending`、`knowledge_base_updated=false`。

## 对比口径

与既有 Full 冻结台账比较：生成假设数、去重 family 数、gate 通过率、稳定/不稳定/无影响数量、稳定弱点率、稳定问题面、Full 覆盖关系、Ablation 独有结果、discovery 时间、runtime 时间、token 和总成本。

该比较描述的是“少量分类 YAML 入门示例下的独立发现能力”与“完整知识、调用链、置信度和停止机制下的 Full 能力”之差，不是无分类消融，也不是同候选池选择实验。
