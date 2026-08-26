# Sock Shop Ablation YAML15 实施计划

> 设计依据：`docs/superpowers/specs/2026-08-16-sockshop-ablation-yaml15-design.md`

## 任务 1：冻结 YAML15 选择器

**文件：**
- 新增 `tools/build_sock_shop_ablation_yaml15.py`
- 新增 `tools/tests/test_build_sock_shop_ablation_yaml15.py`

1. 先写失败测试，覆盖五类各 3 份、确定性、无 runtime outcome 输入、原始/去敏 hash、路径顺序和非空 YAML。
2. 实现特征签名、频率代表和最大汉明距离选择。
3. 使用结构化 YAML 解析进行去敏，不采用字符串替换。
4. 输出 `yaml15-manifest.json`、`yaml15-prompt.json` 和 15 份去敏 YAML；拒绝覆盖非空目录。
5. 对固定 `raw_yaml/` 连续运行两次到不同目录，确认 manifest 内容 hash 一致。

## 任务 2：扩展独立 Ablation discovery 协议

**文件：**
- 修改 `tools/run_sock_shop_ablation_discovery.py`
- 修改 `tools/tests/test_run_sock_shop_ablation_discovery.py`

1. 先写失败测试，要求新协议必须读取且验证 YAML15 manifest/prompt hash。
2. 新增 `chaosatlas-ablation-yaml15` 独立方法名和 prompt protocol v2，禁止改变旧协议的序列化语义。
3. prompt 中提供类别标注和 YAML 文本，但不得提供类别统计、Full 数据、知识库或调用链投影。
4. 强制 `call_chain_position_source` 只能为 `model_inference` 或 `unknown`。
5. checkpoint input hash 纳入 YAML15 hash；错误样本数、类别数、hash 或恢复输入不一致时 fail closed。

## 任务 3：离线冻结与审计

**文件：**
- 新增不覆盖目录 `artifacts/experiments/chaosatlas_sockshop_ablation_yaml15_2026-08-16-r1/`

1. 生成 YAML15 冻结批次。
2. 检查 15 个原始文件 hash、15 个去敏文件 hash、五类计数和无敏感信息。
3. 运行 focused tests 和相关 Sock Shop 回归测试。
4. 冻结 Full discovery wall-clock 来源、值和 SHA-256；不得从 Ablation 结果反推预算。
5. 使用 fake model 完成 discovery dry-run，确认自停、time cap、checkpoint 和输出 provenance。

## 任务 4：执行 DeepSeek discovery 与去重 gate

1. 使用已授权 DeepSeek API，仅发送冻结 YAML15、Sock Shop profile、业务 oracle 和本臂 seen hypotheses。
2. 保存去敏请求、响应、用量、模型名、seed、时间、input/protocol hash；不保存 API key。
3. 模型自主停止或达到 Full 时间硬上限后结束，不人工追加假设。
4. 运行本臂独立去重，保留 family members 和代表选择原因。
5. 通过公共 compiler 和静态 gate；先执行 server-side dry-run，阻断项不注入。

## 任务 5：Runtime 与恢复验证

1. 运行前确认 Minikube context、Sock Shop baseline、Pod 健康和全局 Chaos 资源为空。
2. 每个 gate 通过的唯一 family 串行执行两次。
3. 每轮验证 baseline、injected、recovered、cleanup absent、washout stable 和诊断 hash。
4. 每轮后删除 Chaos 资源并检查全局无残留；失败时定位根因，不重复相同失败命令。
5. 输出 completed、blocked、unstable 和 no-impact 台账。

## 任务 6：审核、对比与归档

1. 将新版 Ablation 作为替换结果与 Full 的 114/96/88/15 冻结口径比较，不叠加旧 Ablation 分母。
2. 区分稳定业务弱点、一次性现象、无影响、无效假设和平台阻断。
3. 聚合 mutation family 为问题面，检查是否覆盖 Full 或出现 Ablation 独有结果。
4. 形成中文审核报告和机器 JSON，保持 human review pending，不更新知识库。
5. 运行测试、JSON/hash 一致性、敏感信息和 diff 检查，只选择性暂存本批必要文件。
