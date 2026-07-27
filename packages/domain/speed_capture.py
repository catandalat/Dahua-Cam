"""Stamp measured speed onto overspeed evidence JPEGs."""

from __future__ import annotations

import io
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont


def _font(size: int) -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
    for path in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ):
        try:
            return ImageFont.truetype(path, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def stamp_speed_on_image(
    jpeg_bytes: bytes,
    *,
    speed: float,
    limit_max: float | None = None,
    peak_speed: float | None = None,
    plate: str | None = None,
    captured_at: datetime | None = None,
    camera_name: str | None = None,
) -> bytes:
    """Overlay speed / limit / peak banner on a JPEG; return JPEG bytes."""
    img = Image.open(io.BytesIO(jpeg_bytes)).convert("RGB")
    draw = ImageDraw.Draw(img, "RGBA")
    w, h = img.size

    title_size = max(18, min(w, h) // 22)
    body_size = max(14, title_size - 4)
    font_title = _font(title_size)
    font_body = _font(body_size)

    when = (captured_at or datetime.now(timezone.utc)).astimezone()
    lines = [
        f"VUOT TOC DO  {speed:.0f} km/h" if limit_max is None or speed > limit_max else f"TOC DO  {speed:.0f} km/h",
    ]
    if limit_max is not None:
        lines.append(f"Nguong: {limit_max:.0f} km/h")
    peak = peak_speed if peak_speed is not None else speed
    if peak is not None:
        lines.append(f"Dinh trong tam nhin: {peak:.0f} km/h")
    if plate:
        lines.append(f"Bien so: {plate}")
    if camera_name:
        lines.append(str(camera_name))
    lines.append(when.strftime("%Y-%m-%d %H:%M:%S %Z"))

    padding = max(8, title_size // 2)
    line_gap = max(4, body_size // 4)
    text_widths = []
    text_heights = []
    for i, line in enumerate(lines):
        font = font_title if i == 0 else font_body
        bbox = draw.textbbox((0, 0), line, font=font)
        text_widths.append(bbox[2] - bbox[0])
        text_heights.append(bbox[3] - bbox[1])

    box_w = max(text_widths) + padding * 2
    box_h = sum(text_heights) + line_gap * (len(lines) - 1) + padding * 2
    x0, y0 = padding, padding
    x1, y1 = x0 + box_w, y0 + box_h

    # Dark translucent banner
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    od.rounded_rectangle([x0, y0, x1, y1], radius=10, fill=(15, 23, 42, 200))
    # Accent bar for overspeed
    od.rectangle([x0, y0, x0 + 6, y1], fill=(239, 68, 68, 255))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(img)

    y = y0 + padding
    for i, line in enumerate(lines):
        font = font_title if i == 0 else font_body
        color = (248, 113, 113) if i == 0 else (226, 232, 240)
        draw.text((x0 + padding + 4, y), line, font=font, fill=color)
        y += text_heights[i] + line_gap

    out = io.BytesIO()
    img.save(out, format="JPEG", quality=90, optimize=True)
    return out.getvalue()


def save_stamped_jpeg(
    jpeg_bytes: bytes,
    dest: Path,
    **stamp_kwargs: Any,
) -> Path:
    stamped = stamp_speed_on_image(jpeg_bytes, **stamp_kwargs)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(stamped)
    return dest


def pick_source_jpeg(image_paths: dict[str, str] | None, event_images: list[Any] | None = None) -> bytes | None:
    """Prefer vehicle/scene frame from saved paths or multipart images."""
    if image_paths:
        for key in ("vehicle", "scene", "global", "plate", "overspeed"):
            p = image_paths.get(key)
            if p and Path(p).is_file():
                return Path(p).read_bytes()
        for p in image_paths.values():
            if p and Path(p).is_file():
                return Path(p).read_bytes()
    if event_images:
        # Prefer larger images (usually full scene)
        ranked = sorted(
            [img for img in event_images if getattr(img, "data", None)],
            key=lambda im: len(im.data),
            reverse=True,
        )
        if ranked:
            return ranked[0].data
    return None
