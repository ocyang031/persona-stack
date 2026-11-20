# persona-stack · persona registry + reconciler

五文件人设集（AGENTS / IDENTITY / SOUL / TOOLS / CONTEXT）的注入工具。
**不是编译器**：五文件即最终形态，工具只做两件事——快照成不可变 bundle（registry）、
把宿主侧副本收敛到快照（reconciler）。设计全文见 [DESIGN.md](./DESIGN.md)
（旧架构的编译/拼装/硬编码源目录路线已被其取代；旧 PRD
[人设配置工具-需求规格.md](./人设配置工具-需求规格.md) 仅作历史资料保留）。

## 目录模型

```
persona-stack/                ← 本仓库 = git registry（seam ②）
├── persona.py                registry + reconciler + adapters，单文件 CLI
├── DESIGN.md                 设计定稿（四不变式、三接缝、决策记录）
├── bundles/<id>/<hash>/      不可变快照：persona.yaml + 五文件（只进不改）
├── bindings.json             绑定表：slot → persona@hash（宿主应然状态，提交）
├── receipts/                 回执流（运行时状态，gitignore）
├── _archive/                 旧 v2.0 架构归档（gitignore）
└── _scratch/                 本机测试落位（gitignore）
```

人设源目录（本机）：`agents-box/EN/` —— 五文件 + `persona.yaml` 清单。
版本史由仓库 `bundles/` + git 提交承担；源目录是编辑现场，不是版本库。

## 快速上手

```bash
python persona.py validate <源目录>                # lint：清单/锚点注册表同步/按名引用
python persona.py pack <源目录>                   # → bundles/xiaoxiao/<hash>/，幂等
python persona.py publish                         # git 提交 + push（不可变发布）
python persona.py list                            # registry 清单 + 绑定概览
python persona.py bind <slot> --host file|dsh --target <目录> xiaoxiao[@hash]
python persona.py status [slot]                   # 漂移报告（exit 0=全收敛, 2=有漂移）
python persona.py reconcile [slot] [--pull]       # 收敛；漂移默认按 revert 恢复
python persona.py revert <slot>                   # 绑定指回上一版本并收敛
python persona.py absorb <slot> --yes             # promote：宿主编辑写回源目录提案
```

`--var KEY=VAL`（bind 时）走渲染层：占位符填充产派生 hash，同源多实例互不干扰。
实测（renderlab 一次性测试人设，验证后已从注册表删除，证据在提交 22dd80d）：
同 bundle 两实例（Ada/Berlin / Lin/Hangzhou）各自收敛、派生 hash不同；
漏填占位符 → `render-fail`（exit 2，拒绝物化，不产出半成品 persona）；
改实例内容 → drifted → reconcile 按源恢复。占位符词汇表大小写敏感。

## 漂移策略（宿主侧被改了怎么办）

| status | 处置 |
|---|---|
| converged | 无事 |
| drifted | `reconcile` = revert（默认恢复原文）；或 `absorb` = promote（写回源目录走版本化晋升） |
| drifted + `bind --pin` | 声明式豁免：该 slot 冻结，reconcile 跳过 |
| missing-bundle | fail-closed：拒绝物化，保持现状，先 pack/pull |

## 宿主接线

- **file / openclaw**：每文件托管块信封（`<!-- persona:id@hash BEGIN/END -->`），
  块外内容归宿主，uninstall 摘块还原。
- **dsh**：prefix 文件（always-on + session-start）拼成单一 `persona.prefix.txt`
  （自描述文件标记），on-demand 文件随目录平铺。**适配器层只有一个 `host: dsh`**
  （`DshAdapter` 在 persona.py，管磁盘契约与信封往返）——TUI 与 web 产品消费同一
  产物形态，不做 dsh / dsh-tui 之分；产品差异在**接线层**，由 slot/device 表达：

  - **win-dsh（本机 TUI）**：profile `cordis.patch.yml` 的 **preset-patch 行
    （seam VII）**——替换 standard 预设里 persona 行的 `prefix` 配置为「配置加载时
    读 `persona.prefix.txt`」的 js 表达式。要点：TUI 会话的 persona 由 agent 预设
    （dsh-persona）供给，会遮蔽部署级 `system-prompt.personaPrefix`（第一版 shim
    打在部署级、被预设遮蔽未生效，已修正到预设层）。preset 内行不受 id 定位补丁
    影响，必须用 preset-patch 接缝；行本身须为 `insert` 形式。
  - **linux-sandbox（dsh web 产品）**：`dsh-bridge.py` 将 prefix.txt 编译为
    `--patch` overlay（自校验往返）。注意它是**设备接线胶水，非适配器**——
    硬编码该机路径，编译期内联（每启动重编等效保鲜；改 prefix 后须重跑）。
  - 两种接线的新鲜度模型不同：win-dsh 配置加载时读文件（永不过期），bridge
    编译期内联（重编才保鲜）。第三台设备接入规则：优先「加载时读产物」的
    产品原生接缝，没有再用 bridge。

  宿主机开机自拉（start.sh / 启动参数）：

  ```bash
  python3 <repo>/persona.py reconcile --pull --device <device> 
  ```

  多设备时用 `--device` 限定本机视角（否则会把别的设备的 slot 报成 not-placed）。
  注意：prefix 内容会成为 dsh-persona 模板（严格 `{{…}}` 渲染，未知引用抛错），
  validate 已含占位符检查；dsh-persona 的 `suffix` 默认被遮蔽为空，本集用不到
  suffix，无影响。

## 状态（2026-11-20）

- ✅ M1 registry（validate/pack/publish/list）—— EN 集 v1.0.0 已入库
- ✅ reconciler + file/openclaw + dsh 适配器（往返、漂移检测、恢复、回执全过）
- ✅ 旧架构归档 `_archive/`
- ✅ M2 真实宿主接线 + 会话级验证闭环：win-dsh preset-patch 行（seam VII）——
  TUI 重启后新会话自报枭枭且否认外部厂商身份；`/debug-prompt` 硬证据：
  system prompt 中 persona 块 = persona.prefix.txt 全文（含标记，19,976 字节
  逐字出现于位置 50），stock `coding agent powered by {{model}}` 模板已被遮蔽，
  TOOLS/CONTEXT 正确留在工作区未进提示词；且该证据采集自 ob-garden 工作区——
  persona 接线是 profile 级，覆盖本机全部会话。linux-sandbox 接线（dsh-bridge）
  由远端设备自行验证。
- ✅ M4 渲染层实测（双实例 + 缺填拒绝 + 漂移恢复全过；测试 fixture 已清理）
- 🚧 M5 Operit 适配器、CN 母版五文件拆分入库
