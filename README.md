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
python persona.py bind <slot> --host file|dsh --target <目录> xiaoxiao[@hash]
python persona.py status [slot]                   # 漂移报告（exit 0=全收敛, 2=有漂移）
python persona.py reconcile [slot] [--pull]       # 收敛；漂移默认按 revert 恢复
python persona.py revert <slot>                   # 绑定指回上一版本并收敛
python persona.py absorb <slot> --yes             # promote：宿主编辑写回源目录提案
```

`--var KEY=VAL`（bind 时）走渲染层：占位符填充产派生 hash，同源多实例互不干扰。

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
- **dsh**：always-on 文件拼成单一 `persona.prefix.txt`（自描述文件标记），
  on-demand 文件随目录平铺。宿主机 start.sh 启动命令前加一行即开机自拉：

  ```bash
  python3 <repo>/persona.py reconcile --pull dsh.web
  ```

  （本机已验证 prefix 的 encode/decode 逐字节往返；真实 dsh 宿主机接线为 M2 收尾项。）

## 状态（2026-11-19）

- ✅ M1 registry（validate/pack/publish/list）—— EN 集 v1.0.0 已入库
- ✅ reconciler + file/openclaw + dsh 适配器（往返、漂移检测、恢复、回执全过）
- ✅ 旧架构归档 `_archive/`
- 🚧 真实宿主接线（dsh start.sh / openclaw 目标机）与渲染层实测（EN 集暂无占位符）
