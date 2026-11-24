"""Compose selected modules into the DSH prompt prefix."""
from __future__ import annotations

import re
from pathlib import Path

from .base import file_marked_body

# Placement rules for immutable snapshots made before module composition.
LEGACY_PREFIX_LOADS = ("always-on", "session-start")


def _legacy_copy(name: str, loads: dict) -> bool:
    return name in loads and loads[name] not in LEGACY_PREFIX_LOADS


def dsh_prefix(pid: str, h: str, files: dict, loads: dict) -> str:
    """One self-describing prefix artifact: header + in-prefix files in
    manifest order, each behind a `<!-- persona:file NAME -->` marker so
    readback can split byte-exactly."""
    return file_marked_body(pid, h, {
        name: content for name, content in files.items()
        if not _legacy_copy(name, loads)
    })


class DshAdapter:
    """Write one prefix. Preserve placement and rollback for old snapshots."""
    name = "dsh"
    target_kind = "dir"
    wants = None
    PREFIX = "persona.prefix.txt"

    @staticmethod
    def place(target: Path, pid: str, h: str, files: dict, loads: dict) -> None:
        target.mkdir(parents=True, exist_ok=True)
        (target / DshAdapter.PREFIX).write_bytes(dsh_prefix(pid, h, files, loads).encode("utf-8"))
        for name, content in files.items():
            if _legacy_copy(name, loads):
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
            if _legacy_copy(name, loads):
                p = target / name
                if p.is_file():
                    out[name] = p.read_bytes()
        return out

    @staticmethod
    def remove(target: Path, pid: str, files: dict, loads: dict) -> "list[str]":
        if not target.is_dir():
            return []
        pfx = target / DshAdapter.PREFIX
        if pfx.is_file():
            pfx.unlink()
        kept = []
        for name, content in files.items():
            if not _legacy_copy(name, loads):
                continue
            p = target / name
            if not p.is_file():
                continue
            # Legacy workspace copies have no marker — only delete the
            # ones still byte-identical to the bundle, else it is host content
            if p.read_bytes() == content:
                p.unlink()
            else:
                kept.append(f"kept {name} — modified on host, not ours to delete")
        return kept
