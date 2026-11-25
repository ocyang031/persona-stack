# persona 注入工具 · 设计契约（v2）

- 日期：2026-11-19（含实施期修正，见 §11 尾注）
- 性质：纯设计文档——不变式、接缝、决策记录。不含实时进度；实施状态看 [AGENTS.md](./AGENTS.md)。
- 编辑面：`sources/<id>/`。正式版本以 `bundles/` 内的快照为准。
- 历史包袱已归档 `_archive/`（旧架构实现）；被取代的旧 PRD 见
  [人设配置工具-需求规格.md](./人设配置工具-需求规格.md)（superseded 标记在 frontmatter）

---

## 0. 一句话定位

每个人设模块都是可直接使用的提示词。绑定决定采用一个模块还是多个模块。Registry 保存不可变快照，Reconciler 按绑定和宿主格式落位并报告漂移。多文件组装负责选择、依清单顺序排列和加可逆信封，正文保持原义。

### 模块写作契约

| 模块 | 模型读到的内容 |
|---|---|
| `AGENTS.md` | 执行规则、权限边界、验收与交付要求 |
| `IDENTITY.md` | Persona 身份、角色与能力表述 |
| `SOUL.md` | 语气、价值观与回复风格 |
| `TOOLS.md` | 工具使用和状态变更流程 |

- 以模块职责为单位编写。模型仅读到该模块时，仍能执行其中每条指令。调整模块排列时，规则含义保持一致。需要共同解释的规则放在同一模块。
- 正文直接写动作、适用条件和结果。保留有行为价值的示例及标题。去除目录、维护导航、定位说明、交叉引用、槽位锚点和重复规则。优先保证机器理解和上下文利用率，篇幅按规则需要控制。
- `persona.yaml` 保存版本和清单顺序。设计理由、文件分工和操作说明维护在 DESIGN 与 README 中，这两份文档均在清单外。
- 从当前枭枭源移除 `CONTEXT.md` 及其槽位注册表。旧快照继续按历史布局读取和回滚。DSH 跨代迁移时先按旧绑定卸载，再接入新包。宿主编辑通过人工合并迁移。

### AGENTS.md 的完整性例外（2026-11-25 实测）

模块契约的"去交叉引用、控制篇幅"不适用于 `AGENTS.md`。三臂对照（裸臂 / 极简
`aed40828ab97718e` / Full `b08ee5f92df2eaed`）显示：裸臂与极简的模型输出基本一致，
Full 仍保留完整的语义职能。

极简版把执行规则压成动作清单，许可域（§2）、拒绝与过度拒绝处理（§3–§4）、
判定程序与示例（§5）、工具与会话纪律（§6–§7）随之消失。这些章节承载的是
语义职能，不是可去重的导航或重复规则。对照的是整套人设，不是单文件消融：
`v2.0.0` 的四份模块都被压缩，所以"整套极简 ≈ 裸臂"不能单独归因给某一份文件。

规则：`AGENTS.md` 的蒸馏只允许压缩表述，不允许删除职能章节；改版须以
裸臂 / 极简 / Full 三臂对照为闸门，极简与裸臂无差异即回退。`v2.0.0`
（`aed408...`）保留为负结果对照，不绑定；`v2.0.1` 回填 Full 的语义正文
（§1–§7），其余三份维持精简。回填只去掉不进入语义的 YAML frontmatter、
维护性导航和模块文件名互引（v2 source lint 的硬性要求），规范性段落不动。
判据是下一步的 AGENTS 消融：裸臂 / `v2.0.1` / `v1.3.0` 全量三臂，
`v2.0.1` 应显著偏离裸臂；若仍与裸臂一致，则其余三份一并回滚。

## 1. 四条不变式（宪法）

| # | 不变式 | 内容 |
|---|---|---|
| I1 | 内容不变式 | 人设文件集内容宿主无关。宿主 `readback` 逐字节还原绑定选定并渲染的模块。 |
| I2 | 事实源唯一式 | 内容只在源仓库被编辑；宿主侧永远是副本。宿主上的编辑不是事实，是漂移（或待晋升提案，见 §7）。 |
| I3 | 不可变发布式 | bundle 一经发布不可改写；任何改动 = 新版本、新 hash。回滚 = 绑定指回旧 hash。 |
| I4 | 声明式收敛式 | 部署状态由两张表描述：绑定表（host.slot → persona@hash）与回执流。工具职责 = 让应然与实然收敛，并报告差异。 |

I3 顺手消灭一类经典漂移："改已部署产物"在不可变模型里没有语法。

## 2. 决策记录（2026-11-19 拍板）

| 板 | 决定 | 理由 |
|---|---|---|
| Registry 形态 | **git 仓库（本仓库）**，`bundles/` 目录存不可变 bundle | 克隆即全量副本（HA 白送）；历史即版本链（revert = 指回旧 hash）；零新增基础设施。不可变性靠纪律 + review 兜底（见 §9 纪律条款）。 |
| 渲染层 | **进 v1** | 多实例需求成立（见 §6）；源 bundle 保持字面量纯净，派生 hash 链回输入，I1 不被污染。 |
| 触发器 | **v1：手动 CLI + DSH 开机自拉**；OpenClaw/Operit 手动；不引入守护进程/cron | 守护进程是另一个要保活的东西，能不养就不养；真嫌烦再加。 |
| 指纹/溯源 | provenance 全部外置（清单 hash、信封标记），不写进正文 | 保住逐字节可比性（I1）。 |

## 3. 组件与数据流

```
人设文件集 + persona.yaml(清单)
        │ validate → pack: 算内容 hash → 不可变 bundle
        ▼
┌─ Registry（git bundles/，不可变）──┐   ← 接缝②：git / 目录 / HTTP 可插
└──────────────────────────────────┘
        │
绑定表（数据不是代码）：
  dsh.web      → xiaoxiao@a1b2c3
  openclaw.ws  → xiaoxiao@a1b2c3     ← 同一 hash = "同一套配置"的机械保证
  operit.card  → xiaoxiao@a1b2c3
        │
┌─ Reconciler（唯一的深模块）─────────────────────┐
│ 接口：reconcile(binding) → receipt               │
│       status() → 漂移报告                        │
│ 内部：取 bundle → 选择模块 → render(可选)        │
│       → adapter.encode → 落位 → readback         │
│       → hash 对账 → 回执落账                     │
└─────────────────────────────────────────────────┘
        │
┌─ Host Adapter（接缝①）─────────────┐
│ place / readback / remove           │
│ encode / decode（信封往返，自描述）  │
└─────────────────────────────────────┘
```

- **persona.yaml 清单**：id、version、按顺序列出的模块。绑定的 `include` 优先于适配器默认选择。
- **Reconciler**：唯一深模块。接口两个动词，后面藏取件、渲染、编码、事务落位、对账、回滚全部行为。无状态：应然在绑定表，实然在回执流。
- **Host Adapter**：用宿主的原生格式落位、读回和卸载选中的模块。

## 4. 三条接缝 = 可扩展性的全部

| 接缝 | 变化轴 | 新增一个 X 要动什么 |
|---|---|---|
| ① Host Adapter | 宿主加载机制 | 一个 ~百行 adapter，核心零改动 |
| ② Registry Backend | 存储位置 | 一个 backend 实现 |
| ③ Trigger | 收敛时机 | 调 `reconcile()` 的另一种方式（手动/开机钩子/未来 cron） |

## 5. 各宿主 adapter 契约

| 宿主 | 默认选择 | 落位形式 |
|---|---|---|
| DSH | 全部模块 | 单一 `persona.prefix.txt`，按清单顺序拼装并用文件标记分段 |
| Codex | `IDENTITY.md` 和 `SOUL.md` | 一个宿主说明文件中的托管块，按清单顺序拼装 |
| File / OpenClaw | 全部模块 | 逐文件写入托管块 |

绑定通过 `--include` 指定单个文件或多个文件，适配器仅落位所选内容。卸载摘除托管部分，保留宿主自有内容。

## 6. 渲染层（v1 进）：多实例语义

**多实例 = 同一份 SOUL，多个身体。** 灵魂只有一份；变的是名牌（名字、称呼、id 等占位符的填充值）。多 soul 是另一回事：那叫多 persona，= registry 里另一套人设文件集目录、另一行绑定，从来不需要渲染层。

```
源 bundle（字面量纯净，含 {{PERSON_NAME}} 等占位符）
    │ render(bundle, vars)
    ├── xiaoxiao@a1b2c3 → {{PERSON_NAME}}=枭枭 → derived bundle hash X
    └── axiao@a1b2c3   → {{PERSON_NAME}}=阿枭 → derived bundle hash Y
```

派生 bundle 的 provenance 记 `render(源hash, vars-hash)`，链回输入。绑定表绑的是派生 hash；同一源、不同填充，互不干扰。占位符词表沿用源集既有的 `{{PERSON_xxx}}` 风格。

## 7. 漂移治理（"避免多事实源"的正面回答）

宿主侧编辑无法禁止（agent 自我修订是活例），正确做法是分歧可见、处理便宜——git 对手动编辑的答案：

| 策略 | 语义 | 适用 |
|---|---|---|
| revert | 恢复 bundle 原文 | 默认；纯意外改动 |
| pin | 该 slot 冻结当前 hash，豁免对账 | 声明式例外 |
| promote | 宿主编辑抽回源仓库，作为新版本提案走 validate → pack → 绑定升级 | agent 自改进循环的安全化：改进变成一次版本化晋升，而不是暗事实源 |

## 8. 质量属性落地

- **可伸缩**：绑定表是数据，N persona × M 宿主 × K slot 零代码增长；reconciler 无状态、任意副本可跑；内容寻址天然去重；pull 接入 = 首次拉取 + 一行绑定。
- **可扩展**：三个真接缝 + schema 扩展位（§4）；新宿主成本 = 一个 adapter 文件。
- **高可用**：不可变 bundle + last-good 本地缓存——registry 不可达时宿主继续用当前 persona（陈旧是安全的，fail-open）；hash 不符 → 拒绝物化、保留现状、告警（fail-closed，损坏不上线）；事务式 apply（写临时区 → 全量对账 → 原子换入 → 回执落账），中断 = 幂等重跑；回滚 = 绑定指回旧 hash + 一次 reconcile。

## 9. 纪律条款（写进贡献指南，人执行）

1. `bundles/` 只进不改：修正 = 新版本新 hash，永不 rewrite 历史；
2. 占位符词表变更 = schema 版本 bump；
3. 模块改动验证独立使用和常用组合，维护说明同步反映实际行为；
4. 绑定表变更走 PR，改动可追溯回源 hash。

## 10. 命令面（9 动词）

```
persona validate                     # lint 人设文件集：清单、编码、正文及文件依赖
persona pack                         # 算 hash → 不可变 bundle
persona publish                       # 写入 registry（git commit+push）
persona list                          # registry 清单 + 绑定概览
persona bind <slot> <persona@hash>    # 声明应然
persona status                        # 全宿主漂移报告
persona reconcile                     # 收敛（DSH 开机钩子调的也是它）
persona revert <slot>                # 指回旧 hash + 收敛
persona absorb <slot>                # promote 路径：宿主编辑 → 新版本提案
```

## 11. 里程碑

| 期 | 内容 | 验收 |
|---|---|---|
| M1 | validate + pack + git registry | 人设文件集 → bundle 落库，hash 稳定可复算 |
| M2 | DSH adapter + reconcile + 开机钩子 | prefix 注入 + readback 对账回执 + 断网 fail-open |
| M3 | OpenClaw adapter | 所选模块逐文件落位 + 宿主自有内容无损 + uninstall 还原 |
| M4 | 渲染层 | 同源两填充，两派生 hash，各自绑定收敛 |
| M5 | Operit adapter | 卡片往返 encode/decode 对账 |
| 收尾 | 旧 persona-stack 归档 `_archive/`，本仓库切换为新实现 | verify 脚本全绿 |

实时进度记录在 [AGENTS.md](./AGENTS.md)（当前状态节），不回写本表。

实施中补的两条设计修正（已并入本文）：DSH 接线最终落在 **preset-patch 接缝**
（TUI 会话 persona 由 agent 预设供给并遮蔽部署级，§5 原表述只对了预设层一级）；
渲染层补 **fail-closed 缺填拒绝**（占位符漏填 → `render-fail`，不物化半成品，
§6 原表述未覆盖该分支）。

## 12. 与旧架构的取舍账

| 旧 persona-stack | 新设计 | 判词 |
|---|---|---|
| 源碎成 identity/soul/contract/domain + 编译拼装 | 可独立使用的正文模块，按绑定选择并可逆拼装 | 扔：源形态≠宿主形态的翻译层是自找的 |
| SOURCE_DIRNAME 硬编码，一机一 persona | 绑定表数据化 | 扔：多 persona 多宿主的最大闸门 |
| 指纹行写进正文首行 | provenance 外置 | 扔：内容被污染，逐字节可比性报废 |
| install 时一次性 verify | readback 对账 + 按触发收敛 | 扔：漂移只在安装瞬间可见 |
| push-only install | pull/push 双向、无状态引擎 | 扔：推送器宕机 = 收敛停摆 |
| managed-block 信封、回滚纪律、"进程真挂载才算数" | 保留，进化为 adapter 契约 | 留：实践挣出来的 |
