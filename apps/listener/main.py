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
    VehicleSession,
    ViolationEvent,
)
from domain.schemas import SessionStatus
from domain.overlay_gate import (
    detection_hits_overlay,
    is_noise_event_code,
    is_passage_event_code,
    overlay_gate_required,
)
from domain.plate import is_valid_vn_plate
from domain.persist import persist_detection, to_relative_snapshot_path
from domain.session import should_dedupe
from domain.settings import get_settings

logging.basicConfig(
    level=get_settings().log_level,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("listener")

# #region agent log
_DEBUG_LOG_PATH = Path("/app/.cursor/debug-dc404e.log")
if not _DEBUG_LOG_PATH.parent.exists():
    _DEBUG_LOG_PATH = Path("/Users/hoanhkiet/Documents/GitHub/Dahua-Cam/.cursor/debug-dc404e.log")


def _agent_log(hypothesis_id: str, location: str, message: str, data: dict[str, Any] | None = None) -> None:
    import json
    import time

    try:
        _DEBUG_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "sessionId": "dc404e",
            "runId": "post-fix",
            "hypothesisId": hypothesis_id,
            "location": location,
            "message": message,
            "data": data or {},
            "timestamp": int(time.time() * 1000),
        }
        with _DEBUG_LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")
    except Exception:
        pass


# #endregion


class CameraWorker:
    def __init__(self, camera_id: uuid.UUID):
        self.camera_id = camera_id
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self._last_plate: str | None = None
        self._last_group_id: int | None = None
        self._last_utc: datetime | None = None
        # #region agent log
        self._hb_count = 0
        self._event_count = 0
        # #endregion

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
                    # #region agent log
                    self._hb_count += 1
                    if self._hb_count % 6 == 1:
                        _agent_log(
                            "H1",
                            "listener.attach_events",
                            "heartbeat_alive",
                            {
                                "hb": self._hb_count,
                                "events": self._event_count,
                                "cam": cam.name,
                            },
                        )
                    # #endregion
                    if pending_event is not None:
                        try:
                            await self._handle_event(cam, pending_event)
                        except Exception:
                            logger.exception("Failed handling event on %s", cam.name)
                        pending_event = None
                    await self._set_status("connected")
                    continue
                await self._set_status("connected")
                # #region agent log
                self._event_count += 1
                _agent_log(
                    "H1",
                    "listener.attach_events",
                    "non_heartbeat_part",
                    {
                        "n": self._event_count,
                        "code": event.event_code,
                        "has_events": bool(event.data.get("Events") if isinstance(event.data, dict) else False),
                        "img_n": len(event.images or []),
                        "keys": list(event.data.keys())[:12] if isinstance(event.data, dict) else [],
                    },
                )
                # #endregion
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
                            "VideoAnalyseRule[0][0].Config.Direction[0]": "Obverse",
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
            # #region agent log
            _agent_log(
                "H4",
                "listener._sync_camera_gate_rule",
                "detectline_synced",
                {
                    "role": role,
                    "bidirectional": bidirectional,
                    "pts": [pts[0], pts[1]],
                    "result": (res or "").strip(),
                    "direction_mode": "Obverse+Reverse" if bidirectional else "single",
                    "lane_type": "Mix",
                },
            )
            # #endregion
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
        # #region agent log
        _pb = det.get("plate_bbox")
        _pb_aspect = None
        if isinstance(_pb, (list, tuple)) and len(_pb) >= 4:
            try:
                _pw = abs(float(_pb[2]) - float(_pb[0]))
                _ph = abs(float(_pb[3]) - float(_pb[1]))
                _pb_aspect = round(_ph / _pw, 3) if _pw > 0 else None
            except (TypeError, ValueError, ZeroDivisionError):
                _pb_aspect = None
        _agent_log(
            "H7",
            "listener._handle_event",
            "extracted",
            {
                "raw_code": code,
                "det_code": det.get("event_code"),
                "plate": det.get("plate_number"),
                "vclass": det.get("vehicle_class"),
                "category": det.get("vehicle_category"),
                "snap_cat": det.get("snap_category"),
                "vsize": det.get("vehicle_size"),
                "vb": det.get("vehicle_bbox"),
                "pb": _pb,
                "pb_aspect": _pb_aspect,
                "unlicensed": det.get("unlicensed"),
                "trigger_occur": det.get("trigger_occur"),
                "junction_dir": det.get("junction_direction"),
                "vehicle_dir": det.get("vehicle_direction"),
                "has_nonmotor_obj": bool(
                    (event.first_event or {}).get("NonMotor")
                    if isinstance(event.first_event, dict)
                    else False
                ),
            },
        )
        # #endregion
        # Truncated Dahua packet (common when stream is interrupted mid-event)
        code_val = event.data.get("Code") if isinstance(event.data, dict) else None
        if isinstance(code_val, str) and ";data={" in code_val and "Events" not in event.data:
            logger.warning(
                "Truncated event on %s (Code=%s…) — bỏ qua, chờ gói đầy đủ",
                cam.name,
                code_val[:48],
            )
            # #region agent log
            _agent_log("H3", "listener._handle_event", "truncated_skip", {"code": code_val[:80]})
            # #endregion
            return

        code_name = str(det.get("event_code") or "").split(";")[0].strip()
        # TrafficVehiclePosition / TrafficManualSnap: keep when plate or body present.
        # Empty ManualSnap floods the stream and must stay filtered.
        if code_name in ("TrafficVehiclePosition", "TrafficManualSnap"):
            if not (det.get("plate_number") or det.get("vehicle_bbox") or det.get("plate_bbox")):
                logger.info("Skip empty %s cam=%s", code_name, cam.name)
                # #region agent log
                _agent_log("H3", "listener._handle_event", "position_empty_skip", {"code": code_name})
                # #endregion
                return
            # ManualSnap without plate: keep bike/NonMotor body; for other bodies
            # defer to overlay (near-line unlicensed — inbound moto often has no OCR).
            if code_name == "TrafficManualSnap" and not det.get("plate_number"):
                is_bike = str(det.get("vehicle_class") or "").lower() in (
                    "motorcycle",
                    "nonmotor",
                    "bike",
                ) or bool(
                    (event.first_event or {}).get("NonMotor")
                    if isinstance(event.first_event, dict)
                    else False
                )
                if is_bike:
                    # #region agent log
                    _agent_log(
                        "H10",
                        "listener._handle_event",
                        "manual_snap_bike_body",
                        {"vb": det.get("vehicle_bbox"), "vclass": det.get("vehicle_class")},
                    )
                    # #endregion
                # else: do not return — overlay NOPLATE threshold drops mid-frame noise
            # #region agent log
            _agent_log(
                "H6",
                "listener._handle_event",
                "special_code_kept",
                {
                    "code": code_name,
                    "plate": det.get("plate_number"),
                    "vclass": det.get("vehicle_class"),
                    "vb": det.get("vehicle_bbox"),
                    "vdir": det.get("vehicle_direction"),
                },
            )
            # #endregion
        elif is_noise_event_code(code_name):
            logger.info("Skip noise event cam=%s code=%s", cam.name, code_name)
            # #region agent log
            _agent_log("H3", "listener._handle_event", "noise_skip", {"code": code_name})
            # #endregion
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
        # Real vehicles without a readable plate still count (bbox present).
        # Only drop empty/ghost frames with neither plate nor vehicle body.
        if not has_plate and not has_vehicle_obj:
            logger.debug(
                "Skip empty event cam=%s code=%s",
                cam.name,
                det.get("event_code"),
            )
            # #region agent log
            _agent_log("H3", "listener._handle_event", "empty_skip", {"code": code_name})
            # #endregion
            return
        # Prefer junction/measurement; other codes only if plate was actually read
        # (NonMotor violation codes allowed via is_passage_event_code)
        if not is_passage_event_code(code_name) and not has_plate and not is_nonmotor:
            logger.debug("Skip non-passage without plate cam=%s code=%s", cam.name, code_name)
            # #region agent log
            _agent_log("H3", "listener._handle_event", "non_passage_skip", {"code": code_name})
            # #endregion
            return

        # Reject OCR garbage that is not a plausible VN plate (OO8313, K8760454, …)
        if has_plate and not is_valid_vn_plate(str(det.get("plate_number") or "")):
            logger.info(
                "Skip invalid plate cam=%s plate=%s code=%s",
                cam.name,
                det.get("plate_number"),
                code_name,
            )
            # #region agent log
            _agent_log(
                "H9",
                "listener._handle_event",
                "invalid_plate_skip",
                {
                    "plate": det.get("plate_number"),
                    "code": code_name,
                    "pconf": det.get("plate_confidence"),
                    "pb": det.get("plate_bbox"),
                },
            )
            # #endregion
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
                plate_number=str(det.get("plate_number") or "") or None,
            )
            # #region agent log
            _ov_dist = None
            _ov_side = None
            try:
                from domain.overlay_gate import min_dist_to_line, _point_side_of_line, _shape_points
                from domain.plate import is_vn_motorcycle_plate

                _pb = det.get("plate_bbox") or det.get("vehicle_bbox")
                for _s in shapes:
                    if _s.get("type") in ("lane_line", "stop_line"):
                        _pts = _shape_points(_s)
                        if len(_pts) >= 2:
                            _ax, _ay = _pts[0]
                            _bx, _by = _pts[1]
                            _ov_dist = min_dist_to_line(_pb, _ax, _ay, _bx, _by)
                            if _pb and len(_pb) >= 4:
                                _mx = (float(_pb[0]) + float(_pb[2])) / 2.0
                                _my = (float(_pb[1]) + float(_pb[3])) / 2.0
                                _ov_side = _point_side_of_line(_mx, _my, _ax, _ay, _bx, _by)
                            break
                _moto_plate = bool(
                    det.get("plate_number")
                    and is_vn_motorcycle_plate(
                        str(det.get("plate_number") or ""),
                        plate_bbox=det.get("plate_bbox"),
                    )
                )
            except Exception:
                _moto_plate = False
            _agent_log(
                "H10",
                "listener._handle_event",
                "overlay_decision",
                {
                    "plate": det.get("plate_number"),
                    "code": code_name,
                    "hit": hit,
                    "dist": round(_ov_dist, 1) if _ov_dist is not None else None,
                    "side": int(_ov_side) if _ov_side is not None else None,
                    "pb": det.get("plate_bbox"),
                    "vb": det.get("vehicle_bbox"),
                    "pconf": det.get("plate_confidence"),
                    "rconf": det.get("recognise_conf"),
                    "vclass": det.get("vehicle_class"),
                    "vdir": det.get("vehicle_direction"),
                    "moto_plate": _moto_plate,
                    "pcolor": det.get("plate_color"),
                },
            )
            # #endregion
            if not hit:
                logger.info(
                    "Skip off-lane cam=%s plate=%s code=%s vb=%s pb=%s",
                    cam.name,
                    det.get("plate_number"),
                    code_name,
                    det.get("vehicle_bbox"),
                    det.get("plate_bbox"),
                )
                # #region agent log
                _agent_log(
                    "H8",
                    "listener._handle_event",
                    "overlay_reject",
                    {
                        "plate": det.get("plate_number"),
                        "code": code_name,
                        "vb": det.get("vehicle_bbox"),
                        "pb": det.get("plate_bbox"),
                        "dist": round(_ov_dist, 1) if _ov_dist is not None else None,
                    },
                )
                # #endregion
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
            # #region agent log
            _agent_log("H5", "listener._handle_event", "dedupe_skip", {"plate": det.get("plate_number")})
            # #endregion
            return

        # DB cooldown: suppress sticky re-fires of the same plate (~12s).
        # Do NOT use 90s — that blocks real exits (matcher needs ≥60s dwell).
        # If the plate is already INSIDE, never cooldown-skip (needed for exit).
        plate = det.get("plate_number")
        if plate:
            async with SessionLocal() as db:
                inside = await db.scalar(
                    select(VehicleSession.id)
                    .where(
                        VehicleSession.site_id == cam.site_id,
                        VehicleSession.plate_number == plate,
                        VehicleSession.status == SessionStatus.INSIDE.value,
                    )
                    .limit(1)
                )
                if inside:
                    # #region agent log
                    _agent_log(
                        "H5",
                        "listener._handle_event",
                        "cooldown_bypass_inside",
                        {"plate": plate},
                    )
                    # #endregion
                else:
                    since = datetime.now(timezone.utc) - timedelta(seconds=12)
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
                        logger.info("Cooldownoldown skip plate=%s cam=%s (<12s)", plate, cam.name)
                        # #region agent log
                        _agent_log("H5", "listener._handle_event", "cooldown_skip", {"plate": plate, "window_s": 12})
                        # #endregion
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
        # #region agent log
        _agent_log(
            "H1",
            "listener._handle_event",
            "stored_ok",
            {
                "plate": det.get("plate_number"),
                "code": det.get("event_code"),
                "vclass": det.get("vehicle_class"),
                "unlicensed": bool(det.get("unlicensed")),
                "vehicle_dir": det.get("vehicle_direction"),
                "trigger_occur": det.get("trigger_occur"),
                "passage": result.get("passage_direction"),
                "session_status": result.get("session_status"),
                "det_id": str(result.get("detection_id") or result.get("id") or ""),
            },
        )
        # #endregion

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
