# Hotel Reservation 只读预检报告（intake report v2）

> 日期：2026-08-10
> 状态：**go_no_go = ready_for_snapshot**（用户已批准受限获取 canonical 源码；静态 intake 完成）
> 本阶段仍**未**启动集群/部署/注入；bring-up 与稳定性闸门保持 `not_run`。

---

## 1. Canonical 来源

| 项 | 值 |
|---|---|
| canonical URL | `https://github.com/delimitrou/DeathStarBench`（findings.md:84 引用） |
| 子项目 | `hotelReservation/` |
| commit | `6ecb09706140f8730b5385c08f1386c654c3c526`（master 浅获取，2026-08-10） |
| 来源类型 | GitHub canonical repo（GPL-2.0） |
| 获取方式 | sparse checkout（仅 hotelReservation/）+ WSL 文件系统 |
| 获取时间 | 2026-08-10 |
| 实际路径 | WSL `/root/heldout_src/deathstarbench/hotelReservation`（仓库外，未加入 git） |
| 文件数 | 1976 |

> 许可提示：GPL-2.0；源码本体不提交仓库（提交范围禁止第三方源码）。

## 2. SHA-256（关键源文件）

| 文件 | SHA-256 |
|---|---|
| `hotelReservation/docker-compose.yml` | `988b3e3d4c0c01c5032f47d6ff69db56a8245966ddb7dcaaef1b726ff641bc12` |
| `hotelReservation/README.md` | `6696c99eb4f698efb76c4360cc74bcb2ed6db8cdab5959cd7166433030463346` |
| `hotelReservation/go.mod` | `a5a886b6b67cea384f09f4497cc273b1d710dbe719d9904bd9258446fa38ce90` |
| `hotelReservation/kubernetes/README.md` | `8c8c3a1fb1a9ad7bb41b1727545e4d4252e2b8a6c59b0be8e662a9692371ef53` |

## 3. 服务 / 工作流 / manifest / 可观测

### 服务（10 业务 + 基础设施）
- 业务：`frontend`、`reservation`、`rate`、`profile`、`geo`、`search`、`recommendation`、`review`、`attractions`、`user`
- 基础设施：`consul`（服务发现）、`jaeger`（all-in-one）、`memcached-{rate,review,profile,reserve}`、`mongodb-{geo,profile,rate,review,attractions,recommendation,reservation,user}`

### 工作流（前端入口）
- `frontend` → `search`、`profile`、`recommendation`（gRPC，`srv-*` 服务名）
- `search` → `geo`、`rate`（gRPC）
- reserve 流程：`reservation` 服务（docker-compose 中 `reservation` 服务；代码含 3 个 .go 文件）

### Manifest / 镜像
- `docker-compose.yml`（compose 部署，10 业务 + 基础设施镜像）
- `kubernetes/`（含 frontend/geo/profile/rate/reccomend/reserve/search/user 子目录 + consul + jaeger）
- `helm-chart/`、`openshift/`、`knative/`（备用部署形态）
- 镜像：`deathstarbench/hotel-reservation:latest`（多服务共用）、`hotel_reserv_review_single_node` 等、`mongo:5.0`、`memcached`、`jaegertracing/all-in-one:latest`

### 可观测入口
- Jaeger（`jaegertracing/all-in-one`，OpenTracing `tracing/` 封装，JAEGER_SAMPLE_RATIO 默认 0.01）
- 前端 HTTP 端口 5000（wrk2 workload 脚本 `wrk2/scripts/hotel-reservation/mixed-workload_type_1.lua`）

## 4. 可构造的静态 contract/availability 事实

**Contract（调用边，无 per-request timeout 的静态观察）**
- `frontend -> search`（gRPC，无显式 per-call timeout）
- `frontend -> profile`（gRPC，无显式 per-call timeout）
- `frontend -> recommendation`（gRPC，无显式 per-call timeout）
- `search -> geo`（gRPC，无显式 per-call timeout）
- `search -> rate`（gRPC，无显式 per-call timeout）
- dialer 全局 `Timeout: 120 * time.Second`（连接级，**非 per-request 契约**——与 OB productcatalog 同类，须标记"连接级非请求级"）

**Availability**
- docker-compose 单副本（每服务 1 容器）；`kubernetes/` manifest 需逐一确认 replicas/PDB（本阶段仅静态确认 compose 单副本）
- memcached/mongo 为基础设施依赖，非业务副本冗余

## 5. 不能确认的字段和原因

| 字段 | 原因 |
|---|---|
| kubernetes manifest 的 replicas/PDB 明细 | 本阶段未逐文件确认（`kubernetes/` 子目录存在，需 P2 前扩展静态检查） |
| 各服务是否监听非 5000 端口 | 仅确认 frontend 5000（wrk2 脚本）；其余服务端口待 docker-compose 逐条确认 |
| bring-up 2h / 稳定 30min / 2 baseline | **not_run**（本阶段禁止启动集群） |

## 6. ≥30 中性候选生成条件

- **满足（静态）**：10 业务服务 + ≥6 条调用边 + delay/loss/kill 三类故障族 → 静态规则可生成 ≥30 中性候选（具体候选池在 P2 后按协议冻结，不在此生成）。

## 7. 可覆盖 fault families

- `delay` / `loss`（gRPC 边级，NetworkChaos）
- `kill`（PodChaos/container-kill）
- 均可在 10 服务上构造

## 8. 闸门状态

| 闸门 | 值 | 阶段状态 |
|---|---|---|
| bring-up 最长 2h | 协议值 | `not_run` |
| 稳定观测 ≥30min | 协议值 | `not_run` |
| 连续 2 baseline 失败 → blocked | 协议规则 | `not_run` |

> 按协议要求，本阶段禁止运行集群，闸门必须 `not_run`，不得填 `passed`。

## 9. go_no_go

**`ready_for_snapshot`**

满足条件（全部）：
1. 源码/manifest 来源可追溯（canonical delimitrou/DeathStarBench，commit 6ecb0970）✅
2. 版本/commit 已固定 ✅
3. 服务（10 业务）、工作流（frontend→search/profile/recommendation；search→geo/rate）、镜像、可观测（Jaeger）静态确认 ✅
4. 可静态构造项目特定 contract/availability ✅
5. 尚未发生任何运行时实验 ✅

> P2（静态知识快照）可创建；bring-up/稳定性闸门仍为 `not_run`。
