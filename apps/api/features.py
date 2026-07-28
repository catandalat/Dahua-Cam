"""Extended camera ops, flow, jam, parking, vehicle registry APIs."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from dahua_client.client import DahuaClient
from domain.db import get_session
from domain.models import (
    Camera,
    CameraOverlay,
    CameraSpeedPolicy,
    JamEvent,
    ParkingSpaceSnapshot,
    TrafficFlowSample,
    VehicleDetection,
    VehicleRegistry,
    ViolationEvent,
)
from domain.plate import normalize_plate
from domain.settings import get_settings
from domain.speed import normalize_speed_limit, resolve_limits, speed_status

logger = logging.getLogger("api.features")
router = APIRouter(tags=["features"])


def _client(cam: Camera) -> DahuaClient:
    return DahuaClient(
        cam.host,
        cam.username,
        cam.password,
        port=cam.port,
        use_https=cam.use_https,
    )


async def _cam(camera_id: UUID, db: AsyncSession) -> Camera:
    cam = await db.get(Camera, camera_id)
    if not cam:
        raise HTTPException(404, "Camera not found")
    return cam


# ---------- Camera device ops ----------


@router.get("/cameras/{camera_id}/rtsp")
async def camera_rtsp(
    camera_id: UUID,
    channel: int = 1,
    subtype: int = 0,
    db: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    cam = await _cam(camera_id, db)
    client = _client(cam)
    return {
        "rtsp_url": client.rtsp_url(channel=channel, subtype=subtype),
        "rtsp_url_sub": client.rtsp_url(channel=channel, subtype=1),
        "note": "Mở bằng VLC / go2rtc. Browser không phát RTSP trực tiếp.",
    }


@router.get("/cameras/{camera_id}/device-info")
async def camera_device_info(
    camera_id: UUID,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    cam = await _cam(camera_id, db)
    try:
        info = await _client(cam).get_traffic_device_info()
    except Exception as exc:
        raise HTTPException(502, f"Device info failed: {exc}") from exc
    return {"camera_id": str(camera_id), "info": info}


@router.get("/cameras/{camera_id}/snapshot")
async def camera_snapshot(
    camera_id: UUID,
    channel: int = 1,
    db: AsyncSession = Depends(get_session),
) -> Response:
    cam = await _cam(camera_id, db)
    try:
        data = await _client(cam).snapshot(channel=channel)
    except Exception as exc:
        raise HTTPException(502, f"Snapshot failed: {exc}") from exc
    return Response(content=data, media_type="image/jpeg")


@router.post("/cameras/{camera_id}/manual-snap")
async def camera_manual_snap(
    camera_id: UUID,
    channel: int = 1,
    db: AsyncSession = Depends(get_session),
) -> Response:
    cam = await _cam(camera_id, db)
    try:
        data = await _client(cam).manual_snap(channel=channel)
    except Exception as exc:
        raise HTTPException(502, f"Manual snap failed: {exc}") from exc
    # also persist under snapshots
    settings = get_settings()
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    path = Path(settings.snapshot_dir) / day / str(camera_id) / f"manual_{int(datetime.now().timestamp())}.jpg"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return Response(
        content=data,
        media_type="image/jpeg",
        headers={"X-Saved-Path": str(path)},
    )


@router.post("/cameras/{camera_id}/strobe/{action}")
async def camera_strobe(
    camera_id: UUID,
    action: str,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    if action not in ("open", "close"):
        raise HTTPException(400, "action must be open|close")
    cam = await _cam(camera_id, db)
    client = _client(cam)
    try:
        text = await (client.open_strobe() if action == "open" else client.close_strobe())
    except Exception as exc:
        raise HTTPException(502, str(exc)) from exc
    return {"status": "ok", "action": action, "response": text}


class SpeedLimitIn(BaseModel):
    min_speed: int = Field(0, ge=0, le=300)
    max_speed: int = Field(80, ge=1, le=300)
    channel: int = 1
    alert_overspeed: bool = True
    alert_underspeed: bool = False
    push_to_camera: bool = True


def _policy_out(cam: Camera, row: CameraSpeedPolicy | None) -> dict[str, Any]:
    return {
        "camera_id": str(cam.id),
        "camera_name": cam.name,
        "min_speed": row.min_speed if row else 0,
        "max_speed": row.max_speed if row else 80,
        "alert_overspeed": row.alert_overspeed if row else True,
        "alert_underspeed": row.alert_underspeed if row else False,
        "push_to_camera": row.push_to_camera if row else True,
        "last_synced_at": row.last_synced_at.isoformat() if row and row.last_synced_at else None,
        "updated_at": row.updated_at.isoformat() if row and row.updated_at else None,
    }


@router.get("/cameras/{camera_id}/speed-policy")
async def get_speed_policy(camera_id: UUID, db: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    cam = await _cam(camera_id, db)
    row = await db.scalar(select(CameraSpeedPolicy).where(CameraSpeedPolicy.camera_id == camera_id))
    out = _policy_out(cam, row)
    try:
        device = await _client(cam).get_speed_limit()
        out["device"] = device
        device_norm = normalize_speed_limit(
            device.get("SpeedLimit") if isinstance(device, dict) else device
        )
        out["device_norm"] = device_norm
    except Exception as exc:
        out["device_error"] = str(exc)
    return out


@router.get("/speed/policies")
async def list_speed_policies(db: AsyncSession = Depends(get_session)) -> list[dict[str, Any]]:
    cams = (await db.scalars(select(Camera).order_by(Camera.name))).all()
    policies = {
        p.camera_id: p
        for p in (await db.scalars(select(CameraSpeedPolicy))).all()
    }
    return [_policy_out(c, policies.get(c.id)) for c in cams]


@router.put("/cameras/{camera_id}/speed-policy")
@router.post("/cameras/{camera_id}/speed-limit")
async def set_speed_policy(
    camera_id: UUID,
    body: SpeedLimitIn,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    if body.min_speed > body.max_speed:
        raise HTTPException(400, "Tốc độ tối thiểu không được lớn hơn tốc độ tối đa")
    cam = await _cam(camera_id, db)
    row = await db.scalar(select(CameraSpeedPolicy).where(CameraSpeedPolicy.camera_id == camera_id))
    if row:
        row.min_speed = body.min_speed
        row.max_speed = body.max_speed
        row.alert_overspeed = body.alert_overspeed
        row.alert_underspeed = body.alert_underspeed
        row.push_to_camera = body.push_to_camera
    else:
        row = CameraSpeedPolicy(
            camera_id=camera_id,
            min_speed=body.min_speed,
            max_speed=body.max_speed,
            alert_overspeed=body.alert_overspeed,
            alert_underspeed=body.alert_underspeed,
            push_to_camera=body.push_to_camera,
        )
        db.add(row)

    device_response: str | None = None
    device_error: str | None = None
    if body.push_to_camera:
        try:
            device_response = await _client(cam).set_speed_limit(
                min_speed=body.min_speed,
                max_speed=body.max_speed,
                channel=body.channel,
            )
            if body.alert_underspeed:
                await _client(cam).set_under_speed_enable(True, body.channel)
            row.last_synced_at = datetime.now(timezone.utc)
        except Exception as exc:
            device_error = str(exc)

    await db.commit()
    out = _policy_out(cam, row)
    out["status"] = "ok"
    if device_response is not None:
        out["device_response"] = device_response
    if device_error:
        out["device_error"] = device_error
        out["warning"] = "Đã lưu ngưỡng trên hệ thống; đồng bộ camera thất bại"
    return out


@router.get("/cameras/{camera_id}/speed-limit")
async def get_speed_limit(camera_id: UUID, db: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    """Tương thích cũ — trả policy + dữ liệu thiết bị nếu có."""
    return await get_speed_policy(camera_id, db)


@router.post("/cameras/{camera_id}/under-speed")
async def set_under_speed(
    camera_id: UUID,
    enable: bool = True,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    cam = await _cam(camera_id, db)
    row = await db.scalar(select(CameraSpeedPolicy).where(CameraSpeedPolicy.camera_id == camera_id))
    if row:
        row.alert_underspeed = enable
    else:
        row = CameraSpeedPolicy(camera_id=camera_id, alert_underspeed=enable)
        db.add(row)
    try:
        text = await _client(cam).set_under_speed_enable(enable)
        row.last_synced_at = datetime.now(timezone.utc)
    except Exception as exc:
        await db.commit()
        raise HTTPException(502, str(exc)) from exc
    await db.commit()
    return {"status": "ok", "enable": enable, "response": text}


@router.get("/speed/stats")
async def speed_stats(
    hours: int = Query(24, ge=1, le=168),
    camera_id: UUID | None = None,
    site_id: UUID | None = None,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    dq = select(VehicleDetection).where(
        VehicleDetection.event_utc >= since,
        VehicleDetection.speed.is_not(None),
    )
    if camera_id:
        dq = dq.where(VehicleDetection.camera_id == camera_id)
    if site_id:
        dq = dq.where(VehicleDetection.site_id == site_id)
    dets = (await db.scalars(dq.order_by(VehicleDetection.event_utc.desc()).limit(5000))).all()

    speeds = [float(d.speed) for d in dets if d.speed is not None and float(d.speed) > 0]
    vq = select(ViolationEvent).where(
        ViolationEvent.event_utc >= since,
        ViolationEvent.violation_type.in_(["overspeed", "underspeed"]),
    )
    if camera_id:
        vq = vq.where(ViolationEvent.camera_id == camera_id)
    if site_id:
        vq = vq.where(ViolationEvent.site_id == site_id)
    viols = (await db.scalars(vq)).all()
    over = sum(1 for v in viols if v.violation_type == "overspeed")
    under = sum(1 for v in viols if v.violation_type == "underspeed")

    return {
        "hours": hours,
        "samples": len(speeds),
        "avg_speed": round(sum(speeds) / len(speeds), 1) if speeds else None,
        "max_speed": max(speeds) if speeds else None,
        "min_speed": min(speeds) if speeds else None,
        "overspeed_count": over,
        "underspeed_count": under,
    }


@router.get("/speed/sightings")
async def list_overspeed_sightings(
    limit: int = Query(50, ge=1, le=200),
    camera_id: UUID | None = None,
    active: bool | None = None,
    db: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    from domain.models import OverspeedSighting

    q = select(OverspeedSighting).order_by(OverspeedSighting.peak_event_utc.desc().nullslast()).limit(limit)
    if camera_id:
        q = q.where(OverspeedSighting.camera_id == camera_id)
    if active is not None:
        q = q.where(OverspeedSighting.active.is_(active))
    rows = (await db.scalars(q)).all()
    cams = {c.id: c for c in (await db.scalars(select(Camera))).all()}
    return [
        {
            "id": str(s.id),
            "camera_id": str(s.camera_id),
            "camera_name": cams[s.camera_id].name if s.camera_id in cams else None,
            "plate_number": s.plate_number,
            "peak_speed": s.peak_speed,
            "first_speed": s.first_speed,
            "limit_max": s.limit_max,
            "active": s.active,
            "first_event_utc": s.first_event_utc.isoformat() if s.first_event_utc else None,
            "peak_event_utc": s.peak_event_utc.isoformat() if s.peak_event_utc else None,
            "closed_at": s.closed_at.isoformat() if s.closed_at else None,
            "detection_id": str(s.peak_detection_id) if s.peak_detection_id else None,
            "violation_id": str(s.violation_id) if s.violation_id else None,
            "image_paths": s.image_paths,
        }
        for s in rows
    ]


@router.get("/speed/measurements")
async def speed_measurements(
    limit: int = Query(50, ge=1, le=200),
    camera_id: UUID | None = None,
    site_id: UUID | None = None,
    only_violations: bool = False,
    db: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    policies = {
        p.camera_id: p
        for p in (await db.scalars(select(CameraSpeedPolicy))).all()
    }
    cams = {c.id: c for c in (await db.scalars(select(Camera))).all()}

    q = (
        select(VehicleDetection)
        .where(
            VehicleDetection.speed.is_not(None),
            VehicleDetection.speed > 0,
        )
        .order_by(VehicleDetection.event_utc.desc().nullslast())
        .limit(limit * 3 if only_violations else limit)
    )
    if camera_id:
        q = q.where(VehicleDetection.camera_id == camera_id)
    if site_id:
        q = q.where(VehicleDetection.site_id == site_id)
    rows = (await db.scalars(q)).all()

    out: list[dict[str, Any]] = []
    for d in rows:
        pol = policies.get(d.camera_id)
        meta = d.meta or {}
        min_s, max_s = resolve_limits(
            event_limit=meta.get("speed_limit"),
            policy_min=pol.min_speed if pol else None,
            policy_max=pol.max_speed if pol else None,
        )
        # Prefer policy max when set (admin configured)
        if pol:
            min_s = float(pol.min_speed)
            max_s = float(pol.max_speed)
        status = speed_status(d.speed, min_speed=min_s, max_speed=max_s)
        if only_violations and status == "ok":
            continue
        cam = cams.get(d.camera_id)
        out.append(
            {
                "id": str(d.id),
                "camera_id": str(d.camera_id),
                "camera_name": cam.name if cam else None,
                "plate_number": d.plate_number,
                "speed": d.speed,
                "limit_min": min_s,
                "limit_max": max_s,
                "status": status,
                "over_pct": (
                    round(((float(d.speed) - float(max_s)) / float(max_s)) * 100, 1)
                    if d.speed is not None and max_s and float(d.speed) > float(max_s)
                    else None
                ),
                "event_utc": d.event_utc.isoformat() if d.event_utc else None,
                "vehicle_class": d.vehicle_class,
                "image_paths": d.image_paths,
            }
        )
        if len(out) >= limit:
            break
    return out


class UnlicensedIn(BaseModel):
    enable: bool = True
    channel: int = 1


@router.post("/cameras/{camera_id}/unlicensed-detection")
async def set_unlicensed(
    camera_id: UUID,
    body: UnlicensedIn,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    cam = await _cam(camera_id, db)
    try:
        text = await _client(cam).set_unlicensed_detection(body.enable, body.channel)
    except Exception as exc:
        raise HTTPException(502, str(exc)) from exc
    return {"status": "ok", "enable": body.enable, "response": text}


# ---------- Flow / Jam ----------


@router.get("/flow")
async def list_flow(
    camera_id: UUID | None = None,
    site_id: UUID | None = None,
    limit: int = Query(100, ge=1, le=1000),
    db: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    q = select(TrafficFlowSample).order_by(TrafficFlowSample.event_utc.desc().nullslast()).limit(limit)
    if camera_id:
        q = q.where(TrafficFlowSample.camera_id == camera_id)
    if site_id:
        q = q.where(TrafficFlowSample.site_id == site_id)
    rows = (await db.scalars(q)).all()
    return [
        {
            "id": str(f.id),
            "camera_id": str(f.camera_id),
            "site_id": str(f.site_id),
            "event_code": f.event_code,
            "event_utc": f.event_utc.isoformat() if f.event_utc else None,
            "lane_number": f.lane_number,
            "vehicles_num": f.vehicles_num,
            "queue_len": f.queue_len,
            "direction": f.direction,
        }
        for f in rows
    ]


@router.get("/flow/by-lane")
async def flow_by_lane(
    hours: int = Query(24, ge=1, le=168),
    site_id: UUID | None = None,
    db: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    q = (
        select(
            TrafficFlowSample.lane_number,
            TrafficFlowSample.direction,
            func.coalesce(func.sum(TrafficFlowSample.vehicles_num), 0),
            func.count(),
        )
        .where(TrafficFlowSample.event_utc >= since)
        .group_by(TrafficFlowSample.lane_number, TrafficFlowSample.direction)
        .order_by(TrafficFlowSample.lane_number)
    )
    if site_id:
        q = q.where(TrafficFlowSample.site_id == site_id)
    rows = (await db.execute(q)).all()
    return [
        {
            "lane_number": lane,
            "direction": direction,
            "vehicles_sum": int(total or 0),
            "samples": int(cnt or 0),
        }
        for lane, direction, total, cnt in rows
    ]


@router.post("/cameras/{camera_id}/flow/pull-history")
async def pull_flow_history(
    camera_id: UUID,
    hours: float = 2.0,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    cam = await _cam(camera_id, db)
    client = _client(cam)
    end = datetime.now(timezone.utc)
    start = end - timedelta(hours=hours)
    fmt = "%Y-%m-%d %H:%M:%S"
    try:
        text = await client.start_traffic_stat_search(
            start_time=start.strftime(fmt),
            end_time=end.strftime(fmt),
        )
        # object id often in result=
        from dahua_client.kv_parser import kv_lines_to_dict

        data = kv_lines_to_dict(text)
        obj = str(data.get("result") or data.get("object") or "")
        found = 0
        if obj:
            stats = await client.get_traffic_statistics(obj, count=200)
            # store raw as one sample batch
            db.add(
                TrafficFlowSample(
                    camera_id=cam.id,
                    site_id=cam.site_id,
                    event_code="TrafficFlowHistory",
                    event_utc=datetime.now(timezone.utc),
                    vehicles_num=None,
                    payload=stats,
                )
            )
            await db.commit()
            found = int(stats.get("found") or stats.get("count") or 1)
            await client.end_traffic_stat_search(obj)
        return {"status": "ok", "object": obj, "found": found, "raw_start": data}
    except Exception as exc:
        raise HTTPException(502, f"Flow history failed: {exc}") from exc


@router.get("/jams")
async def list_jams(
    camera_id: UUID | None = None,
    limit: int = Query(50, ge=1, le=500),
    db: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    q = select(JamEvent).order_by(JamEvent.event_utc.desc().nullslast()).limit(limit)
    if camera_id:
        q = q.where(JamEvent.camera_id == camera_id)
    rows = (await db.scalars(q)).all()
    return [
        {
            "id": str(j.id),
            "camera_id": str(j.camera_id),
            "event_code": j.event_code,
            "event_utc": j.event_utc.isoformat() if j.event_utc else None,
            "lane_number": j.lane_number,
            "jam_length_pct": j.jam_length_pct,
            "jam_real_length_m": j.jam_real_length_m,
        }
        for j in rows
    ]


# ---------- Parking ----------


@router.get("/cameras/{camera_id}/parking")
async def get_parking(
    camera_id: UUID,
    persist: bool = True,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    cam = await _cam(camera_id, db)
    try:
        status = await _client(cam).get_parking_space_status()
    except Exception as exc:
        raise HTTPException(502, f"Parking API unavailable on this camera: {exc}") from exc
    if persist:
        db.add(
            ParkingSpaceSnapshot(
                camera_id=cam.id,
                site_id=cam.site_id,
                payload=status,
            )
        )
        await db.commit()
    return {"camera_id": str(camera_id), "status": status}


@router.get("/parking/snapshots")
async def parking_snapshots(
    camera_id: UUID | None = None,
    limit: int = 20,
    db: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    q = select(ParkingSpaceSnapshot).order_by(ParkingSpaceSnapshot.created_at.desc()).limit(limit)
    if camera_id:
        q = q.where(ParkingSpaceSnapshot.camera_id == camera_id)
    rows = (await db.scalars(q)).all()
    return [
        {
            "id": str(p.id),
            "camera_id": str(p.camera_id),
            "created_at": p.created_at.isoformat() if p.created_at else None,
            "payload": p.payload,
        }
        for p in rows
    ]


# ---------- Vehicle registry (10.7 mirror) ----------


class RegistryIn(BaseModel):
    site_id: UUID
    plate_number: str
    group_name: str = "default"
    brand: str | None = None
    color: str | None = None
    note: str | None = None


@router.get("/vehicle-registry")
async def list_registry(
    site_id: UUID | None = None,
    db: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    q = select(VehicleRegistry).order_by(VehicleRegistry.created_at.desc())
    if site_id:
        q = q.where(VehicleRegistry.site_id == site_id)
    rows = (await db.scalars(q)).all()
    return [
        {
            "id": str(r.id),
            "site_id": str(r.site_id),
            "group_name": r.group_name,
            "plate_number": r.plate_number,
            "brand": r.brand,
            "color": r.color,
            "note": r.note,
            "synced_to_camera": r.synced_to_camera,
        }
        for r in rows
    ]


@router.post("/vehicle-registry")
async def create_registry(
    body: RegistryIn,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    plate = normalize_plate(body.plate_number)
    if not plate:
        raise HTTPException(400, "Invalid plate")
    row = VehicleRegistry(
        site_id=body.site_id,
        group_name=body.group_name,
        plate_number=plate,
        brand=body.brand,
        color=body.color,
        note=body.note,
    )
    db.add(row)
    try:
        await db.commit()
    except Exception as exc:
        await db.rollback()
        raise HTTPException(409, str(exc)) from exc
    await db.refresh(row)
    return {
        "id": str(row.id),
        "plate_number": row.plate_number,
        "group_name": row.group_name,
    }


@router.delete("/vehicle-registry/{entry_id}")
async def delete_registry(entry_id: UUID, db: AsyncSession = Depends(get_session)) -> dict[str, str]:
    row = await db.get(VehicleRegistry, entry_id)
    if not row:
        raise HTTPException(404, "Not found")
    await db.delete(row)
    await db.commit()
    return {"status": "deleted"}


@router.post("/vehicle-registry/sync/{camera_id}")
async def sync_registry_to_camera(
    camera_id: UUID,
    group_id: str = "00001",
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    cam = await _cam(camera_id, db)
    rows = (
        await db.scalars(select(VehicleRegistry).where(VehicleRegistry.site_id == cam.site_id))
    ).all()
    client = _client(cam)
    synced = 0
    errors: list[str] = []
    for r in rows:
        try:
            await client.add_vehicle_record(group_id=group_id, plate_number=r.plate_number)
            r.synced_to_camera = True
            synced += 1
        except Exception as exc:
            errors.append(f"{r.plate_number}: {exc}")
    await db.commit()
    return {"synced": synced, "errors": errors}


@router.get("/cameras/{camera_id}/vehicle-groups")
async def camera_vehicle_groups(
    camera_id: UUID,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    cam = await _cam(camera_id, db)
    try:
        return await _client(cam).search_vehicle_groups()
    except Exception as exc:
        raise HTTPException(502, f"Vehicle Manager unavailable: {exc}") from exc


# ---------- Overlays (vạch / vùng quan sát) ----------


class OverlayIn(BaseModel):
    shapes: list[dict[str, Any]] = Field(default_factory=list)
    enabled: bool = True


@router.get("/cameras/{camera_id}/overlay")
async def get_overlay(camera_id: UUID, db: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    await _cam(camera_id, db)
    row = await db.scalar(select(CameraOverlay).where(CameraOverlay.camera_id == camera_id))
    if not row:
        return {"camera_id": str(camera_id), "shapes": [], "enabled": True}
    shapes = row.shapes.get("shapes", row.shapes) if isinstance(row.shapes, dict) else []
    if not isinstance(shapes, list):
        shapes = []
    return {
        "camera_id": str(camera_id),
        "shapes": shapes,
        "enabled": row.enabled,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


@router.put("/cameras/{camera_id}/overlay")
async def put_overlay(
    camera_id: UUID,
    body: OverlayIn,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    await _cam(camera_id, db)
    # Validate shapes: points in 0..8192
    cleaned: list[dict[str, Any]] = []
    for s in body.shapes:
        stype = str(s.get("type") or "lane_line")
        if stype not in ("lane_line", "stop_line", "region"):
            raise HTTPException(400, f"Loại vạch không hợp lệ: {stype}")
        pts = s.get("points") or []
        if not isinstance(pts, list) or len(pts) < 2:
            raise HTTPException(400, "Mỗi vạch cần ít nhất 2 điểm")
        if stype == "region" and len(pts) < 3:
            raise HTTPException(400, "Vùng phát hiện cần ít nhất 3 điểm")
        norm_pts: list[list[int]] = []
        for p in pts:
            if not isinstance(p, (list, tuple)) or len(p) < 2:
                raise HTTPException(400, "Điểm không hợp lệ")
            x, y = int(p[0]), int(p[1])
            x = max(0, min(8192, x))
            y = max(0, min(8192, y))
            norm_pts.append([x, y])
        cleaned.append(
            {
                "id": str(s.get("id") or f"s{len(cleaned)+1}"),
                "type": stype,
                "label": str(s.get("label") or ""),
                "color": str(s.get("color") or ""),
                "points": norm_pts,
            }
        )

    row = await db.scalar(select(CameraOverlay).where(CameraOverlay.camera_id == camera_id))
    payload = {"shapes": cleaned}
    if row:
        row.shapes = payload
        row.enabled = body.enabled
    else:
        row = CameraOverlay(camera_id=camera_id, shapes=payload, enabled=body.enabled)
        db.add(row)
    await db.commit()

    # Push lane_line / region to camera DetectLine + DetectRegion
    cam_sync: dict[str, Any] = {"pushed": False}
    lane = next((s for s in cleaned if s.get("type") == "lane_line" and len(s.get("points") or []) >= 2), None)
    from domain.overlay_gate import first_overlay_region_points, region_to_detect_quad

    region_pts = first_overlay_region_points(cleaned)
    detect_quad = region_to_detect_quad(region_pts) if region_pts else None
    if not lane and detect_quad:
        lane_pts = [detect_quad[3], detect_quad[2]]
    elif lane:
        lane_pts = lane["points"]
    else:
        lane_pts = None

    if lane_pts and body.enabled:
        cam = await _cam(camera_id, db)
        client = DahuaClient(
            cam.host, cam.username, cam.password, port=cam.port, use_https=cam.use_https, timeout=12.0
        )
        try:
            res = await client.sync_tollgate_detect_line(
                lane_pts[0],
                lane_pts[1],
                bidirectional=True,
                snap_motor=True,
                detect_region=detect_quad,
            )
            cam_sync = {
                "pushed": True,
                "result": (res or "").strip(),
                "direction": "Obverse+Reverse",
                "detect_region": bool(detect_quad and region_pts),
            }
            logger.info(
                "Synced DetectLine+region on cam=%s region=%s → %s",
                cam.name,
                cam_sync["detect_region"],
                cam_sync["result"],
            )
        except Exception as exc:
            cam_sync = {"pushed": False, "error": str(exc)}
            logger.warning("DetectLine sync failed cam=%s: %s", cam.name, exc)

    return {
        "camera_id": str(camera_id),
        "shapes": cleaned,
        "enabled": body.enabled,
        "camera_sync": cam_sync,
    }


@router.get("/cameras/{camera_id}/live-detections")
async def camera_live_detections(
    camera_id: UUID,
    limit: int = Query(5, ge=1, le=50),
    max_age_sec: int = Query(12, ge=1, le=300),
    db: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    """Nhận diện rất gần đây theo created_at (tránh event_utc lệch làm kẹt bbox)."""
    await _cam(camera_id, db)
    since = datetime.now(timezone.utc) - timedelta(seconds=max_age_sec)
    rows = (
        await db.scalars(
            select(VehicleDetection)
            .where(
                VehicleDetection.camera_id == camera_id,
                VehicleDetection.created_at >= since,
                VehicleDetection.plate_number.is_not(None),
            )
            .order_by(VehicleDetection.created_at.desc())
            .limit(limit)
        )
    ).all()
    out: list[dict[str, Any]] = []
    for d in rows:
        meta = d.meta or {}
        out.append(
            {
                "id": str(d.id),
                "plate_number": d.plate_number,
                "event_utc": d.event_utc.isoformat() if d.event_utc else None,
                "vehicle_class": d.vehicle_class,
                "vehicle_brand": d.vehicle_brand,
                "vehicle_color": d.vehicle_color,
                "speed": d.speed,
                "passage_direction": d.passage_direction,
                "plate_bbox": meta.get("plate_bbox"),
                "vehicle_bbox": meta.get("vehicle_bbox"),
                "image_paths": d.image_paths,
            }
        )
    return out
