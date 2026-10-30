"""The run-state mark of a working import corpus (D-610; MN N.1.10(2), (5); HL H.2).

An ``import`` run that stops before it ran to the end leaves each snapshot it was importing marked
``incomplete: {"reason": "drained" | "interrupted"}`` in the working ``corpus.json``, and the corpus ``partial``:

* ``drained``: a ``--control-file`` drain (D-394) stopped it at a batch boundary;
* ``interrupted``: it raised (a first SIGINT, SIGTERM or SIGHUP, a ``stop`` request, or any error) and flushed what
  it held on the way out.

A run killed outright (SIGKILL, or the second signal's ``os._exit``) writes nothing: a fresh corpus then has no
``corpus.json`` and an existing one keeps its previous manifest and rows (the index is flushed only at the end).

The mark records what happened, not a selection: the executions a stopped run held need not be any selection's (a
drained completion of a filtered snapshot holds units outside its filter), so no ``--limit`` is invented for them. A
drain that NF-36's cumulative cap describes (a drained ``--limit`` run, or a capped snapshot's completion or
same-selection run, from the source, whose last mapped candidate ended in a unit the cap counts) is not marked: the
snapshot stays partial through its selection and a re-map maps the same units. An interrupted run is always marked. A
later run of the snapshot that runs to the end with nothing left to map (the same selection or none, and no
``--limit`` short of exhausting it) clears the mark. Until then ``package`` refuses the corpus
(``package.refused.incomplete``), and so do ``derive`` and ``recompute`` (``corpus.derive.incomplete``): a re-map would
map what the raw store holds, not what the corpus holds. An ordinary corpus carries no mark, so its manifest is
unchanged.

Plain data: the importer writes the mark; ``package`` and ``derive``/``recompute`` read it here.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

__all__ = ["REASONS", "incomplete_record", "incomplete_snapshots", "is_incomplete_record"]

#: why a run stopped before it ran to the end
REASONS: Final = ("drained", "interrupted")


def incomplete_record(reason: str) -> dict[str, str]:
    """The snapshot member a stopped run records."""
    if reason not in REASONS:
        raise ValueError(f"unknown incomplete reason {reason!r}")
    return {"reason": reason}


def is_incomplete_record(value: Any) -> bool:
    return isinstance(value, Mapping) and value.get("reason") in REASONS


def incomplete_snapshots(manifest: Mapping[str, Any] | None) -> dict[str, str]:
    """Snapshot id -> the reason its last stopped run gave, for every snapshot a stopped run marked."""
    if not isinstance(manifest, Mapping):
        return {}
    sources = manifest.get("sources")
    source = sources[0] if isinstance(sources, list) and sources and isinstance(sources[0], Mapping) else {}
    out: dict[str, str] = {}
    for snapshot in source.get("snapshots") or ():
        if isinstance(snapshot, Mapping) and isinstance(snapshot.get("snapshot_id"), str):
            mark = snapshot.get("incomplete")
            if isinstance(mark, Mapping) and is_incomplete_record(mark):
                out[str(snapshot["snapshot_id"])] = str(mark["reason"])
    return out
