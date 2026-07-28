"""Normalize Dahua vehicle / plate color strings and RGB tuples."""

from __future__ import annotations

from typing import Any, Sequence

# Dahua English names → Vietnamese labels for UI
COLOR_LABEL_VI: dict[str, str] = {
    "white": "Trắng",
    "black": "Đen",
    "gray": "Xám",
    "grey": "Xám",
    "silver": "Bạc",
    "red": "Đỏ",
    "blue": "Xanh dương",
    "green": "Xanh lá",
    "yellow": "Vàng",
    "orange": "Cam",
    "brown": "Nâu",
    "purple": "Tím",
    "pink": "Hồng",
    "cyan": "Xanh lơ",
    "gold": "Vàng kim",
    "beige": "Be",
    "maroon": "Đỏ nâu",
}


def _norm(raw: str) -> str:
    return raw.lower().replace(" ", "").replace("_", "").replace("-", "")


def color_label_vi(raw: str | None) -> str | None:
    """Return Vietnamese label for a color name, or the cleaned original."""
    if not raw:
        return None
    s = str(raw).strip()
    if not s or s.lower() in ("unknown", "null", "none", "n/a", "-"):
        return None
    key = _norm(s)
    if key in COLOR_LABEL_VI:
        return COLOR_LABEL_VI[key]
    # YellowBottomBlackText → try prefix
    for eng, vi in COLOR_LABEL_VI.items():
        if key.startswith(eng):
            return vi
    return s


def rgb_to_color_name(rgb: Sequence[Any] | None) -> str | None:
    """Map Dahua MainColor / VehicleColorRGB [R,G,B,(A)] to a simple English name."""
    if not rgb or len(rgb) < 3:
        return None
    try:
        r, g, b = int(rgb[0]), int(rgb[1]), int(rgb[2])
    except (TypeError, ValueError):
        return None
    # Ignore fully transparent / empty
    if r == 0 and g == 0 and b == 0:
        return "Black"
    mx = max(r, g, b)
    mn = min(r, g, b)
    if mx < 40:
        return "Black"
    if mn > 200 and (mx - mn) < 40:
        return "White"
    if (mx - mn) < 35:
        return "Gray" if mx < 160 else "Silver"
    # Dominant channel
    if r >= g and r >= b:
        if r > 180 and g > 100 and b < 80:
            return "Orange"
        if r > 150 and g > 120 and b > 80 and (r - b) < 80:
            return "Brown" if mx < 180 else "Beige"
        return "Red"
    if g >= r and g >= b:
        return "Green"
    if b >= r and b >= g:
        return "Blue"
    if r > 150 and g > 150 and b < 100:
        return "Yellow"
    return None


def resolve_vehicle_color(
    named: str | None,
    *,
    rgb: Sequence[Any] | None = None,
    main_color: Sequence[Any] | None = None,
) -> str | None:
    """Prefer named VehicleColor; fall back to RGB / MainColor."""
    if named is not None:
        s = str(named).strip()
        if s and s.lower() not in ("unknown", "null", "none", "n/a", "-", "undefined"):
            return s
    for candidate in (rgb, main_color):
        name = rgb_to_color_name(candidate)
        if name:
            return name
    return None
