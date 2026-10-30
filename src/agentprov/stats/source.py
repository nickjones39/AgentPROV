"""Opening a corpus for ``stats`` and the public API: N.1.5 resolution, verification, identity, selection.

:func:`open_corpus` resolves ``--corpus DIR`` with :class:`agentprov.corpus.reader.CorpusReader` (sealed, working or
``DIR.partial``; read-only, strict) and, by default, runs the ``checksums`` level of H.5.5 on a **sealed** corpus
(N.2.12: "a corpus is opened with ``verify="checksums"``"). ``verify="chain"`` and ``verify="rederive"`` run those levels
of ``agentprov verify`` (:func:`agentprov.corpus.verify.verify_corpus`; U4); ``rederive`` re-maps through the import
pipeline, injected here as :func:`import_hooks` (``adapters.runner``, L6, below this L7 module). A working tree has no
``checksums.sha256`` (H.5.3 writes it at sealing), so it is not verified: it is opened with ``verification =
"not_sealed"`` and every consumer prints a notice recommending ``verify``.

**Identity** (N.2.12 "labelled with ``corpus_id`` and its root digest (sealed) or content digest (working)"): the manifest's
``corpus_id``; for a sealed corpus its recorded ``content_digest`` and the root digest (the sha256 of
``checksums.sha256``, H.5.4); for a working tree the content digest computed from its working manifest (H.5.4), or
``None`` when the working manifest is absent or not corpus-layer JSON. No absolute path enters any output. A
``corpus_id`` outside the manifest grammar (:data:`agentprov.corpus.spec.CORPUS_ID_RE`, at most 64 characters) or a
recorded ``content_digest`` that is not ``sha256:<64 hex>`` is untrusted text, not a label: it is dropped (``None``) and
the corpus carries a notice (G.8.6; a self-consistent sealed corpus passes ``checksums`` with either).

**Selection** (``--select K=V``; M.6 ``iter_executions(select=…)``): equality on index-row members (:data:`SELECT_KEYS`), a
value list meaning "any of". ``snapshot`` matches any of a row's ``snapshot_ids`` and ``issue`` any of its issue codes;
``facet.<name>`` matches a string facet, or any element of a string-array facet, of a full row; ``cell.<member>`` matches a
known cell member (H.7.4: ``suite``, ``task_id``, ``attack_id``, ``attack_target_id``, ``defense_id``, ``model``,
``repeat`` and the rest; a string, an integer as its decimal spelling, or any element of a string array); an unknown
member (``$unk``) never matches. ``outcome.<claim>`` takes ``true``, ``false`` or ``none``: whether an ``outcome`` element
with that SEM claim (``attack_succeeded``, ``user_task_solved``, …) holds, does not hold, or no element with that claim
has a ``holds`` (not judged, which includes a benign cell's ``attack_succeeded``). Working rows carry no facets or cell
and never match these keys (``outcome.<claim>=none`` included: nothing is known about them).
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final, Literal

from agentprov.corpus.index import IndexRow
from agentprov.corpus.rowvalues import OUTCOME_STATES, cell_strings, outcome_states
from agentprov.corpus.integrity import IntegrityError, content_digest, root_digest, verify_checksums
from agentprov.corpus.reader import CorpusReader
from agentprov.corpus.spec import CORPUS_ID_RE
from agentprov.errors import AgentProvError

__all__ = [
    "SELECT_FORMS",
    "SELECT_KEYS",
    "import_hooks",
    "VERIFY_CHOICES",
    "SelectionError",
    "StatsCorpus",
    "VerifyLevelUnavailable",
    "normalise_select",
    "open_corpus",
    "outcome_states",
    "row_matches",
]

VERIFY_CHOICES: Final = ("none", "checksums", "chain", "rederive")
#: Index-row members ``--select`` may name, plus ``facet.<name>`` (full rows only).
SELECT_KEYS: Final = ("adapter", "completeness", "execution_observed", "mode", "profile", "snapshot", "source_id", "status", "unit")
FACET_PREFIX: Final = "facet."
CELL_PREFIX: Final = "cell."
OUTCOME_PREFIX: Final = "outcome."
OUTCOME_VALUES: Final = OUTCOME_STATES
#: the keys besides :data:`SELECT_KEYS`, as error messages and ``--help`` name them
SELECT_FORMS: Final = ("issue", "facet.<name>", "cell.<member>", "outcome.<claim>")
_PREFIXES: Final = (FACET_PREFIX, CELL_PREFIX, OUTCOME_PREFIX)
#: A recorded ``content_digest`` that may label output (H.5.4).
_DIGEST_RE: Final = re.compile(r"sha256:[0-9a-f]{64}")
_CORPUS_ID_MAX: Final = 64


class VerifyLevelUnavailable(AgentProvError):
    """A verification level that this build does not implement (exit 5). Every H.5.5 level is implemented since phase 11
    U4; the class stays part of the public API (M.6)."""

    code = "stats.verify.unavailable"
    exit_code = 5


class SelectionError(AgentProvError):
    """A ``select`` key outside :data:`SELECT_KEYS` / ``facet.<name>``, or a malformed value (usage, exit 2)."""

    code = "stats.select.invalid"
    exit_code = 2


@dataclass(slots=True)
class StatsCorpus:
    """An opened corpus (the ``Corpus`` of :mod:`agentprov.api`).

    ``verification`` is the level the sealed tree passed (``"checksums"``, ``"chain"``, ``"rederive"``), ``"failed"``
    (it did not; ``checksum_findings`` counts the findings by code), ``"unverified"`` (nothing failed but a check could not
    run, e.g. a catalogue version the package does not ship), ``"not_sealed"`` (a working tree: nothing to verify) or
    ``"skipped"`` (``verify="none"``). ``notices`` are about the corpus itself (a manifest identity that was dropped);
    :func:`agentprov.stats.compute` carries them into the corpus's tables."""

    reader: CorpusReader
    corpus_id: str | None
    state: str
    content_digest: str | None
    root_digest: str | None
    verification: str
    checksum_findings: dict[str, int] = field(default_factory=dict)
    notices: list[str] = field(default_factory=list)

    @property
    def root(self) -> Path:
        return self.reader.root

    @property
    def sealed(self) -> bool:
        return self.reader.sealed

    @property
    def verified(self) -> bool:
        return self.verification in ("checksums", "chain", "rederive")

    def identity(self) -> dict[str, Any]:
        """The label every stats table carries (no path; N.2.12)."""
        return {
            "content_digest": self.content_digest,
            "corpus_id": self.corpus_id,
            "root_digest": self.root_digest,
            "state": self.state,
            "verification": self.verification,
        }

    def iter_rows(self, select: Mapping[str, frozenset[str]] | None = None) -> Iterator[IndexRow]:
        """Stream the index rows (strict, in ``ex`` order), filtered by a normalised selection."""
        for row in self.reader.iter_index():
            if not select or row_matches(row, select):
                yield row


def _manifest_identity(reader: CorpusReader) -> tuple[str | None, str | None, list[str]]:
    """``(corpus_id, content_digest, notices)``; a value outside its grammar is dropped with a notice (never quoted)."""
    manifest = reader.manifest()
    if manifest is None:
        return None, None, []
    notices: list[str] = []
    corpus_id = manifest.get("corpus_id")
    if corpus_id is not None and not (isinstance(corpus_id, str) and len(corpus_id) <= _CORPUS_ID_MAX
                                      and CORPUS_ID_RE.fullmatch(corpus_id)):  # fmt: skip
        notices.append("the manifest's corpus_id is not a corpus id (lowercase alphanumeric words joined by '-', at most "
                       "64 characters); it is not shown")  # fmt: skip
        corpus_id = None
    if reader.sealed:
        recorded = manifest.get("content_digest")
        if recorded is not None and not (isinstance(recorded, str) and _DIGEST_RE.fullmatch(recorded)):
            notices.append("the manifest's recorded content_digest is not sha256:<64 hex>; it is not shown")
            recorded = None
        return corpus_id, recorded, notices
    try:
        return corpus_id, content_digest(manifest), notices
    except ValueError:
        return corpus_id, None, notices


def open_corpus(
    path: str | os.PathLike[str],
    *,
    verify: Literal["none", "checksums", "chain", "rederive"] = "checksums",
    raise_on_failure: bool = True,
) -> StatsCorpus:
    """Open the corpus at ``path`` (N.1.5) and verify it at ``verify`` (see the module docstring).

    A sealed corpus whose checksums fail raises :class:`agentprov.corpus.integrity.IntegrityError` unless
    ``raise_on_failure`` is false; then ``verification`` is ``"failed"``."""
    if verify not in VERIFY_CHOICES:
        raise ValueError("verify is none, checksums, chain or rederive")
    reader = CorpusReader.open(path)
    corpus_id, digest, notices = _manifest_identity(reader)
    findings: dict[str, int] = {}
    root_d: str | None = None
    if verify == "none":
        verification = "skipped"
    elif not reader.sealed:
        verification = "not_sealed"
    elif verify == "checksums":
        report = verify_checksums(reader.root)
        findings = report.codes()
        verification = "checksums" if report.ok else "failed"
        if report.ok:
            root_d = root_digest(reader.root)
        elif raise_on_failure:
            raise IntegrityError("the corpus fails the checksums check: " + ", ".join(f"{c} x{n}" for c, n in findings.items()),
                                 code="corpus.integrity.checksums")  # fmt: skip
    else:
        from agentprov.corpus.verify import verify_corpus

        level_report = verify_corpus(reader=reader, level=verify, import_hooks=import_hooks() if verify == "rederive" else None)
        findings = level_report.codes()
        verification = verify if level_report.ok else "unverified" if level_report.passed(release=False) else "failed"
        if verification != "failed":
            root_d = level_report.root_digest
        elif raise_on_failure:
            raise IntegrityError(f"the corpus fails the {verify} level: " + ", ".join(f"{c} x{n}" for c, n in findings.items()),
                                 code=f"corpus.integrity.{verify}")  # fmt: skip
    if root_d is None and reader.sealed and verification != "failed":
        try:
            root_d = root_digest(reader.root)
        except IntegrityError:
            root_d = None
    return StatsCorpus(reader, corpus_id, reader.state, digest, root_d, verification, findings, notices)


def import_hooks() -> Any:
    """The import pipeline a ``rederive`` re-map needs (:class:`agentprov.corpus.verify.ImportHooks`), from
    ``agentprov.adapters.runner.importer`` (L6) and ``agentprov.adapters.types`` (L4)."""
    from agentprov.adapters.runner.importer import ImportFilters, import_source
    from agentprov.adapters.types import CandidateArtefact
    from agentprov.corpus.verify import ImportHooks

    return ImportHooks(import_source=import_source, candidate_type=CandidateArtefact, filters_type=ImportFilters)


# ------------------------------------------------------------------------------------------------ selection
def normalise_select(select: Mapping[str, str | Sequence[str]] | None) -> dict[str, frozenset[str]]:
    """Check the keys and turn every value into a set of strings (``execution_observed`` takes ``true``/``false``)."""
    out: dict[str, frozenset[str]] = {}
    for key, value in (select or {}).items():
        if not isinstance(key, str) or not (key in SELECT_KEYS or key == "issue" or any(
                key.startswith(pre) and len(key) > len(pre) for pre in _PREFIXES)):
            raise SelectionError("a select key is one of " + ", ".join((*SELECT_KEYS, *SELECT_FORMS)))
        values = [value] if isinstance(value, str) else list(value)
        if not values or not all(isinstance(v, str) and v for v in values):
            raise SelectionError("a select value is a non-empty string or a list of them")
        if key == "execution_observed" and not set(values) <= {"true", "false"}:
            raise SelectionError("execution_observed is selected with true or false")
        if key.startswith(OUTCOME_PREFIX) and not set(values) <= set(OUTCOME_VALUES):
            raise SelectionError("outcome.<claim> is selected with true, false or none")
        out[key] = out.get(key, frozenset()) | frozenset(values)
    return dict(sorted(out.items()))


def _row_values(row: IndexRow, key: str) -> list[str]:
    if key == "snapshot":
        return list(row.snapshot_ids)
    if key == "execution_observed":
        return ["true" if row.execution_observed else "false"]
    if key == "issue":
        return list(row.issues)
    if key.startswith(CELL_PREFIX):
        members = row.facet_members
        return cell_strings(None if members is None else members.cell.get(key[len(CELL_PREFIX):]))
    if key.startswith(OUTCOME_PREFIX):
        members = row.facet_members
        if members is None:
            return []
        return outcome_states(members.facets.get("outcome"), key[len(OUTCOME_PREFIX):])
    if key.startswith(FACET_PREFIX):
        members = row.facet_members
        value = None if members is None else members.facets.get(key[len(FACET_PREFIX):])
        if isinstance(value, str):
            return [value]
        if isinstance(value, list):
            return [v for v in value if isinstance(v, str)]
        return []
    value = getattr(row, key)
    return [value] if isinstance(value, str) else []


def row_matches(row: IndexRow, select: Mapping[str, frozenset[str]]) -> bool:
    """Every key matches (AND); within a key, any of its values (OR)."""
    return all(any(v in wanted for v in _row_values(row, key)) for key, wanted in select.items())
