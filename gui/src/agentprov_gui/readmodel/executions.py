"""The executions table: ``executions.jsonl`` read once into columns (design §2.4). No Qt here.

**Why not ``CorpusReader.iter_index``.** It re-encodes every row as JCS to prove the line canonical and builds a fully
validated :class:`~agentprov.corpus.index.IndexRow`. That is the right check for a writer or a verifier, but it costs
16.4 s for the 38,281 rows of agentdyn-a-p10 (measured 2026-10-14; 55 % JCS, 37 % ``IndexRow``), far over the G1 budget
of 3 s. The table therefore reads the same file through the same strict, size-limited opener
(:meth:`CorpusReader.open_file`) and the same strict JSON loader, one record per line, and keeps only display columns,
the ``ex`` order and each line's byte offset (1.9 s for the same file). The full H.3.1 row check (``IndexRow.from_json``
plus the canonical-line test) runs for one row when its execution is opened (:func:`read_row`), before any per-execution
file is read, so nothing is displayed from an execution whose row fails the core's checks. The table's own checks: every
line is a strict JSON object under the record limit, ``ex`` is a string, and the rows are sorted and unique by ``ex``.

Table text is data: the view escapes it (S3). Sorting and filtering happen here, in Python (research §M5: a
``QSortFilterProxyModel`` over a Python model is ~100× slower at 10k rows).

**Task and outcome columns** (D-706). A full row's ``cell`` gives suite, task, attack, injection task, defence and
repeat; its ``outcome`` facet gives utility (SEM claim ``user_task_solved``) and attack succeeded (``attack_succeeded``)
through :func:`agentprov.corpus.rowvalues.outcome_states`, the function ``agentprov stats --select outcome.<claim>``
uses: ``yes`` when an element with the claim holds, ``no`` when one does not, blank when none has a ``holds`` (not
judged; a benign cell's attack success is never judged). Nothing is computed from a raw judgement. A working row has no
cell or facets: these columns stay blank, and :attr:`ExecutionTable.full_rows` tells the view to say "derive the corpus".

**Every filter is a CLI selection** (D-700): :func:`cli_selection` turns a :class:`TableFilter` into the
``agentprov stats --select`` arguments that select the same rows. Filtering by a list column (snapshots, models) or an
outcome matches any of the row's values, as the CLI does.
"""

from __future__ import annotations

import os
import threading
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any, Final

from agentprov.corpus.index import IndexError_, IndexRow
from agentprov.corpus.layout import EXECUTIONS
from agentprov.corpus.reader import CorpusReader, CorpusReadError
from agentprov.corpus.rowvalues import OUTCOME_STATES, cell_strings, outcome_states
from agentprov.errors import IngestError
from agentprov.ingest.loaders import strict_json_loads

__all__ = [
    "COLUMNS",
    "Column",
    "ExecutionTable",
    "IndexChangedError",
    "LoadCancelled",
    "TableFilter",
    "cli_selection",
    "load_table",
    "read_row",
]


@dataclass(frozen=True, slots=True)
class Column:
    key: str
    title: str
    numeric: bool = False
    vocabulary: bool = False  # a closed or small vocabulary: offered as a filter picker
    multi: bool = False  # several values per row (shown joined; a filter matches any of them)
    outcome: str | None = None  # the SEM claim of an outcome column (shown yes / no / blank)
    selector: str | None = None  # the ``agentprov stats --select`` key of this column's filter (D-706)


#: The table's columns, in display order. Facet columns are empty for working rows (they are filled by full rows only).
COLUMNS: Final[tuple[Column, ...]] = (
    Column("ex", "ex"),
    Column("status", "status", vocabulary=True, selector="status"),
    Column("completeness", "completeness", vocabulary=True, selector="completeness"),
    Column("source_id", "source", vocabulary=True, selector="source_id"),
    Column("snapshot", "snapshot", vocabulary=True, multi=True, selector="snapshot"),
    Column("unit", "unit", vocabulary=True, selector="unit"),
    Column("profile", "profile", vocabulary=True, selector="profile"),
    Column("cell.suite", "suite", vocabulary=True, selector="cell.suite"),
    Column("cell.task_id", "task", vocabulary=True, selector="cell.task_id"),
    Column("cell.attack_id", "attack", vocabulary=True, selector="cell.attack_id"),
    Column("cell.attack_target_id", "injection task", vocabulary=True, selector="cell.attack_target_id"),
    Column("cell.defense_id", "defence", vocabulary=True, selector="cell.defense_id"),
    Column("outcome.attack_succeeded", "attack succeeded", vocabulary=True, outcome="attack_succeeded",
           selector="outcome.attack_succeeded"),
    Column("outcome.user_task_solved", "utility", vocabulary=True, outcome="user_task_solved",
           selector="outcome.user_task_solved"),
    Column("model.requested", "model.requested", vocabulary=True, multi=True, selector="facet.model.requested"),
    Column("model.served", "model.served", vocabulary=True, multi=True, selector="facet.model.served"),
    Column("judgements", "judgements"),
    Column("cell.repeat", "repeat", numeric=True),
    Column("n.messages", "n.messages", numeric=True),
    Column("n.model_calls", "n.calls", numeric=True),
    Column("n.tool_executions", "n.tools", numeric=True),
    Column("n_issues", "issues", numeric=True),
    Column("attempt", "attempt", numeric=True),
)
_KEYS: Final = tuple(c.key for c in COLUMNS)
_COUNTS: Final = ("n.messages", "n.model_calls", "n.tool_executions")
_BY_KEY: Final = {c.key: c for c in COLUMNS}
_CELL_TEXT: Final = ("suite", "task_id", "attack_id", "attack_target_id", "defense_id")
#: how an outcome state reads in the table and its filter
OUTCOME_LABELS: Final = {"true": "yes", "false": "no", "none": "not judged"}


class LoadCancelled(Exception):
    """The load was cancelled (another corpus was opened)."""


class IndexChangedError(CorpusReadError):
    """``executions.jsonl`` was replaced after the table was read: the table must be reloaded."""

    code = "gui.index.changed"


def _str(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _joined(value: Any) -> str | None:
    if isinstance(value, list) and value and all(isinstance(v, str) for v in value):
        return ", ".join(value)
    return None


def _strings(value: Any) -> tuple[str, ...]:
    return tuple(v for v in value if isinstance(v, str)) if isinstance(value, list) else ()


def _judgement_text(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, dict) and isinstance(value.get("$dec"), str):
        return str(value["$dec"])
    return str(value) if isinstance(value, int | str) else "…"


def _judgements(outcome: Any) -> str | None:
    parts = [f"{e['name']}={_judgement_text(e.get('value'))}" for e in (outcome if isinstance(outcome, list) else [])
             if isinstance(e, dict) and isinstance(e.get("name"), str) and e.get("value") is not None]
    return ", ".join(parts) or None


def _outcome_text(states: tuple[str, ...]) -> str | None:
    return "yes" if "true" in states else "no" if "false" in states else None


def _row_values(obj: dict[str, Any]) -> tuple[tuple[Any, ...], dict[str, tuple[str, ...]]]:
    """The display values of one row (``_KEYS`` order) and its multi-valued columns (any-of filtering)."""
    facets = obj.get("facets")
    full = isinstance(facets, dict)
    facets = facets if isinstance(facets, dict) else {}
    raw_cell = obj.get("cell")
    cell: dict[str, Any] = raw_cell if isinstance(raw_cell, dict) else {}
    issues = obj.get("issues")
    outcome = facets.get("outcome")
    sets: dict[str, tuple[str, ...]] = {
        "snapshot": _strings(obj.get("snapshot_ids")),
        "model.requested": _strings(facets.get("model.requested")),
        "model.served": _strings(facets.get("model.served")),
        # a working row has no outcome facet: no state at all, so no outcome filter matches it (as the CLI)
        **{c.key: tuple(outcome_states(outcome, c.outcome)) if full else () for c in COLUMNS if c.outcome},
    }
    repeat = cell.get("repeat")
    by_key: dict[str, Any] = {
        "ex": obj["ex"], "status": _str(obj.get("status")), "completeness": _str(obj.get("completeness")),
        "source_id": _str(obj.get("source_id")), "snapshot": _joined(obj.get("snapshot_ids")),
        "unit": _str(obj.get("unit")), "profile": _str(obj.get("profile")),
        **{f"cell.{m}": ", ".join(cell_strings(cell.get(m))) or None for m in _CELL_TEXT},
        **{c.key: _outcome_text(sets[c.key]) for c in COLUMNS if c.outcome},
        "model.requested": _joined(facets.get("model.requested")), "model.served": _joined(facets.get("model.served")),
        "judgements": _judgements(outcome), "cell.repeat": _int(repeat),
        **{k: _int(facets.get(k)) for k in _COUNTS},
        "n_issues": len(issues) if isinstance(issues, list) else None, "attempt": _int(obj.get("attempt")),
    }  # fmt: skip
    return tuple(by_key[k] for k in _KEYS), sets


@dataclass(frozen=True, slots=True)
class TableFilter:
    """Closed-vocabulary pickers (column key → allowed values) and a substring over ``ex``; an issue code picker."""

    pickers: tuple[tuple[str, frozenset[str]], ...] = ()
    ex_contains: str = ""
    issue_code: str | None = None

    @property
    def empty(self) -> bool:
        return not self.pickers and not self.ex_contains and self.issue_code is None


@dataclass(slots=True)
class ExecutionTable:
    """Column-oriented rows of one corpus index, in ``ex`` order. Immutable once loaded."""

    root: str
    identity: tuple[int, int, int]  # (st_ino, st_size, st_mtime_ns) of executions.jsonl when it was read
    columns: dict[str, list[Any]] = field(default_factory=lambda: {k: [] for k in _KEYS})
    #: per row, the values a multi or outcome column's filter matches (any of them)
    sets: dict[str, list[tuple[str, ...]]] = field(default_factory=lambda: {
        c.key: [] for c in COLUMNS if c.multi or c.outcome})
    offsets: list[int] = field(default_factory=list)
    issues: list[tuple[str, ...]] = field(default_factory=list)
    full_rows: int = 0  # rows with ``cell`` and facets (H.3.1); 0 for a working corpus
    load_seconds: float = 0.0

    def __len__(self) -> int:
        return len(self.offsets)

    def value(self, row: int, key: str) -> Any:
        return self.columns[key][row]

    def ex(self, row: int) -> str:
        return str(self.columns["ex"][row])

    def vocabulary(self, key: str, limit: int = 500) -> list[str]:
        """The distinct values a vocabulary column's filter offers (at most ``limit``), sorted; ``[]`` if there are
        more. A multi column offers its single values; an outcome column offers ``true``, ``false``, ``none`` (those
        present)."""
        seen: set[str] = set()
        values: Iterable[Any] = ([v for vs in self.sets[key] for v in vs] if key in self.sets else self.columns[key])
        for v in values:
            if isinstance(v, str):
                seen.add(v)
                if len(seen) > limit:
                    return []
        if _BY_KEY[key].outcome:
            return [s for s in OUTCOME_STATES if s in seen]
        return sorted(seen)

    def issue_codes(self, limit: int = 500) -> list[str]:
        seen: set[str] = set()
        for codes in self.issues:
            seen.update(codes)
            if len(seen) > limit:
                return []
        return sorted(seen)

    def non_empty_columns(self) -> list[str]:
        return [k for k in _KEYS if any(v is not None for v in self.columns[k])]

    def select(self, flt: TableFilter, sort_key: str = "ex", descending: bool = False) -> list[int]:
        """Row numbers that pass ``flt``, ordered by ``sort_key`` (missing values last, ties by ``ex``)."""
        rows: Iterable[int] = range(len(self))
        for key, allowed in flt.pickers:
            if key in self.sets:
                sets = self.sets[key]
                rows = [r for r in rows if any(v in allowed for v in sets[r])]
            else:
                col = self.columns[key]
                rows = [r for r in rows if col[r] in allowed]
        if flt.ex_contains:
            needle = flt.ex_contains.lower()
            exs = self.columns["ex"]
            rows = [r for r in rows if needle in exs[r]]
        if flt.issue_code is not None:
            code = flt.issue_code
            rows = [r for r in rows if code in self.issues[r]]
        chosen = list(rows)
        if sort_key == "ex":
            if descending:
                chosen.reverse()
            return chosen
        col = self.columns[sort_key]
        present = [r for r in chosen if col[r] is not None]
        missing = [r for r in chosen if col[r] is None]
        present.sort(key=col.__getitem__, reverse=descending)  # stable: ties keep ex order
        return present + missing


def _identity(reader: CorpusReader) -> tuple[int, int, int]:
    st = os.lstat(reader.root / EXECUTIONS)
    return (st.st_ino, st.st_size, st.st_mtime_ns)


def load_table(
    reader: CorpusReader,
    *,
    chunk: int = 4096,
    on_chunk: Callable[[int], None] | None = None,
    cancel: threading.Event | None = None,
) -> ExecutionTable:
    """Read ``executions.jsonl`` into an :class:`ExecutionTable` (see the module docstring).

    ``on_chunk(rows_so_far)`` is called every ``chunk`` rows; ``cancel`` stops the load with :class:`LoadCancelled`.
    Raises :class:`~agentprov.corpus.reader.CorpusReadError` for a file the table cannot trust; the message names a line
    number and a closed code, never corpus text.
    """
    import time

    started = time.perf_counter()
    if not reader.exists(EXECUTIONS):
        return ExecutionTable(str(reader.root), (0, 0, 0))
    limits = reader.limits
    cap = limits.max_jsonl_line_bytes + 2
    table = ExecutionTable(str(reader.root), _identity(reader))
    cols = [table.columns[k] for k in _KEYS]
    previous: bytes | None = None
    offset = 0
    number = 0
    with reader.open_file(EXECUTIONS) as stream:
        while True:
            raw = stream.readline(cap)
            if not raw:
                break
            number += 1
            if not raw.endswith(b"\n"):
                raise CorpusReadError(f"executions.jsonl line {number}: no final LF or over the line limit",
                                      code="corpus.read.index")
            try:
                obj = strict_json_loads(raw[:-1], limits, record=True)
            except IngestError as exc:
                raise CorpusReadError(f"executions.jsonl line {number}: not strict JSON ({exc.code})",
                                      code="corpus.read.index") from None
            if not isinstance(obj, dict) or not isinstance(obj.get("ex"), str) or not obj["ex"].isascii():
                raise CorpusReadError(f"executions.jsonl line {number}: not an index row", code="corpus.read.index")
            key = obj["ex"].encode("ascii")
            if previous is not None and key <= previous:
                raise CorpusReadError(f"executions.jsonl line {number}: not sorted by ex, or a duplicate",
                                      code="corpus.read.index")
            previous = key
            values, sets = _row_values(obj)
            for col, value in zip(cols, values, strict=True):
                col.append(value)
            for key, members in sets.items():
                table.sets[key].append(members)
            if isinstance(obj.get("facets"), dict):
                table.full_rows += 1
            issues = obj.get("issues")
            table.issues.append(tuple(i for i in issues if isinstance(i, str)) if isinstance(issues, list) else ())
            table.offsets.append(offset)
            offset += len(raw)
            if number % chunk == 0:
                if cancel is not None and cancel.is_set():
                    raise LoadCancelled
                if on_chunk is not None:
                    on_chunk(number)
    table.load_seconds = time.perf_counter() - started
    return table


def read_row(reader: CorpusReader, table: ExecutionTable, row: int) -> IndexRow:
    """The fully checked :class:`IndexRow` of table row ``row``: the line is re-read at its offset, parsed strictly,
    validated by ``IndexRow.from_json`` against the layout, and must be in canonical (JCS) form (H.3.1)."""
    if _identity(reader) != table.identity:
        raise IndexChangedError("executions.jsonl changed after the table was read; reload the corpus")
    limits = reader.limits
    with reader.open_file(EXECUTIONS) as stream:
        stream.seek(table.offsets[row])
        raw = stream.readline(limits.max_jsonl_line_bytes + 2)
    try:
        value = strict_json_loads(raw.rstrip(b"\n"), limits, record=True)
        index_row = IndexRow.from_json(value, reader.layout)
    except (IngestError, IndexError_) as exc:
        raise CorpusReadError(f"executions.jsonl row {row + 1}: not an index row ({exc.code})",
                              code="corpus.read.index") from None
    if index_row.line() != raw or index_row.ex != table.ex(row):
        raise CorpusReadError(f"executions.jsonl row {row + 1}: not in canonical (JCS) form", code="corpus.read.index")
    return index_row


def vocabulary_columns() -> Sequence[Column]:
    return [c for c in COLUMNS if c.vocabulary]


def cli_selection(flt: TableFilter) -> tuple[list[str], list[str]]:
    """The ``agentprov stats --select`` arguments that select the rows ``flt`` keeps, and notes on any part with no CLI
    spelling (the id search; a value with a comma, which ``--select K=V,V`` would split)."""
    args: list[str] = []
    notes: list[str] = []
    for key, allowed in flt.pickers:
        selector = _BY_KEY[key].selector if key in _BY_KEY else None
        if selector is None:
            notes.append(f"{key}: no CLI selector")
            continue
        if any("," in v for v in allowed):
            notes.append(f"{key}: a value with a comma has no --select spelling")
            continue
        args += ["--select", f"{selector}={','.join(sorted(allowed))}"]
    if flt.issue_code is not None:
        if "," in flt.issue_code:
            notes.append("issue: a code with a comma has no --select spelling")
        else:
            args += ["--select", f"issue={flt.issue_code}"]
    if flt.ex_contains:
        notes.append("the id search is a view search with no CLI selector (render takes the ids with --ex)")
    return args, notes
