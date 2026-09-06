# 四项目正式实验准入设计

日期：2026-09-06

## 目标

沿用现有统一 `RunEngine -> IsolationManager -> fault executor -> transaction Oracle -> evidence gate` 架构，把 Rocket.Chat、ERPNext 和 Immich 推进到正式实验前的人工事务契约审批门。Medusa 已有的真实 Kubernetes API L2 证据继续复用，不新建第二条实验流水线。

本阶段只建立正式实验准入能力和真实 canary 证据，不执行未经批准的业务写入，不把模拟测试、健康检查或单次机制成功表述成正式业务结论。

## 已确认方案

采用逐项目推进：`Rocket.Chat -> ERPNext -> Immich`。

每个项目必须依次完成：

1. 编译不含静态凭据、仅使用合成空数据的 L2 隔离蓝图；
2. 创建真实可销毁副本，并验证关键依赖、应用 Ready、业务健康探针和清理；
3. 通过公共 `chaosatlas run --mode live --isolation-fault ... --approve-isolation` 入口分别执行 `secret_rotation`、`image_pull_failure`、`pod_unschedulable`；
4. 验证注入效果、恢复探针、故障对象清理、租约释放和命名空间消失；
5. 将合格证据接入 `CapabilityEvidenceIndex`，重新生成项目能力矩阵。

一个项目失败时保留真实负向证据并定位原因。与该失败无依赖的后续项目可以继续，但失败项目不能被标记为已准入。

## 项目边界

### Rocket.Chat

使用 Rocket.Chat 与 MongoDB replica set 的最小真实副本。数据从空库初始化，不复制生产数据。只有 Rocket.Chat API 健康、MongoDB replica set Ready 且清理完整时，才能执行三项隔离故障 canary。

### ERPNext

保留 ERPNext 启动所必需的 MariaDB、Valkey、Gunicorn、Nginx、Socket.IO 和 worker 依赖，但只初始化合成站点。若完整拓扑受镜像、初始化时间或资源预算阻断，应保存诊断证据；不得用 `pause` 或静态 HTTP 容器替代 ERPNext 业务副本。

### Immich

先解决现有 L2 副本中 Immich Server 对 PostgreSQL 的 DNS 启动失败。必须证明同一蓝图连续创建时可稳定 Ready，才能恢复三项故障 canary。最小 DNS Pod 成功只能用于定位，不能作为 Immich 准入证据。

## 正式实验前的统一准入门

项目进入事务契约审批包必须同时满足：

- 代码已实现且专项测试、全量测试通过；
- 至少一轮真实副本基线、故障机制、恢复和清理证据完整；
- 证据绑定项目 revision、Kubernetes context、隔离 lease、唯一 run id 和机制证明；
- 外层隔离 lifecycle 为 `verified`，cleanup state 为 `released`；
- 敏感信息扫描无命中；
- 能力矩阵仅按证据索引计算，不允许手工提升状态；
- 事务 Oracle 草稿包含准备、执行、观察、精确清理、补偿和失败分类；
- 所有业务写入步骤在人工批准前保持冻结。

三次独立复现是正式异常与 Issue 草稿的门槛，不是本阶段单次机制准入 canary 的门槛。单次 canary 只能证明当前项目副本上的机制可执行。

## 事务契约审核包

完成可达到的项目准入后，生成一次集中审核包。每个项目包括：

- 被测业务事务及其风险边界；
- 请求步骤、断言、对象所有权与唯一标识；
- baseline、故障期、恢复期的配对关系；
- 精确清理与失败补偿；
- 合约哈希、项目 revision 和运行环境；
- 首批建议实验及为什么选择它们；
- 尚未解锁能力及其真实阻断原因。

只有用户明确批准审核包后，才运行 P5 正式业务实验。

## 失败处理与证据表述

- 应用未 Ready：记录为副本保真或环境阻断，不执行注入；
- 注入未观察到预期机制：记录为 capability blocked，不声称支持；
- 恢复或清理失败：整体运行降级为 partial/failed，并保留租约供安全恢复；
- 业务断言失败：在三次独立配对复现前只生成候选发现，不生成可提交 Issue；
- 平台证据不能自动替代项目业务证据；模拟结果不能进入真实证据等级。

## 测试与验收

实现时先增加蓝图和统一入口的单元/契约测试，再运行专项测试和全量测试。真实验收产物写入 `%LOCALAPPDATA%/ChaosAtlas/runs`，仓库只保存不含秘密的规格、实现、测试和汇总报告。

每个阶段提交一个可回滚的 Git 提交并推送。最终报告严格分为“已实现”“已测试”“真实证据支持”“仍阻断”四部分。

## 非目标

- 本阶段不运行正式业务写入实验；
- 不为四个项目另建适配器式实验引擎；
- 不在当前缺少 `ebtables/broute` 的 WSL2 环境重复 HTTPChaos 注入；
- 不为了清零矩阵而降低证据门槛；
- 不提交上游 Issue，只准备后续可人工审核的材料。
