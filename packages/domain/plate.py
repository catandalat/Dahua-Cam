from __future__ import annotations

import re
from typing import Sequence


_PLATE_RE = re.compile(r"[^A-Z0-9]")
# VN plates from Dahua OCR (digits/letters only after normalize):
#   car:     51F12345 / 30A1234     (7–8 chars)
#   moto:    59B123456 / 41D074011  (9 chars = letter + 6 digits)
#   moto OCR sometimes drops a digit → 8 chars with tall 2-line bbox
_VN_PLATE_RE = re.compile(r"^\d{2}[A-Z]{1,2}\d{3,6}$")
_VN_MOTO_9_RE = re.compile(r"^\d{2}[A-Z]\d{6}$")
_VN_MOTO_8_RE = re.compile(r"^\d{2}[A-Z]\d{5}$")


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


def is_vn_motorcycle_plate(raw: str | None, *, plate_bbox: Sequence[float] | None = None) -> bool:
    """Match VN motorcycle plates as produced by Dahua OCR.

    - 9-char definite: 41D074011 / 59B123456 (province + letter + 6 digits)
    - 8-char ambiguous with cars: only when plate bbox is taller than wide
      (2-line moto plate), e.g. 49C04891 on exit Tail
    """
    p = normalize_plate(raw)
    if not p:
        return False
    if _VN_MOTO_9_RE.match(p):
        return True
    if _VN_MOTO_8_RE.match(p) and plate_bbox_is_two_line(plate_bbox):
        return True
    return False


def plate_bbox_is_two_line(plate_bbox: Sequence[float] | None, *, min_ratio: float = 1.05) -> bool:
    """Two-line VN motorcycle plates are square/taller; car plates are wider."""
    if not plate_bbox or len(plate_bbox) < 4:
        return False
    try:
        x1, y1, x2, y2 = (
            float(plate_bbox[0]),
            float(plate_bbox[1]),
            float(plate_bbox[2]),
            float(plate_bbox[3]),
        )
    except (TypeError, ValueError):
        return False
    w = abs(x2 - x1)
    h = abs(y2 - y1)
    if w < 20 or h < 20:
        return False
    return (h / w) >= min_ratio


def plate_bbox_aspect(plate_bbox: Sequence[float] | None) -> float | None:
    if not plate_bbox or len(plate_bbox) < 4:
        return None
    try:
        w = abs(float(plate_bbox[2]) - float(plate_bbox[0]))
        h = abs(float(plate_bbox[3]) - float(plate_bbox[1]))
    except (TypeError, ValueError):
        return None
    if w < 1:
        return None
    return h / w
