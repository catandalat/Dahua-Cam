"""Plate watch / trace alerts for admin notifications."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.db import get_session
from domain.models import PlateWatch, WatchAlert
from domain.plate import normalize_plate

router = APIRouter(tags=["watch"])


class WatchIn(BaseModel):
    plate_number: str
    site_id: UUID | None = None
    label: str | None = None
    note: str | None = None
    priority: str = Field(default="normal", pattern="^(low|normal|high|critical)$")
    active: bool = True
    notify_dashboard: bool = True


class WatchUpdate(BaseModel):
    label: str | None = None
    note: str | None = None
    priority: str | None = Field(default=None, pattern="^(low|normal|high|critical)$")
    active: bool | None = None
    notify_dashboard: bool | None = None
    site_id: UUID | None = None


def _watch_out(w: PlateWatch) -> dict[str, Any]:
    return {
        "id": str(w.id),
        "site_id": str(w.site_id) if w.site_id else None,
        "plate_number": w.plate_number,
        "label": w.label,
        "note": w.note,
        "priority": w.priority,
        "active": w.active,
        "notify_dashboard": w.notify_dashboard,
        "created_at": w.created_at.isoformat() if w.created_at else None,
    }


def _alert_out(a: WatchAlert) -> dict[str, Any]:
    return {
        "id": str(a.id),
        "watch_id": str(a.watch_id),
        "detection_id": str(a.detection_id) if a.detection_id else None,
        "camera_id": str(a.camera_id),
        "site_id": str(a.site_id),
        "plate_number": a.plate_number,
        "priority": a.priority,
        "label": a.label,
        "message": a.message,
        "event_utc": a.event_utc.isoformat() if a.event_utc else None,
        "image_paths": a.image_paths,
        "read": a.read,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


@router.get("/watches")
async def list_watches(
    active: bool | None = None,
    site_id: UUID | None = None,
    db: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    q = select(PlateWatch).order_by(PlateWatch.created_at.desc())
    if active is not None:
        q = q.where(PlateWatch.active.is_(active))
    if site_id is not None:
        q = q.where(PlateWatch.site_id == site_id)
    rows = (await db.scalars(q)).all()
    return [_watch_out(w) for w in rows]


@router.post("/watches")
async def create_watch(body: WatchIn, db: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    plate = normalize_plate(body.plate_number)
    if not plate:
        raise HTTPException(400, "Biển số không hợp lệ")
    existing = await db.scalar(
        select(PlateWatch).where(
            PlateWatch.plate_number == plate,
            PlateWatch.site_id == body.site_id,
        )
    )
    if existing:
        existing.active = True
        existing.label = body.label or existing.label
        existing.note = body.note or existing.note
        existing.priority = body.priority
        existing.notify_dashboard = body.notify_dashboard
        await db.commit()
        await db.refresh(existing)
        return _watch_out(existing)

    w = PlateWatch(
        plate_number=plate,
        site_id=body.site_id,
        label=body.label,
        note=body.note,
        priority=body.priority,
        active=body.active,
        notify_dashboard=body.notify_dashboard,
    )
    db.add(w)
    await db.commit()
    await db.refresh(w)
    return _watch_out(w)


@router.patch("/watches/{watch_id}")
async def update_watch(
    watch_id: UUID,
    body: WatchUpdate,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    w = await db.get(PlateWatch, watch_id)
    if not w:
        raise HTTPException(404, "Watch not found")
    data = body.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(w, k, v)
    await db.commit()
    await db.refresh(w)
    return _watch_out(w)


@router.delete("/watches/{watch_id}")
async def delete_watch(watch_id: UUID, db: AsyncSession = Depends(get_session)) -> dict[str, str]:
    w = await db.get(PlateWatch, watch_id)
    if not w:
        raise HTTPException(404, "Watch not found")
    await db.delete(w)
    await db.commit()
    return {"status": "deleted"}


@router.get("/watch-alerts")
async def list_alerts(
    unread_only: bool = False,
    plate: str | None = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    q = select(WatchAlert).order_by(WatchAlert.created_at.desc())
    if unread_only:
        q = q.where(WatchAlert.read.is_(False))
    if plate:
        q = q.where(WatchAlert.plate_number == normalize_plate(plate))
    rows = (await db.scalars(q.offset(offset).limit(limit))).all()
    return [_alert_out(a) for a in rows]


@router.get("/watch-alerts/unread-count")
async def unread_count(db: AsyncSession = Depends(get_session)) -> dict[str, int]:
    n = await db.scalar(
        select(func.count()).select_from(WatchAlert).where(WatchAlert.read.is_(False))
    )
    return {"count": int(n or 0)}


@router.post("/watch-alerts/{alert_id}/read")
async def mark_read(alert_id: UUID, db: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    a = await db.get(WatchAlert, alert_id)
    if not a:
        raise HTTPException(404, "Alert not found")
    a.read = True
    await db.commit()
    return _alert_out(a)


@router.post("/watch-alerts/read-all")
async def mark_all_read(db: AsyncSession = Depends(get_session)) -> dict[str, int]:
    rows = (await db.scalars(select(WatchAlert).where(WatchAlert.read.is_(False)))).all()
    for a in rows:
        a.read = True
    await db.commit()
    return {"marked": len(rows)}
