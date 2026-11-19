#!/usr/bin/env python3
"""dsh-bridge · persona.prefix.txt → dsh patch overlay（M2 宿主接线）。

registry+reconciler 架构中 dsh 适配器只物化 persona.prefix.txt；
本桥接负责最后一公里：把 prefix 文本编译进 dsh 的 patch overlay，
供 start.sh 的 --patch 挂载。编译逻辑与旧架构（99fa1f9）逐行一致。

  - dump 当前有效配置（--dump-config --profile web，不带 patch）
  - 提取 preset-standard 完整 entry（浅覆盖语义要求保留全部插件）
  - 将 persona 的 prefix 行替换为 block scalar（内容 = persona.prefix.txt）
  - 写 <target>/persona.patch.yml
  - 自校验：反缩进后与 persona.prefix.txt 逐字节比对
"""
import os
import re
import subprocess
import sys

REPO = "/root/001_OcLedger/100_Works/persona-stack"
TARGET = "/workspace/dsh-app/persona"      # 与 bindings.json 的 dsh.web target 一致
PREFIX_TXT = os.path.join(TARGET, "persona.prefix.txt")
PATCH_FILE = os.path.join(TARGET, "persona.patch.yml")
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


def main():
    if not os.path.isfile(PREFIX_TXT):
        sys.exit(f"[bridge] ERROR: {PREFIX_TXT} missing — run: persona.py reconcile dsh.web")
    prefix_body = open(PREFIX_TXT, encoding="utf-8").read()
    # strip a single trailing newline so block scalar |- keeps content exact
    if prefix_body.endswith("\n"):
        prefix_body = prefix_body[:-1]

    block = extract_standard_block(dump_config())
    new_block, cont = replace_prefix(block, prefix_body)

    out = (
        "# dsh-bridge generated patch overlay (compiled from persona.prefix.txt; do not edit)\n"
        f"# source: persona:xiaoxiao@c29bd653519cacb8 (slot dsh.web)\n"
        f"{new_block}\n"
    )
    os.makedirs(TARGET, exist_ok=True)
    open(PATCH_FILE, "w", encoding="utf-8").write(out)

    # 自校验：反缩进 block scalar 与 prefix.txt 逐字节一致
    lines = out.split("\n")
    start = next(i for i, l in enumerate(lines) if l.strip() == "prefix: |-")
    body, cont_prefix = [], " " * len(cont)
    for ln in lines[start + 1:]:
        if ln == "" or ln.startswith(cont_prefix) or ln.strip() == "":
            body.append(ln[len(cont):] if ln.startswith(cont_prefix) else "")
        else:
            break
    decoded = "\n".join(body).rstrip("\n")
    if decoded != prefix_body:
        sys.exit("[bridge] ERROR: roundtrip mismatch — prefix.txt vs patch scalar differ")
    print(f"[bridge] OK: {PATCH_FILE} ({len(new_block.splitlines())} lines, roundtrip byte-exact)")


if __name__ == "__main__":
    main()
