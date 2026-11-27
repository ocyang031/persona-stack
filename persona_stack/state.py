"""Desired-state face: bindings table and the append-only receipt stream."""
from __future__ import annotations

import json
import re

from .paths import BINDINGS_FILE, RECEIPTS_DIR, TARGETS_FILE
from .util import now_iso


def _dump(path, data) -> None:
    """Byte-level, LF-only JSON — Path.write_text would translate newlines."""
    payload = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    path.write_bytes(payload.encode("utf-8"))


def load_bindings() -> dict:
    if BINDINGS_FILE.is_file():
        # utf-8-sig: tolerate Windows-side edits that leave a BOM
        return json.loads(BINDINGS_FILE.read_text(encoding="utf-8-sig"))
    return {"bindings": []}


def save_bindings(data: dict) -> None:
    _dump(BINDINGS_FILE, data)


def load_targets() -> "dict[str, str]":
    """This clone's slot -> absolute host target map (gitignored)."""
    if TARGETS_FILE.is_file():
        raw = json.loads(TARGETS_FILE.read_text(encoding="utf-8-sig"))
        return {str(k): str(v) for k, v in raw.items()}
    return {}


def save_targets(targets: "dict[str, str]") -> None:
    _dump(TARGETS_FILE, dict(sorted(targets.items())))


def find_binding(data: dict, slot: str) -> "dict | None":
    for b in data["bindings"]:
        if b["slot"] == slot:
            return b
    return None


def receipt(slot: str, **payload) -> None:
    RECEIPTS_DIR.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", slot)
    payload = {"ts": now_iso(), "slot": slot, **payload}
    with open(RECEIPTS_DIR / f"{safe}.jsonl", "a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False) + "\n")
