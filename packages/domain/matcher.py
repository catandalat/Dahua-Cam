from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.models import VehicleDetection, VehicleSession
from domain.schemas import SessionStatus
from domain.session import resolve_passage_direction


async def apply_session_match(
    session: AsyncSession,
    *,
    detection: VehicleDetection,
    camera_role: str,
    overstay_hours: float = 24.0,  # noqa: ARG001 — reserved for future auto-close
) -> VehicleSession | None:
    """Open/close vehicle sessions based on entry/exit detections."""
    plate = detection.plate_number
    if not plate:
        return None

    direction = detection.passage_direction or resolve_passage_direction(
        camera_role, detection.trigger_occur
    )
    detection.passage_direction = direction
    if not direction:
        return None

    event_time = detection.event_utc or datetime.now(timezone.utc)

    if direction == "entry":
        existing = await session.scalar(
            select(VehicleSession)
            .where(
                VehicleSession.site_id == detection.site_id,
                VehicleSession.plate_number == plate,
                VehicleSession.status == SessionStatus.INSIDE.value,
            )
            .order_by(VehicleSession.entered_at.desc())
            .limit(1)
        )
        if existing:
            # Refresh metadata; keep original entered_at
            existing.vehicle_brand = detection.vehicle_brand or existing.vehicle_brand
            existing.vehicle_model = detection.vehicle_model or existing.vehicle_model
            existing.vehicle_color = detection.vehicle_color or existing.vehicle_color
            if detection.speed is not None and existing.entry_speed is None:
                existing.entry_speed = detection.speed
            return existing

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

    if direction == "exit":
        existing = await session.scalar(
            select(VehicleSession)
            .where(
                VehicleSession.site_id == detection.site_id,
                VehicleSession.plate_number == plate,
                VehicleSession.status == SessionStatus.INSIDE.value,
            )
            .order_by(VehicleSession.entered_at.desc())
            .limit(1)
        )
        if existing:
            existing.status = SessionStatus.COMPLETED.value
            existing.exited_at = event_time
            existing.exit_detection_id = detection.id
            existing.exit_gate_id = detection.gate_id
            existing.exit_speed = detection.speed
            existing.vehicle_brand = detection.vehicle_brand or existing.vehicle_brand
            existing.vehicle_model = detection.vehicle_model or existing.vehicle_model
            existing.vehicle_color = detection.vehicle_color or existing.vehicle_color
            return existing

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

    return None
