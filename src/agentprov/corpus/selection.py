"""The selection each snapshot of a working import corpus was imported with (MN N.1.7; NF-36, regen item 130).

A working ``corpus.json`` written by ``import`` records, in each snapshot entry imported with ``--limit``, a filter or
``--sample``, that snapshot's ``selection`` (``{filters, limit[, sample]}``, its ``limit`` the cumulative cap of the
units it holds); a snapshot imported whole records none, so an ordinary import's manifest is unchanged. The corpus is ``partial`` while any snapshot records one. A manifest
written before the per-snapshot record (``partial`` and no snapshot carrying a selection) gives every listed snapshot
its top-level ``selection``: the conservative reading, since the run it describes is not recorded; a selection-free
resume of each snapshot (the completion path) clears it.

Plain data: the importer (which writes and checks the record), ``derive``/``recompute`` (which replay each snapshot with
its own selection) and ``package`` (whose working check refuses a snapshot that records one) read it here.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

#: the selection keys a snapshot records (``until`` is a stage, never a selection)
SELECTION_KEYS = ("filters", "limit", "sample")


def is_import_selection(value: Any) -> bool:
    """Whether a snapshot entry's ``selection`` is one the import recorded (``{filters, limit[, sample]}``). A sealed
    manifest's snapshot ``selection`` is the spec's ``{include, exclude}`` (H.2), which a ``derive`` from a sealed corpus
    copies into the working manifest: a complete snapshot, never a partial import (NF-36 review)."""
    return isinstance(value, Mapping) and any(k in value for k in SELECTION_KEYS)


def snapshot_selections(manifest: Mapping[str, Any] | None) -> dict[str, dict[str, Any]]:
    """Snapshot id -> the selection that snapshot was imported with; a snapshot imported whole is absent."""
    if not isinstance(manifest, Mapping):
        return {}
    sources = manifest.get("sources")
    source = sources[0] if isinstance(sources, list) and sources and isinstance(sources[0], Mapping) else {}
    snapshots = [s for s in source.get("snapshots") or () if isinstance(s, Mapping) and isinstance(s.get("snapshot_id"), str)]
    recorded = {str(s["snapshot_id"]): dict(s["selection"]) for s in snapshots if is_import_selection(s.get("selection"))}
    if recorded or manifest.get("partial") is not True:
        return recorded
    top = manifest.get("selection")
    legacy = {k: top[k] for k in SELECTION_KEYS if isinstance(top, Mapping) and k in top}
    return {str(s["snapshot_id"]): dict(legacy) for s in snapshots}


def selection_key(selection: Mapping[str, Any] | None) -> tuple[Any, ...]:
    """What two selections must share to choose the same eligible units (N.1.7): the filters and the sample's ``n``,
    ``mode`` and ``seed`` (its ``candidates``/``selected`` are what the draw found, not what was asked). ``limit`` is
    not part of it: it is an incremental cap (it counts the units a run newly maps), so a later run with another limit,
    or none, extends the same snapshot. ``None`` is no selection."""
    selection = selection or {}
    given, drawn = selection.get("filters"), selection.get("sample")
    filters: Mapping[str, Any] = given if isinstance(given, Mapping) else {}
    sample: Mapping[str, Any] | None = drawn if isinstance(drawn, Mapping) else None
    return (
        tuple(filters.get("include_paths") or ()),
        tuple(sorted((str(k), tuple(v)) for k, v in (filters.get("select") or {}).items())),
        None if filters.get("variants") is None else tuple(filters["variants"]),
        None if sample is None else (sample.get("n"), sample.get("mode") or "first", sample.get("seed")),
    )
