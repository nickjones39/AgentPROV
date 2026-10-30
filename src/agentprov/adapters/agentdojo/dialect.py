"""Reader of the AgentDojo TraceLogger dialect family (docs/architecture D.6.1-D.6.3; D.2.3; layer L4).

Dialect ``agentdojo.tracelogger``. A file is classified by its **key set** (D.6.2; key order carries no semantics):

=============================  ===============================================================  =====================
variant                        key set                                                          v0.1 status
=============================  ===============================================================  =====================
``v0.k11``                     K11 (AgentDojo <= 0.1.29, June-2024 logs)                        mapped (phase 6)
``v1.k14``                     K14 = K11 + benchmark_version, evaluation_timestamp, package ver  mapped (phase 10)
``v1.k14.incomplete``          K14 with outcome or duration keys missing                        mapped (phase 10)
``drift.k18.messages``         DRIFT keys + ``messages``                                        mapped (phase 10l)
``drift.k18.conversations``    DRIFT keys + ``conversations``                                   mapped (phase 10l)
``pre_v0``                     no ``pipeline_name`` (May-2024 dev logs, git history only)       recognised; planned
=============================  ===============================================================  =====================

The reader recognises every variant (``sniff`` matches, ``parse`` yields the located item); the mapper maps ``v0.k11``,
``v1.k14`` and ``v1.k14.incomplete`` (and, through ``drift_mapper``, the two DRIFT variants; D-270) where the profile
declares them and raises
:class:`~agentprov.errors.UnsupportedVariant` for the others, so each such file is sealed as a degenerate
AER with ``unsupported_variant`` (D.2.8 case 3), never dropped. A file that sniffs as the dialect but lacks a structural
key of its variant is a :class:`~agentprov.errors.MalformedArtefact` (``unparseable_artefact``).

Parsing goes through :func:`agentprov.ingest.loaders.strict_json_loads` only (R-PARSE; invariant 3): UTF-8 strict, no BOM,
no duplicate keys, no ``NaN``/``Infinity``, bounded depth and size. The parsed value keeps source member order and
int/float typing, which the mapper turns into ``ext.lex`` hints. Nothing here interprets message content.
"""

from __future__ import annotations

import fnmatch
from collections.abc import Iterator, Mapping
from typing import Any, Final

from agentprov.adapters.profiles import SourceProfile
from agentprov.adapters.protocols import SourceTree
from agentprov.adapters.types import ArtefactRef, CandidateArtefact, LocatedItem, Locator, SniffResult
from agentprov.errors import IngestError, MalformedArtefact
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.loaders import strict_json_loads

__all__ = [
    "DIALECT_ID",
    "K11",
    "K14",
    "KD18_BASE",
    "KNOWN_FORK_EXTRAS",
    "MAPPED_VARIANTS",
    "OUTCOME",
    "VARIANTS",
    "TraceLoggerReader",
    "classify",
]

DIALECT_ID: Final = "agentdojo.tracelogger"
K11: Final = frozenset({"suite_name", "pipeline_name", "user_task_id", "injection_task_id", "attack_type",
                        "injections", "messages", "error", "utility", "security", "duration"})
K14: Final = K11 | {"benchmark_version", "evaluation_timestamp", "agentdojo_package_version"}
KD18_BASE: Final = frozenset({"suite_name", "pipeline_name", "user_task_id", "injection_task_id", "attack_type",
                              "build_constraints", "injection_isolation", "dynamic_validation", "adaptive_attack",
                              "tool_permission", "initial_trajectory", "initial_checklist", "benchmark_version",
                              "utility", "security", "total_tokens", "duration"})
OUTCOME: Final = frozenset({"utility", "security", "duration"})
KNOWN_FORK_EXTRAS: Final = frozenset({"injection_attack_name", "error_type", "router_bucket"})
VARIANTS: Final = frozenset({"v0.k11", "v1.k14", "v1.k14.incomplete", "drift.k18.messages", "drift.k18.conversations",
                             "pre_v0"})
#: Variants the mapper maps where the profile declares them (phase 6: v0.k11; phase 10: v1.k14); the others take the
#: typed unsupported path.
MAPPED_VARIANTS: Final = frozenset({"v0.k11", "v1.k14", "v1.k14.incomplete"})
MALFORMED_REASON: Final = "missing_structural_keys"
FLAG_MALFORMED: Final = "malformed:missing_structural_keys"
_STRAYS: Final = (".DS_Store",)


def classify(obj: Any) -> SniffResult:
    """D.6.2 classification of a parsed object (total: never raises)."""
    if not isinstance(obj, dict) or not {"suite_name", "user_task_id"} <= obj.keys():
        return SniffResult(False, reasons=("not_tracelogger",))
    msgs = "messages" if "messages" in obj else "conversations" if "conversations" in obj else None
    if msgs is None:
        return SniffResult(False, reasons=("no_message_list",))
    if "pipeline_name" not in obj:  # May-2024 banking_rw dev logs (git history only)
        return SniffResult(True, DIALECT_ID, "pre_v0", reasons=("unsupported_variant",))
    expected: frozenset[str]
    if "build_constraints" in obj:
        expected = KD18_BASE | {msgs}
        variant = f"drift.k18.{msgs}"
    elif "agentdojo_package_version" in obj:  # upstream's own discriminator (benchmark.py load_task_results)
        variant, expected = "v1.k14", K14
    else:
        variant, expected = "v0.k11", K11
    missing = expected - obj.keys()
    if missing - OUTCOME:
        return SniffResult(True, DIALECT_ID, variant, reasons=("missing_structural_keys",))
    if missing and variant == "v1.k14":
        variant = "v1.k14.incomplete"
    flags = {f"missing:{k}" for k in sorted(missing)} | {f"extra:{k}" for k in sorted(obj.keys() - expected)}
    return SniffResult(True, DIALECT_ID, variant, frozenset(flags))


def _match(label: str, glob: str) -> bool:
    """``fnmatch`` over a POSIX label, with ``**/`` also matching zero directories."""
    if fnmatch.fnmatchcase(label, glob):
        return True
    return glob.startswith("**/") and fnmatch.fnmatchcase(label, glob[3:])


class TraceLoggerReader:
    """``Reader`` for ``agentdojo.tracelogger`` (D.2.3, D.6.3)."""

    dialect_id: Final = DIALECT_ID
    version: Final = "0.1.0"
    variants: Final = VARIANTS
    media_types: Final = frozenset({"application/json"})

    def iter_artefacts(self, tree: SourceTree, profile: SourceProfile) -> Iterator[CandidateArtefact]:
        """Candidates matching the profile's ``[import] include`` globs, minus strays and excludes, in label order."""
        imp = profile.data.get("import", {})
        include = tuple(imp.get("include", ())) or ("**/*.json",)
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
        return classify(value)

    def parse(self, data: bytes, artefact: ArtefactRef, *, limits: IngestLimits) -> Iterator[LocatedItem]:
        """One located item per file (locator ``{"p": ""}``). ``IngestError`` (limits) or ``MalformedArtefact``."""
        value = strict_json_loads(data, limits)
        result = classify(value)
        if not result.match or result.variant is None:
            raise MalformedArtefact(f"not a TraceLogger object ({', '.join(result.reasons)})")
        # A recognised object without its structural keys is still yielded, flagged: the mapper raises
        # MalformedArtefact on it, so the file is sealed as a degenerate AER (D.2.8 case 3) instead of being lost.
        flags = result.flags | {FLAG_MALFORMED} if MALFORMED_REASON in result.reasons else result.flags
        yield LocatedItem(
            artefact=artefact,
            locator=Locator(a=artefact.id, p=""),
            dialect=DIALECT_ID,
            variant=result.variant,
            flags=flags,
            value=value,
        )
