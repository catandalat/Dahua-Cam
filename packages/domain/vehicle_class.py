"""Normalize Dahua vehicle Category into car / motorcycle / other classes."""

from __future__ import annotations

import re
from typing import Sequence

# Exact / token matches for motor vehicles (ô tô). Avoid bare "motor" — Dahua
# SnapCategory "Motor" means motor vehicle, not motorcycle.
CAR_KEYWORDS = (
    "car",
    "sedan",
    "suv",
    "mpv",
    "van",
    "bus",
    "truck",
    "lorry",
    "pickup",
    "trailer",
    "taxi",
    "midibus",
    "minibus",
    "heavytruck",
    "mediumtruck",
    "lighttruck",
    "largebus",
    "microbus",
    "vehicle",
    "motorvehicle",
    "automobile",
    "lightduty",
    "mediumduty",
    "heavyduty",
    "passenger",
)

MOTORCYCLE_KEYWORDS = (
    "motorcycle",
    "motorbike",
    "nonmotor",
    "non-motor",
    "bicycle",
    "tricycle",
    "dualtriwheel",
    "lightmotorcycle",
    "embassymotorcycle",
    "coachmotorcycle",
    "foreignmotorcycle",
    "trialmotorcycle",
    "areaoutmotorcycle",
    "marginalmotorcycle",
    "twowheel",
    "threewheel",
    "scooter",
    "ebike",
    "bike",
)

# TrafficCar.CarType is allow/block list status — NOT vehicle body type
_LIST_STATUS_TYPES = {
    "normalcar",
    "trustcar",
    "suspiciouscar",
    "unknown",
}

# VN motorcycle: 59B123456 (province + letter + series digit + 5 digits) = 9 chars
_VN_MOTO_PLATE = re.compile(r"^\d{2}[A-Z]\d{6}$")


def _norm_key(raw: str) -> str:
    return raw.lower().replace(" ", "").replace("_", "").replace("-", "")


def plate_bbox_suggests_motorcycle(plate_bbox: Sequence[float] | None) -> bool:
    """Two-line VN motorcycle plates are taller than wide; car plates are wider."""
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
    return (h / w) >= 1.15


def vn_plate_suggests_motorcycle(plate: str | None) -> bool:
    """Heuristic for Vietnamese motorcycle plate numbers (e.g. 59B123456)."""
    if not plate:
        return False
    p = re.sub(r"[^A-Z0-9]", "", plate.upper())
    return bool(_VN_MOTO_PLATE.match(p))


def classify_vehicle(
    category: str | None,
    *,
    event_code: str | None = None,
    snap_category: str | None = None,
    vehicle_size: str | None = None,
    object_type: str | None = None,
    has_non_motor: bool = False,
    plate_number: str | None = None,
    plate_bbox: Sequence[float] | None = None,
) -> str:
    """Return vehicle_class: car | motorcycle | other | unknown."""
    code = (event_code or "").lower().replace("-", "").replace("_", "")
    if "nonmotor" in code:
        return "motorcycle"

    snap = _norm_key(snap_category or "")
    if snap in ("nonmotor", "nonmotorvehicle"):
        return "motorcycle"

    if has_non_motor:
        return "motorcycle"

    ot = _norm_key(object_type or "")
    if ot in ("nonmotor", "motorcycle", "bike"):
        return "motorcycle"

    # Camera often mis-tags motorcycles as Light-duty / SnapCategory=Motor.
    # Prefer plate geometry + VN plate shape over those weak labels.
    if plate_bbox_suggests_motorcycle(plate_bbox) or vn_plate_suggests_motorcycle(plate_number):
        return "motorcycle"

    if snap in ("motor", "motorvehicle"):
        return "car"

    if ot == "vehicle":
        return "car"

    size = _norm_key(vehicle_size or "")
    if size in ("lightduty", "mediumduty", "heavyduty", "large", "light", "medium", "heavy"):
        return "car"

    raw = (category or "").strip()
    if not raw:
        return "unknown"

    key = _norm_key(raw)
    if key in _LIST_STATUS_TYPES or key in ("null", "none", ""):
        return "unknown"

    for mk in MOTORCYCLE_KEYWORDS:
        if key == mk or (len(mk) >= 4 and mk in key):
            return "motorcycle"

    for ck in CAR_KEYWORDS:
        if key == ck or (len(ck) >= 3 and ck in key):
            return "car"

    return "other"


def vehicle_class_label_vi(vehicle_class: str | None) -> str:
    return {
        "car": "Ô tô",
        "motorcycle": "Xe máy / Non-motor",
        "other": "Khác",
        "unknown": "Chưa rõ",
    }.get(vehicle_class or "unknown", vehicle_class or "Chưa rõ")


def clean_camera_attr(value: object | None) -> str | None:
    """Drop Dahua placeholder strings like Unknown / empty."""
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    if s.lower() in ("unknown", "null", "none", "n/a", "-", "undefined"):
        return None
    return s
