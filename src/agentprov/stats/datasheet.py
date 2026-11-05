"""The field-group coverage table of a sealed corpus's ``DATASHEET.md`` (HL H.9; R-57; O.3.5).

``agentprov package`` injects :func:`renderer` into the datasheet (``SealInputs.field_groups``), so the datasheet and
``agentprov stats --tables field_groups`` share one computation: the rows are those of
:func:`agentprov.stats.tables.compute_corpus`, rendered as a Markdown table. Coverage is ``(O + D) / (cells −
not_applicable)``; the two shares are computed here from the integer columns and rounded once, exactly, to four
decimals (half to even), and a share with an empty denominator is ``-``. Formatting the six-decimal ``share()`` of the
stats row would round twice and get the fourth decimal wrong for about 0.5 % of cells (AU-MSR-2).

The table is computed over the working tree being sealed, read-only and without verification (it is about to be sealed;
its checksums do not exist yet), leaving out the executions the seal withholds (:meth:`FieldGroupRenderer.excluding`), so
it covers the released set like every other count (H.2.9; AU-BND-6). No corpus string reaches the table: its cells are source ids, profile ids, group ids
(all package or registry identifiers) and counts.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from typing import Any, Final

from agentprov.stats.exclusions import declared_exclusions
from agentprov.stats.source import open_corpus
from agentprov.stats.tables import StatsInputError, compute_corpus

__all__ = ["COLUMNS", "DatasheetFailuresError", "FieldGroupRenderer", "datasheet_field_groups", "render_rows", "renderer"]

#: The columns of the datasheet table, in order (a subset of the ``field_groups`` row).
COLUMNS: Final = ("source_id", "profile", "group", "n_executions", "cells", "not_applicable", "O", "D", "I",
                  "coverage", "observed_share")  # fmt: skip


class DatasheetFailuresError(StatsInputError):
    """An execution of the corpus could not be read or evaluated, so the field-group table would be incomplete.

    The message lists the failure codes and their counts (identifiers only, sorted); ``agentprov stats`` reports the
    same failures per execution."""

    code = "stats.datasheet.failures"


def _cell(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value).replace("\\", "\\\\").replace("|", "\\|")


def _share4(numerator: int, denominator: int) -> str:
    """``numerator / denominator`` rounded once, exactly, to four decimals (half to even); ``-`` for a zero denominator."""
    if denominator == 0:
        return "-"
    units = round(Fraction(numerator, denominator) * 10_000)
    return f"{units // 10_000}.{units % 10_000:04d}"


def _row_cells(row: Mapping[str, Any]) -> list[str]:
    denominator = int(row["cells"]) - int(row["not_applicable"])
    shares = {"coverage": _share4(int(row["O"]) + int(row["D"]), denominator),
              "observed_share": _share4(int(row["O"]), denominator)}
    return [shares[c] if c in shares else _cell(row.get(c)) for c in COLUMNS]


def render_rows(rows: Sequence[Mapping[str, Any]]) -> str:
    """The Markdown table of ``field_groups`` rows: a header, a rule and one line per row (the shares from the counts)."""
    out = ["| " + " | ".join(COLUMNS) + " |", "|" + "|".join("---" for _ in COLUMNS) + "|"]
    out += ["| " + " | ".join(_row_cells(row)) + " |" for row in rows]
    return "\n".join(out)


def datasheet_field_groups(root: str | os.PathLike[str], manifest: Mapping[str, Any] | None = None, *,
                           withheld: Collection[str] = ()) -> str:
    """The Markdown field-group table of the corpus at ``root`` (a working ``DIR.partial`` or a sealed ``DIR``).

    ``manifest`` is accepted for the datasheet hook's signature and is not read: every number comes from the index and
    the AERs, exactly as ``agentprov stats`` computes it. ``withheld`` names the executions a seal withholds: the
    working tree still holds them, and the table leaves them out so it covers the released set (H.2.9; AU-BND-6). An
    execution that cannot be read or evaluated raises :class:`DatasheetFailuresError` (``stats.datasheet.failures``)
    instead of rendering an incomplete table."""
    del manifest
    corpus = open_corpus(root, verify="none")
    tables = compute_corpus(corpus, tables=("field_groups",), exclusions=declared_exclusions(),
                            exclude_ex=frozenset(withheld))
    if tables.failures:
        # a failed execution still counts in n_executions but contributes no cells: refuse rather than seal a table
        # that silently understates the loss (package renders this before it writes, so nothing is left behind)
        listed = ", ".join(f"{code}={n}" for code, n in sorted(tables.failures.items()))
        raise DatasheetFailuresError(f"the field-group table is incomplete: executions failed ({listed})")
    rows =tables.tables.get("field_groups", [])
    if not rows:
        return "(No execution with an observed agent run: the field-group table is empty.)"
    return render_rows(rows)


@dataclass(frozen=True)
class FieldGroupRenderer:
    """The datasheet hook for the corpus at ``root``: ``manifest -> Markdown table``. :meth:`excluding` gives the hook
    for the released set of a seal that withholds executions (``agentprov package`` calls it; AU-BND-6)."""

    root: str | os.PathLike[str]
    withheld: frozenset[str] = frozenset()

    def __call__(self, manifest: Mapping[str, Any]) -> str:
        return datasheet_field_groups(self.root, manifest, withheld=self.withheld)

    def excluding(self, executions: Collection[str]) -> FieldGroupRenderer:
        return FieldGroupRenderer(self.root, self.withheld | frozenset(executions))


def renderer(root: str | os.PathLike[str]) -> Callable[[Mapping[str, Any]], str]:
    """The datasheet hook for the corpus at ``root``: ``manifest -> Markdown table`` (a :class:`FieldGroupRenderer`)."""
    return FieldGroupRenderer(root)
