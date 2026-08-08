# Progress

## 2026-08-07

- 创建实际执行计划。
- 已载入公平对比协议和现有项目证据，准备进行只读环境检查。
- 沙箱内 kubeconfig/Docker socket 受限；主机侧只读检查确认 `docker-desktop`、两个隔离实验 namespace 和 Docker daemon 可用。
- 阶段 1 完成，开始运行器/隔离 namespace smoke。
- 集群健康检查完成：节点、Chaos Mesh 控制面和 Train Ticket lab 正常；记录 Online Boutique adservice 已知镜像阻断。
- 完成 Station NetworkChaos smoke：完整生命周期和离线分类证据写入 `artifacts/experiments/execution/`。
- 修复动态 UUID 契约误判，并把 runtime gate 安全扩展到三个隔离项目 namespace；25 个测试通过。
- 阶段 2 完成，开始 Track K 控制集。
- 创建三个 Online Boutique 单目标 Track K mutation，原 `mode: all` 文件未修改。
- 重放 productcatalog pod kill 并补齐 PodChaos replacement-Pod Ready 恢复语义。
- 新增 `run_grpc_chaos_experiment.py`，完成 payment delay/loss 基线、注入、恢复和清理证据。
- ChaosEater/FastFI 官方仓库地址已核对，但 Git 代理、直连和应用内浏览器下载均失败；不伪造复现结果。
- 为 OTel 控制集创建单目标、15 秒的 `mode: one` 安全 mutation 副本，原始 `mode: all` 文件保留。
- OTel 首轮基线因不完整夹具失败并作废；运行器新增 `invalid_baseline` 门禁，基线失败时不再注入。
- 对照官方 Compose 补齐 quote 服务、email production bind 和 cart 显式监听端口。
- Track K 主实验完成：Train Ticket station delay、Online Boutique productcatalog kill/payment delay/payment loss、OTel payment delay/payment loss 均完成 3 次有效重复；每次都有 baseline、injection、recovery 和 cleanup 证据。
- K7 probe-restart r3 观察到 paymentservice restart、Ready 超时和业务连接拒绝；已单独归一化为 `probe_restart_recovery_timeout`，不与普通注入效果混算。
- adservice 已记录为负控：两 Pod `ImagePullBackOff`，但 frontend baseline 5/5 为 HTTP 200；未执行注入，未计作算法失败。
- HTTPChaos 平台门禁记录为 blocked（WSL2 ebtables/tproxy 前置条件）；Train Ticket order network-delay 路径记录为 unreachable/deferred。
- 生成 `pilot_registry_r1..r3` 和对应 gate evaluation；M1/M2 外部复现因网络阻塞保持 blocked，M0/M3/M4 仅作为候选资格 pilot，不宣称算法排名。
- 生成 `comparative_results_summary.json` 与 `.md`：18/18 运行记录生命周期有效，六个场景各 3/3；全量测试 37 个通过，Python compileall 通过。
- 因 M1/M2 没有可执行外部复现、M0/M3/M4 pilot 仍共用受控候选库，本轮不计算或虚构 U@10/算法优越性排名；只报告可审计的运行效果、资格 gate 和阻断原因。
- 最终清理检查：三个隔离实验 namespace 无遗留 PodChaos/NetworkChaos/HTTPChaos；未触碰既有 `chaos-testing/real-inject-test`。
- 用户要求进一步深入后，新增阶段 8 计划：同预算公平复现外部方法、分层故障矩阵、方法消融、发现覆盖率/误报/成本指标，以及至少 5 次重复的统计检验。
- 阶段 8 开始：先固定 12 个跨三项目的核心候选矩阵和统一预算，生成可供 M0/M3/M4、外部 adapter 及 A0-A4 消融共同使用的 registry；本阶段先做 gate/coverage 检查，不直接批量注入。

## r4 补跑（2026-08-07，本会话）

- 审查 Codex 执行：41 测试通过、gate 审计 80/80、18 次有效生命周期，工具改动合理（body_contract_mode / 3-namespace gate / deletionTimestamp 排除）。
- 补跑 6 场景第 4 次重复（r4）：
  - TT station delay r4：5×200，113-120ms（response_preserved_latency_degradation）
  - OB productcatalog kill r4：4×超时(5s)+1×500（client_timeout_observed）
  - OB payment delay r4：2021.9ms（grpc_response_observed）
  - OB payment loss r4：10007.2ms DEADLINE_EXCEEDED（grpc_error_observed）
  - OTel payment delay r4：4927.4ms（grpc_response_observed）
  - OTel payment loss r4：10008.6ms DEADLINE_EXCEEDED（grpc_error_observed）
- 汇总更新：24/24 有效生命周期（6 场景 × 4 次），`valid_runtime_replicates=4`。
- 过程中确认的 gate 行为（非 bug）：payment pod 探针重启后未就绪 → gate 拒绝注入（正确纪律）；端口残留 → runner 端口占用失败（清理后重跑成功）；MSYS 路径转换 → `MSYS_NO_PATHCONV=1` 绕过。
- 41 测试通过；三个实验 namespace 无遗留 Chaos 资源。

## 2026-08-08

- ChaosEater adapter 真提取完成（选项 1）：`tools/chaos_eater_adapter/` 包复刻 FaultScenarioAgent 提示词/Fault 结构/7 故障类型枚举，无 docker-compose/langchain 依赖；LLM 后端可插拔（OpenAI 兼容协议，Ollama/DeepSeek/OpenAI 通用）+ MockBackend（确定性管线验证，明确标注非真实选择）。
- 生成脚本 `tools/generate_m1_adapter_plans.py`：读既有 registry → M1 plans（全局 rank 1-10、同候选池、I0 级上下文不泄漏静态评分/测量结论）→ 增量 registry `deep_matrix_registry_r1..r3_m1.json`；原 registry 与既有测试不动（M1 默认 blocked 的断言保持稳定）。
- M1 mock 产物 r1-r3 全部通过 evaluate（ready_for_injection 10/10，same_candidate_pool=True）；58 测试通过。
- 真实 LLM 运行待用户 API key（明天提供）；届时用 `--backend openai-compat` 覆盖 mock 产物并记录 model/tokens/event 溯源。

## 2026-08-08（下午）

- 真实 LLM 接入：用户提供 DeepSeek v4 flash 正式版 API key（经环境变量传入，不落盘）。`deepseek-v4-flash` 生成 M1 r1-r3 真实选择并覆盖 mock 产物；evaluate 全部通过（ready_for_injection 10/10，same_candidate_pool=True）。
- M1 真实选择三次高度稳定：`OB-PAYMENT-LOSS-100` / `OTEL-PAYMENT-LOSS-100` / `TT-STATION-DELAY-2000` / `OTEL-PAYMENT-DELAY-2000` 稳居前四；两次 100ms 低强度候选（TT-STATION-DELAY-100、TT-BASIC-DELAY-100）三次全排除。每次选择均记录 event/thought/model/tokens 溯源（prompt≈1.9k/completion≈3.6k，单次≈34s）。
- M1 与 M4（ours-full）存在实质差异：M4 偏好 Train Ticket（4 个 TT 候选入 top10，含两个 100ms 低强度候选），M1 更均衡（4 OB + 4 OTel + 2 TT）且聚焦支付 loss/delay 高影响路径。
- M1 所选 10 候选中有 6 个已有受控运行时证据（TT station delay、OB kill/delay/loss、OTel delay/loss），另 4 个（TT-STATION-CPU-80、OB-PRODUCTCATALOG-DELAY-500、OTEL-EMAIL-LOSS-100、OTEL-EMAIL-DELAY-2000）未执行过注入。
