from __future__ import annotations

import re
from typing import Sequence


_PLATE_RE = re.compile(r"[^A-Z0-9]")
# VN plates from Dahua OCR (digits/letters only after normalize):
#   car:     51F12345 / 30A1234     (7–8 chars)
#   moto:    59B123456 / 41D074011  (9 chars = letter + 6 digits)
#   moto OCR sometimes drops a digit → 8 chars with tall/near-square 2-line bbox
_VN_PLATE_RE = re.compile(r"^\d{2}[A-Z]{1,2}\d{3,6}$")
_VN_MOTO_9_RE = re.compile(r"^\d{2}[A-Z]\d{6}$")
_VN_MOTO_8_RE = re.compile(r"^\d{2}[A-Z]\d{5}$")
# Two-letter series (51AA12345) are cars, not motos
_VN_CAR_2LETTER_RE = re.compile(r"^\d{2}[A-Z]{2}\d{4,5}$")

# Dahua clothing / billboard OCR often reports very low confidence
MIN_PLATE_CONFIDENCE = 45.0


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


def plate_confidence_ok(confidence: float | None, *, min_conf: float = MIN_PLATE_CONFIDENCE) -> bool:
    """False when camera reports a confidence below the floor (clothing OCR).

    Missing confidence is treated as OK — older firmware often omits the field.
    """
    if confidence is None:
        return True
    try:
        return float(confidence) >= min_conf
    except (TypeError, ValueError):
        return True


def is_vn_motorcycle_plate(raw: str | None, *, plate_bbox: Sequence[float] | None = None) -> bool:
    """Match VN motorcycle plates as produced by Dahua OCR.

    - 9-char definite: 41D074011 / 59B123456 (province + letter + 6 digits)
    - 8-char ambiguous with cars: when plate bbox is near-square / taller
      (2-line moto plate), e.g. 49C04891 / 51K23865 on gate snaps
    """
    p = normalize_plate(raw)
    if not p:
        return False
    if _VN_CAR_2LETTER_RE.match(p):
        return False
    if _VN_MOTO_9_RE.match(p):
        return True
    if _VN_MOTO_8_RE.match(p) and plate_bbox_is_two_line(plate_bbox):
        return True
    return False


def is_vn_moto_8_candidate(raw: str | None) -> bool:
    """True for 8-char single-letter plates that may be OCR-truncated motos."""
    p = normalize_plate(raw)
    if not p or _VN_CAR_2LETTER_RE.match(p):
        return False
    return bool(_VN_MOTO_8_RE.match(p))


def plate_bbox_is_two_line(plate_bbox: Sequence[float] | None, *, min_ratio: float = 0.90) -> bool:
    """Two-line VN motorcycle plates are near-square/taller; car plates are wider.

    Gate snaps often report aspect ~0.90–1.20 before a perfect frontal crop; 1.05
    was too strict and left many real motos classified as cars.
    """
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
