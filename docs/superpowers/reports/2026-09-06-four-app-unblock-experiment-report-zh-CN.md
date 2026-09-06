# 四项目阻断解锁实验报告

日期：2026-09-06

本轮按“先解锁通用前置，再进入正式业务实验”的顺序执行了真实环境实验。所有产物均在仓库外的 `%LOCALAPPDATA%\\ChaosAtlas\\runs` 下。

## 实验结果

### 当前 `chaosatlas-apps` 主集群 L2

外置证据：`l2-medusa-unlock-20260906-a/acceptance-summary.json`。

- 真实 Medusa L1 子集克隆：Ready，`/health` 返回 200。
- L2 Redis 目标：同 namespace PING 通过。
- ResourceQuota 超限创建：被 API Server 拒绝。
- 跨 namespace 网络访问：仍返回 `PONG`，隔离检查失败。
- 所有租约已释放，临时 namespace 已清理。

结论：主集群当前 CNI 没有提供可证明的 NetworkPolicy 数据面隔离，不能作为需要跨 namespace 边界的高风险实验环境。

### 独立 L3 + Calico 集群

外置证据：`p0-calico-unlock-20260906-c/acceptance-summary.json`。

- 父 L3 Minikube 租约创建、Ready、释放：通过。
- 真实 Medusa 子集：健康检查通过。
- L2 Redis 同 namespace 访问：通过。
- 跨 namespace 访问：超时拒绝，通过。
- ResourceQuota 超限创建：拒绝，通过。
- 租约外源 Redis 前后健康：通过。
- 父租约和全部子租约：已释放。

结论：L3+Calico 可以作为需要强隔离的实验安全边界，但当前只验证了 Medusa/Redis 子集和基础设施守卫，不能外推为四项目完整环境。

## HTTP 能力状态

本轮没有执行 HTTPChaos 注入。L3 蓝图只包含应用和 Redis 镜像，没有 Chaos Mesh 控制面与 daemon；主集群运行时探测仍返回 `httpchaos_runtime_verified=false`。因此 HTTP 延迟、中断、状态错误、响应破坏、依赖错误和连接重置 6 项仍保持 blocked，未用健康检查或静态配置冒充 tproxy 正向证据。

## 四项目矩阵影响

本轮重新扫描结果仍为每项目 19 blocked、17 canary_required、5 inapplicable。L3+Calico 证据验证了可复用的隔离方案，但尚未绑定到四个项目 profile，也没有解除任何项目的业务故障能力状态。

## 下一步

下一步应在 L3+Calico 蓝图中加入固定版本 Chaos Mesh，并先对无业务写入的合成 HTTP 服务做 tproxy 正向 canary；通过后再把该运行时证据接入 CapabilityBootstrapper。四项目业务事务仍需冻结 Oracle 后才能执行。
