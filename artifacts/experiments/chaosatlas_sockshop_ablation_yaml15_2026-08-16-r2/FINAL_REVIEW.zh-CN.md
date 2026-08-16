# Sock Shop YAML15 Ablation 最终审核

## 1. 审核结论

本批次按冻结协议完成。`chaosatlas-ablation-yaml15` 从五类、每类 3 份的真实
YAML 示例出发，在不给知识库、Full 假设、置信度、Full 停止轨迹和 Sock Shop
调用链证据的条件下自主生成假设并自然停止。458 个原始假设独立去重为 51 个
family，46 个通过 gate 并各执行两次，共得到 92 份 completed 报告。

正式结果是 9 个稳定弱点、0 个不稳定结果、37 个未观察到业务影响。稳定弱点率为
`9/46 = 19.57%`。本报告保持 `human_review=pending`，没有更新知识库。

## 2. 实验输入与生成过程

- YAML 示例：五类明确标注，每类 3 份，共 15 份。
- 模型可见：去敏 YAML 示例、公共 Sock Shop profile 和业务 oracle。
- 模型不可见：知识库、历史弱点、Full 假设、Full 置信度、Full 停止轨迹、
  Sock Shop 调用链证据。
- 停止：LLM 自主停止；Full discovery 的 `1419.047s` 仅作为硬上限。
- 实际生成：734.188 秒、458 次调用、13,593,910 tokens，模型自然停止，未碰上限。
- 去重：458 -> 51，保留原始 family members 和代表选择理由。
- gate：46 个可执行，5 个数据库 HTTP abort 因缺少可信 HTTP 接口而阻断。

5 个阻断目标为 carts-db、session-db、orders-db、user-db 和 catalogue-db。它们不是
“没来得及跑”，而是 mutation 语义不适用于非 HTTP 数据库接口，未进行注入。

## 3. Runtime 验收

| 指标 | 结果 |
|---|---:|
| 可执行 family | 46 |
| 计划报告槽位 | 92 |
| completed | 92 |
| invalid/failed | 0 |
| 稳定弱点 | 9 |
| 不稳定 | 0 |
| 未观察到业务影响 | 37 |
| 稳定弱点率 | 19.57% |
| 报告生命周期耗时之和 | 10,691.027 秒 |

92 份报告的 baseline、injected、recovered、cleanup absent、washout stable、
`human_review=pending` 和 `knowledge_base_updated=false` 全部通过。独立复核了 92 个
mutation SHA-256 和 552 个诊断文件 SHA-256，缺失和 mismatch 均为 0。最终
Sock Shop 14/14 Pod Ready，全局 Chaos 资源为空。

## 4. 稳定弱点

| family | 类别 | 故障 | 两次业务现象 | Full 稳定问题面覆盖 |
|---|---|---|---|---|
| `hyp-003` | Pod | user PodKill | login timeout/401，orders 500 | 是 |
| `hyp-006` | Pod | orders-db PodKill | orders 连接关闭；每次另有 2 个直接业务失败 journey | 是 |
| `hyp-008` | Pod | catalogue-db PodKill | catalogue HTTP 200 但响应契约失败 | 是 |
| `hyp-014` | HTTP | catalogue response abort | catalogue 500 | 是 |
| `hyp-018` | Network | user 500ms delay | login 401，orders 500 | 否，Ablation 独有 |
| `hyp-020` | HTTP | orders response abort | orders 500 | 是 |
| `hyp-021` | HTTP | user response abort | login 401，orders 500 | 是 |
| `hyp-030` | Pod | catalogue PodKill | catalogue 500/timeout | 是 |
| `hyp-065` | Resource | orders memory pressure | orders 500 | 是 |

按类别统计：Pod 4/14，Network 1/14，HTTP 3/6，Resource 1/12；模型没有生成进入
runtime 的 Composite/Schedule 唯一 family。这是生成结果，不是人为删减。

## 5. 与 Full 的比较

| 方法 | 去重 family | 完成两次注入 | 稳定 | 不稳定 | no-impact | 稳定率 |
|---|---:|---:|---:|---:|---:|---:|
| ChaosAtlas-full | 114 | 88 | 15 | 3 | 70 | 17.05% |
| YAML15 Ablation | 51 | 46 | 9 | 0 | 37 | 19.57% |

Full 的 15 个稳定 family 合并直接/定时重复后对应 10 个问题面；Ablation 的 9 个
稳定 family 对应 9 个问题面。两者重合 8 个：catalogue/orders/user HTTP abort、
orders memory，以及 catalogue、catalogue-db、orders-db、user PodKill。

- Full 独有稳定问题面：catalogue loss、catalogue partition。
- Ablation 独有稳定问题面：user 500ms delay。
- Full 覆盖 Ablation 8/9；Ablation 覆盖 Full 8/10。

Full 为 `15/88`，Ablation 为 `9/46`，比例差为 Ablation 高 2.52 个百分点。Fisher
双侧精确检验 `p=0.8132`；Full Wilson 95% CI 为 `[10.61%, 26.24%]`，Ablation
为 `[10.65%, 33.17%]`。区间高度重叠，小样本不支持任何稳定率优越性结论。

这里的合理解释不是“Ablation 比 Full 强”，也不是“Full 必然更强”。当前证据说明：
Full 找到更宽的故障问题面，尤其是 loss/partition；加入 15 个按类别标注的真实 YAML
示例后，Ablation 也能找到 9 个稳定问题面，并找到 Full 本批稳定集合未覆盖的 user
delay。两边的候选数和生成轨迹不同，命中率只能作为描述性结果。

## 6. 证据边界

1. `hyp-008` 的 catalogue 日志明确出现 `database connection error`，支持数据库不可用
   与响应契约失败的关联；orders-db PodKill 日志可见连接恢复。
2. 其他 family 主要由两次业务 oracle 复现确认。日志不足以证明内部缓存、重试、服务
   发现或注册机制，因此不作此类根因推断。
3. `hyp-006` 每个 replicate 有 2 个直接业务失败 journey，另有 3 个本地
   port-forward-only 失败。后者不计作独立业务证据，但前者足以支持两次复现。
4. 92 份 `zipkin.json` 都是明确的 unavailable placeholder，因为冻结 Sock Shop
   输入没有 trace backend；不作 trace 根因结论。
5. 首批 53 个 completed 报告使用旧 runner schema，没有最终 `target_ready` 字段；
   它们满足原 baseline/injection/recovery/cleanup/washout/hash gate，但不能证明同轮
   目标 Pod 通过当前 Ready gate。续跑前修复了 NetworkChaos 目标 Pod Ready 检查，
   39 个新报告全部记录 `target_ready=true`。
6. Full 的 `15/88` 由两个不重叠证据批次组成：canonical 38 family 为 `8/2/28`，
   route-aware 50 family 为 `7/1/42`。前一批的 76 份报告已冻结逐文件 SHA，后一批
   由 route-aware final audit 回链。

## 7. 最终状态

- 实验：completed
- 人工审核：pending
- 知识库更新：false
- 敏感信息：已完成扫描，5 类模式命中 0 个文件
- 当前可写结论：新版 YAML15 Ablation 发现 9 个稳定问题面，和 Full 重合 8 个；
  Full 与 Ablation 各有独有问题面，稳定率差异无统计证据支持。
