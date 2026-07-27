from __future__ import annotations

import re
from typing import Any


_INDEXED_RE = re.compile(r"^(.+)\[(\d+)\]$")


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
                # Prefer scalar overwrite when leaf is empty dict placeholder
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
    # array-like [a, b, c]
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


def kv_lines_to_dict(text: str) -> dict[str, Any]:
    """Parse Dahua key=value lines (possibly with Events[0].Foo=bar) into nested dict."""
    root: dict[str, Any] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("--") or line.startswith("Heartbeat") or "=" not in line:
            continue
        # Skip HTTP-ish headers accidentally included
        if line.lower().startswith(("content-", "http/")):
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        if not key:
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
