"""Process-level helpers: console encoding, clock, fatal exit."""
from __future__ import annotations

import sys
from datetime import datetime, timezone

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def die(msg: str) -> "None":
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)
