"""Opening-hours parsing. Format: {"mon": [["09:00","17:00"]], ...}.

A weekday that is absent or empty means closed that day. `None` hours mean
unknown (the optimizer assumes open but emits a warning).
"""

from __future__ import annotations

import itertools
import re
from typing import Any

WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
_HHMM = re.compile(r"^(\d{1,2}):(\d{2})$")

Windows = dict[int, list[tuple[int, int]]]


def parse_hhmm(value: str) -> int:
    m = _HHMM.match(value.strip())
    if not m:
        raise ValueError(f"invalid time '{value}', expected HH:MM")
    h, mi = int(m.group(1)), int(m.group(2))
    if mi > 59 or h > 24 or (h == 24 and mi != 0):
        raise ValueError(f"invalid time '{value}'")
    return h * 60 + mi


def fmt_hhmm(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def parse_hours(raw: Any) -> Windows | None:
    """Return weekday(0=Mon) -> sorted windows in minutes, or None if unknown."""
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError("opening hours must be an object keyed by weekday")
    out: Windows = {}
    for key, spans in raw.items():
        if key not in WEEKDAYS:
            raise ValueError(f"unknown weekday key '{key}'")
        if not isinstance(spans, list):
            raise ValueError(f"hours for '{key}' must be a list of [open, close]")
        wins: list[tuple[int, int]] = []
        for span in spans:
            if not (isinstance(span, (list, tuple)) and len(span) == 2):
                raise ValueError(f"bad window for '{key}'")
            a, b = parse_hhmm(str(span[0])), parse_hhmm(str(span[1]))
            if a >= b:
                raise ValueError(f"window for '{key}' must open before it closes")
            wins.append((a, b))
        wins.sort()
        for (_, e1), (s2, _) in itertools.pairwise(wins):
            if s2 < e1:
                raise ValueError(f"overlapping windows on '{key}'")
        if wins:
            out[WEEKDAYS.index(key)] = wins
    return out
