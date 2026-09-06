# H1 重放器失败证据

核对基线：`3defd5c`（执行代码来自 `6e81cd6`）。所有反例均为 synthetic-test-only 内存 transport，
没有调用应用、持久化真实审批或创建业务对象。

本轮实跑 `tests/test_transaction_replay_hardening.py`：3 failed，符合修复前预期。
原始 JUnit：`%LOCALAPPDATA%/ChaosAtlas/runs/h1-replay-hardening-20260906/before.xml`。

| 反例 | 实测 | 代码位置 | 修复要求 |
|---|---|---|---|
| 上传和重试均响应丢失 | prepare_failed，但 cleanup_confirmed=true | replay.py 的 _recover_response_loss、cleanup | 每个可能写入的操作保留未决状态，清理不得成功 |
| fixture 注入 run_id | 未拒绝并发送请求 | replay.py 的 prepare | 身份与响应捕获变量拒绝从普通 fixture 注入 |
| 非法 JSON path | 校验器返回无错误 | transaction_contracts.py 的验证器、_json_path | 完整语法验证和执行时拒绝 |

后续静态风险：查回无唯一性/ownership 证明；输入与契约可变别名；无持久恢复账本；旧观察重复用于 probe；
状态/成功字段门不足；超时/大小/URL/header 不严格；删除响应代替缺失证明；无 disposable 释放器仍可先写；
普通进程退出与强杀恢复不完整。它们是待用反例核实的实现风险，尚不是应用事故。

当前边界：v1 历史批准件保留，v2 未批准；已有合成测试仅覆盖选定分支，不能证明 H2/H3 的完整边界。
本轮尚未获得新真实业务、故障、Issue 或论文统计证据。H1 红测试独立提交，H2 修复后须回跑并保存 after.xml。
