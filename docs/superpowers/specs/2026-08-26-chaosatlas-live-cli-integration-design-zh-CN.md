# ChaosAtlas Live CLI 接入设计

## 目标

将现有 Kubernetes/native `run_closed_loop` 能力接入产品级 `chaosatlas run` 入口，使部署好的项目可以通过一条命令执行受控 live 检测，同时保持 dry-run 行为、显式审批、命名空间隔离和证据边界不变。

## 设计

- `--mode dry-run` 继续调用新的离线闭环编排器。
- `--mode live` 调用现有维护中的 native runner，不重新实现生命周期执行器。
- live 默认 fail-closed：没有 `--approve-live` 时直接返回阻断结果。
- CLI 转发 `--candidate-id`、`--kube-context`、`--advisory-provider`、`--api-key-file`、`--base-url`、`--model`、`--defense-history-root`、`--knowledge-write-root` 和 `--registry-shadow`。
- live 输出目录必须为空；不允许用 `--resume` 复用 live 目录。
- DeepSeek 仅生成假设和证据建议，不能改变确定性分类、RCA 或知识晋级。
- Nginx 首次验证只做 preflight 和单候选 canary，失败归类为 `environment_blocked`、`not_reachable` 或其他证据支持的状态，不升级为漏洞。

## 验证

CLI 测试锁定 dry-run 不回归、live 未审批阻断、live 参数转发和非空目录保护。真实 Nginx 执行前通过 kubectl 检查 context、namespace、deployment、service、pod 以及 Chaos Mesh 组件；只有 preflight 成功才允许注入。
