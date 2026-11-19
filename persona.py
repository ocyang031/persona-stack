#!/usr/bin/env python3
"""persona — registry + reconciler for the five-file persona set.

Implements DESIGN.md v1: the five files ARE the final form. This tool never
compiles or reshapes them. It snapshots them into an immutable, content-hashed
bundle directory (the registry), records desired state in bindings.json, and
converges host-side copies to it (the reconciler), reporting drift.

Host adapters (seam ①): file/openclaw (managed-block envelope), dsh (single
prefix with self-describing file markers). Registry backend (seam ②): a git
repo — this one. Triggers (seam ③): manual CLI or the dsh start.sh hook.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

REPO = Path(__file__).resolve().parent
BUNDLES_DIR = REPO / "bundles"
BINDINGS_FILE = REPO / "bindings.json"
RECEIPTS_DIR = REPO / "receipts"
HASH_LEN = 16
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
ANCHOR_RE = re.compile(r"\(([A-Z]+_[A-Z0-9_]+)\)")
PLACEHOLDER_RE = re.compile(r"\{\{([A-Za-z][A-Za-z0-9_]*)\}\}")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def die(msg: str) -> "None":
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------- manifest

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


# ---------------------------------------------------------------- validate

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


# ---------------------------------------------------------------- pack

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


# ---------------------------------------------------------------- adapters

def block_regex(pid: str) -> "re.Pattern[bytes]":
    esc = re.escape(pid.encode("utf-8"))
    return re.compile(
        rb"<!-- persona:" + esc + rb"@\S+ BEGIN -->\n.*?\n<!-- persona:"
        + esc + rb"@\S+ END -->\n?",
        re.S,
    )


def inner_regex(pid: str) -> "re.Pattern[bytes]":
    esc = re.escape(pid.encode("utf-8"))
    return re.compile(
        rb"<!-- persona:" + esc + rb"@\S+ BEGIN -->\n(.*?)\n<!-- persona:"
        + esc + rb"@\S+ END -->",
        re.S,
    )


class FileAdapter:
    """openclaw-style host: each file lives inside a managed-block envelope.
    All placement is byte-level (no newline translation, no decode round
    trips) so the host file lands byte-exact to the bundle content."""
    name = "file"
    aliases = ("openclaw",)

    @staticmethod
    def place(target: Path, pid: str, h: str, files: dict, loads: dict) -> None:
        target.mkdir(parents=True, exist_ok=True)
        for name, content in files.items():
            p = target / name
            block = b"".join((
                f"<!-- persona:{pid}@{h} BEGIN -->\n".encode("utf-8"),
                content,
                f"<!-- persona:{pid}@{h} END -->\n".encode("utf-8"),
            ))
            if not p.exists():
                p.write_bytes(f"# persona:{pid}@{h} managed file\n\n".encode("utf-8") + block)
                continue
            data = p.read_bytes()
            pat = block_regex(pid)
            if pat.search(data):
                p.write_bytes(pat.sub(lambda _m: block, data))
            else:
                p.write_bytes(data.rstrip(b"\n") + b"\n\n" + block)

    @staticmethod
    def readback(target: Path, pid: str, names: list, loads: dict):
        if not target.is_dir():
            return None
        out: "dict[str, bytes]" = {}
        pat = inner_regex(pid)
        for name in names:
            p = target / name
            if not p.is_file():
                continue
            m = pat.search(p.read_bytes())
            if m:
                out[name] = m.group(1) + b"\n"
        return out

    @staticmethod
    def remove(target: Path, pid: str) -> None:
        if not target.is_dir():
            return
        pat = block_regex(pid)
        for p in target.glob("*"):
            if not p.is_file():
                continue
            data = p.read_bytes()
            if pat.search(data):
                new = re.sub(rb"\n{3,}", b"\n\n", pat.sub(b"", data)).strip(b"\n")
                if new:
                    p.write_bytes(new + b"\n")
                else:
                    p.unlink()


DSH_PREFIX_LOADS = ("always-on", "session-start")


def dsh_prefix(pid: str, h: str, files: dict, loads: dict) -> str:
    """One self-describing prefix artifact: header + in-prefix files in
    manifest order, each behind a `<!-- persona:file NAME -->` marker so
    readback can split byte-exactly."""
    parts = [f"<!-- persona:{pid}@{h} -->\n"]
    for name, content in files.items():
        if loads.get(name) in DSH_PREFIX_LOADS:
            parts.append(f"<!-- persona:file {name} -->\n")
            parts.append(content.decode("utf-8"))
    return "".join(parts)


class DshAdapter:
    """dsh-style host: the system prompt is one stable prefix region, so the
    session-start distinction collapses — everything session-start-or-stronger
    is concatenated into one self-describing prefix artifact; on-demand files
    are delivered as plain workspace copies the agent reaches by pointer."""
    name = "dsh"
    PREFIX = "persona.prefix.txt"
    IN_PREFIX = DSH_PREFIX_LOADS

    @staticmethod
    def place(target: Path, pid: str, h: str, files: dict, loads: dict) -> None:
        target.mkdir(parents=True, exist_ok=True)
        (target / DshAdapter.PREFIX).write_bytes(dsh_prefix(pid, h, files, loads).encode("utf-8"))
        for name, content in files.items():
            if loads.get(name) not in DshAdapter.IN_PREFIX:
                (target / name).write_bytes(content)

    @staticmethod
    def readback(target: Path, pid: str, names: list, loads: dict):
        if not target.is_dir():
            return None
        out: "dict[str, bytes]" = {}
        pfx = target / DshAdapter.PREFIX
        if pfx.is_file():
            pieces = re.split(rb"<!-- persona:file (.+?) -->\n", pfx.read_bytes())
            # pieces: [header, name1, body1, name2, body2, ...]
            for i in range(1, len(pieces) - 1, 2):
                out[pieces[i].decode("utf-8")] = pieces[i + 1]
        for name in names:
            if loads.get(name) not in DshAdapter.IN_PREFIX:
                p = target / name
                if p.is_file():
                    out[name] = p.read_bytes()
        return out

    @staticmethod
    def remove(target: Path, pid: str) -> None:
        if not target.is_dir():
            return
        pfx = target / DshAdapter.PREFIX
        if pfx.is_file():
            pfx.unlink()


ADAPTERS: dict = {FileAdapter.name: FileAdapter, DshAdapter.name: DshAdapter}
for a in (FileAdapter, DshAdapter):
    for alias in getattr(a, "aliases", ()):  # type: ignore[attr-defined]
        ADAPTERS[alias] = a


def get_adapter(host: str):
    if host not in ADAPTERS:
        die(f"unknown host adapter {host!r} (have: {', '.join(sorted(ADAPTERS))})")
    return ADAPTERS[host]


# ---------------------------------------------------------------- render

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


# ---------------------------------------------------------------- bindings

def load_bindings() -> dict:
    if BINDINGS_FILE.is_file():
        # utf-8-sig: tolerate Windows-side edits that leave a BOM
        return json.loads(BINDINGS_FILE.read_text(encoding="utf-8-sig"))
    return {"bindings": []}


def save_bindings(data: dict) -> None:
    BINDINGS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def find_binding(data: dict, slot: str) -> "dict | None":
    for b in data["bindings"]:
        if b["slot"] == slot:
            return b
    return None


# ---------------------------------------------------------------- receipts

def receipt(slot: str, **payload) -> None:
    RECEIPTS_DIR.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", slot)
    payload = {"ts": now_iso(), "slot": slot, **payload}
    with open(RECEIPTS_DIR / f"{safe}.jsonl", "a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------- commands

def cmd_validate(args) -> int:
    src = Path(args.source).resolve()
    m, _, files, errors, warnings = validate_source(src)
    for w in warnings:
        print(f"warn: {w}")
    if errors:
        for e in errors:
            print(f"error: {e}")
        print(f"validate: FAIL ({len(errors)} errors, {len(warnings)} warnings) — {src}")
        return 1
    print(f"validate: OK — persona {m.get('id')}@{m.get('version')}, {len(files)} files, "
          f"{len(warnings)} warnings — {src}")
    return 0


def cmd_pack(args) -> int:
    src = Path(args.source).resolve()
    m, manifest_bytes, files, errors, warnings = validate_source(src)
    for w in warnings:
        print(f"warn: {w}")
    if errors:
        for e in errors:
            print(f"error: {e}")
        die("pack: source failed validation; fix the five files first")
    pid = m["id"]
    plain = [(name, content) for name, _, content in files]
    h = canonical_hash(manifest_bytes, plain)
    bdir = BUNDLES_DIR / pid / h
    if bdir.exists():
        same = (bdir / "persona.yaml").read_bytes() == manifest_bytes and all(
            (bdir / name).read_bytes() == content for name, content in plain
        )
        if same:
            print(f"pack: idempotent — {pid}@{h} already in registry")
            return 0
        die(f"pack: hash collision at {bdir} with different content")
    bdir.mkdir(parents=True)
    (bdir / "persona.yaml").write_bytes(manifest_bytes)
    for name, content in plain:
        (bdir / name).write_bytes(content)
    idx = load_index(pid)
    if not any(e["hash"] == h for e in idx["bundles"]):
        idx["bundles"].append(
            {"version": m["version"], "hash": h, "packed_at": now_iso(), "source": str(src)}
        )
    save_index(pid, idx)
    print(f"pack: {pid}@{h} (v{m['version']}, {len(plain)} files) → {bdir}")
    return 0


def cmd_publish(args) -> int:
    refs = []
    for pid_dir in sorted(BUNDLES_DIR.glob("*")) if BUNDLES_DIR.is_dir() else []:
        idx = load_index(pid_dir.name)
        if idx["bundles"]:
            refs.append(f"{pid_dir.name}@{idx['bundles'][-1]['hash']}")
    msg = args.msg or ("registry: " + (", ".join(refs) if refs else "(empty)"))
    for cmd in (
        ["add", "-A"],
        ["commit", "-m", msg],
    ):
        r = subprocess.run(["git", "-C", str(REPO), *cmd], capture_output=True, text=True)
        if r.returncode != 0 and "nothing to commit" not in (r.stdout + r.stderr):
            print(r.stdout.strip())
            print(r.stderr.strip(), file=sys.stderr)
            die(f"publish failed: {' '.join(cmd[:3])}")
    remotes = subprocess.run(["git", "-C", str(REPO), "remote"], capture_output=True, text=True)
    if remotes.stdout.strip():
        r = subprocess.run(["git", "-C", str(REPO), "push"], capture_output=True, text=True)
        if r.returncode != 0:
            print(f"warn: git push failed — push manually later\n{r.stderr.strip()}")
        else:
            print("publish: pushed to remote")
    print(f"publish: committed ({msg})")
    return 0


def cmd_bind(args) -> int:
    pid, h = resolve_ref(args.ref)
    bdir = BUNDLES_DIR / pid / h
    if not bdir.is_dir():
        die(f"cannot bind: bundle {pid}@{h} not in registry — pack first")
    variables = {}
    for kv in args.var or []:
        k, _, v = kv.partition("=")
        variables[k] = v
    data = load_bindings()
    entry = find_binding(data, args.slot)
    if entry is None:
        entry = {"slot": args.slot}
        data["bindings"].append(entry)
    entry.update(
        persona=pid,
        hash=h,
        host=args.host,
        target=str(Path(args.target).resolve()),
        vars=variables,
        pin=bool(args.pin),
        device=getattr(args, "device", None) or "",
        bound_at=now_iso(),
    )
    save_bindings(data)
    print(f"bind: {args.slot} → {pid}@{h} (host={args.host}, target={entry['target']}"
          + (f", device={entry['device']}" if entry["device"] else "")
          + (", pin" if entry["pin"] else "") + ")")
    return 0


def _slot_entries(data: dict, slot: "str | None", device: "str | None" = None):
    if slot:
        e = find_binding(data, slot)
        if e is None:
            die(f"no binding for slot {slot!r}")
        return [e]
    entries = data["bindings"]
    if device is not None:
        entries = [e for e in entries if e.get("device", "") == device]
    return entries


def _check(e: dict):
    """One binding → (state, detail). Loads bundle, renders, readbacks, compares."""
    pid, h = e["persona"], e["hash"]
    bdir = BUNDLES_DIR / pid / h
    if not bdir.is_dir():
        return "missing-bundle", f"{pid}@{h} not in local registry — pack or pull"
    manifest_bytes, files, loads = load_bundle(pid, h)
    try:
        rendered = render_files(files, e.get("vars") or {})
    except KeyError as exc:
        return "render-fail", f"{exc}"
    dh = derived_hash(manifest_bytes, rendered)
    adapter = get_adapter(e["host"])
    got = adapter.readback(Path(e["target"]), pid, list(files), loads)
    if got is None or not got:
        return "not-placed", "host target empty or absent — run reconcile"
    names = [n for n in files if n not in got]
    if names:
        return "partial", f"missing on host: {', '.join(names)}"
    diff = [n for n in files if got[n] != rendered[n]]
    if diff:
        state = "drifted" if not e.get("pin") else "drifted-pinned"
        return state, f"host differs: {', '.join(diff)} (reconcile=revert, absorb=promote)"
    return "converged", f"{pid}@{h}{'*' if e.get('vars') else ''} = {dh}"


def cmd_status(args) -> int:
    data = load_bindings()
    entries = _slot_entries(data, args.slot, args.device)
    if not entries:
        print("status: no bindings match"
              + (f" device {args.device!r}" if args.device else "")
              + " — persona bind <slot> <id[@hash]> --host --target")
        return 0
    bad = 0
    for e in entries:
        state, detail = _check(e)
        mark = "" if state == "converged" else "  ←"
        print(f"  {e['slot']:<24} {e['persona']}@{e['hash']:<{HASH_LEN}}  {state:<16} {detail}{mark}")
        if state not in ("converged",):
            bad += 1
    return 0 if bad == 0 else 2


def cmd_reconcile(args) -> int:
    data = load_bindings()
    entries = _slot_entries(data, args.slot, args.device)
    if not entries:
        print("reconcile: no bindings match"
              + (f" device {args.device!r}" if args.device else "")
              + " — nothing to converge")
        return 0
    if args.pull:
        r = subprocess.run(["git", "-C", str(REPO), "pull", "--ff-only"], capture_output=True, text=True)
        if r.returncode != 0:
            print(f"warn: git pull failed, continuing with local registry\n{r.stderr.strip()}")
        else:
            print(f"pull: {r.stdout.strip().splitlines()[-1] if r.stdout.strip() else 'up to date'}")
    failed = 0
    for e in entries:
        if e.get("pin"):
            print(f"  {e['slot']}: pinned — skipping (drift is declared, not converged away)")
            continue
        pid, h = e["persona"], e["hash"]
        bdir = BUNDLES_DIR / pid / h
        if not bdir.is_dir():
            receipt(e["slot"], persona=pid, hash=h, ok=False, detail="missing bundle")
            print(f"  {e['slot']}: FAIL — bundle {pid}@{h} not in local registry (kept as-is)")
            failed += 1
            continue
        manifest_bytes, files, loads = load_bundle(pid, h)
        try:
            rendered = render_files(files, e.get("vars") or {})
        except KeyError as exc:
            receipt(e["slot"], persona=pid, hash=h, ok=False, detail=f"render: {exc}")
            print(f"  {e['slot']}: FAIL — {exc}")
            failed += 1
            continue
        dh = derived_hash(manifest_bytes, rendered)
        adapter = get_adapter(e["host"])
        try:
            adapter.place(Path(e["target"]), pid, dh, rendered, loads)
        except Exception as exc:  # noqa: BLE001
            receipt(e["slot"], persona=pid, hash=h, derived=dh, ok=False, detail=f"place: {exc}")
            print(f"  {e['slot']}: FAIL — place error: {exc}")
            failed += 1
            continue
        state, detail = _check(e)
        ok = state == "converged"
        receipt(e["slot"], persona=pid, hash=h, derived=dh, ok=ok, detail=detail)
        print(f"  {e['slot']}: {'converged' if ok else 'FAIL after place'} — {detail}")
        if not ok:
            failed += 1
    return 0 if failed == 0 else 2


def cmd_revert(args) -> int:
    data = load_bindings()
    e = find_binding(data, args.slot)
    if e is None:
        die(f"no binding for slot {args.slot!r}")
    idx = load_index(e["persona"])
    hs = [b["hash"] for b in idx["bundles"]]
    if e["hash"] not in hs:
        die(f"current hash {e['hash']} not in index — registry and bindings disagree")
    i = hs.index(e["hash"])
    if i == 0:
        die(f"{e['persona']}@{e['hash']} is the oldest packed version — nothing to revert to")
    prev = hs[i - 1]
    e["hash"] = prev
    e["bound_at"] = now_iso()
    save_bindings(data)
    print(f"revert: {args.slot} → {e['persona']}@{prev}")
    return cmd_reconcile(argparse.Namespace(slot=args.slot, pull=False))


def cmd_absorb(args) -> int:
    data = load_bindings()
    e = find_binding(data, args.slot)
    if e is None:
        die(f"no binding for slot {args.slot!r}")
    if not args.yes:
        die("absorb overwrites the source files with host-side content — re-run with --yes")
    pid, h = e["persona"], e["hash"]
    idx = load_index(pid)
    entry = next((b for b in idx["bundles"] if b["hash"] == h), None)
    src = Path(entry["source"]) if entry and entry.get("source") else None
    if src is None or not (src / "persona.yaml").is_file():
        die("source directory from pack time is unreachable — absorb needs it")
    _, files, loads = load_bundle(pid, h)
    adapter = get_adapter(e["host"])
    got = adapter.readback(Path(e["target"]), pid, list(files), loads)
    if not got:
        die("nothing readable on host side")
    changed = []
    for name in files:
        if name in got and got[name] != files[name]:
            (src / name).write_bytes(got[name])
            changed.append(name)
    if not changed:
        print("absorb: host matches bundle — nothing to promote")
        return 0
    print(f"absorb: wrote back {len(changed)} files into source {src}: {', '.join(changed)}")
    print("next: edit persona.yaml version → validate → pack → bind upgrade → reconcile")
    return 0


def cmd_list(args) -> int:
    if BUNDLES_DIR.is_dir():
        for pid_dir in sorted(BUNDLES_DIR.glob("*")):
            idx = load_index(pid_dir.name)
            for b in idx["bundles"]:
                print(f"  {pid_dir.name}@{b['hash']}  v{b['version']}  {b['packed_at']}")
    data = load_bindings()
    for e in data["bindings"]:
        print(f"  ~{e['slot']} → {e['persona']}@{e['hash']} ({e['host']})")
    return 0


# ---------------------------------------------------------------- cli

def main() -> int:
    ap = argparse.ArgumentParser(prog="persona", description="five-file persona registry + reconciler")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("validate", help="lint the source five-file set")
    p.add_argument("source")
    p.set_defaults(fn=cmd_validate)

    p = sub.add_parser("pack", help="snapshot source into an immutable bundle")
    p.add_argument("source")
    p.set_defaults(fn=cmd_pack)

    p = sub.add_parser("publish", help="commit the registry (bundles + bindings) to git")
    p.add_argument("--msg", help="override the commit message")
    p.set_defaults(fn=cmd_publish)

    p = sub.add_parser("bind", help="declare desired state for a host slot")
    p.add_argument("slot")
    p.add_argument("ref", help="persona or persona@hash")
    p.add_argument("--host", required=True, choices=sorted(ADAPTERS))
    p.add_argument("--target", required=True, help="host-side directory for this slot")
    p.add_argument("--var", action="append", metavar="KEY=VAL", help="render variable (repeatable)")
    p.add_argument("--pin", action="store_true", help="exempt this slot from reconcile")
    p.add_argument("--device", default="", help="wiring identity tag (per-device, e.g. linux-sandbox / win-dsh)")
    p.set_defaults(fn=cmd_bind)

    p = sub.add_parser("status", help="report drift for all/one binding(s)")
    p.add_argument("slot", nargs="?")
    p.add_argument("--device", default=None, help="filter to one device's bindings (per-box view)")
    p.set_defaults(fn=cmd_status)

    p = sub.add_parser("reconcile", help="converge host(s) to their bindings")
    p.add_argument("slot", nargs="?")
    p.add_argument("--device", default=None, help="filter to one device's bindings (per-box view)")
    p.add_argument("--pull", action="store_true", help="git pull the registry first (dsh boot hook)")
    p.set_defaults(fn=cmd_reconcile)

    p = sub.add_parser("revert", help="point a slot at the previous packed version")
    p.add_argument("slot")
    p.set_defaults(fn=cmd_revert)

    p = sub.add_parser("absorb", help="promote host-side edits back into the source")
    p.add_argument("slot")
    p.add_argument("--yes", action="store_true")
    p.set_defaults(fn=cmd_absorb)

    p = sub.add_parser("list", help="list registry bundles and bindings")
    p.set_defaults(fn=cmd_list)

    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
