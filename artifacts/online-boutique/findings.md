# Online Boutique 发现记录（Findings）

> 日期：2026-08-05
> 版本：microservices-demo @ `9a4616e7`（v0.10.6 镜像语义），本地构建 lab 镜像
> 方法：测试节点中心 + 证据链（复用 train-ticket 方法论）
> 状态：运行时证据已采集，**未提交任何 issue**（保留待导师/用户决策）
> 证据来源：`experiment_results.md`（4 个实验）

---

## 第一层：有运行时证据的实质问题（候选 issue）

### F1. checkout 业务链（payment→shipping→email）无任何 timeout/retry/fallback
- **证据（实验 1）**：paymentservice 注入 2000ms 延迟 → PlaceOrder 从基线 17ms 变为 **2019ms**（精确 +2000ms，零防护 1:1 全额传导）
- **证据（实验 3）**：100% 丢包 → PlaceOrder **挂起 10 秒**（10008.3ms）直到客户端 deadline 才失败；若无调用方 deadline 则永久阻塞
- **代码**：`checkoutservice/main.go:252`（chargeCard→payment）、`:380`（email）、`:387`（shipping）——ctx 直接透传，无 WithTimeout
- **严重性**：中高。下游故障全额传导/无限挂起

### F2. frontend 核心数据路径（products/currencies/cart）无降级 → 单服务故障整站 500 级联
- **证据（实验 2）**：productcatalogservice 被杀 → 首页 **HTTP 500**（~9ms 即失败），持续 ~2 分钟直到 pod 重建
- **代码**：`frontend/handlers.go:62-90`（currencies/products/cart/汇率任一错误 → renderHTTPError 500）；`rpc.go:30-57`（无 timeout）
- **严重性**：高（级联面最大）。且违反 `docs/product-requirements.md` 的 "golden user journey"（productcatalog 是核心用户旅程必经路径）

### F3. 支付服务 liveness/readiness 探针（1s 超时）过紧，2s 延迟即触发 SIGKILL
- **证据（实验 1 意外发现）**：注入 2s 延迟 → 探针失败 → kubelet 判定不健康 → 容器 **SIGKILL（exit 137）** 自动重启
- **对比（实验 3）**：100% 丢包 → 探针失败但**不重启**（只标 0/1）——丢包 vs 延迟对探针行为不同
- **代码**：`kubernetes-manifests/paymentservice.yaml` 探针 `timeoutSeconds: 1`
- **严重性**：中

## 第二层：设计权衡（非 bug，可作建议/背景）

- 恢复完全依赖 Kubernetes Deployment 重建（实验 2 实测 ~2 分钟），无业务层恢复/降级——对"演示云产品"定位合理，但对"韧性演示"是缺口
- 广告是唯一降级点（100ms 超时 + 吞错）——adservice 整体缺失时首页仍 200（附带实验 4）——**正面案例**：降级策略只覆盖非核心路径
- 全项目无 Istio retry/timeout/circuit 声明（istio-manifests/、service-mesh-istio component 检索为空）——静态事实

## 第三层：环境问题（非项目问题，不报）

- adservice 构建失败（`services.gradle.org` 本机网络不可达）→ 未完成广告路径注入实验；但以 ImagePullBackOff 状态验证了降级路径（附带实验 4）
- Artifact Registry / github.com git 协议本机不可达 → 被迫本地构建镜像

## 诚实评估（报告决策依据）

- Online Boutique 定位 = "演示云产品"的 demo（product-requirements.md 要求 preserve simplicity）
- **F1（无 timeout）**：对 demo 可能是有意设计 → 报 issue 价值中等（只能作 enhancement/参考建议，不当 bug）
- **F2（核心路径级联 500）**：**最有报告价值**——直接破坏 golden journey，且与"广告优雅降级"形成矛盾对照（核心硬失败 vs 非核心优雅降级），是"声明了 A 却做了 B"型发现
- **F3（探针过紧）**：边缘案例，低价值
- **推荐提交顺序**：F2（主）→ F1（佐证/增强）→ F3（可选）

## 关联 train-ticket 对照

- train-ticket：benchmark 无韧性是设计使然，报告价值在基准完整性（如 Order 下游调用被注释）
- Online Boutique：活跃仓库 + 有降级设计（广告）→ "为什么核心路径没有同样的降级"是可讨论的真实问题
- 两项目对照证明：方法论可迁移（同套 test-node 中心 + 证据链在第二个项目立即产出运行时发现）
