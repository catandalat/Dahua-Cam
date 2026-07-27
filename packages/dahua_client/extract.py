from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from dahua_client.kv_parser import dig
from dahua_client.multipart import MultipartEvent
from domain.plate import normalize_plate
from domain.schemas import EVENT_TO_VIOLATION, ViolationType
from domain.vehicle_class import classify_vehicle


def _event_utc(ev: dict[str, Any]) -> datetime | None:
    for key in ("UTC", "Utc", "Pts", "PTS", "UTCMS"):
        val = dig(ev, key, f"EventBaseInfo.{key}")
        if val is None:
            continue
        try:
            n = float(val)
            if key == "UTCMS" or n > 10_000_000_000:
                n = n / 1000.0
            return datetime.fromtimestamp(n, tz=timezone.utc)
        except (TypeError, ValueError, OSError):
            continue
    for key in ("LocalTime", "Time"):
        val = dig(ev, key)
        if isinstance(val, str) and val:
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
                try:
                    return datetime.strptime(val, fmt).replace(tzinfo=timezone.utc)
                except ValueError:
                    continue
    return None


def _bbox(ev: dict[str, Any], *paths: str) -> list[int] | None:
    for path in paths:
        val = dig(ev, path)
        if isinstance(val, list) and len(val) >= 4:
            try:
                return [int(x) for x in val[:4]]
            except (TypeError, ValueError):
                continue
        if isinstance(val, dict):
            try:
                return [int(val[k]) for k in sorted(val.keys()) if str(k).isdigit()][:4] or None
            except (TypeError, ValueError, KeyError):
                continue
    return None


def extract_detection(event: MultipartEvent) -> dict[str, Any]:
    """Normalize a multipart traffic event into a detection dict."""
    ev = event.first_event
    code = event.event_code or dig(ev, "EventBaseInfo.Code", "Code", "Name")

    plate = dig(
        ev,
        "TrafficCar.PlateNumber",
        "Object.PlateNumber",
        "PlateNumber",
        "Object.Text",
    )
    plate_color = dig(ev, "TrafficCar.PlateColor", "Object.PlateColor", "PlateColor")
    plate_type = dig(ev, "TrafficCar.PlateType", "Object.PlateType", "PlateType")
    front_plate = dig(ev, "FrontPlateNumber", "TrafficCar.FrontPlateNumber", "Object.FrontPlateNumber")
    back_plate = dig(ev, "BackPlateNumber", "TrafficCar.BackPlateNumber", "Object.BackPlateNumber")
    front_plate_color = dig(ev, "FrontPlateColor", "TrafficCar.FrontPlateColor")
    back_plate_color = dig(ev, "BackPlateColor", "TrafficCar.BackPlateColor")

    vehicle = dig(ev, "Vehicle", default={}) or {}
    if not isinstance(vehicle, dict):
        vehicle = {}

    brand = dig(ev, "Vehicle.Text", "TrafficCar.VehicleSign", "Text") or vehicle.get("Text")
    model = dig(ev, "Vehicle.SubText", "SubText") or vehicle.get("SubText")
    category = dig(ev, "Vehicle.Category", "TrafficCar.Category", "Category", "NonMotor.Category") or vehicle.get(
        "Category"
    )
    color = dig(ev, "Vehicle.VehicleColor", "TrafficCar.VehicleColor", "VehicleColor", "NonMotor.Color") or vehicle.get(
        "VehicleColor"
    )
    color_rgb = dig(ev, "Vehicle.VehicleColorRGB", "VehicleColorRGB")
    speed = dig(ev, "Speed", "TrafficCar.Speed", "Vehicle.Speed")
    lane = dig(ev, "Lane", "TrafficCar.Lane", "PhysicalLane")
    physical_lane = dig(ev, "PhysicalLane")
    direction = dig(ev, "VehicleDirection", "Direction", "TrafficCar.Direction")
    junction_dir = dig(ev, "JunctionDirection")
    trigger_occur = dig(ev, "TriggerOccur")
    trigger_type = dig(ev, "TriggerType")
    try:
        trigger_occur_i = int(trigger_occur) if trigger_occur is not None else None
    except (TypeError, ValueError):
        trigger_occur_i = None

    group_id = dig(ev, "GroupID")
    try:
        group_id_i = int(group_id) if group_id is not None else None
    except (TypeError, ValueError):
        group_id_i = None

    seatbelt_main, seatbelt_sub, calling, smoking, sun_shade = _seat_flags(ev)

    plate_norm = normalize_plate(str(plate) if plate is not None else None)
    unlicensed = False
    if plate is None or plate_norm is None or str(plate).strip() in ("", "unknown", "Unknown", "-"):
        if code and ("Traffic" in str(code) or "Junction" in str(code) or "Measurement" in str(code)):
            if dig(ev, "Vehicle", "TrafficCar", "Object") is not None:
                unlicensed = plate_norm is None

    speed_limit = dig(ev, "SpeedLimit")
    over_pct = dig(ev, "OverSpeedingPercentage")
    under_pct = dig(ev, "UnderSpeedingPercentage")
    red_light_utc = dig(ev, "RedLightUTC")

    from domain.speed import normalize_speed_limit

    speed_limit_norm = normalize_speed_limit(speed_limit)

    category_s = str(category) if category is not None else None
    vehicle_class = classify_vehicle(category_s, event_code=str(code) if code else None)

    return {
        "event_code": code,
        "event_utc": _event_utc(ev),
        "plate_raw": str(plate) if plate is not None else None,
        "plate_number": plate_norm,
        "plate_color": plate_color,
        "plate_type": plate_type,
        "front_plate_number": normalize_plate(str(front_plate)) if front_plate else None,
        "back_plate_number": normalize_plate(str(back_plate)) if back_plate else None,
        "front_plate_color": front_plate_color,
        "back_plate_color": back_plate_color,
        "vehicle_brand": brand,
        "vehicle_model": model,
        "vehicle_category": category_s,
        "vehicle_class": vehicle_class,
        "vehicle_color": color,
        "vehicle_color_rgb": color_rgb,
        "speed": _as_float(speed),
        "lane": _as_int(lane),
        "physical_lane": _as_int(physical_lane),
        "vehicle_direction": direction,
        "junction_direction": junction_dir,
        "trigger_occur": trigger_occur_i,
        "trigger_type": _as_int(trigger_type),
        "group_id": group_id_i,
        "count_in_group": _as_int(dig(ev, "CountInGroup")),
        "index_in_group": _as_int(dig(ev, "IndexInGroup")),
        "seatbelt_main": seatbelt_main,
        "seatbelt_sub": seatbelt_sub,
        "calling": calling,
        "smoking": smoking,
        "sun_shade": sun_shade,
        "country": dig(ev, "Object.Country", "Country", "TrafficCar.Country"),
        "rec_no": dig(ev, "TrafficCar.RecNo", "RecNo", "EventID"),
        "plate_bbox": _bbox(ev, "Object.BoundingBox", "TrafficCar.BoundingBox"),
        "vehicle_bbox": _bbox(ev, "Vehicle.BoundingBox"),
        "speed_limit": speed_limit,
        "speed_limit_norm": speed_limit_norm,
        "over_speeding_pct": _as_float(over_pct),
        "under_speeding_pct": _as_float(under_pct),
        "red_light_utc": red_light_utc,
        "unlicensed": unlicensed,
        "brand_year": dig(ev, "Vehicle.BrandYear", "BrandYear"),
        "sub_brand": dig(ev, "Vehicle.SubBrand", "SubBrand"),
        "pts": dig(ev, "PTS"),
        "utcms": dig(ev, "UTCMS"),
    }


def _seat_flags(ev: dict[str, Any]) -> tuple[str | None, str | None, bool, bool, str | None]:
    main = dig(ev, "MainSeat", "CommInfo.Seat[0].SafeBelt")
    sub = dig(ev, "SubSeat")
    calling = False
    smoking = False
    sun_shade = dig(ev, "CommInfo.Seat[0].SunShade")

    seats = dig(ev, "CommInfo.Seat", default=None)
    if isinstance(seats, list):
        for seat in seats:
            if not isinstance(seat, dict):
                continue
            stype = str(seat.get("Type", "")).lower()
            sb = seat.get("SafeBelt")
            if stype == "main" and sb:
                main = main or sb
            if stype == "slave" and sb:
                sub = sub or sb
            if seat.get("SunShade") and (stype == "main" or not sun_shade):
                sun_shade = seat.get("SunShade")
            status = seat.get("Status") or []
            if isinstance(status, str):
                status = [status]
            for s in status:
                sl = str(s).lower()
                if "call" in sl:
                    calling = True
                if "smok" in sl:
                    smoking = True
    return (
        str(main) if main else None,
        str(sub) if sub else None,
        calling,
        smoking,
        str(sun_shade) if sun_shade else None,
    )


def extract_violations(detection: dict[str, Any]) -> list[dict[str, Any]]:
    """Derive violation records from a normalized detection."""
    out: list[dict[str, Any]] = []
    code = str(detection.get("event_code") or "")

    if detection.get("seatbelt_main") == "WithoutSafeBelt":
        out.append(
            {
                "violation_type": ViolationType.SEATBELT.value,
                "detail": {"seat": "main", "status": detection["seatbelt_main"]},
            }
        )
    if detection.get("seatbelt_sub") == "WithoutSafeBelt":
        out.append(
            {
                "violation_type": ViolationType.SEATBELT.value,
                "detail": {"seat": "sub", "status": detection["seatbelt_sub"]},
            }
        )
    if detection.get("calling"):
        out.append({"violation_type": ViolationType.CALLING.value, "detail": {}})
    if detection.get("smoking"):
        out.append({"violation_type": ViolationType.SMOKING.value, "detail": {}})
    if detection.get("unlicensed"):
        out.append({"violation_type": ViolationType.UNLICENSED.value, "detail": {}})

    mapped = EVENT_TO_VIOLATION.get(code)
    if not mapped:
        # fuzzy match numbered variants TrafficOverSpeed1
        for key, vtype in EVENT_TO_VIOLATION.items():
            if code.startswith(key):
                mapped = vtype
                break
    if mapped:
        detail: dict[str, Any] = {"event_code": code}
        if detection.get("speed") is not None:
            detail["speed"] = detection["speed"]
        if detection.get("speed_limit") is not None:
            detail["speed_limit"] = detection["speed_limit"]
        if detection.get("over_speeding_pct") is not None:
            detail["over_speeding_pct"] = detection["over_speeding_pct"]
        if detection.get("under_speeding_pct") is not None:
            detail["under_speeding_pct"] = detection["under_speeding_pct"]
        if detection.get("red_light_utc") is not None:
            detail["red_light_utc"] = detection["red_light_utc"]
        out.append({"violation_type": mapped.value, "detail": detail})

    return out


def extract_flow_sample(event: MultipartEvent) -> dict[str, Any] | None:
    ev = event.first_event
    code = event.event_code or dig(ev, "EventBaseInfo.Code")
    flow_states = dig(ev, "FlowStates", default=None)

    if code and "Flow" not in str(code) and "Vehicles" not in str(event.data):
        if "VehiclesData" not in event.data and "VehiclesData" not in ev:
            if code != "TrafficFlowStat" and not flow_states:
                return None

    vehicles_data = dig(event.data, "VehiclesData", default=None) or dig(
        ev, "VehiclesData", default=None
    )

    lanes: list[dict[str, Any]] = []
    if isinstance(flow_states, list):
        for st in flow_states:
            if not isinstance(st, dict):
                continue
            lanes.append(
                {
                    "lane": _as_int(st.get("Lane")),
                    "flow": _as_int(st.get("Flow")),
                    "period": _as_int(st.get("Period")),
                    "period_ms": _as_int(st.get("PeriodByMili")),
                    "direction": st.get("DrivingDirection") or st.get("DrivingDirecti"),
                }
            )

    return {
        "event_code": code or "TrafficFlowStat",
        "event_utc": _event_utc(ev),
        "lane": _as_int(dig(ev, "Lane")),
        "vehicles_num": _as_int(dig(ev, "VehiclesNum", "VehicleNum", "Flow", "Period")),
        "queue_len": _as_int(dig(ev, "QueueLen")),
        "lanes": lanes,
        "payload": {"event": ev, "vehicles_data": vehicles_data, "flow_states": flow_states},
    }


def extract_jam_event(event: MultipartEvent) -> dict[str, Any] | None:
    ev = event.first_event
    code = str(event.event_code or dig(ev, "EventBaseInfo.Code") or "")
    if "Jam" not in code and dig(ev, "JamLenght", "JamLength", "JamRealLength") is None:
        return None
    return {
        "event_code": code or "TrafficJam",
        "event_utc": _event_utc(ev),
        "lane": _as_int(dig(ev, "Lane")),
        "jam_length_pct": _as_float(dig(ev, "JamLenght", "JamLength")),
        "jam_real_length_m": _as_float(dig(ev, "JamRealLength")),
        "start_jamming": dig(ev, "StartJaming", "StartJamming"),
        "alarm_interval": dig(ev, "AlarmInterval"),
        "payload": ev,
    }


def _as_int(v: Any) -> int | None:
    try:
        return int(v) if v is not None and v != "" else None
    except (TypeError, ValueError):
        return None


def _as_float(v: Any) -> float | None:
    try:
        return float(v) if v is not None and v != "" else None
    except (TypeError, ValueError):
        return None
