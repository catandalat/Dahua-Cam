"""Gate detections by camera overlay shapes (Dahua 0–8192 coordinates)."""

from __future__ import annotations

import math
from typing import Any, Sequence


Point = tuple[float, float]
BBox = Sequence[float]  # [x1, y1, x2, y2]

# ~20% of frame — motorcycles are small and often snap slightly off the painted line
DEFAULT_LINE_THRESHOLD = 1600.0
MOTORCYCLE_LINE_THRESHOLD = 2200.0


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


def _bbox_near_line(bbox: BBox | None, ax: float, ay: float, bx: float, by: float, threshold: float) -> bool:
    if not bbox or len(bbox) < 4:
        return False
    for px, py in _bbox_sample_points(bbox):
        if _dist_point_to_segment(px, py, ax, ay, bx, by) <= threshold:
            return True
    return False


def detection_hits_overlay(
    shapes: list[dict[str, Any]] | None,
    *,
    vehicle_bbox: BBox | None = None,
    plate_bbox: BBox | None = None,
    line_threshold: float | None = None,
    vehicle_class: str | None = None,
) -> bool:
    """
    Return True if detection should be kept given overlay shapes.

    Rules (when overlay has shapes):
    - region: keep if vehicle/plate sample point is inside any region
    - lane_line / stop_line: keep if vehicle or plate bbox is within threshold
      of any line segment (corners + bottom-center)
    - motorcycles use a wider threshold (small bbox / late plate read)
    """
    if not shapes:
        return True

    if line_threshold is None:
        line_threshold = (
            MOTORCYCLE_LINE_THRESHOLD
            if (vehicle_class or "").lower() in ("motorcycle", "nonmotor", "bike")
            else DEFAULT_LINE_THRESHOLD
        )

    regions = [s for s in shapes if s.get("type") == "region" and len(_shape_points(s)) >= 3]
    lines = [
        s
        for s in shapes
        if s.get("type") in ("lane_line", "stop_line") and len(_shape_points(s)) >= 2
    ]
    if not regions and not lines:
        return True

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
                if _bbox_near_line(box, ax, ay, bx, by, line_threshold):
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
NOISE_EVENT_CODES = {
    "TrafficVehiclePosition",
    "TrafficVehicleInParkingSpace",
    "TrafficManualSnap",
}

# Codes we accept as real passage / measurement (plus any with a plate that is not noise)
PASSAGE_EVENT_CODES = {
    "TrafficJunction",
    "TrafficCarMeasurement",
    "TrafficTollGate",
    "TrafficGate",
    "TrafficNonMotorInMotorRoute",
    "TrafficNonMotorHoldUmbrella",
    "TrafficNonMotorOverload",
    "TrafficNonMotorWithoutSafehat",
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
