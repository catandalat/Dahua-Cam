from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from dahua_client.client import DahuaClient, select_subscribe_codes
from dahua_client.extract import (
    extract_detection,
    extract_flow_sample,
    extract_jam_event,
)
from dahua_client.multipart import MultipartEvent
from domain.db import SessionLocal, init_db
from domain.live import live_bus
from domain.models import (
    Camera,
    CameraOverlay,
    JamEvent,
    Lane,
    TrafficFlowSample,
    VehicleDetection,
    ViolationEvent,
)
from domain.overlay_gate import (
    detection_hits_overlay,
    is_noise_event_code,
    is_passage_event_code,
    overlay_gate_required,
)
from domain.persist import persist_detection, to_relative_snapshot_path
from domain.session import should_dedupe
from domain.settings import get_settings

logging.basicConfig(
    level=get_settings().log_level,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("listener")


class CameraWorker:
    def __init__(self, camera_id: uuid.UUID):
        self.camera_id = camera_id
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self._last_plate: str | None = None
        self._last_group_id: int | None = None
        self._last_utc: datetime | None = None

    def start(self) -> None:
        self._stop.clear()
        self._task = asyncio.create_task(self._run_loop(), name=f"cam-{self.camera_id}")

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _run_loop(self) -> None:
        backoff = 2.0
        while not self._stop.is_set():
            try:
                await self._attach_once()
                backoff = 2.0
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.exception("Camera %s stream error: %s", self.camera_id, exc)
                await self._set_status("error", str(exc))
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60.0)

    async def _load_camera(self) -> Camera | None:
        async with SessionLocal() as db:
            return await db.scalar(
                select(Camera)
                .options(selectinload(Camera.caps), selectinload(Camera.lane).selectinload(Lane.gate))
                .where(Camera.id == self.camera_id)
            )

    async def _set_status(self, status: str, error: str | None = None) -> None:
        async with SessionLocal() as db:
            cam = await db.get(Camera, self.camera_id)
            if not cam:
                return
            cam.listener_status = status
            cam.listener_error = error
            if status == "connected":
                cam.last_event_at = datetime.now(timezone.utc)
            await db.commit()

    async def _attach_once(self) -> None:
        cam = await self._load_camera()
        if not cam or not cam.enabled:
            await asyncio.sleep(5)
            return

        codes = cam.subscribe_codes
        if not codes:
            supported = cam.caps.supported_codes if cam.caps else None
            codes = select_subscribe_codes(supported, include_p1=True, include_p2=True)

        client = DahuaClient(
            cam.host,
            cam.username,
            cam.password,
            port=cam.port,
            use_https=cam.use_https,
            timeout=30.0,
        )
        logger.info("Connecting camera %s (%s) codes=%s", cam.name, cam.host, codes)
        await self._set_status("connecting")

        # Sync camera wall clock to VN local time (fixes OSD year 2024 / wrong event times)
        try:
            before = await client.get_current_time()
            await client.set_current_time()
            after = await client.get_current_time()
            logger.info("Synced camera clock %s: %s → %s", cam.name, before, after)
        except Exception as exc:
            logger.warning("Could not sync camera clock %s: %s", cam.name, exc)

        # Push system direction_role + overlay lane onto camera DetectLine
        # (Dahua Obverse-only ignores exit even when app is set bidirectional)
        await self._sync_camera_gate_rule(client, cam)

        # Optional side-stream for vehicles distribution (best-effort)
        dist_task = asyncio.create_task(self._attach_distribution(cam), name=f"dist-{cam.id}")
        pending_event: MultipartEvent | None = None
        try:
            async for event in client.attach_events(codes, heartbeat=5):
                if self._stop.is_set():
                    break
                if event.is_heartbeat:
                    if pending_event is not None:
                        try:
                            await self._handle_event(cam, pending_event)
                        except Exception:
                            logger.exception("Failed handling event on %s", cam.name)
                        pending_event = None
                    await self._set_status("connected")
                    continue
                await self._set_status("connected")
                # Dahua often sends JPEG in a following multipart part with no event JSON
                has_event_body = bool(event.data.get("Events") or event.event_code)
                image_only = bool(event.images) and not has_event_body and not (event.text or "").strip()
                if image_only:
                    if pending_event is not None:
                        pending_event.images = list(pending_event.images or []) + [
                            img for img in event.images if img.data
                        ]
                    continue
                if pending_event is not None:
                    try:
                        await self._handle_event(cam, pending_event)
                    except Exception:
                        logger.exception("Failed handling event on %s", cam.name)
                pending_event = event
            if pending_event is not None and not self._stop.is_set():
                try:
                    await self._handle_event(cam, pending_event)
                except Exception:
                    logger.exception("Failed handling event on %s", cam.name)
        finally:
            dist_task.cancel()
            try:
                await dist_task
            except asyncio.CancelledError:
                pass

    async def _sync_camera_gate_rule(self, client: DahuaClient, cam: Camera) -> None:
        """Align camera VideoAnalyseRule DetectLine with app overlay + direction_role."""
        try:
            async with SessionLocal() as db:
                overlay = await db.scalar(
                    select(CameraOverlay).where(CameraOverlay.camera_id == cam.id)
                )
            shapes: list = []
            if overlay and overlay.enabled:
                payload = overlay.shapes or {}
                shapes = list(payload.get("shapes") or []) if isinstance(payload, dict) else []
            lane = next(
                (
                    s
                    for s in shapes
                    if s.get("type") == "lane_line" and len(s.get("points") or []) >= 2
                ),
                None,
            )
            if not lane:
                role = str(cam.direction_role or "entry")
                if role == "bidirectional":
                    await client.get_text(
                        "/cgi-bin/configManager.cgi",
                        {
                            "action": "setConfig",
                            "VideoAnalyseRule[0][0].Config.Direction[0]": "Both",
                            "VideoAnalyseRule[0][0].Config.Direction[1]": "Reverse",
                            "VideoAnalyseRule[0][0].Config.SnapMotor": "1",
                        },
                    )
                    logger.info(
                        "No lane_line for %s — pushed Direction=Both only (draw vạch trên Trực tiếp để khớp DetectLine)",
                        cam.name,
                    )
                else:
                    logger.info(
                        "No lane_line overlay for %s — skip DetectLine sync (draw & save vạch trên Trực tiếp)",
                        cam.name,
                    )
                return
            pts = lane["points"]
            role = str(cam.direction_role or "entry")
            bidirectional = role == "bidirectional"
            res = await client.sync_tollgate_detect_line(
                pts[0],
                pts[1],
                bidirectional=bidirectional,
                snap_motor=True,
            )
            # Entry-only / exit-only cameras still need a single Direction on device
            if not bidirectional:
                direction = "Obverse" if role == "entry" else "Reverse"
                await client.get_text(
                    "/cgi-bin/configManager.cgi",
                    {
                        "action": "setConfig",
                        "VideoAnalyseRule[0][0].Config.Direction[0]": direction,
                        "VideoAnalyseRule[0][0].Config.Direction[1]": "",
                    },
                )
            logger.info(
                "Synced DetectLine on %s role=%s bidirectional=%s → %s",
                cam.name,
                role,
                bidirectional,
                (res or "").strip(),
            )
        except Exception as exc:
            logger.warning("DetectLine sync failed cam=%s: %s", cam.name, exc)

    async def _attach_distribution(self, cam: Camera) -> None:
        """Best-effort Vehicles Distribution attach (10.6.1)."""
        client = DahuaClient(
            cam.host,
            cam.username,
            cam.password,
            port=cam.port,
            use_https=cam.use_https,
        )
        while not self._stop.is_set():
            try:
                async for event in client.attach_vehicles_distribution(heartbeat=5):
                    if self._stop.is_set():
                        return
                    if event.is_heartbeat:
                        continue
                    flow = extract_flow_sample(event)
                    if not flow:
                        continue
                    async with SessionLocal() as db:
                        db.add(
                            TrafficFlowSample(
                                camera_id=cam.id,
                                site_id=cam.site_id,
                                event_code=flow.get("event_code") or "VehiclesDistribution",
                                event_utc=flow.get("event_utc") or datetime.now(timezone.utc),
                                lane_number=flow.get("lane"),
                                vehicles_num=flow.get("vehicles_num"),
                                queue_len=flow.get("queue_len"),
                                payload=flow.get("payload"),
                            )
                        )
                        await db.commit()
                    await live_bus.publish(
                        {
                            "type": "flow",
                            "camera_id": str(cam.id),
                            "vehicles_num": flow.get("vehicles_num"),
                            "queue_len": flow.get("queue_len"),
                        }
                    )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.debug("Vehicles distribution unavailable on %s: %s", cam.name, exc)
                await asyncio.sleep(60)
    async def _handle_event(self, cam: Camera, event: MultipartEvent) -> None:
        settings = get_settings()
        code = event.event_code or ""

        # Jam events
        jam = extract_jam_event(event)
        if jam and ("Jam" in str(code) or jam.get("jam_length_pct") is not None):
            async with SessionLocal() as db:
                db.add(
                    JamEvent(
                        camera_id=cam.id,
                        site_id=cam.site_id,
                        event_code=jam.get("event_code"),
                        event_utc=jam.get("event_utc") or datetime.now(timezone.utc),
                        lane_number=jam.get("lane"),
                        jam_length_pct=jam.get("jam_length_pct"),
                        jam_real_length_m=jam.get("jam_real_length_m"),
                        payload=jam.get("payload"),
                    )
                )
                db.add(
                    ViolationEvent(
                        camera_id=cam.id,
                        site_id=cam.site_id,
                        violation_type="jam",
                        plate_number=None,
                        event_utc=jam.get("event_utc"),
                        detail={
                            "jam_length_pct": jam.get("jam_length_pct"),
                            "jam_real_length_m": jam.get("jam_real_length_m"),
                            "lane": jam.get("lane"),
                        },
                    )
                )
                c = await db.get(Camera, cam.id)
                if c:
                    c.last_event_at = datetime.now(timezone.utc)
                    c.listener_status = "connected"
                await db.commit()
            await live_bus.publish(
                {
                    "type": "jam",
                    "camera_id": str(cam.id),
                    "jam_length_pct": jam.get("jam_length_pct"),
                    "jam_real_length_m": jam.get("jam_real_length_m"),
                    "lane": jam.get("lane"),
                }
            )
            if "Jam" in str(code):
                return

        # Flow / distribution samples (possibly multi-lane)
        if "Flow" in str(code) or "VehiclesData" in event.data or dig_flow(event):
            flow = extract_flow_sample(event)
            if flow:
                async with SessionLocal() as db:
                    lanes = flow.get("lanes") or []
                    if lanes:
                        for lane_row in lanes:
                            db.add(
                                TrafficFlowSample(
                                    camera_id=cam.id,
                                    site_id=cam.site_id,
                                    event_code=flow.get("event_code"),
                                    event_utc=flow.get("event_utc"),
                                    lane_number=lane_row.get("lane"),
                                    vehicles_num=lane_row.get("flow"),
                                    queue_len=None,
                                    direction=str(lane_row.get("direction"))
                                    if lane_row.get("direction") is not None
                                    else None,
                                    payload={"lane_row": lane_row, "parent": flow.get("payload")},
                                )
                            )
                    else:
                        db.add(
                            TrafficFlowSample(
                                camera_id=cam.id,
                                site_id=cam.site_id,
                                event_code=flow.get("event_code"),
                                event_utc=flow.get("event_utc"),
                                lane_number=flow.get("lane"),
                                vehicles_num=flow.get("vehicles_num"),
                                queue_len=flow.get("queue_len"),
                                payload=flow.get("payload"),
                            )
                        )
                    c = await db.get(Camera, cam.id)
                    if c:
                        c.last_event_at = datetime.now(timezone.utc)
                        c.listener_status = "connected"
                    await db.commit()
                await live_bus.publish(
                    {
                        "type": "flow",
                        "camera_id": str(cam.id),
                        **{k: v for k, v in flow.items() if k != "payload"},
                    }
                )
                return

        det = extract_detection(event)
        # Truncated Dahua packet (common when stream is interrupted mid-event)
        code_val = event.data.get("Code") if isinstance(event.data, dict) else None
        if isinstance(code_val, str) and ";data={" in code_val and "Events" not in event.data:
            logger.warning(
                "Truncated event on %s (Code=%s…) — bỏ qua, chờ gói đầy đủ",
                cam.name,
                code_val[:48],
            )
            return

        code_name = str(det.get("event_code") or "").split(";")[0].strip()
        if is_noise_event_code(code_name):
            logger.info("Skip noise event cam=%s code=%s", cam.name, code_name)
            return

        # Skip empty / ghost frames with neither plate nor real vehicle/NonMotor object
        ev0 = event.first_event if isinstance(event.first_event, dict) else {}
        vehicle_obj = ev0.get("Vehicle") if isinstance(ev0.get("Vehicle"), dict) else {}
        non_motor_obj = ev0.get("NonMotor") if isinstance(ev0.get("NonMotor"), dict) else {}
        has_vehicle_obj = bool(
            vehicle_obj.get("ObjectID")
            or vehicle_obj.get("BoundingBox")
            or non_motor_obj.get("ObjectID")
            or non_motor_obj.get("BoundingBox")
        )
        has_plate = bool(det.get("plate_number"))
        is_nonmotor = bool(non_motor_obj) or str(det.get("vehicle_class") or "") == "motorcycle" or str(
            det.get("snap_category") or ""
        ).lower() in ("nonmotor", "motorcycle")
        # Unlicensed ghosts — require plate, except NonMotor (xe máy often unread plate)
        if not has_plate and det.get("unlicensed") and not is_nonmotor:
            logger.debug("Skip unlicensed without plate cam=%s code=%s", cam.name, code_name)
            return
        if not has_plate and not has_vehicle_obj:
            logger.debug(
                "Skip empty event cam=%s code=%s",
                cam.name,
                det.get("event_code"),
            )
            return
        # Prefer junction/measurement; other codes only if plate was actually read
        # (NonMotor violation codes allowed via is_passage_event_code)
        if not is_passage_event_code(code_name) and not has_plate and not is_nonmotor:
            logger.debug("Skip non-passage without plate cam=%s code=%s", cam.name, code_name)
            return

        # Gate by drawn lane / stop / region overlays (Dahua 0–8192)
        async with SessionLocal() as db:
            overlay = await db.scalar(
                select(CameraOverlay).where(CameraOverlay.camera_id == cam.id)
            )
        shapes: list = []
        if overlay and overlay.enabled:
            payload = overlay.shapes or {}
            shapes = list(payload.get("shapes") or []) if isinstance(payload, dict) else []
        if overlay_gate_required(shapes):
            hit = detection_hits_overlay(
                shapes,
                vehicle_bbox=det.get("vehicle_bbox"),
                plate_bbox=det.get("plate_bbox"),
                vehicle_class=str(det.get("vehicle_class") or "") or None,
            )
            if not hit:
                logger.info(
                    "Skip off-lane cam=%s plate=%s code=%s vb=%s pb=%s",
                    cam.name,
                    det.get("plate_number"),
                    code_name,
                    det.get("vehicle_bbox"),
                    det.get("plate_bbox"),
                )
                return

        if should_dedupe(
            plate=det.get("plate_number"),
            group_id=det.get("group_id"),
            event_utc=det.get("event_utc"),
            last_plate=self._last_plate,
            last_group_id=self._last_group_id,
            last_utc=self._last_utc,
        ):
            logger.info(
                "Dedupe skip plate=%s group=%s",
                det.get("plate_number"),
                det.get("group_id"),
            )
            return

        # DB cooldown: same plate on this camera within 90s (survives listener restart)
        plate = det.get("plate_number")
        if plate:
            since = datetime.now(timezone.utc) - timedelta(seconds=90)
            async with SessionLocal() as db:
                recent = await db.scalar(
                    select(VehicleDetection.id)
                    .where(
                        VehicleDetection.camera_id == cam.id,
                        VehicleDetection.plate_number == plate,
                        VehicleDetection.created_at >= since,
                    )
                    .limit(1)
                )
            if recent:
                logger.info("Cooldownoldown skip plate=%s cam=%s (<90s)", plate, cam.name)
                return

        image_paths = await self._save_images(event, cam.id)
        source_jpeg = None
        for img in event.images or []:
            if img.data and len(img.data) > 1000:
                source_jpeg = img.data
                break
        if not image_paths:
            if not source_jpeg:
                source_jpeg = await self._fetch_snapshot_bytes(cam)
            if source_jpeg:
                image_paths = await self._write_fallback_image(cam.id, source_jpeg)

        gate_id = None
        lane_id = cam.lane_id
        if cam.lane and cam.lane.gate:
            gate_id = cam.lane.gate.id
        elif lane_id:
            async with SessionLocal() as db:
                lane = await db.get(Lane, lane_id)
                if lane:
                    gate_id = lane.gate_id

        async with SessionLocal() as db:
            # reload camera in this session
            cam_row = await db.get(Camera, cam.id)
            if not cam_row:
                return
            result = await persist_detection(
                db,
                cam=cam_row,
                det=det,
                raw_payload=event.data,
                image_paths=image_paths,
                source_jpeg=source_jpeg,
                gate_id=gate_id,
                publish=True,
            )

        self._last_plate = det.get("plate_number")
        self._last_group_id = det.get("group_id")
        self._last_utc = det.get("event_utc")
        logger.info(
            "Stored detection cam=%s plate=%s class=%s category=%s speed=%s status=%s",
            cam.name,
            det.get("plate_number"),
            det.get("vehicle_class"),
            det.get("vehicle_category"),
            det.get("speed"),
            result.get("speed_status"),
        )

    async def _save_images(self, event: MultipartEvent, camera_id: uuid.UUID) -> dict[str, str]:
        usable = [img for img in (event.images or []) if img.data and len(img.data) > 500]
        if not usable:
            return {}
        settings = get_settings()
        day = datetime.now(timezone.utc).strftime("%Y%m%d")
        event_id = uuid.uuid4().hex
        base = Path(settings.snapshot_dir) / day / str(camera_id) / event_id
        base.mkdir(parents=True, exist_ok=True)
        paths: dict[str, str] = {}
        for i, img in enumerate(usable):
            kind = img.kind if img.kind != "unknown" else ("scene" if i == 0 else f"img{i}")
            name = f"{kind}.jpg"
            key = kind
            if key in paths:
                key = f"{kind}_{i}"
                name = f"{key}.jpg"
            fp = base / name
            fp.write_bytes(img.data)
            paths[key] = to_relative_snapshot_path(fp)
        return paths

    async def _write_fallback_image(self, camera_id: uuid.UUID, jpeg: bytes) -> dict[str, str]:
        """Persist live snapshot so UI thumbs are not empty when multipart had no JPEG."""
        if not jpeg or len(jpeg) < 500:
            return {}
        settings = get_settings()
        day = datetime.now(timezone.utc).strftime("%Y%m%d")
        event_id = uuid.uuid4().hex
        base = Path(settings.snapshot_dir) / day / str(camera_id) / event_id
        base.mkdir(parents=True, exist_ok=True)
        fp = base / "scene.jpg"
        fp.write_bytes(jpeg)
        return {"scene": to_relative_snapshot_path(fp)}

    async def _fetch_snapshot_bytes(self, cam: Camera) -> bytes | None:
        # Never call manual_snap() here — it injects TrafficManualSnap noise into the event stream
        client = DahuaClient(
            cam.host,
            cam.username,
            cam.password,
            port=cam.port,
            use_https=cam.use_https,
            timeout=12.0,
        )
        try:
            return await client.snapshot()
        except Exception as exc:
            logger.warning("Snapshot failed cam=%s: %s", cam.name, exc)
            return None


def dig_flow(event: MultipartEvent) -> bool:
    return "FlowStates" in event.data or (
        isinstance(event.first_event, dict) and "FlowStates" in event.first_event
    )

class ListenerSupervisor:
    def __init__(self) -> None:
        self.workers: dict[uuid.UUID, CameraWorker] = {}
        self._config_fp: dict[uuid.UUID, str] = {}
        self._stop = asyncio.Event()

    async def run(self) -> None:
        await init_db()
        logger.info("Listener supervisor started")
        while not self._stop.is_set():
            await self._reconcile()
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=15.0)
            except asyncio.TimeoutError:
                pass
        for w in list(self.workers.values()):
            await w.stop()

    @staticmethod
    def _fingerprint(cam: Camera) -> str:
        # Do NOT include updated_at — heartbeat/status writes bump it and would
        # restart the worker every reconcile cycle, dropping live events.
        return "|".join(
            [
                cam.host,
                str(cam.port),
                cam.username,
                cam.password,
                str(cam.use_https),
                ",".join(cam.subscribe_codes or []),
                cam.direction_role,
                str(bool(cam.enabled)),
            ]
        )

    async def _reconcile(self) -> None:
        async with SessionLocal() as db:
            cams = (
                await db.scalars(select(Camera).where(Camera.enabled.is_(True)))
            ).all()
            wanted = {c.id: self._fingerprint(c) for c in cams}

        # stop removed or config-changed
        for cid in list(self.workers):
            if cid not in wanted:
                logger.info("Stopping worker %s", cid)
                await self.workers[cid].stop()
                del self.workers[cid]
                self._config_fp.pop(cid, None)
            elif self._config_fp.get(cid) != wanted[cid]:
                logger.info("Restarting worker %s (config changed)", cid)
                await self.workers[cid].stop()
                del self.workers[cid]
                self._config_fp.pop(cid, None)

        for cid, fp in wanted.items():
            if cid not in self.workers:
                logger.info("Starting worker %s", cid)
                w = CameraWorker(cid)
                self.workers[cid] = w
                self._config_fp[cid] = fp
                w.start()

    def request_stop(self) -> None:
        self._stop.set()


def main() -> None:
    supervisor = ListenerSupervisor()

    async def _main() -> None:
        task = asyncio.create_task(supervisor.run())
        try:
            await task
        except asyncio.CancelledError:
            supervisor.request_stop()
            await task

    try:
        asyncio.run(_main())
    except KeyboardInterrupt:
        logger.info("Shutting down")


if __name__ == "__main__":
    main()
