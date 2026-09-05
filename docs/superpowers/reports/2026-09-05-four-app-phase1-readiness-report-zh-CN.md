# 四项目第一阶段接入与基线验收报告

日期：2026-09-05

项目：ChaosAtlas

结果：第一阶段方法接入通过；浏览器入口网关单独阻塞

## 验收范围

本阶段只验证以下能力，不进行消融测试和故障注入：

1. 四个项目都有合法、脱敏、版本冻结的项目 profile；
2. 每个项目都有已注册的只读 HTTP 业务 Oracle；
3. Kubernetes 工作负载已经恢复到 Ready；
4. 四个 profile 都通过同一个 `RunEngine` 完成 dry-run；
5. dry-run 只产生 planned 证据，不产生运行时 weakness、defense 或 Issue 结论；
6. 业务 Oracle 与计划执行目标保持一致。

原始运行产物保存在仓库外：
`%LOCALAPPDATA%\ChaosAtlas\runs\four-app-phase1-20260905-r3`。

## 能力矩阵

| 项目 | Profile | 工作负载 | 服务 Oracle | RunEngine dry-run | 计划目标 | 第二阶段资格 |
|---|---|---|---|---|---|---|
| Immich | 合法 | 通过 | 200，正文包含 `pong` | `dry_run_ready` | `immich-server` | 就绪 |
| Medusa | 合法 | 通过 | 200，正文包含 `OK` | `dry_run_ready` | `medusa-backend` | 就绪 |
| Rocket.Chat | 合法 | 通过 | 200，正文包含 `status=ok` | `dry_run_ready` | `rocketchat-rocketchat` | 就绪 |
| ERPNext | 合法 | 通过 | 200，正文包含 `pong` | `dry_run_ready` | `erpnext-nginx` | 就绪 |

四个项目均复用通用 Kubernetes adapter、通用 HTTP Oracle 和统一
`RunEngine`。本阶段没有新增四套项目专用适配器或第二条实验流水线。

## 本阶段发现并修复的方法问题

第一次 dry-run 中，候选排序会让 Rocket.Chat 选中辅助工具
`rocketchat-nats-box`，ERPNext 选中 `erpnext-gunicorn`，而不是业务 Oracle
所属入口。这会导致计划报告与后续业务验证对象不一致。

修复后，统一 RunEngine 在 dry-run 和 live 中都优先选择业务 Oracle
对应的 `pod_kill` 候选；离线事实通过通用 `service_target` 表达 Service 与
工作负载的关系。候选 ID 和公共 CLI 没有改变。

## 当前环境阻塞

四个 `*.local` 浏览器入口当前均不可达，但集群内 Service Oracle 全部通过。
根因位于本地入口网关，而不是四个应用：此前使用的 Dify Nginx 容器挂载了已归档的
`environment-reports` 路径，并且其上游依赖 Minikube 容器名解析。该容器无法恢复后，
本机 80 端口没有四域名转发器。

这个问题不阻止 ChaosAtlas 通过 Kubernetes Service port-forward 执行第二阶段
canary，但会阻止浏览器驱动或经 Ingress 的工作流实验。应将网关改为独立、外置、可重建
的运行组件，不能再次依赖被忽略或可能归档的仓库目录。

## 证据边界与后续工作

- 当前 dry-run 结果只能证明接入、候选生成、安全门和证据规划有效，不能证明应用存在异常。
- `pod_kill` 的 `supported` 表示通用执行器和安全契约可用，不表示应用结果已经验证。
- 当前 Oracle 是只读服务基线；事务型登录、创建测试数据和清理测试数据仍属于第二阶段。
- 本阶段没有满足三次独立复现与 RCA 门，因此没有生成应用 Issue 草稿。
- 下一阶段应按 Immich、Medusa、Rocket.Chat、ERPNext 的顺序各执行一次低风险 live canary。
