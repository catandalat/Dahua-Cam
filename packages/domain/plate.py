from __future__ import annotations

import re


_PLATE_RE = re.compile(r"[^A-Z0-9]")


def normalize_plate(raw: str | None) -> str | None:
    """Uppercase and strip non-alphanumeric characters from a plate string."""
    if not raw:
        return None
    cleaned = _PLATE_RE.sub("", str(raw).upper().strip())
    return cleaned or None
