# persona-stack

人设注入工具：五文件人设集（AGENTS / IDENTITY / SOUL / TOOLS / CONTEXT）→ 不可变快照 → 多宿主收敛。

**解决什么问题**：人设只在源目录维护一处（`../EN/`）；本工具把它打包成不可变版本（bundle），让任意多台宿主机上的副本自动对齐该版本，并报告谁被改了。

## 日常三条命令

```bash
python persona.py status        # 看所有宿主是否收敛
python persona.py reconcile      # 有漂移就恢复
python persona.py pack ../EN     # 改了人设源之后发新版本
```

改人设的完整流程：编辑 `../EN/` 五文件 → `pack` → `publish` → `reconcile` → 重启 TUI。

## 想深入

- 设计为什么长这样 → [DESIGN.md](./DESIGN.md)
- 开发/操作手册（命令全表、接线知识、硬纪律、当前状态）→ [AGENTS.md](./AGENTS.md)
