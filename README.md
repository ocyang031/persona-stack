# 项目入口 · persona-stack

| 字段 | 内容 |
|---|---|
| 项目名 | persona-stack（多 Agent 人设配置工具） |
| 状态 | P0 最小链路已跑通（dsh standard + prefix 注入，install/verify/uninstall 全验证）；其余 preset 与 AGENTS.md 待第一批验证后铺 |
| 关联仓库的 remote | 🚧 暂无（尚未建代码仓库；若后续建仓，在此登记 remote 地址） |
| 指向仓库与交付物的链接 | 需求规格：[人设配置工具-需求规格.md](./人设配置工具-需求规格.md)；实现：[persona.py](./persona.py)；dsh 方案：[落位映射.md](./dsh/落位映射.md) / [勘察清单](./dsh/可适配替换清单-dsh-2026-11-18.md) / [approved.json](./dsh/approved.json)；A 产品（已冻结）：[网关注入引擎-Project.md](../../000_Inbox/网关注入引擎-Project.md) |

> 入口说明：按《收口目录部署方案（首次落地版）》§6，项目入口文档是代码仓库与项目之间的唯一纽带——代码事实以仓库为准，项目过程资料保留在本目录。当前无代码仓库，remote 留空待建仓后补，不编造。

## 目录模型（2026-11-18 确认）

```
persona-stack/
├── persona-<YYMMDD>-v<x.y>/   ① 人写源目录：一个版本一个目录，唯一事实源
│   └── (persona.yaml / soul.md / contract/ / domain/)
├── dsh/                       ② dsh 已验证方案：勘察清单 + 落位映射 + approved.json + persona.patch.yml（编译产物）
├── alma/                      ② alma 已验证方案（待勘察）
├── persona.py                   P0 编译落位实现（compile/install/verify/uninstall）
└── 人设配置工具-需求规格.md      PRD（四层模型见 §2）
```

源目录只管"我是谁"（版本化），方案目录只管"我在这个 agent 怎么落地、已验证"（固定名、不跟版本走）。源升版须重验并更新方案，旧方案移入各 `<host>/_archive/`。详见 PRD §1/§2/§4.2。

## P0 用法

```bash
P=001_OcLedger/100_Works/persona-stack/persona.py   # 相对 /workspace/dsh-app
python3 $P compile                    # 源目录 → dsh/persona.patch.yml
python3 $P install --host dsh         # 挂载 + 重启 + verify（失败自动回滚）
python3 $P verify                     # 校验运行进程与有效配置
python3 $P uninstall                  # 摘除 + 重启，恢复 dsh 原样
```

**当前源目录是示例人设**（YanShen 骨架，来自 persona-template），非用户真实人设——替换 `persona-*/soul.md` 与 `contract/*.md` 后重跑 install 即可生效。首版只在 standard preset 注入、契约合并进 prefix；ptc/cordis/minimal 与 AGENTS.md 未动。
