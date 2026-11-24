"""Repo layout constants — the only module that knows where things live."""
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BUNDLES_DIR = REPO / "bundles"
SOURCES_DIR = REPO / "sources"
BINDINGS_FILE = REPO / "bindings.json"
RECEIPTS_DIR = REPO / "receipts"
HASH_LEN = 16
