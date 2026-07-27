"""Shared domain models, plate normalization, and session matching."""

from domain.plate import normalize_plate
from domain.schemas import (
    DirectionRole,
    EventCode,
    SessionStatus,
    ViolationType,
)

__all__ = [
    "normalize_plate",
    "DirectionRole",
    "EventCode",
    "SessionStatus",
    "ViolationType",
]
