"""Source face: the persona.yaml manifest parser and the source linter."""
from __future__ import annotations

import re
from pathlib import Path

from .util import die

ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
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
    files: "list[tuple[str, bytes]]" = []
    for f in m.get("files") or []:
        name = f.get("name")
        if not name or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*\.md", name):
            die(f"invalid persona file name: {name!r}")
        p = src / name
        if not p.is_file():
            die(f"manifest lists missing file: {p}")
        files.append((name, p.read_bytes()))
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

    names = {name for name, _ in files}
    if len(names) != len(files):
        errors.append("manifest lists duplicate files")
    if any("load" in entry for entry in m.get("files", [])):
        errors.append("persona.yaml: remove load hints; select modules with bind --include")

    module_names = names | ({"CONTEXT.md"} if m.get("id") == "xiaoxiao" else set())
    for name, content in files:
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            errors.append(f"{name}: not valid utf-8")
            continue
        if not text.strip():
            errors.append(f"{name}: prompt body is empty")
        if content.startswith(b"\xef\xbb\xbf") or text.lstrip().startswith("---\n"):
            errors.append(f"{name}: use UTF-8 without BOM or frontmatter")
        if re.search(r"^#{1,6}\s+(Positioning|Boundary Definition|Slot registry)\b", text, re.M | re.I):
            errors.append(f"{name}: move maintenance headings to DESIGN.md or README.md")
        if re.search(r"<!--\s*persona:", text):
            errors.append(f"{name}: persona envelope markers are reserved for adapters")
        refs = sorted(module for module in module_names if re.search(
            rf"(?<![\w.-]){re.escape(module)}(?![\w-])", text, re.I
        ))
        if refs:
            errors.append(f"{name}: remove module filename references: {', '.join(refs)}")
        if not content.endswith(b"\n"):
            errors.append(f"{name}: must end with a newline (byte-exact envelopes need it)")
        if b"\r" in content:
            errors.append(f"{name}: contains CR; byte-exact hosts need LF-only sources")

        found = set(PLACEHOLDER_RE.findall(text))
        if found:
            warnings.append(f"{name}: placeholders present {sorted(found)} — bind with --var to fill")

    return m, manifest_bytes, files, errors, warnings
