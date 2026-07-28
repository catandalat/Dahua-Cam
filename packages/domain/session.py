from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from domain.plate import normalize_plate
from domain.schemas import DirectionRole, SessionStatus


def resolve_passage_direction(
    camera_role: DirectionRole | str,
    trigger_occur: int | None,
    *,
    vehicle_direction: str | None = None,
) -> str | None:
    """Return 'entry', 'exit', or None when direction cannot be resolved."""
    role = DirectionRole(camera_role)
    if role == DirectionRole.ENTRY:
        return "entry"
    if role == DirectionRole.EXIT:
        return "exit"
    if role == DirectionRole.BIDIRECTIONAL:
        if trigger_occur == 0:
            return "entry"
        if trigger_occur == 1:
            return "exit"
        # Fallback from Dahua direction strings when TriggerOccur missing
        vd = (vehicle_direction or "").strip().lower()
        if vd in ("0", "approach", "head", "front", "in", "entry", "come"):
            return "entry"
        if vd in ("1", "away", "tail", "back", "out", "exit", "leave"):
            return "exit"
    return None


def is_overstay(entered_at: datetime, overstay_hours: float = 24.0) -> bool:
    now = datetime.now(timezone.utc)
    if entered_at.tzinfo is None:
        entered_at = entered_at.replace(tzinfo=timezone.utc)
    return now - entered_at > timedelta(hours=overstay_hours)


def should_dedupe(
    *,
    plate: str | None,
    group_id: int | None,
    event_utc: datetime | None,
    last_plate: str | None,
    last_group_id: int | None,
    last_utc: datetime | None,
    window_seconds: float = 12.0,
    vehicle_class: str | None = None,
    last_vehicle_class: str | None = None,
) -> bool:
    """Suppress near-duplicate fires for same plate/group (parked / sticky ANPR).

    Window is short (~12s) so a real exit pass after ≥60s dwell is not blocked.
    Same GroupID always dedupes (multi-part snap of one crossing).

    Exception: allow car → motorcycle upgrade within the window so an early flat
    OCR classified as car does not block the better tall-plate moto snap.
    """
    np = normalize_plate(plate)
    lp = normalize_plate(last_plate)
    if not np or not lp or np != lp:
        return False
    vc = (vehicle_class or "").lower()
    lvc = (last_vehicle_class or "").lower()
    if vc == "motorcycle" and lvc in ("car", "unknown", "other", ""):
        return False
    if group_id is not None and last_group_id is not None and group_id == last_group_id:
        # Still allow class upgrade across multi-part snaps
        if vc == "motorcycle" and lvc in ("car", "unknown", "other", ""):
            return False
        return True
    if event_utc and last_utc:
        eu = event_utc if event_utc.tzinfo else event_utc.replace(tzinfo=timezone.utc)
        lu = last_utc if last_utc.tzinfo else last_utc.replace(tzinfo=timezone.utc)
        if abs((eu - lu).total_seconds()) <= window_seconds:
            return True
    return False


class SessionMatchResult:
    def __init__(
        self,
        action: str,
        session_id: UUID | None = None,
        status: SessionStatus | None = None,
        extra: dict[str, Any] | None = None,
    ):
        self.action = action  # open | close | orphan_exit | skip
        self.session_id = session_id
        self.status = status
        self.extra = extra or {}
