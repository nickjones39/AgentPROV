"""Reader of the AgentDojo-PROV ``transcript/v1`` dialect (docs/architecture D.7.2; D.2.3; layer L4).

Dialect ``adprov.transcript_v1``, variant ``v1``. A file belongs to the dialect when it parses strictly as one JSON
object with ``adprov_schema == "transcript/v1"``, an object ``meta`` and an array ``turns``. The schema id was never
bumped, so sub-variants are flags (D.7.2):

* ``capture:block``       ``meta.capture`` present;
* ``attempts:discarded``  ``discarded_attempts`` present;
* ``timing:stubbed``      ``meta.timing_stubbed`` is true;
* ``source:converted``    ``meta.source == "agentdojo_native_run_log"`` (the converted legacy tree);
* ``null_reply:encoded_empty``  a released transcript without any post-June field (``meta.capture``,
  ``meta.n_attempts``, ``meta.reasoning_alignment``, ``discarded_attempts``): written before 2026-10-04, when a null
  reply was stored as ``""`` (``adprov.release_null_as_empty@1``).

Parsing goes through :func:`agentprov.ingest.loaders.strict_json_loads` only (A-1, invariant 3): the reader produces the
value and its locator ``{"p": ""}`` and interprets nothing.
"""

from __future__ import annotations

import fnmatch
from collections.abc import Iterator, Mapping
from typing import Any, Final

from agentprov.adapters.profiles import SourceProfile
from agentprov.adapters.protocols import SourceTree
from agentprov.adapters.types import ArtefactRef, CandidateArtefact, LocatedItem, Locator, Origin, SniffResult
from agentprov.errors import IngestError, MalformedArtefact
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.loaders import strict_json_loads

__all__ = [
    "CONVERTED_SOURCE",
    "DIALECT_ID",
    "FLAG_CAPTURE",
    "FLAG_CONVERTED",
    "FLAG_DISCARDED",
    "FLAG_NULL_AS_EMPTY",
    "FLAG_STUBBED",
    "POST_JUNE_META",
    "TranscriptV1Reader",
    "flags_of",
]

DIALECT_ID: Final = "adprov.transcript_v1"
VARIANT: Final = "v1"
SCHEMA_ID: Final = "transcript/v1"
CONVERTED_SOURCE: Final = "agentdojo_native_run_log"
FLAG_CAPTURE: Final = "capture:block"
FLAG_DISCARDED: Final = "attempts:discarded"
FLAG_STUBBED: Final = "timing:stubbed"
FLAG_CONVERTED: Final = "source:converted"
FLAG_NULL_AS_EMPTY: Final = "null_reply:encoded_empty"
#: meta members that only the generator of 2026-10-04 onwards writes (D.7.2).
POST_JUNE_META: Final = ("capture", "n_attempts", "reasoning_alignment")
#: The frozen corpus the released and converted transcript trees belong to (J.4; v2.3 is on Zenodo since 2026-10-10, DECISIONS D-900, correcting D-4).
CORPUS_NAME: Final = "AgentDojo-PROV"
CORPUS_VERSION: Final = "2.3"
_STRAYS: Final = (".DS_Store",)


def flags_of(value: Mapping[str, Any]) -> frozenset[str]:
    """The D.7.2 sub-variant flags of a parsed transcript/v1 object."""
    meta = value.get("meta")
    meta = meta if isinstance(meta, Mapping) else {}
    flags: set[str] = set()
    if "capture" in meta:
        flags.add(FLAG_CAPTURE)
    if "discarded_attempts" in value:
        flags.add(FLAG_DISCARDED)
    if meta.get("timing_stubbed") is True:
        flags.add(FLAG_STUBBED)
    converted = meta.get("source") == CONVERTED_SOURCE
    if converted:
        flags.add(FLAG_CONVERTED)
    elif not any(k in meta for k in POST_JUNE_META) and "discarded_attempts" not in value:
        flags.add(FLAG_NULL_AS_EMPTY)
    return frozenset(flags)


def _shape(value: Any) -> str | None:
    """``None`` when ``value`` has the dialect's shape, else the reason code."""
    if not isinstance(value, dict):
        return "not_object"
    if value.get("adprov_schema") != SCHEMA_ID:
        return "schema_id"
    if not isinstance(value.get("meta"), dict):
        return "meta_not_object"
    if not isinstance(value.get("turns"), list):
        return "turns_not_array"
    return None


class TranscriptV1Reader:
    """``Reader`` for ``adprov.transcript_v1`` (D.2.3)."""

    dialect_id: Final = DIALECT_ID
    version: Final = "0.1.0"
    variants: Final = frozenset({VARIANT})
    media_types: Final = frozenset({"application/json"})

    @staticmethod
    def listing_origin(pin: Mapping[str, Any], label: str) -> Origin:
        """The origin of a file that ``import --verify-against-pin`` verified by the pin's J.1.4 tree-listing digest.

        The AgentDojo-PROV corpus trees are git-ignored at the pinned framework commit, so no git blob vouches for a file;
        the listing digest does, and the file is recorded as an object of the frozen corpus
        ``{corpus: AgentDojo-PROV, version: 2.3, producer_commit, path}`` (J.4 comparison table, H.2.3 ``corpus`` kind), with
        ``path`` relative to ``corpus/`` (the tree's last component and the label), as the migration gates record it.
        """
        leaf = str(pin.get("tree", "")).rstrip("/").rsplit("/", 1)[-1]
        return Origin.corpus(CORPUS_NAME, CORPUS_VERSION, f"{leaf}/{label}", producer_commit=str(pin.get("commit")))

    def iter_artefacts(self, tree: SourceTree, profile: SourceProfile) -> Iterator[CandidateArtefact]:
        """Candidates matching the profile's ``[import] include`` globs, minus strays and excludes, in label order."""
        imp = profile.data.get("import", {})
        include = tuple(imp.get("include", ())) or ("**/*.transcript.json",)
        exclude = tuple(e["glob"] for e in imp.get("exclude", ()) if isinstance(e, Mapping) and "glob" in e)
        for candidate in sorted(tree.walk(), key=lambda c: c.label):
            name = candidate.label.rsplit("/", 1)[-1]
            if name in _STRAYS or name.startswith("._"):
                continue
            if not any(_match(candidate.label, g) for g in include):
                continue
            if any(_match(candidate.label, g) for g in exclude):
                continue
            yield candidate

    def sniff(self, data: bytes, *, label: str, limits: IngestLimits) -> SniffResult:
        """Total classification: never raises for foreign input."""
        try:
            value = strict_json_loads(data, limits)
        except IngestError as exc:
            return SniffResult(False, reasons=(exc.code,))
        reason = _shape(value)
        if reason is not None:
            return SniffResult(False, reasons=(f"adprov.sniff.{reason}",))
        return SniffResult(True, DIALECT_ID, VARIANT, flags_of(value), ("adprov.sniff.schema_id",))

    def parse(self, data: bytes, artefact: ArtefactRef, *, limits: IngestLimits) -> Iterator[LocatedItem]:
        """One located item per file (locator ``{"p": ""}``). ``IngestError`` (limits) or ``MalformedArtefact``."""
        value = strict_json_loads(data, limits)
        reason = _shape(value)
        if reason is not None:
            raise MalformedArtefact(f"not a transcript/v1 object ({reason})")
        yield LocatedItem(
            artefact=artefact,
            locator=Locator(a=artefact.id, p=""),
            dialect=DIALECT_ID,
            variant=VARIANT,
            flags=flags_of(value),
            value=value,
        )


def _match(label: str, glob: str) -> bool:
    """``fnmatch`` over a POSIX label, with ``**/`` also matching zero directories."""
    if fnmatch.fnmatchcase(label, glob):
        return True
    return glob.startswith("**/") and fnmatch.fnmatchcase(label, glob[3:])
