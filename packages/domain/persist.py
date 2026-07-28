"""Persist a normalized ANPR detection (shared by listener + HTTP ingest)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dahua_client.extract import extract_violations
from domain.live import live_bus
from domain.matcher import apply_session_match
from domain.models import (
    Camera,
    CameraSpeedPolicy,
    OverspeedSighting,
    RawEvent,
    VehicleDetection,
    ViolationEvent,
)
from domain.session import resolve_passage_direction
from domain.settings import get_settings
from domain.speed import evaluate_speed_policy, resolve_limits
from domain.speed_capture import save_stamped_jpeg
from domain.watch import alert_to_payload, create_watch_alerts_for_detection

OVERSPEED_FOV_WINDOW_SEC = 45.0


def _json_safe(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_json_safe(v) for v in obj]
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, uuid.UUID):
        return str(obj)
    return obj


def to_relative_snapshot_path(path: Path | str) -> str:
    """Store paths relative to SNAPSHOT_DIR when possible."""
    settings = get_settings()
    root = Path(settings.snapshot_dir).resolve()
    fp = Path(path).resolve()
    try:
        return str(fp.relative_to(root))
    except ValueError:
        return str(path)


def resolve_snapshot_path(path: str) -> Path:
    settings = get_settings()
    fp = Path(path)
    if fp.is_file():
        return fp
    candidate = Path(settings.snapshot_dir) / path
    return candidate


def build_meta(det: dict[str, Any]) -> dict[str, Any]:
    return {
        "country": det.get("country"),
        "rec_no": det.get("rec_no"),
        "count_in_group": det.get("count_in_group"),
        "index_in_group": det.get("index_in_group"),
        "front_plate_number": det.get("front_plate_number"),
        "back_plate_number": det.get("back_plate_number"),
        "front_plate_color": det.get("front_plate_color"),
        "back_plate_color": det.get("back_plate_color"),
        "plate_bbox": det.get("plate_bbox"),
        "vehicle_bbox": det.get("vehicle_bbox"),
        "trigger_type": det.get("trigger_type"),
        "physical_lane": det.get("physical_lane"),
        "sun_shade": det.get("sun_shade"),
        "speed_limit": det.get("speed_limit"),
        "speed_limit_norm": det.get("speed_limit_norm"),
        "over_speeding_pct": det.get("over_speeding_pct"),
        "under_speeding_pct": det.get("under_speeding_pct"),
        "red_light_utc": det.get("red_light_utc"),
        "unlicensed": det.get("unlicensed"),
        "vehicle_color_rgb": det.get("vehicle_color_rgb"),
        "brand_year": det.get("brand_year"),
        "sub_brand": det.get("sub_brand"),
        "pts": det.get("pts"),
        "utcms": det.get("utcms"),
    }


async def stamp_and_track_overspeed(
    db: AsyncSession,
    *,
    cam: Camera,
    detection: VehicleDetection,
    image_paths: dict[str, str],
    source_jpeg: bytes | None,
    speed: float,
    limit_max: float | None,
    base_detail: dict[str, Any],
) -> tuple[dict[str, str], dict[str, Any] | None]:
    """Update FOV peak sighting, stamp evidence image, create/update violation."""
    now = detection.event_utc or datetime.now(timezone.utc)
    plate = detection.plate_number or "UNKNOWN"
    settings = get_settings()

    sighting = await db.scalar(
        select(OverspeedSighting)
        .where(
            OverspeedSighting.camera_id == cam.id,
            OverspeedSighting.plate_number == plate,
            OverspeedSighting.active.is_(True),
        )
        .order_by(OverspeedSighting.updated_at.desc())
        .limit(1)
    )
    if sighting and sighting.peak_event_utc:
        age = (now - sighting.peak_event_utc).total_seconds()
        if age > OVERSPEED_FOV_WINDOW_SEC:
            sighting.active = False
            sighting.closed_at = now
            sighting = None

    is_new_peak = True
    peak = speed
    if sighting:
        if speed > float(sighting.peak_speed):
            peak = speed
            is_new_peak = True
        else:
            peak = float(sighting.peak_speed)
            is_new_peak = False

    stamped_paths = dict(image_paths or {})
    if (is_new_peak or not sighting) and source_jpeg:
        dest = (
            Path(settings.snapshot_dir)
            / datetime.now(timezone.utc).strftime("%Y%m%d")
            / str(cam.id)
            / str(detection.id)
            / "overspeed.jpg"
        )
        try:
            save_stamped_jpeg(
                source_jpeg,
                dest,
                speed=speed,
                peak_speed=peak,
                limit_max=limit_max,
                plate=detection.plate_number,
                captured_at=now,
                camera_name=cam.name,
            )
            stamped_paths["overspeed"] = to_relative_snapshot_path(dest)
            detection.image_paths = stamped_paths
        except Exception:
            pass

    over_pct = None
    if limit_max and limit_max > 0:
        over_pct = round(((peak - float(limit_max)) / float(limit_max)) * 100, 1)
    detail = {
        **base_detail,
        "speed": speed,
        "peak_speed": peak,
        "limit_max": limit_max,
        "over_speeding_pct": over_pct,
        "stamped": bool(stamped_paths.get("overspeed")),
        "source": base_detail.get("source") or "policy",
    }

    alert: dict[str, Any] | None = None
    if sighting and sighting.violation_id:
        ve = await db.get(ViolationEvent, sighting.violation_id)
        if ve:
            if is_new_peak:
                ve.detection_id = detection.id
                ve.event_utc = now
                ve.detail = detail
                ve.image_paths = stamped_paths or ve.image_paths
                sighting.peak_speed = peak
                sighting.peak_event_utc = now
                sighting.peak_detection_id = detection.id
                sighting.image_paths = stamped_paths
            await db.flush()
            if is_new_peak:
                alert = _speed_alert(ve, cam, plate, speed, peak, limit_max, over_pct, detection, now)
            return stamped_paths, alert

    ve = ViolationEvent(
        detection_id=detection.id,
        camera_id=cam.id,
        site_id=cam.site_id,
        violation_type="overspeed",
        plate_number=None if plate == "UNKNOWN" else plate,
        event_utc=now,
        detail=detail,
        image_paths=stamped_paths or None,
    )
    db.add(ve)
    await db.flush()

    if sighting:
        sighting.peak_speed = peak
        sighting.peak_event_utc = now
        sighting.peak_detection_id = detection.id
        sighting.violation_id = ve.id
        sighting.image_paths = stamped_paths
        sighting.limit_max = limit_max
    else:
        db.add(
            OverspeedSighting(
                camera_id=cam.id,
                site_id=cam.site_id,
                plate_number=plate,
                limit_max=limit_max,
                peak_speed=peak,
                first_speed=speed,
                first_event_utc=now,
                peak_event_utc=now,
                active=True,
                peak_detection_id=detection.id,
                violation_id=ve.id,
                image_paths=stamped_paths,
            )
        )
    await db.flush()
    alert = _speed_alert(ve, cam, plate, speed, peak, limit_max, over_pct, detection, now)
    return stamped_paths, alert


def _speed_alert(ve, cam, plate, speed, peak, limit_max, over_pct, detection, now) -> dict[str, Any]:
    return {
        "type": "speed_alert",
        "alert": {
            "id": str(ve.id),
            "kind": "overspeed",
            "plate_number": plate,
            "speed": speed,
            "peak_speed": peak,
            "limit_max": limit_max,
            "over_pct": over_pct,
            "camera_id": str(cam.id),
            "camera_name": cam.name,
            "detection_id": str(detection.id),
            "message": (
                f"Vượt tốc {plate} · {speed:.0f} km/h · đỉnh {peak:.0f} km/h"
                + (f" (ngưỡng {limit_max:.0f})" if limit_max is not None else "")
                + f" · {cam.name}"
            ),
            "event_utc": now.isoformat(),
            "updated_peak": True,
        },
    }


async def persist_detection(
    db: AsyncSession,
    *,
    cam: Camera,
    det: dict[str, Any],
    raw_payload: dict[str, Any] | None = None,
    image_paths: dict[str, str] | None = None,
    source_jpeg: bytes | None = None,
    gate_id: uuid.UUID | None = None,
    publish: bool = True,
) -> dict[str, Any]:
    """Write raw event + detection + violations/sessions/watch/speed and optionally publish live."""
    settings = get_settings()
    image_paths = dict(image_paths or {})
    # normalize any absolute paths already present
    image_paths = {k: to_relative_snapshot_path(v) for k, v in image_paths.items()}

    passage = resolve_passage_direction(
        cam.direction_role,
        det.get("trigger_occur"),
        vehicle_direction=str(det.get("vehicle_direction") or det.get("junction_direction") or "")
        or None,
    )
    meta = build_meta(det)

    raw = RawEvent(
        camera_id=cam.id,
        event_code=det.get("event_code"),
        event_utc=det.get("event_utc"),
        payload=_json_safe(raw_payload or det),
        image_paths=image_paths or None,
    )
    db.add(raw)
    await db.flush()

    detection = VehicleDetection(
        raw_event_id=raw.id,
        camera_id=cam.id,
        site_id=cam.site_id,
        gate_id=gate_id or None,
        lane_id=cam.lane_id,
        event_code=det.get("event_code"),
        event_utc=det.get("event_utc") or datetime.now(timezone.utc),
        plate_raw=det.get("plate_raw"),
        plate_number=det.get("plate_number"),
        plate_color=str(det["plate_color"]) if det.get("plate_color") is not None else None,
        plate_type=str(det["plate_type"]) if det.get("plate_type") is not None else None,
        vehicle_brand=str(det["vehicle_brand"]) if det.get("vehicle_brand") else None,
        vehicle_model=str(det["vehicle_model"]) if det.get("vehicle_model") else None,
        vehicle_category=str(det["vehicle_category"]) if det.get("vehicle_category") else None,
        vehicle_class=str(det["vehicle_class"]) if det.get("vehicle_class") else None,
        vehicle_color=str(det["vehicle_color"]) if det.get("vehicle_color") else None,
        speed=det.get("speed"),
        lane_number=det.get("lane"),
        vehicle_direction=str(det["vehicle_direction"]) if det.get("vehicle_direction") else None,
        junction_direction=str(det["junction_direction"]) if det.get("junction_direction") else None,
        trigger_occur=det.get("trigger_occur"),
        passage_direction=passage,
        group_id=det.get("group_id"),
        seatbelt_main=det.get("seatbelt_main"),
        seatbelt_sub=det.get("seatbelt_sub"),
        calling=bool(det.get("calling")),
        smoking=bool(det.get("smoking")),
        image_paths=image_paths or None,
        meta=meta,
    )
    db.add(detection)
    await db.flush()

    policy = await db.scalar(select(CameraSpeedPolicy).where(CameraSpeedPolicy.camera_id == cam.id))
    event_min, event_max = resolve_limits(
        event_limit=det.get("speed_limit"),
        policy_min=policy.min_speed if policy else None,
        policy_max=policy.max_speed if policy else None,
    )
    limit_min = float(policy.min_speed) if policy else event_min
    limit_max = float(policy.max_speed) if policy else event_max
    meta["limit_min"] = limit_min
    meta["limit_max"] = limit_max
    detection.meta = meta

    viols = extract_violations(det)
    existing = {v["violation_type"] for v in viols}
    if policy is None or policy.alert_overspeed or policy.alert_underspeed:
        viols.extend(
            evaluate_speed_policy(
                det.get("speed"),
                min_speed=limit_min,
                max_speed=limit_max,
                alert_overspeed=policy.alert_overspeed if policy else True,
                alert_underspeed=policy.alert_underspeed if policy else False,
                existing_types=existing,
                source="policy" if policy else "event_limit",
            )
        )

    speed_alerts: list[dict[str, Any]] = []
    overspeed_items = [v for v in viols if v["violation_type"] == "overspeed"]
    other_viols = [v for v in viols if v["violation_type"] != "overspeed"]

    for v in other_viols:
        ve = ViolationEvent(
            detection_id=detection.id,
            camera_id=cam.id,
            site_id=cam.site_id,
            violation_type=v["violation_type"],
            plate_number=detection.plate_number,
            event_utc=detection.event_utc,
            detail=v.get("detail"),
            image_paths=image_paths or None,
        )
        db.add(ve)
        await db.flush()
        if v["violation_type"] == "underspeed":
            detail = v.get("detail") or {}
            speed_alerts.append(
                {
                    "type": "speed_alert",
                    "alert": {
                        "id": str(ve.id),
                        "kind": "underspeed",
                        "plate_number": detection.plate_number,
                        "speed": detail.get("speed", detection.speed),
                        "limit_min": detail.get("limit_min") or limit_min,
                        "limit_max": limit_max,
                        "camera_id": str(cam.id),
                        "camera_name": cam.name,
                        "detection_id": str(detection.id),
                        "message": f"Dưới tốc {detection.plate_number or '—'} · {detail.get('speed', detection.speed)} km/h · {cam.name}",
                        "event_utc": detection.event_utc.isoformat() if detection.event_utc else None,
                    },
                }
            )

    if overspeed_items and detection.speed is not None:
        jpeg = source_jpeg
        if not jpeg:
            # synthesize a frame so stamped evidence always exists when ingesting without camera snap
            try:
                from PIL import Image
                import io

                img = Image.new("RGB", (1280, 720), color=(30, 40, 55))
                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=85)
                jpeg = buf.getvalue()
            except Exception:
                jpeg = None
        image_paths, alert = await stamp_and_track_overspeed(
            db,
            cam=cam,
            detection=detection,
            image_paths=image_paths,
            source_jpeg=jpeg,
            speed=float(detection.speed),
            limit_max=float(limit_max) if limit_max is not None else None,
            base_detail=overspeed_items[0].get("detail") or {},
        )
        if alert:
            speed_alerts.append(alert)

    session_row = await apply_session_match(
        db,
        detection=detection,
        camera_role=cam.direction_role,
        overstay_hours=settings.session_overstay_hours,
    )

    watch_alerts = await create_watch_alerts_for_detection(
        db,
        detection_id=detection.id,
        camera_id=cam.id,
        site_id=cam.site_id,
        camera_name=cam.name,
        plate_number=detection.plate_number,
        event_utc=detection.event_utc,
        passage_direction=detection.passage_direction,
        image_paths=image_paths or None,
    )

    c = await db.get(Camera, cam.id)
    if c:
        c.last_event_at = datetime.now(timezone.utc)
        if c.listener_status in ("unknown", "disconnected", "error", "connecting"):
            # don't override live listener status aggressively when ingesting via API
            if c.listener_status != "connected":
                c.listener_status = c.listener_status or "unknown"

    await db.commit()
    await db.refresh(detection)

    speed_status_val = "ok"
    if any(a["alert"]["kind"] == "overspeed" for a in speed_alerts):
        speed_status_val = "overspeed"
    elif any(a["alert"]["kind"] == "underspeed" for a in speed_alerts):
        speed_status_val = "underspeed"

    payload: dict[str, Any] = {
        "type": "detection",
        "detection": {
            "id": str(detection.id),
            "camera_id": str(cam.id),
            "site_id": str(cam.site_id),
            "plate_number": detection.plate_number,
            "event_utc": detection.event_utc.isoformat() if detection.event_utc else None,
            "passage_direction": detection.passage_direction,
            "vehicle_brand": detection.vehicle_brand,
            "vehicle_model": detection.vehicle_model,
            "vehicle_category": detection.vehicle_category,
            "vehicle_class": detection.vehicle_class,
            "vehicle_color": detection.vehicle_color,
            "speed": detection.speed,
            "speed_status": speed_status_val,
            "limit_max": limit_max,
            "limit_min": limit_min,
            "seatbelt_main": detection.seatbelt_main,
            "calling": detection.calling,
            "smoking": detection.smoking,
            "event_code": detection.event_code,
            "image_paths": detection.image_paths,
            "unlicensed": bool(det.get("unlicensed")),
            "meta": meta,
            "watched": bool(watch_alerts),
        },
    }
    if session_row:
        payload["session"] = {
            "id": str(session_row.id),
            "status": session_row.status,
            "plate_number": session_row.plate_number,
            "entry_speed": session_row.entry_speed,
            "exit_speed": session_row.exit_speed,
        }
    if viols:
        payload["violations"] = viols

    if publish:
        await live_bus.publish(payload)
        for alert in watch_alerts:
            await live_bus.publish(alert_to_payload(alert, camera_name=cam.name))
        for sa in speed_alerts:
            await live_bus.publish(sa)

    return {
        "detection_id": str(detection.id),
        "session_id": str(session_row.id) if session_row else None,
        "session_status": session_row.status if session_row else None,
        "speed": detection.speed,
        "speed_status": speed_status_val,
        "violations": [v["violation_type"] for v in viols],
        "image_paths": detection.image_paths,
        "payload": payload,
    }
