# Sock Shop R5 最终审核报告

## 1. 审核结论

本轮按最终冻结方案完成。旧 stratified pilot 的 4 份 Ablation 报告被保留但未进入正式统计；Full discovery 和已经完成的 Full mutation 没有重跑；新 Ablation discovery 不含分类、置信度、Full 停止轨迹、知识库、故障图或历史证据，并由 LLM 自主停止。

主比较结果如下：

| 方法 | 稳定弱点 | 不稳定 | 非弱点 | 分母 | 稳定弱点率 | Wilson 95% CI |
|---|---:|---:|---:|---:|---:|---:|
| native-full | 2 | 1 | 8 | 11 | 18.18% | 5.14% - 47.70% |
| ChaosAtlas-ablation | 2 | 0 | 9 | 11 | 18.18% | 5.14% - 47.70% |

Fisher 双侧精确检验的 odds ratio 为 1.0，p=1.0。本次冻结小样本中两臂稳定弱点率相同，不能据此宣称任一方法具有普遍性优势。

## 2. 方案执行情况

- Ablation discovery 生成 12 条假设、调用模型 13 次，耗时 39.438 秒；prompt token 12,476，completion token 1,310，总 token 13,786。
- Ablation 为 `self_stop=true`、`time_cap_hit=false`，未触及 Full 的 1,419.047 秒硬上限。
- Ablation 固定 seed=0。历史 Full discovery 没有记录 seed，因此只能写 `full_discovery_seed=unrecorded`，不能声称两边 seed 匹配。
- 统一归一化配置 SHA-256 为 `dea50beeaae3499a03e8c68e9fb94e5f623eaf29ad279589623d418a65c5bdae`。
- 冻结 identity 为 `kind + action + target + call_chain_position`；严格实例 identity 再加入归一化 mutation 参数。
- Full 只有 10 个高置信度 full-only 候选同时具备两份严格匹配的历史 completed 证据；另有 18 个高置信候选因没有既有严格证据而排除，没有为了补证据重跑 Full。
- 主分母由 1 个 strict-overlap 和每臂 10 个 only 样本组成，每个 mutation 两次重复。
- Ablation 共 fresh 执行 24 轮，全部 completed；其中 22 轮属于主分母，`hyp-003` 的 2 轮属于额外 exploratory 证据。
- Full 主分母 22 份历史报告累计生命周期耗时 2,592.145 秒；Ablation 主分母 22 份 fresh 报告累计 2,616.110 秒。Ablation 全部 24 份报告累计 3,133.535 秒，批次跨度 3,136.032 秒。
- 审核器重新打开并校验 44 份主报告、264 个诊断文件，报告状态、baseline、注入、恢复、cleanup、washout、mutation SHA-256 和诊断 SHA-256 全部通过。
- `human_review=pending`，`knowledge_base_updated=false`，没有自动写入知识库。

## 3. 主样本逐项结果

### native-full

稳定弱点：

1. `sock-pod-kill-catalogue-db-112`：catalogue-db PodKill，两次均复现。
2. `net-loss-frontend-catalogue-046`：catalogue 方向 50% 网络丢包，两次均复现。

不稳定：

1. `net-delay-frontend-catalogue-072`：catalogue 500ms 延迟，一次复现、一次无业务影响，不计为稳定弱点。

非弱点：front-end PodKill、carts-db PodKill、carts PodKill、catalogue 256MB memory stress、orders 到 shipping partition、shipping 500ms delay、payment 500ms delay、carts 500ms delay，共 8 个。

### ChaosAtlas-ablation

稳定弱点：

1. `hyp-006`：catalogue-db PodKill，两次均复现。
2. `hyp-012`：orders-db PodKill，两次均复现。

非弱点：front-end PodKill、orders 500ms delay、catalogue 500ms delay、shipping PodKill、queue-master PodKill、rabbitmq 500ms delay、user-db PodKill、carts PodKill、payment PodKill，共 9 个。

`hyp-003`（user PodKill）两次均复现，但它是固定随机种子修正后排除的多跑样本，只作为 exploratory 结果，不进入主分母，也不用于方法优劣统计。

## 4. 可执行身份敏感性

注册 identity 把调用链位置包含在 family 和 instance key 中，因此 strict-overlap 只有 1 个。若忽略描述性的调用链措辞，只比较实际执行的 Chaos kind、action、target 和参数，则主样本有 4 个 executable overlap：

| Full | Ablation | 实际 mutation | strict identity |
|---|---|---|---|
| `sock-pod-kill-front-end-110` | `hyp-001` | front-end PodKill | 相同 |
| `sock-pod-kill-catalogue-db-112` | `hyp-006` | catalogue-db PodKill | 因调用链措辞不同而不相同 |
| `sock-pod-kill-carts-104` | `hyp-005` | carts PodKill | 因调用链措辞不同而不相同 |
| `net-delay-frontend-catalogue-072` | `hyp-002` | catalogue 500ms delay | 因调用链措辞不同而不相同 |

这不改变预注册的 2/11 对 2/11 主统计，但会改变对“方法独有发现”的解释。`catalogue-db PodKill` 是两种方法发现的同一个可执行弱点，不是两个独立 ISSUE。两臂主样本合并并按 executable mutation 去重后，共有 3 个稳定可复现弱点：catalogue-db PodKill、catalogue 50% 网络丢包、orders-db PodKill。

## 5. 根因证据审核

### catalogue-db PodKill

业务弱点已确认，且两种方法均复现。oracle 中 `/catalogue` 虽返回 HTTP 200，但 5/5 body contract 不匹配。catalogue 日志在注入窗口直接记录 `database connection error`、MySQL `unexpected EOF`，随后记录 `circuit breaker 'List' is open`；front-end 日志同时出现 `Can't set headers after they are sent`。

证据支持“catalogue-db 中断导致 catalogue 数据路径失败，并向前端错误处理路径传播”。日志明确显示了 circuit breaker 状态，但本报告不推断其配置、重试、缓存或连接池策略。

### catalogue 50% 网络丢包

业务弱点已确认：每轮 oracle 均观察到 catalogue 请求超时或 HTTP 500。Chaos 注入和生命周期证据完整，但当前没有可用 trace，服务日志也不足以把内部故障链精确定位到某个实现机制。因此只能确认该网络故障下的业务弱点，不能进一步猜测重试、连接池或错误传播的具体内部根因。

### orders-db PodKill

业务弱点已确认。两轮首个相关业务失败均为 `/orders` 的 `Remote end closed connection without response`。orders 日志直接记录到 `orders-db:27017` 的 socket exception、`MongoSocketReadException: Prematurely reached end of stream` 和 `SocketTimeoutException: connect timed out`，之后又记录重新建立连接。

证据支持“orders-db PodKill 打断 Mongo 连接并导致 orders 请求处理异常”。后续 journey 出现本地 port-forward 的 WinError 10061/10053，这些只能作为观测通道边界，不能拿来扩展根因结论；首个 `/orders` 失败和 orders/Mongo 日志仍提供了独立直接证据。

### trace 边界

所有 `zipkin.json` 都明确记录 `status=unavailable`，原因为冻结 Sock Shop 输入没有 trace backend。不得声称本轮获得 Zipkin trace 证据。

## 6. 解释边界

- 本轮是 evidence-backed 小样本比较，不是对 Full 114 个 family 和 Ablation 12 个 family 的全量 runtime 比较。
- Full 候选受“已有两份严格历史证据”过滤，Ablation-only 再按固定种子匹配数量；这保证不重跑 Full，但引入了证据可得性边界。
- 调用链位置是自由文本语义，当前归一化仍可能把同一可执行 mutation 分为不同 only family。后续正式版本应同时报告 hypothesis identity 和 executable mutation identity，重合抽样优先以可执行身份为准。
- 一次性结果不计为真实稳定弱点；`net-delay-frontend-catalogue-072` 必须保持“不稳定”。
- 本轮没有自动更新知识库，最终结论仍等待人工审核。
