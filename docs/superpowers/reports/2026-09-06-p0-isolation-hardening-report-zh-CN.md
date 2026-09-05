# P0 隔离纠错与真实验收报告

日期：2026-09-06。阶段状态：**P0 已完成；主应用集群的直接网络隔离能力保持 blocked**。

本报告严格区分代码、离线测试、真实生命周期、真实业务和真实故障。外置原始证据位于
`%LOCALAPPDATA%\ChaosAtlas\runs\p0-isolation-20260906-e\acceptance-summary.json` 和
`%LOCALAPPDATA%\ChaosAtlas\runs\p0-calico-20260906-b\acceptance-summary.json`；仓库只保存脱敏结论，
不复制运行日志和租约。

## 已实现

- 隔离等级改为 `required`、`proposed`、机制最低要求三者取最高，计划记录提议值和升级理由；
- plan v2 在序列化前脱敏，lease v2 固定 Kubernetes context/cluster UID 或 Minikube runtime root；
- Ready 同时检查所有非 Completed Pod、工作负载 generation、期望/Ready/Available/Updated 副本和 Job 完成；
- 全机 L3 声明移动到跨 store 协调根；prepare/release/reaper 使用每租约进程锁，运行中的 prepare 不被过期回收；
- L3 清理以 profile list 和 Docker 容器标签形成正向缺失证据，命令不可用、超时或 JSON 损坏均为 unknown 并闭锁；
- 允许且只允许同一 lease 创建的 ConfigMap、运行时生成 Secret 和空 PVC 引用；用户蓝图不能创建
  NetworkPolicy/Quota/LimitRange 放宽守卫；支持显式等待前置 Job；
- 创建 namespace 后 UID 尚未写回时，可依据精确名称和双所有权标签恢复；已有 UID 不同或 cluster UID 改变时拒绝删除；
- 进程内 `KeyboardInterrupt`/`SystemExit` 先清理再继续抛出。外部强杀无法保证同步 finally，依靠已持久化租约、TTL 和显式 recover。
- L3 可显式选择 Calico，并按 plan 中的安全镜像引用从宿主 Docker 预载到独立 containerd；子 L1/L2
  lease 记录父 L3 lease 身份，避免把嵌套环境误报成普通 namespace 隔离。

## 离线测试

- 2026-09-06 当前专项：45 passed；
- 当前全量回归：329 passed；`git diff --check` 通过；
- 反例覆盖：L1/L2/L3 组合、`stress_memory` L3 不降级、敏感 canary 不进入 plan、Ready+Pending、
  滚动更新未完成、跨 store L3、prepare/reaper 竞争、KeyboardInterrupt、cluster UID 改变、UID 写回窗口、
  L3 unknown、租约内安全引用和守卫放宽拒绝。

离线测试不等于真实集群或真实业务证据。

## 已获得的真实证据

在 `chaosatlas-apps` 上未注入任何故障：

| 项目 | 结果 | 证据范围 |
|---|---|---|
| Immich adopted L1 | 通过 | 现有专用 namespace 的 Ready/采用/释放；无业务事务 |
| 公共 CLI 跨进程恢复 | 通过 | 两个独立 CLI 进程保持同一 cluster UID/context 并 released |
| pause L1 | 通过 | 仅基础设施冒烟，不是应用克隆 |
| Medusa L1 子集克隆 | 通过 | 真实 2.20.1 后端、PostgreSQL、Redis、migration，`/health` 返回 200；无购物车事务 |
| Medusa Redis L2 | 部分 | 真实 Redis 镜像 PING 和清理通过；资源限制反例被拒绝 |
| NetworkPolicy 数据面 | **失败** | 源 namespace 的 Redis 客户端仍能跨 namespace 得到 `PONG`，证明当前 CNI 未执行该边界 |
| ResourceQuota 数据面 | 通过 | 带显式 3 CPU request/limit 的 server dry-run 被 `exceeded quota` 拒绝，不是 LimitRange 误判 |
| L3 disposable profile | 通过 | 独立 runtime root 内创建/Ready/删除；profile 清单、Docker 容器身份、目录和 kubeconfig 均确认无残留 |
| L3+Calico 嵌套 L1 Medusa | 通过 | 全自动本地镜像预载、migration、后端 `/health=200`、子 lease 清理 |
| L3+Calico 嵌套 L2 Redis | 通过 | 同 namespace PING、跨 namespace 超时拒绝、租约外探针前后 PING、Quota 拒绝 |
| L3+Calico 父环境清理 | 通过 | 第二轮全自动复现最终 `parent_cleanup_state=released`，敏感扫描 0、错误 0 |

Medusa 克隆明确替换了数据库持久卷、凭据和数据，遗漏 worker、admin UI、ingress；因此只能支持
“真实应用子集能在安全生成配置下启动并通过健康检查”，不能支持完整业务代表性。第一次克隆暴露
`sslmode=disable` 配置差异，修正后 migration 完成且健康检查通过。

两次人工强制终止验收进程后，临时 namespace 未由被强杀进程同步清理；公共 CLI 根据精确 lease、
cluster UID、namespace UID 和标签成功 recover，随后查询为 NotFound。它证明可恢复性，不证明强杀时
同步零残留。

## 尚未获得的证据与保留阻断

- 四项目事务 Oracle 尚未生成、审核、冻结，所以真实业务证据为 **未评估**；
- P0 按约束不做故障注入，真实故障证据为 **未运行**；
- 当前 `chaosatlas-apps` 的 NetworkPolicy 数据面未生效。仅创建 YAML 不能视为隔离通过；依赖网络边界
  的实验必须自动升级到已验证的 L3+Calico 嵌套路由，或保持 blocked；不能把 Calico 样例外推到主集群；
- `environment-reports/` 仍是活跃 Dify bind mount，仓库卫生阻断按既有维护边界保留。

## P0 退出结论

独立 disposable Minikube+Calico 的第二轮全自动复现已完成：真实 Medusa 子集、真实 Redis 目标、跨
namespace 拒绝、租约外探针、ResourceQuota、敏感扫描和父子零残留全部通过。P0 因此退出；下一阶段
进入 P3 OracleBuilder。P3 首次事务契约仍须形成具体草稿后由人工批准，P0 健康检查不能替代该批准。
