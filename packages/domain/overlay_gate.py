"""Gate detections by camera overlay shapes (Dahua 0–8192 coordinates)."""

from __future__ import annotations

import math
from typing import Any, Sequence


Point = tuple[float, float]
BBox = Sequence[float]  # [x1, y1, x2, y2]

# Plate must be close to the painted line on the approach side.
# Evidence: clothing false-OCR 57R6409 was ~1418px away (tall plate); real on-line ~10–680px.
DEFAULT_LINE_THRESHOLD = 1000.0
MOTORCYCLE_LINE_THRESHOLD = 1200.0
# Wide (car) plates often OCR via ManualSnap while still approaching — allow earlier.
# Evidence: 92G15255 dist≈1576 pconf=70; 49A81434 dist≈1855 — both rejected under 1000.
APPROACH_CAR_LINE_THRESHOLD = 2000.0
# Body-only / unread plate: must be close to the line (mid-frame people ~1100px out).
NOPLATE_LINE_THRESHOLD = 900.0
# After the vehicle has crossed, late snaps can sit further past the line (e.g. 49B02391).
PAST_LINE_THRESHOLD = 2800.0
# Inbound motorcycles OCR via ManualSnap while still approaching (tall plate).
# Clothing false OCR (57R6409) was 7-char car-shaped + tall — not moto pattern.
APPROACH_MOTO_LINE_THRESHOLD = 2000.0


def bbox_center(bbox: BBox | None) -> Point | None:
    if not bbox or len(bbox) < 4:
        return None
    try:
        x1, y1, x2, y2 = (float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3]))
    except (TypeError, ValueError):
        return None
    return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)


def _bbox_sample_points(bbox: BBox) -> list[Point]:
    """Corners + centers; bottom-center approximates wheels near a ground line."""
    try:
        x1, y1, x2, y2 = (float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3]))
    except (TypeError, ValueError):
        return []
    mx, my = (x1 + x2) / 2.0, (y1 + y2) / 2.0
    return [
        (mx, my),
        (mx, y2),
        (mx, y1),
        (x1, y1),
        (x2, y1),
        (x1, y2),
        (x2, y2),
        (x1, my),
        (x2, my),
    ]


def _dist_point_to_segment(px: float, py: float, ax: float, ay: float, bx: float, by: float) -> float:
    abx, aby = bx - ax, by - ay
    apx, apy = px - ax, py - ay
    ab2 = abx * abx + aby * aby
    if ab2 <= 1e-9:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, (apx * abx + apy * aby) / ab2))
    cx, cy = ax + t * abx, ay + t * aby
    return math.hypot(px - cx, py - cy)


def _point_side_of_line(px: float, py: float, ax: float, ay: float, bx: float, by: float) -> float:
    """Signed cross product; >0 = camera-near / past side for typical L→R gate lines."""
    return (bx - ax) * (py - ay) - (by - ay) * (px - ax)


def _point_in_polygon(px: float, py: float, poly: Sequence[Sequence[float]]) -> bool:
    """Ray casting; poly is [[x,y], ...]."""
    if len(poly) < 3:
        return False
    inside = False
    n = len(poly)
    for i in range(n):
        x1, y1 = float(poly[i][0]), float(poly[i][1])
        x2, y2 = float(poly[(i + 1) % n][0]), float(poly[(i + 1) % n][1])
        if ((y1 > py) != (y2 > py)) and (px < (x2 - x1) * (py - y1) / (y2 - y1 + 1e-12) + x1):
            inside = not inside
    return inside


def _shape_points(shape: dict[str, Any]) -> list[list[float]]:
    pts = shape.get("points") or []
    out: list[list[float]] = []
    for p in pts:
        if isinstance(p, (list, tuple)) and len(p) >= 2:
            try:
                out.append([float(p[0]), float(p[1])])
            except (TypeError, ValueError):
                continue
    return out


def min_dist_to_line(bbox: BBox | None, ax: float, ay: float, bx: float, by: float) -> float | None:
    if not bbox or len(bbox) < 4:
        return None
    dists = [_dist_point_to_segment(px, py, ax, ay, bx, by) for px, py in _bbox_sample_points(bbox)]
    return min(dists) if dists else None


def _bbox_near_line(bbox: BBox | None, ax: float, ay: float, bx: float, by: float, threshold: float) -> bool:
    d = min_dist_to_line(bbox, ax, ay, bx, by)
    return d is not None and d <= threshold


def _bbox_hits_line_segment(
    bbox: BBox | None,
    ax: float,
    ay: float,
    bx: float,
    by: float,
    *,
    near_threshold: float,
    past_threshold: float,
) -> bool:
    """Keep if near the line, or already past it (late snap after crossing)."""
    if not bbox or len(bbox) < 4:
        return False
    for px, py in _bbox_sample_points(bbox):
        dist = _dist_point_to_segment(px, py, ax, ay, bx, by)
        if dist <= near_threshold:
            return True
        if _point_side_of_line(px, py, ax, ay, bx, by) > 0 and dist <= past_threshold:
            return True
    return False


def _plate_aspect_hw(plate_bbox: BBox | None) -> float | None:
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


def detection_hits_overlay(
    shapes: list[dict[str, Any]] | None,
    *,
    vehicle_bbox: BBox | None = None,
    plate_bbox: BBox | None = None,
    line_threshold: float | None = None,
    vehicle_class: str | None = None,
    plate_number: str | None = None,
) -> bool:
    """
    Return True if detection should be kept given overlay shapes.

    Rules (when overlay has shapes):
    - region: keep if vehicle/plate sample point is inside any region
    - lane_line / stop_line: when a plate bbox exists, gate on the plate only
      (giant person/vehicle boxes must not pull mid-frame OCR across the line)
    - VN motorcycle plate pattern: wider approach threshold (inbound ManualSnap)
    - tall non-moto plates (clothing OCR): strict near-line threshold
    - wide car plates: wider approach threshold
    - past side allows late snaps
    """
    if not shapes:
        return True

    if line_threshold is None:
        from domain.plate import is_valid_vn_plate, is_vn_motorcycle_plate, normalize_plate

        vc = (vehicle_class or "").lower()
        aspect = _plate_aspect_hw(plate_bbox)
        plen = len(normalize_plate(plate_number) or "")
        if plate_number and is_vn_motorcycle_plate(plate_number, plate_bbox=plate_bbox):
            # VN moto OCR (9-char or tall 8-char) — often ManualSnap before the line
            line_threshold = APPROACH_MOTO_LINE_THRESHOLD
        elif (
            aspect is not None
            and aspect >= 1.05
            and plate_number
            and is_valid_vn_plate(plate_number)
            and plen >= 8
        ):
            line_threshold = APPROACH_MOTO_LINE_THRESHOLD
        elif aspect is not None and aspect < 1.0:
            line_threshold = APPROACH_CAR_LINE_THRESHOLD
        elif vc in ("motorcycle", "nonmotor", "bike") or (aspect is not None and aspect >= 1.05):
            # Tall plate without moto number shape — keep strict (shirt OCR ~1418)
            line_threshold = MOTORCYCLE_LINE_THRESHOLD
        elif not plate_bbox:
            line_threshold = NOPLATE_LINE_THRESHOLD
        else:
            line_threshold = DEFAULT_LINE_THRESHOLD

    regions = [s for s in shapes if s.get("type") == "region" and len(_shape_points(s)) >= 3]
    lines = [
        s
        for s in shapes
        if s.get("type") in ("lane_line", "stop_line") and len(_shape_points(s)) >= 2
    ]
    if not regions and not lines:
        return True

    # Prefer plate geometry when OCR claims a plate — clothing false-reads sit
    # on the torso while a huge Vehicle box can still touch the lane line.
    if plate_bbox and len(plate_bbox) >= 4:
        boxes = [plate_bbox]
    else:
        boxes = [b for b in (vehicle_bbox, plate_bbox) if b and len(b) >= 4]
    if not boxes:
        return False

    for reg in regions:
        poly = _shape_points(reg)
        for box in boxes:
            for px, py in _bbox_sample_points(box):
                if _point_in_polygon(px, py, poly):
                    return True

    for line in lines:
        pts = _shape_points(line)
        for i in range(len(pts) - 1):
            ax, ay = pts[i]
            bx, by = pts[i + 1]
            for box in boxes:
                if _bbox_hits_line_segment(
                    box,
                    ax,
                    ay,
                    bx,
                    by,
                    near_threshold=line_threshold,
                    past_threshold=PAST_LINE_THRESHOLD,
                ):
                    return True

    return False


def overlay_gate_required(shapes: list[dict[str, Any]] | None) -> bool:
    """True when enabled overlay defines at least one gateable shape."""
    if not shapes:
        return False
    for s in shapes:
        t = s.get("type")
        pts = _shape_points(s)
        if t == "region" and len(pts) >= 3:
            return True
        if t in ("lane_line", "stop_line") and len(pts) >= 2:
            return True
    return False


# Event codes that are position-tracking / forced-snap noise, not passage events
# TrafficManualSnap is handled specially in the listener (keep when plate present).
NOISE_EVENT_CODES = {
    "TrafficVehicleInParkingSpace",
}

# Codes we accept as real passage / measurement (plus any with a plate that is not noise)
PASSAGE_EVENT_CODES = {
    "TrafficJunction",
    "TrafficCarMeasurement",
    "TrafficTollGate",
    "TrafficGate",
    "TrafficVehiclePosition",  # some firmware emit motorcycle ANPR only here
    "TrafficManualSnap",  # keep only when plate/body present (listener filters)
    "TrafficNonMotorInMotorRoute",
    "TrafficNonMotorHoldUmbrella",
    "TrafficNonMotorOverload",
    "TrafficNonMotorWithoutSafehat",
    "TrafficNonMotor",
}


def is_noise_event_code(code: str | None) -> bool:
    if not code:
        return False
    c = str(code).split(";")[0].strip()
    return c in NOISE_EVENT_CODES


def is_passage_event_code(code: str | None) -> bool:
    if not code:
        return False
    c = str(code).split(";")[0].strip()
    if c in PASSAGE_EVENT_CODES:
        return True
    # Numbered variants e.g. TrafficJunction1
    return any(c.startswith(p) for p in PASSAGE_EVENT_CODES)
