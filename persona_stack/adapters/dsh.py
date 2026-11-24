"""dsh-style host: one prefix artifact concatenates the always-on set."""
from __future__ import annotations

import re
from pathlib import Path

from .base import file_marked_body

DSH_PREFIX_LOADS = ("always-on", "session-start")


def dsh_prefix(pid: str, h: str, files: dict, loads: dict) -> str:
    """One self-describing prefix artifact: header + in-prefix files in
    manifest order, each behind a `<!-- persona:file NAME -->` marker so
    readback can split byte-exactly."""
    return file_marked_body(pid, h, {
        name: content for name, content in files.items()
        if loads.get(name) in DSH_PREFIX_LOADS
    })


class DshAdapter:
    """dsh-style host: the system prompt is one stable prefix region, so the
    session-start distinction collapses — everything session-start-or-stronger
    is concatenated into one self-describing prefix artifact; on-demand files
    are delivered as plain workspace copies the agent reaches by pointer."""
    name = "dsh"
    target_kind = "dir"
    wants = None
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
    def remove(target: Path, pid: str, files: dict, loads: dict) -> "list[str]":
        if not target.is_dir():
            return []
        pfx = target / DshAdapter.PREFIX
        if pfx.is_file():
            pfx.unlink()
        kept = []
        for name, content in files.items():
            if loads.get(name) in DshAdapter.IN_PREFIX:
                continue
            p = target / name
            if not p.is_file():
                continue
            # on-demand files are plain copies with no marker — only delete the
            # ones still byte-identical to the bundle, else it is host content
            if p.read_bytes() == content:
                p.unlink()
            else:
                kept.append(f"kept {name} — modified on host, not ours to delete")
        return kept
