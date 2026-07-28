"""Gate detections by camera overlay shapes (Dahua 0–8192 coordinates).

Preferred design: draw a detection *region* — only keep when the plate (or bike
body) is inside that polygon. Clearer and less noisy than line-distance.

Fallback: if no region is drawn, keep passages near / just past the lane line.
Do NOT let giant vehicle body boxes invent hits for cars without a plate.
"""

from __future__ import annotations

import math
from typing import Any, Sequence


Point = tuple[float, float]
BBox = Sequence[float]  # [x1, y1, x2, y2]

# Cars must be near the painted line (real on-line snaps were ~10–700px).
DEFAULT_LINE_THRESHOLD = 800.0
# Wide car plate — same strict corridor (do not allow 2000px early OCR).
APPROACH_CAR_LINE_THRESHOLD = 800.0
# Motorcycles: slightly wider; still far tighter than the old 2000/4000.
MOTORCYCLE_LINE_THRESHOLD = 1000.0
APPROACH_MOTO_LINE_THRESHOLD = 1200.0
# Body-only (no plate): only motorcycle/unlicensed very close to the line.
NOPLATE_LINE_THRESHOLD = 500.0
# Late snap after the vehicle has already crossed (past side of the line).
PAST_LINE_THRESHOLD = 2200.0


def bbox_center(bbox: BBox | None) -> Point | None:
    if not bbox or len(bbox) < 4:
        return None
    try:
        x1, y1, x2, y2 = (float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3]))
    except (TypeError, ValueError):
        return None
    return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)


def bbox_bottom_center(bbox: BBox | None) -> Point | None:
    if not bbox or len(bbox) < 4:
        return None
    try:
        x1, y1, x2, y2 = (float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3]))
    except (TypeError, ValueError):
        return None
    return ((x1 + x2) / 2.0, max(y1, y2))


def region_to_detect_quad(points: Sequence[Sequence[float]]) -> list[list[int]]:
    """Axis-aligned quad for Dahua DetectRegion (exactly 4 corners, 0–8191)."""
    xs: list[float] = []
    ys: list[float] = []
    for p in points:
        if isinstance(p, (list, tuple)) and len(p) >= 2:
            try:
                xs.append(float(p[0]))
                ys.append(float(p[1]))
            except (TypeError, ValueError):
                continue
    if len(xs) < 3:
        return [[0, 4600], [8191, 4600], [8191, 8191], [0, 8191]]
    x1 = max(0, min(8191, int(min(xs))))
    y1 = max(0, min(8191, int(min(ys))))
    x2 = max(0, min(8191, int(max(xs))))
    y2 = max(0, min(8191, int(max(ys))))
    if x2 <= x1:
        x2 = min(8191, x1 + 1)
    if y2 <= y1:
        y2 = min(8191, y1 + 1)
    return [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]


def first_overlay_region_points(shapes: list[dict[str, Any]] | None) -> list[list[float]] | None:
    if not shapes:
        return None
    for s in shapes:
        if s.get("type") != "region":
            continue
        pts = _shape_points(s)
        if len(pts) >= 3:
            return pts
    return None


def is_valid_bbox(bbox: BBox | None) -> bool:
    """Reject missing / degenerate boxes like [0,0,0,0]."""
    if not bbox or len(bbox) < 4:
        return False
    try:
        vals = [float(bbox[i]) for i in range(4)]
    except (TypeError, ValueError):
        return False
    if all(abs(v) < 1.0 for v in vals):
        return False
    w = abs(vals[2] - vals[0])
    h = abs(vals[3] - vals[1])
    return w >= 8 and h >= 8


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
    if not is_valid_bbox(bbox):
        return None
    dists = [_dist_point_to_segment(px, py, ax, ay, bx, by) for px, py in _bbox_sample_points(bbox)]  # type: ignore[arg-type]
    return min(dists) if dists else None


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
    if not is_valid_bbox(bbox):
        return False
    for px, py in _bbox_sample_points(bbox):  # type: ignore[arg-type]
        dist = _dist_point_to_segment(px, py, ax, ay, bx, by)
        if dist <= near_threshold:
            return True
        if _point_side_of_line(px, py, ax, ay, bx, by) > 0 and dist <= past_threshold:
            return True
    return False


def _plate_aspect_hw(plate_bbox: BBox | None) -> float | None:
    if not is_valid_bbox(plate_bbox):
        return None
    try:
        w = abs(float(plate_bbox[2]) - float(plate_bbox[0]))  # type: ignore[index]
        h = abs(float(plate_bbox[3]) - float(plate_bbox[1]))  # type: ignore[index]
    except (TypeError, ValueError):
        return None
    if w < 1:
        return None
    return h / w


def _gate_probe_points(
    *,
    plate_bbox: BBox | None,
    vehicle_bbox: BBox | None,
    is_bike: bool,
    region_mode: bool,
) -> list[Point]:
    """Points used to decide in-region / near-line.

    Region mode: plate center (+ bottom-center); bike without plate uses body
    center/bottom only. Avoids giant body corners poking into the polygon.
    """
    pb = plate_bbox if is_valid_bbox(plate_bbox) else None
    vb = vehicle_bbox if is_valid_bbox(vehicle_bbox) else None
    if region_mode:
        if pb is not None:
            pts: list[Point] = []
            c = bbox_center(pb)
            b = bbox_bottom_center(pb)
            if c:
                pts.append(c)
            if b and b != c:
                pts.append(b)
            # Moto: also accept when body is in the region but plate crop is
            # slightly outside (common on approach / angled snaps).
            if is_bike and vb is not None:
                vc = bbox_center(vb)
                vb_b = bbox_bottom_center(vb)
                if vc:
                    pts.append(vc)
                if vb_b and vb_b != vc:
                    pts.append(vb_b)
            return pts
        if is_bike and vb is not None:
            pts = []
            c = bbox_center(vb)
            b = bbox_bottom_center(vb)
            if c:
                pts.append(c)
            if b and b != c:
                pts.append(b)
            return pts
        return []
    if pb is not None:
        return _bbox_sample_points(pb)
    if is_bike and vb is not None:
        return _bbox_sample_points(vb)
    return []


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

    Design rules:
    - If a region exists → ONLY region containment (line distance ignored).
    - With a valid plate bbox → gate on the plate (never the giant vehicle box).
    - Cars without a plate → reject.
    - Motorcycles without a plate → body center/bottom only (region) or near line.
    - No region: near / past-line late snaps still accepted.
    """
    if not shapes:
        return True

    vc = (vehicle_class or "").lower()
    is_bike = vc in ("motorcycle", "nonmotor", "bike")
    pb = plate_bbox if is_valid_bbox(plate_bbox) else None
    vb = vehicle_bbox if is_valid_bbox(vehicle_bbox) else None

    regions = [s for s in shapes if s.get("type") == "region" and len(_shape_points(s)) >= 3]
    lines = [
        s
        for s in shapes
        if s.get("type") in ("lane_line", "stop_line") and len(_shape_points(s)) >= 2
    ]
    if not regions and not lines:
        return True

    # Region-first: drawn zone is the sole app-side gate when present.
    if regions:
        probes = _gate_probe_points(
            plate_bbox=pb, vehicle_bbox=vb, is_bike=is_bike, region_mode=True
        )
        if not probes:
            return False
        for reg in regions:
            poly = _shape_points(reg)
            for px, py in probes:
                if _point_in_polygon(px, py, poly):
                    return True
        return False

    if line_threshold is None:
        from domain.plate import is_valid_vn_plate, is_vn_motorcycle_plate, normalize_plate

        aspect = _plate_aspect_hw(pb)
        plen = len(normalize_plate(plate_number) or "")
        if plate_number and is_vn_motorcycle_plate(plate_number, plate_bbox=pb):
            line_threshold = APPROACH_MOTO_LINE_THRESHOLD
        elif (
            aspect is not None
            and aspect >= 0.90
            and plate_number
            and is_valid_vn_plate(plate_number)
            and plen >= 8
        ):
            line_threshold = APPROACH_MOTO_LINE_THRESHOLD
        elif is_bike:
            line_threshold = MOTORCYCLE_LINE_THRESHOLD if pb else NOPLATE_LINE_THRESHOLD
        elif pb is None:
            line_threshold = NOPLATE_LINE_THRESHOLD
        else:
            line_threshold = APPROACH_CAR_LINE_THRESHOLD

    if pb is not None:
        boxes = [pb]
    elif is_bike and vb is not None:
        boxes = [vb]
    else:
        return False

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
    "TrafficVehiclePosition",
    "TrafficManualSnap",
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
    return any(c.startswith(p) for p in PASSAGE_EVENT_CODES)
