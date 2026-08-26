# ChaosAtlas 产品运行入口

产品仓库只保存可复用的编排、策略、契约、适配器、项目 profile、测试和文档。运行证据写入同级的 `ChaosAtlas-evidence` 目录，不写回产品代码树。

## Dry-run

```powershell
python -m chaosatlas run `
  --profile projects/sock-shop/profile.json `
  --mode dry-run `
  --evidence-root ..\ChaosAtlas-evidence
```

dry-run 只读取 profile 并生成计划摘要，不调用 LLM，也不修改 Kubernetes。

## 兼容入口

迁移期间原有入口继续可用：

```powershell
python tools/chaosatlas.py --help
python tools/run_closed_loop.py --help
```

新代码统一从 `src/chaosatlas` 导入；`tools/` 作为兼容和历史脚本边界。

## Live 安全门

live 执行必须显式提供允许的 namespace、executor、业务 Oracle、恢复和清理契约。缺少任一契约时应停在 preflight，不得注入。
