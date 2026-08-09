# r2 Prospective Head-to-Head — 冻结后三方法对比

> 日期：2026-08-09
> 协议：pre-registration 冻结（代码 commit + 候选池 + 盲排序）→ 等预算 Top-8 → 统一 runner 执行 → 盲评 → U@8
> 定位：同项目 prospective 验证，**不是跨项目泛化**（held-out 项目才够格写"跨项目优于"）

---

## 一、冻结（执行前锁定）

| 项 | 值 |
|---|---|
| 代码 commit | `f870e32`（`freeze_snapshot.json`） |
| 候选池 | `prospective_pool_r2.json`，18 候选，全部未执行 |
| mutation 集 | `execution/remediation/r2_mutations/`（18 个 NetworkChaos, mode=one） |
| 盲排序 | `execution/remediation/r2_rankings/rankings_frozen.json` |
| 预算 | 每方法 Top-8（统一候选成本，不临时补位） |

**执行范围（诚实声明）**：OB/OTEL/TT 三项目原定，但当前集群仅 OB 镜像存在（OTEL/TT 部署需数小时）。本轮**仅执行 OB 的 8 个候选**（三方法 Top-8 并集 ∩ OB = 8/13）；OTEL 4 + TT 1 候选标记 `not_deployed`，不计入 U@8。这是执行范围截断，不是测量偏倚——8 个候选全部用同一 runner、同一测量。

## 二、盲排序（冻结于执行前）

| 方法 | Top-8（冻结） |
|---|---|
| **Ours-full** (decision_engine, 无 LLM) | OB-EMAIL-LOSS, OB-CART-LOSS, OB-CHECKOUT-LOSS, OB-EMAIL-DELAY, OTEL-CART-LOSS, OTEL-CHECKOUT-LOSS, OB-CURRENCY-LOSS, OB-PRODUCTCATALOG-LOSS |
| **CE-adapter** (盲 LLM, 无知识) | OTEL-SHIPPING-LOSS, OB-EMAIL-LOSS, OB-EMAIL-DELAY, OB-CURRENCY-DELAY, OB-CURRENCY-LOSS, OB-CART-LOSS, OTEL-CART-LOSS, OB-PRODUCTCATALOG-LOSS |
| **Random** (seed 202) | OB-CURRENCY-DELAY, OB-SHIPPING-LOSS, OB-EMAIL-LOSS, OB-CURRENCY-LOSS, OTEL-PRODUCTCATALOG-LOSS, TT-STATION-LOSS, OTEL-CHECKOUT-LOSS, OB-PRODUCTCATALOG-LOSS |

## 三、统一执行（8 候选 × 首跑+确认，同一 runner）

`r2_execute_one.sh`：port-forward 复现既有 gRPC 测量路径 → baseline 3 calls → apply NetworkChaos → 确认注入 → workload 3 calls → 恢复 → cleanup（absence-confirmed）。

全部 8 候选：**injection=True, cleanup=absent**（0 残留）。

## 四、盲评（评审者只见测量行，不见方法名）

| 候选 | baseline | workload | 判定 | 确认 |
|---|---|---|---|---|
| OB-CART-LOSS-100 | 3/3 OK | 0/3, 3 err | **weakness** | ✅ 2× |
| OB-CHECKOUT-LOSS-100 | 3/3 OK | 0/3, 3 err | **weakness** | ✅ 2× |
| OB-CURRENCY-DELAY-2000 | 3/3 OK | 3/3, med 4019ms (20x) | **weakness** | ✅ 2× |
| OB-CURRENCY-LOSS-100 | 3/3 OK | 0/3, hung | **weakness** | ✅ 多数票 2/3 |
| OB-EMAIL-DELAY-2000 | 3/3 OK | 3/3, med 2017ms (100x) | **weakness** | ✅ 2× |
| OB-EMAIL-LOSS-100 | 3/3 OK | 0/3, hung | **weakness** | ✅ 2× |
| OB-PRODUCTCATALOG-LOSS-100 | 3/3 OK | 0/3, hung | **weakness** | ✅ 2× |
| OB-SHIPPING-LOSS-100 | 3/3 OK | 0/3, hung | **weakness** | ✅ 2× |

**8/8 confirmed weakness**（loss → 挂死/报错；delay → 放大 20-100x）。盲评输入：`r2_blind_evaluation.json`。

## 五、U@8（主指标）+ 成本

| 方法 | U@8 (confirmed weakness) | 注入成本 | weakness/注入 |
|---|---|---|---|
| **Ours-full** | **6** | 16 | 0.375 |
| **CE-adapter** | **6** | 16 | 0.375 |
| **Random** | **5** | 16 | 0.312 |

（OB 内候选：Ours Top-8 含 6 个 OB、CE 含 6 个 OB、Random 含 5 个 OB；8 个 OB 候选全 weakness，故 U@8 = OB 候选数。）

## 六、结论（诚实）

1. **U@8 三方法打平（6 vs 6 vs 5），无统计显著差异**——与既有 B1 结论一致：选择方法在同质池上无区分度。池的 8 个 OB 候选**全部是真实弱点**（OB 支付链无超时是既有已证模式），任何方法选到即命中。
2. **差异来自排序而非测量**：Ours 与 CE 把 OB 候选排在更前（Top-8 含 6 OB），Random 含 5。但样本仅 8 候选，差异 = 1 个候选，无统计意义（同 prospective r1 教训）。
3. **本轮价值 = 规范化的同条件对比**：冻结、盲评、等预算、同一 runner、无污染、8/8 可复现确认。它不是"我们更优"的证据，是"我们的对比流程经得起审稿"的证据。
4. **CE-adapter 盲 LLM 无知识仍达 6/6**：它凭"支付/下单链路优先"的通用常识排中 OB 候选。Ours 的契约知识（跳过 protected 边）在本池无 protected 边可跳过，故无差异化表现——与 OB 混合池结论一致（protected 边太明显时契约知识无增益）。

## 七、边界与未执行

- **OTEL 4 + TT 1 候选未执行**（`not_deployed`）——三方法在这些候选上的 U@8 无法计算；已从分母剔除。
- **8 候选全部 weakness = floor effect**：本池无 protected 边，方法区分度无法显现。含 protected 边的池（如 mixed_pool）才有区分度——已被 OB 混合池证明（Ours 跳过 protected, M0 浪费 49%）。
- **跨项目泛化**：本轮仅 OB 同项目，不能写"跨项目优于"。需 held-out 项目（冻结协议下未查看）才有资格。

## 八、产物清单

- `execution/remediation/freeze_snapshot.json` — 冻结
- `execution/remediation/r2_mutations/` — 18 mutation（mode=one）
- `execution/remediation/r2_rankings/rankings_frozen.json` — 盲排序
- `execution/remediation/r2_runs/*.json` — 8 候选 × 首跑+确认（含 confirm2/3）
- `execution/remediation/r2_blind_evaluation.json` — 盲评 + U@8
- 工具：`tools/r2_blind_ranking.py`、`tools/generate_r2_mutations.py`、`tools/r2_execute_one.sh`、`tools/r2_blind_evaluate.py`
