"""The ten verbs. Each cmd_* is one vertical slice of the registry+reconciler."""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from .adapters import get_adapter
from .manifest import load_source, validate_source
from .paths import BUNDLES_DIR, HASH_LEN, REPO, SOURCES_DIR
from .registry import (
    canonical_hash,
    derived_hash,
    load_bundle,
    load_index,
    render_files,
    resolve_ref,
    save_index,
)
from .state import find_binding, load_bindings, receipt, save_bindings
from .util import die, now_iso


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
    m, manifest_bytes, plain, errors, warnings = validate_source(src)
    for w in warnings:
        print(f"warn: {w}")
    if errors:
        for e in errors:
            print(f"error: {e}")
        die("pack: source failed validation; fix the source files first")
    pid = m["id"]
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
    # 先晋升：sources/ 下每个 persona 都 pack 一遍（幂等——内容没变即跳过；
    # 校验失败则中止，脏 sources 不得静默推送）。人的发版动词只有这一个。
    if SOURCES_DIR.is_dir():
        for src in sorted(SOURCES_DIR.iterdir()):
            if src.is_dir() and (src / "persona.yaml").is_file():
                cmd_pack(argparse.Namespace(source=str(src)))
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
        r = subprocess.run(
            ["git", "-C", str(REPO), *cmd], capture_output=True, text=True,
            encoding="utf-8", errors="replace",
        )
        if r.returncode != 0 and "nothing to commit" not in (r.stdout + r.stderr):
            print(r.stdout.strip())
            print(r.stderr.strip(), file=sys.stderr)
            die(f"publish failed: {' '.join(cmd[:3])}")
    remotes = subprocess.run(
        ["git", "-C", str(REPO), "remote"], capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    if remotes.stdout.strip():
        r = subprocess.run(
            ["git", "-C", str(REPO), "push"], capture_output=True, text=True,
            encoding="utf-8", errors="replace",
        )
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
    adapter = get_adapter(args.host)
    target = Path(args.target).resolve()
    if target.exists():
        if adapter.target_kind == "file" and target.is_dir():
            die(f"host {args.host!r} places one file; target is a directory: {target}")
        if adapter.target_kind == "dir" and target.is_file():
            die(f"host {args.host!r} places files into a directory; target is a file: {target}")
    include = [s.strip() for s in (getattr(args, "include", "") or "").split(",") if s.strip()]
    _, files, _ = load_bundle(pid, h)
    try:
        _selected({"include": include}, adapter, files)
    except KeyError as exc:
        die(str(exc))
    data = load_bindings()
    entry = find_binding(data, args.slot)
    if entry is None:
        entry = {"slot": args.slot}
        data["bindings"].append(entry)
    entry.update(
        persona=pid,
        hash=h,
        host=args.host,
        target=str(target),
        vars=variables,
        pin=bool(args.pin),
        device=getattr(args, "device", None) or "",
        bound_at=now_iso(),
    )
    if include:
        entry["include"] = include
    else:
        entry.pop("include", None)
    save_bindings(data)
    print(f"bind: {args.slot} → {pid}@{h} (host={args.host}, target={entry['target']}"
          + (f", device={entry['device']}" if entry["device"] else "")
          + (", pin" if entry["pin"] else "") + ")")
    return 0


def cmd_unbind(args) -> int:
    data = load_bindings()
    e = find_binding(data, args.slot)
    if e is None:
        die(f"no binding for slot {args.slot!r}")
    if not args.yes:
        die(f"unbind strips the persona block from {e['target']} and drops the binding "
            f"— re-run with --yes")
    pid, h = e["persona"], e["hash"]
    files: dict = {}
    loads: dict = {}
    if (BUNDLES_DIR / pid / h).is_dir():
        _, files, loads = load_bundle(pid, h)
    else:
        print(f"warn: bundle {pid}@{h} not in local registry — "
              f"removing the block without a file list")
    adapter = get_adapter(e["host"])
    for note in adapter.remove(Path(e["target"]), pid, files, loads):
        print(f"  note: {note}")
    data["bindings"].remove(e)
    save_bindings(data)
    print(f"unbind: {args.slot} → {e['target']}")
    print(f"  restore: python persona.py bind {args.slot} --host {e['host']} "
          f"--target \"{e['target']}\" {pid}@{h}")
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


def _selected(e: dict, adapter, files: dict) -> dict:
    """Files this slot actually places: binding include > adapter wants > all."""
    keep = e.get("include") or list(adapter.wants or ())
    if not keep:
        return files
    missing = set(e.get("include") or ()) - files.keys()
    if missing:
        raise KeyError(f"unknown persona modules: {', '.join(sorted(missing))}")
    selected = {n: c for n, c in files.items() if n in keep}
    if not selected:
        raise KeyError("no persona modules selected; set --include to a manifest file name")
    return selected


def _check(e: dict):
    """One binding → (state, detail). Loads bundle, renders, readbacks, compares."""
    pid, h = e["persona"], e["hash"]
    bdir = BUNDLES_DIR / pid / h
    if not bdir.is_dir():
        return "missing-bundle", f"{pid}@{h} not in local registry — pack or pull"
    manifest_bytes, files, loads = load_bundle(pid, h)
    adapter = get_adapter(e["host"])
    try:
        files = _selected(e, adapter, files)
        rendered = render_files(files, e.get("vars") or {})
    except KeyError as exc:
        return "render-fail", f"{exc}"
    dh = derived_hash(manifest_bytes, rendered)
    got = adapter.readback(Path(e["target"]), pid, list(files), loads)
    if got is None or not got:
        return "not-placed", "host target empty or absent — run reconcile"
    names = [n for n in files if n not in got]
    if names:
        return "partial", f"missing on host: {', '.join(names)}"
    diff = [n for n in files if got[n] != rendered[n]]
    diff.extend(sorted(got.keys() - files.keys()))
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
        adapter = get_adapter(e["host"])
        try:
            files = _selected(e, adapter, files)
            rendered = render_files(files, e.get("vars") or {})
        except KeyError as exc:
            receipt(e["slot"], persona=pid, hash=h, ok=False, detail=f"render: {exc}")
            print(f"  {e['slot']}: FAIL — {exc}")
            failed += 1
            continue
        dh = derived_hash(manifest_bytes, rendered)
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
        # pack-time source moved/deleted (repo migration) — fall back to the
        # in-repo editing face; copy old bundle there if it is empty/missing.
        src = SOURCES_DIR / pid
        if src.is_dir() and (src / "persona.yaml").is_file():
            print(f"note: pack-time source unreachable, using {src}")
        else:
            die(f"source directory unreachable — copy bundle {pid}@{h} into sources/{pid}/ first, then absorb")
    _, files, loads = load_bundle(pid, h)
    adapter = get_adapter(e["host"])
    try:
        files = _selected(e, adapter, files)
    except KeyError as exc:
        die(str(exc))
    source_manifest, _, source_files = load_source(src)
    source_is_legacy = any("load" in entry for entry in source_manifest["files"])
    if loads and not source_is_legacy:
        die("cannot absorb a legacy placement into module sources; merge edits into the source manually")
    missing = files.keys() - {name for name, _ in source_files}
    if missing:
        die(f"cannot absorb modules absent from source: {sorted(missing)}")
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
