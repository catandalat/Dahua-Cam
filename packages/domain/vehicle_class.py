"""Normalize Dahua vehicle Category into car / motorcycle / truck / other classes."""

from __future__ import annotations

from typing import Sequence

from domain.plate import is_vn_motorcycle_plate, plate_bbox_is_two_line

# Exact / token matches for motor vehicles (ô tô). Avoid bare "motor" — Dahua
# SnapCategory "Motor" means motor vehicle, not motorcycle.
CAR_KEYWORDS = (
    "car",
    "sedan",
    "suv",
    "mpv",
    "van",
    "pickup",
    "taxi",
    "midibus",
    "minibus",
    "microbus",
    "vehicle",
    "motorvehicle",
    "automobile",
    "lightduty",
    "passenger",
)

TRUCK_KEYWORDS = (
    "truck",
    "lorry",
    "trailer",
    "bus",
    "largebus",
    "heavytruck",
    "mediumtruck",
    "lighttruck",
    "mediumduty",
    "heavyduty",
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


def plate_bbox_suggests_motorcycle(plate_bbox: Sequence[float] | None) -> bool:
    return plate_bbox_is_two_line(plate_bbox)


def vn_plate_suggests_motorcycle(plate: str | None, plate_bbox: Sequence[float] | None = None) -> bool:
    return is_vn_motorcycle_plate(plate, plate_bbox=plate_bbox)


def vehicle_bbox_suggests_large(vehicle_bbox: Sequence[float] | None) -> bool:
    """Wide / large body → car or truck, not motorcycle (even if plate crop looks tall)."""
    if not vehicle_bbox or len(vehicle_bbox) < 4:
        return False
    try:
        x1, y1, x2, y2 = (
            float(vehicle_bbox[0]),
            float(vehicle_bbox[1]),
            float(vehicle_bbox[2]),
            float(vehicle_bbox[3]),
        )
    except (TypeError, ValueError):
        return False
    w = abs(x2 - x1)
    h = abs(y2 - y1)
    if w < 50 or h < 50:
        return False
    # Very wide body typical of truck/car close to camera
    if w >= 3600 and (w / h) >= 1.2:
        return True
    return False


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
    plate_type: str | None = None,
    vehicle_bbox: Sequence[float] | None = None,
) -> str:
    """Return vehicle_class: car | motorcycle | truck | other | unknown.

    Dahua on this site usually sends Category=Unknown and VehicleSize=Light-duty
    for everything. Reliable signals are: NonMotor event/object, VN plate shape
    (2-line bbox / 9-char number), and Medium/Heavy duty → truck.
    """
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

    pt = _norm_key(plate_type or "")
    if pt and ("motorcycle" in pt or "nonmotor" in pt or pt in ("bike", "twowheel")):
        return "motorcycle"

    size = _norm_key(vehicle_size or "")
    if size in ("mediumduty", "heavyduty", "heavy", "medium"):
        return "truck"

    raw = (category or "").strip()
    key = _norm_key(raw) if raw else ""

    for tk in TRUCK_KEYWORDS:
        if key == tk or (len(tk) >= 4 and tk in key):
            return "truck"

    # VN moto plate number / 2-line plate — but not if body is clearly a large truck/car
    moto_plate = vn_plate_suggests_motorcycle(plate_number, plate_bbox)
    tall_plate = plate_bbox_suggests_motorcycle(plate_bbox)
    large_body = vehicle_bbox_suggests_large(vehicle_bbox)

    if moto_plate:
        return "motorcycle"
    if tall_plate and not large_body:
        return "motorcycle"
    # Tall plate on a wide large body → treat as car/truck plate crop error
    if tall_plate and large_body:
        return "truck" if size in ("mediumduty", "heavyduty") else "car"

    if snap in ("motor", "motorvehicle"):
        return "car"

    if ot == "vehicle":
        return "car"

    if size in ("lightduty", "large", "light"):
        return "car"

    if not raw:
        return "unknown"

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
        "motorcycle": "Xe máy",
        "truck": "Xe tải / bus",
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
