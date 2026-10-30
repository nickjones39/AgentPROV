"""``agentprov.stats``: minimal, generic statistics over a corpus (AD-10 as ruled; MN N.2.12; K.5.11; PQ Q.32).

Layer L7: a consumer outside the derivation DAG (HL H.8.1). It reads a sealed or working corpus read-only through
:class:`agentprov.corpus.reader.CorpusReader`, computes the four tables of N.2.12 (and, on request, the D.15.4 artefact
table) **per corpus, never pooled**, and writes nothing into any corpus. Core dependencies only (no pandas, numpy or
pyarrow; K.14).

* :func:`compute` (``compute(corpora, tables) -> StatsReport``, MN M.1.2) runs :func:`agentprov.stats.tables.compute_corpus`
  over each opened corpus;
* :class:`StatsReport` is the result; :meth:`StatsReport.to_json` is the ``agentprov-stats/0.1`` document, labelled with the
  function digest :func:`fn_digest` (H.8.1: a cache of stats output is keyed by ``(content_digest, fn_digest)``);
* :mod:`agentprov.stats.output` renders it as JSON (JCS), text, Markdown or CSV;
* :mod:`agentprov.stats.fieldgroups` holds the field groups of O.3.5 (``field_groups.toml``) and their evaluation;
* :mod:`agentprov.stats.exclusions` reads the rate exclusions adapter families declare as data (D.16.17 item 4).
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from functools import cache
from importlib import resources
from typing import Any, Final

from agentprov.corpus.index import IndexRow
from agentprov.stats.exclusions import Exclusion, declared_exclusions
from agentprov.stats.fieldgroups import FieldGroup, field_groups, field_groups_bytes
from agentprov.stats.source import StatsCorpus, normalise_select, open_corpus
from agentprov.stats.tables import DEFAULT_TABLES, OPTIONAL_TABLES, PROV_SPECS, TABLES, CorpusTables, compute_corpus
from agentprov.versions import __version__

__all__ = [
    "DEFAULT_TABLES",
    "OPTIONAL_TABLES",
    "PROV_SPECS",
    "STATS_FORMAT",
    "TABLES",
    "CorpusTables",
    "Exclusion",
    "FieldGroup",
    "StatsCorpus",
    "StatsReport",
    "compute",
    "field_groups",
    "fn_digest",
    "open_corpus",
]

STATS_FORMAT: Final = "agentprov-stats/0.1"


@cache
def fn_digest() -> str:
    """``sha256:`` over the source files of this package (``*.py`` and ``*.toml``, sorted by name, each framed by its
    name and length): the function identity of the stats output (HL H.8.1, H.8.3)."""
    digest = hashlib.sha256(b"agentprov-stats-fn/1\n")
    package = resources.files("agentprov.stats")
    for entry in sorted(package.iterdir(), key=lambda e: e.name):
        if entry.is_file() and entry.name.endswith((".py", ".toml")):
            data = entry.read_bytes()
            digest.update(f"{entry.name}\n{len(data)}\n".encode())
            digest.update(data)
    return "sha256:" + digest.hexdigest()


@dataclass(slots=True)
class StatsReport:
    """The tables of every corpus, in the order the corpora were given."""

    tables: tuple[str, ...]
    prov_spec: str
    select: dict[str, list[str]]
    corpora: list[CorpusTables] = field(default_factory=list)
    per_execution: bool = False
    exclusions: tuple[Exclusion, ...] = ()

    @property
    def notices(self) -> list[str]:
        return [n for c in self.corpora for n in c.notices]

    @property
    def failed(self) -> bool:
        return any(c.failures for c in self.corpora)

    def to_json(self) -> dict[str, Any]:
        return {
            "agentprov_version": __version__,
            "corpora": [c.to_json() for c in self.corpora],
            "exclusions": [e.to_json() for e in self.exclusions],
            "field_groups_sha256": "sha256:" + hashlib.sha256(field_groups_bytes()).hexdigest(),
            "fn_digest": fn_digest(),
            "format": STATS_FORMAT,
            "per_execution": self.per_execution,
            "prov_spec": self.prov_spec,
            "select": self.select,
            "tables": list(self.tables),
        }


def compute(
    corpora: Sequence[StatsCorpus],
    tables: Sequence[str] = DEFAULT_TABLES,
    *,
    prov_spec: str = "agentprov-prov/0.1",
    select: Mapping[str, str | Sequence[str]] | None = None,
    on_row: Callable[[IndexRow], None] | None = None,
    per_execution: bool = False,
) -> StatsReport:
    """Compute ``tables`` over each corpus separately (never pooled). A corpus whose checksums failed gets no tables:
    its entry carries its identity and the failure, so a caller can never mistake it for a verified result."""
    order = [t for t in (*TABLES, *OPTIONAL_TABLES) if t in set(tables)]
    if len(order) != len(set(tables)):
        raise ValueError("unknown stats table")
    chosen = normalise_select(select)
    exclusions = declared_exclusions()
    report = StatsReport(tuple(order), prov_spec, {k: sorted(v) for k, v in chosen.items()}, [], per_execution, exclusions)
    for corpus in corpora:
        if corpus.verification == "failed":
            report.corpora.append(CorpusTables(
                identity=corpus.identity(), population={"n_executions": 0, "rows": 0, "selected": 0}, tables={},
                failures=dict(corpus.checksum_findings),
                notices=[*corpus.notices, "the corpus fails the checksums check; no table was computed (run 'agentprov verify')"],
            ))  # fmt: skip
            continue
        report.corpora.append(compute_corpus(corpus, tables=order, prov_spec=prov_spec, select=chosen, on_row=on_row,
                                             per_execution=per_execution, exclusions=exclusions))
    return report

