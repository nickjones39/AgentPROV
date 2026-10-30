"""Reader of the Qwen Code JSON-output dialect ``qwencode.json`` (docs/architecture D.24.1, D.24.2; D.2.3; layer L4).

**Files.** One RedCode case's ``qwen --output-format json`` stdout: a single JSON array of message objects whose first is
the ``system``/``init`` message (Qwen Code ``0.21.0`` in all 3,295 complete census files: variant ``v0.21``). The reader
parses with :func:`agentprov.ingest.loaders.strict_json_loads` under the ingest limits and interprets nothing: it yields one
located item for the whole file (key locator ``{"a": <id>}``) whose value lists the messages; the mapper cites one as
``{"p": "/<n>"}``.

**A capture cut at 64 KiB** (D-577 option (b)). The harness's capture cut four outputs at exactly 65,536 bytes, mid-message.
:mod:`agentprov.ingest.jsonstream` is fail-closed (a defective document yields nothing), so the reader salvages the
complete top-level messages itself, through the strict loader only, and **only for a capture cut** (regen item 120,
NF-14): the output is exactly :data:`CAPTURE_CUT_BYTES` long (the premise of ``qwencode:CaptureCut``), the strict
loader's error is ``ingest.json.syntax``, the top-level array is still open at the end of the bytes, and the error lies at
the end of the input (at the end itself, or inside the string, number or literal the cut leaves open: the JSON decoder
reports an unterminated string at its opening quote). Every other rejection (invalid UTF-8, a duplicate key, ``NaN``,
trailing data, an over-size file, a syntax error before the cut, another size) is re-raised, so the runner seals the
D.2.8 case-3 degenerate AER (``unparseable_artefact``) instead of mapping a prefix and dropping the rest silently. The
salvage is bounded (regen item 121, NF-15): one forward pass over the bytes finds the complete top-level elements, the kept
prefix ``data[:cut] + b"]"`` is parsed once with :func:`strict_json_loads`, and each element's span is checked to parse
strictly to its message; the stored bytes are never edited. The item then carries the flag ``qwencode:truncated``, the cut
offset and each salvaged message's byte span: such a file is not valid JSON as a whole, so the mapper cites its messages
as byte ranges, not array pointers (C.9.1).

**Primaries.** Per trajectory directory the reader offers every ``qwen_*.json``; the group's ``_full_api_request_sample.json``
is never a primary (it is a supporting artefact of each run of its group). A 0-byte output is refused with the reason
``qwencode.empty_output`` (register detail of ``select.not_execution_artefact``).

**Label grammar** (D.24.1)::

    <root>results/Qwen/<model>/<S1|S2|S3>/<python|bash>/trajectory/qwen_<scenario>_<payload>[_py|_sh]_<S1|S2|S3>.json

The last seven segments are matched (a prefix is tolerated); the target in the directory and in the file name must agree.

**Per-unit inputs** (runner items R1 and R2 of D.16.14): :meth:`QwenJsonReader.auxiliary_for` names the run's score
record file (``score``), its RedCode request (``dataset`` for S1, ``prompt`` for S2/S3), the execution rules the harness
copied to ``/app/QWEN.md`` (``rules``) and the group's API sample (``api_sample``). The first three live in the deposit's
supplementary zip, a second pin: a reference is ``supp:<label>`` when that pin is a context tree (D-530), else the plain
label when one tree holds both (the trial driver).

Standard library and ``agentprov.{ingest,errors,adapters}`` only.
"""

from __future__ import annotations

import fnmatch
import re
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final, Protocol

from agentprov.adapters.profiles import SourceProfile
from agentprov.adapters.protocols import SourceTree
from agentprov.adapters.qwencode import DIALECT_ID, VARIANT
from agentprov.adapters.types import ArtefactRef, CandidateArtefact, LocatedItem, Locator, SniffResult
from agentprov.errors import IngestError, MalformedArtefact
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.loaders import strict_json_loads

__all__ = [
    "API_SAMPLE",
    "CAPTURE_CUT_BYTES",
    "VERSION_PREFIX",
    "FLAG_TRUNCATED",
    "SUPP_ROLE",
    "LabelFacets",
    "Parsed",
    "QwenJsonReader",
    "parse_label",
    "parse_output",
]

API_SAMPLE: Final = "_full_api_request_sample.json"
SUPP_ROLE: Final = "supp"
FLAG_TRUNCATED: Final = "qwencode:truncated"
#: The harness's capture cap (``qwencode:CaptureCut``; Qwen_evaluation/scoring.py ``_load_trajectory``): only an output of
#: exactly this many bytes is a capture cut, and only a capture cut is salvaged (regen item 120, NF-14).
CAPTURE_CUT_BYTES: Final = 65_536
#: The supported Qwen Code version prefix of variant ``v0.21``: the mapper raises ``UnsupportedVariant`` for any other
#: ``init.qwen_code_version`` (regen item 123, NF-17).
VERSION_PREFIX: Final = "0.21."
_STRAYS: Final = (".DS_Store",)
_FILE: Final = re.compile(r"qwen_(?P<scenario>[0-9]+)_(?P<payload>[0-9]+)(?:_(?P<suffix>py|sh))?_(?P<target>S[123])\.json")
_LANGS: Final = {"python": "py2text_dataset_json", "bash": "bash2text_dataset_json"}
#: The dataset file the harness reads for an S1 scenario (Qwen_evaluation/Qwen.py: python ``_full.json``, bash
#: ``_full_upd.json``).
_DATASET_FILE: Final = {"python": "index{sc}_30_codes_full.json", "bash": "index{sc}_30_codes_full_upd.json"}
_RULES: Final = "OH_evaluation/execution_rules.md"


class Listing(Protocol):
    """What the runner tells a reader about the walked trees (runner items R1/R2): directory siblings and existence."""

    def siblings(self, label: str) -> Sequence[str]: ...

    def exists(self, ref: str) -> bool: ...


# ------------------------------------------------------------------------------------------------ label grammar
@dataclass(frozen=True, slots=True)
class LabelFacets:
    """The facets of a run label (D.24.1). ``prefix`` is everything before ``results/``."""

    prefix: str
    model: str
    target: str
    language: str
    scenario: str
    payload: str
    suffix: str | None
    file: str

    @property
    def case_key(self) -> str:
        """``<scenario>_<payload>``: the score record's ``index`` and the request's ``Index``/``payload_index``."""
        return f"{self.scenario}_{self.payload}"

    @property
    def directory(self) -> str:
        return f"{self.prefix}results/Qwen/{self.model}/{self.target}/{self.language}/trajectory"

    def to_json(self) -> dict[str, Any]:
        return {"model": self.model, "target": self.target, "language": self.language, "scenario": self.scenario,
                "payload": self.payload, "suffix": self.suffix, "file": self.file}  # fmt: skip


def parse_label(label: str) -> LabelFacets | None:
    """The facets of a run label, or ``None`` outside the grammar (or when the two targets disagree)."""
    parts = [p for p in label.replace("\\", "/").split("/") if p]
    if len(parts) < 7:
        return None
    results, qwen, model, target, language, trajectory, name = parts[-7:]
    m = _FILE.fullmatch(name)
    if (results, qwen, trajectory) != ("results", "Qwen", "trajectory") or language not in _LANGS or m is None:
        return None
    if target not in ("S1", "S2", "S3") or m["target"] != target:
        return None
    prefix = "/".join(parts[:-7])
    return LabelFacets(prefix + "/" if prefix else "", model, target, language, m["scenario"], m["payload"],
                       m["suffix"], name)


def _match(label: str, glob: str) -> bool:
    """``fnmatch`` over a POSIX label, ``**/`` also matching zero directories (the runner's matcher)."""
    if fnmatch.fnmatchcase(label, glob):
        return True
    return "**/" in glob and fnmatch.fnmatchcase(label, glob.replace("**/", "", 1))


# ------------------------------------------------------------------------------------------------ parsing
@dataclass(frozen=True, slots=True)
class Parsed:
    """A parsed output: its messages, and for a salvaged one the cut offset (bytes kept) and the bytes dropped."""

    messages: list[Any]
    cut: int | None = None
    dropped: int = 0
    spans: tuple[tuple[int, int], ...] = ()


def parse_output(data: bytes, limits: IngestLimits) -> Parsed:
    """The messages of one output (D-577). ``IngestError`` when the bytes are neither a strict JSON array nor a salvageable
    capture cut of one; ``MalformedArtefact`` when the value is not an array of objects starting with ``system``/``init``."""
    parsed = _load_array(data, limits)
    if parsed is None:
        raise MalformedArtefact("the output is not a JSON array")
    _check_shape(parsed)
    return parsed


def _load_array(data: bytes, limits: IngestLimits) -> Parsed | None:
    """The array of one output, strict or a salvaged capture cut; ``None`` for valid JSON that is not an array;
    ``IngestError`` for everything else."""
    try:
        value = strict_json_loads(data, limits)
    except IngestError as exc:
        salvaged = _salvage(data, exc, limits)
        if salvaged is None:
            raise exc from None
        return salvaged
    return Parsed(value) if isinstance(value, list) else None


def _check_shape(parsed: Parsed) -> None:
    """``MalformedArtefact`` unless the array is a non-empty list of message objects starting with ``system``/``init``."""
    if not parsed.messages or not all(isinstance(m, dict) for m in parsed.messages):
        raise MalformedArtefact("the output is not a non-empty array of message objects")
    first = parsed.messages[0]
    if first.get("type") != "system" or first.get("subtype") != "init":
        raise MalformedArtefact("the output does not start with the system init message")


_STRING_STOP: Final = re.compile(rb'["\\]')
_WS: Final = b" \t\r\n"


@dataclass(frozen=True, slots=True)
class _Scan:
    """One forward pass over the bytes (:func:`_scan`): the byte span ``[start, end)`` of each complete top-level element,
    whether the top-level array closed before the end, and the byte offset of the opening quote of a string still open at
    the end or of a number or literal running to the end."""

    elements: tuple[tuple[int, int], ...]
    closed: bool
    string: int | None = None
    token: int | None = None


def _scan(data: bytes, lead: int) -> _Scan:
    """One forward pass from the top-level ``[`` at ``lead`` (regen item 121, NF-15): tracks strings (with their escapes),
    nesting and bare tokens, and records each complete top-level element (a container up to its closing bracket, a scalar
    up to its last byte before the ``,``); it validates nothing (the strict loader does)."""
    elements: list[tuple[int, int]] = []
    depth, i, n = 0, lead, len(data)
    start: int | None = None  # the current top-level element's first byte
    last = 0  # the end of the current top-level element's last token
    token: int | None = None
    while i < n:
        b = data[i]
        if b == 0x22:  # a string: skip to its closing quote, an escape taking the next byte
            if depth == 1 and start is None:
                start = i
            j = i + 1
            while True:
                m = _STRING_STOP.search(data, j)
                if m is None:
                    return _Scan(tuple(elements), False, string=i)
                j = m.start()
                if data[j] == 0x5C:
                    j += 2
                    continue
                break
            i, token, last = j + 1, None, j + 1
            continue
        if b in b"[{":
            if depth == 1 and start is None:
                start = i
            depth, token = depth + 1, None
        elif b in b"]}":
            depth, token = depth - 1, None
            if depth == 0:
                return _Scan(tuple(elements), True)
            if depth == 1 and start is not None:
                elements.append((start, i + 1))
                start = None
        elif b in b",":
            if depth == 1 and start is not None:
                elements.append((start, last))
                start = None
            token = None
        elif b in _WS:
            token = None
        else:
            if depth == 1 and start is None:
                start = i
            if token is None:
                token = i
            last = i + 1
        i += 1
    return _Scan(tuple(elements), False, token=token)


def _salvage(data: bytes, exc: IngestError, limits: IngestLimits) -> Parsed | None:
    """The complete top-level messages of a capture cut (module docstring), or ``None`` for every other rejection.

    Bounded (regen item 121, NF-15): the exact size is checked before any work (no salvage above 64 KiB), then one forward
    pass (:func:`_scan`) finds the element boundaries, one strict parse of the kept prefix ``data[:cut] + b"]"`` reads the
    messages, and each span is checked to parse strictly to its message (a salvaged file is not valid JSON as a whole, so
    the mapper cites its messages as byte ranges, C.9.1): O(messages) strict parses of O(size) bytes in all. The
    decoder's error position is a character index into the decoded text (a syntax error means the bytes decoded): it is
    converted to a byte offset."""
    if len(data) != CAPTURE_CUT_BYTES or exc.code != "ingest.json.syntax" or exc.offset is None:
        return None
    body = data.lstrip(_WS)
    if not body.startswith(b"["):
        return None
    scan = _scan(data, len(data) - len(body))
    if scan.closed or not scan.elements:
        return None
    try:
        at = len(data.decode("utf-8")[: exc.offset].encode("utf-8"))
    except UnicodeDecodeError:
        return None
    opened = scan.string if scan.string is not None else scan.token
    if at < len(data) and (opened is None or at < opened):
        return None  # the syntax error is not at the end of the input: not a capture cut
    cut = scan.elements[-1][1]
    try:
        value = strict_json_loads(data[:cut] + b"]", limits)
        if not isinstance(value, list) or len(value) != len(scan.elements):
            return None
        for k, (first, end) in enumerate(scan.elements):
            if strict_json_loads(data[first:end], limits) != value[k]:
                return None
    except IngestError:
        return None
    return Parsed(value, cut, len(data) - cut, scan.elements)


class QwenJsonReader:
    """``Reader`` for ``qwencode.json`` (D.2.3, D.24.2)."""

    dialect_id: Final = DIALECT_ID
    version: Final = "0.1.0"
    variants: Final = frozenset({VARIANT})
    media_types: Final = frozenset({"application/json"})

    def __init__(self) -> None:
        self._last: tuple[bytes, Parsed | None] | None = None

    # ---------------------------------------------------------------------------------------------- discovery
    def iter_artefacts(self, tree: SourceTree, profile: SourceProfile) -> Iterator[CandidateArtefact]:
        """Primary candidates: the run outputs the profile includes and does not exclude, in label order."""
        imp = profile.data.get("import", {})
        include = tuple(imp.get("include", ())) or ("**/trajectory/qwen_*.json",)
        exclude = tuple(e["glob"] for e in imp.get("exclude", ()) if isinstance(e, Mapping) and "glob" in e)
        chosen: list[CandidateArtefact] = []
        for candidate in tree.walk():
            name = candidate.label.rsplit("/", 1)[-1]
            if name in _STRAYS or name.startswith("._") or name == API_SAMPLE or parse_label(candidate.label) is None:
                continue
            if any(_match(candidate.label, g) for g in include) and not any(_match(candidate.label, g) for g in exclude):
                chosen.append(candidate)
        yield from sorted(chosen, key=lambda c: c.label)

    def auxiliary_for(self, label: str, listing: Listing) -> dict[str, str]:
        """The per-unit inputs of primary ``label``: those the listing has (module docstring)."""
        f = parse_label(label)
        if f is None:
            return {}
        plan: dict[str, str] = {}
        sample = f"{f.directory}/{API_SAMPLE}"
        if listing.exists(sample):
            plan["api_sample"] = sample
        wanted = {
            "score": f"results/Qwen/{f.model}/{f.target}/{f.language}/conversation_log/index{f.scenario}.json",
            "rules": _RULES,
        }
        if f.target == "S1":
            wanted["dataset"] = f"dataset/RedCode-Exec/{_LANGS[f.language]}/" + _DATASET_FILE[f.language].format(sc=f.scenario)
        else:
            wanted["prompt"] = f"prompt_generator/output/{f.language}/{f.target}/index{f.scenario}.json"
        for role, rel in wanted.items():
            for ref in (f"{SUPP_ROLE}:{rel}", f"{f.prefix}{rel}"):
                if listing.exists(ref):
                    plan[role] = ref
                    break
        return plan

    # ---------------------------------------------------------------------------------------------- sniff and parse
    def _load(self, data: bytes, limits: IngestLimits) -> Parsed | None:
        if self._last is not None and self._last[0] is data:
            return self._last[1]
        parsed = _load_array(data, limits)
        self._last = (data, parsed)
        return parsed

    def sniff(self, data: bytes, *, label: str, limits: IngestLimits) -> SniffResult:
        """Total classification (never raises for foreign input). Every JSON array matches (regen item 123, NF-17): the
        primaries are already selected by the D.24.1 label grammar, so a run output of the wrong shape is a
        ``MalformedArtefact`` at ``parse`` and one of an unsupported Qwen Code version an ``UnsupportedVariant`` of the
        mapper, both sealed as degenerate AERs (D.2.8 case 3). Valid JSON that is not an array is input of another kind
        (``qwencode.sniff.not_array``; D.2.8 case 4), bytes the strict loader refuses outside a capture cut carry its
        ``ingest.*`` code (a degenerate AER, ``unparseable_artefact``)."""
        if not data:
            return SniffResult(False, reasons=("qwencode.empty_output",))
        try:
            parsed = self._load(data, limits)
        except IngestError as exc:
            return SniffResult(False, reasons=(exc.code,))
        if parsed is None:
            return SniffResult(False, reasons=("qwencode.sniff.not_array",))
        flags = frozenset({FLAG_TRUNCATED}) if parsed.cut is not None else frozenset()
        return SniffResult(True, DIALECT_ID, VARIANT, flags, ("qwencode.sniff.json_array",))

    @staticmethod
    def register_detail(reasons: Sequence[str]) -> str | None:
        """The register detail of a valid non-execution input (``qwencode.empty_output``); ``None`` for the default."""
        return next((r for r in reasons if r.startswith("qwencode.") and not r.startswith("qwencode.sniff.")), None)

    def parse(self, data: bytes, artefact: ArtefactRef, *, limits: IngestLimits) -> Iterator[LocatedItem]:
        """One item for the whole file (key locator ``{"a": <id>}``)."""
        sniff = self.sniff(data, label="", limits=limits)
        if not sniff.match:
            raise MalformedArtefact(f"not a Qwen Code JSON output ({', '.join(sniff.reasons)})")
        parsed = self._load(data, limits)
        self._last = None
        if parsed is None:
            raise MalformedArtefact("the output is not a JSON array")
        _check_shape(parsed)
        yield LocatedItem(
            artefact=artefact,
            locator=Locator(a=artefact.id),
            dialect=DIALECT_ID,
            variant=VARIANT,
            flags=sniff.flags,
            value={"messages": parsed.messages, "cut": parsed.cut, "dropped": parsed.dropped, "size": len(data),
                   "spans": [list(span) for span in parsed.spans]},
        )
