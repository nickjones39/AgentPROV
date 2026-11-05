"""The daily price refresh of Run Live (D-1062). No Qt, no network.

When Run Live opens, the dialog asks ``agentprov prices status --format json`` (``agentprov-prices-status/0.1``: the
newest OpenRouter snapshot's ``written_at`` in UTC, ``refresh_due`` and the setting ``prices.auto_refresh``). When the
setting is on (unset: on) and today's refresh is due, it starts ``agentprov prices refresh --allow-network --if-stale``
as an ordinary CLI job: the GUI itself opens no connection (S11), and the CLI fetches only when no snapshot was written
today and the setting is not false, so a stale status read can never cause a second fetch. The status is read
defensively (an older CLI has no such command: then nothing is started). The dialog never waits for any of it.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any, Final

from agentprov.errors import IngestError
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.loaders import strict_json_loads

__all__ = ["STATUS_ARGV", "STATUS_FORMAT", "PricesStatus", "due", "local_time_text", "parse_status"]

STATUS_ARGV: Final = ("prices", "status", "--format", "json")
STATUS_FORMAT: Final = "agentprov-prices-status/0.1"
_LIMITS: Final = IngestLimits().replace(max_json_bytes=1024 * 1024, max_json_depth=8)


@dataclass(frozen=True, slots=True)
class PricesStatus:
    """``prices status``: when the newest OpenRouter snapshot was written (UTC; ``None``: never), whether today's
    refresh is due, whether the setting ``prices.auto_refresh`` allows it, and the snapshot's prices date."""

    refreshed_at: dt.datetime | None
    refresh_due: bool | None = None
    auto_refresh: bool | None = None
    as_of: str | None = None


def _when(value: Any) -> dt.datetime | None:
    if not isinstance(value, str) or not 10 <= len(value) <= 40:
        return None
    try:
        when = dt.datetime.fromisoformat(value.strip())
    except ValueError:
        return None
    if when.tzinfo is None:  # the CLI's times are UTC
        when = when.replace(tzinfo=dt.UTC)
    return when.astimezone(dt.UTC)


def _flag(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def parse_status(code: int, out: bytes) -> PricesStatus | None:
    """``prices status --format json``; ``None`` when the command failed or is not that document (an older CLI)."""
    if code != 0 or not out.strip():
        return None
    try:
        doc = strict_json_loads(out.strip(), _LIMITS)
    except IngestError:
        return None
    if not isinstance(doc, dict) or doc.get("format") != STATUS_FORMAT:
        return None
    raw = doc.get("openrouter_snapshot")
    snap: dict[str, Any] = raw if isinstance(raw, dict) else {}
    as_of = snap.get("as_of")
    return PricesStatus(_when(snap.get("written_at")), _flag(doc.get("refresh_due")), _flag(doc.get("auto_refresh")),
                        as_of[:10] if isinstance(as_of, str) else None)


def due(status: PricesStatus | None, *, attempted: str, today: dt.date) -> bool:
    """Whether Run Live starts today's refresh: the CLI says it is due and the setting is on, and this GUI has not
    started one today already (a failed refresh is not retried every time the dialog opens). Without a status (an
    older CLI, or the command failed) nothing is started."""
    if status is None or attempted == today.isoformat():
        return False
    return status.auto_refresh is not False and status.refresh_due is True


def local_time_text(when: dt.datetime, *, today: dt.date | None = None) -> str:
    """``today 09:14 NZDT`` or ``21 Oct 2026, 09:14 NZDT``: the time in the computer's own time zone, named."""
    local = when.astimezone()
    zone = local.tzname() or "local time"
    clock = f"{local:%H:%M} {zone}"
    if local.date() == (today or dt.date.today()):
        return f"today {clock}"
    return f"{local.day} {local:%b %Y}, {clock}"
