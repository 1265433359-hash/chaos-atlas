# ChaosAtlas 仓库架构重构设计

## 1. 目标

重构本地 ChaosAtlas 工作区和 GitHub 产品仓库，使产品代码、项目接入、实验定义、运行证据、外部源码和本机状态拥有清晰且相互独立的生命周期边界。

重构后必须继续支持一条命令完成现有闭环，同时让产品仓库能够独立阅读、测试和发布。

## 2. 范围

### 包含内容

- 重组目前集中在 `tools/` 下的产品代码。
- 将实验输入、运行证据、报告和外部源码分离到独立的证据归档仓库。
- 迁移期间保留现有 `tools/chaosatlas.py` 和受支持实验命令的兼容入口。
- 定义稳定的运行 manifest、证据目录、来源关系和恢复行为。
- 验证通过后，将干净的产品分支作为 GitHub 的 `main` 产品主线。
- 在归档完整性确认前，将当前旧分支保留为只读回滚参考。

### 不包含内容

- 不重写闭环算法、候选策略、停止策略、RCA 方法或 executor 行为。
- 不因为目录迁移而重新执行 Kubernetes 实验。
- 在复制并完成哈希校验前，不删除历史证据。
- 不自动执行远端 force-push 或删除远端分支。
- 不把密钥、kubeconfig、虚拟环境或本机状态迁移到任一仓库。

## 3. 目标仓库

### 产品仓库：`ChaosAtlas`

```text
ChaosAtlas/
├─ src/chaosatlas/
│  ├─ orchestration/       # 一条命令的闭环主编排
│  ├─ adapters/             # Kubernetes、native 和服务器部署检测
│  ├─ policies/             # 候选、排序、停止和反馈策略
│  ├─ contracts/            # profile、证据、RCA 和知识契约
│  ├─ knowledge/            # 检索、验证、晋级和回归意图
│  ├─ runtime/              # 基线、注入、观测、恢复和清理
│  └─ reporting/            # 汇总、覆盖率、Issue 草案和验收报告
├─ cli/                     # 安装后的 `chaosatlas` 命令
├─ projects/                # 版本化项目 profile 和脱敏接入输入
├─ tests/
│  ├─ unit/
│  ├─ contract/
│  ├─ integration/
│  └─ fixtures/
├─ docs/
├─ scripts/                 # 薄封装、检查和迁移工具
├─ examples/
├─ pyproject.toml
└─ README.md
```

产品仓库不包含大批运行证据、上游源码副本、kubeconfig、凭据、虚拟环境或本机状态。

### 证据归档仓库：`ChaosAtlas-evidence`

```text
ChaosAtlas-evidence/
├─ projects/
├─ experiment-manifests/
├─ inputs/
├─ runs/
├─ reports/
├─ knowledge-snapshots/
├─ external-sources/
└─ README.md
```

归档仓库是历史实验输入、运行证据、RCA 产物、生成报告和外部项目快照的事实来源。预期远端仓库名为 `chaos-atlas-evidence`，具体远端 URL 在发布阶段配置。

## 4. 产品代码边界

当前 `tools/` 中的模块按职责迁移，而不是按历史文件名机械搬迁：

- `chaosatlas.py`、`chaosatlas_batch.py`、`run_closed_loop.py` 和生命周期编排迁移到 `src/chaosatlas/orchestration/`。
- Kubernetes 项目适配器、生命周期 executor、native executor、NGINX 契约和 executor 注册表迁移到 `src/chaosatlas/adapters/`。
- 候选生成、假设注册、排序、停止、反馈和 registry signal 模块迁移到 `src/chaosatlas/policies/`。
- profile、证据、RCA、恢复、反馈和实验 schema 迁移到 `src/chaosatlas/contracts/`。
- 知识检索、迁移审计、弱点晋级和知识更新模块迁移到 `src/chaosatlas/knowledge/`。
- 证据采集器、适用性门禁、运行状态、恢复和清理协调迁移到 `src/chaosatlas/runtime/`。
- 问题身份、覆盖率、验收、Issue 和汇总生成器迁移到 `src/chaosatlas/reporting/`。

迁移期间保留 `tools/` 作为兼容层。保留的每个入口都是导入新包的薄封装，不再包含独立业务逻辑。一次性实验 runner 只有在属于受支持产品工作流时才保留；历史 runner 及其输入迁移到证据仓库。

## 5. 数据流和运行契约

逻辑流程保持不变：

```text
项目 profile
  -> 只读接入和全量画像
  -> 架构/配置/依赖/运行时假设
  -> 价值排序和停止预算
  -> 受控执行
  -> 证据、RCA、恢复和清理
  -> 结果分类
  -> 知识验证和晋级
  -> 回归意图
```

每次执行写入一个不可变的运行目录：

```text
runs/<project>/<run-id>/
├─ manifest.json
├─ checkpoints/
├─ inventory/
├─ hypotheses/
├─ selection/
├─ lifecycle/
├─ evidence/
├─ rca/
├─ cleanup/
├─ knowledge/
├─ regression/
└─ summary.md
```

`manifest.json` 固定记录：

- 产品提交版本和 profile 版本；
- 项目、namespace 和集群上下文摘要；
- 候选策略、停止策略的标识和预算；
- 候选决策以及每轮状态；
- executor、Oracle、恢复和清理契约；
- 产物的相对路径和 SHA-256；
- 是否发生 Kubernetes mutation、LLM 调用或正式知识写入。

知识卡引用归档中的 `run-id` 和产物哈希，不把原始证据复制到产品仓库。运行恢复只能读取自身的 checkpoint；已经完成的候选在恢复时不得再次注入。

## 6. 兼容性和配置

- 迁移期间继续支持 `python tools/chaosatlas.py run ...`。
- 新安装提供使用同一套编排契约的 `chaosatlas` CLI。
- 证据根目录可配置，默认指向同级的 `ChaosAtlas-evidence`。
- 只有新 CLI 通过三个项目的离线回放门禁后，兼容包装器才开始输出弃用提示。
- 路径引用使用项目 ID、运行 ID 和 manifest 相对路径，不依赖历史绝对路径。

## 7. 安全和回滚

迁移在独立工作树中按以下顺序执行：

1. 保存当前 Git 引用，生成包含来源类别、大小和 SHA-256 的完整清单。
2. 将证据和外部源码复制到归档仓库，并校验数量和哈希。
3. 构建筛选后的产品目录，并保留兼容包装器。
4. 执行结构、行为、安全和归档完整性验证。
5. 先推送证据仓库，再推送干净产品分支。
6. 只有审阅通过后，才将已验证的产品分支设为 GitHub 默认分支。

当前旧分支冻结为 `archive/legacy-2026-08-26`，作为回滚参考。默认不执行破坏性删除、force-push 或分支移除。后续任何历史重写或仓库替换，都需要单独明确授权。

如果发现文件未分类、哈希不一致、路径引用断裂、疑似凭据文件，或者无法证明归档完整，迁移必须 fail closed。历史上的 `blocked`、`unsupported` 和 `cleanup_failed` 结果只能作为证据保留，不能因为迁移而晋级为知识。

## 8. 验证和验收

### 产品验证

- 编译所有新的 package 和 CLI 模块。
- 运行迁移后的完整测试套件。
- 验证 CLI 帮助、dry-run、resume 和错误退出码。
- 通过同一个离线编排器回放 Sock Shop、Online Boutique 和 P02。
- 验证旧 CLI 和新 CLI 产生等价的 dry-run 契约。

### 归档验证

- 对比迁移前后的文件清单数量。
- 校验所有已跟踪证据和选定未跟踪证据的 SHA-256。
- 验证每个运行 manifest 及其引用路径。
- 从 manifest 随机恢复运行，确认输入、证据、RCA 和知识链接完整。
- 恢复一个 fixture 运行，证明已完成候选不会重复执行。

### 安全和仓库边界验证

- 确认产品 Git 不跟踪 artifacts、大批 raw YAML 输入、凭据、kubeconfig、虚拟环境和本机状态。
- 执行敏感信息扫描和路径引用扫描。
- 确认默认命令不调用 LLM，也不修改 Kubernetes。
- 执行 `git diff --check` 和仓库卫生检查。

### 远端验证

- 产品分支只包含允许的产品目录和文档。
- 证据仓库可以独立克隆和验证。
- 产品 README 指向归档仓库和实验复现入口。
- 旧分支仍然存在，并与记录的回滚引用一致。
- 远端分支指针与发布 manifest 一致。

只有满足以下条件，重构才算验收通过：产品仓库能够独立运行，证据仓库能够审计，一条命令继续可用，历史证据没有丢失，并且没有敏感本机数据被发布。

## 9. 分阶段实施

- 阶段 1：独立工作树、全量盘点、备份引用和归档迁移工具。
- 阶段 2：产品核心打包和兼容包装器。
- 阶段 3：项目 profile、fixtures、受支持 runner 和文档迁移。
- 阶段 4：证据和外部源码迁移，验证 manifest 和哈希。
- 阶段 5：发布证据仓库和干净产品分支，完成远端审阅。
- 阶段 6：执行全量验证，记录最终运行方式。
