# 多项目接入清单（Project Intake Checklist）

> 用途：把新项目接入「测试节点中心 + 证据链」方法论的标准化流程。
> 已跑通：train-ticket（完整闭环）、Online Boutique（完整闭环）。
> 原则：先静态后运行时；运行时只在隔离环境；每次实验可复现、可清理、可追溯。

## 阶段 0：项目筛选（决策层）

- [ ] 维护活跃度（最近 push 时间、issue 响应率）——用 gh/api 核实，不凭印象
- [ ] 有 CI/测试（能跑复现）
- [ ] 接受 issue / 有韧性或 SLO 声明（报告价值高）
- [ ] 部署成本可控（本机 Docker Desktop / 小型集群可承载）
- [ ] 记录：`reporting/projects_matrix.md`

## 阶段 1：接入与静态映射

- [ ] pin commit（`gh api repos/<repo>/commits/main --jq .sha`），记录来源（git clone / tarball / api）
- [ ] 加入 `.gitignore`（`/<dir>/`，与 train-ticket/online-boutique 同模式）
- [ ] 构建服务清单 + 服务图（服务、语言、端口、依赖）
- [ ] **韧性声明检索**（高价值 bug 藏身处）：
  - [ ] 部署清单（istio/k8s/helm/kustomize）有无 retry/timeout/circuit 声明
  - [ ] 文档（product-requirements/SLO/README）有无韧性承诺
  - [ ] 源码：gRPC/HTTP 调用有无 timeout/deadline/retry/fallback
  - [ ] 探针配置（timeoutSeconds 是否与注入量级匹配）
- [ ] 测试节点中心候选表（路径 → 假设 → 预期分类 → 优先级）
- [ ] 产出：`artifacts/<project>/onboarding_static_report.md`

## 阶段 2：镜像/部署就绪

- [ ] 镜像源可达性测试（registry / goproxy / npm / pypi / mcr / nuget / maven）
- [ ] 不可达时：本地构建（替换 gcr.io/distroless 等基础镜像、配置镜像加速器/GOPROXY）
- [ ] 隔离 namespace 部署（`<project>-lab`），排除负载生成器（避免基线噪声）
- [ ] `imagePullPolicy: Always`（支持重建后拉新镜像）
- [ ] 修复构建缺陷并记录（Lab 适配 vs 上游 bug 分开标注）
- [ ] 基线：核心路径可观测（首页 / 下单 / 关键 RPC）+ 三阶段测量表

## 阶段 3：注入实验（运行时）

- [ ] 每个实验：单因素注入（延迟/丢包/杀 pod 等），一次一个变量
- [ ] 验证注入真实生效（`AllInjected` / `injectedCount>=1`，等待 status 再测量）
- [ ] 三阶段测量：基线 → 注入 → 恢复，记录精确数值
- [ ] 观察探针/重启/级联等意外行为（往往是高价值发现）
- [ ] 实验后：清理 chaos 资源 + 确认链路恢复
- [ ] 产出：`experiment_results.md` + `findings.md`（分层：实质问题/设计权衡/环境问题）

## 阶段 4：报告决策

- [ ] 用 `reporting/issue_template.md` 起草
- [ ] 用 `reporting/tracking.md` 登记
- [ ] 只报：有运行时证据 + 可复现 + 与项目声明矛盾
- [ ] 用户确认后才对外提交
- [ ] 用 `tools/package_report_evidence.py` 打包证据包

## 阶段 5：知识库闭环（可选）

- [ ] 实验结论转成知识卡片（复用 validate_knowledge_base 校验）
- [ ] 沉淀可迁移经验（跨项目对照：train-ticket vs Online Boutique）
