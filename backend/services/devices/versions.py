"""Vergleich von Firmwareversionen.

Gerätetreiber melden Versionen in unterschiedlicher Form (``2.3.4``, ``V4.5.2``,
``IRF3xxx-2.3.4-SVN-R68479``). Verglichen wird die erste Zahlenfolge ``a.b[.c[.d]]``.
Lässt sich keine Version erkennen, gilt der Vergleich als nicht möglich (``None``).
"""

from __future__ import annotations

import re

_VERSION = re.compile(r"(?<![\d.])(\d+(?:\.\d+){1,3})(?![\d])")


def parse_version(text: str | None) -> tuple[int, ...] | None:
    if not text:
        return None
    match = _VERSION.search(str(text))
    if not match:
        return None
    parts = tuple(int(p) for p in match.group(1).split("."))
    # 2.3 == 2.3.0
    while len(parts) > 1 and parts[-1] == 0:
        parts = parts[:-1]
    return parts


def compare_versions(installed: str | None, target: str | None) -> int | None:
    """-1: installiert ist älter, 0: gleich, 1: installiert ist neuer, None: nicht vergleichbar."""
    a, b = parse_version(installed), parse_version(target)
    if a is None or b is None:
        return None
    return (a > b) - (a < b)


def version_from_filename(name: str) -> str | None:
    match = _VERSION.search(name)
    return match.group(1) if match else None
