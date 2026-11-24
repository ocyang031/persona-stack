"""Adapter registry: host name (and alias) → adapter class."""
from __future__ import annotations

from ..util import die
from .dsh import DshAdapter
from .file import FileAdapter

ADAPTERS: dict = {}


def register(adapter) -> None:
    """Register one adapter under its name and every alias."""
    ADAPTERS[adapter.name] = adapter
    for alias in getattr(adapter, "aliases", ()):
        ADAPTERS[alias] = adapter


register(FileAdapter)
register(DshAdapter)


def get_adapter(host: str):
    if host not in ADAPTERS:
        die(f"unknown host adapter {host!r} (have: {', '.join(sorted(ADAPTERS))})")
    return ADAPTERS[host]
