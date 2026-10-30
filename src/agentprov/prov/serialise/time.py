"""The ``xsd:dateTime`` predicate of E.5.3 item 7 (shared with the validators; B VAL-11).

A time is emitted as ``prov:startTime``/``prov:endTime`` only when it is an RFC 3339 instant with an offset and at most
6 fractional digits; it is then written as ``datetime.isoformat()`` of the parsed value in UTC (``+00:00``), the only
form the pinned ``prov`` library writes back unchanged (caveat C3). Anything else is emitted verbatim as
``apv:startTimeLexical``/``apv:endTimeLexical``. The verbatim source value stays in AER ``t.raw`` and is never read here.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Final

__all__ = ["RFC3339_RE", "prov_time"]

RFC3339_RE: Final = re.compile(
    r"(?P<date>\d{4}-\d{2}-\d{2})[Tt](?P<time>\d{2}:\d{2}:\d{2})(?:\.(?P<frac>\d+))?(?P<off>[Zz]|[+-]\d{2}:\d{2})",
    re.ASCII,  # \d is [0-9] only; other Nd digits were already refused by fromisoformat (escaping audit F-12)
)


def prov_time(value: object) -> str | None:
    """The canonical ``xsd:dateTime`` lexical form of ``value``, or ``None`` when it fails the E.5.3 conditions."""
    if not isinstance(value, str):
        return None
    match = RFC3339_RE.fullmatch(value)
    if match is None:
        return None
    frac = match.group("frac") or ""
    if len(frac) > 6:
        return None
    off = match.group("off")
    off = "+00:00" if off in ("Z", "z") else off
    text = f"{match.group('date')}T{match.group('time')}" + (f".{frac.ljust(6, '0')}" if frac else "") + off
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed.astimezone(UTC).isoformat()
