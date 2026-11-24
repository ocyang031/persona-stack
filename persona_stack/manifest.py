"""Source face: the persona.yaml manifest parser and the source linter."""
from __future__ import annotations

import re
from pathlib import Path

from .util import die

ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
ANCHOR_RE = re.compile(r"\(([A-Z]+_[A-Z0-9_]+)\)")
PLACEHOLDER_RE = re.compile(r"\{\{([A-Za-z][A-Za-z0-9_]*)\}\}")


def _kv(s: str) -> "tuple[str, str]":
    k, _, v = s.partition(":")
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        v = v[1:-1]
    return k.strip(), v


def parse_manifest(text: str) -> dict:
    """Tiny YAML subset: top-level scalars, one list of flat dicts (files)."""
    data: dict = {}
    list_key, item = None, None
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if raw.startswith(" ") or raw.startswith("- "):
            if list_key is None:
                continue
            s = raw.strip()
            if s.startswith("- "):
                item = {}
                data[list_key].append(item)
                k, v = _kv(s[2:])
                item[k] = v
            elif item is not None:
                k, v = _kv(s)
                item[k] = v
            continue
        k, v = _kv(raw)
        if v == "":
            data[k] = []
            list_key, item = k, None
        elif v == "[]":
            data[k] = []
            list_key, item = None, None
        else:
            data[k] = v
            list_key, item = None, None
    return data


def load_source(src: Path):
    mf = src / "persona.yaml"
    if not mf.is_file():
        die(f"source manifest not found: {mf}")
    manifest_bytes = mf.read_bytes()
    m = parse_manifest(manifest_bytes.decode("utf-8"))
    files: "list[tuple[str, str, bytes]]" = []
    for f in m.get("files") or []:
        name, load = f.get("name"), f.get("load", "on-demand")
        p = src / name
        if not p.is_file():
            die(f"manifest lists missing file: {p}")
        files.append((name, load, p.read_bytes()))
    return m, manifest_bytes, files


def validate_source(src: Path):
    m, manifest_bytes, files = load_source(src)
    errors: "list[str]" = []
    warnings: "list[str]" = []

    if not ID_RE.match(str(m.get("id", ""))):
        errors.append(f"id invalid or missing: {m.get('id')!r} (want ^[a-z0-9][a-z0-9-]*$)")
    if not m.get("version"):
        errors.append("version missing in persona.yaml")
    if not files:
        errors.append("manifest lists no files")
    if not manifest_bytes.decode("utf-8", "replace").strip():
        errors.append("persona.yaml is empty")

    for name, load, content in files:
        if load not in ("always-on", "session-start", "on-demand"):
            errors.append(f"{name}: unknown load hint {load!r}")
        try:
            content.decode("utf-8")
        except UnicodeDecodeError:
            errors.append(f"{name}: not valid utf-8")
        if not content.endswith(b"\n"):
            errors.append(f"{name}: must end with a newline (byte-exact envelopes need it)")
        if b"\r" in content:
            errors.append(f"{name}: contains CR — the dsh prefix rides a YAML scalar, and YAML "
                          f"normalizes CRLF; byte-exact hosts need LF-only sources")

    # anchor registry sync: anchors in IDENTITY/SOUL vs CONTEXT slot table
    by_name = {name: content for name, _, content in files}
    anchors: "set[str]" = set()
    for name in ("IDENTITY.md", "SOUL.md"):
        if name in by_name:
            anchors |= set(ANCHOR_RE.findall(by_name[name].decode("utf-8")))
    ctx_rows: "set[str]" = set()
    if "CONTEXT.md" in by_name:
        text = by_name["CONTEXT.md"].decode("utf-8")
        match = re.search(r"## Slot registry.*?(?=\n## |\Z)", text, re.S)
        if match:
            ctx_rows = set(re.findall(r"^\|\s*([A-Z]+_[A-Z0-9_]+)\s*\|", match.group(0), re.M))
    missing = anchors - ctx_rows
    extra = ctx_rows - anchors
    if missing:
        errors.append(f"anchors missing from CONTEXT slot registry: {sorted(missing)}")
    if extra:
        errors.append(f"CONTEXT slot registry rows without a live anchor: {sorted(extra)}")

    # bare "Section N" refs outside AGENTS.md (cross-file refs must be by name)
    for name, _, content in files:
        if name != "AGENTS.md" and re.search(r"Section \d|§\d", content.decode("utf-8")):
            warnings.append(f"{name}: bare 'Section N' reference — use a section/file name instead")

    # unresolved placeholders when no vars in play is fine at pack time; just report
    for name, _, content in files:
        found = set(PLACEHOLDER_RE.findall(content.decode("utf-8")))
        if found:
            warnings.append(f"{name}: placeholders present {sorted(found)} — bind with --var to fill")

    return m, manifest_bytes, files, errors, warnings
