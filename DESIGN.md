# persona 注入工具 · 设计定稿（v1）

- 日期：2026-11-19（含实施期修正，见 §11 尾注）
- 性质：纯设计文档——不变式、接缝、决策记录。不含实时进度；实施状态看 [AGENTS.md](./AGENTS.md)。
- 前置：五文件人设集（AGENTS / IDENTITY / SOUL / TOOLS / CONTEXT，以 `agents-box/EN/` 现状为准）
- 历史包袱已归档 `_archive/`（旧架构实现）；被取代的旧 PRD 见
  [人设配置工具-需求规格.md](./人设配置工具-需求规格.md)（superseded 标记在 frontmatter）

---

## 0. 一句话定位

**这不是编译器，是一台"注册表 + 收敛器"。**
五文件本身就是最终形态，不需要拼装、碎片化、再缝回。工具只做两件事：

1. **Registry** —— 把五文件变成不可变的版本化快照（bundle）；
2. **Reconciler** —— 让任意多台宿主机上的副本与快照保持收敛，并把差异报告出来。

编译阶段整个消失。宿主之间的真实差异是"加载机制"的差异，不是"内容"的差异；五文件的切分恰好按加载时机切，它就是为分布而生的粒度。人读的、agent 读的、机器校验的，是同一份东西。

## 1. 四条不变式（宪法）

| # | 不变式 | 内容 |
|---|---|---|
| I1 | 内容不变式 | 五文件内容宿主无关。任意宿主上 `decode(readback)` 与 bundle 逐字节相等（按 hash 判等）。 |
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
五文件 + persona.yaml(清单)
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
│ 内部：取 bundle → render(可选) → adapter.encode  │
│       → 事务式落位 → adapter.readback → decode   │
│       → hash 对账 → 回执落账                     │
└─────────────────────────────────────────────────┘
        │
┌─ Host Adapter（接缝①）─────────────┐
│ place / readback / remove           │
│ encode / decode（信封往返，自描述）  │
│ + load hints 翻译成本宿主加载机制    │
└─────────────────────────────────────┘
```

- **persona.yaml 清单**：id、version、必需文件集、load hints（AGENTS=always-on；TOOLS/CONTEXT=on-demand）。load hints 是元数据不是内容——宿主按自己的机制翻译它。
- **Reconciler**：唯一深模块。接口两个动词，后面藏取件、渲染、编码、事务落位、对账、回滚全部行为。无状态：应然在绑定表，实然在回执流。
- **Host Adapter**：三动词 + 一对往返 + hints 翻译，每个约百行。

## 4. 三条接缝 = 可扩展性的全部

| 接缝 | 变化轴 | 新增一个 X 要动什么 |
|---|---|---|
| ① Host Adapter | 宿主加载机制 | 一个 ~百行 adapter，核心零改动 |
| ② Registry Backend | 存储位置 | 一个 backend 实现 |
| ③ Trigger | 收敛时机 | 调 `reconcile()` 的另一种方式（手动/开机钩子/未来 cron） |

DSH、OpenClaw、Operit 三个宿主已确定存在且互不相同——这是三个现役 adapter 证明过的真缝，不是假想接缝。内容层扩展位：清单可声明五文件之外的 advisory 文件（如本 DESIGN），标"按需、允许宿主不物化"；文件集 schema 本身版本化。

## 5. 各宿主 adapter 契约

| 宿主 | encode | load hint 翻译 | 触发 |
|---|---|---|---|
| DSH | 五文件按清单序拼成单一 prefix，文件间插自描述标记 `<!-- persona:file X.md -->`，decode 按标记切回五段 | always-on = 进 prefix；on-demand = 不进 prefix、留在工作区 | 开机自拉（start.sh 起动前 reconcile） |
| OpenClaw | 逐文件 managed-block 信封（BEGIN/END 标记），decode 按信封剥壳；区块外内容归宿主 | always-on 三文件；on-demand 留工作区 | 手动（未来可挂 session-start） |
| Operit | 卡片 JSON 字段映射（encode/decode 按字段 schema 往返） | 卡片即常驻；CONTEXT 之类塞进卡片附注区 | 刷卡时手动 |

信封原则从旧架构保留：**宿主自有内容永不被动**，uninstall 摘区块、宿主恢复原样。

## 6. 渲染层（v1 进）：多实例语义

**多实例 = 同一份 SOUL，多个身体。** 灵魂只有一份；变的是名牌（名字、称呼、id 等占位符的填充值）。多 soul 是另一回事：那叫多 persona，= registry 里另一套五文件目录、另一行绑定，从来不需要渲染层。

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
3. 锚点/槽位改动与注册表同步在同一次提交内完成；
4. 绑定表变更走 PR，改动可追溯回源 hash。

## 10. 命令面（9 动词）

```
persona validate                     # lint 五文件：schema、锚点注册表、按名交叉引用
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
| M1 | validate + pack + git registry | 五文件 → bundle 落库，hash 稳定可复算 |
| M2 | DSH adapter + reconcile + 开机钩子 | prefix 注入 + readback 对账回执 + 断网 fail-open |
| M3 | OpenClaw adapter | 三文件落位 + 宿主自有内容无损 + uninstall 还原 |
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
| 源碎成 identity/soul/contract/domain + 编译拼装 | 五文件即源，零编译 | 扔：源形态≠宿主形态的翻译层是自找的 |
| SOURCE_DIRNAME 硬编码，一机一 persona | 绑定表数据化 | 扔：多 persona 多宿主的最大闸门 |
| 指纹行写进正文首行 | provenance 外置 | 扔：内容被污染，逐字节可比性报废 |
| install 时一次性 verify | readback 对账 + 按触发收敛 | 扔：漂移只在安装瞬间可见 |
| push-only install | pull/push 双向、无状态引擎 | 扔：推送器宕机 = 收敛停摆 |
| managed-block 信封、回滚纪律、"进程真挂载才算数" | 保留，进化为 adapter 契约 | 留：实践挣出来的 |
