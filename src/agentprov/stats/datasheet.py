"""The field-group coverage table of a sealed corpus's ``DATASHEET.md`` (HL H.9; R-57; O.3.5).

``agentprov package`` injects :func:`renderer` into the datasheet (``SealInputs.field_groups``), so the datasheet and
``agentprov stats --tables field_groups`` share one computation: the rows are those of
:func:`agentprov.stats.tables.compute_corpus`, rendered as a Markdown table. Coverage is ``(O + D) / (cells −
not_applicable)``; values are written with four decimals, and a share with an empty denominator is ``-``.

The table is computed over the working tree being sealed, read-only and without verification (it is about to be sealed;
its checksums do not exist yet). No corpus string reaches the table: its cells are source ids, profile ids, group ids
(all package or registry identifiers) and counts.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from typing import Any, Final

from agentprov.stats.exclusions import declared_exclusions
from agentprov.stats.source import open_corpus
from agentprov.stats.tables import StatsInputError, compute_corpus

__all__ = ["COLUMNS", "DatasheetFailuresError", "datasheet_field_groups", "renderer"]

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


def datasheet_field_groups(root: str | os.PathLike[str], manifest: Mapping[str, Any] | None = None) -> str:
    """The Markdown field-group table of the corpus at ``root`` (a working ``DIR.partial`` or a sealed ``DIR``).

    ``manifest`` is accepted for the datasheet hook's signature and is not read: every number comes from the index and
    the AERs, exactly as ``agentprov stats`` computes it. An execution that cannot be read or evaluated raises
    :class:`DatasheetFailuresError` (``stats.datasheet.failures``) instead of rendering an incomplete table."""
    del manifest
    corpus = open_corpus(root, verify="none")
    tables = compute_corpus(corpus, tables=("field_groups",), exclusions=declared_exclusions())
    if tables.failures:
        # a failed execution still counts in n_executions but contributes no cells: refuse rather than seal a table
        # that silently understates the loss (package renders this before it writes, so nothing is left behind)
        listed = ", ".join(f"{code}={n}" for code, n in sorted(tables.failures.items()))
        raise DatasheetFailuresError(f"the field-group table is incomplete: executions failed ({listed})")
    rows =tables.tables.get("field_groups", [])
    if not rows:
        return "(No execution with an observed agent run: the field-group table is empty.)"
    out = ["| " + " | ".join(COLUMNS) + " |", "|" + "|".join("---" for _ in COLUMNS) + "|"]
    out += ["| " + " | ".join(_cell(row.get(c)) for c in COLUMNS) + " |" for row in rows]
    return "\n".join(out)


def renderer(root: str | os.PathLike[str]) -> Callable[[Mapping[str, Any]], str]:
    """The datasheet hook for the corpus at ``root``: ``manifest -> Markdown table``."""

    def render(manifest: Mapping[str, Any]) -> str:
        return datasheet_field_groups(root, manifest)

    return render
