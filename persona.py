#!/usr/bin/env python3
"""persona-stack · 编译落位（dsh P1 prefix 注入 + openclaw SOUL/AGENTS 生成）。

设计依据：人设配置工具-需求规格.md（四层模型，2026-11-18）。
dsh 口径：只改 standard preset；契约合并进 prefix；不碰其余 preset 与 AGENTS.md。
openclaw 口径（2026-11-18 采纳）：主流 SOUL.md + AGENTS.md 组合作为落位格式——
  compile 生成 openclaw/SOUL.md（身份+风格）与 openclaw/AGENTS.md（契约+域规格），
  install 按「托管区块三态」写入目标 workspace（无标记追加 / 有标记换块 / uninstall 删块），
  区块外内容一律不动——双文件边界由编译期强制切分。

命令：
  persona.py compile [--host dsh|openclaw]
  persona.py install --host dsh            # compile + 挂 --patch + 重启 + verify（失败回滚）
  persona.py install --host openclaw [--target DIR]   # compile + 托管区块落位 + verify（失败还原）
  persona.py verify [--host dsh|openclaw]
  persona.py uninstall [--host dsh|openclaw] [--target DIR]

关键机制（源码实读 @deepseek-ai/dsh-app-boot/lib/index.js:61-115）：
  - patch 按 id 命中顶层 entry，overrides 浅覆盖（整体替换 config）。
  - preset 的 config.plugins 未标 group:true，故子项 id:persona 不在索引里，
    不能直接 patch；必须整体覆盖 standard 的 config（保留全部插件，只改 prefix）。
  - 因此编译产物 = 从「当前 dump」动态提取的完整 standard config + 改后的 prefix，
    这样 dsh 升级/插件变化时重新 compile 即可跟上，不硬编码插件列表。
"""
import argparse
import datetime as dt
import hashlib
import os
import re
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SOURCE_DIRNAME = "persona-261118-v1.0"          # 首版源目录；未来由 persona.yaml 发现
DSH_PATCH_DIR = os.path.join(HERE, "dsh")
PATCH_FILE = os.path.join(DSH_PATCH_DIR, "persona.patch.yml")
START_SH = "/workspace/dsh-app/start.sh"

# openclaw 宿主（SOUL.md + AGENTS.md 主流组合，作为 persona-stack 的落位格式之一）
OC_PERSONA_ID = "persona-261118-v1.0"
OC_DIR = os.path.join(HERE, "openclaw")
OC_IDENTITY_ART = os.path.join(OC_DIR, "IDENTITY.md")
OC_SOUL_ART = os.path.join(OC_DIR, "SOUL.md")
OC_AGENTS_ART = os.path.join(OC_DIR, "AGENTS.md")
OC_ARTIFACTS = ("IDENTITY.md", "SOUL.md", "AGENTS.md")   # 统一维护：install / uninstall 都以此为准
OC_DEFAULT_TARGET = "/root/.openclaw/workspace"   # OpenClaw 默认 workspace；可 --target 覆盖
OC_BLOCK_RE = re.compile(
    rf"<!-- persona:{OC_PERSONA_ID}@[\w.]+ BEGIN -->.*?<!-- persona:{OC_PERSONA_ID}@[\w.]+ END -->\n?",
    re.S,
)
NODE24 = "/root/.nvm/versions/node/v24.21.0/bin/node"
DSH_ENTRY = "/workspace/dsh-app/node_modules/@deepseek-ai/dsh/lib/bin.js"
PROFILE = "web"
DUMP_FILE = "/tmp/persona-dsh-dump.yml"

# 托管区块标记（start.sh 里 --patch 参数），可识别、可替换、可删除
MARK_BEGIN = "# >>> persona-stack managed (dsh prefix) >>>"
MARK_END = "# <<< persona-stack managed (dsh prefix) <<<"
FINGERPRINT = "<!-- persona:persona-261118-v1.0@{} -->"   # {} = version from persona.yaml


def die(msg, code=1):
    print(f"[persona] ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def log(msg):
    print(f"[persona] {msg}")


# ---------- 源目录读取 ----------
def find_source_dir():
    """找源目录：优先 persona.yaml 的 id，否则固定目录名。"""
    d = os.path.join(HERE, SOURCE_DIRNAME)
    if not os.path.isdir(d):
        die(f"源目录不存在: {d}")
    return d


def read_yaml_scalars(path):
    """只读顶层简单标量（key: value），不引依赖、不解析嵌套。"""
    out = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            m = re.match(r"^([A-Za-z_][\w-]*):\s*(.+?)\s*$", line)
            if m:
                v = m.group(2).strip().strip("'\"")
                out[m.group(1)] = v
    return out


def read_parts(src):
    """读取源目录分区：返回 (version, identity文本, soul文本, [contract文本], [domain文本])。"""
    meta = read_yaml_scalars(os.path.join(src, "persona.yaml"))
    version = meta.get("version", "0.0.0")

    def _read(name, required=True):
        p = os.path.join(src, name)
        if os.path.isfile(p):
            return open(p, encoding="utf-8").read().strip()
        if required:
            die(f"{name} 缺失（最小可用要求 IDENTITY.md + soul.md + persona.yaml）")
        return ""

    identity = _read("IDENTITY.md")
    soul = _read("soul.md")

    contracts, domains = [], []
    for sub, bucket in (("contract", contracts), ("domain", domains)):
        d = os.path.join(src, sub)
        if os.path.isdir(d):
            for fn in sorted(os.listdir(d)):
                if fn.endswith(".md"):
                    bucket.append(open(os.path.join(d, fn), encoding="utf-8").read().strip())
    return version, identity, soul, contracts, domains


def flatten_source(src):
    """展平 IDENTITY.md + soul.md + contract/*.md + domain/*.md，返回 (prefix正文, version)。"""
    version, identity, soul, contracts, domains = read_parts(src)
    parts = [p for p in (identity, soul, *contracts, *domains) if p]
    body = "\n\n".join(parts)
    fp = FINGERPRINT.format(version)
    if fp not in body:
        body = f"{fp}\n{body}"
    return body, version


# ---------- openclaw 宿主（SOUL.md + AGENTS.md 托管区块落位） ----------
def _oc_block(version, body):
    """生成托管区块：BEGIN/END 标记内含指纹行，区块外内容归宿主所有。"""
    return (
        f"<!-- persona:{OC_PERSONA_ID}@{version} BEGIN -->\n"
        f"{FINGERPRINT.format(version)}\n"
        f"{body}\n"
        f"<!-- persona:{OC_PERSONA_ID}@{version} END -->"
    )


def compile_openclaw():
    """编译产物：openclaw/IDENTITY.md（身份事实）、SOUL.md（气质语气）、AGENTS.md（契约+域规格）。

    对齐 README 六文件布局的常驻层：IDENTITY/SOUL/AGENTS 均为宿主常驻加载面，
    裁决性内容只进这三个文件；TOOLS/CONTEXT/DESIGN/MEMORY 等按需层不入编译。
    """
    src = find_source_dir()
    version, identity, soul, contracts, domains = read_parts(src)
    os.makedirs(OC_DIR, exist_ok=True)
    header = (f"<!-- persona-stack 编译产物（禁止手工编辑托管区块；区块外内容归宿主所有）\n"
              f"     source: {os.path.basename(src)}  version: {version}  "
              f"generated: {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} -->")

    docs = [
        (OC_IDENTITY_ART, "IDENTITY", identity),
        (OC_SOUL_ART, "SOUL", soul),
        (OC_AGENTS_ART, "AGENTS", "\n\n".join(contracts + domains)),
    ]
    for path, title, body in docs:
        open(path, "w", encoding="utf-8").write(
            f"{header}\n\n# {title}\n\n{_oc_block(version, body)}\n")
    log(f"编译完成: IDENTITY.md + SOUL.md + AGENTS.md (version={version})")
    return OC_IDENTITY_ART, OC_SOUL_ART, OC_AGENTS_ART


def oc_apply(target, artifacts):
    """托管区块三态落位：无标记追加 / 有标记换块 / 目标不存在则整文件写入。

    返回备份 dict（路径 → 原内容或 None=原不存在），供失败还原。
    """
    backups = {}
    for art in artifacts:
        name = os.path.basename(art)
        target_path = os.path.join(target, name)
        art_text = open(art, encoding="utf-8").read()
        m = OC_BLOCK_RE.search(art_text)
        if not m:
            die(f"编译产物缺托管区块: {art}")
        new_block = m.group(0).rstrip("\n")

        if os.path.exists(target_path):
            content = open(target_path, encoding="utf-8").read()
            backups[target_path] = content
            if OC_BLOCK_RE.search(content):
                content = OC_BLOCK_RE.sub(lambda _: new_block, content, count=1)
                log(f"{target_path}: 已替换托管区块")
            else:
                content = content.rstrip() + "\n\n" + new_block + "\n"
                log(f"{target_path}: 已追加托管区块（原有内容保留）")
        else:
            backups[target_path] = None
            content = art_text
            log(f"{target_path}: 新建（首个托管区块）")
        os.makedirs(target, exist_ok=True)
        open(target_path, "w", encoding="utf-8").write(content)
    return backups


def oc_restore(backups):
    for path, old in backups.items():
        if old is None:
            if os.path.exists(path):
                os.remove(path)
                log(f"还原: 删除新建文件 {path}")
        else:
            open(path, "w", encoding="utf-8").write(old)
            log(f"还原: {path}")


def verify_openclaw(target):
    version, identity, soul, contracts, domains = read_parts(find_source_dir())
    fp = FINGERPRINT.format(version)
    checks = [
        (os.path.join(target, "IDENTITY.md"), identity),
        (os.path.join(target, "SOUL.md"), soul),
        (os.path.join(target, "AGENTS.md"), "\n\n".join(contracts + domains)),
    ]
    for path, body in checks:
        if not os.path.isfile(path):
            die(f"verify 失败：目标不存在 {path}")
        content = open(path, encoding="utf-8").read()
        if fp not in content:
            die(f"verify 失败：{path} 不含指纹 {fp}")
        key = [l.strip() for l in body.split("\n") if l.strip()][:2]
        for kl in key:
            if kl not in content:
                die(f"verify 失败：{path} 缺少人设关键行: {kl[:40]}")
    log(f"verify 通过：{target} 的 IDENTITY.md / SOUL.md / AGENTS.md 均含 {fp} 与关键行")


def uninstall_openclaw(target):
    """回滚=删整块：从三个目标文件摘除本 persona 的托管区块，其余内容保留。"""
    for name in OC_ARTIFACTS:
        p = os.path.join(target, name)
        if not os.path.isfile(p):
            continue
        content = open(p, encoding="utf-8").read()
        if not OC_BLOCK_RE.search(content):
            log(f"{p}: 无本 persona 托管区块，跳过")
            continue
        new = OC_BLOCK_RE.sub("", content)
        new = re.sub(r"\n{3,}", "\n\n", new).rstrip() + "\n"
        open(p, "w", encoding="utf-8").write(new)
        log(f"{p}: 已摘除托管区块")
    log("uninstall 完成：宿主自有内容未动")


# ---------- dsh dump 与 patch 生成 ----------
def dump_config(out=DUMP_FILE, with_patch=False):
    # 注意参数顺序：--dump-config/--profile 是 boot 层标志，必须在 web 之前；
    # --patch 同样是 boot 标志。实测可用的 dump 顺序：
    #   dsh --dump-config --profile web --patch X
    cmd = [NODE24, DSH_ENTRY, "--dump-config", "--profile", PROFILE]
    if with_patch:
        cmd += ["--patch", PATCH_FILE]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        die(f"dsh --dump-config 失败: {r.stderr[:300]}")
    open(out, "w", encoding="utf-8").write(r.stdout)
    return r.stdout


def extract_standard_block(dump_text):
    """从 dump 提取 preset-standard 的完整 entry 块（到下一个顶层 - id:）。"""
    lines = dump_text.split("\n")
    s = next((i for i, l in enumerate(lines) if l.strip() == "- id: preset-standard"), None)
    if s is None:
        die("dump 里找不到 preset-standard")
    e = next((i for i in range(s + 1, len(lines)) if lines[i].startswith("- id:")), len(lines))
    block = [l for l in lines[s:e] if not l.startswith("# == ")]
    return "\n".join(block).rstrip()


def replace_prefix_in_block(block, new_prefix):
    """在 standard 块里替换 persona 的 prefix（YAML block scalar 形式）。

    dump 中 prefix 形如：`          prefix: You are a coding agent...`（单行）。
    用 block scalar `|-` 承载多行人设，缩进 10 空格（prefix 在 config.plugins[].config 下）。
    """
    prefix_re = re.compile(r"^(\s*)prefix:.*$", re.M)
    m = prefix_re.search(block)
    if not m:
        die("standard 块里找不到 persona prefix 行")

    indent = m.group(1)
    cont_indent = indent + "  "
    scalar = "\n".join(cont_indent + ln if ln else "" for ln in new_prefix.split("\n"))
    replacement = f"{indent}prefix: |-\n{scalar}"
    new_block, n = prefix_re.subn(lambda _: replacement, block, count=1)
    if n != 1:
        die("prefix 替换数量异常")
    return new_block


def compile_patch():
    src = find_source_dir()
    prefix_body, version = flatten_source(src)
    dump_text = dump_config()
    block = extract_standard_block(dump_text)
    new_block = replace_prefix_in_block(block, prefix_body)

    out = (
        "# persona-stack 生成的 dsh patch overlay（编译产物，禁止手工编辑）\n"
        f"# source: {os.path.basename(src)}  version: {version}\n"
        f"# generated: {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        "# 由 start.sh 通过 --patch 挂载；uninstall = 摘掉该参数。\n"
        f"{new_block}\n"
    )
    os.makedirs(DSH_PATCH_DIR, exist_ok=True)
    open(PATCH_FILE, "w", encoding="utf-8").write(out)
    log(f"编译完成: {PATCH_FILE} ({len(new_block.splitlines())} 行, version={version})")
    return PATCH_FILE


# ---------- start.sh 托管区块 ----------
def read_start():
    return open(START_SH, encoding="utf-8").read()


def write_start(text):
    shutil.copy2(START_SH, START_SH + ".bak-persona-" + dt.datetime.now().strftime("%Y%m%d-%H%M%S"))
    open(START_SH, "w", encoding="utf-8").write(text)


def patch_start_add():
    s = read_start()
    if MARK_BEGIN in s:
        # 已挂载：更新 patch 路径行（本版路径固定，只需确认）
        return False
    marker = f"{MARK_BEGIN}\nDSH_PERSONA_PATCH=\"{PATCH_FILE}\"\nPERSONA_PATCH_ARG=\"--patch $DSH_PERSONA_PATCH\"\n{MARK_END}\n"
    # 插到 dsh 启动 nohup 行之前
    anchor = 'nohup "$NODE24" "$DSH_ENTRY" web --no-open --port 3080 \\\n  --trusted-host "$TRUSTED_HOST" > /tmp/dsh.log 2>&1 &'
    if anchor not in s:
        die("start.sh 里找不到 dsh 启动锚点，拒绝盲改")
    # --patch 是 launcher 标志，必须紧跟 profile 名（web）之后、app 参数之前。
    # 放最后会被 web app 当成未知选项 → dsh 起不来（实测）。
    new_anchor = marker + 'nohup "$NODE24" "$DSH_ENTRY" web $PERSONA_PATCH_ARG --no-open --port 3080 \\\n  --trusted-host "$TRUSTED_HOST" > /tmp/dsh.log 2>&1 &'
    write_start(s.replace(anchor, new_anchor, 1))
    log("start.sh 已挂载 persona patch overlay（托管区块）")
    return True


def patch_start_remove():
    s = read_start()
    if MARK_BEGIN not in s:
        log("start.sh 无 persona 托管区块，无需摘除")
        return
    new = re.sub(rf"{re.escape(MARK_BEGIN)}.*?{re.escape(MARK_END)}\n", "", s, flags=re.S)
    new = new.replace('web $PERSONA_PATCH_ARG --no-open', 'web --no-open')
    write_start(new)
    log("start.sh 已摘除 persona patch overlay")


# ---------- 重启与校验 ----------
def restart_dsh():
    env = dict(os.environ, FORCE_RESTART="1", PORT="8080")
    # start.sh 自己会阻塞等 token 并写盘（最多 60s），这里同步等它返回即可。
    r = subprocess.run(["bash", START_SH], cwd="/workspace/dsh-app", env=env,
                       capture_output=True, text=True, timeout=120)
    log("dsh 重启完成")
    if r.returncode != 0:
        # start.sh 非 0 = 启动失败（token 未生成 / 端口冲突），带错误回滚
        raise RuntimeError(f"start.sh exit {r.returncode}: {(r.stderr or r.stdout)[-400:]}")
    if not (os.path.exists("/tmp/dsh-token") and os.path.getsize("/tmp/dsh-token") > 0):
        raise RuntimeError("重启后 token 为空")


def verify():
    """校验挂载 patch 后的有效配置里 standard.prefix 含源指纹且内容一致。

    实际 dsh 启动经 start.sh 的 --patch 挂载本产物，故 verify 必须同样带 --patch，
    否则读的是裸配置、必然不含指纹（上一版失败根因）。
    """
    src = find_source_dir()
    prefix_body, version = flatten_source(src)
    dump_text = dump_config(with_patch=True)
    block = extract_standard_block(dump_text)
    fp = FINGERPRINT.format(version)
    if fp not in block:
        die(f"verify 失败：dump 的 standard 段不含指纹 {fp}")
    # 取 prefix 块内容做关键行比对（首行 + 末行）
    key_lines = [l.strip() for l in prefix_body.split("\n") if l.strip()][:2]
    for kl in key_lines:
        if kl and kl not in block:
            die(f"verify 失败：standard 段缺少人设关键行: {kl[:40]}")
    # 证明运行中的 dsh 真的带 --patch 启动了（不是只有 patch 文件正确）
    p = subprocess.run(["pgrep", "-f", "dsh/lib/bin.js web"], capture_output=True, text=True)
    running_ok = False
    for pid in p.stdout.split():
        try:
            cmdline = open(f"/proc/{pid}/cmdline", "rb").read().replace(b"\0", b" ").decode()
            if "--patch" in cmdline and "persona.patch.yml" in cmdline:
                running_ok = True
                break
        except OSError:
            continue
    if not running_ok:
        die("verify 失败：运行中的 dsh 进程未带 persona --patch 参数")
    log(f"verify 通过：standard.prefix 含指纹 + 人设关键行，且运行进程已挂载 patch（version={version}）")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["compile", "install", "verify", "uninstall"])
    ap.add_argument("--host", default="dsh")
    ap.add_argument("--target", default=None, help="openclaw 落位目标 workspace 目录")
    args = ap.parse_args()

    if args.cmd == "compile":
        if args.host == "openclaw":
            compile_openclaw()
        else:
            compile_patch()
    elif args.cmd == "verify":
        if args.host == "openclaw":
            verify_openclaw(args.target or OC_DEFAULT_TARGET)
        else:
            verify()
    elif args.cmd == "install":
        if args.host == "openclaw":
            target = args.target or OC_DEFAULT_TARGET
            compile_openclaw()
            backups = oc_apply(target, [OC_IDENTITY_ART, OC_SOUL_ART, OC_AGENTS_ART])
            try:
                verify_openclaw(target)
            except SystemExit:
                log("install 失败，还原目标文件...")
                oc_restore(backups)
                die("openclaw install 失败已还原")
            return
        if args.host != "dsh":
            die("支持的 host: dsh / openclaw")
        compile_patch()
        patch_start_add()
        # 备份用于回滚
        backup = DUMP_FILE + ".pre-install"
        shutil.copy2(DUMP_FILE, backup)
        try:
            restart_dsh()
            verify()
        except (SystemExit, RuntimeError) as e:
            log(f"install 失败（{e}），执行回滚...")
            patch_start_remove()
            try:
                restart_dsh()
                log("回滚完成：dsh 已恢复原样")
            except Exception as re:
                die(f"回滚重启也失败，请人工检查 start.sh: {re}")
            die("install 失败已回滚")
    elif args.cmd == "uninstall":
        if args.host == "openclaw":
            uninstall_openclaw(args.target or OC_DEFAULT_TARGET)
            return
        patch_start_remove()
        restart_dsh()
        log("uninstall 完成：dsh 已恢复原 persona prefix")


if __name__ == "__main__":
    main()
