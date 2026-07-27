from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.models import PlateWatch, WatchAlert
from domain.plate import normalize_plate


async def find_matching_watches(
    session: AsyncSession,
    *,
    plate_number: str | None,
    site_id: UUID,
) -> list[PlateWatch]:
    plate = normalize_plate(plate_number)
    if not plate:
        return []
    q = select(PlateWatch).where(
        PlateWatch.active.is_(True),
        PlateWatch.plate_number == plate,
        or_(PlateWatch.site_id.is_(None), PlateWatch.site_id == site_id),
    )
    return list((await session.scalars(q)).all())


async def create_watch_alerts_for_detection(
    session: AsyncSession,
    *,
    detection_id: UUID,
    camera_id: UUID,
    site_id: UUID,
    camera_name: str,
    plate_number: str | None,
    event_utc: datetime | None,
    passage_direction: str | None,
    image_paths: dict[str, Any] | None,
) -> list[WatchAlert]:
    watches = await find_matching_watches(session, plate_number=plate_number, site_id=site_id)
    if not watches:
        return []

    plate = normalize_plate(plate_number) or ""
    direction = passage_direction or "unknown"
    when = event_utc or datetime.now(timezone.utc)
    alerts: list[WatchAlert] = []
    for w in watches:
        msg = (
            f"Truy vết {plate}"
            + (f" ({w.label})" if w.label else "")
            + f" xuất hiện tại camera «{camera_name}»"
            + (f", hướng {direction}" if passage_direction else "")
            + f" lúc {when.isoformat()}"
        )
        alert = WatchAlert(
            watch_id=w.id,
            detection_id=detection_id,
            camera_id=camera_id,
            site_id=site_id,
            plate_number=plate,
            priority=w.priority,
            label=w.label,
            message=msg,
            event_utc=when,
            image_paths=image_paths,
            read=False,
        )
        session.add(alert)
        alerts.append(alert)
    await session.flush()
    return alerts


def alert_to_payload(alert: WatchAlert, *, camera_name: str | None = None) -> dict[str, Any]:
    return {
        "type": "watch_alert",
        "alert": {
            "id": str(alert.id),
            "watch_id": str(alert.watch_id),
            "detection_id": str(alert.detection_id) if alert.detection_id else None,
            "camera_id": str(alert.camera_id),
            "camera_name": camera_name,
            "site_id": str(alert.site_id),
            "plate_number": alert.plate_number,
            "priority": alert.priority,
            "label": alert.label,
            "message": alert.message,
            "event_utc": alert.event_utc.isoformat() if alert.event_utc else None,
            "image_paths": alert.image_paths,
            "read": alert.read,
            "created_at": alert.created_at.isoformat() if alert.created_at else None,
        },
    }
