# Remote Publish Checklist

- [ ] 产品包、CLI、profile、fixture 和边界检查通过。
- [ ] 证据清单的数量、大小和 SHA-256 全部通过。
- [ ] 产品仓库不跟踪 `artifacts/`、`raw_yaml/`、kubeconfig、凭据或虚拟环境。
- [ ] `ChaosAtlas-evidence` 已独立创建并可验证。
- [ ] 已执行 `git push --dry-run` 并记录结果。
- [ ] 用户单独确认是否切换 GitHub 默认分支。

默认不 force-push、不删除旧分支、不重写历史。
