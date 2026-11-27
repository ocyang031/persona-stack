#!/usr/bin/env python3
"""dsh-bridge · persona.prefix.txt → dsh patch overlay（M2 宿主接线，多设备版）。

从 bindings.json 读取所有 host=dsh 的绑定（按 slot/device 标识区分设备），
再用本机 targets.local.json 解析每个 slot 的落点；对每条绑定：物化产物
（reconcile 已完成）中的 persona.prefix.txt 编译进 dsh patch overlay，供
start.sh 的 --patch 挂载。编译逻辑与旧架构（99fa1f9）一致。

  用法：
    dsh-bridge.py [slot ...]        # 无参数 = 处理全部 host=dsh 的绑定

  每个产物 patch 头部携带接线标识：slot / device / persona@hash / target，
  使多台设备的接线结果可区分、互不覆盖（slot 命名约定：dsh.web.<device>）。

  自校验：反缩进后与 persona.prefix.txt 逐字节比对，不一致拒绝写盘。
"""
import json
import os
import re
import subprocess
import sys

REPO = "/root/001_OcLedger/100_Works/persona-stack"
BINDINGS = os.path.join(REPO, "bindings.json")
TARGETS = os.path.join(REPO, "targets.local.json")
NODE24 = "/root/.nvm/versions/node/v24.21.0/bin/node"
DSH_ENTRY = "/workspace/dsh-app/node_modules/@deepseek-ai/dsh/lib/bin.js"
PROFILE = "web"


def dump_config():
    cmd = [NODE24, DSH_ENTRY, "--dump-config", "--profile", PROFILE]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"[bridge] ERROR: dsh --dump-config failed: {r.stderr[:300]}")
    return r.stdout


def extract_standard_block(dump_text):
    lines = dump_text.split("\n")
    s = next((i for i, l in enumerate(lines) if l.strip() == "- id: preset-standard"), None)
    if s is None:
        sys.exit("[bridge] ERROR: preset-standard not found in dump")
    e = next((i for i in range(s + 1, len(lines)) if lines[i].startswith("- id:")), len(lines))
    block = [l for l in lines[s:e] if not l.startswith("# == ")]
    return "\n".join(block).rstrip()


def replace_prefix(block, new_prefix):
    prefix_re = re.compile(r"^(\s*)prefix:.*$", re.M)
    m = prefix_re.search(block)
    if not m:
        sys.exit("[bridge] ERROR: persona prefix line not found in standard block")
    indent, cont = m.group(1), m.group(1) + "  "
    scalar = "\n".join(cont + ln if ln else "" for ln in new_prefix.split("\n"))
    new_block, n = prefix_re.subn(lambda _: f"{indent}prefix: |-\n{scalar}", block, count=1)
    if n != 1:
        sys.exit("[bridge] ERROR: prefix replacement count != 1")
    return new_block, cont


def compile_binding(e, target, dump_text):
    slot = e["slot"]
    pid, h = e["persona"], e["hash"]
    device = e.get("device") or "(no device tag)"
    prefix_txt = os.path.join(target, "persona.prefix.txt")
    patch_file = os.path.join(target, "persona.patch.yml")
    if not os.path.isfile(prefix_txt):
        print(f"[bridge] SKIP {slot}: {prefix_txt} missing — run: persona.py reconcile {slot}")
        return False
    prefix_body = open(prefix_txt, encoding="utf-8").read()
    if prefix_body.endswith("\n"):
        prefix_body = prefix_body[:-1]

    block = extract_standard_block(dump_text)
    new_block, cont = replace_prefix(block, prefix_body)

    # 接线标识：slot / device / persona@hash / target —— 设备可区分，产物不串线
    out = (
        "# dsh-bridge generated patch overlay (compiled from persona.prefix.txt; do not edit)\n"
        f"# wiring: slot={slot}  device={device}\n"
        f"# source: persona:{pid}@{h}  target={target}\n"
        f"{new_block}\n"
    )

    # 自校验：反缩进 block scalar 与 prefix.txt 逐字节一致
    lines = out.split("\n")
    start = next(i for i, l in enumerate(lines) if l.strip() == "prefix: |-")
    body = []
    cont_prefix = " " * len(cont)
    for ln in lines[start + 1:]:
        if ln == "" or ln.startswith(cont_prefix) or ln.strip() == "":
            body.append(ln[len(cont_prefix):] if ln.startswith(cont_prefix) else "")
        else:
            break
    decoded = "\n".join(body).rstrip("\n")
    if decoded != prefix_body:
        sys.exit(f"[bridge] ERROR: {slot} roundtrip mismatch — prefix.txt vs patch scalar differ")

    os.makedirs(target, exist_ok=True)
    open(patch_file, "w", encoding="utf-8").write(out)
    print(f"[bridge] OK: {slot} (device={device}) → {patch_file} "
          f"({len(new_block.splitlines())} lines, persona:{pid}@{h}, roundtrip byte-exact)")
    return True


def main():
    slots = set(sys.argv[1:])
    if not os.path.isfile(BINDINGS):
        sys.exit(f"[bridge] ERROR: {BINDINGS} missing")
    data = json.load(open(BINDINGS, encoding="utf-8-sig"))  # utf-8-sig: tolerate BOM
    targets = json.load(open(TARGETS, encoding="utf-8-sig")) if os.path.isfile(TARGETS) else {}
    entries = [b for b in data.get("bindings", []) if b.get("host") == "dsh"]
    if slots:
        entries = [b for b in entries if b["slot"] in slots]
    if not entries:
        print("[bridge] no host=dsh bindings match" + (f" {sorted(slots)}" if slots else "") + " — nothing to do")
        return
    unresolved = [b["slot"] for b in entries if b["slot"] not in targets]
    for slot in unresolved:
        print(f"[bridge] SKIP {slot}: no local target in {TARGETS} (bound to another device?)")
    entries = [b for b in entries if b["slot"] in targets]
    if not entries:
        print("[bridge] nothing to compile on this device")
        return
    dump_text = dump_config()
    ok = sum(compile_binding(e, targets[e["slot"]], dump_text) for e in entries)
    print(f"[bridge] done: {ok}/{len(entries)} binding(s) compiled")


if __name__ == "__main__":
    main()
