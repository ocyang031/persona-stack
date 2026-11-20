# persona-stack

人设注入工具：五文件人设集（AGENTS / IDENTITY / SOUL / TOOLS / CONTEXT）→ 不可变快照 → 多宿主收敛。

**权威版本在 GitHub**：`git@github.com:ocyang031/persona-stack.git`。仓库里的 `bundles/` 是人设的不可变版本库，`sources/` 是编辑现场，clone 一次全拿到。

**解决什么问题**：人设编辑一次、发布成不可变版本，任意多台宿主机上的副本自动对齐该版本，并报告谁被改了。

## 两个日常场景

**临时改人设（不发版）**：

```
编辑 sources\xiaoxiao\SOUL.md
python persona.py reconcile dsh.local
/restart
```

只有本机生效，远端设备不受影响。

**转正**：

```
python persona.py publish
python persona.py reconcile dsh.local
/restart
```

publish 一条命令完成：校验 → 算 hash → 存入 bundles → git 提交 → 推送 GitHub。

新机器 clone 后跑一次：`git config core.hooksPath .githooks`（启用 bundles 防篡改闸门）。

## 想深入

- 设计为什么长这样 → [DESIGN.md](./DESIGN.md)
- 开发/操作手册（命令全表、接线知识、硬纪律、当前状态）→ [AGENTS.md](./AGENTS.md)
