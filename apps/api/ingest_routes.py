"""HTTP ingest for ANPR events — production test path without physical camera stream."""

from __future__ import annotations

import base64
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from domain.db import get_session
from domain.models import Camera
from domain.persist import persist_detection
from domain.plate import normalize_plate
from domain.vehicle_class import classify_vehicle

router = APIRouter(prefix="/ingest", tags=["ingest"])


class IngestDetectionIn(BaseModel):
    camera_id: UUID
    plate_number: str
    speed: float | None = None
    event_code: str = "TrafficJunction"
    passage_hint: str | None = None  # unused; direction from camera role
    vehicle_brand: str | None = None
    vehicle_model: str | None = None
    vehicle_category: str | None = None
    vehicle_color: str | None = None
    seatbelt_main: str | None = None
    calling: bool = False
    smoking: bool = False
    unlicensed: bool = False
    event_utc: datetime | None = None
    # optional JPEG evidence (base64) — used for overspeed stamp
    image_jpeg_base64: str | None = None
    publish: bool = True


@router.post("/detection")
async def ingest_detection(
    body: IngestDetectionIn,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    cam = await db.scalar(
        select(Camera).options(selectinload(Camera.lane)).where(Camera.id == body.camera_id)
    )
    if not cam:
        raise HTTPException(404, "Camera not found")

    plate = normalize_plate(body.plate_number)
    if not plate and not body.unlicensed:
        raise HTTPException(400, "plate_number required (or set unlicensed=true)")

    category = body.vehicle_category
    det: dict[str, Any] = {
        "event_code": body.event_code,
        "event_utc": body.event_utc or datetime.now(timezone.utc),
        "plate_raw": body.plate_number,
        "plate_number": plate,
        "speed": body.speed,
        "vehicle_brand": body.vehicle_brand,
        "vehicle_model": body.vehicle_model,
        "vehicle_category": category,
        "vehicle_class": classify_vehicle(category, event_code=body.event_code),
        "vehicle_color": body.vehicle_color,
        "seatbelt_main": body.seatbelt_main,
        "calling": body.calling,
        "smoking": body.smoking,
        "unlicensed": body.unlicensed or plate is None,
    }

    jpeg: bytes | None = None
    if body.image_jpeg_base64:
        try:
            raw = body.image_jpeg_base64
            if "," in raw[:80]:
                raw = raw.split(",", 1)[1]
            jpeg = base64.b64decode(raw)
        except Exception as exc:
            raise HTTPException(400, f"Invalid image_jpeg_base64: {exc}") from exc

    result = await persist_detection(
        db,
        cam=cam,
        det=det,
        raw_payload={"ingest": True, **body.model_dump(mode="json", exclude={"image_jpeg_base64"})},
        source_jpeg=jpeg,
        publish=body.publish,
    )
    return {"status": "ok", **{k: v for k, v in result.items() if k != "payload"}}
