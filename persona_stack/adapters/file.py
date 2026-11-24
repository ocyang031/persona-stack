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
