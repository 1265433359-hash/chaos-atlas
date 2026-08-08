# 双轨方法论：薄弱点发现 + 防御模式提取（核心设计确认）

> 日期：2026-08-09
> 状态：已由项目负责人确认（"我们的方法就是找薄弱点"，防御住的分析是第二类资产）
> 定位：这是方法论的核心演进，替代早期"判断系统防御能力"的单一措辞

## 一、核心主张

**我们的方法主目标是"发现项目的薄弱点"；注入后系统防御住的实验不是废数据，而是第二类资产——提取"防御模式"，用于跨项目候选降级。**

```
注入 → 被打穿 → 薄弱点（root_cause）→ 跨项目迁移：去类似地方找弱点
注入 → 防住了 → 分析为什么防住（timeout/retry/circuit/redundancy/...）
                  → 防御模式库 → 新项目看到相同机制的服务边 → 候选降级（跳过，省预算）
```

一句话：**薄弱点知识告诉我们"去哪找"，防御模式知识告诉我们"哪不用找"**。后者省下注入预算，把实验花在真正未知的地方。

## 二、两类资产的对比

| 维度 | 薄弱点（主） | 防御模式（次，但同样重要） |
|---|---|---|
| 触发 | 注入后被打穿（timeout/hang/cascade/放大） | 注入后防住（响应 1:1 无放大，或近基线） |
| 记录 | 知识卡片 `root_cause` + severity | 防御模式库 `defense_mechanism` + evidence |
| 作用 | 跨项目迁移：去类似边找弱点 | 跨项目降级：同机制边跳过/后置 |
| 已有资产 | 14+ 张卡片，全部 root_cause 导向 | 本次新建 |
| 与 severity 关系 | severity 3=被打穿，2=放大，1=无放大 | severity 1 = 防御模式候选 |

## 三、防御模式库设计

### Schema（v1）

```json
{
  "schema_version": 1,
  "pattern_id": "DP-DEFENSE-TIMEOUT-001",
  "defense_mechanism": "bounded_timeout",      // 机制分类（见下）
  "evidence": {
    "project": "train-ticket",
    "candidate_id": "TT-BASIC-DELAY-500",
    "mutation": ".../tt-basic-delay-500-one.yaml",
    "observation": "500ms injection -> 520ms response (1:1, no amplification), 5/5 HTTP 200",
    "evidence_files": ["m1_ext_tt_basic_delay_500_r1/r2/r3.json"]
  },
  "inference": "basic service propagates latency 1:1 with no compounding (single-call path, no fan-out)"
}
```

### 机制分类（v1，来自防御/反模式文献 + 我们的观察）

- `bounded_timeout`：下游调用有显式超时，超时后有降级
- `retry_fast_fail`：快速失败 + 有限重试，不挂起
- `circuit_breaker`：熔断隔离
- `redundancy`：多副本/冗余，单点故障被吸收
- `isolation_non_critical`：非关键副作用与主流程解耦（异步/独立预算）
- `absorbed_by_design`：单调用路径 1:1 传递，无放大（TT-BASIC-500 案例——"没被打穿是因为结构简单"，这也是一种模式）
- `weak_stressor`：注入强度低于触发阈值（CPU 80% 单 worker 不饱和）

### 候选降级规则

新项目接入时，对候选池中每条边：
1. 查询防御模式库，匹配"边类型 × 机制"（如 `checkout->email` × `isolation_non_critical`）
2. 命中 → 候选**降级**（`candidate_priority: low` / `skip_recommended`），附模式 id 作为证据
3. 未命中 → 保持原优先级，继续注入

降级不是"永不测"：如果新项目的行为证据（静态分析）表明机制可能缺失（如 email 调用是同步的），降级被推翻、恢复原优先级。**模式库提供先验，行为证据可推翻先验。**

## 四、M5 重构：双向归因

M5 的 LLM 输出从单轨"防御等级"改为双轨归因：

```json
{
  "verdict": "weakness" | "defended",
  "severity": 1|2|3,            // weakness 时：薄弱严重度（与我们现有 severity 一致）
  "root_cause": "...",           // weakness 时：薄弱根因
  "defense_mechanism": "...",    // defended 时：什么机制扛住的（模式分类）
  "confidence": "high|medium|low"
}
```

真值映射（可审计协议）：
- `grpc_error / client_timeout / cascade / hang` → verdict=weakness, severity=3
- `grpc_response / response + severity 2`（放大）→ verdict=weakness, severity=2
- `response + severity 1`（无放大/近基线）→ verdict=defended，机制由 LLM 归因 + 我们核实

## 五、落地顺序

1. ✅ 本设计文档（本次）
2. 实现 `tools/defense_pattern_library.py`：模式库 CRUD + 候选降级查询
3. 从现有防御住案例提取第一版模式（TT-BASIC-500 无放大、TT-STATION-100 弱注入、TT-CPU-80 弱压）
4. 重构 `tools/llm_interpret_evidence.py` 为双向归因（verdict/severity/root_cause/defense_mechanism）
5. 候选降级接入对比流程（新增 `candidate_priority` 字段）
6. 与 M1/M5-select 对比衔接

## 六、对论文的含义

- 贡献从"混沌测试方法"升级为"**薄弱点发现 + 防御模式库 + 跨项目候选降级**"的完整方法论
- 防御模式库是可检索的第三类知识资产（知识卡片 = 薄弱点，模式库 = 防御手段，二者互补）
- 跨项目降级是可量化的价值主张：省多少注入预算 = 降级候选数 / 总候选数
