"""Normalize Dahua vehicle Category into car / motorcycle / other classes."""

from __future__ import annotations

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
)

MOTORCYCLE_KEYWORDS = (
    "motor",
    "motorcycle",
    "motorbike",
    "bike",
    "bicycle",
    "tricycle",
    "nonmotor",
    "dualtriwheel",
    "lightmotorcycle",
    "embassymotorcycle",
    "coachmotorcycle",
    "foreignmotorcycle",
    "trialmotorcycle",
    "areaoutmotorcycle",
    "marginalmotorcycle",
    "twowheel",
    "scooter",
)


def classify_vehicle(category: str | None, *, event_code: str | None = None) -> str:
    """Return vehicle_class: car | motorcycle | other | unknown."""
    raw = (category or "").strip()
    code = (event_code or "").lower()
    if "nonmotor" in code.replace("-", "") or "nonmotor" in code:
        return "motorcycle"

    if not raw:
        return "unknown"

    key = raw.lower().replace(" ", "").replace("_", "").replace("-", "")

    for mk in MOTORCYCLE_KEYWORDS:
        if mk == key or mk in key:
            return "motorcycle"

    for ck in CAR_KEYWORDS:
        if ck == key or ck in key:
            return "car"

    return "other"


def vehicle_class_label_vi(vehicle_class: str | None) -> str:
    return {
        "car": "Ô tô",
        "motorcycle": "Xe máy / Non-motor",
        "other": "Khác",
        "unknown": "Chưa rõ",
    }.get(vehicle_class or "unknown", vehicle_class or "Chưa rõ")
