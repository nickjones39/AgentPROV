"""The one claims/lint library (docs/architecture I.5.6, I.4; HL H.9(3)-(4); MN N.2.5(7); DoD Q.11b; DECISIONS D-36).

It serves the README, ``docs/``, the corpus cards and generated datasheets, the labels of ``agentprov stats`` and the
paper's macros. A separate datasheet claims registry or card linter does not exist (AD-10 row 9). It holds:

1. **The must-not-claim items of I.4** as lint rules keyed by the closed claim-tag vocabulary (:data:`CLAIM_TAGS`,
   :data:`MUST_NOT_CLAIM`): :func:`forbidden_tags` and :func:`check_claim` (I.5.6 rules 1 and 3).
2. **The registry-generated coverage phrase** (AD-08 as ruled; NC-ALL-08): :func:`coverage_phrase`, ``None`` until DoD
   Q.11a has passed and a counted part has a dialect outside the AgentDojo lineage.
3. **Datasheet claims** (H.9(4)): predicates over manifest values (:data:`CLAIMS`), evaluated by
   :func:`evaluate_claims`; a failing claim fails the build, and the results are recorded in
   ``corpus.json.datasheet.claims``.
4. **Text lint** (:func:`lint_text`): the bare agnosticism term outside a design-goal block (and counts or source names
   inside one), an unqualified "reproducible" (the canonical phrase is "derivation-reproducible", AR-12), the scope words
   "lossless" and "faithful" outside an explicitly scoped claim, coverage phrases that are not the generated one, and a
   "Live Capture" title without an approved live corpus (NC-LIVE-02).
5. **Card lint** (:func:`lint_card`, ``agentprov validate --card``; H.9(3), H.9(5), N.2.5(7)): the front matter declares
   ``mode: import|live``; no digit outside a placeholder (``{{v:…}}``, ``{{t:…}}``, ``{{claim:…}}``; ``{{f:…}}`` in a
   decided statement) except the allow-list
   of version ids, ISO dates, DOIs, arXiv ids, commit SHAs, section numbers and identifiers in code spans; every
   ``{{claim:id}}`` is registered; and :func:`lint_text`.
6. **Datasheet lint** (:func:`lint_datasheet`): :func:`lint_text` plus the mandatory "Untrusted content" section (G.8.5).

:data:`CHECKER` bundles 3, 5 and 6 for injection into :mod:`agentprov.corpus.datasheet` (L5 never imports this L6
module, M.5.2(1)). Every message is generated text; text taken from a checked file is passed through
:func:`agentprov.ingest.quote.escape_untrusted` before it enters a violation's ``detail``.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Literal

from agentprov.adapters.registry import REGISTRY, SourceRegistration
from agentprov.ingest.quote import escape_untrusted

__all__ = [
    "CHECKER",
    "CLAIMS",
    "CLAIM_TAGS",
    "MUST_NOT_CLAIM",
    "ClaimTag",
    "ClaimViolation",
    "DatasheetClaim",
    "MustNotClaim",
    "check_claim",
    "coverage_phrase",
    "evaluate_claims",
    "forbidden_tags",
    "lint_card",
    "lint_datasheet",
    "lint_text",
]

ClaimTag = Literal[
    "per_step_time", "timezone", "lossless", "llm_params", "reasoning", "env_state", "raw_tool_output",
    "payload_observed", "outcome_observed", "asr", "model_identity_observed", "code_identity", "checker_version",
    "agent_execution", "distinct_corpus", "coverage_claim", "retry_absence", "provider_route",
    "controlled_comparison", "paper_reproduction", "leaderboard_equivalence", "release_equivalence",
    "selection_free", "replayable", "stock_behaviour", "real_model_live", "blind_input",
]  # fmt: skip
#: The closed claim-tag vocabulary of I.5.6 (no ``benchmark_agnostic`` tag: R-27, AD-08).
CLAIM_TAGS: Final[tuple[str, ...]] = ClaimTag.__args__  # type: ignore[attr-defined]


@dataclass(frozen=True)
class ClaimViolation:
    """One violation (I.5.6). ``detail`` is generated text; any quoted input is escaped."""

    source_id: str | None
    tag: str | None
    nc_id: str
    location: str
    detail: str


@dataclass(frozen=True)
class MustNotClaim:
    """One I.4 item with claim tags: ``source_id`` ``None`` applies to every imported source (NC-ALL) or every corpus."""

    nc_id: str
    source_id: str | None
    tags: tuple[str, ...]


#: The I.4 items enforced by claim tags ([T]); the items enforced only by a validator, mapper, SEM rule or policy carry
#: no tag here (their enforcement lives in those layers, I.4 legend).
MUST_NOT_CLAIM: Final[tuple[MustNotClaim, ...]] = (
    MustNotClaim("NC-ALL-01", None, ("per_step_time", "timezone")),
    MustNotClaim("NC-ALL-03", None, ("lossless",)),
    MustNotClaim("NC-ALL-04", None, ("model_identity_observed",)),
    MustNotClaim("NC-ALL-05", None, ("outcome_observed",)),
    MustNotClaim("NC-ALL-08", None, ("coverage_claim", "agent_execution")),
    MustNotClaim("NC-ALL-10", None, ("code_identity",)),
    MustNotClaim("NC-ALL-11", None, ("retry_absence",)),
    MustNotClaim("NC-ALL-12", None, ("llm_params", "reasoning")),
    MustNotClaim("NC-ALL-13", None, ("agent_execution",)),
    MustNotClaim("NC-AD-01", "agentdojo", ("checker_version",)),
    MustNotClaim("NC-AD-03", "agentdojo", ("outcome_observed", "agent_execution")),
    MustNotClaim("NC-AD-06", "agentdojo", ("leaderboard_equivalence",)),
    MustNotClaim("NC-ADPROV-01", "adprov-v1", ("reasoning", "env_state", "lossless")),
    MustNotClaim("NC-ADPROV-02", "adprov-v1", ("llm_params",)),
    MustNotClaim("NC-ADPROV-03", "adprov-v1", ("stock_behaviour",)),
    MustNotClaim("NC-ADPROV-04", "adprov-v1", ("release_equivalence", "selection_free")),
    MustNotClaim("NC-CONV-01", "adprov-v1", ("distinct_corpus",)),
    MustNotClaim("NC-NIST-01", "agentdojo-inspect", ("distinct_corpus",)),
    MustNotClaim("NC-DYN-02", "agentdyn", ("payload_observed",)),
    MustNotClaim("NC-DYN-04", "agentdyn", ("provider_route",)),
    MustNotClaim("NC-DYN-05", "agentdyn", ("controlled_comparison", "checker_version")),
    MustNotClaim("NC-DYN-06", "agentdyn", ("paper_reproduction",)),
    MustNotClaim("NC-DYN-07", "agentdyn", ("code_identity", "replayable")),
    MustNotClaim("NC-AUTO-01", "autodojo", ("distinct_corpus", "paper_reproduction")),
    MustNotClaim("NC-AUTO-03", "autodojo", ("agent_execution",)),
    MustNotClaim("NC-AUTO-05", "autodojo", ("paper_reproduction",)),
    MustNotClaim("NC-ROPE-02", "rope", ("code_identity",)),
    MustNotClaim("NC-DRIFT-01", "drift", ("raw_tool_output",)),
    MustNotClaim("NC-DRIFT-02", "drift", ("llm_params",)),
    MustNotClaim("NC-DRIFT-03", "drift", ("payload_observed",)),
    MustNotClaim("NC-DRIFT-04", "drift", ("paper_reproduction",)),
    MustNotClaim("NC-MID-01", "midojo", ("agent_execution",)),
    MustNotClaim("NC-SUR-05", "agent-security-tools-survey", ("agent_execution",)),
    MustNotClaim("NC-MAN-01", "mandate-agentdojo-eval", ("paper_reproduction",)),
    MustNotClaim("NC-MAN-03", "mandate-agentdojo-eval", ("llm_params", "timezone")),
    MustNotClaim("NC-STAC-01", "stac", ("agent_execution", "asr")),
    MustNotClaim("NC-CIA-01", "ciaware-bench", ("raw_tool_output", "agent_execution")),
    MustNotClaim("NC-CIA-04", "ciaware-bench", ("env_state", "asr")),
    MustNotClaim("NC-LIVE-01", None, ("stock_behaviour",)),
    MustNotClaim("NC-LIVE-02", None, ("real_model_live",)),
    MustNotClaim("NC-PROV-01", None, ("blind_input",)),
)
#: Tags that the NC-ALL / NC-LIVE / NC-PROV items forbid only conditionally; they are decided by :func:`check_claim`
#: from its arguments rather than forbidden outright for every source.
_CONDITIONAL: Final = frozenset({"NC-ALL-08", "NC-ALL-13", "NC-LIVE-01", "NC-LIVE-02", "NC-ALL-04", "NC-ALL-05"})


def forbidden_tags(source_id: str, part_id: str | None = None) -> frozenset[str]:
    """The claim tags forbidden for ``source_id`` outright: its per-source items and the unconditional NC-ALL/NC-PROV
    items. ``part_id`` is accepted for the I.5.6 signature; v0.1 items are per source."""
    del part_id
    tags: set[str] = set()
    for item in MUST_NOT_CLAIM:
        if item.nc_id in _CONDITIONAL:
            continue
        if item.source_id is None or item.source_id == source_id:
            tags.update(item.tags)
    return frozenset(tags)


def check_claim(
    source_ids: Iterable[str], tags: Iterable[str], *, derivation: Mapping[str, str] | None = None,
    location: str = "", agent_executions_only: bool = False, phrase: str | None = None,
) -> list[ClaimViolation]:
    """Violations of a claim with ``tags`` about ``source_ids`` (I.5.6 rules 1-3).

    * an unknown tag is a violation (closed vocabulary);
    * ``asr`` needs ``derivation`` naming ``labels`` (``raw`` or ``recomputed:<rule>``) and ``averaging``
      (``micro``/``macro``) (NC-AUTO-04);
    * ``coverage_claim`` is allowed only with ``phrase`` equal to :func:`coverage_phrase` (which must not be ``None``);
    * ``agent_execution`` counts are allowed only over ``unit == agent_execution ∧ execution_observed``
      (``agent_executions_only``; NC-ALL-13), and never for a source whose items forbid it outright;
    * every other tag is checked against :func:`forbidden_tags`.
    """
    out: list[ClaimViolation] = []
    tag_list = list(tags)
    sources: list[str | None] = [*source_ids] or [None]
    for tag in tag_list:
        if tag not in CLAIM_TAGS:
            out.append(ClaimViolation(None, None, "I.5.6", location, f"unknown claim tag {escape_untrusted(tag, max_chars=60)}"))
    if "asr" in tag_list:
        d = derivation or {}
        labels, averaging = d.get("labels", ""), d.get("averaging")
        if not (labels == "raw" or str(labels).startswith("recomputed:")) or averaging not in ("micro", "macro"):
            out.append(ClaimViolation(None, "asr", "NC-AUTO-04", location, "an ASR needs its label derivation and averaging"))
    if "coverage_claim" in tag_list:
        expected = coverage_phrase()
        if expected is None or phrase != expected:
            out.append(ClaimViolation(None, "coverage_claim", "NC-ALL-08", location,
                                      "an empirical coverage claim must be the registry-generated phrase, after DoD Q.11a"))
    if "agent_execution" in tag_list and not agent_executions_only:
        out.append(ClaimViolation(None, "agent_execution", "NC-ALL-13", location,
                                  "execution counts are over unit == agent_execution and execution_observed only"))
    for source in sources:
        if source is None:
            continue
        banned = forbidden_tags(source)
        for tag in tag_list:
            if tag in banned and tag not in ("asr", "coverage_claim"):
                item = next(i for i in MUST_NOT_CLAIM if tag in i.tags and i.nc_id not in _CONDITIONAL
                            and (i.source_id is None or i.source_id == source))
                out.append(ClaimViolation(source, tag, item.nc_id, location, f"claim tag {tag} is forbidden for this source"))
    return out


# ------------------------------------------------------------------------------------------------ coverage phrase
_AGENTDOJO_LINEAGE: Final = frozenset({"agentdojo.tracelogger", "adprov.transcript_v1", "agentprov.capture"})


def _q11a_passed(registry: Sequence[SourceRegistration]) -> bool:
    """DoD Q.11a: the survey AgentHarm logs import, derive and validate end to end; the registry records it as the gated
    ``supported`` status of the part whose dialect is ``inspect.eval`` (D.3.2 rule 4)."""
    return any(
        c.import_status == "supported" and "inspect.eval" in c.dialects for r in registry for c in r.capabilities
    )


def coverage_phrase(registry: Sequence[SourceRegistration] = REGISTRY) -> str | None:
    """"adapter-based core; demonstrated on N sources in K formats (single-agent, tool-calling traces)" (I.5.6 rule 2).

    N counts the registered sources with a ``source`` part whose gated import status is ``supported`` or ``partial``
    (scenario populations excluded: no such part has an import status in v0.1), not counting parts served through
    another source's import (``via``; their executions count under that source, NC-AUTO-01; D-481); K counts the
    distinct dialects of those parts. ``None`` before DoD Q.11a or when every counted dialect is of the AgentDojo lineage."""
    if not _q11a_passed(registry):
        return None
    counted = [
        (r.source_id, c) for r in registry for c in r.capabilities
        if c.role == "source" and c.import_status in ("supported", "partial") and c.via is None
    ]  # fmt: skip
    dialects = {d for _, c in counted for d in c.dialects}
    if not dialects - _AGENTDOJO_LINEAGE:
        return None
    n = len({source for source, _ in counted})
    return f"adapter-based core; demonstrated on {n} sources in {len(dialects)} formats (single-agent, tool-calling traces)"


# ------------------------------------------------------------------------------------------------ datasheet claims
@dataclass(frozen=True)
class DatasheetClaim:
    """A registered datasheet claim: a predicate over the manifest (H.9(4)); ``tags`` are checked by :func:`check_claim`."""

    id: str
    text: str
    predicate: Callable[[Mapping[str, Any]], bool]
    tags: tuple[str, ...] = ()


def _counts(m: Mapping[str, Any]) -> Mapping[str, Any]:
    return m["counts"]


#: The registered claims, by id. A card cites one as ``{{claim:<id>}}``; the rendered sentence is its ``text``.
CLAIMS: Final[Mapping[str, DatasheetClaim]] = {c.id: c for c in (
    DatasheetClaim("no_execution_observed_nonzero",
                   "Some records hold an outcome without an observed execution; they are counted separately from agent "
                   "executions.",
                   lambda m: _counts(m)["issues_by_code"].get("map.no_execution_observed", 0) > 0),
    DatasheetClaim("every_execution_observed", "Every record of this corpus holds an observed execution.",
                   lambda m: _counts(m)["execution_observed"]["false"] == 0),
    DatasheetClaim("all_unverifiable",
                   "No execution of this corpus has a verified-complete record: completeness is unverifiable for every "
                   "execution.",
                   lambda m: _counts(m)["by_completeness"]["unverifiable"] == _counts(m)["executions"]),
    DatasheetClaim("no_failed_rows", "No execution row failed a stage.",
                   lambda m: _counts(m)["by_status"]["failed"] == 0),
    DatasheetClaim("no_outcome_only_records", "The corpus holds no outcome-only or scenario record.",
                   lambda m: _counts(m)["by_unit"]["outcome_only"] == 0 and _counts(m)["by_unit"]["scenario"] == 0),
    DatasheetClaim("raw_included", "The raw evidence of every snapshot is included in the corpus.",
                   lambda m: all(s["raw_policy"] == "include" for src in m["sources"] for s in src["snapshots"])),
    DatasheetClaim("validation_strict", "Validation ran in strict mode, with no gating check skipped.",
                   lambda m: m["validation"]["mode"] == "strict"
                   and all(c["skipped"] == 0 for c in m["validation"]["checks"])),
    DatasheetClaim("restricted_use", "The corpus carries a use restriction, listed under Distribution and licensing.",
                   lambda m: bool(m["licences"]["restrictions"])),
    DatasheetClaim("no_restrictions", "The corpus carries no use restriction beyond its licence.",
                   lambda m: not m["licences"]["restrictions"]),
    DatasheetClaim("compat_outputs_flagged",
                   "Regression-oracle PROV graphs are present and flagged apv:RegressionOracle; they are not the "
                   "recommended semantics.",
                   lambda m: bool(m["oracle_specs"])),
    DatasheetClaim("no_compat_outputs", "The corpus holds no regression-oracle graph.", lambda m: not m["oracle_specs"]),
    DatasheetClaim("has_generic_records", "Some events are represented by generic activity or artefact records.",
                   lambda m: any(_counts(m)["generic_types"][k] for k in ("activity", "artefact"))),
    DatasheetClaim("no_generic_records", "No event needed a generic activity or artefact record.",
                   lambda m: not any(_counts(m)["generic_types"][k] for k in ("activity", "artefact"))),
    DatasheetClaim("has_selection_exclusions",
                   "Some files matched by the source's selection were excluded by declared rules; each is in the "
                   "register with its code.",
                   lambda m: bool(_counts(m)["selection_excluded_by_code"])),
    DatasheetClaim("has_archive_members", "Some executions were read from archive members, recorded in raw/members.jsonl.",
                   lambda m: _counts(m)["members"] is not None and _counts(m)["members"]["selected"] > 0),
)}  # fmt: skip


def evaluate_claims(ids: Iterable[str], manifest: Mapping[str, Any], *, source_ids: Iterable[str] = ()) -> tuple[
        list[dict[str, Any]], list[ClaimViolation]]:
    """``(results, violations)``: ``results`` is ``[{id, holds}]`` (sorted, unique) for ``corpus.json.datasheet.claims``;
    an unknown id, a claim that does not hold, and a claim whose tags are forbidden for the source are violations (a
    failing claim fails the build, H.9(4))."""
    results: list[dict[str, Any]] = []
    violations: list[ClaimViolation] = []
    sources = list(source_ids)
    for claim_id in sorted(set(ids)):
        claim = CLAIMS.get(claim_id)
        if claim is None:
            violations.append(ClaimViolation(None, None, "H.9", "card", f"unregistered claim {escape_untrusted(claim_id, max_chars=60)}"))
            continue
        try:
            holds = bool(claim.predicate(manifest))
        except (KeyError, TypeError):
            holds = False
        results.append({"holds": holds, "id": claim_id})
        if not holds:
            violations.append(ClaimViolation(None, None, "H.9", "card", f"claim {claim_id} does not hold for this corpus"))
        violations.extend(check_claim(sources, claim.tags, location=f"claim {claim_id}", agent_executions_only=True))
    return results, violations


# ------------------------------------------------------------------------------------------------ text lint
_DESIGN_OPEN: Final = re.compile(r"<!--\s*agentprov:design-goal\s*-->|^%\s*agentprov:design-goal\s*$", re.MULTILINE)
_DESIGN_CLOSE: Final = re.compile(r"<!--\s*agentprov:end-design-goal\s*-->|^%\s*agentprov:end-design-goal\s*$", re.MULTILINE)
_AGNOSTIC: Final = re.compile(r"\b(?:benchmark|framework)[- ]agnostic(?:ism)?\b", re.IGNORECASE)
_REPRODUCIBLE: Final = re.compile(r"(?<![-\w])reproducib(?:le|ility)\b", re.IGNORECASE)
_QUALIFIED_REPRO: Final = re.compile(r"derivation[- ]reproducib(?:le|ility)|execution reproducibility|reproducible\s+(?:by|from)\s+"
                                     r"(?:the\s+)?derivation", re.IGNORECASE)
_SCOPE_WORDS: Final = re.compile(r"\b(?:lossless|faithful(?:ly)?)\b", re.IGNORECASE)
_COVERAGE: Final = re.compile(r"demonstrated on \S+ sources", re.IGNORECASE)
_LIVE_TITLE: Final = re.compile(r"^#+\s.*\blive capture\b", re.IGNORECASE | re.MULTILINE)
_PLACEHOLDER: Final = re.compile(r"\{\{(v|t|claim|f):([^{}]*)\}\}")
#: The fixed start of the datasheet line that quotes a source's required attribution verbatim (D-910;
#: ``corpus/datasheet.py`` holds the same string): only the AR-12 and NC-ALL-03 word rules skip such a line, and only in a
#: generated datasheet; a card or statement holding the phrase is refused.
ATTRIBUTION_PREFIX: Final = "- Required attribution (verbatim): "
_ATTRIBUTION_PHRASE: Final = "Required attribution (verbatim)"
_CODE_SPAN: Final = re.compile(r"`[^`\n]*`")
_FENCE: Final = re.compile(r"^```.*?^```[ \t]*$", re.MULTILINE | re.DOTALL)


def _line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _design_blocks(text: str) -> list[tuple[int, int]]:
    blocks: list[tuple[int, int]] = []
    position = 0
    while (opened := _DESIGN_OPEN.search(text, position)) is not None:
        closed = _DESIGN_CLOSE.search(text, opened.end())
        end = len(text) if closed is None else closed.start()
        blocks.append((opened.end(), end))
        position = end if closed is None else closed.end()
    return blocks


def _verbatim_spans(text: str) -> list[tuple[int, int]]:
    """The lines that start with :data:`ATTRIBUTION_PREFIX` (from the prefix's end to the line's end)."""
    spans: list[tuple[int, int]] = []
    at = 0
    while at <= len(text):
        end = text.find("\n", at)
        end = len(text) if end < 0 else end
        if text.startswith(ATTRIBUTION_PREFIX, at):
            spans.append((at + len(ATTRIBUTION_PREFIX), end))
        at = end + 1
    return spans


def lint_text(path: Path | str, text: str, *, source_names: Iterable[str] = (), verbatim: bool = False) -> list[ClaimViolation]:
    """The text rules of I.5.6 rule 2 and H.9(4) over one document (see the module docstring). With ``verbatim`` (a
    generated datasheet only), the AR-12 and NC-ALL-03 word rules skip the third-party text on a line that starts with
    :data:`ATTRIBUTION_PREFIX` (D-910)."""
    where = str(path)
    out: list[ClaimViolation] = []
    blocks = _design_blocks(text)
    quoted = _verbatim_spans(text) if verbatim else []

    def third_party(offset: int) -> bool:
        return any(a <= offset < b for a, b in quoted)

    def inside(offset: int) -> bool:
        return any(a <= offset < b for a, b in blocks)

    for match in _AGNOSTIC.finditer(text):
        if not inside(match.start()):
            out.append(ClaimViolation(None, "coverage_claim", "NC-ALL-08", f"{where}:{_line_of(text, match.start())}",
                                      "the bare agnosticism term outside a design-goal block"))
    names = [n for n in source_names if n]
    for a, b in blocks:
        block = text[a:b]
        if re.search(r"\d", block) or any(n.lower() in block.lower() for n in names):
            out.append(ClaimViolation(None, "coverage_claim", "NC-ALL-08", f"{where}:{_line_of(text, a)}",
                                      "a design-goal block holds a count or a source name"))
    qualified = {m.start() for q in _QUALIFIED_REPRO.finditer(text) for m in _REPRODUCIBLE.finditer(text, q.start(), q.end())}
    for match in _REPRODUCIBLE.finditer(text):
        if match.start() not in qualified and not third_party(match.start()):
            out.append(ClaimViolation(None, None, "AR-12", f"{where}:{_line_of(text, match.start())}",
                                      "use 'derivation-reproducible'; execution reproducibility is never claimed (L.2.1)"))
    claims = [(text.rfind("\n", 0, m.start()) + 1, len(text) if text.find("\n", m.end()) < 0 else text.find("\n", m.end()))
              for m in _PLACEHOLDER.finditer(text) if m.group(1) == "claim"]  # the line of a claim states its scope
    for match in _SCOPE_WORDS.finditer(text):
        if not any(a <= match.start() < b for a, b in claims) and not third_party(match.start()):
            out.append(ClaimViolation(None, "lossless", "NC-ALL-03", f"{where}:{_line_of(text, match.start())}",
                                      "a scope word outside a claim with an explicit scope (H.9(4))"))
    expected = coverage_phrase()
    for match in _COVERAGE.finditer(text):
        line_end = text.find("\n", match.start())
        line = text[text.rfind("\n", 0, match.start()) + 1 : None if line_end < 0 else line_end]
        if expected is None or expected not in line:
            out.append(ClaimViolation(None, "coverage_claim", "NC-ALL-08", f"{where}:{_line_of(text, match.start())}",
                                      "a coverage phrase that is not the registry-generated one"))
    for match in _LIVE_TITLE.finditer(text):
        out.append(ClaimViolation(None, "real_model_live", "NC-LIVE-02", f"{where}:{_line_of(text, match.start())}",
                                  "'Live Capture' in a title needs an approved, sealed, non-test_only live corpus"))
    return out


# ------------------------------------------------------------------------------------------------ card lint
_FRONT: Final = re.compile(r"\A---\n(?P<body>.*?)\n---\n", re.DOTALL)
#: Tokens with a digit that a card may hold outside placeholders (H.9(3) allow-list).
_ALLOWED_TOKENS: Final = tuple(re.compile(p) for p in (
    r"[a-z][a-z0-9-]*/[0-9]+\.[0-9]+",  # version ids: aer/0.1, agentprov-prov/0.1, capture/0.1
    r"v?[0-9]+\.[0-9]+\.[0-9]+",  # SemVer and software versions
    r"[0-9]{4}-[0-9]{2}(-[0-9]{2})?",  # ISO dates (and year-month snapshot ids such as 2024-06)
    r"10\.[0-9]{4,9}/\S+",  # DOIs
    r"arXiv:[0-9]{4}\.[0-9]{4,5}(v[0-9]+)?",  # arXiv ids
    r"[0-9a-f]{7,40}",  # commit SHAs (abbreviated or full); must contain a letter, checked below
    r"§?[A-Z]{1,2}(\.[0-9]+)+(\([0-9a-z]+\))?",  # section numbers: H.9, C.16.1, H.1.5(4)
    r"§[0-9]+(\.[0-9]+)*",  # report section numbers: §8.3
    r"(AD|D|R|RF|U|AR|CAP|REP|NC-[A-Z]+|OM|SEC|HL-T|K|Q)-?[0-9]+[a-z]?(\([0-9a-z]+\))?",  # decision, review and item ids
    r"[a-z][a-z0-9_.-]*@[0-9]+",  # rule and profile references
    r"[A-Z][0-9]{1,2}",  # row ids of the analyses: N2, C4
    r"W3C|sha(1|256)",  # names, not quantities
))  # fmt: skip
_TOKEN: Final = re.compile(r"[^\s,;\[\]{}\"'*|<>]+")


def _strip(text: str) -> str:
    """The card text without fenced blocks, inline code spans that contain a letter, and placeholders (each replaced by
    spaces so that offsets and line numbers stay valid)."""
    def blank(match: re.Match[str]) -> str:
        return re.sub(r"[^\n]", " ", match.group(0))

    text = _FENCE.sub(blank, text)
    text = _CODE_SPAN.sub(lambda m: blank(m) if re.search(r"[A-Za-z]", m.group(0)) else m.group(0), text)
    return _PLACEHOLDER.sub(blank, text)


def _token_allowed(token: str) -> bool:
    core = token.strip("`").rstrip(".:")
    while core.startswith("(") and core.count("(") > core.count(")"):
        core = core[1:]
    while core.endswith(")") and core.count(")") > core.count("("):
        core = core[:-1]
    core = core.strip("`").rstrip(".:")
    for pattern in _ALLOWED_TOKENS:
        if pattern.fullmatch(core):
            return not (pattern.pattern.startswith("[0-9a-f]{7") and not re.search(r"[a-f]", core))
    return False


def card_front_matter(text: str) -> dict[str, str] | None:
    """The ``key: value`` lines of the card's front matter (between ``---`` lines at the top), or ``None``."""
    match = _FRONT.match(text)
    if match is None:
        return None
    out: dict[str, str] = {}
    for line in match.group("body").splitlines():
        key, sep, value = line.partition(":")
        if sep and key.strip():
            out[key.strip()] = value.strip()
    return out


def lint_card(text: str, *, location: str = "CARD.md", source_ids: Iterable[str] = ()) -> list[ClaimViolation]:
    """``agentprov validate --card`` (N.2.5(7); H.9(3), H.9(5)); see the module docstring. Empty list: the card passes."""
    out: list[ClaimViolation] = []
    front = card_front_matter(text)
    if front is None or front.get("mode") not in ("import", "live"):
        out.append(ClaimViolation(None, None, "H.9(5)", f"{location}:1", "the front matter declares mode: import or live"))
    for match in _PLACEHOLDER.finditer(text):
        kind, body = match.group(1), match.group(2)
        here = f"{location}:{_line_of(text, match.start())}"
        if kind == "claim" and body not in CLAIMS:
            out.append(ClaimViolation(None, None, "H.9(4)", here, f"unregistered claim {escape_untrusted(body, max_chars=60)}"))
        if kind == "v" and not body.startswith("/"):
            out.append(ClaimViolation(None, None, "H.9(3)", here, "a {{v:…}} placeholder holds a JSON Pointer into corpus.json"))
    stripped = _strip(text)
    front_match = _FRONT.match(stripped)
    body_start = front_match.end() if front_match else 0
    for match in _TOKEN.finditer(stripped, body_start):
        token = match.group(0)
        if re.search(r"[0-9]", token) and not _token_allowed(token):
            out.append(ClaimViolation(None, None, "H.9(3)", f"{location}:{_line_of(text, match.start())}",
                                      f"a literal number outside a placeholder: {escape_untrusted(token, max_chars=40)}"))
    if (at := text.find(_ATTRIBUTION_PHRASE)) >= 0:  # only the datasheet renderer quotes third-party text (D-910)
        out.append(ClaimViolation(None, None, "H.9(4)", f"{location}:{_line_of(text, at)}",
                                  "the verbatim attribution phrase; only the datasheet renderer may quote third-party text"))
    out.extend(lint_text(location, text))
    for source in source_ids:
        del source  # per-source tags are checked on claims (evaluate_claims), never guessed from prose
    return out


_UNTRUSTED_HEADING: Final = re.compile(r"^#{1,3}\s+Untrusted content\s*$", re.MULTILINE)
_UNTRUSTED_POINTS: Final = ("prompt-injection", "data", "model")


def lint_datasheet(text: str, *, location: str = "DATASHEET.md") -> list[ClaimViolation]:
    """A generated ``DATASHEET.md``: :func:`lint_text` and the G.8.5 "Untrusted content" section."""
    out = lint_text(location, text, verbatim=True)
    match = _UNTRUSTED_HEADING.search(text)
    if match is None:
        out.append(ClaimViolation(None, None, "G.8.5", location, "the datasheet has no 'Untrusted content' section"))
    else:
        section = text[match.end():]
        nxt = re.search(r"^#{1,3}\s", section, re.MULTILINE)
        section = section[: nxt.start()] if nxt else section
        if not all(point in section.lower() for point in _UNTRUSTED_POINTS):
            out.append(ClaimViolation(None, None, "G.8.5", location,
                                      "the 'Untrusted content' section misses a G.8.5 point"))
    return out


class _Checker:
    """The checker injected into :func:`agentprov.corpus.datasheet.render` (M.5.2(1)): card lint, claim evaluation and
    datasheet lint, with violations reduced to ``(code, location, detail)`` triples."""

    def lint_card(self, text: str, *, source_ids: Sequence[str] = ()) -> list[tuple[str, str, str]]:
        return [(v.nc_id, v.location, v.detail) for v in lint_card(text, source_ids=source_ids)]

    def evaluate_claims(self, ids: Iterable[str], manifest: Mapping[str, Any], *, source_ids: Sequence[str] = ()) -> tuple[
            list[dict[str, Any]], list[tuple[str, str, str]]]:
        results, violations = evaluate_claims(ids, manifest, source_ids=source_ids)
        return results, [(v.nc_id, v.location, v.detail) for v in violations]

    def claim_text(self, claim_id: str) -> str:
        return CLAIMS[claim_id].text

    def lint_datasheet(self, text: str) -> list[tuple[str, str, str]]:
        return [(v.nc_id, v.location, v.detail) for v in lint_datasheet(text)]


#: The claims checker of this library (inject it into the datasheet renderer).
CHECKER: Final = _Checker()
