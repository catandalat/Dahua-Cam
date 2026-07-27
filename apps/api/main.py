from __future__ import annotations

import csv
import io
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from dahua_client.client import DahuaClient, extract_supported_event_codes, select_subscribe_codes
from domain.db import get_session, init_db
from domain.live import live_bus
from domain.models import (
    Camera,
    CameraCaps,
    Gate,
    Lane,
    PlateListEntry,
    Site,
    TrafficFlowSample,
    VehicleDetection,
    VehicleSession,
    ViolationEvent,
)
from domain.plate import normalize_plate
from domain.schemas import DirectionRole, SessionStatus
from domain.settings import get_settings

logging.basicConfig(level=get_settings().log_level)
logger = logging.getLogger("api")

from api.features import router as features_router  # noqa: E402
from api.ingest_routes import router as ingest_router  # noqa: E402
from api.watch_routes import router as watch_router  # noqa: E402


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await init_db()
    # seed default site if empty
    async for session in get_session():
        count = await session.scalar(select(func.count()).select_from(Site))
        if not count:
            site = Site(name="Default Site")
            session.add(site)
            await session.commit()
        break
    yield
    await live_bus.close()


app = FastAPI(title="Dahua ANPR Operations", version="0.1.0", lifespan=lifespan)
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list + ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(features_router)
app.include_router(watch_router)
app.include_router(ingest_router)


# ---------- Schemas ----------


class SiteIn(BaseModel):
    name: str
    timezone: str = "Asia/Ho_Chi_Minh"


class GateIn(BaseModel):
    site_id: UUID
    name: str


class LaneIn(BaseModel):
    gate_id: UUID
    name: str
    lane_number: int | None = None


class CameraIn(BaseModel):
    site_id: UUID
    lane_id: UUID | None = None
    name: str
    host: str
    port: int = 80
    use_https: bool = False
    username: str
    password: str
    direction_role: DirectionRole = DirectionRole.ENTRY
    enabled: bool = True
    subscribe_codes: list[str] | None = None
    latitude: float | None = None
    longitude: float | None = None
    map_icon: str = "camera"
    map_note: str | None = None


class CameraUpdate(BaseModel):
    name: str | None = None
    host: str | None = None
    port: int | None = None
    use_https: bool | None = None
    username: str | None = None
    password: str | None = None
    direction_role: DirectionRole | None = None
    enabled: bool | None = None
    lane_id: UUID | None = None
    subscribe_codes: list[str] | None = None
    latitude: float | None = None
    longitude: float | None = None
    map_icon: str | None = None
    map_note: str | None = None


class CameraLocationIn(BaseModel):
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    map_icon: str | None = Field(default=None, pattern="^(camera|gate|radar|dome|ptz)$")
    map_note: str | None = None


class PlateListIn(BaseModel):
    site_id: UUID
    list_type: str = Field(pattern="^(allow|block)$")
    plate_number: str
    note: str | None = None


# ---------- Health ----------


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


# ---------- Topology ----------


@app.get("/sites")
async def list_sites(db: AsyncSession = Depends(get_session)) -> list[dict[str, Any]]:
    rows = (await db.scalars(select(Site).order_by(Site.name))).all()
    return [{"id": str(s.id), "name": s.name, "timezone": s.timezone} for s in rows]


@app.post("/sites")
async def create_site(body: SiteIn, db: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    site = Site(name=body.name, timezone=body.timezone)
    db.add(site)
    await db.commit()
    await db.refresh(site)
    return {"id": str(site.id), "name": site.name, "timezone": site.timezone}


@app.get("/gates")
async def list_gates(
    site_id: UUID | None = None,
    db: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    q = select(Gate).order_by(Gate.name)
    if site_id:
        q = q.where(Gate.site_id == site_id)
    rows = (await db.scalars(q)).all()
    return [{"id": str(g.id), "site_id": str(g.site_id), "name": g.name} for g in rows]


@app.post("/gates")
async def create_gate(body: GateIn, db: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    gate = Gate(site_id=body.site_id, name=body.name)
    db.add(gate)
    await db.commit()
    await db.refresh(gate)
    return {"id": str(gate.id), "site_id": str(gate.site_id), "name": gate.name}


@app.get("/lanes")
async def list_lanes(
    gate_id: UUID | None = None,
    db: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    q = select(Lane).order_by(Lane.name)
    if gate_id:
        q = q.where(Lane.gate_id == gate_id)
    rows = (await db.scalars(q)).all()
    return [
        {
            "id": str(l.id),
            "gate_id": str(l.gate_id),
            "name": l.name,
            "lane_number": l.lane_number,
        }
        for l in rows
    ]


@app.post("/lanes")
async def create_lane(body: LaneIn, db: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    lane = Lane(gate_id=body.gate_id, name=body.name, lane_number=body.lane_number)
    db.add(lane)
    await db.commit()
    await db.refresh(lane)
    return {
        "id": str(lane.id),
        "gate_id": str(lane.gate_id),
        "name": lane.name,
        "lane_number": lane.lane_number,
    }


def _camera_out(c: Camera) -> dict[str, Any]:
    return {
        "id": str(c.id),
        "site_id": str(c.site_id),
        "lane_id": str(c.lane_id) if c.lane_id else None,
        "name": c.name,
        "host": c.host,
        "port": c.port,
        "use_https": c.use_https,
        "username": c.username,
        "direction_role": c.direction_role,
        "enabled": c.enabled,
        "subscribe_codes": c.subscribe_codes,
        "listener_status": c.listener_status,
        "listener_error": c.listener_error,
        "last_event_at": c.last_event_at.isoformat() if c.last_event_at else None,
        "latitude": c.latitude,
        "longitude": c.longitude,
        "map_icon": getattr(c, "map_icon", None) or "camera",
        "map_note": getattr(c, "map_note", None),
        "caps": {
            "supported_codes": c.caps.supported_codes if c.caps else [],
            "probed_at": c.caps.probed_at.isoformat() if c.caps else None,
        }
        if c.caps or True
        else None,
    }


@app.get("/cameras")
async def list_cameras(db: AsyncSession = Depends(get_session)) -> list[dict[str, Any]]:
    rows = (
        await db.scalars(select(Camera).options(selectinload(Camera.caps)).order_by(Camera.name))
    ).all()
    return [_camera_out(c) for c in rows]


@app.post("/cameras")
async def create_camera(body: CameraIn, db: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    cam = Camera(
        site_id=body.site_id,
        lane_id=body.lane_id,
        name=body.name,
        host=body.host,
        port=body.port,
        use_https=body.use_https,
        username=body.username,
        password=body.password,
        direction_role=body.direction_role.value,
        enabled=body.enabled,
        subscribe_codes=body.subscribe_codes,
        latitude=body.latitude,
        longitude=body.longitude,
        map_icon=body.map_icon or "camera",
        map_note=body.map_note,
    )
    db.add(cam)
    await db.commit()
    await db.refresh(cam)
    cam = (
        await db.scalar(
            select(Camera).options(selectinload(Camera.caps)).where(Camera.id == cam.id)
        )
    )
    assert cam
    return _camera_out(cam)


@app.patch("/cameras/{camera_id}")
async def update_camera(
    camera_id: UUID,
    body: CameraUpdate,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    cam = await db.scalar(
        select(Camera).options(selectinload(Camera.caps)).where(Camera.id == camera_id)
    )
    if not cam:
        raise HTTPException(404, "Camera not found")
    data = body.model_dump(exclude_unset=True)
    if "direction_role" in data and data["direction_role"] is not None:
        data["direction_role"] = data["direction_role"].value
    if "map_icon" in data and data["map_icon"] is not None:
        if data["map_icon"] not in ("camera", "gate", "radar", "dome", "ptz"):
            raise HTTPException(400, "map_icon không hợp lệ")
    for k, v in data.items():
        setattr(cam, k, v)
    await db.commit()
    await db.refresh(cam)
    return _camera_out(cam)


@app.delete("/cameras/{camera_id}")
async def delete_camera(
    camera_id: UUID,
    db: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    cam = await db.get(Camera, camera_id)
    if not cam:
        raise HTTPException(404, "Camera not found")
    await db.delete(cam)
    await db.commit()
    return {"status": "deleted", "id": str(camera_id)}


@app.put("/cameras/{camera_id}/location")
async def set_camera_location(
    camera_id: UUID,
    body: CameraLocationIn,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    cam = await db.scalar(
        select(Camera).options(selectinload(Camera.caps)).where(Camera.id == camera_id)
    )
    if not cam:
        raise HTTPException(404, "Camera not found")
    cam.latitude = body.latitude
    cam.longitude = body.longitude
    if body.map_icon is not None:
        cam.map_icon = body.map_icon
    if body.map_note is not None:
        cam.map_note = body.map_note
    await db.commit()
    await db.refresh(cam)
    return _camera_out(cam)


@app.delete("/cameras/{camera_id}/location")
async def clear_camera_location(
    camera_id: UUID,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    cam = await db.scalar(
        select(Camera).options(selectinload(Camera.caps)).where(Camera.id == camera_id)
    )
    if not cam:
        raise HTTPException(404, "Camera not found")
    cam.latitude = None
    cam.longitude = None
    await db.commit()
    await db.refresh(cam)
    return _camera_out(cam)


@app.get("/map/cameras")
async def map_cameras(db: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    """Danh sách camera cho bản đồ (có / chưa có toạ độ)."""
    rows = (
        await db.scalars(select(Camera).options(selectinload(Camera.caps)).order_by(Camera.name))
    ).all()
    placed = [c for c in rows if c.latitude is not None and c.longitude is not None]
    unplaced = [c for c in rows if c.latitude is None or c.longitude is None]
    # Default center: HCMC; fit to placed cameras when available
    if placed:
        lats = [float(c.latitude) for c in placed if c.latitude is not None]
        lngs = [float(c.longitude) for c in placed if c.longitude is not None]
        center = {"lat": sum(lats) / len(lats), "lng": sum(lngs) / len(lngs)}
    else:
        center = {"lat": 10.7769, "lng": 106.7009}
    return {
        "center": center,
        "style_url": "https://tiles.openfreemap.org/styles/liberty",
        "placed": [_camera_out(c) for c in placed],
        "unplaced": [_camera_out(c) for c in unplaced],
    }


@app.post("/cameras/{camera_id}/probe-caps")
async def probe_caps(camera_id: UUID, db: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    cam = await db.scalar(
        select(Camera).options(selectinload(Camera.caps)).where(Camera.id == camera_id)
    )
    if not cam:
        raise HTTPException(404, "Camera not found")
    client = DahuaClient(
        cam.host,
        cam.username,
        cam.password,
        port=cam.port,
        use_https=cam.use_https,
    )
    try:
        caps = await client.get_caps()
    except Exception as exc:
        raise HTTPException(502, f"Failed to probe camera: {exc}") from exc

    supported = extract_supported_event_codes(caps)
    subscribe = select_subscribe_codes(supported, include_p1=True, include_p2=True)
    if cam.caps:
        cam.caps.raw_caps = caps
        cam.caps.supported_codes = supported
        cam.caps.probed_at = datetime.now(timezone.utc)
    else:
        db.add(
            CameraCaps(
                camera_id=cam.id,
                raw_caps=caps,
                supported_codes=supported,
            )
        )
    if not cam.subscribe_codes:
        cam.subscribe_codes = subscribe
    await db.commit()
    await db.refresh(cam)
    cam = (
        await db.scalar(
            select(Camera).options(selectinload(Camera.caps)).where(Camera.id == camera_id)
        )
    )
    assert cam
    return {
        "camera": _camera_out(cam),
        "supported_codes": supported,
        "suggested_subscribe": subscribe,
    }


# ---------- Detections / Sessions / Violations ----------


def _detection_out(d: VehicleDetection) -> dict[str, Any]:
    return {
        "id": str(d.id),
        "camera_id": str(d.camera_id),
        "site_id": str(d.site_id),
        "gate_id": str(d.gate_id) if d.gate_id else None,
        "lane_id": str(d.lane_id) if d.lane_id else None,
        "event_code": d.event_code,
        "event_utc": d.event_utc.isoformat() if d.event_utc else None,
        "plate_number": d.plate_number,
        "plate_raw": d.plate_raw,
        "vehicle_brand": d.vehicle_brand,
        "vehicle_model": d.vehicle_model,
        "vehicle_category": d.vehicle_category,
        "vehicle_class": d.vehicle_class,
        "vehicle_color": d.vehicle_color,
        "speed": d.speed,
        "lane_number": d.lane_number,
        "vehicle_direction": d.vehicle_direction,
        "passage_direction": d.passage_direction,
        "trigger_occur": d.trigger_occur,
        "seatbelt_main": d.seatbelt_main,
        "seatbelt_sub": d.seatbelt_sub,
        "calling": d.calling,
        "smoking": d.smoking,
        "image_paths": d.image_paths,
        "meta": d.meta,
        "created_at": d.created_at.isoformat() if d.created_at else None,
    }


@app.get("/detections")
async def list_detections(
    plate: str | None = None,
    site_id: UUID | None = None,
    camera_id: UUID | None = None,
    gate_id: UUID | None = None,
    vehicle_class: str | None = None,
    vehicle_color: str | None = None,
    vehicle_brand: str | None = None,
    vehicle_category: str | None = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    q: Select[Any] = select(VehicleDetection).order_by(VehicleDetection.event_utc.desc().nullslast())
    if plate:
        q = q.where(VehicleDetection.plate_number == normalize_plate(plate))
    if site_id:
        q = q.where(VehicleDetection.site_id == site_id)
    if camera_id:
        q = q.where(VehicleDetection.camera_id == camera_id)
    if gate_id:
        q = q.where(VehicleDetection.gate_id == gate_id)
    if vehicle_class:
        q = q.where(VehicleDetection.vehicle_class == vehicle_class)
    if vehicle_color:
        q = q.where(VehicleDetection.vehicle_color.ilike(vehicle_color))
    if vehicle_brand:
        q = q.where(VehicleDetection.vehicle_brand.ilike(f"%{vehicle_brand}%"))
    if vehicle_category:
        q = q.where(VehicleDetection.vehicle_category.ilike(f"%{vehicle_category}%"))
    q = q.offset(offset).limit(limit)
    rows = (await db.scalars(q)).all()
    return [_detection_out(d) for d in rows]


@app.get("/stats/vehicles")
async def stats_vehicles(
    site_id: UUID | None = None,
    days: int = Query(7, ge=1, le=90),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Breakdown by vehicle_class, color, brand."""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    base = select(VehicleDetection).where(VehicleDetection.event_utc >= since)
    if site_id:
        base = base.where(VehicleDetection.site_id == site_id)

    async def group_count(col):
        q = (
            select(col, func.count())
            .where(VehicleDetection.event_utc >= since)
            .group_by(col)
            .order_by(func.count().desc())
            .limit(30)
        )
        if site_id:
            q = q.where(VehicleDetection.site_id == site_id)
        rows = (await db.execute(q)).all()
        return [{"key": (k if k is not None else "unknown"), "count": c} for k, c in rows]

    return {
        "days": days,
        "by_class": await group_count(VehicleDetection.vehicle_class),
        "by_color": await group_count(VehicleDetection.vehicle_color),
        "by_brand": await group_count(VehicleDetection.vehicle_brand),
        "by_category": await group_count(VehicleDetection.vehicle_category),
    }


def _session_out(s: VehicleSession, overstay_hours: float) -> dict[str, Any]:
    overstay = False
    if s.status == SessionStatus.INSIDE.value and s.entered_at:
        from domain.session import is_overstay

        overstay = is_overstay(s.entered_at, overstay_hours)
    duration_sec = None
    if s.entered_at and s.exited_at:
        duration_sec = (s.exited_at - s.entered_at).total_seconds()
    return {
        "id": str(s.id),
        "site_id": str(s.site_id),
        "plate_number": s.plate_number,
        "status": s.status,
        "entered_at": s.entered_at.isoformat() if s.entered_at else None,
        "exited_at": s.exited_at.isoformat() if s.exited_at else None,
        "entry_gate_id": str(s.entry_gate_id) if s.entry_gate_id else None,
        "exit_gate_id": str(s.exit_gate_id) if s.exit_gate_id else None,
        "vehicle_brand": s.vehicle_brand,
        "vehicle_model": s.vehicle_model,
        "vehicle_color": s.vehicle_color,
        "entry_speed": s.entry_speed,
        "exit_speed": s.exit_speed,
        "overstay": overstay,
        "duration_sec": duration_sec,
    }


@app.get("/sessions")
async def list_sessions(
    status: str | None = None,
    site_id: UUID | None = None,
    plate: str | None = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    q = select(VehicleSession).order_by(VehicleSession.updated_at.desc())
    if status:
        q = q.where(VehicleSession.status == status)
    if site_id:
        q = q.where(VehicleSession.site_id == site_id)
    if plate:
        q = q.where(VehicleSession.plate_number == normalize_plate(plate))
    rows = (await db.scalars(q.offset(offset).limit(limit))).all()

    # Backfill tốc độ từ detection nếu phiên cũ chưa có entry_speed/exit_speed
    det_ids = [
        did
        for s in rows
        for did in (s.entry_detection_id, s.exit_detection_id)
        if did is not None and (
            (did == s.entry_detection_id and s.entry_speed is None)
            or (did == s.exit_detection_id and s.exit_speed is None)
        )
    ]
    speed_by_det: dict[UUID, float | None] = {}
    if det_ids:
        dets = (
            await db.scalars(select(VehicleDetection).where(VehicleDetection.id.in_(det_ids)))
        ).all()
        speed_by_det = {d.id: d.speed for d in dets}
        for s in rows:
            if s.entry_speed is None and s.entry_detection_id in speed_by_det:
                s.entry_speed = speed_by_det[s.entry_detection_id]
            if s.exit_speed is None and s.exit_detection_id in speed_by_det:
                s.exit_speed = speed_by_det[s.exit_detection_id]

    hours = get_settings().session_overstay_hours
    return [_session_out(s, hours) for s in rows]


@app.get("/sessions/stats")
async def session_stats(
    site_id: UUID | None = None,
    days: int = Query(7, ge=1, le=90),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    entry_q = select(func.count()).select_from(VehicleSession).where(
        VehicleSession.entered_at >= since
    )
    exit_q = select(func.count()).select_from(VehicleSession).where(
        VehicleSession.exited_at >= since,
        VehicleSession.status.in_(
            [SessionStatus.COMPLETED.value, SessionStatus.ORPHAN_EXIT.value]
        ),
    )
    inside_q = select(func.count()).select_from(VehicleSession).where(
        VehicleSession.status == SessionStatus.INSIDE.value
    )
    if site_id:
        entry_q = entry_q.where(VehicleSession.site_id == site_id)
        exit_q = exit_q.where(VehicleSession.site_id == site_id)
        inside_q = inside_q.where(VehicleSession.site_id == site_id)

    entries = await db.scalar(entry_q) or 0
    exits = await db.scalar(exit_q) or 0
    inside = await db.scalar(inside_q) or 0

    # hourly buckets for last 24h
    day_ago = datetime.now(timezone.utc) - timedelta(hours=24)
    det_q = (
        select(
            func.date_trunc("hour", VehicleDetection.event_utc).label("hour"),
            VehicleDetection.passage_direction,
            func.count(),
        )
        .where(VehicleDetection.event_utc >= day_ago)
        .group_by("hour", VehicleDetection.passage_direction)
        .order_by("hour")
    )
    if site_id:
        det_q = det_q.where(VehicleDetection.site_id == site_id)
    hourly_rows = (await db.execute(det_q)).all()
    hourly: list[dict[str, Any]] = []
    for hour, direction, cnt in hourly_rows:
        hourly.append(
            {
                "hour": hour.isoformat() if hour else None,
                "direction": direction,
                "count": cnt,
            }
        )

    return {
        "entries": entries,
        "exits": exits,
        "inside": inside,
        "days": days,
        "hourly": hourly,
    }


@app.get("/violations")
async def list_violations(
    type: str | None = Query(None, alias="type"),
    site_id: UUID | None = None,
    plate: str | None = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    q = select(ViolationEvent).order_by(ViolationEvent.event_utc.desc().nullslast())
    if type:
        q = q.where(ViolationEvent.violation_type == type)
    if site_id:
        q = q.where(ViolationEvent.site_id == site_id)
    if plate:
        q = q.where(ViolationEvent.plate_number == normalize_plate(plate))
    rows = (await db.scalars(q.offset(offset).limit(limit))).all()
    return [
        {
            "id": str(v.id),
            "detection_id": str(v.detection_id) if v.detection_id else None,
            "camera_id": str(v.camera_id),
            "site_id": str(v.site_id),
            "violation_type": v.violation_type,
            "plate_number": v.plate_number,
            "event_utc": v.event_utc.isoformat() if v.event_utc else None,
            "detail": v.detail,
            "image_paths": v.image_paths,
        }
        for v in rows
    ]


@app.get("/stats/overview")
async def stats_overview(
    site_id: UUID | None = None,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    det_q = select(func.count()).select_from(VehicleDetection).where(
        VehicleDetection.created_at >= since
    )
    viol_q = select(func.count()).select_from(ViolationEvent).where(
        ViolationEvent.created_at >= since
    )
    inside_q = select(func.count()).select_from(VehicleSession).where(
        VehicleSession.status == SessionStatus.INSIDE.value
    )
    cams_q = select(func.count()).select_from(Camera).where(Camera.enabled.is_(True))
    connected_q = select(func.count()).select_from(Camera).where(
        Camera.listener_status == "connected"
    )
    if site_id:
        det_q = det_q.where(VehicleDetection.site_id == site_id)
        viol_q = viol_q.where(ViolationEvent.site_id == site_id)
        inside_q = inside_q.where(VehicleSession.site_id == site_id)
        cams_q = cams_q.where(Camera.site_id == site_id)
        connected_q = connected_q.where(Camera.site_id == site_id)

    return {
        "detections_24h": await db.scalar(det_q) or 0,
        "violations_24h": await db.scalar(viol_q) or 0,
        "vehicles_inside": await db.scalar(inside_q) or 0,
        "cameras_enabled": await db.scalar(cams_q) or 0,
        "cameras_connected": await db.scalar(connected_q) or 0,
    }


@app.get("/flow-legacy")
async def list_flow_legacy(
    camera_id: UUID | None = None,
    limit: int = Query(50, ge=1, le=500),
    db: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    """Deprecated alias — use GET /flow from features router."""
    q = select(TrafficFlowSample).order_by(TrafficFlowSample.event_utc.desc().nullslast()).limit(limit)
    if camera_id:
        q = q.where(TrafficFlowSample.camera_id == camera_id)
    rows = (await db.scalars(q)).all()
    return [
        {
            "id": str(f.id),
            "camera_id": str(f.camera_id),
            "event_code": f.event_code,
            "event_utc": f.event_utc.isoformat() if f.event_utc else None,
            "lane_number": f.lane_number,
            "vehicles_num": f.vehicles_num,
            "queue_len": f.queue_len,
        }
        for f in rows
    ]


# ---------- Plate lists ----------


@app.get("/plate-lists")
async def list_plates(
    site_id: UUID | None = None,
    list_type: str | None = None,
    db: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    q = select(PlateListEntry).order_by(PlateListEntry.created_at.desc())
    if site_id:
        q = q.where(PlateListEntry.site_id == site_id)
    if list_type:
        q = q.where(PlateListEntry.list_type == list_type)
    rows = (await db.scalars(q)).all()
    return [
        {
            "id": str(p.id),
            "site_id": str(p.site_id),
            "list_type": p.list_type,
            "plate_number": p.plate_number,
            "note": p.note,
            "synced_to_camera": p.synced_to_camera,
        }
        for p in rows
    ]


@app.post("/plate-lists")
async def create_plate(body: PlateListIn, db: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    plate = normalize_plate(body.plate_number)
    if not plate:
        raise HTTPException(400, "Invalid plate")
    entry = PlateListEntry(
        site_id=body.site_id,
        list_type=body.list_type,
        plate_number=plate,
        note=body.note,
    )
    db.add(entry)
    try:
        await db.commit()
    except Exception as exc:
        await db.rollback()
        raise HTTPException(409, f"Duplicate or invalid: {exc}") from exc
    await db.refresh(entry)
    return {
        "id": str(entry.id),
        "site_id": str(entry.site_id),
        "list_type": entry.list_type,
        "plate_number": entry.plate_number,
        "note": entry.note,
    }


@app.delete("/plate-lists/{entry_id}")
async def delete_plate(entry_id: UUID, db: AsyncSession = Depends(get_session)) -> dict[str, str]:
    entry = await db.get(PlateListEntry, entry_id)
    if not entry:
        raise HTTPException(404, "Not found")
    await db.delete(entry)
    await db.commit()
    return {"status": "deleted"}


@app.post("/plate-lists/sync/{camera_id}")
async def sync_plate_lists_to_camera(
    camera_id: UUID,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Push site allow/block list entries to a camera (CGI 10.3.x best-effort)."""
    cam = await db.get(Camera, camera_id)
    if not cam:
        raise HTTPException(404, "Camera not found")
    entries = (
        await db.scalars(select(PlateListEntry).where(PlateListEntry.site_id == cam.site_id))
    ).all()
    client = DahuaClient(
        cam.host, cam.username, cam.password, port=cam.port, use_https=cam.use_https
    )
    synced = 0
    errors: list[str] = []
    for e in entries:
        list_name = "AllowList" if e.list_type == "allow" else "BlockList"
        try:
            await client.insert_traffic_list_record(
                list_type=list_name,
                plate_number=e.plate_number,
            )
            e.synced_to_camera = True
            synced += 1
        except Exception as exc:
            errors.append(f"{e.plate_number}: {exc}")
    await db.commit()
    return {"synced": synced, "errors": errors}


# ---------- Export ----------


@app.get("/export/detections.csv")
async def export_detections_csv(
    site_id: UUID | None = None,
    days: int = Query(1, ge=1, le=90),
    db: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    q = select(VehicleDetection).where(VehicleDetection.event_utc >= since).order_by(
        VehicleDetection.event_utc.desc()
    )
    if site_id:
        q = q.where(VehicleDetection.site_id == site_id)
    rows = (await db.scalars(q.limit(10_000))).all()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "id",
            "event_utc",
            "plate_number",
            "passage_direction",
            "vehicle_class",
            "vehicle_category",
            "vehicle_brand",
            "vehicle_model",
            "vehicle_color",
            "speed",
            "seatbelt_main",
            "camera_id",
            "event_code",
        ]
    )
    for d in rows:
        writer.writerow(
            [
                str(d.id),
                d.event_utc.isoformat() if d.event_utc else "",
                d.plate_number or "",
                d.passage_direction or "",
                d.vehicle_class or "",
                d.vehicle_category or "",
                d.vehicle_brand or "",
                d.vehicle_model or "",
                d.vehicle_color or "",
                d.speed or "",
                d.seatbelt_main or "",
                str(d.camera_id),
                d.event_code or "",
            ]
        )
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=detections.csv"},
    )


@app.get("/export/sessions.csv")
async def export_sessions_csv(
    site_id: UUID | None = None,
    days: int = Query(7, ge=1, le=90),
    db: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    q = select(VehicleSession).where(
        (VehicleSession.entered_at >= since) | (VehicleSession.exited_at >= since)
    )
    if site_id:
        q = q.where(VehicleSession.site_id == site_id)
    rows = (await db.scalars(q.limit(10_000))).all()
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "id",
            "plate_number",
            "status",
            "entered_at",
            "exited_at",
            "entry_speed_kmh",
            "exit_speed_kmh",
            "vehicle_brand",
            "vehicle_color",
        ]
    )
    for s in rows:
        writer.writerow(
            [
                str(s.id),
                s.plate_number,
                s.status,
                s.entered_at.isoformat() if s.entered_at else "",
                s.exited_at.isoformat() if s.exited_at else "",
                s.entry_speed if s.entry_speed is not None else "",
                s.exit_speed if s.exit_speed is not None else "",
                s.vehicle_brand or "",
                s.vehicle_color or "",
            ]
        )
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=sessions.csv"},
    )


# ---------- Media ----------


@app.get("/media/{detection_id}/{kind}")
async def get_media(detection_id: UUID, kind: str, db: AsyncSession = Depends(get_session)):
    from domain.persist import resolve_snapshot_path

    d = await db.get(VehicleDetection, detection_id)
    if not d or not d.image_paths:
        raise HTTPException(404, "Media not found")
    path = d.image_paths.get(kind)
    if not path:
        # Prefer stamped overspeed evidence when available
        path = d.image_paths.get("overspeed") or next(iter(d.image_paths.values()), None)
    if not path:
        raise HTTPException(404, "Media not found")
    fp = resolve_snapshot_path(str(path))
    if not fp.is_file():
        raise HTTPException(404, f"File missing: {path}")
    return FileResponse(fp)


# ---------- WebSocket live ----------


@app.websocket("/ws/live")
async def ws_live(websocket: WebSocket):
    import asyncio

    await websocket.accept()
    settings = get_settings()
    r = await live_bus.connect()
    pubsub = r.pubsub()
    await pubsub.subscribe(settings.live_channel)

    async def pump_redis() -> None:
        async for message in pubsub.listen():
            if message.get("type") != "message":
                continue
            data = message["data"]
            text = data if isinstance(data, str) else data.decode()
            await websocket.send_text(text)

    task = asyncio.create_task(pump_redis())
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        await pubsub.unsubscribe(settings.live_channel)
        await pubsub.aclose()
