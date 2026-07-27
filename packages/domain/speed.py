"""Speed measurement policy helpers — normalize limits and evaluate overspeed."""

from __future__ import annotations

from typing import Any


def normalize_speed_limit(raw: Any) -> dict[str, float | None]:
    """Parse Dahua SpeedLimit (often [min, max] or a single max) into min/max."""
    min_s: float | None = None
    max_s: float | None = None
    if raw is None:
        return {"min": None, "max": None}
    if isinstance(raw, dict):
        for k, target in (("0", "min"), ("1", "max"), ("Min", "min"), ("Max", "max"), ("min", "min"), ("max", "max")):
            if k in raw:
                try:
                    val = float(raw[k])
                except (TypeError, ValueError):
                    continue
                if target == "min":
                    min_s = val
                else:
                    max_s = val
        if min_s is None and max_s is None and len(raw) >= 1:
            vals = []
            for v in raw.values():
                try:
                    vals.append(float(v))
                except (TypeError, ValueError):
                    pass
            if len(vals) >= 2:
                min_s, max_s = vals[0], vals[1]
            elif len(vals) == 1:
                max_s = vals[0]
    elif isinstance(raw, (list, tuple)):
        nums: list[float] = []
        for v in raw:
            try:
                nums.append(float(v))
            except (TypeError, ValueError):
                pass
        if len(nums) >= 2:
            min_s, max_s = nums[0], nums[1]
        elif len(nums) == 1:
            max_s = nums[0]
    else:
        try:
            max_s = float(raw)
        except (TypeError, ValueError):
            pass
    return {"min": min_s, "max": max_s}


def resolve_limits(
    *,
    event_limit: Any = None,
    policy_min: float | int | None = None,
    policy_max: float | int | None = None,
) -> tuple[float | None, float | None]:
    """Prefer camera event SpeedLimit; fall back to site/camera policy."""
    norm = normalize_speed_limit(event_limit)
    min_s = norm["min"] if norm["min"] is not None else (
        float(policy_min) if policy_min is not None else None
    )
    max_s = norm["max"] if norm["max"] is not None else (
        float(policy_max) if policy_max is not None else None
    )
    return min_s, max_s


def evaluate_speed_policy(
    speed: float | int | None,
    *,
    min_speed: float | None = None,
    max_speed: float | None = None,
    alert_overspeed: bool = True,
    alert_underspeed: bool = False,
    existing_types: set[str] | None = None,
    source: str = "policy",
) -> list[dict[str, Any]]:
    """Create overspeed/underspeed violations by comparing measured speed to limits.

    Skips types already present (e.g. from TrafficOverSpeed camera event).
    """
    if speed is None:
        return []
    try:
        spd = float(speed)
    except (TypeError, ValueError):
        return []

    existing = existing_types or set()
    out: list[dict[str, Any]] = []

    if (
        alert_overspeed
        and max_speed is not None
        and spd > float(max_speed)
        and "overspeed" not in existing
    ):
        over_pct = round(((spd - float(max_speed)) / float(max_speed)) * 100, 1) if max_speed else None
        out.append(
            {
                "violation_type": "overspeed",
                "detail": {
                    "source": source,
                    "speed": spd,
                    "speed_limit": {"min": min_speed, "max": max_speed},
                    "limit_max": max_speed,
                    "limit_min": min_speed,
                    "over_speeding_pct": over_pct,
                },
            }
        )

    if (
        alert_underspeed
        and min_speed is not None
        and float(min_speed) > 0
        and spd < float(min_speed)
        and "underspeed" not in existing
    ):
        under_pct = round(((float(min_speed) - spd) / float(min_speed)) * 100, 1) if min_speed else None
        out.append(
            {
                "violation_type": "underspeed",
                "detail": {
                    "source": source,
                    "speed": spd,
                    "speed_limit": {"min": min_speed, "max": max_speed},
                    "limit_max": max_speed,
                    "limit_min": min_speed,
                    "under_speeding_pct": under_pct,
                },
            }
        )

    return out


def speed_status(
    speed: float | int | None,
    *,
    min_speed: float | None = None,
    max_speed: float | None = None,
) -> str:
    """ok | overspeed | underspeed | unknown"""
    if speed is None:
        return "unknown"
    try:
        spd = float(speed)
    except (TypeError, ValueError):
        return "unknown"
    if max_speed is not None and spd > float(max_speed):
        return "overspeed"
    if min_speed is not None and float(min_speed) > 0 and spd < float(min_speed):
        return "underspeed"
    return "ok"
