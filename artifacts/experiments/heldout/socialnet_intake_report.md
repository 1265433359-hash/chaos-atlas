# Social Network 只读预检报告（SOCIALNET intake, Stage C）

> 日期：2026-08-10
> 状态：静态 intake 完成;snapshot 见 `socialnet_knowledge_snapshot_pre.json`
> 本阶段未部署/未注入/未运行实验;bring-up/稳定/2-baseline 闸门保持 `not_run`

---

## 1. Canonical 来源

| 项 | 值 |
|---|---|
| canonical URL | `https://github.com/delimitrou/DeathStarBench`（findings.md:84 引用） |
| 子目录 | `socialNetwork/` |
| commit | `6ecb09706140f8730b5385c08f1386c654c3c526`（同 Hotel 仓库 master 浅获取,2026-08-10） |
| license | GPL-2.0 |
| 获取方式 | WSL sparse checkout（仅 socialNetwork/,仓库外,未提交 git） |
| 实际路径 | `/root/heldout_src/socialnet/socialNetwork` |

## 2. 关键文件 SHA-256

| 文件 | SHA-256 |
|---|---|
| `docker-compose.yml` | `b2b3dec888d099a60101b8a3d1eae9bf71ef18ef64b557942048db905ec4d529` |
| `social_network.thrift` | `2a199791eb2c12ea8aa1ff259d0c0d98b89e67ed27868a4991a23d5cb4bdbaa2` |
| `config/service-config.json` | `783c9b76cc673f8f583b6fdc02a8f2272a9b183cad24c3edc94267458f689057` |
| `src/ComposePostService/ComposePostService.cpp` | `ba0d2b08c0df94efcb8d53fd6f817a3259c028a75196adf9b9fa350601216211` |
| `src/tracing.h`（共享 infra） | `ec488043c28083fce487725ba3b1765470828407198d26edf58bf54e41290f42` |
| `src/utils_thrift.h`（共享 infra） | `75702e79c4f42b23bf6921580aeabc57a39e1d2e51d9d0007b84745ad7b46953` |
| `src/utils.h`（共享 infra） | `064b444be99f443f9041e60608f9453f8a8ccd7ce1e6e1fdb9fe05bef00f9db7` |

## 3. 服务清单与服务依赖图

- **服务（docker-compose）**:social-graph-service、compose-post-service、post-storage-service、user-timeline-service、url-shorten-service、user-service、media-service、text-service、unique-id-service、user-mention-service、home-timeline-service、nginx-thrift、media-frontend + 基础设施（mongodb ×6、redis ×3、memcached ×4、jaeger-agent）
- **技术栈**:C++/thrift（与 Hotel Go/gRPC **不同**;与 ESHOP .NET 也不同）
- **thrift 服务接口**:UniqueIdService、TextService、UserService、ComposePostService、PostStorageService、HomeTimelineService、UserTimelineService、SocialGraphService、UserMentionService、UrlShortenService、MediaService

**调用边（静态,ComposePostService/HomeTimelineService 源码）**:
```
nginx-thrift -> (HTTP 路由到各服务)
ComposePostService -> PostStorage, UserTimeline, Text, User, Media, HomeTimeline, UniqueId (7 下游)
HomeTimelineService -> PostStorage, SocialGraph (2 下游)
```
（其余服务下游边未逐文件展开,标记 unknown 待扩展核查）

## 4. 调用超时 / retry / fallback / circuit breaker

- **显式 thrift timeout**:`config/service-config.json` 各服务 `"timeout_ms": 10000`（10s）——**与 Hotel/ESHOP 不同（它们无 per-request timeout）**
- ComposePostService 源码从 config 读 `post-storage-service["timeout_ms"]` 等,构造 ClientPool
- retry/fallback/circuit breaker:未逐文件确认,标记 unknown（ClientPool 语义待扩展核查）
- 可观测:Jaeger（jaeger-agent;`src/tracing.h` 共享 OpenTracing 封装）

## 5. Manifest / 镜像 / replicas / probe / PDB / HPA

- docker-compose.yml 多文件（docker-compose.yml / -sharding / -swarm / -tls）+ helm-chart/socialnetwork + openshift
- 镜像:各服务构建（Dockerfile 存在）;nginx-thrift、media-frontend 等
- k8s replicas/PDB/HPA/probe:28 个 sub-chart 已核对；replicas=1、无业务 probe/PDB、HPA disabled → `verified`
- 共享 infra（同仓库）:tracing.h / utils.h / utils_thrift.h —— **与 Hotel 共享 DeathStarBench 基础设施**,须标注 `shared_infra_deathstarbench` 并在 SOCIALNET 各自重新核对

## 6. fault family 可支持

- delay/loss:thrift 边理论上可注入，但只对来源核验的边开放候选
- kill:helm-chart 28 个 sub-chart 已核查，replicas/probe/PDB/HPA 状态已验证，可进入 availability 候选
- **候选池潜力**:目前 9 条边具有完整源码 SHA（ComposePost 7 + HomeTimeline 2）；另 3 条已发现但因源码 SHA 未完成而排除，pilot 24/formal 48 仍标 `unknown`

## 7. 泄漏审计（追加,与 Hotel 同仓库）

- **SE/DP/JE 扫描**:`social`/`SOCIALNET`/`media`/`MEDIA`/`DeathStar` 全部 **0 命中**（Stage B 已确认）——无后验污染
- **共享 infra 剥离规则（强制）**:
  1. SOCIALNET contract 边**必须从 socialNetwork/ 源码独立重建**,不得复用 Hotel contract 结论;
  2. 共享 infra（tracing.h/utils.h/utils_thrift.h）标注 `shared_infra_deathstarbench`,不伪装成项目特定;
  3. 通用 SE/DP/JE 允许使用,但 snapshot provenance 中通用与项目特定分离
- **结构性风险**:ComposePostService 有 7 下游、HomeTimeline 2 下游——**SOCIALNET 有显式 10s thrift timeout → 有 protected 候选**；UserTimeline/User/SocialGraph 的 3 条边虽已发现，但源码 SHA 未完成，当前不得进入候选池

## 8. go_no_go

**`ready_for_snapshot`**（源码可追溯、commit 固定、服务图/调用边/超时/可观测静态确认）
- 注意:k8s replicas/PDB 未逐文件核对 → availability 候选 `unknown`（helm-chart 待扩展核查）
- bring-up/稳定/2-baseline 闸门 `not_run`
