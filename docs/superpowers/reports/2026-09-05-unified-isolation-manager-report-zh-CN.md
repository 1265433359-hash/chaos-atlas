# 统一 IsolationManager 实现与验收报告

日期：2026-09-05

> 2026-09-06 范围校正：本文记录的是当时实现与验收快照，不代表当前安全边界。原 L1 ephemeral
> 和 L2 使用 `pause:3.10.1`，只能证明最小资源生命周期，不能称为完整应用克隆或真实目标代表性；
> 原 Ready 判定、全机 L3 锁域、运行根固定、未知 profile 状态和敏感 plan 也存在后续发现的缺口。
> 最新纠错与真实证据见 `2026-09-06-p0-isolation-hardening-report-zh-CN.md`。本文下方历史数字不作
> 当前能力声明。

结论：IsolationManager 子项目的实现与真实 L1/L2/L3 无故障生命周期验收通过。它解决的是
“在哪里安全测试”以及“如何可靠回收环境”，没有执行故障、没有生成业务 Oracle，也尚未接入
RunEngine live。

## 已交付能力

- 一个公共 `IsolationPlanner`，消费 32 核心加 9 provisional 能力记录，并保证隔离等级只升不降；
- 一个持久化 `IsolationManager`，统一管理 prepare、Ready、release、recover 和过期回收；
- 外置原子 LeaseStore、进程间创建锁、TTL、每项目单 active lease 和全机单 L3 lease；
- Kubernetes L1 adopted、L1 ephemeral 和 L2 sandbox Provider；
- 独立 Minikube home、kubeconfig、证书及唯一 profile 的 L3 Provider；
- 安全蓝图编译器，拒绝真实 Secret 值、Secret/ConfigMap 环境引用、PVC、hostPath、host namespace、
  ServiceAccount、hostPort、特权容器和新增 Linux capability；
- 精确 namespace/profile、租约标签和 UID 三重清理门禁；
- `chaosatlas isolation` 公共 CLI 和可重复的真实验收脚本；
- Immich、ERPNext、Medusa、Rocket.Chat 的薄 L1 专用测试副本声明。

## 自动化验证

- 隔离专项测试：38 passed；
- 全量测试：309 passed；
- 41 项默认隔离映射全部覆盖：L1 25 项、L2 15 项、L3 1 项；
- `compileall`、架构契约、Sock Shop dry-run、Online Boutique dry-run 和产品边界检查通过；
- `git diff --check` 通过，仅有 Windows LF/CRLF 提示。

专项测试覆盖摘要、状态机、外置原子写入、损坏 lease fail-closed、并发创建门禁、Provider 选择、
部分创建失败、runner 清理异常、重复清理、TTL 回收、UID 不一致拒删、蓝图安全规则、L1/L2/L3
生命周期和 CLI 授权门禁。

## 真实生命周期证据

逻辑证据目录：
`%LOCALAPPDATA%\ChaosAtlas\acceptance\isolation-manager-20260905-2330`

机器实际解析目录记录在 `acceptance-summary.json` 的输出字段中。验收结论如下：

| 阶段 | Provider | Ready | 清理 | 零残留 |
|---|---|---:|---:|---:|
| L1 adopted Immich | kubernetes-l1 | 通过 | released | 原 namespace/UID 未变 |
| L1 ephemeral app clone | kubernetes-l1 | 通过 | released | namespace NotFound |
| L2 sandbox | kubernetes-l2 | 通过 | released | namespace NotFound |
| L3 disposable cluster | minikube-l3 | 通过 | released | profile、machine 目录、kubeconfig 和租约缓存文件均不存在 |

总结果为 `verified`；四项目环境前后快照完全相同，敏感模式扫描命中 0，错误 0，
`fault_injection_performed=false`。L3 为绕开代理对 Google Storage 的零字节下载，仅读取本机已有的
公开 Kubernetes containerd 预载镜像包，在独立 Minikube home 内建立租约所有的硬链接或副本；
profile、kubeconfig、证书和集群状态没有与现有 `chaosatlas-apps` 复用，租约文件在清理后删除。

第一次 L1 ephemeral 验收还真实验证了失败路径：集群未缓存 `pause:3.9`，Pod 进入 ErrImagePull，
Manager 在 Ready 超时后进入清理；人工中断后，`recover` 根据持久化 lease 将 terminating namespace
确认清空并把 lease 置为 released。正式验收随后固定使用集群已有的 `pause:3.10.1`。

## 能力边界

这次实现为 41 项能力提供了 L1/L2/L3 环境承载路径，但不等于 41 种故障已经可注入，也不会仅因
环境准备成功就把能力证据提升为 E1。它消除了“缺少安全隔离环境”这一类前置阻塞；具体能力仍需
后续 Provider/Executor、Oracle、恢复契约和真实注入证据共同通过。RunEngine 接入仍按上位设计作为
后续子项目完成，不能从本报告宣称四项目已经支持全面故障测试。

## 已知的非本次阻塞

仓库卫生检查发现根目录 `environment-reports/`。该目录创建于本实现开始前，当前仍被运行中的 Dify
PostgreSQL、Nginx 等容器作为 bind mount 使用，约 80 MB、2463 个文件。直接移动会破坏活跃 Dify
运行状态，因此本次未擅自停止容器或迁移它。它使仓库级综合 acceptance 保持 `partial`，但不影响
IsolationManager 专项与真实生命周期的 `verified` 结论。后续应安排一次 Dify 维护窗口：停止栈、
迁移到 `%LOCALAPPDATA%\ChaosAtlas\runtime\dify-1.17.0-docker`、更新 Compose 路径、重建并验证，再让
workspace hygiene 归零。
