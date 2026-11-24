# AGENTS.md — persona-stack 机读操作手册

> 给在本仓库工作的 agent：读完本文件即可上手开发。分工固定——AGENTS.md=机读操作、
> README.md=人读用法、DESIGN.md=人读设计理由。注意命名碰撞：本文件是**仓库操作手册**，
> 不是人设内容；人设文件集在 `sources/<id>/`（那边也有 AGENTS.md，是注入宿主的
> persona 文件）。

## 项目一句话

人设文件集（AGENTS/IDENTITY/SOUL/TOOLS/CONTEXT）的注入工具 = registry（不可变快照）
+ reconciler（多宿主收敛）。不是编译器：人设文件集即最终形态，不拼装、不碎片化。

**权威版本 = 本仓库 `bundles/`（远端 `git@github.com:ocyang031/persona-stack.git`，
clone 即全量副本）**；`sources/<id>/` 是编辑现场（在仓库内、随 clone 分发），
编辑 → `publish` 晋升，一步成版。

## 布局与权限

| 路径 | 角色 | agent 读写权 |
|---|---|---|
| `persona.py` | 入口壳（~20 行）：re-export + `main()`；实现已迁到 `persona_stack/` | 可改；改后 `python -m py_compile persona.py` 必过 |
| `persona_stack/` | 实现：`paths`/`util` · `manifest` · `registry`（hash+bundle+render） · `state`（bindings+receipts） · `adapters/`（每宿主一文件） · `commands`（十动词） · `cli`（argparse） | 可改；**加宿主 = 新建 `adapters/<host>.py` + 一行 `register()`** |
| `sources/<id>/` | 人设编辑现场（人设文件集 + persona.yaml，随 clone 分发，自由编辑） | 可编辑；晋升走 publish |
| `verify.py` | bundles 完整性闸门（重算全部 bundle hash + index/绑定对账） | 可改；commit 前必须绿 |
| `.githooks/pre-commit` | 提交闸门：跑 verify.py，bundles 被偷改则拒绝提交 | 启用方式：`git config core.hooksPath .githooks`（clone 后需一次性设置） |
| `bindings.json` | 绑定表（宿主应然状态） | 可改；schema：slot/persona/hash/host/target/vars/pin/device/bound_at（+ 可选 `include`：该槽位的文件白名单，缺省用 adapter 的 `wants`） |
| `bundles/<id>/<hash>/` | 不可变快照 | **只增不改不删**（纪律 1） |
| `receipts/` | 回执流 | 只追加；gitignore |
| `dsh-bridge.py` | linux-sandbox 设备接线胶水（**非适配器**，硬编码该机路径） | 原则上不改 |
| `_archive/` `_scratch/` | 旧架构归档 / 本机临时 | gitignore，勿提交 |

（外部草稿目录已废除：编辑面就是仓库内 `sources/`，2026-11-20 起生效。）

## 硬纪律（违反即错误）

1. `bundles/` 只进不改：修正 = 新版本新 hash；回滚 = 绑定指回旧 hash。唯一例外
   = 从未被任何绑定消费的测试件（前例 renderlab：22dd80d 入库 → 03865f8 删除，
   commit 信息必须写明理由）。机器闸门：`verify.py`（pre-commit 自动跑）重算
   全部 bundle hash，偷改已发布快照 = commit 被拒。
2. `publish` = 自动晋升 + `git add -A && git commit && git push`：先对
   `sources/<id>/` 逐个 pack（validate 不过即中止），再提交推送。人的发版动词
   只有这一个。
3. Windows 本机：只有 `python`（无 `py`）；文件操作全字节级（read_bytes/write_bytes）；
   源必须 LF-only、无 BOM（dsh 前缀走 YAML 标量，CRLF/CR 会破坏逐字节往返）；
   bindings.json 读取用 utf-8-sig 容 BOM，写回无 BOM。
4. 测试 fixture 用完即清：删测试绑定（bindings.json）+ 测试 bundle + `_scratch/` 产物。
5. 宿主自有内容永不被动（信封原则）；receipts 之外的运行时状态不碰。
6. 新 clone 的一次性动作：`git config core.hooksPath .githooks`（启用提交闸门）。

## 命令面（9 动词）

```
python persona.py validate <源目录>          # lint：schema/锚点/按名引用
python persona.py pack <源目录>             # → bundles/<id>/<hash>/，幂等
python persona.py publish                    # git 提交 + push
python persona.py list                       # registry + 绑定概览
python persona.py bind <slot> [--host] [--target] [--var K=V] [--device] [--pin] <persona>[@hash]
python persona.py status [slot] [--device]   # 漂移报告
python persona.py reconcile [slot] [--pull] [--device]
python persona.py revert <slot>              # 指回上一版本并收敛
python persona.py absorb <slot> --yes       # promote：宿主编辑写回源目录提案
```

exit：0=全收敛；2=有漂移/缺件；其余=参数错。
漂移状态机：`converged / drifted(-pinned) / partial / not-placed / missing-bundle / render-fail`。

## 改动前必读的实现事实

- `render_files`：任一占位符漏填 → `render-fail`，拒绝物化（fail-closed，不产半成品）。
  正则 `[A-Za-z][A-Za-z0-9_]*`（曾因 `[A-Z]` 漏小写出过静默通过 bug，已修）。
- `derived_hash` 按 manifest 顺序：`list(files.items())`，**不是** `sorted()`——
  否则无 vars 时派生 hash ≠ 源 hash。
- `dsh_prefix`：头 `<!-- persona:<id>@<hash> -->` + 每文件 `<!-- persona:file X -->`
  标记；readback 按标记切回；信封外内容归宿主，uninstall 摘块还原。
- reconcile 单槽顺序：load_bundle → render → derived_hash → adapter.place → _check → receipt。

## dsh 接线知识（M2 实战挣出来的，别再踩）

- **适配器层只有一个 `host: dsh`**：磁盘契约 = prefix.txt（always-on+session-start 拼接）
  + on-demand 平铺。TUI 与 web 产品同契约 → **不拆 dsh/dsh-tui**；产品差异在接线层，
  由 slot/device 表达。
- **TUI persona 体系**：会话 persona 由 agent 预设内 `dsh-persona` 行供给（standard
  preset 默认文案 `You are a coding agent powered by the {{model}} model.`），**遮蔽**
  部署级 `system-prompt.personaPrefix`。接线必须打 preset 层——第一版 shim 打部署级
  被遮蔽，无效。
- **win-dsh 当前接线（生效中）**：`D:\00_WY\300_Dev\.dsh\profiles\dsh-tui\cordis.patch.yml`
  末尾 persona 托管块（BEGIN/END 标记，整块删除即卸载）= preset-patch 行
  （seam VII，模块 `@deepseek-harness-tui/dsh-tui/preset-patch`），替换 standard
  预设 persona 行的 prefix 为「配置加载时读 `persona.prefix.txt`」的 `!!js` 表达式。
  两个坑：①行必须 `- insert:` 形式（id 定位式报 entry not found）；②prefix 内容是
  dsh-persona 模板，未知 `{{…}}` 引用直接抛错（validate 的占位符检查即为此）。
- 生效链：改 prefix.txt → 接线无需动 → TUI `/restart` → 新会话即新 persona
  （配置加载时读文件，永不过期）。
- **linux-sandbox 接线**：`dsh-bridge.py` 把 prefix.txt 编译进 `--patch` overlay
  （编译期内联；改 prefix 后须重跑 bridge）。第三台设备规则：优先「加载时读产物」
  的产品原生接缝，没有再写 bridge 类胶水。
- 验证手段：`dsh --dump-config --profile dsh-tui` 看 stderr（`entry "…" not found`
  = 接线语法错）；会话级 `/debug-prompt` 导 `.dsh-prompt-debug.json`，比对 system
  prompt 内 persona 块与 prefix.txt 逐字一致（含标记）。

## 当前状态（2026-11-20）

- 仓库位置：`D:\00_WY\400_Code\410_Remote\persona-stack`（本机 clone；权威在 GitHub）。
- 编辑面 = 仓库内 `sources/<id>/`（外部草稿目录已废除并删除）。
- **absorb 端到端实测通过（本轮）**：临时改落位 → drifted（exit 2）→ reconcile 恢复
  → 再造临时版 → `absorb --yes`（写回 sources 提案）→ 升版本 → publish（v1.1.0）→
  bind 升级 → reconcile 收敛 → 清测试标记再发 v1.1.1 → 全链 green。版本链
  v1.0.0/v1.1.0/v1.1.1，verify 3 bundle 全过。绑定现指 v1.1.1。
- absorb 健壮化：pack-time source 失效时回退 `sources/<id>/`（仓库迁移后旧
  index 条目不再炸 absorb）。
- M1 ✅ registry；M2 ✅ win-dsh 会话级闭环（枭枭生效，/debug-prompt 证据 d13d23f），
  linux-sandbox 待远端自验；M3 🚧 openclaw adapter 已实现，待真实宿主；M4 ✅ 渲染层
  （fixture 已清）；M5 🚧 未开工。
- 绑定：`dsh.local`（win-dsh → `D:\00_WY\100_Works\dsh-workspace`，现指
  v1.1.1）、`dsh.web.sandbox`（linux-sandbox → `/workspace/dsh-app/persona`）。
- 实测暴露的工具坑（已修）：`Path.write_text` 默认换行翻译会在 Windows 上把 LF
  变 CRLF，破坏 readback 标记切分——落位/写回操作必须字节级（`write_bytes`）。

## 常见任务配方

- **改人设内容（正式版）**：编辑 `sources/xiaoxiao/` 人设文件集 → `publish`
  （自动 validate+hash+快照+提交+推送）→ `reconcile dsh.local` → 提醒用户 `/restart`。
- **临时人设（不发版）**：直接改**落位目录**的 `persona.prefix.txt`（接线读它）→
  `/restart`。reconcile 读 bundles 快照、不读 sources 草稿——改 sources 不跑
  publish 是刷不下去的。`status` 报 drifted = 临时版生效中的标记；恢复正式版 =
  `reconcile`；临时版转正 = `absorb dsh.local --yes`（宿主编辑写回 sources 提案）
  → `publish`。远端设备不受影响（它们只认 bundles）。
- **排查 persona 未生效**：`status dsh.local` → prefix.txt 在否/新否 → dump-config
  stderr → 引擎进程启动时间 vs prefix.txt mtime → 最后才怀疑接线本体。
- **新设备接入**：`clone` → `git config core.hooksPath .githooks`（一次性）→
  `bind` 新 slot（带 `--device`）→ `reconcile` 物化 → 按「接线知识」选接缝 →
  会话级验证。
- **linux-sandbox 侧操作**：那边有本仓库 clone；`python3 persona.py reconcile --pull
  --device linux-sandbox` + `dsh-bridge.py`。
