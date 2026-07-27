"""End-to-end ingest: detection → session speed → overspeed stamp/sighting."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from domain.db import SessionLocal, init_db
from domain.models import (
    Camera,
    CameraSpeedPolicy,
    OverspeedSighting,
    Site,
    VehicleDetection,
    VehicleSession,
    ViolationEvent,
)
from domain.persist import persist_detection, resolve_snapshot_path


@pytest.fixture
async def db_cam():
    await init_db()
    async with SessionLocal() as db:
        site = await db.scalar(select(Site).limit(1))
        if not site:
            site = Site(name=f"Test Site {uuid.uuid4().hex[:6]}")
            db.add(site)
            await db.flush()
        cam = Camera(
            site_id=site.id,
            name=f"Test Cam {uuid.uuid4().hex[:6]}",
            host="192.168.1.50",
            port=80,
            username="admin",
            password="test",
            direction_role="entry",
            enabled=True,
        )
        db.add(cam)
        await db.flush()
        db.add(
            CameraSpeedPolicy(
                camera_id=cam.id,
                min_speed=0,
                max_speed=60,
                alert_overspeed=True,
                alert_underspeed=False,
                push_to_camera=False,
            )
        )
        await db.commit()
        await db.refresh(cam)
        cam_id = cam.id
        site_id = site.id

    yield cam_id, site_id

    async with SessionLocal() as db:
        cam = await db.get(Camera, cam_id)
        if cam:
            await db.delete(cam)
            await db.commit()


@pytest.mark.asyncio
async def test_persist_overspeed_and_session_speed(db_cam):
    cam_id, _site_id = db_cam
    async with SessionLocal() as db:
        cam = await db.get(Camera, cam_id)
        assert cam
        result = await persist_detection(
            db,
            cam=cam,
            det={
                "event_code": "TrafficJunction",
                "event_utc": datetime.now(timezone.utc),
                "plate_raw": "30A-999.99",
                "plate_number": "30A99999",
                "speed": 95.0,
                "vehicle_brand": "Honda",
                "vehicle_color": "Black",
                "vehicle_category": "Car",
                "vehicle_class": "car",
            },
            publish=False,
        )

    assert result["speed"] == 95.0
    assert result["speed_status"] == "overspeed"
    assert "overspeed" in result["violations"]
    assert result["image_paths"] and result["image_paths"].get("overspeed")
    assert resolve_snapshot_path(result["image_paths"]["overspeed"]).is_file()

    async with SessionLocal() as db:
        det = await db.get(VehicleDetection, uuid.UUID(result["detection_id"]))
        assert det and det.speed == 95.0
        sess = await db.scalar(
            select(VehicleSession).where(VehicleSession.plate_number == "30A99999").limit(1)
        )
        assert sess and sess.entry_speed == 95.0
        viol = await db.scalar(
            select(ViolationEvent).where(
                ViolationEvent.plate_number == "30A99999",
                ViolationEvent.violation_type == "overspeed",
            )
        )
        assert viol and viol.detail and viol.detail.get("peak_speed") == 95.0
        sight = await db.scalar(
            select(OverspeedSighting).where(
                OverspeedSighting.plate_number == "30A99999",
                OverspeedSighting.active.is_(True),
            )
        )
        assert sight and sight.peak_speed == 95.0

        # Second event higher speed → peak updates
        cam = await db.get(Camera, cam_id)
        result2 = await persist_detection(
            db,
            cam=cam,
            det={
                "event_code": "TrafficJunction",
                "event_utc": datetime.now(timezone.utc),
                "plate_raw": "30A-999.99",
                "plate_number": "30A99999",
                "speed": 110.0,
                "vehicle_category": "Car",
                "vehicle_class": "car",
            },
            publish=False,
        )
        assert result2["speed_status"] == "overspeed"
        await db.refresh(sight)
        assert sight.peak_speed == 110.0
