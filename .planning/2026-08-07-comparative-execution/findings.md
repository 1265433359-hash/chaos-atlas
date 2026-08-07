# Findings

## 本轮执行前已知条件

- 统一 runner：`tools/run_chaos_experiment.py`。
- 统一分类器：`tools/classify_runtime_result.py`。
- 运行时门禁：`tools/runtime_applicability_gate.py`。
- Train Ticket 固定 commit：`313886e99befb94be6cd45f085c98e0019f59829`。
- Online Boutique 固定版本：`9a4616e7`。
- OpenTelemetry Demo 固定版本：`2e72d8bc`。
- 当前协议的 pilot 目标：2 项目 x 5 方法 x 3 replicate x K=6，最多 180 个候选。

## 待验证

- 当前 shell 是否能访问 Docker daemon 和 kubeconfig。
- `kind`、`helm`、`skaffold`、Chaos Mesh 和外部方法依赖是否可用。
- runner 参数是否能对现有固定 mutation 完整重放。
- candidate_plan adapter 是否已存在；若不存在，先实现最小 registry，不直接批量注入。

## 前置检查结果（2026-08-07）

- 主机侧 Kubernetes context 为 `docker-desktop`；`train-ticket-lab`、`online-boutique-lab`、`chaos-testing`、`default` 均存在。
- Docker daemon 可用：Server 29.6.1，16 CPU，15.18 GiB，WSL2 kernel `6.18.33.2-microsoft-standard-WSL2`。
- 当前 shell 沙箱无法读取 kubeconfig/Docker config；主机侧只读检查已通过受控权限完成。
- `kind`、`helm`、`skaffold` 不在当前 PATH；已有 `chaos-kind` Docker 容器但本轮先使用已验证的 `docker-desktop` context。
- WSL2 ebtables 仍是 HTTPChaos 的已知平台阻断，不能作为应用防御结论。
- `desktop-control-plane`/`desktop-worker` 均 Ready，Chaos Mesh controller 3/3、daemon 1/1 Running。
- `train-ticket-lab` 六个核心 Pod 均 Ready；`online-boutique-lab` 的 `adservice` 为已知 ImagePullBackOff，其余主要服务 Ready。
- CRD 中 NetworkChaos、PodChaos、StressChaos、HTTPChaos 等资源均存在；当前 smoke 只使用单目标 NetworkChaos。
- Station smoke 于 2026-08-07 成功：`injectedCount=1`、`recoveredCount=1`、资源删除确认；5 个正式请求均 HTTP 200，中位 215.281ms，对旧基线 30.146ms 增加 185.135ms。
- Station `data` UUID 随部署变化；精确 body 比较会误报。分类器现支持显式 `--body-contract status_only`，并在输出中记录模式。
- runtime gate 已扩展为只允许三个隔离 namespace：Train Ticket、Online Boutique、OTel Demo；`default` 和 `mode: all` 仍硬阻断。
- 全量单元测试 25/25 通过。
- Online Boutique Track K single-target gate：payment delay、payment loss、productcatalog kill 三项均 ready。
- Productcatalog kill 重放两次均产生客户端超时/HTTP 500；第二次 runner 使用目标 replacement Pod Ready 语义确认恢复，cleanup 成功。
- 新增 gRPC runner 后，payment delay 基线 922.8ms、注入 2022.8ms，PlaceOrder 成功；100% loss 基线 40.4ms、注入 10006.9ms 后 DEADLINE_EXCEEDED。两项均 `injectedCount=1`、`recoveredCount=1`、cleanup 成功。
- 当前只有 Train Ticket 和 Online Boutique namespace；OTel Demo 需要重新部署后才能跑 K8/K9。
- 外部代码未在工作区：ChaosEater 官方仓库为 `https://github.com/ntt-dkiku/chaos-eater`；FastFI 为 `https://github.com/TanYuzhen/TOSEM-FastFI-Code`。
