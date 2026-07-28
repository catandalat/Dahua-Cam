from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.models import VehicleDetection, VehicleSession
from domain.schemas import DirectionRole, SessionStatus
from domain.session import resolve_passage_direction

# Min time between entry and exit on a single-camera gate (seconds).
# Keep below anti-spam cooldown so a real return pass can close the session.
_MIN_DWELL_SEC = 60.0


async def _find_inside(
    session: AsyncSession, *, site_id, plate: str
) -> VehicleSession | None:
    return await session.scalar(
        select(VehicleSession)
        .where(
            VehicleSession.site_id == site_id,
            VehicleSession.plate_number == plate,
            VehicleSession.status == SessionStatus.INSIDE.value,
        )
        .order_by(VehicleSession.entered_at.desc())
        .limit(1)
    )


def _close_as_exit(
    existing: VehicleSession,
    detection: VehicleDetection,
    event_time: datetime,
) -> VehicleSession:
    existing.status = SessionStatus.COMPLETED.value
    existing.exited_at = event_time
    existing.exit_detection_id = detection.id
    existing.exit_gate_id = detection.gate_id
    existing.exit_speed = detection.speed
    existing.vehicle_brand = detection.vehicle_brand or existing.vehicle_brand
    existing.vehicle_model = detection.vehicle_model or existing.vehicle_model
    existing.vehicle_color = detection.vehicle_color or existing.vehicle_color
    detection.passage_direction = "exit"
    return existing


def _refresh_inside(existing: VehicleSession, detection: VehicleDetection) -> VehicleSession:
    existing.vehicle_brand = detection.vehicle_brand or existing.vehicle_brand
    existing.vehicle_model = detection.vehicle_model or existing.vehicle_model
    existing.vehicle_color = detection.vehicle_color or existing.vehicle_color
    if detection.speed is not None and existing.entry_speed is None:
        existing.entry_speed = detection.speed
    return existing


async def apply_session_match(
    session: AsyncSession,
    *,
    detection: VehicleDetection,
    camera_role: str,
    overstay_hours: float = 24.0,  # noqa: ARG001
) -> VehicleSession | None:
    """Open/close vehicle sessions based on entry/exit detections.

    Single-camera gates often lack TriggerOccur. If the plate is already
    INSIDE for ≥60s, the next sighting closes the session as exit so
    History can show completed vào/ra pairs.
    """
    plate = detection.plate_number
    if not plate:
        return None

    role = DirectionRole(camera_role)
    direction = detection.passage_direction or resolve_passage_direction(
        camera_role,
        detection.trigger_occur,
        vehicle_direction=detection.vehicle_direction or detection.junction_direction,
    )
    existing = await _find_inside(session, site_id=detection.site_id, plate=plate)
    event_time = detection.event_utc or datetime.now(timezone.utc)

    # Explicit exit from camera
    if direction == "exit":
        if existing:
            return _close_as_exit(existing, detection, event_time)
        orphan = VehicleSession(
            site_id=detection.site_id,
            plate_number=plate,
            status=SessionStatus.ORPHAN_EXIT.value,
            exited_at=event_time,
            exit_detection_id=detection.id,
            exit_gate_id=detection.gate_id,
            vehicle_brand=detection.vehicle_brand,
            vehicle_model=detection.vehicle_model,
            vehicle_color=detection.vehicle_color,
            exit_speed=detection.speed,
        )
        session.add(orphan)
        await session.flush()
        return orphan

    # Already inside: second pass after dwell → exit (gate with one camera)
    if existing:
        entered = existing.entered_at
        if entered is not None:
            if entered.tzinfo is None:
                entered = entered.replace(tzinfo=timezone.utc)
            dwell = (event_time - entered).total_seconds()
            if dwell >= _MIN_DWELL_SEC:
                return _close_as_exit(existing, detection, event_time)
        return _refresh_inside(existing, detection)

    # Not inside — open entry (or skip pure-exit cameras without direction)
    if direction is None:
        if role == DirectionRole.EXIT:
            return None
        direction = "entry"

    if direction != "entry":
        return None

    detection.passage_direction = "entry"
    vs = VehicleSession(
        site_id=detection.site_id,
        plate_number=plate,
        status=SessionStatus.INSIDE.value,
        entered_at=event_time,
        entry_detection_id=detection.id,
        entry_gate_id=detection.gate_id,
        vehicle_brand=detection.vehicle_brand,
        vehicle_model=detection.vehicle_model,
        vehicle_color=detection.vehicle_color,
        entry_speed=detection.speed,
    )
    session.add(vs)
    await session.flush()
    return vs
