# 同候选池公平对比运行审核报告

状态：human_review=pending  
知识库更新：false  
有效运行目录：`artifacts/experiments/chaosatlas_same_pool_fair_2026-08-14-r3/runtime_results-r2`  
说明：`runtime_results-r1` 的 Online Boutique 首个单元停在 baseline，根因是实验 Python 环境缺少 `grpcio/protobuf`，未注入 Chaos；已保留为环境失败旁证，不纳入本轮结果。

## 运行完整性

- Runtime plan：18 个唯一候选，36 个注入单元。
- 有效报告：36/36 `status=completed`。
- 全部报告通过字段审计：baseline 无失败、已确认 injected、业务恢复、cleanup absent、washout stable、diagnostics captured。
- mutation SHA-256：36/36 与实际 YAML 文件一致。
- diagnostics SHA-256：所有记录文件与实际文件一致。
- 全局 Chaos 残留：批次后 `podchaos,networkchaos,stresschaos -A` 无资源。

## 旁证文件

- Online Boutique：每轮生成 `cartservice.log`、`checkoutservice.log`、`events.log`、`target.log`、`trace-unavailable.json`。
- OpenTelemetry Demo：每轮生成 `cart.log`、`checkout.log`、`events.json`、`zipkin.json`。
- Sock Shop：每轮生成 `catalogue.log`、`front-end.log`、`orders.log`、`target.log`、`events.json`、`zipkin-unavailable.json`。

注意：OTel 的 `zipkin.json` 记录的是冻结事实 `trace backend unavailable`，Sock Shop 记录 `zipkin-unavailable.json`。因此本轮 Zipkin 文件只能证明 trace 后端不可用，不能支持具体调用链根因归因。

## 项目结果

| 项目 | Runtime 单元 | 唯一候选 | 确认弱点候选 | 弱点复现实例 |
|---|---:|---:|---:|---:|
| Online Boutique | 8 | 4 | 4 | 8/8 |
| OpenTelemetry Demo | 12 | 6 | 5 | 10/12 |
| Sock Shop | 16 | 8 | 4 | 8/16 |

确认弱点候选：

- Online Boutique：`cartservice network_delay`、`cartservice pod_kill`、`checkoutservice network_delay`、`checkoutservice pod_kill`，均 2/2 复现。
- OpenTelemetry Demo：`cart network_delay`、`cart pod_kill`、`checkout network_delay`、`checkout network_loss`、`checkout pod_kill`，均 2/2 复现；`payment network_delay` 为 0/2。
- Sock Shop：`catalogue network_delay`、`catalogue pod_kill`、`user network_delay`、`user pod_kill`，均 2/2 复现；`carts network_delay`、`front-end pod_kill`、`orders network_delay`、`orders pod_kill` 为 0/2。

## 方法对比

统计单位为唯一候选；每个方法在每个项目 3 个 seed，每个 seed 选择 4 个候选，因此每个方法总选择槽位为 36。

| 方法 | 选择槽位 | 唯一候选 | 确认弱点候选 | 唯一命中率 |
|---|---:|---:|---:|---:|
| ChaosAtlas-full | 36 | 15 | 12 | 80.0% |
| ChaosEater-adapter | 36 | 15 | 11 | 73.3% |
| ChaosAtlas-ablation | 36 | 17 | 12 | 70.6% |

分项目：

| 方法 | Online Boutique | OpenTelemetry Demo | Sock Shop |
|---|---:|---:|---:|
| ChaosAtlas-full | 4/4 = 100.0% | 4/5 = 80.0% | 4/6 = 66.7% |
| ChaosEater-adapter | 4/4 = 100.0% | 5/6 = 83.3% | 2/5 = 40.0% |
| ChaosAtlas-ablation | 4/4 = 100.0% | 5/6 = 83.3% | 3/7 = 42.9% |

## 证据边界

业务弱点已确认：以上确认弱点均满足两次 replicate 中业务 oracle 失败，并且 baseline、恢复、cleanup、washout 均通过。

具体根因未确认：日志和 observation 可支持入口不可用、deadline exceeded、HTTP 500/401、服务调用失败等外部现象；但 Zipkin trace 不可用，且未进行代码级或服务内部状态复核。因此不能声称具体根因是缓存、注册、重试、服务发现或某个内部机制。

可报告的 ISSUE：

- Online Boutique：checkout/cart 关键路径对 PodKill 和高延迟敏感，表现为 gRPC `UNAVAILABLE`、`DEADLINE_EXCEEDED` 或 cart failure。
- OpenTelemetry Demo：checkout/cart 关键路径对 PodKill、网络丢包和高延迟敏感；payment 高延迟在本 oracle 下未造成业务失败。
- Sock Shop：catalogue 与 user 路径对 PodKill 和高延迟敏感；front-end PodKill、orders 故障和 carts 高延迟在本 oracle 下未造成业务失败，是本轮选择中的假阳性/低效候选。
