#!/usr/bin/env python3
"""persona — CLI entry shim.

The implementation lives in persona_stack/. This file stays at the repo root
because verify.py and .githooks/pre-commit do `from persona import ...`, and
because `python persona.py <verb>` is the documented entry point.
"""
import sys

from persona_stack import (  # noqa: F401  (re-exported for verify.py)
    BINDINGS_FILE,
    BUNDLES_DIR,
    SOURCES_DIR,
    canonical_hash,
    parse_manifest,
)
from persona_stack.cli import main

if __name__ == "__main__":
    sys.exit(main())
