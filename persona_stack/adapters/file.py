"""openclaw-style host: one file per source file, each inside an envelope."""
from __future__ import annotations

import re
from pathlib import Path

from .base import block_regex, inner_regex


class FileAdapter:
    """openclaw-style host: each file lives inside a managed-block envelope.
    All placement is byte-level (no newline translation, no decode round
    trips) so the host file lands byte-exact to the bundle content."""
    name = "file"
    aliases = ("openclaw",)
    target_kind = "dir"
    wants = None

    @staticmethod
    def place(target: Path, pid: str, h: str, files: dict, loads: dict) -> None:
        target.mkdir(parents=True, exist_ok=True)
        pat = block_regex(pid)
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
            if pat.search(data):
                p.write_bytes(pat.sub(lambda _m: block, data))
            else:
                p.write_bytes(data + b"\n" + block)
        FileAdapter._remove_blocks(target, pid, keep=files)

    @staticmethod
    def readback(target: Path, pid: str, names: list, loads: dict):
        if not target.is_dir():
            return None
        out: "dict[str, bytes]" = {}
        pat = inner_regex(pid)
        for p in target.glob("*.md"):
            if not p.is_file():
                continue
            m = pat.search(p.read_bytes())
            if m:
                out[p.name] = m.group(1) + b"\n"
        return out

    @staticmethod
    def remove(target: Path, pid: str, files: dict, loads: dict) -> "list[str]":
        FileAdapter._remove_blocks(target, pid, keep={})
        return []

    @staticmethod
    def _remove_blocks(target: Path, pid: str, keep: dict) -> None:
        block = block_regex(pid)
        pat = re.compile(rb"\n?" + block.pattern, block.flags)
        # a file we created holds only our header — deleting the block must take
        # the header with it, or an empty shell is left behind
        hdr = re.compile(rb"^\s*# persona:" + re.escape(pid.encode()) + rb"@\S+ managed file\s*$")
        for p in target.glob("*.md"):
            if p.name in keep or not p.is_file():
                continue
            data = p.read_bytes()
            if pat.search(data):
                new = pat.sub(b"", data)
                if new and not hdr.match(new):
                    p.write_bytes(new)
                else:
                    p.unlink()
