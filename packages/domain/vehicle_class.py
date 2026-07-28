"""Normalize Dahua vehicle Category into car / motorcycle / other classes."""

from __future__ import annotations

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


def _norm_key(raw: str) -> str:
    return raw.lower().replace(" ", "").replace("_", "").replace("-", "")


def classify_vehicle(
    category: str | None,
    *,
    event_code: str | None = None,
    snap_category: str | None = None,
    vehicle_size: str | None = None,
    object_type: str | None = None,
    has_non_motor: bool = False,
) -> str:
    """Return vehicle_class: car | motorcycle | other | unknown."""
    code = (event_code or "").lower().replace("-", "").replace("_", "")
    if "nonmotor" in code:
        return "motorcycle"

    snap = _norm_key(snap_category or "")
    if snap in ("nonmotor", "nonmotorvehicle"):
        return "motorcycle"
    if snap in ("motor", "motorvehicle"):
        return "car"

    if has_non_motor:
        return "motorcycle"

    ot = _norm_key(object_type or "")
    if ot == "vehicle":
        return "car"
    if ot in ("nonmotor", "motorcycle", "bike"):
        return "motorcycle"

    size = _norm_key(vehicle_size or "")
    if size in ("lightduty", "mediumduty", "heavyduty", "large", "light", "medium", "heavy"):
        return "car"

    raw = (category or "").strip()
    if not raw:
        return "unknown"

    key = _norm_key(raw)
    if key in _LIST_STATUS_TYPES or key in ("null", "none", ""):
        return "unknown"

    # Exact motorcycle tokens first (avoid "motor" matching "Motor" snap already handled)
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
