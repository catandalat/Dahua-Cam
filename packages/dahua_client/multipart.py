from __future__ import annotations

import re
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass, field
from typing import Any

from dahua_client.kv_parser import dig, kv_lines_to_dict


@dataclass
class ImagePart:
    kind: str  # plate | vehicle | scene | unknown
    offset: int
    length: int
    width: int | None = None
    height: int | None = None
    data: bytes = b""


@dataclass
class MultipartEvent:
    headers: dict[str, str] = field(default_factory=dict)
    text: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    binary: bytes = b""
    images: list[ImagePart] = field(default_factory=list)
    is_heartbeat: bool = False

    @property
    def event_code(self) -> str | None:
        return dig(
            self.data,
            "Events[0].EventBaseInfo.Code",
            "Code",
            default=None,
        )

    @property
    def first_event(self) -> dict[str, Any]:
        events = self.data.get("Events")
        if isinstance(events, list) and events:
            return events[0] if isinstance(events[0], dict) else {}
        return self.data


_BOUNDARY_RE = re.compile(rb"boundary=([^\s;]+)", re.I)
_HEADER_RE = re.compile(rb"^([\w-]+):\s*(.+)$", re.I | re.M)


def extract_boundary(content_type: str | bytes | None) -> bytes | None:
    if not content_type:
        return None
    raw = content_type if isinstance(content_type, bytes) else content_type.encode()
    m = _BOUNDARY_RE.search(raw)
    if not m:
        return None
    b = m.group(1).strip().strip(b'"')
    return b


def _parse_part(raw: bytes) -> MultipartEvent:
    if raw.startswith(b"--"):
        # strip leading boundary residue
        idx = raw.find(b"\n")
        raw = raw[idx + 1 :] if idx >= 0 else raw

    sep = b"\r\n\r\n"
    sep2 = b"\n\n"
    if sep in raw:
        header_blob, body = raw.split(sep, 1)
    elif sep2 in raw:
        header_blob, body = raw.split(sep2, 1)
    else:
        header_blob, body = b"", raw

    headers: dict[str, str] = {}
    for m in _HEADER_RE.finditer(header_blob):
        headers[m.group(1).decode(errors="ignore").lower()] = m.group(2).decode(errors="ignore").strip()

    ctype = headers.get("content-type", "")
    event = MultipartEvent(headers=headers)

    # Heartbeat parts are often plain text
    if body.strip() in (b"Heartbeat", b"Heartbeat\r\n", b"Heartbeat\n") or body.strip().startswith(
        b"Heartbeat"
    ):
        event.is_heartbeat = True
        event.text = "Heartbeat"
        return event

    if "text" in ctype or ctype == "" or "x-www-form-urlencoded" in ctype:
        # May contain text then binary appended, or pure text
        text_end = _find_binary_start(body)
        text_bytes = body[:text_end] if text_end >= 0 else body
        binary = body[text_end:] if text_end >= 0 else b""
        # Also handle Content-Length based binary after text block inside same part
        try:
            text = text_bytes.decode("utf-8", errors="ignore")
        except Exception:
            text = text_bytes.decode("latin-1", errors="ignore")
        if "Heartbeat" in text and "=" not in text:
            event.is_heartbeat = True
            event.text = text.strip()
            return event
        event.text = text
        event.data = kv_lines_to_dict(text)
        event.binary = binary
        event.images = _extract_images(event.data, binary)
        return event

    # image/* or application/octet-stream alone
    event.binary = body
    event.images = [ImagePart(kind="unknown", offset=0, length=len(body), data=body)]
    return event


def _find_binary_start(body: bytes) -> int:
    """Heuristic: JPEG/PNG magic after text section."""
    for magic in (b"\xff\xd8\xff", b"\x89PNG"):
        idx = body.find(magic)
        if idx > 0:
            return idx
    return -1


def _extract_images(data: dict[str, Any], binary: bytes) -> list[ImagePart]:
    ev = {}
    events = data.get("Events")
    if isinstance(events, list) and events and isinstance(events[0], dict):
        ev = events[0]
    else:
        ev = data

    candidates: list[tuple[str, Any]] = []

    def walk(obj: Any, prefix: str = "") -> None:
        if not isinstance(obj, dict):
            return
        # Image node with Offset/Length
        if "Offset" in obj and "Length" in obj and (
            "Image" in prefix or prefix.endswith("Image") or "Scene" in prefix or "Vehicle" in prefix
        ):
            candidates.append((prefix or "Image", obj))
        for k, v in obj.items():
            path = f"{prefix}.{k}" if prefix else k
            if isinstance(v, dict):
                if k in ("Image", "OriginalVehicle", "SceneImage", "PlateImage") or (
                    "Offset" in v and "Length" in v
                ):
                    if "Offset" in v and "Length" in v:
                        candidates.append((path, v))
                walk(v, path)
            elif isinstance(v, list):
                for i, item in enumerate(v):
                    walk(item, f"{path}[{i}]")

    walk(ev)
    # Also common paths
    for path, kind in (
        ("Object.Image", "plate"),
        ("TrafficCar.PlateImage", "plate"),
        ("OriginalVehicle", "vehicle"),
        ("Vehicle.Image", "vehicle"),
        ("SceneImage", "scene"),
        ("Picture", "scene"),
    ):
        node = dig(ev, path)
        if isinstance(node, dict) and "Offset" in node and "Length" in node:
            candidates.append((kind, node))

    images: list[ImagePart] = []
    seen: set[tuple[int, int]] = set()
    for path, node in candidates:
        try:
            offset = int(node.get("Offset", 0))
            length = int(node.get("Length", 0))
        except (TypeError, ValueError):
            continue
        if length <= 0:
            continue
        key = (offset, length)
        if key in seen:
            continue
        seen.add(key)
        kind = "unknown"
        pl = path.lower()
        if "plate" in pl or path.endswith("Object.Image") or path == "plate":
            kind = "plate"
        elif "scene" in pl:
            kind = "scene"
        elif "vehicle" in pl or "original" in pl:
            kind = "vehicle"
        elif path in ("plate", "vehicle", "scene"):
            kind = path

        chunk = b""
        if binary and offset + length <= len(binary):
            chunk = binary[offset : offset + length]
        elif binary and length <= len(binary) and offset == 0:
            chunk = binary[:length]
        images.append(
            ImagePart(
                kind=kind,
                offset=offset,
                length=length,
                width=_as_int(node.get("Width")),
                height=_as_int(node.get("Height")),
                data=chunk,
            )
        )

    # Fallback: whole binary is one image
    if not images and binary and binary[:3] in (b"\xff\xd8\xff",) or (
        binary and binary[:4] == b"\x89PNG"
    ):
        images.append(ImagePart(kind="scene", offset=0, length=len(binary), data=binary))

    return images


def _as_int(v: Any) -> int | None:
    try:
        return int(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def iter_multipart_parts(buffer: bytes, boundary: bytes) -> tuple[list[bytes], bytes]:
    """Split buffer into complete parts; return (parts, remainder)."""
    delim = b"--" + boundary
    parts: list[bytes] = []
    # Normalize
    if not buffer:
        return [], b""

    chunks = buffer.split(delim)
    # First chunk is preamble
    remainder = b""
    for i, chunk in enumerate(chunks):
        if i == 0:
            continue
        if chunk.startswith(b"--"):
            # closing boundary
            continue
        if chunk.startswith(b"\r\n"):
            chunk = chunk[2:]
        elif chunk.startswith(b"\n"):
            chunk = chunk[1:]
        # Incomplete if we are on the last piece and buffer didn't end with next delim
        # Caller should only pass complete segments; we treat last as remainder if no trailing delim
        parts.append(chunk.rstrip(b"\r\n"))

    # If buffer does not end with boundary, last part may be incomplete
    if not buffer.rstrip().endswith(delim) and not buffer.rstrip().endswith(delim + b"--"):
        if parts:
            remainder = delim + parts.pop()
            # restore proper framing for remainder
            if not remainder.startswith(delim):
                remainder = delim + b"\r\n" + remainder
    return parts, remainder


def parse_multipart_buffer(data: bytes, boundary: bytes) -> list[MultipartEvent]:
    delim = b"--" + boundary
    events: list[MultipartEvent] = []
    segments = data.split(delim)
    for seg in segments[1:]:
        if seg.startswith(b"--"):
            break
        if seg.startswith(b"\r\n"):
            seg = seg[2:]
        elif seg.startswith(b"\n"):
            seg = seg[1:]
        # trim trailing CRLF
        if seg.endswith(b"\r\n"):
            seg = seg[:-2]
        elif seg.endswith(b"\n"):
            seg = seg[:-1]
        if not seg.strip():
            continue
        events.append(_parse_part(seg))
    return events


async def parse_multipart_stream(
    byte_iter: AsyncIterator[bytes],
    boundary: bytes,
) -> AsyncIterator[MultipartEvent]:
    """Incrementally parse multipart/x-mixed-replace from an async byte stream."""
    delim = b"--" + boundary
    buf = b""
    async for chunk in byte_iter:
        buf += chunk
        while True:
            # Find next complete part: delim ... delim
            first = buf.find(delim)
            if first < 0:
                # keep buffer bounded
                if len(buf) > 8_000_000:
                    buf = buf[-1_000_000:]
                break
            next_pos = buf.find(delim, first + len(delim))
            if next_pos < 0:
                # incomplete
                if first > 0:
                    buf = buf[first:]
                break
            part = buf[first + len(delim) : next_pos]
            buf = buf[next_pos:]
            if part.startswith(b"--"):
                return
            if part.startswith(b"\r\n"):
                part = part[2:]
            elif part.startswith(b"\n"):
                part = part[1:]
            if part.endswith(b"\r\n"):
                part = part[:-2]
            if not part.strip():
                continue
            yield _parse_part(part)


def parse_multipart_stream_sync(
    byte_iter: Iterator[bytes],
    boundary: bytes,
) -> Iterator[MultipartEvent]:
    delim = b"--" + boundary
    buf = b""
    for chunk in byte_iter:
        buf += chunk
        while True:
            first = buf.find(delim)
            if first < 0:
                if len(buf) > 8_000_000:
                    buf = buf[-1_000_000:]
                break
            next_pos = buf.find(delim, first + len(delim))
            if next_pos < 0:
                if first > 0:
                    buf = buf[first:]
                break
            part = buf[first + len(delim) : next_pos]
            buf = buf[next_pos:]
            if part.startswith(b"--"):
                return
            if part.startswith(b"\r\n"):
                part = part[2:]
            elif part.startswith(b"\n"):
                part = part[1:]
            if part.endswith(b"\r\n"):
                part = part[:-2]
            if not part.strip():
                continue
            yield _parse_part(part)
