"""codex-style host: ONE instructions file at a fixed path the host owns."""
from __future__ import annotations

import re
from pathlib import Path

from ..util import die
from .base import block_regex, file_marked_body, inner_regex

FILE_MARKER = re.compile(rb"<!-- persona:file (.+?) -->\n")


class CodexAdapter:
    """codex-style host: `~/.codex/AGENTS.md` (or a project `AGENTS.md`) is a
    single file the host — and often other tools — already own. Persona goes
    into one envelope, everything outside it stays untouched.

    The host offers only one slot, so the load hints collapse: only files codex
    can actually consume are placed (see `wants`); on-demand sets have nowhere
    to mount and are dropped rather than pasted in permanently."""
    name = "codex"
    target_kind = "file"
    wants = ("IDENTITY.md", "SOUL.md", "DISCIPLINE.md")

    @staticmethod
    def place(target: Path, pid: str, h: str, files: dict, loads: dict) -> None:
        if not files:
            die(f"codex places one file: nothing selected for {pid} — "
                f"check --include and the set's file names")
        block = b"".join((
            f"<!-- persona:{pid}@{h} BEGIN -->\n".encode("utf-8"),
            file_marked_body(pid, h, files).encode("utf-8"),
            f"<!-- persona:{pid}@{h} END -->\n".encode("utf-8"),
        ))
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            target.write_bytes(block)
            return
        data = target.read_bytes()
        pat = block_regex(pid)
        if pat.search(data):
            target.write_bytes(pat.sub(lambda _m: block, data))
        else:
            target.write_bytes(data.rstrip(b"\n") + b"\n\n" + block)

    @staticmethod
    def readback(target: Path, pid: str, names: list, loads: dict):
        if not target.is_file():
            return None
        m = inner_regex(pid).search(target.read_bytes())
        if not m:
            return None
        # inner_regex eats the newline that ends the envelope body, so the last
        # file loses exactly one trailing newline (validate enforces it exists).
        out: "dict[str, bytes]" = {}
        pieces = FILE_MARKER.split(m.group(1))
        for i in range(1, len(pieces) - 1, 2):
            body = pieces[i + 1]
            out[pieces[i].decode("utf-8")] = body if body.endswith(b"\n") else body + b"\n"
        return out

    @staticmethod
    def remove(target: Path, pid: str) -> None:
        if not target.is_file():
            return
        pat = block_regex(pid)
        data = target.read_bytes()
        if not pat.search(data):
            return
        new = re.sub(rb"\n{3,}", b"\n\n", pat.sub(b"", data)).strip(b"\n")
        if new:
            target.write_bytes(new + b"\n")
        else:
            target.unlink()
