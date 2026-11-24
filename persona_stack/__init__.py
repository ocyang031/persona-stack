"""persona — registry + reconciler for the persona file set.

Implements DESIGN.md v1: the persona files ARE the final form. This tool never
compiles or reshapes them. It snapshots them into an immutable, content-hashed
bundle directory (the registry), records desired state in bindings.json, and
converges host-side copies to it (the reconciler), reporting drift.

Host adapters (seam ①): file/openclaw (managed-block envelope), dsh (single
prefix with self-describing file markers). Registry backend (seam ②): a git
repo — this one. Triggers (seam ③): manual CLI or the dsh start.sh hook.

Layout: paths/util (process + layout) · manifest (source face) · registry
(hash + bundles + render) · state (bindings + receipts) · adapters/ (one file
per host) · commands (the ten verbs) · cli (argparse wiring).
"""
from __future__ import annotations

from .manifest import parse_manifest
from .paths import BINDINGS_FILE, BUNDLES_DIR, SOURCES_DIR
from .registry import canonical_hash

__all__ = ["BINDINGS_FILE", "BUNDLES_DIR", "SOURCES_DIR", "canonical_hash", "parse_manifest"]
