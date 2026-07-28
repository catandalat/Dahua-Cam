from __future__ import annotations

import json
import re
from typing import Any


_INDEXED_RE = re.compile(r"^(.+)\[(\d+)\]$")
_CODE_DATA_RE = re.compile(
    r"^Code=([^;\r\n]+)((?:;[^;\r\n=]+=[^;\r\n]+)*)?;data=\{",
    re.IGNORECASE | re.MULTILINE,
)


def _set_path(root: dict[str, Any], path: str, value: Any) -> None:
    """Set nested dict/list value from dotted path with optional [n] indices."""
    parts = path.split(".")
    cur: Any = root
    for i, part in enumerate(parts):
        is_last = i == len(parts) - 1
        m = _INDEXED_RE.match(part)
        if m:
            key, idx_s = m.group(1), int(m.group(2))
            if key not in cur or not isinstance(cur[key], list):
                cur[key] = []
            lst: list[Any] = cur[key]
            while len(lst) <= idx_s:
                lst.append({})
            if is_last:
                if isinstance(lst[idx_s], dict) and not lst[idx_s]:
                    lst[idx_s] = value
                else:
                    lst[idx_s] = value
            else:
                if not isinstance(lst[idx_s], dict):
                    lst[idx_s] = {}
                cur = lst[idx_s]
        else:
            if is_last:
                cur[part] = value
            else:
                if part not in cur or not isinstance(cur[part], dict):
                    cur[part] = {}
                cur = cur[part]


def _coerce(raw: str) -> Any:
    s = raw.strip()
    if s == "":
        return ""
    if s.lower() in ("true", "false"):
        return s.lower() == "true"
    if s.startswith("[") and s.endswith("]"):
        inner = s[1:-1].strip()
        if not inner:
            return []
        items = [x.strip().strip('"').strip("'") for x in inner.split(",")]
        out: list[Any] = []
        for it in items:
            try:
                if "." in it:
                    out.append(float(it))
                else:
                    out.append(int(it))
            except ValueError:
                out.append(it)
        return out
    try:
        if "." in s:
            return float(s)
        return int(s)
    except ValueError:
        return s.strip('"').strip("'")


def _extract_balanced_object(text: str, start: int) -> tuple[str | None, int]:
    """Return JSON object text starting at `start` (must be '{') and end index."""
    if start < 0 or start >= len(text) or text[start] != "{":
        return None, start
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1], i + 1
    return None, start


def _parse_semicolon_header(header: str) -> dict[str, Any]:
    """Parse `Code=TrafficJunction;action=Pulse;index=0` into a dict."""
    out: dict[str, Any] = {}
    for part in header.split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        k, _, v = part.partition("=")
        k, v = k.strip(), v.strip()
        if not k:
            continue
        key = {"action": "Action", "index": "Index", "code": "Code"}.get(k.lower(), k)
        out[key] = _coerce(v)
    return out


def parse_code_data_block(text: str) -> dict[str, Any] | None:
    """
    Parse Dahua eventManager text of the form:
      Code=TrafficJunction;action=Pulse;index=0;data={ ...json... }
    into a nested dict compatible with extract_detection().
    """
    m = _CODE_DATA_RE.search(text)
    if not m:
        return None
    code = m.group(1).strip()
    extra = m.group(2) or ""
    brace_at = text.find("{", m.start())
    raw_json, end = _extract_balanced_object(text, brace_at)
    if not raw_json:
        return None
    try:
        data_obj = json.loads(raw_json)
    except json.JSONDecodeError:
        try:
            data_obj = json.loads(re.sub(r",\s*}", "}", re.sub(r",\s*]", "]", raw_json)))
        except json.JSONDecodeError:
            return None
    if not isinstance(data_obj, dict):
        return None

    header = _parse_semicolon_header(f"Code={code}{extra}")
    action = header.get("Action")
    event_body: dict[str, Any] = {
        "EventBaseInfo": {
            "Code": code,
            **({"Action": action} if action is not None else {}),
        },
        **data_obj,
    }
    for nest_key in ("Data", "EventInfo", "TrafficInfo"):
        nested = data_obj.get(nest_key)
        if isinstance(nested, dict):
            for k, v in nested.items():
                event_body.setdefault(k, v)

    root: dict[str, Any] = {
        "Code": code,
        "Events": [event_body],
        **header,
        "Data": data_obj,
    }

    trailing = text[end:].strip()
    if trailing and "=" in trailing:
        for line in trailing.splitlines():
            line = line.strip()
            if not line or "=" not in line or line.startswith("--"):
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            if key:
                _set_path(root, key, _coerce(val))
    return root


def kv_lines_to_dict(text: str) -> dict[str, Any]:
    """Parse Dahua key=value lines (possibly with Events[0].Foo=bar) into nested dict.

    Also supports eventManager `Code=...;data={...}` JSON packets.
    """
    block = parse_code_data_block(text)
    if block is not None:
        return block

    root: dict[str, Any] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("--") or line.startswith("Heartbeat") or "=" not in line:
            continue
        if line.lower().startswith(("content-", "http/")):
            continue
        if line.startswith("{") or line.startswith("}") or line.startswith('"'):
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        if not key:
            continue
        if key.lower() == "code" and ";action=" in val.lower():
            header = _parse_semicolon_header(f"Code={val.split(';data=')[0]}")
            root.update(header)
            if "Code" in header:
                _set_path(root, "Events[0].EventBaseInfo.Code", header["Code"])
            if "Action" in header:
                _set_path(root, "Events[0].EventBaseInfo.Action", header["Action"])
            continue
        _set_path(root, key, _coerce(val))
    return root


def dig(data: dict[str, Any], *paths: str, default: Any = None) -> Any:
    """Try multiple dotted paths; return first hit."""
    for path in paths:
        cur: Any = data
        ok = True
        for part in path.split("."):
            m = _INDEXED_RE.match(part)
            if m:
                key, idx = m.group(1), int(m.group(2))
                if not isinstance(cur, dict) or key not in cur:
                    ok = False
                    break
                lst = cur[key]
                if not isinstance(lst, list) or idx >= len(lst):
                    ok = False
                    break
                cur = lst[idx]
            else:
                if not isinstance(cur, dict) or part not in cur:
                    ok = False
                    break
                cur = cur[part]
        if ok:
            return cur
    return default
