# TeaStore 只读预检报告（TeaStore intake, Stage C3）

> 日期：2026-08-10
> 状态：静态 intake 完成;snapshot 见 `teastore_knowledge_snapshot_pre.json`
> 本阶段未部署/未注入/未运行实验;bring-up/稳定/2-baseline 闸门保持 `not_run`

---

## 1. Canonical 来源

| 项 | 值 |
|---|---|
| canonical URL | `https://github.com/DescartesResearch/TeaStore` |
| commit | `34b37f7e7be433ce72d5f9455e66922a13116749`（master 浅获取,2026-08-10） |
| license | Apache-2.0 |
| 获取方式 | WSL shallow fetch（仓库外,未提交 git） |
| 实际路径 | `/root/heldout_src/teastore` |

## 2. 关键文件 SHA-256

| 文件 | SHA-256 |
|---|---|
| `examples/helm/values.yaml` | `4b5dcbfd2752b8206343fb0b2029e1a632bb626c39b7273af5ec295e73c2d36e` |
| `examples/kubernetes/teastore-ribbon.yaml` | `3e7b473c3086b208d7699081fe4091ca90b3fb20ae8489922ad01d57ad6934c9` |
| `examples/docker/docker-compose_default.yaml` | `cf26a369810edb8714f277deb4ec75afafe7772eb8a27bcd5703055904bd577d` |
| `utilities/.../loadbalancers/ServiceLoadBalancer.java` | `e5d44e7bf7726341732b489a9503b9c36911a989b27da927ef9e01077abebb07` |
| `utilities/.../registryclient/RegistryClient.java` | `a2e77b0e11bb8e2a6aefd3986ab5bb9a9fb3741b81fcb71b4ebe9c44ee18f302` |
| `pom.xml` | `198cb1cbd27dc8bcda09134ae4fc24f8ebaf9fe44a83295f497493255037fe6c` |

## 3. 部署路径核查（排除 all-in-one）

| 路径 | 状态 | 内容 |
|---|---|---|
| `examples/helm/` | ✅ verified | Chart.yaml + templates（auth/db/image/persistence/recommender/registry/webui 的 service + statefulset）+ values.yaml（含 autoscaling 配置） |
| `examples/kubernetes/teastore-ribbon.yaml` | ✅ verified | 7 个 Deployment（db/registry/persistence/auth/image/recommender/webui）+ Service;**Ribbon 负载均衡路径** |
| `examples/docker/docker-compose_default.yaml` | ✅ verified | compose 多服务部署 |
| `examples/kubernetes/teastore-all.yaml` | ⛔ 排除 | all-in-one 备用路径,不作为正式多服务部署 |

## 4. 服务清单与调用边

- **6 业务服务**:registry、persistence、auth、image、recommender、webui（+ db 基础设施）
- **调用机制**:`RegistryClient`（服务发现,`utilities/.../registryclient/`）→ `ServiceLoadBalancer`（Ribbon 负载均衡）
- **REST/Ribbon 边**（经 RegistryClient 服务发现 + Ribbon 选择）:
  - webui → auth / image / persistence / recommender（经 load balancer）
  - 各服务经 `RegistryClient.getServersForService(Service)` 发现下游
- **超时/重试/fallback/circuit**:
  - ✅ **有重试**:`ServiceLoadBalancer` 用 `DefaultLoadBalancerRetryHandler(0, 2, true)`（同服务器 0 次、跨服务器 2 次重试）
  - ✅ **有超时语义**:`LoadBalancerTimeoutException`（408 响应 + 重复 socket 超时抛异常）
  - fallback/circuit breaker:未逐类确认 → `unknown`
- **可观测**:Kieker（`examples/kubernetes/teastore-ribbon-kieker.yaml`）+ OpenTracing（webui `GlobalTracer.register(Tracing.init(...))`）;rabbitmq 变体（teastore-rabbitmq.yaml）

## 5. Manifest / replicas / probe / PDB / HPA

- `teastore-ribbon.yaml`:7 个 Deployment 无显式 `replicas`（默认 1）;无 PDB;无显式 probe
- `helm/values.yaml`:含 `autoscaling` 配置（enabled 值未在本轮确认 → `unknown`）
- **PDB/HPA**:grep ribbon.yaml + helm values.yaml 均 0 命中 PDB;HPA 依赖 autoscaling.enabled（未确认）
- **端口**:helm 各服务 port 8080（image/recommender/persistence 等均 8080）

## 6. fault family 可支持

- delay/loss:REST/Ribbon 边可注入（NetworkChaos 服务级）;Ribbon 重试语义使 **protected 候选可构造**（重试吸收瞬时 loss/delay）
- kill:PodChaos（ribbon 7 Deployment 完整目标）
- **候选池潜力**:6 业务服务 + registry 发现边 + Ribbon 重试 → pilot 24 / formal 48 可行（边×故障族×保护状态组合）

## 7. 知识隔离

- **SE/DP/JE 扫描**:`TeaStore`/`teastore`/`Descartes`/`descartes`/`Ribbon`/`ribbon` 全部 **0 命中** —— 无后验污染
- TeaStore contract 边**从 TeaStore 源码独立构造**（registryclient/Ribbon）,未复用 Hotel/SOCIALNET contract
- 通用 SE/DP/JE 允许使用,provenance 与项目特定分离

## 8. go_no_go

**`ready_for_snapshot`**（源码可追溯、commit 固定、部署路径完整、契约/超时/重试/可观测静态确认、无 PDB 但 Deployment 目标完整）
- 注意:helm autoscaling.enabled 值、Ribbon 重试的实际超时 ms 未确认 → 标注 unknown,不伪造
- bring-up/稳定/2-baseline 闸门 `not_run`
