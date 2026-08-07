# 混沌测试方法对比实际执行

## 目标

在不把既有运行证据冒充为新对比数据的前提下，实际运行 Track K 控制集、统一候选接口 pilot 和可运行的主实验；对外部方法缺少代码/依赖/环境的部分如实记录为 blocked 或 adapter，不伪造结果。

## 阶段

| 阶段 | 状态 | 交付物 |
|---|---|---|
| 1. 主机/集群前置检查 | complete | Docker/Kubernetes 可用；kubeconfig 需主机侧权限；WSL2 ebtables 限制已记录 |
| 2. 运行器与干净隔离 smoke | complete | Station 100ms delay：注入/恢复/清理确认，动态 body 契约修复 |
| 3. Track K 控制集 | complete | HTTP、PodChaos、gRPC、负控和 K7 重启证据 |
| 4. 公共候选接口和方法适配 | complete | candidate_plan registry、五方法状态和统一 gate |
| 5. Pilot | complete | 两项目、五方法、3 replicate、K=6 的 gate pilot |
| 6. 主实验/确认/盲评 | complete | 六个场景各 3 次有效重复，含恢复/清理确认 |
| 7. 统计汇总和限制报告 | complete | 18 条运行记录汇总、invalid/duplicate、负控、阻断项和限制说明；未伪造 U@10 算法排名 |
| 8. 深入公平性/消融/统计阶段 | in_progress | 同预算方法对比、故障发现覆盖率、组件消融、成本和置信区间 |

## 下一阶段深入验证

1. 固定相同候选池、故障类型、强度、持续时间、随机种子和时间预算，恢复 ChaosEater/FastFI 的可执行环境；无法原样运行的实现必须单独标注为 adapter/reimplementation。
2. 为每个方法记录 `valid injection rate`、`unique meaningful faults`、`discovery coverage`、`time-to-first-finding`、`false positive`、`duplicate/unreachable rate`、恢复时间和 CPU/内存成本。
3. 将当前 6 个场景扩展为分层故障矩阵：网络延迟/丢包、Pod kill、服务不可用、资源压力，并覆盖入口服务、关键依赖和非关键依赖。
4. 对本方法做消融：去掉业务路径约束、去掉运行时门禁、去掉恢复/探针分析、只保留随机选择；每个消融都使用同一候选池和预算。
5. 每个核心场景至少 5 次重复，报告中位数、IQR 或 bootstrap 95% CI；配对方法比较使用 Wilcoxon 或置换检验，并进行多重比较校正。
6. 预先定义“更好”：发现更多真实故障、误报更少、重复/不可达更少、发现更快，且不能以更高的注入失败率或更长运行成本换取表面覆盖率。

## 执行边界

- 只使用隔离 namespace/集群和固定 commit；禁止生产环境、`default` namespace、`mode: all` 和未批准的跨 namespace selector。
- 所有运行必须保留 baseline、injection confirmation、recovery、cleanup 和分类结果。
- 平台阻断、缺依赖、方法无公开实现和 out-of-domain 必须单独计数，不得充当应用防御或算法失败。
- 外部方法没有可执行代码时，先完成公开版本原样可行性检查，再决定是否做明确标注的 adapter/reimplementation。

## 错误记录

| 错误 | 尝试 | 处理 |
|---|---:|---|
| PowerShell kubectl jsonpath 引号解析失败 | 1 | 改用标准列表/custom-columns；已有 Pod Ready 证据 |
| 动态 UUID 被精确 body 比较误判为契约变化 | 1 | 分类器新增显式 `status_only` body contract，默认仍为 exact |
| 新 lab namespace 单测最初 CRD mock 条件错误 | 2 | 修正 mock 后 targeted + 全量 25 tests 通过 |
| GitHub 仓库通过用户 Git 代理克隆失败 | 1 | `127.0.0.1:7897` 不可达；未修改全局 Git 配置 |
| 禁用 Git 代理后直连 GitHub 失败 | 2 | 一次审批超时、一次连接重置；外部方法标记为环境阻塞而非实验失败 |
| 应用内浏览器加载 GitHub 仓库超时 | 1 | 页面只有空 document；继续本地可执行矩阵并保存阻塞证据 |
| OTel 原始清单缺少两个 ConfigMap | 1 | 新增 Kustomize 生成器，补齐 postgres-init 与 flagd-config |
| 误将 cart targetPort 从 8080 改为 7070 | 1 | 容器日志确认实际监听 8080；撤回修改并新增端口映射回归测试 |
| OTel 首轮基线失败后仍执行了注入 | 1 | 该轮作废；运行器新增 baseline success gate，失败时不再注入 |
| OTel QUOTE_ADDR 重复包含 `/getquote` | 1 | shipping 日志确认双路径 404；改为官方基础地址，第二轮由门禁阻止注入 |
| OTel payment 基线缺少中央 flagd | 1 | payment 已收请求但 feature flag 调用超时；补 flagd Service 和显式地址 |
| OTel 延迟轮次选中正在删除的旧 payment Pod | 1 | 零注入，轮次作废；门禁排除带 deletionTimestamp 的 Pod |
| K7 首轮重启后目标在超时内仍 NotReady | 1 | 捕获 latency→connection refused；分离 restart/Ready 状态并在清理后等待恢复再重注入 |
| K7 第二轮 Kubernetes Ready 早于业务恢复 | 1 | 重注入首请求连接拒绝；新增清理后成功业务请求门禁 |
