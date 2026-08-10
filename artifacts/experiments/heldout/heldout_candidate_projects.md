# Held-out 候选项目盘点（P1b）

> 日期：2026-08-10
> 范围：仅盘点仓库已有文档引用的项目来源，不下载/不部署。
> 目的：为 held-out 协议补充 ≥2 个 comparable 候选项目，供主代理审核后再决定获取。

---

## 候选 1：eShop（dotnet/eShop）

| 项 | 值 |
|---|---|
| project_id | `ESHOP` |
| canonical URL | `https://github.com/dotnet/eShop`（findings.md 引用） |
| 版本/commit | `unknown`（未获取；需获取时固定） |
| 源码 | 未获取（不在仓库本地） |
| manifest | 未确认（Kubernetes YAML 需额外确认，findings.md 标注） |
| 镜像 | 未确认 |
| 可观测入口 | 未确认 |
| 可支持 fault family | delay/loss/kill（目标；未确认服务图） |
| protected/unprotected/unknown 可构造性 | `unknown`（需源码 intake） |
| 是否可能 comparable | **是**（.NET 电商参考应用，服务数适中；findings.md 已列入外部资料） |
| 是否需要新的人工批准 | **是**（受限获取批准） |

## 候选 2：Social Network（DeathStarBench 子项目）

| 项 | 值 |
|---|---|
| project_id | `SOCIALNET` |
| canonical URL | `https://github.com/delimitrou/DeathStarBench`（findings.md 引用；**与 Hotel 同仓库**） |
| 版本/commit | `unknown`（同仓库 master 6ecb0970；子目录 `socialNetwork/` 未获取） |
| 源码 | 未获取（同仓库，需受限获取 socialNetwork/） |
| manifest | 未确认（README 含 compose/kubernetes） |
| 镜像 | 未确认 |
| 可观测入口 | 未确认 |
| 可支持 fault family | delay/loss/kill（目标） |
| protected/unprotected/unknown 可构造性 | `unknown`（需源码 intake） |
| 是否可能 comparable | **是**（同仓库同语言 Go 微服务；与 Hotel 共享基础设施知识,可作为第二 held-out） |
| 是否需要新的人工批准 | **是**（同仓库子目录获取批准；且需确认与 Hotel 知识隔离——两子项目可能共享 dialer/registry 模式） |

## 候选 3（备选）：Media Service（DeathStarBench 子项目）

| 项 | 值 |
|---|---|
| project_id | `MEDIA` |
| canonical URL | `https://github.com/delimitrou/DeathStarBench`（同仓库 `mediaMicroservices/`） |
| 版本/commit | `unknown` |
| 源码 | 未获取 |
| 是否可能 comparable | 是（备选；依赖链更深） |
| 是否需要新的人工批准 | 是 |

---

## 对比评估

| 候选 | 优势 | 风险 | 建议 |
|---|---|---|---|
| **ESHOP** | 不同技术栈(.NET) → 跨栈泛化证据 | Kubernetes YAML 待确认;新批准 | 第二 held-out 首选 |
| **SOCIALNET** | 同仓库同栈,获取成本低 | 与 Hotel 共享 dialer/registry 模式 → 知识隔离风险(SE/DP/JE 可能已含 DeathStarBench 模式) | 需确认隔离后可用 |
| **MEDIA** | 备选 | 同 SOCIALNET 风险 | 备选 |

> **隔离警告**:DeathStarBench 的三个子项目(hotelReservation/socialNetwork/mediaMicroservices)共享 dialer/registry/tracing 模式。若 SE/DP/JE 已含 DeathStarBench 通用模式,用作 held-out 时须在 intake 时核对并标注——否则"项目特定知识"可能泄漏到通用知识库。这与 Sock 的 SE/DP/JE posthoc 教训同理。

## 结论

- 至少 2 个候选可推进:ESHOP(跨栈)+ SOCIALNET(同栈隔离确认后)或 MEDIA。
- 全部需主代理批准受限获取;本轮不下载。
- 达到 ≥3 held-out(Hotel + ESHOP + SOCIALNET/MEDIA)后,协议 v1.1 的跨项目结论条件才可满足。
