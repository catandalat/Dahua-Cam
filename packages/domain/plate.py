from __future__ import annotations

import re


_PLATE_RE = re.compile(r"[^A-Z0-9]")
# VN plates: province (2 digits) + series letter(s) + 3–6 digits (car/moto).
_VN_PLATE_RE = re.compile(r"^\d{2}[A-Z]{1,2}\d{3,6}$")
# Definite motorcycle: 59B123456 (series digit + 5 digits → 6 digits after letter).
_VN_MOTO_PLATE_RE = re.compile(r"^\d{2}[A-Z]\d{6}$")


def normalize_plate(raw: str | None) -> str | None:
    """Uppercase and strip non-alphanumeric characters from a plate string."""
    if not raw:
        return None
    cleaned = _PLATE_RE.sub("", str(raw).upper().strip())
    return cleaned or None


def is_valid_vn_plate(raw: str | None) -> bool:
    """True for plausible Vietnamese plate strings (rejects OO8313 / K8760454)."""
    p = normalize_plate(raw)
    if not p or not (7 <= len(p) <= 10):
        return False
    return bool(_VN_PLATE_RE.match(p))


def is_vn_motorcycle_plate(raw: str | None) -> bool:
    """True for definite VN motorcycle numbers (9 chars, e.g. 59B123456)."""
    p = normalize_plate(raw)
    if not p:
        return False
    return bool(_VN_MOTO_PLATE_RE.match(p))
