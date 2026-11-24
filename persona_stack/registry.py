"""Registry face: content hash, immutable bundle index, bundle loading, render."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .manifest import PLACEHOLDER_RE, parse_manifest
from .paths import BUNDLES_DIR, HASH_LEN
from .util import die


def canonical_hash(manifest_bytes: bytes, files: "list[tuple[str, bytes]]") -> str:
    h = hashlib.sha256(b"persona-bundle-v1\n")
    h.update(manifest_bytes)
    h.update(b"\x00")
    for name, content in files:
        h.update(name.encode())
        h.update(b"\x00")
        h.update(len(content).to_bytes(8, "big"))
        h.update(content)
    return h.hexdigest()[:HASH_LEN]


def index_file(pid: str) -> Path:
    return BUNDLES_DIR / pid / "index.json"


def load_index(pid: str) -> dict:
    p = index_file(pid)
    if p.is_file():
        return json.loads(p.read_text(encoding="utf-8"))
    return {"persona": pid, "bundles": []}


def save_index(pid: str, idx: dict) -> None:
    index_file(pid).parent.mkdir(parents=True, exist_ok=True)
    index_file(pid).write_text(json.dumps(idx, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def resolve_ref(ref: str) -> "tuple[str, str]":
    if "@" in ref:
        pid, h = ref.split("@", 1)
        return pid, h
    idx = load_index(ref)
    if not idx["bundles"]:
        die(f"persona {ref!r} has no packed bundles yet")
    return ref, idx["bundles"][-1]["hash"]


def load_bundle(pid: str, h: str) -> "tuple[bytes, dict[str, bytes], dict[str, str]]":
    bdir = BUNDLES_DIR / pid / h
    if not bdir.is_dir():
        die(f"bundle {pid}@{h} not found in local registry ({bdir}) — pack it or git pull")
    manifest_bytes = (bdir / "persona.yaml").read_bytes()
    m = parse_manifest(manifest_bytes.decode("utf-8"))
    files: "dict[str, bytes]" = {}
    loads: "dict[str, str]" = {}
    for f in m["files"]:
        name, load = f["name"], f.get("load", "on-demand")
        files[name] = (bdir / name).read_bytes()
        loads[name] = load
    return manifest_bytes, files, loads


def render_files(files: dict, variables: dict) -> dict:
    if not variables:
        return files
    out = {}
    for name, content in files.items():
        text = content.decode("utf-8")
        for k, v in variables.items():
            text = text.replace("{{" + k + "}}", v)
        left = PLACEHOLDER_RE.findall(text)
        if left:
            raise KeyError(
                f"render incomplete: {name} still carries placeholders {sorted(set(left))} "
                f"(missing vars: {sorted(set(p[len('PERSON_'):] if p.startswith('PERSON_') else p for p in left))}) — "
                "fill every placeholder or pin this binding"
            )
        out[name] = text.encode("utf-8")
    return out


def derived_hash(manifest_bytes: bytes, files: dict) -> str:
    # files preserves the manifest order (dict insertion order), so a render
    # with no substitutions yields exactly the bundle hash.
    return canonical_hash(manifest_bytes, list(files.items()))
