from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any
import httpx

from dahua_client.kv_parser import kv_lines_to_dict
from dahua_client.multipart import (
    MultipartEvent,
    extract_boundary,
    parse_multipart_stream,
)

logger = logging.getLogger(__name__)


class DahuaClient:
    """HTTP Digest client for Dahua ITC camera CGI APIs."""

    def __init__(
        self,
        host: str,
        username: str,
        password: str,
        *,
        port: int = 80,
        use_https: bool = False,
        timeout: float = 30.0,
    ):
        self.host = host.rstrip("/")
        self.username = username
        self.password = password
        self.port = port
        self.use_https = use_https
        scheme = "https" if use_https else "http"
        if (use_https and port == 443) or (not use_https and port == 80):
            self.base_url = f"{scheme}://{host}"
        else:
            self.base_url = f"{scheme}://{host}:{port}"
        self._timeout = timeout
        self._auth = httpx.DigestAuth(username, password)

    def _client(self, timeout: float | httpx.Timeout | None = None) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.base_url,
            auth=self._auth,
            timeout=timeout or self._timeout,
            verify=False,
        )

    async def get_text(self, path: str, params: dict[str, Any] | None = None) -> str:
        async with self._client() as client:
            r = await client.get(path, params=params)
            r.raise_for_status()
            return r.text

    async def get_caps(self) -> dict[str, Any]:
        """GET /cgi-bin/eventManager.cgi?action=getCaps"""
        text = await self.get_text("/cgi-bin/eventManager.cgi", {"action": "getCaps"})
        return kv_lines_to_dict(text)

    async def get_traffic_device_info(self) -> dict[str, Any]:
        text = await self.get_text(
            "/cgi-bin/trafficSnap.cgi",
            {"action": "getDeviceInfo"},
        )
        return kv_lines_to_dict(text)

    async def attach_events(
        self,
        codes: list[str],
        *,
        heartbeat: int = 5,
    ) -> AsyncIterator[MultipartEvent]:
        """Long-lived eventManager attach stream."""
        codes_param = "[" + ",".join(codes) + "]"
        params = {
            "action": "attach",
            "codes": codes_param,
            "heartbeat": str(heartbeat),
        }
        timeout = httpx.Timeout(None, connect=15.0)
        async with self._client(timeout=timeout) as client:
            async with client.stream("GET", "/cgi-bin/eventManager.cgi", params=params) as resp:
                resp.raise_for_status()
                boundary = extract_boundary(resp.headers.get("content-type"))
                if not boundary:
                    boundary = b"myboundary"
                    logger.warning("No multipart boundary in content-type; using default")

                async def byte_iter() -> AsyncIterator[bytes]:
                    async for chunk in resp.aiter_bytes():
                        yield chunk

                async for event in parse_multipart_stream(byte_iter(), boundary):
                    yield event

    async def attach_vehicles_distribution(
        self,
        *,
        channel: int = 1,
        heartbeat: int = 5,
    ) -> AsyncIterator[MultipartEvent]:
        params = {"action": "attach", "Channel": channel, "heartbeat": heartbeat}
        timeout = httpx.Timeout(None, connect=15.0)
        async with self._client(timeout=timeout) as client:
            # Prefer documented vehiclesDistribution.cgi; some firmwares use intelli.cgi
            path = "/cgi-bin/vehiclesDistribution.cgi"
            try:
                async with client.stream("GET", path, params=params) as resp:
                    if resp.status_code == 404:
                        raise httpx.HTTPStatusError(
                            "not found", request=resp.request, response=resp
                        )
                    resp.raise_for_status()
                    boundary = extract_boundary(resp.headers.get("content-type")) or b"myboundary"

                    async def byte_iter() -> AsyncIterator[bytes]:
                        async for chunk in resp.aiter_bytes():
                            yield chunk

                    async for event in parse_multipart_stream(byte_iter(), boundary):
                        yield event
            except httpx.HTTPStatusError:
                path = "/cgi-bin/intelli.cgi"
                params2 = {"action": "attachResource", "heartbeat": heartbeat}
                async with client.stream("GET", path, params=params2) as resp:
                    resp.raise_for_status()
                    boundary = extract_boundary(resp.headers.get("content-type")) or b"myboundary"

                    async def byte_iter2() -> AsyncIterator[bytes]:
                        async for chunk in resp.aiter_bytes():
                            yield chunk

                    async for event in parse_multipart_stream(byte_iter2(), boundary):
                        yield event

    # --- Traffic record allow/block list ---

    async def find_traffic_list(
        self,
        *,
        list_type: str = "AllowList",
        start: int = 0,
        count: int = 100,
    ) -> str:
        return await self.get_text(
            "/cgi-bin/recordUpdater.cgi",
            {
                "action": "get",
                "name": list_type,
                "start": start,
                "count": count,
            },
        )

    async def insert_traffic_list_record(
        self,
        *,
        list_type: str,
        plate_number: str,
        begin_time: str = "2000-01-01 00:00:00",
        end_time: str = "2037-12-31 23:59:59",
    ) -> str:
        return await self.get_text(
            "/cgi-bin/recordUpdater.cgi",
            {
                "action": "insert",
                "name": list_type,
                "PlateNumber": plate_number,
                "BeginTime": begin_time,
                "CancelTime": end_time,
            },
        )

    # --- Media find with TrafficCar ---

    async def media_find_create(self, object_type: str = "TrafficCar") -> str:
        text = await self.get_text(
            "/cgi-bin/mediaFileFind.cgi",
            {"action": "factory.create"},
        )
        data = kv_lines_to_dict(text)
        return str(data.get("result", data.get("object", "")))

    async def media_find_file(
        self,
        finder_id: str,
        *,
        start_time: str,
        end_time: str,
        plate_number: str | None = None,
        channel: int = 1,
    ) -> str:
        params: dict[str, Any] = {
            "action": "findFile",
            "object": finder_id,
            "condition.Channel": channel,
            "condition.StartTime": start_time,
            "condition.EndTime": end_time,
            "condition.Types[0]": "jpg",
            "condition.Events[0]": "TrafficJunction",
        }
        if plate_number:
            params["condition.TrafficCar.PlateNumber"] = plate_number
        return await self.get_text("/cgi-bin/mediaFileFind.cgi", params)

    async def media_find_next(self, finder_id: str, count: int = 50) -> str:
        return await self.get_text(
            "/cgi-bin/mediaFileFind.cgi",
            {"action": "findNextFile", "object": finder_id, "count": count},
        )

    async def media_find_close(self, finder_id: str) -> str:
        return await self.get_text(
            "/cgi-bin/mediaFileFind.cgi",
            {"action": "close", "object": finder_id},
        )

    async def media_find_destroy(self, finder_id: str) -> str:
        return await self.get_text(
            "/cgi-bin/mediaFileFind.cgi",
            {"action": "destroy", "object": finder_id},
        )

    # --- Traffic flow history ---

    async def start_traffic_stat_search(
        self,
        *,
        start_time: str,
        end_time: str,
        channel: int = 1,
        lane: int = -1,
    ) -> str:
        return await self.get_text(
            "/cgi-bin/trafficFlowStat.cgi",
            {
                "action": "startFind",
                "channel": channel,
                "StartTime": start_time,
                "EndTime": end_time,
                "Lane": lane,
            },
        )

    async def get_traffic_statistics(self, object_id: str, count: int = 100) -> dict[str, Any]:
        text = await self.get_text(
            "/cgi-bin/trafficFlowStat.cgi",
            {"action": "doFind", "object": object_id, "count": count},
        )
        return kv_lines_to_dict(text)

    async def end_traffic_stat_search(self, object_id: str) -> str:
        return await self.get_text(
            "/cgi-bin/trafficFlowStat.cgi",
            {"action": "stopFind", "object": object_id},
        )

    # --- Snap / strobe / speed / unlicensed (10.4) ---

    async def open_strobe(self, channel: int = 1) -> str:
        return await self.get_text(
            "/cgi-bin/trafficSnap.cgi",
            {"action": "openStrobe", "channel": channel},
        )

    async def close_strobe(self, channel: int = 1) -> str:
        return await self.get_text(
            "/cgi-bin/trafficSnap.cgi",
            {"action": "closeStrobe", "channel": channel},
        )

    async def set_unlicensed_detection(self, enable: bool, channel: int = 1) -> str:
        return await self.get_text(
            "/cgi-bin/trafficSnap.cgi",
            {
                "action": "setUnlicensedVehicleDetection",
                "channel": channel,
                "enable": str(enable).lower(),
            },
        )

    async def manual_snap(self, channel: int = 1) -> bytes:
        """Trigger manual snap; return JPEG bytes when available."""
        async with self._client(timeout=20.0) as client:
            r = await client.get(
                "/cgi-bin/trafficSnap.cgi",
                params={"action": "manualSnap", "channel": channel},
            )
            r.raise_for_status()
            ctype = r.headers.get("content-type", "")
            if "image" in ctype or r.content[:3] == b"\xff\xd8\xff":
                return r.content
            # Some firmwares return key=value + redirect; try snapshot.cgi
            r2 = await client.get(
                "/cgi-bin/snapshot.cgi",
                params={"channel": channel},
            )
            r2.raise_for_status()
            return r2.content

    async def get_current_time(self) -> str:
        text = await self.get_text("/cgi-bin/global.cgi", {"action": "getCurrentTime"})
        # result=2026-7-28 10:04:00  or similar
        data = kv_lines_to_dict(text)
        return str(data.get("result") or data.get("time") or text).strip()

    async def set_current_time(self, when: datetime | None = None) -> str:
        """Set camera wall clock (local time string Y-M-D H:m:S)."""
        from datetime import datetime as _dt
        from zoneinfo import ZoneInfo

        dt = when or _dt.now(ZoneInfo("Asia/Ho_Chi_Minh"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=ZoneInfo("Asia/Ho_Chi_Minh"))
        else:
            dt = dt.astimezone(ZoneInfo("Asia/Ho_Chi_Minh"))
        # Dahua accepts Y-M-D H:m:S (no zero-pad required, but padded is fine)
        stamp = f"{dt.year}-{dt.month}-{dt.day} {dt.hour}:{dt.minute:02d}:{dt.second:02d}"
        return await self.get_text(
            "/cgi-bin/global.cgi",
            {"action": "setCurrentTime", "time": stamp},
        )

    async def sync_tollgate_detect_line(
        self,
        point_a: tuple[int, int] | list[int],
        point_b: tuple[int, int] | list[int],
        *,
        bidirectional: bool = True,
        snap_motor: bool = True,
    ) -> str:
        """Push overlay lane into VideoAnalyseRule DetectLine (Dahua 0–8192).

        Bidirectional uses Obverse+Reverse. SnapMotor enables motorcycle body snaps.
        NoPlateConfirmFrame is lowered so unread-plate vehicles still emit events.
        """
        x1, y1 = int(point_a[0]), int(point_a[1])
        x2, y2 = int(point_b[0]), int(point_b[1])
        params: dict[str, Any] = {
            "action": "setConfig",
            "VideoAnalyseRule[0][0].Config.DetectLine[0][0]": str(x1),
            "VideoAnalyseRule[0][0].Config.DetectLine[0][1]": str(y1),
            "VideoAnalyseRule[0][0].Config.DetectLine[1][0]": str(x2),
            "VideoAnalyseRule[0][0].Config.DetectLine[1][1]": str(y2),
            "VideoAnalyseRule[0][0].Config.SnapMotor": "1" if snap_motor else "0",
            "VideoAnalyseRule[0][0].Config.LastSnapPosition": "50",
            # Faster no-plate / motorcycle body confirmation (firmware default was 20)
            "VideoAnalyseRule[0][0].Config.NoPlateConfirmFrame": "3",
            "VideoAnalyseRule[0][0].Config.DelayTime": "0",
            "VideoAnalyseRule[0][0].Enable": "true",
        }
        if bidirectional:
            # Dahua expects Obverse+Reverse pair for 2-way snap
            params["VideoAnalyseRule[0][0].Config.Direction[0]"] = "Obverse"
            params["VideoAnalyseRule[0][0].Config.Direction[1]"] = "Reverse"
        # Do not push ObjectTypes — NonMotor as extra type is rejected by this firmware;
        # SnapMotor=1 is the supported motorcycle snap switch for TrafficTollGate.
        rule_res = await self.get_text("/cgi-bin/configManager.cgi", params)
        # Lane Type=Light-duty suppresses motorcycle events; Mix allows cars + bikes.
        # Also widen DetectRegion and align global lane DetectLine with overlay.
        try:
            await self.get_text(
                "/cgi-bin/configManager.cgi",
                {
                    "action": "setConfig",
                    "VideoAnalyseGlobal[0].Scene.Detail.Lanes[0].Type": "Mix",
                    "VideoAnalyseGlobal[0].Scene.Detail.Judgment": "Region",
                    "VideoAnalyseGlobal[0].Scene.Detail.ConfidenceFilter": "20",
                    # VN ANPR: was UN + Chinese PlateHints + wide PlateSize → poor moto OCR
                    "VideoAnalyseGlobal[0].Scene.Detail.CountryArea": "VN",
                    "VideoAnalyseGlobal[0].Scene.Detail.HangingWordPlate": "true",
                    "VideoAnalyseGlobal[0].Scene.Detail.PlateSize.Width": "100",
                    "VideoAnalyseGlobal[0].Scene.Detail.PlateSize.Height": "100",
                    "VideoAnalyseGlobal[0].Scene.Detail.Lanes[0].DetectLine[0][0]": str(x1),
                    "VideoAnalyseGlobal[0].Scene.Detail.Lanes[0].DetectLine[0][1]": str(y1),
                    "VideoAnalyseGlobal[0].Scene.Detail.Lanes[0].DetectLine[1][0]": str(x2),
                    "VideoAnalyseGlobal[0].Scene.Detail.Lanes[0].DetectLine[1][1]": str(y2),
                    "VideoAnalyseGlobal[0].Scene.Detail.DetectRegions[0].Enable": "true",
                    "VideoAnalyseGlobal[0].Scene.Detail.DetectRegions[0].DetectRegion[0][0]": "0",
                    "VideoAnalyseGlobal[0].Scene.Detail.DetectRegions[0].DetectRegion[0][1]": "4300",
                    "VideoAnalyseGlobal[0].Scene.Detail.DetectRegions[0].DetectRegion[1][0]": "8191",
                    "VideoAnalyseGlobal[0].Scene.Detail.DetectRegions[0].DetectRegion[1][1]": "4300",
                    "VideoAnalyseGlobal[0].Scene.Detail.DetectRegions[0].DetectRegion[2][0]": "8191",
                    "VideoAnalyseGlobal[0].Scene.Detail.DetectRegions[0].DetectRegion[2][1]": "8191",
                    "VideoAnalyseGlobal[0].Scene.Detail.DetectRegions[0].DetectRegion[3][0]": "0",
                    "VideoAnalyseGlobal[0].Scene.Detail.DetectRegions[0].DetectRegion[3][1]": "8191",
                },
            )
        except Exception:
            pass
        return rule_res

    async def snapshot(self, channel: int = 1) -> bytes:
        async with self._client(timeout=15.0) as client:
            r = await client.get("/cgi-bin/snapshot.cgi", params={"channel": channel})
            r.raise_for_status()
            return r.content

    async def get_speed_limit(self, channel: int = 1) -> dict[str, Any]:
        text = await self.get_text(
            "/cgi-bin/trafficSnap.cgi",
            {"action": "getSpeedLimit", "channel": channel},
        )
        return kv_lines_to_dict(text)

    async def set_speed_limit(
        self,
        *,
        min_speed: int,
        max_speed: int,
        channel: int = 1,
    ) -> str:
        return await self.get_text(
            "/cgi-bin/trafficSnap.cgi",
            {
                "action": "setSpeedLimit",
                "channel": channel,
                "SpeedLimit[0]": min_speed,
                "SpeedLimit[1]": max_speed,
            },
        )

    async def set_under_speed_enable(self, enable: bool, channel: int = 1) -> str:
        return await self.get_text(
            "/cgi-bin/trafficSnap.cgi",
            {
                "action": "setEnableUnderSpeed",
                "channel": channel,
                "Enable": str(enable).lower(),
            },
        )

    async def network_snap(self, channel: int = 1) -> str:
        return await self.get_text(
            "/cgi-bin/trafficSnap.cgi",
            {"action": "networkSnap", "channel": channel},
        )

    # --- Parking (10.5) ---

    async def get_parking_space_status(self, space_id: int | None = None) -> dict[str, Any]:
        params: dict[str, Any] = {"action": "getParkingSpaceStatus"}
        if space_id is not None:
            params["ParkingSpaceID"] = space_id
            text = await self.get_text("/cgi-bin/parkingSpaceManager.cgi", params)
        else:
            params = {"action": "getAllParkingSpaceStatus"}
            text = await self.get_text("/cgi-bin/parkingSpaceManager.cgi", params)
        return kv_lines_to_dict(text)

    # --- Vehicle manager (10.7) ---

    async def search_vehicle_groups(self) -> dict[str, Any]:
        text = await self.get_text(
            "/cgi-bin/TrafficVehicleManager.cgi",
            {"action": "listGroup"},
        )
        return kv_lines_to_dict(text)

    async def add_vehicle_record(
        self,
        *,
        group_id: str,
        plate_number: str,
        uid: int | None = None,
    ) -> str:
        import time

        params: dict[str, Any] = {
            "action": "addVehicle",
            "GroupID": group_id,
            "PlateNumber": plate_number,
            "UID": uid or int(time.time()),
        }
        return await self.get_text("/cgi-bin/TrafficVehicleManager.cgi", params)

    async def search_vehicles(self, *, group_id: str | None = None, plate: str | None = None) -> dict[str, Any]:
        params: dict[str, Any] = {"action": "startFind"}
        if group_id:
            params["GroupID"] = group_id
        if plate:
            params["PlateNumber"] = plate
        text = await self.get_text("/cgi-bin/TrafficVehicleManager.cgi", params)
        return kv_lines_to_dict(text)

    def rtsp_url(self, *, channel: int = 1, subtype: int = 0) -> str:
        """Live RTSP URL (open in VLC / go2rtc)."""
        auth = f"{self.username}:{self.password}@"
        host = self.host
        return f"rtsp://{auth}{host}:554/cam/realmonitor?channel={channel}&subtype={subtype}"

    def url(self, path: str) -> str:
        return f"{self.base_url}{path}"


def extract_supported_event_codes(caps: dict[str, Any]) -> list[str]:
    """Best-effort extraction of supported event codes from getCaps payload."""
    codes: set[str] = set()

    def walk(obj: Any) -> None:
        if isinstance(obj, dict):
            for k, v in obj.items():
                kl = k.lower()
                if "code" in kl or "event" in kl:
                    if isinstance(v, str) and v.startswith("Traffic"):
                        codes.add(v)
                    elif isinstance(v, list):
                        for item in v:
                            if isinstance(item, str) and (
                                item.startswith("Traffic") or item.startswith("Non")
                            ):
                                codes.add(item)
                walk(v)
        elif isinstance(obj, list):
            for item in obj:
                if isinstance(item, str) and (
                    item.startswith("Traffic") or "Motor" in item
                ):
                    codes.add(item)
                else:
                    walk(item)

    walk(caps)
    # Also flatten string values that look like codes
    for v in _all_strings(caps):
        if v.startswith("Traffic") or v.startswith("NonMotor") or "Traffic" in v:
            # sometimes comma-separated
            for part in v.replace("[", "").replace("]", "").split(","):
                part = part.strip().strip('"').strip("'")
                if part.startswith("Traffic") or "NonMotor" in part:
                    codes.add(part)
    return sorted(codes)


def _all_strings(obj: Any) -> list[str]:
    out: list[str] = []
    if isinstance(obj, str):
        out.append(obj)
    elif isinstance(obj, dict):
        for v in obj.values():
            out.extend(_all_strings(v))
    elif isinstance(obj, list):
        for v in obj:
            out.extend(_all_strings(v))
    return out


def select_subscribe_codes(
    supported: list[str] | None,
    *,
    include_p1: bool = True,
    include_p2: bool = True,
) -> list[str]:
    from domain.schemas import P0_EVENT_CODES, P1_EVENT_CODES, P2_EVENT_CODES

    wanted = list(P0_EVENT_CODES)
    if include_p1:
        wanted.extend(P1_EVENT_CODES)
    if include_p2:
        wanted.extend(P2_EVENT_CODES)

    if not supported:
        # Prefer curated P0 over All — All floods ManualSnap / position noise
        return [c.value for c in P0_EVENT_CODES]

    supported_set = set(supported)
    # Also accept fuzzy: TrafficCarMeasurement1 etc.
    selected: list[str] = []
    for code in wanted:
        name = code.value
        if name in supported_set:
            selected.append(name)
            continue
        # prefix match for numbered variants
        if any(s.startswith(name) for s in supported_set):
            selected.append(name)
    if not selected:
        selected = [c.value for c in P0_EVENT_CODES]
    # de-dupe preserve order
    seen: set[str] = set()
    out: list[str] = []
    for c in selected:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out
