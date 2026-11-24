"""Adapter registry: host name (and alias) → adapter class."""
from __future__ import annotations

from ..util import die
from .base import Adapter
from .codex import CodexAdapter
from .dsh import DshAdapter
from .file import FileAdapter

ADAPTERS: dict = {}


def register(adapter: "type[Adapter]") -> None:
    """Register one adapter under its name and every alias."""
    ADAPTERS[adapter.name] = adapter
    for alias in getattr(adapter, "aliases", ()):
        ADAPTERS[alias] = adapter


register(FileAdapter)
register(DshAdapter)
register(CodexAdapter)


def get_adapter(host: str) -> "type[Adapter]":
    if host not in ADAPTERS:
        die(f"unknown host adapter {host!r} (have: {', '.join(sorted(ADAPTERS))})")
    return ADAPTERS[host]
