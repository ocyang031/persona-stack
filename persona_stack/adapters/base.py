"""Shared envelope mechanics for host adapters.

Every adapter wraps persona content in a managed block so the host file can
carry its own content too:

    <!-- persona:<id>@<hash> BEGIN -->
    ...persona bytes...
    <!-- persona:<id>@<hash> END -->
"""
from __future__ import annotations

import re


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
