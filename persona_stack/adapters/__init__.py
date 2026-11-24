"""Adapter registry: host name (and alias) → adapter class."""
from __future__ import annotations

from ..util import die
from .dsh import DshAdapter
from .file import FileAdapter

ADAPTERS: dict = {FileAdapter.name: FileAdapter, DshAdapter.name: DshAdapter}
for a in (FileAdapter, DshAdapter):
    for alias in getattr(a, "aliases", ()):  # type: ignore[attr-defined]
        ADAPTERS[alias] = a


def get_adapter(host: str):
    if host not in ADAPTERS:
        die(f"unknown host adapter {host!r} (have: {', '.join(sorted(ADAPTERS))})")
    return ADAPTERS[host]
