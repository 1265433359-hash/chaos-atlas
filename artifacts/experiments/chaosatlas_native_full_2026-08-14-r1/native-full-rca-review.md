# ChaosAtlas-native-full Sock Shop RCA Review

日期：2026-08-14

## 实验边界

本轮直接使用 Sock Shop 原始项目知识快照，不使用 ChaosAtlas-full-v2 projection，也不做 leave-one-project-out 泛化映射。

- 方法：`ChaosAtlas-native-full`
- 项目：Sock Shop
- Namespace：`chaosatlas-sock-shop`
- 运行单元：3 个 seed × 4 个假设 × 2 次重复 = 24
- 原始知识：`artifacts/sock-shop/sock_knowledge_snapshot_static.json`
- 知识快照 SHA-256：`a61b8694aa686f8627f722b2cd93c71c3262cb8fdbc6e8e8a1918cca033ab25a`
- `projection_used=false`
- `pollution_intentionally_not_excluded=true`
- `human_review=pending`
- `knowledge_base_updated=false`

因此，本轮衡量的是项目知识直接可用时的 native-full 实际发现能力，属于允许污染的能力上界，不是无污染公平比较。

## 运行验收

独立验收文件：
`artifacts/experiments/chaosatlas_native_full_2026-08-14-r1/runtime-results-r1/sock-shop/verification.json`

- 报告：24/24
- `status=completed`：24/24
- baseline 无失败：24/24
- `injection.injected=true`：24/24
- `recovery.recovered=true`：24/24
- `cleanup.absent_confirmed=true`：24/24
- `washout.stable=true`：24/24
- 诊断旁证已捕获并通过 SHA-256 核对：24/24
- `human_review=pending`：保持
- `knowledge_base_updated=false`：保持
- 最终全局 `podchaos,networkchaos,stresschaos -A`：无残留

## 结果

| 分类 | 单元数 |
|---|---:|
| `weakness_observed` | 8/24 |
| `no_business_impact_observed` | 16/24 |

8 个弱点全部来自 seed-1003，并且 4 个假设各自 2/2 复现：

| 假设 | 目标 | 注入 | 业务结果 |
|---|---|---|---|
| H2 | `front-end` | 100% loss，30s，direction=to | `catalogue` HTTP 500，`login` 超时，`orders` HTTP 500 |
| H4 | `catalogue` | 100% loss，30s，direction=to | `catalogue` 超时并持续 HTTP 500 |
| H6 | `carts` | 100% loss，30s，direction=to | `login` 超时，`orders` HTTP 500 |
| H8 | `orders` | 100% loss，30s，direction=to | `orders` 超时并持续 HTTP 500 |

## 证据解释

业务弱点由 Sock Shop 真实业务 oracle 直接确认：baseline 旅程全部成功，注入期出现稳定的 HTTP 500 或超时，恢复与 washout 后重新达到成功窗口。

日志旁证支持以下有限结论：

- `catalogue` 目标报告中出现 `Unable to connect to Database`，目标连接为 `catalogue-db:3306`。
- `carts` 目标报告中出现 `MongoSocketException` / `UnknownHostException`，目标为 `carts-db:27017`。
- `orders` 目标报告中出现 `MongoSocketException` / `UnknownHostException`，目标为 `orders-db:27017`。
- `front-end` 日志出现 `Can't set headers after they are sent`，与网关层错误响应现象相符，但不足以单独证明内部处理机制。
- events.json 记录了每轮 Chaos Apply/Recover 事件；每轮报告都记录了 mutation、诊断文件和实际 SHA-256。
- Sock Shop 冻结拓扑没有可用 Zipkin trace；每轮均生成 `zipkin-unavailable.json`。因此不能用 trace 证明具体调用链，也不能猜测 Eureka、缓存、注册、重试、熔断或其他内部机制。

结论边界：已确认“这些网络故障能使真实业务旅程失败”，并有日志支持下游数据库访问失败的观测；没有证据支持更具体的内部根因机制。

## 历史结果对照

| 方法 | 弱点单元 | 口径 |
|---|---:|---|
| ChaosAtlas-native-full | 8/24 | 本轮，直接使用 Sock Shop 原始项目知识，允许污染 |
| ChaosAtlas-full-v1 | 11/24 | 历史 Sock Shop 两臂批次 |
| ChaosAtlas-ablation | 14/24 | 历史 Sock Shop 两臂批次 |
| ChaosAtlas-full-v2 LOO | 6/24 | 每项目 leave-one-project-out |

这四个数字不能直接解释为方法优劣排序：候选假设、知识边界和污染条件不同。native-full 的有效含义是证明“直接把项目原生知识交给方法时，它能稳定发现 4 个可复现业务弱点”；它不是公平 head-to-head 的统计结论。

## 审核状态

- 审核：`pending`
- 知识库写入：否
- 本报告只记录证据和边界，不自动把弱点写回知识库。
- 敏感信息扫描未发现 DeepSeek/GitHub token、API key 或私钥；原始诊断中出现的 `default_password` 是 Sock Shop 固定测试 fixture，未被当作外部凭据使用。
