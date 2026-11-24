"""Shared envelope mechanics for host adapters.

Every adapter wraps persona content in a managed block so the host file can
carry its own content too:

    <!-- persona:<id>@<hash> BEGIN -->
    ...persona bytes...
    <!-- persona:<id>@<hash> END -->
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Literal, Protocol


class Adapter(Protocol):
    """The seam every host adapter implements.

    target_kind  — "dir" places many files into a directory; "file" places one
                   artifact at a path the host already owns. Checked at bind.
    wants        — file whitelist this host should receive; None = every file
                   the manifest declares (the load hints decide placement).
    """
    name: str
    aliases: tuple[str, ...]
    target_kind: Literal["dir", "file"]
    wants: "tuple[str, ...] | None"

    @staticmethod
    def place(target: Path, pid: str, h: str, files: dict, loads: dict) -> None: ...

    @staticmethod
    def readback(target: Path, pid: str, names: list, loads: dict) -> "dict[str, bytes] | None": ...

    @staticmethod
    def remove(target: Path, pid: str, files: dict, loads: dict) -> "list[str]":
        """Strip this host's persona placement. `files`/`loads` are the bundle
        set (an adapter needs them to tell its own copies from host edits).
        Returns notes for anything deliberately left behind."""
        ...



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


def file_marked_body(pid: str, h: str, files: dict) -> str:
    """Concatenated artifact body shared by single-artifact hosts: a header
    naming the derived hash, then each file behind a `<!-- persona:file NAME -->`
    marker so readback can split byte-exactly. Callers decide what goes in."""
    parts = [f"<!-- persona:{pid}@{h} -->\n"]
    for name, content in files.items():
        parts.append(f"<!-- persona:file {name} -->\n")
        parts.append(content.decode("utf-8"))
    return "".join(parts)
