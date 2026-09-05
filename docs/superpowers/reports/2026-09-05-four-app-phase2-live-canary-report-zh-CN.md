# 四项目第二阶段真实 Canary 验收报告

日期：2026-09-05

项目：ChaosAtlas

结果：四项目均通过统一 `RunEngine` 完成一次低风险 `pod_kill`；方法能力验证通过，尚无异常满足上游 Issue 门槛

## 验收范围

本阶段不做消融测试，也不宣称已经覆盖完整业务。每个项目只对业务入口工作负载执行一次
`pod_kill`，并用独立的只读 HTTP Oracle 验证注入前基线、注入期间表现、Pod 替换恢复和
Chaos Mesh 资源清理。四次实验均由公共 CLI 进入统一 `RunEngine`，没有另建项目专用流水线。

运行环境：Minikube profile `chaosatlas-apps`，Chaos Mesh `2.8.4`。原始证据位于仓库外：
`%LOCALAPPDATA%\ChaosAtlas\runs\four-app-phase2-20260905`。

## 实验结果

| 项目 | 目标 | 基线 | 注入 | 观察 | 恢复 | 清理 | 证据认证 | Issue 门槛 |
|---|---|---|---|---|---|---|---|---|
| Immich | `immich-server` | 3/3 HTTP 200 | 已确认 | 先失败 4 次，后连续成功 3 次 | 新 Pod Ready | 残留 0 | 有效 | 未满足 |
| Medusa | `medusa-backend` | 3/3 HTTP 200 | 已确认 | 先失败 4 次，后连续成功 3 次 | 新 Pod Ready | 残留 0 | 有效 | 未满足 |
| Rocket.Chat | `rocketchat-rocketchat` | 3/3 HTTP 200 | 已确认 | 先失败 7 次，后连续成功 3 次 | 新 Pod Ready | 残留 0 | 有效 | 未满足 |
| ERPNext | `erpnext-nginx` | 3/3 HTTP 200 | 已确认 | 先失败 1 次，后连续成功 3 次 | 新 Pod Ready | 残留 0 | 有效 | 未满足 |

四次运行的批次状态均为 `completed`，子运行状态均为 `live_completed`，分类均为
`availability_degraded`，RCA 状态均为 `bounded`，知识状态均为 `provisional`，清理状态均为
`verified`。运行时 attestation 对 baseline、independent oracle、injection、observation、
recovery 和 cleanup 六项全部给出真值。

## 结论边界

这组结果证明 ChaosAtlas 现在能对四个不同应用完成同一套真实生命周期：发现候选、执行安全门、
建立基线、注入、独立观察、恢复、清理、分类、RCA 和学习证据落盘。

本轮观察到的短暂不可用不能直接作为四个上游项目的缺陷：这些入口工作负载均为单副本，删除唯一
Pod 后出现短暂中断是预期的可用性风险信号；每个项目目前只有一次有效运行，而且 Oracle 只是健康
端点。批次证据明确记录 `stable_reproduction_required=3`、
`stable_reproduction_verified_count=0` 和 `reproduction_gate_incomplete_count=1`。因此：

- 不写入正式知识库；
- 不生成声称可提交的上游 Issue 草稿；
- 将本轮结果保留为后续重复实验的 provisional 证据。

## 本阶段发现并修复的 ChaosAtlas 问题

在第一次成功注入之前，三次 Immich 诊断运行暴露了三个本项目问题：

1. live-batch 只接受动态候选 ID，公共 CLI 文档中的稳定候选别名会被拒绝；现已在统一批次入口解析稳定别名，并增加回归测试。
2. Windows 下动态候选 ID 生成的结果文件路径可能超过安全长度，导致真正的安全门原因被写盘异常遮蔽；现已用确定性摘要限制结果文件名，并增加长路径测试。
3. 运行适用性门将 Chaos Mesh 命名空间写死为 `chaos-testing`，无法识别标准安装所用的 `chaos-mesh`；现已按允许列表发现实际命名空间，并让 daemon 日志检查使用该命名空间。

上述三项属于 ChaosAtlas 自身缺陷，均已修复并有自动化测试。前三次诊断没有执行故障注入，产物保留
在同一外置证据根目录中，不能混入应用异常复现次数。

## 浏览器入口与环境状态

独立本地网关 `chaosatlas-apps-gateway` 已接入 Minikube Docker 网络并监听
`127.0.0.1:80`。四个浏览器健康地址均返回 HTTP 200。生成的 Nginx 配置放在
`%LOCALAPPDATA%\ChaosAtlas\runtime\chaosatlas-apps-gateway`，不再依赖 Dify 容器或仓库内
临时目录；网关脚本默认使用固定镜像摘要。

## 下一阶段准入条件

要形成可人工审核的上游 Issue 草稿，下一阶段至少需要：

1. 每个候选完成三次相互独立、条件一致的有效复现；
2. 将健康端点升级为项目级事务 Oracle，并自动清理测试数据；
3. 用对照或配置变化排除“单副本预期中断”等显然解释；
4. RCA、影响范围、最小复现步骤和敏感信息审查全部通过。

只有通过这些门槛，才把结果提升为正式 finding 并生成 Issue 草稿供人工审核。
