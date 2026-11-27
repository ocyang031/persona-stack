"""argparse wiring only — every verb lives in commands.py."""
from __future__ import annotations

import argparse

from .adapters import ADAPTERS
from .commands import (
    cmd_absorb,
    cmd_bind,
    cmd_list,
    cmd_pack,
    cmd_publish,
    cmd_reconcile,
    cmd_revert,
    cmd_status,
    cmd_unbind,
    cmd_validate,
)


def main() -> int:
    ap = argparse.ArgumentParser(prog="persona", description="persona file-set registry + reconciler")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("validate", help="lint the source persona file set")
    p.add_argument("source")
    p.set_defaults(fn=cmd_validate)

    p = sub.add_parser("pack", help="snapshot source into an immutable bundle")
    p.add_argument("source")
    p.set_defaults(fn=cmd_pack)

    p = sub.add_parser("publish", help="commit the registry (version bump gate before git)")
    p.add_argument("--msg", help="override the commit message")
    p.set_defaults(fn=cmd_publish)

    p = sub.add_parser("bind", help="declare desired state for a host slot")
    p.add_argument("slot")
    p.add_argument("ref", help="persona or persona@hash")
    p.add_argument("--host", required=True, choices=sorted(ADAPTERS))
    p.add_argument("--target", required=True, help="host-side directory (or file); stored machine-locally")
    p.add_argument("--var", action="append", metavar="KEY=VAL", help="render variable (repeatable)")
    p.add_argument("--include", default="", help="comma-separated file whitelist (default: the adapter's)")
    p.add_argument("--pin", action="store_true", help="exempt this slot from reconcile (revert still converges)")
    p.add_argument("--device", default="", help="wiring identity tag (per-device, e.g. linux-sandbox / win-dsh)")
    p.set_defaults(fn=cmd_bind)

    p = sub.add_parser("unbind", help="strip a slot's host placement and drop the binding")
    p.add_argument("slot")
    p.add_argument("--yes", action="store_true", help="confirm removing the host-side block")
    p.set_defaults(fn=cmd_unbind)

    p = sub.add_parser("status", help="report drift for all/one binding(s)")
    p.add_argument("slot", nargs="?")
    p.add_argument("--device", default=None, help="filter to one device's bindings (per-box view)")
    p.set_defaults(fn=cmd_status)

    p = sub.add_parser("reconcile", help="converge host(s) to their bindings")
    p.add_argument("slot", nargs="?")
    p.add_argument("--device", default=None, help="filter to one device's bindings (per-box view)")
    p.add_argument("--pull", action="store_true", help="git pull the registry first (dsh boot hook)")
    p.set_defaults(fn=cmd_reconcile)

    p = sub.add_parser("revert", help="point a slot at the previous packed version")
    p.add_argument("slot")
    p.set_defaults(fn=cmd_revert)

    p = sub.add_parser("absorb", help="promote host-side edits back into the source")
    p.add_argument("slot")
    p.add_argument("--yes", action="store_true")
    p.set_defaults(fn=cmd_absorb)

    p = sub.add_parser("list", help="list registry bundles and bindings")
    p.set_defaults(fn=cmd_list)

    args = ap.parse_args()
    return args.fn(args)
