#!/usr/bin/env python3
"""verify.py — bundles 完整性闸门（机器层）。

独立于 persona.py，可重复执行：
  1. 逐 bundle 重算内容 hash，与目录名比对——改已发布快照必然被抓；
  2. index.json 与磁盘 bundle 双向对账（磁盘有而 index 无 / index 有而磁盘无）；
  3. 顺带校验 bindings 引用的 bundle 存在。

CI（.github/workflows/verify.yml）与本地同跑这一份逻辑。
exit 0 = 注册表干净；非 0 = 有污染，先修再推。
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from persona import canonical_hash, parse_manifest, BUNDLES_DIR, BINDINGS_FILE

REPO = Path(__file__).resolve().parent


def fail(msgs):
    print("verify: FAIL")
    for m in msgs:
        print(f"  ✗ {m}")
    sys.exit(1)


def main() -> int:
    problems = []

    bundle_dirs = sorted(p for p in BUNDLES_DIR.iterdir() if p.is_dir())
    checked = 0
    for pid_dir in bundle_dirs:
        pid = pid_dir.name
        idx_path = pid_dir / "index.json"
        index_hashes = []
        if idx_path.is_file():
            idx = json.loads(idx_path.read_text(encoding="utf-8"))
            index_hashes = [b["hash"] for b in idx.get("bundles", [])]
        else:
            problems.append(f"{pid}: missing index.json")

        disk_hashes = []
        for hdir in sorted(p for p in pid_dir.iterdir() if p.is_dir() and p.name != "_archive"):
            h = hdir.name
            disk_hashes.append(h)
            mf = hdir / "persona.yaml"
            if not mf.is_file():
                problems.append(f"{pid}@{h}: missing persona.yaml")
                continue
            manifest_bytes = mf.read_bytes()
            m = parse_manifest(manifest_bytes.decode("utf-8"))
            files = []
            for f in m.get("files") or []:
                fp = hdir / f["name"]
                if not fp.is_file():
                    problems.append(f"{pid}@{h}: missing file {f['name']}")
                    continue
                files.append((f["name"], fp.read_bytes()))
            if not files:
                problems.append(f"{pid}@{h}: manifest lists no files")
                continue
            recomputed = canonical_hash(manifest_bytes, files)
            if recomputed != h:
                problems.append(
                    f"{pid}@{h}: HASH MISMATCH — dir name says {h}, content hashes to "
                    f"{recomputed}; a published bundle was modified after the fact"
                )
            checked += 1

        for h in index_hashes:
            if h not in disk_hashes:
                problems.append(f"{pid}: index lists {h} but bundle dir absent")

    # bindings reference existing bundles
    if BINDINGS_FILE.is_file():
        data = json.loads(BINDINGS_FILE.read_text(encoding="utf-8-sig"))
        for e in data.get("bindings", []):
            pid, h = e.get("persona"), e.get("hash")
            if not (BUNDLES_DIR / str(pid) / str(h)).is_dir():
                problems.append(f"binding {e.get('slot')}: references missing bundle {pid}@{h}")

    if problems:
        fail(problems)
    print(f"verify: OK — {checked} bundle(s) hash-verified, index/bindings consistent")
    return 0


if __name__ == "__main__":
    sys.exit(main())
