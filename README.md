# persona-stack

人设注入工具：五文件人设集（AGENTS / IDENTITY / SOUL / TOOLS / CONTEXT）→ 不可变快照 → 多宿主收敛。

**权威版本在 GitHub**：`git@github.com:ocyang031/persona-stack.git`。仓库里的 `bundles/` 是人设的不可变版本库，`sources/` 是编辑现场，clone 一次全拿到。

**解决什么问题**：人设编辑一次、发布成不可变版本，任意多台宿主机上的副本自动对齐该版本，并报告谁被改了。

## CLI 使用指南

所有命令在仓库根目录运行（`python persona.py <命令>`）。

### 日常（最常用）

| 命令 | 作用 |
|---|---|
| `status` | 体检：所有宿主是否与注册表一致。exit 0 = 全收敛，2 = 有漂移 |
| `reconcile [slot]` | 刷新：把宿主落位刷成绑定表声明的版本；漂移时按注册表恢复 |
| `publish` | 发版：校验 sources → 算 hash → 存 bundles → git 提交 → 推送 GitHub |
| `reconcile --pull` | 先拉远端注册表再刷新（多机场景用这个） |

### 编辑人设

| 场景 | 操作 |
|---|---|
| **正式改版** | 编辑 `sources/<id>/` 五文件 → `publish` → `reconcile` → 重启宿主 |
| **临时改（不发版）** | 直接编辑本机落位目录的 `persona.prefix.txt`（位置见 `bindings.json` 对应绑定的 target）→ 重启宿主。`status` 显示 drifted = 临时版生效中的标记 |
| **临时版恢复正式版** | `reconcile` |
| **临时版转正** | `absorb <slot> --yes`（落位上的编辑写回 sources 作为提案）→ `publish` |

### 版本管理

| 命令 | 作用 |
|---|---|
| `revert <slot>` | 回滚：绑定指回上一版本并刷新 |
| `list` | 查看注册表里有哪些 persona、各版本、绑定概览 |
| `bind <slot> --host dsh --target <目录> <persona>` | 新宿主接入：声明「这个槽位用哪个人设的哪个版本」。可加 `--var KEY=VAL`（占位符填充）、`--device <标识>`（多机区分）、`--pin`（豁免对账） |
| `absorb <slot> --yes` | 晋升：把宿主落位上的编辑写回 sources 作为新版本提案 |

### 新机器接入（一次性）

```
git clone git@github.com:ocyang031/persona-stack.git
cd persona-stack
git config core.hooksPath .githooks        # 启用 bundles 防篡改闸门
python persona.py bind <slot> --host dsh --target <落位目录> --device <设备名> xiaoxiao
python persona.py reconcile --pull
```

## 想深入

- 设计为什么长这样 → [DESIGN.md](./DESIGN.md)
- 开发/操作手册（实现细节、接线知识、硬纪律、当前状态）→ [AGENTS.md](./AGENTS.md)
