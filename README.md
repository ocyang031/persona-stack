# persona-stack

将独立的人设提示词模块打成不可变快照，在各宿主按绑定使用一个模块或拼装一组模块。

**权威版本在 GitHub**：`git@github.com:ocyang031/persona-stack.git`。仓库里的 `bundles/` 是人设的不可变版本库，`sources/` 是编辑现场，clone 一次全拿到。

**解决什么问题**：人设编辑一次、发布成不可变版本，任意多台宿主机上的副本自动对齐该版本，并报告谁被改了。

## 选用与维护模块

枭枭提供四份可直接使用的提示词。选执行规则用 `AGENTS.md`，选身份用 `IDENTITY.md`，选语气与价值观用 `SOUL.md`，选工具操作流程用 `TOOLS.md`。也可以按需要组合，例如身份加语气。直接使用时，把所需模块正文交给宿主的指令入口。

使用本工具时，`--include` 指定一份或多份，以逗号分隔。DSH 默认拼装全部模块，Codex 默认拼装身份与语气，File/OpenClaw 默认逐文件落位。多份文件按 `persona.yaml` 顺序组装。

```powershell
python persona.py bind dsh.voice --host dsh --target ./voice-slot --include 'SOUL.md' xiaoxiao
python persona.py bind dsh.persona --host dsh --target ./persona-slot --include 'IDENTITY.md,SOUL.md' xiaoxiao
```

修改人设时编辑 `sources/<id>/`。模块正文只写模型需要执行的内容，维护分工和组装契约见 [DESIGN.md](./DESIGN.md)。先运行 `python persona.py validate sources/xiaoxiao`，用 `pack` 生成本地快照。

### 旧版 DSH 迁移

先记下旧绑定的参数，运行 `python persona.py unbind <slot> --yes`，让工具按旧快照移除原来的托管产物，包括字节未改动的工作区副本。宿主上改过的副本会报告并保留，所需内容应人工合入新模块。再用新快照重新 `bind`，运行 `reconcile <slot>` 并重启对应会话。

## CLI 使用指南

所有命令在仓库根目录运行（`python persona.py <命令>`）。

### 日常（最常用）

| 命令 | 作用 |
|---|---|
| `status` | 体检：所有宿主是否与注册表一致。exit 0 = 全收敛，2 = 有漂移 |
| `reconcile [slot]` | 刷新：把宿主落位刷成绑定表声明的版本；漂移时按注册表恢复 |
| `publish` | 发版：校验 sources → 版本号闸门 → 算 hash → 存 bundles → git 提交 → 推送 GitHub |
| `reconcile --pull` | 先拉远端注册表再刷新（多机场景用这个） |

### 编辑人设

| 场景 | 操作 |
|---|---|
| **正式改版** | 编辑 `sources/<id>/` 人设文件集 → `publish` → `bind` 到新版本 → `reconcile` → 重启宿主 |
| **临时改（不发版）** | 直接编辑本机落位目录的 `persona.prefix.txt`（位置查 `targets.local.json` 对应 slot 的 target）→ 重启宿主。`status` 显示 drifted = 临时版生效中的标记 |
| **临时版恢复正式版** | `reconcile` |
| **临时版转正** | `absorb <slot> --yes`（落位上的编辑写回 sources 作为提案）→ `publish` |

### 版本管理

| 命令 | 作用 |
|---|---|
| `revert <slot>` | 回滚：绑定指回上一版本并刷新宿主（pinned 槽位也收敛，pin 继续防后续漂移） |
| `list` | 查看注册表里有哪些 persona、各版本、绑定概览 |
| `bind <slot> --host dsh --target <目录> <persona>` | 新宿主接入：声明「这个槽位用哪个人设的哪个版本」。可加 `--var KEY=VAL`（占位符填充）、`--device <标识>`（多机区分）、`--pin`（豁免对账）。target 只写本机 `targets.local.json`，不进权威表 |
| `unbind <slot> --yes` | 卸载：从宿主摘掉人设块（块外内容不动）并删除该绑定；输出里给出恢复命令 |
| `absorb <slot> --yes` | 晋升：把宿主落位上的编辑写回 sources 作为新版本提案 |

版本号是内容 hash 的人读名字。**内容变了必须在 `sources/<id>/persona.yaml` 升 version**：
同一 version 已发布过不同 hash 时，`pack` / `publish` 会拒绝（一个 version 只对应一个 hash）。

宿主落点（`target`）是机器本地事实，存在仓库根的 `targets.local.json`（gitignore）；
`bindings.json` 只记槽位 → 版本，随仓库走。换机器或新 clone 后，对本机每个槽位
重跑一次 `bind` 声明 target 即可，不必手改权威表。

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
