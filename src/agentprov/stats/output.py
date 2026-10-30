"""Deterministic renderings of a stats report (MN N.2.12): JSON (JCS), text, Markdown and CSV.

Every format is a pure function of the report document (:meth:`agentprov.stats.StatsReport.to_json`): rows keep the order
the tables give them (sorted), columns follow :data:`COLUMNS` (unknown columns last, sorted), and no wall-clock value is
written. ``json`` is the RFC 8785 (JCS) serialisation plus one LF, validated in the tests against
``tests/cli/schemas/stats-0.1.schema.json``.

* ``text``: per corpus a label line (its ``corpus_id`` and digests pass :func:`agentprov.ingest.quote.escape_untrusted_line`,
  so the label is one line with no raw control character), then per table an aligned plain-text table.
* ``markdown``: ``## corpus`` / ``### table`` headings and pipe tables; every cell and the corpus heading pass
  :func:`agentprov.ingest.quote.escape_markdown` (``|`` and ``\\`` escaped, no raw HTML, link, image or code-span
  breakout; F-12C-04, G.8.6).
* ``csv``: one block per (corpus, table), each with its own header row whose first two columns are ``corpus_id`` and
  ``table`` (the ``corpus_id`` cell escaped like the text label); blocks are separated by one empty line. A string cell
  that starts with ``=``, ``+``, ``-``, ``@``, TAB or CR is prefixed with ``'`` so that a spreadsheet never evaluates a
  data-derived label as a formula.

Lists are written space-separated and ``null`` as an empty cell (``-`` in text). Labels in the report are already
closed-vocabulary values or escaped (G.8.6); nothing here adds content.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Mapping, Sequence
from typing import Any, Final

from agentprov.ingest.quote import escape_markdown, escape_untrusted_line
from agentprov.io.canonical import jcs_bytes

__all__ = ["COLUMNS", "FORMATS", "render"]

FORMATS: Final = ("text", "csv", "json", "markdown")
_REASONS: Final = ("not_recorded", "undeclared", "lost", "overwritten", "withheld", "ambiguous", "not_captured", "not_applicable")
_STATUS_COLUMNS: Final = ("O", "D", "I", *_REASONS)
#: The preferred column order of each table.
COLUMNS: Final[Mapping[str, tuple[str, ...]]] = {
    "counts": (
        "source_id", "profile", "registry_parts", "registry_import_status", "records", "n_executions", "n_outcome_only",
        "unit_agent_execution", "unit_outcome_only", "unit_scenario", "execution_observed_true", "execution_observed_false",
        "status_ok", "status_ok_with_issues", "status_failed", "completeness_verified_complete",
        "completeness_known_incomplete", "completeness_unverifiable", "prov_output", "rate_excluded",
    ),
    "register": ("stage", "code", "severity", "disposition", "n"),
    "statements": ("source_id", "profile", "bundle", "method", "stype", "evidence", "rule", "n"),
    "statements_by_execution": ("source_id", "profile", "ex", "bundle", "method", "stype", "evidence", "rule", "n"),
    "statements_structural": ("source_id", "profile", "bundle", "method", "stype", "n"),
    "unknowns": (
        "source_id", "profile", "group", "occurrence", "record", "pointer", "excluded", "n", *_STATUS_COLUMNS,
        *(f"share_{s}" for s in _STATUS_COLUMNS if s != "undeclared"),
    ),
    "field_groups": (
        "source_id", "profile", "group", "n_executions", "excluded", "cells", "denominator", "coverage", "observed_share",
        *_STATUS_COLUMNS,
    ),
    "artefacts": (
        "source_id", "profile", "model", "artefact_id", "handling", "executions", "n_executions", "proportion", "hits", "first",
    ),
}  # fmt: skip
_FORMULA_START: Final = ("=", "+", "-", "@", "\t", "\r")


def _columns(table: str, rows: Sequence[Mapping[str, Any]]) -> list[str]:
    preferred = list(COLUMNS.get(table, ()))
    present = {k for row in rows for k in row}
    return [c for c in preferred if c in present or not rows] + sorted(present - set(preferred))


def _cell(value: Any, *, null: str) -> str:
    if value is None:
        return null
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list | tuple):
        return " ".join(_cell(v, null=null) for v in value)
    if isinstance(value, float):
        return repr(value)
    return str(value)


def _corpus_label(corpus: Mapping[str, Any]) -> str:
    c = corpus["corpus"]
    corpus_id = escape_untrusted_line(c["corpus_id"]) if c["corpus_id"] else "(no corpus_id)"
    parts = [f"corpus {corpus_id}", f"state {c['state']}", f"verification {c['verification']}"]
    if c.get("root_digest"):
        parts.append(f"root {escape_untrusted_line(c['root_digest'])}")
    if c.get("content_digest"):
        parts.append(f"content {escape_untrusted_line(c['content_digest'])}")
    pop = corpus["population"]
    parts.append(f"rows {pop['rows']}, selected {pop['selected']}, n_executions {pop['n_executions']}")
    if corpus["failures"]:
        parts.append("failures " + ", ".join(f"{k} x{v}" for k, v in corpus["failures"].items()))
    return "; ".join(parts)


def _text(document: Mapping[str, Any]) -> str:
    out: list[str] = [f"agentprov stats ({document['format']}; agentprov {document['agentprov_version']}; "
                      f"fn {document['fn_digest']}; prov spec {document['prov_spec']})"]  # fmt: skip
    for corpus in document["corpora"]:
        out.append("")
        out.append(_corpus_label(corpus))
        for name, rows in corpus["tables"].items():
            out.append("")
            out.append(f"== {name} ({len(rows)} rows)")
            columns = _columns(name, rows)
            grid = [columns] + [[_cell(row.get(c), null="-") for c in columns] for row in rows]
            widths = [max(len(r[i]) for r in grid) for i in range(len(columns))]
            for r in grid:
                out.append("  ".join(v.ljust(w) for v, w in zip(r, widths, strict=True)).rstrip())
    return "\n".join(out) + "\n"


def _md(value: str) -> str:
    return escape_markdown(value)


def _markdown(document: Mapping[str, Any]) -> str:
    out: list[str] = ["# agentprov stats", "",
                      f"`{document['format']}`; agentprov {document['agentprov_version']}; fn `{document['fn_digest']}`; "
                      f"prov spec `{document['prov_spec']}`"]  # fmt: skip
    for corpus in document["corpora"]:
        out += ["", f"## {_md(_corpus_label(corpus))}"]
        for name, rows in corpus["tables"].items():
            columns = _columns(name, rows)
            out += ["", f"### {name}", "", "| " + " | ".join(columns) + " |", "|" + "|".join("---" for _ in columns) + "|"]
            for row in rows:
                out.append("| " + " | ".join(_md(_cell(row.get(c), null="")) for c in columns) + " |")
    return "\n".join(out) + "\n"


def _csv_cell(value: Any) -> str:
    text = _cell(value, null="")
    if isinstance(value, str) and text.startswith(_FORMULA_START):
        return "'" + text
    return text


def _csv(document: Mapping[str, Any]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    first = True
    for corpus in document["corpora"]:
        corpus_id = escape_untrusted_line(corpus["corpus"]["corpus_id"] or "")
        for name, rows in corpus["tables"].items():
            if not first:
                buffer.write("\n")
            first = False
            columns = _columns(name, rows)
            writer.writerow(["corpus_id", "table", *columns])
            for row in rows:
                writer.writerow([_csv_cell(corpus_id), name, *(_csv_cell(row.get(c)) for c in columns)])
    return buffer.getvalue()


def render(document: Mapping[str, Any], fmt: str) -> bytes:
    """The report ``document`` in ``fmt`` (one of :data:`FORMATS`), as UTF-8 bytes ending in LF."""
    if fmt == "json":
        return jcs_bytes(dict(document)) + b"\n"
    if fmt == "text":
        return _text(document).encode("utf-8")
    if fmt == "markdown":
        return _markdown(document).encode("utf-8")
    if fmt == "csv":
        return _csv(document).encode("utf-8")
    raise ValueError("unknown stats output format")
