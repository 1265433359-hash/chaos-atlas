# Online Boutique 运行时实验结果（阶段 3b）

> 日期：2026-08-05
> 方法：复用 train-ticket 的「测试节点中心 + 证据链」方法论
> 环境：Docker Desktop Kubernetes 1.36.1（2 节点）/ Chaos Mesh 2.8.3 / 隔离 namespace `online-boutique-lab`
> 版本：Online Boutique @ `9a4616e7`（v0.10.6 镜像语义），本地构建 lab 镜像

## 部署与基线（阶段 3b-1/2/3）

- **镜像构建**：因 `us-central1-docker.pkg.dev`（Artifact Registry）在本机网络不可达，改用**本地源码构建**全部 10 个服务镜像（Go×4、Node×2、Python×2、.NET×1、Java×1），替换 `gcr.io/distroless` 运行时基镜像为 alpine，Go 依赖走 `goproxy.cn`，移除 `@google-cloud/profiler`（避免 pprof musl 编译）。
- **部署**：`online-boutique-lab` 隔离 namespace，**不含 loadgenerator**（避免负载污染基线），`imagePullPolicy: Always`（支持重建后拉取新镜像）。
- **修复的构建缺陷**（Lab 构建自身，非上游 bug）：frontend 漏 `templates/`+`static/`（panic 启动失败）、productcatalog 漏 `products.json`（fatal 退出）、email 缺 `python-json-logger`（ModuleNotFoundError）。
- **基线**：首页 `GET /` HTTP 200 / ~25-30ms；`PlaceOrder`（cart→product-catalog→currency→payment→shipping→email 全链路）HTTP 成功 / **~17ms**，email 服务端确认收到通知。

## 实验 1：checkout→payment 2000ms 延迟注入（NetworkChaos）

**测试节点**：`paymentservice`（inbound delay 2000ms，60s，mode all）

| 阶段 | PlaceOrder 延迟 | 结果 |
|---|---|---|
| 基线 | ~17ms | 成功 |
| 注入中（3 次） | 2019.2 / 2017.6 / 2019.7 ms | **全部成功**（+2000ms 精确传导） |
| 恢复后（3 次） | 21.8 / 19.0 / 17.5 ms | 成功，回到基线 |

**关键发现（运行时证据）**：
1. **延迟 1:1 传导，无任何中间层防护**：checkout 的 `chargeCard` 无 timeout/retry/fallback → 下游 2s 延迟完整叠加到端到端下单延迟（2019ms ≈ 17ms 基线 + 2000ms 注入）。验证静态假设。
2. **探针超时触发容器重启（意外发现）**：paymentservice 的 liveness/readiness probe（gRPC, 1s 超时）在 2s 延迟注入下失败 → kubelet 判定不健康 → **容器被 SIGKILL（exit 137）** → 自动重启恢复。这是**自动恢复机制**，但代价是容器重启（注入本身未恢复前先因探针触发重启）。
3. 恢复后链路完全正常，无数据损坏（订单 id / tracking 均正常生成）。

## 实验 2：productcatalog pod-kill（PodChaos）

**测试节点**：`productcatalogservice`（pod-kill，60s，mode all）

| 阶段 | 首页 `GET /` | 结果 |
|---|---|---|
| 基线 | HTTP 200 / ~25ms | 正常 |
| kill 生效后（多次） | **HTTP 500 / ~9ms** | **级联失败** |
| pod 重建期间（~2 分钟） | HTTP 500 | 持续不可用 |
| 恢复后（3 次） | HTTP 200 / 24.9 / 45.9 / 21.6 ms | 回到基线 |

**关键发现（运行时证据）**：
1. **核心数据路径无降级 → 全站级联**：frontend `homeHandler` 对 `getProducts`（productcatalog）无 timeout/降级，productcatalog 故障 → **首页整页 500**（8.9ms 即失败）。验证静态假设。
2. **自动恢复 = 依赖 Kubernetes pod 重建**：无业务层恢复逻辑，恢复完全依赖 Deployment 重建（本次重建含镜像拉取等待耗时 ~1.5-2 分钟），期间服务不可用。
3. 恢复后回到基线，无残留。

## 实验 3：checkout→payment 100% 丢包（NetworkChaos）

**测试节点**：`paymentservice`（inbound loss 100%，45s，mode all）

| 阶段 | PlaceOrder 行为 | 结果 |
|---|---|---|
| 基线 | ~17-23ms | 成功 |
| 丢包中（2 次） | **DEADLINE_EXCEEDED @ 10008.3ms / 10003.3ms** | **挂起 10 秒直到客户端 deadline 才失败** |
| 丢包中 payment pod | Ready 0/1（探针失败），**未触发重启** | 与实验 1 的延迟→重启行为形成对照 |
| 恢复后（3 次） | 17-23ms | 成功 |

**关键发现（运行时证据）**：
1. **无超时 → 故障无限挂起，直到调用方边界**：checkout `chargeCard` 无 timeout，100% 丢包导致请求**挂起整整 10 秒**（客户端 gRPC deadline），而非快速失败。这比延迟实验更严重——故障表现为"无限阻塞"而非"延迟边界"。
2. **丢包 vs 延迟对探针的不同影响（对照发现）**：
   - 实验 1（2s 延迟）：探针 1s 超时失败 → kubelet **SIGKILL 重启**（exit 137，自动恢复）
   - 实验 3（100% 丢包）：探针超时失败但**未重启**（只标记不健康 0/1）——丢包导致连接无法建立而非响应慢，kubelet 的探针处理行为不同
3. 恢复需删除 chaos 资源后链路正常（`recovered` 状态不自动删除 CR，需手动清理——与 train-ticket 的 cleanup 纪律一致）。

## 附带实验 4：adservice 缺失时的降级（静态假设验证）

adservice 因 `services.gradle.org` 网络不可达构建失败（非代码问题），以 ImagePullBackOff 状态运行。

| 场景 | 首页 | 商品页 |
|---|---|---|
| adservice 完全不可用（40+ 分钟） | **HTTP 200** / ~22ms | **HTTP 200** |

**关键发现（运行时证据）**：
1. **"唯一降级点"假设验证**：frontend `getAd`（100ms 超时 + `chooseAd` 吞错返回 nil）在广告服务整体缺失时**完全降级**，系统主链路不受影响。这与实验 2（productcatalog 缺失 → 首页 500）形成**鲜明对照**：核心数据路径硬失败 vs 非核心广告路径优雅降级。
2. **对照组价值**：productcatalog 和 adservice 同属"服务缺失"，但前者导致整站 500、后者无感知——证明 Online Boutique 的降级策略**只覆盖非核心路径**。

## 结论对照静态假设

| 静态假设 | 运行时验证 |
|---|---|
| checkout 业务链（payment/email/shipping）无 timeout/retry/fallback | ✅ 验证：2s 延迟全额传导，无降级 |
| frontend 核心数据路径（products/cart/currency）无降级 → 硬 500 | ✅ 验证：productcatalog kill → 首页 500 级联 |
| 唯一降级是广告（100ms timeout + 吞错） | ✅ 验证：adservice 完全缺失时首页/商品页仍 200（附带实验 4） |
| email 失败是 Warn 降级（非致命） | ✅ 静态已确认 `log.Warnf`；实验 1 中 email 成功路径验证 |

## 证据文件

- 注入 manifest：`chaos/payment-delay-r1.yaml`、`chaos/productcatalog-kill-r1.yaml`
- 客户端：`ob_client.py`（PlaceOrder gRPC 客户端）
- 基线/注入/恢复时序见上文表格

## 已知限制

- adservice 未参与注入实验（Gradle 下载网络不可达）；但以其"整体缺失"状态验证了降级路径（附带实验 4）
- 实验为单次注入，无统计重复（后续可做多次重复取置信区间）
- 未注入 checkout→email / checkout→shipping 单独故障（可后续补充）
