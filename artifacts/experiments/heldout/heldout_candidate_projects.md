# Held-out 候选项目选择与知识泄漏审计（Stage B）

> 日期：2026-08-10
> 状态：**阶段 B 完成——选择两个最终 held-out 项目(不获取)**
> 范围：仅文档级来源审计 + 知识泄漏分析；**未下载、未部署、未构造候选池、未运行实验**
> 依据：findings.md / comparative_evaluation_protocol.md / heldout_protocol_v1_1 / Stage A intake

---

## 一、B1 候选项目审计

### 候选 1：ESHOP（dotnet/eShop）

| 项 | 值 |
|---|---|
| project_id | `ESHOP` |
| canonical URL | `https://github.com/dotnet/eShop`（findings.md:82 引用） |
| 引用位置 | findings.md:82（外部资料表，MIT，10,745 stars） |
| 技术栈 | .NET 9 / .NET Aspire 电商参考应用（**跨技术栈**，Go→.NET） |
| 预计源码 | 存在（需受限获取时确认） |
| 预计 manifest | 需确认（findings.md 明确标注 "Kubernetes YAML 需要额外确认"） |
| 预计镜像 | 需确认 |
| 可观测入口 | Aspire dashboard / e2e tests（findings.md:82） |
| delay/loss/kill 支持 | `unknown`（需源码 intake 确认服务图） |
| protected/unprotected/unknown 构造条件 | `unknown`（需源码 intake） |
| ≥24 pilot / ≥48 formal 候选 | `unknown`（需确认服务数与边数） |
| 环境门槛/blocked 风险 | Aspire 依赖 Docker Desktop 生态;K8s manifest 待确认 → 若缺失则 availability 候选受限 |
| 需人工批准 | **是**（受限获取 eShop 源码） |

### 候选 2：SOCIALNET（DeathStarBench 子项目）

| 项 | 值 |
|---|---|
| project_id | `SOCIALNET` |
| canonical URL | `https://github.com/delimitrou/DeathStarBench`（findings.md:84 引用;**与 Hotel 同仓库**） |
| 引用位置 | findings.md:84（外部资料表,DeathStarBench 含 Social Network） |
| 技术栈 | Go（**与 Hotel 同栈**） |
| 预计源码 | 存在（`socialNetwork/` 子目录,未获取） |
| 预计 manifest | 存在（compose/kubernetes,未确认） |
| 预计镜像 | 存在（需确认） |
| 可观测入口 | 需确认（与 Hotel 同结构,预计 Jaeger/registry） |
| delay/loss/kill 支持 | `unknown`（需源码 intake） |
| protected/unprotected/unknown 构造条件 | `unknown`（需源码 intake） |
| ≥24/≥48 候选 | `unknown` |
| 环境门槛/blocked 风险 | 同仓库共享 dialer/registry/tracing 模式 → **知识泄漏风险**(见 B2) |
| 需人工批准 | **是**（同仓库 `socialNetwork/` 子目录获取） |

### 候选 3：MEDIA（DeathStarBench 子项目,备选）

| 项 | 值 |
|---|---|
| project_id | `MEDIA` |
| canonical URL | `https://github.com/delimitrou/DeathStarBench`（同仓库 `mediaMicroservices/`） |
| 引用位置 | findings.md:84（DeathStarBench 含 Media） |
| 技术栈 | Go（同栈） |
| 预计源码 | 存在（`mediaMicroservices/`,未获取） |
| 其余字段 | 同 SOCIALNET 模式:`unknown` 待 intake |
| 需人工批准 | **是**（同仓库子目录获取） |

---

## 二、B2 知识泄漏审计

### 2.1 当前知识库基线（关键事实）

对 `selection_experience` / `defense_pattern_library` / `judgment_experience` 三个 JSON 的完整文本进行大小写不敏感字面扫描；扫描文件、方法和 SHA-256 已记录在结构化清单的 `leakage_audit.knowledge_library_scan` 中:

| 关键词 | 出现次数 |
|---|---|
| `DeathStar` / `DeathStarBench` | **0** |
| `Hotel` / `hotel` | **0** |
| `SOCIALNET` / `social` | **0** |
| `MEDIA` / `media` | **0** |

**结论**:三个知识库当前未发现 DeathStarBench/Hotel/SOCIALNET/MEDIA 的直接文本证据。该结果证明的是“扫描到的文件版本没有直接命中”，不等同于证明所有抽象规则都与这些项目结构独立；同仓库候选仍须完成源码级剥离审计。

### 2.2 规则类型区分

| 类型 | 内容 | 能否跨项目迁移 |
|---|---|---|
| 通用选择/判定规则 | SE-NETWORK-FAMILY(delay/loss 优先)、SE-LOSS-STRONGEST、JE-COUPLING(email 旁路)、DP 超时/冗余机制 | **可迁移**（不依赖 DeathStarBench 特定实现） |
| DeathStarBench/Hotel 特定规则 | 当前知识库 **无**（0 命中） | 不存在,无需剥离 |
| 使用过某项目 runtime 结果的后验知识 | 当前仅 TT/OB/OTEL/Sock;**无 DeathStarBench 后验** | 不存在 |

### 2.3 SOCIALNET / MEDIA 泄漏风险

- **共享实现模式（结构性风险,非知识库污染）**:SOCIALNET/MEDIA 与 Hotel 同属 DeathStarBench,共享 `dialer/`(dial 120s 连接级超时)、`registry/`(consul)、`tracing/`(Jaeger/OpenTracing)等基础设施代码。
- **剥离规则（协议强制）**:
  1. SOCIALNET/MEDIA 的 project-specific contract 边**必须从各自源码静态重建**,不得复用 Hotel 的 contract 结论（如 `HOTEL-frontend->search` 边结论不可复制到 SOCIALNET 的对应边）;
  2. 共享基础设施事实（dialer 120s 连接级超时）在 SOCIALNET/MEDIA intake 时须**重新从各自源码确认**,并标注 `shared_infra_deathstarbench`（不伪装成项目特定）;
  3. 通用规则(SE/DP/JE)允许使用,但 SOCIALNET/MEDIA 的 selection snapshot 中的 `source_provenance` 必须注明通用规则来源与项目特定来源分离。
- **leakage risk**:
  - `SOCIALNET`: **medium**（结构性共享可管理,剥离规则明确后降至 low;当前知识库 0 污染）;
  - `MEDIA`: **medium**（同 SOCIALNET）。

### 2.4 ESHOP 泄漏风险

- 技术栈不同(.NET vs Go)、仓库不同(dotnet/eShop vs delimitrou)、语言/框架不同 → **无结构性共享**。
- 当前知识库 0 次 `eShop`/`ESHOP` 证据(见 2.1 扫描,ESHOP 未单独列但同法确认)。
- **leakage risk: low**——技术栈差异足以形成独立泛化证据。

---

## 三、B3 推荐两个项目（不获取）

### 首选两个

1. **ESHOP** —— 跨技术栈泛化证据（不同栈、不同仓库、leakage low）
2. **SOCIALNET** —— 同栈第二个 DeathStarBench 项目（leakage medium,剥离规则明确后可接受;与 Hotel 共享 infra 但项目特定契约各自重建）

### 备选

- **MEDIA** —— 仅当 SOCIALNET 获取后泄漏审计不通过时启用（同仓库同泄漏限制）

### 排除理由

- 无硬排除；本协议当前采用 **SOCIALNET 与 MEDIA 二选一** 的保守设计（同仓库共享基础设施，避免相关项目重复计数）。这不是统计学上的绝对排除；若要同时纳入，必须先补充并冻结项目簇聚类分析规则。
- environment-blocked 项目一律不计入 comparable 分母（协议 v1.1 §7）。

### 是否满足 ≥3 comparable

**目前不能判定**。Hotel + ESHOP + SOCIALNET 只是目标组合；ESHOP/SOCIALNET 尚未获取，服务图、manifest、候选规模、可观测性和环境闸门均为 unknown。只有三者完成 intake、pre snapshot、候选池冻结且 CE 线可比较后，才可能计为 3 个 comparable 项目。

### 获取顺序

1. **ESHOP**（跨栈,最高泛化价值）
2. **SOCIALNET**（同栈第二,需完成泄漏剥离后 intake）
3. MEDIA（备选,仅在 SOCIALNET 不通过时）

### 需主代理单独批准的 canonical URL

| 项目 | URL | 批准项 |
|---|---|---|
| ESHOP | `https://github.com/dotnet/eShop` | 受限获取源码（MIT;需确认 commit + k8s manifest 存在性） |
| SOCIALNET | `https://github.com/delimitrou/DeathStarBench`（`socialNetwork/` 子目录） | 同仓库子目录受限获取 + 泄漏剥离审计授权 |
| MEDIA（备选） | `https://github.com/delimitrou/DeathStarBench`（`mediaMicroservices/` 子目录） | 同上 |

---

## 四、明确声明

本阶段**未下载**任何项目源码、**未部署**、**未构造 candidate pool**、**未运行** CE/pilot/formal/任何 fault injection;未修改协议 v1/v1.1、Hotel snapshot、历史实验真值或 reporting 文件。等待主代理审核。
