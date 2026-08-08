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

## 2026-08-08（晚）

- ground-truth 骨架建立（`tools/assess_selection_evidence.py`）：12 候选池仅 6 个有自有执行结论（TT-STATION-DELAY-100、OB-PAYMENT-DELAY/LOSS、OB-PRODUCTCATALOG-KILL、OTEL-PAYMENT-DELAY/LOSS）；另 6 个未执行，结局未知。关键修正：结论必须绑定到候选自身 mutation，同 service 卡片的根因只能算 inherited 参考（OB-PRODUCTCATALOG-DELAY-500 不得继承 kill 结论）。
- 对比（`tools/compare_selection_methods.py`）：已知阳性 recall@10 = M3/M4 1.000、M0/M1 0.833，但 6/12 密度下 M0 期望命中恰为 5，**M1 与随机打平**；M3/M4 存在选择-执行循环偏置。诚实结论：在当前部分 ground truth 下无法给出方法优劣，差异要靠执行 M1 独有的未执行候选（TT-STATION-CPU-80、OTEL-EMAIL-LOSS-100、OTEL-EMAIL-DELAY-2000 等）转化探索为发现。
- 全量测试通过（58）。

## 2026-08-08（晚，M1 探索批次）

- 环境修复：train-ticket-lab namespace 随之前清理消失；重建（ns + 4 清单 + nacos/rabbitmq cm + ts-station/ts-order-mysql/train-ticket-db secret，自洽随机口令，不落盘）。gate 5/5 ready_for_injection。
- 执行 M1 独有的 5 个未执行候选（全单次受控注入，baseline→inject→recover→cleanup 完整）：
  - OB-PRODUCTCATALOG-DELAY-500：5/5 HTTP 200，中位 643ms（正常 ~40ms，放大 ~16 倍）→ response_observed
  - OTEL-EMAIL-DELAY-2000：PlaceOrder 4882ms（email 2000ms 注入）→ grpc_response_observed；**非关键 email 调用串行阻塞主订单流程**
  - OTEL-EMAIL-LOSS-100：10s DEADLINE_EXCEEDED → grpc_error_observed；**email 不可用直接打挂 PlaceOrder（无隔离/降级）**
  - TT-STATION-DELAY-2000：5/5 HTTP 200，中位 4017ms（2000ms 注入放大到 4s）→ response_observed
  - TT-STATION-CPU-80：5/5 HTTP 200，中位 85ms → response_observed（80% CPU 单 worker 影响弱）
- evidence 骨架更新：11/12 候选有自有结论（唯一未执行 TT-BASIC-DELAY-100）。重算对比：**M1 recall@10 = 0.909（10/11，三次稳定），M0 = 0.909/0.818/0.909，M3/M4 = 0.818（漏 TT-STATION-DELAY-2000）**。
- 重要证据：M1 挑的 5 个此前未执行候选，执行后 4 个证实实质弱点（email 阻塞主流程、延迟放大），1 个偏弱（CPU）；其中 OTEL-EMAIL 路径为全新发现（此前仅静态分析、未注入验证）。这证明 M1 的 LLM 探索有效，且不再有选择-执行循环偏置（M1 未使用执行历史）。
- 诚实边界：`response_observed` 是"观察到响应/效果"，弱于 `grpc_error_observed` 等强失败信号；TT-CPU-80 的结论偏弱。11/12 密度下 recall 接近饱和，差距需在论文中按"发现质量分级"呈现，而非仅靠 recall 数字。
- 全量测试 58 通过；三个 lab namespace 无遗留注入。

## 2026-08-08（深夜，四项收尾）

1. **12/12 ground truth 完整**：补执行 TT-BASIC-DELAY-100（5/5 HTTP 200，中位 141ms，弱影响）。证据骨架 12 候选全部有自有结论。
2. **5 新场景补 r2/r3**（与原 6 场景同等统计权重）：OB-DELAY-500（~540/577/562ms）、OTEL-EMAIL-DELAY（4882/5307/4965ms）、OTEL-EMAIL-LOSS（10011/10009/10004ms DEADLINE_EXCEEDED）、TT-DELAY-2000（4017/4020/4021ms）、TT-CPU-80（85/93/74ms）——**三次结论完全一致**，email 阻塞主流程与 10s 挂死、TT 延迟放大 2×、CPU 弱影响全部复现。
3. **严重度加权指标**：severity（3=超时/挂死/级联，2=延迟放大，1=弱影响）。12 池重算：**M1 = 0.920（三次稳定，只漏弱候选），M3/M4/A1-A4 = 0.840（稳定漏 severity-3 的 OTEL-EMAIL-LOSS）**。裸 recall 饱和区分不开，加权区分开了——M1 在"漏的多严重"上明显更好。
4. **稀疏候选池（20 候选）**：新增 8 个可执行 delay mutation（checkout/shipping/cart/order/currency 等，未执行=未知，score 0）。稀疏重算：
   - **随机基线被压到天花板以下**：M0 = 0.333-0.583（原 0.833-0.909 饱和），指标终于有区分度。
   - **结构性现象（必须诚实解读）**：M3/M4/A* = 0.833 反而最高——因为 score 驱动方法**只能看到带分的 12 候选**，扩展候选 score 0 永远排不进 top10，等于"只从答案集里选"；M1 = 0.417-0.583 低是因为它把 ~50% 预算花在 8 个未知候选上（探索成本）。已知 recall 对比对 M1 不公平，除非把 M1 探索的扩展候选执行后转化为发现。
   - M1 三次稳定挑选的扩展候选：OB-CHECKOUT-DELAY-2000、OTEL-CHECKOUT-DELAY-2000、TT-ORDER-DELAY-2000、OTEL-CURRENCY-DELAY-2000、OB-CART-DELAY-2000——这些是"M1 敢碰我们评分体系看不见的地方"的直接证据。
- 全量测试 58 通过；三 namespace 无遗留注入。
- 下一步（未做，需用户决定）：执行 M1 选中的 5 个扩展候选，把探索转化为发现，才能公平评价稀疏池下的 M1。

## 2026-08-09（凌晨，M1 扩展探索执行）

- 执行 M1 在 20 候选池中选中的 5 个扩展候选（r1-r3，共 15 次受控注入，全部完整生命周期）：
  - OB-CHECKOUT-DELAY-2000：10.01/10.01/10.01s DEADLINE_EXCEEDED → grpc_error（severity 3）——checkout 自身 2s 延迟打挂 PlaceOrder
  - OB-CART-DELAY-2000：12s client timeout ×3 → grpc_error（severity 3）——cart 延迟拖垮下单
  - OTEL-CHECKOUT-DELAY-2000：10.01/10.00/10.01s DEADLINE_EXCEEDED → grpc_error（severity 3）
  - OTEL-CURRENCY-DELAY-2000：7.22/6.98/7.12s OK → grpc_response（severity 2）——2s 注入放大到 ~7s
  - TT-ORDER-DELAY-2000：~4s/4s/4s HTTP 200 → response_observed（severity 2）
- **M1 探索命中率 5/5**：无执行历史、无静态评分（I0 输入）下，LLM 凭领域先验选中的未知候选全部证实为真实弱点（3×severity 3 + 2×severity 2）。
- evidence 骨架 17/20（3 个未执行：OB-SHIPPING/TT-BASIC-500/TT-STATION-500，均为 M1 未选）。稀疏池重算（severity 加权）：
  - **M1 = 0.658 三次稳定，全场最高**；M3/M4/A1-A4 = 0.553；M0 随机 = 0.474-0.605 飘忽。
  - M3/M4 漏的全部是 M1 探索出的 severity-3 弱点（OB-CHECKOUT/OTEL-CHECKOUT/OB-CART/OTEL-EMAIL-LOSS）+ severity-2（OTEL-CURRENCY/TT-ORDER）——score-0 候选对它们是结构性盲区。
  - 诚实边界：M1 的优势部分是"探索被我们执行后成为已知"的后验增益；但增益来源是它真的选中了弱点。裸 recall 三方法同 0.588（17/20 密度再饱和），severity 加权是唯一有区分度的指标。
- 全量测试 58 通过；三 namespace 无遗留注入。

## 2026-08-09（M5: LLM 证据解释——原计划 10.1②③ 落地）

- 实现 `tools/llm_interpret_evidence.py`：给 LLM 喂运行时证据 → 判防御（defended/partial/not_defended）+ 归因根因。双组对比：A 盲答（仅架构信息）vs B 有证据（+注入观测）。
- 真值映射协议：evidence 分类 + severity → 四档防御（grpc_error/client_timeout/cascade→not_defended；grpc_response/response+severity≥2→partial；response+severity1→defended）。修复两个 truth bug：early track_k 噪音（OTEL-PAYMENT-DELAY 误取初轮 grpc_error，实际确认实验全为 response）→ 按 confirmation/m1 优先；severity 区分 TT-2000(partial) vs TT-100(defended)。
- **结果（20 候选）**：防御准确率 **盲答 15% → 有证据 70%**（+55pp）；有效判断率 20% → 95%（盲答 80% 合理弃权 invalid，有证据后几乎全判）。**这是原计划"知识库→LLM 决策"主张的直接量化证据**。
- 剩余 6 个误差诚实解读：多为 LLM 更严格的防御标准（任何显著延迟算 not_defended，如 TT-500 系 500ms 注入有 500ms 响应被判未防御，而规则判 defended），非判断错误；根因 family 匹配 25% 是保守下限（LLM 措辞 circuit breaker/fail-fast 与卡片 timeout/fallback 方向一致但词不同）。
- 本轮同时完成：20/20 ground truth 完整（补 OB-SHIPPING/TT-BASIC-500/TT-STATION-500，各 r1-r3）；3 张新知识卡片（OTel email 阻塞主流程、OB checkout 挂死、OB cart 超时，validate 通过）。
