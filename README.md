# persona-stack

人设注入工具：五文件人设集（AGENTS / IDENTITY / SOUL / TOOLS / CONTEXT）→ 不可变快照 → 多宿主收敛。

**权威版本在 GitHub**：`git@github.com:ocyang031/persona-stack.git`。仓库里的 `bundles/` 就是人设的不可变版本库，clone 即全量副本。本地的五文件目录只是编辑草稿现场——在哪台机器、放在哪里，是各机器自己的事，不属于本仓库的事。

**解决什么问题**：人设编辑一次、发布成不可变版本（bundle），任意多台宿主机上的副本自动对齐该版本，并报告谁被改了。

## 日常三条命令

```bash
python persona.py status           # 看所有宿主是否收敛
python persona.py reconcile        # 有漂移就恢复
python persona.py pack <草稿目录>  # 改了五文件之后发新版本
```

改人设的完整流程：在草稿目录编辑五文件 → `pack` → `publish`（提交并推送到 GitHub）→ 各宿主 `reconcile` → 重启宿主会话。

## 想深入

- 设计为什么长这样 → [DESIGN.md](./DESIGN.md)
- 开发/操作手册（命令全表、接线知识、硬纪律、当前状态）→ [AGENTS.md](./AGENTS.md)
