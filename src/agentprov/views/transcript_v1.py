"""The AgentDojo-PROV ``transcript/v1`` view of an AER (docs/architecture C.15.3; D.7.4; J.3.2; AD-02, AD-07).

::

    doc = render(aer)               # order- and type-faithful v1 document from an ``adprov.transcript_v1`` AER
    doc = render_converted(aer)     # the converted-tree form from an ``agentdojo.tracelogger`` AER
    data = serialise(doc)           # json.dumps(doc, indent=2), Python defaults, UTF-8, no trailing newline

The view reads **nothing** from raw artefacts: every value comes from the AER records and their ``ext.lex`` hints
(C.11.4), which restore the source member order and integral floats that JCS lines lose. ``serialise(render(aer))``
equals the source bytes for every AER the ``adprov.transcript_v1`` importer produced from a frozen-baseline transcript
(gates A1 and A2, J.3.2); for AER from other sources the view is defined, but byte identity does not apply.

Where each v1 member comes from is the single field table ``transcript_v1_fields.toml`` (R-30), which the importer reads
too. ``aer`` is an :class:`agentprov.aer.reader.AerDocument` or any sequence of records (header first; a trailing seal is
ignored). The view never raises on source text and prints none; a structural defect raises :class:`ViewError` naming a
record id and pointer only.

**Content not inlined** (C.15.3; D-1063, regen-batch row 180; the D-934 pattern). A string whose UTF-8 encoding exceeds
1 MiB is not in the AER: the mapper put ``{"not_inlined": {"sha256", "bytes"}}`` in its place and cited a
``<family>.content_not_inlined@<n>`` rule at that pointer. The view renders every such position, and only those, as the
marker ``{"agentprov:not_inlined": {"sha256": <hex>, "bytes": <n>}}`` (:data:`NOT_INLINED_KEY`): a tool turn's content, a
system, user or assistant text, a reasoning or refusal, or a value inside tool arguments, an injection payload or an extra
member. A tool turn's ``content_sha256`` stays the digest of the content (the recorded one, else ``sha256:`` and the
marker's digest). The view is lossy exactly there: the text stays in the raw artefact and is never made up. Source data
that holds a member named ``agentprov:not_inlined`` is refused, so a marker in a view is never source content.
"""

from __future__ import annotations

import hashlib
import json
import re
import tomllib
from collections.abc import Iterable, Mapping, Sequence
from functools import cache
from importlib import resources
from typing import Any, Final

from agentprov.aer.canon import LexHints, decode_value, pointer_unescape
from agentprov.aer.locators import pointer_get
from agentprov.errors import AgentProvError

__all__ = [
    "BENIGN_LABEL",
    "CONVERTED_SOURCE",
    "NOT_INLINED_KEY",
    "SCHEMA_ID",
    "TIMING_STUB",
    "ViewError",
    "field_table",
    "layout",
    "render",
    "render_converted",
    "serialise",
]

SCHEMA_ID: Final = "transcript/v1"
BENIGN_LABEL: Final = "benign"  # adprov.v1_benign_label@1
CONVERTED_SOURCE: Final = "agentdojo_native_run_log"
TIMING_STUB: Final = "0"  # rendered by render_converted only (erratum E8): the stub is a view rule, never AER data
_TABLE_RESOURCE: Final = "transcript_v1_fields.toml"
_ID_RE: Final = re.compile(r"([a-z_]*?)([0-9]+)$")
#: The member of the marker that stands for content the AER does not inline (C.15.3; D-1063): a namespaced name, never a
#: v1 member, and refused in source data, so a marker cannot be mistaken for source content or forged by it.
NOT_INLINED_KEY: Final = "agentprov:not_inlined"
#: A rule that replaced a string over 1 MiB by its digest (C.2.1(6); ``adprov.content_not_inlined@1``,
#: ``agentdojo.content_not_inlined@1``, the D-934 pattern of every family).
_NOT_INLINED_RULE: Final = re.compile(r"[a-z][a-z0-9_]*\.content_not_inlined@[1-9][0-9]*")
_HEX64: Final = re.compile(r"[0-9a-f]{64}")


class ViewError(AgentProvError):
    """The AER cannot be rendered as transcript/v1 (a missing record or a value of the wrong type)."""

    code = "view.transcript_v1"
    exit_code = 1


# ------------------------------------------------------------------------------------------------ the field table
@cache
def field_table() -> Mapping[str, Any]:
    """The parsed field table (package data; immutable by convention)."""
    data = resources.files("agentprov.views").joinpath(_TABLE_RESOURCE).read_bytes()
    return tomllib.loads(data.decode("utf-8"))


def layout(name: str) -> tuple[tuple[str, bool], ...]:
    """The J.3.2 member order of object ``name``: ``(member, optional)`` pairs."""
    raw = field_table()["layout"][name]
    return tuple((m[1:], True) if m.startswith("?") else (m, False) for m in raw)


def layout_members(name: str) -> tuple[str, ...]:
    return tuple(m for m, _ in layout(name))


@cache
def _meta_sources() -> dict[str, tuple[str, ...]]:
    return {e["key"]: tuple(e["sources"]) for e in field_table()["meta"]}


@cache
def _meta_null_renders() -> dict[str, str]:
    return {e["key"]: e["null_renders"] for e in field_table()["meta"] if "null_renders" in e}


@cache
def _model_config_sources() -> dict[str, tuple[str, ...]]:
    return {e["key"]: tuple(e["sources"]) for e in field_table()["model_config"]}


@cache
def usage_map() -> dict[str, str]:
    """v1 ``usage`` member -> AER ``Usage`` member (C.15.3)."""
    return {e["key"]: e["aer"] for e in field_table()["usage"]}


# ------------------------------------------------------------------------------------------------ AER access
class _Aer:
    """Index over one AER's records (header first; the seal, if present, is ignored)."""

    def __init__(self, aer: Any) -> None:
        records = list(getattr(aer, "records", aer))
        records = [r for r in records if isinstance(r, Mapping) and r.get("k") != "seal"]
        if not records or records[0].get("k") != "execution":
            raise ViewError("the first record is not the execution header")
        if len(records) == 2 and records[1].get("k") == "scope" and records[1].get("kind") == "run":
            # F-2 (pre-round review #32): a degenerate AER (D.2.8 case 3: the header, the run scope and the seal) holds
            # no run to transcribe; rendering it would invent a complete benign run with no turns (an absent attack_id
            # is not a null one), and the compat graph built from that view an empty user query
            raise ViewError("a degenerate AER (header, run scope and seal only) has no run to render")
        self.header: Mapping[str, Any] = records[0]
        self.records: list[Mapping[str, Any]] = records
        self.by_id: dict[str, Mapping[str, Any]] = {}
        for record in records:
            rid = record.get("id")
            if isinstance(rid, str):
                self.by_id[rid] = record
        self._lex: dict[int, LexHints] = {}
        self._digests: dict[int, dict[str, Mapping[str, Any]]] = {}
        self._markers: list[dict[str, Any]] = []  # kept alive: their ids identify the view's own markers
        self._marker_ids: set[int] = set()

    def not_inlined(self, record: Mapping[str, Any]) -> Mapping[str, Mapping[str, Any]]:
        """``{pointer: digest}`` of the strings ``record`` does not inline: each pointer a ``*.content_not_inlined``
        rule reference names, whose value is ``{"not_inlined": {"sha256", "bytes"}}`` (C.2.1(6); D-1063). Only the
        citation makes a digest object one: a source object of that shape elsewhere is data."""
        key = id(record)
        found = self._digests.get(key)
        if found is None:
            found = {}
            for ref in _list(record.get("rule")):
                rid, hash_, pointer = ref.partition("#") if isinstance(ref, str) else ("", "", "")
                if not hash_ or not _NOT_INLINED_RULE.fullmatch(rid):
                    continue
                try:
                    raw = pointer_get(record, pointer)
                except (KeyError, IndexError, TypeError):
                    raw = None
                digest = raw.get("not_inlined") if isinstance(raw, Mapping) and len(raw) == 1 else None
                if not (isinstance(digest, Mapping) and set(digest) <= {"sha256", "bytes", "media"}
                        and isinstance(digest.get("sha256"), str) and _HEX64.fullmatch(digest["sha256"])
                        and type(digest.get("bytes")) is int and digest["bytes"] >= 0
                        and isinstance(digest.get("media", ""), str)):
                    raise ViewError(f"record {record.get('id')!s}: {pointer} cites {rid} but holds no digest")
                found[pointer] = digest
            self._digests[key] = found
        return found

    def marker(self, digest: Mapping[str, Any]) -> dict[str, Any]:
        """The view's marker for one string not inlined (C.15.3): ``{"agentprov:not_inlined": {sha256, bytes}}``."""
        body: dict[str, Any] = {"sha256": digest["sha256"], "bytes": digest["bytes"]}
        if "media" in digest:
            body["media"] = digest["media"]
        mark = {NOT_INLINED_KEY: body}
        self._markers.append(mark)
        self._marker_ids.add(id(mark))
        return mark

    def check_reserved(self, out: object) -> None:
        """Refuse a document in which a member named ``agentprov:not_inlined`` is not one of this view's markers:
        source data holding that name would read as a marker (C.15.3)."""
        stack = [out]
        while stack:
            node = stack.pop()
            if isinstance(node, dict):
                if id(node) in self._marker_ids:
                    continue
                if NOT_INLINED_KEY in node:
                    raise ViewError(f"source data holds the reserved member {NOT_INLINED_KEY}")
                stack.extend(node.values())
            elif isinstance(node, list):
                stack.extend(node)

    def text(self, message: Mapping[str, Any], k: int) -> tuple[bool, Any]:
        """``(found, value)`` of part ``k``'s text: the decoded ``text``, or the marker where the part's text was not
        inlined (the mapper moved the digest to ``value``)."""
        found, value = self.value(message, f"/parts/{k}/text")
        if not found and f"/parts/{k}/value" in self.not_inlined(message):
            return self.value(message, f"/parts/{k}/value")
        return found, value

    def kind(self, message: Mapping[str, Any], k: int, part: Mapping[str, Any]) -> object:
        """The part's kind: ``t``, or for an ``other`` part that holds a text not inlined, the source type it keeps."""
        if part.get("t") == "other" and f"/parts/{k}/value" in self.not_inlined(message):
            return part.get("type")
        return part.get("t")

    def lex(self, record: Mapping[str, Any]) -> LexHints:
        key = id(record)
        hints = self._lex.get(key)
        if hints is None:
            ext = record.get("ext")
            hints = LexHints.from_dict(ext.get("lex") if isinstance(ext, Mapping) else None)
            self._lex[key] = hints
        return hints

    def value(self, record: Mapping[str, Any] | None, pointer: str) -> tuple[bool, Any]:
        """``(found, decoded value)`` of ``pointer`` in ``record``, with the record's lexical hints applied."""
        if record is None:
            return False, None
        try:
            raw = pointer_get(record, pointer)
        except (KeyError, IndexError, TypeError):
            return False, None
        digests = self.not_inlined(record)
        if pointer in digests:
            return True, self.marker(digests[pointer])
        value = decode_value(raw, at=pointer, lex=self.lex(record))
        for at, digest in digests.items():
            if at.startswith(pointer + "/"):
                tokens = [pointer_unescape(t) for t in at[len(pointer) + 1:].split("/")]
                value = _put(value, raw, tokens, self.marker(digest), at=f"record {record.get('id')!s}: {at}")
        return True, value

    def of_kind(self, kind: str) -> list[Mapping[str, Any]]:
        return [r for r in self.records if r.get("k") == kind]

    def judgement(self, name: str) -> Mapping[str, Any] | None:
        for record in self.of_kind("judgement"):
            if record.get("name") == name and "revises" not in record:
                return record
        return None

    def part(self, part_id: str) -> Mapping[str, Any] | None:
        base, _, ordinal = part_id.partition("#")
        message = self.by_id.get(base)
        if message is None or not (ordinal.isascii() and ordinal.isdigit()) or len(ordinal) > 18:  # split_part_id
            return None
        parts = message.get("parts")
        k = int(ordinal)
        return parts[k] if isinstance(parts, list) and k < len(parts) else None

    def resolve(self, source: str) -> tuple[bool, Any]:
        """Resolve one ``<record>:<pointer>`` source of the field table (``handler:`` sources are not resolved here)."""
        head, _, rest = source.partition(":")
        if head == "exec":
            return self.value(self.header, rest)
        if head in ("actor", "scope"):
            rid, _, pointer = rest.partition(":")
            return self.value(self.by_id.get(rid), pointer)
        if head == "judgement":
            name, _, pointer = rest.partition(":")
            return self.value(self.judgement(name), pointer)
        raise ViewError(f"unknown source form {head!r} in the field table")


def _put(decoded: Any, raw: Any, tokens: Sequence[str], mark: dict[str, Any], *, at: str, literal: bool = False) -> Any:
    """``decoded`` (the decoded form of the AER value ``raw``) with ``mark`` at the encoded-form path ``tokens``: a
    ``$lit`` wrapper token (C.11.3) has no decoded counterpart; any other token names the same member or item."""
    if not tokens:
        return mark
    head, rest = tokens[0], tokens[1:]
    if isinstance(raw, dict):
        if not literal and head == "$lit" and len(raw) == 1 and "$lit" in raw:
            return _put(decoded, raw["$lit"], rest, mark, at=at, literal=True)
        if isinstance(decoded, dict) and head in raw and head in decoded:
            decoded[head] = _put(decoded[head], raw[head], rest, mark, at=at)
            return decoded
    elif isinstance(raw, list) and isinstance(decoded, list) and head.isascii() and head.isdigit():
        index = int(head) if len(head) <= 18 else len(raw)
        if index < len(raw) and len(raw) == len(decoded):
            decoded[index] = _put(decoded[index], raw[index], rest, mark, at=at)
            return decoded
    raise ViewError(f"{at}: the digest's pointer does not resolve in the decoded value")


def _is_marker(value: object) -> bool:
    """A marker's shape (:meth:`_Aer.marker`); :meth:`_Aer.check_reserved` refuses any the view did not make."""
    return isinstance(value, dict) and len(value) == 1 and isinstance(value.get(NOT_INLINED_KEY), dict)


def _content_digest(content: Any) -> str:
    """v1 ``content_sha256``: ``sha256:`` + hex SHA-256 of the content's UTF-8, which a marker carries (C.15.3)."""
    if _is_marker(content):
        return "sha256:" + str(content[NOT_INLINED_KEY]["sha256"])
    return "sha256:" + hashlib.sha256(content.encode("utf-8")).hexdigest()


def _concat(pieces: Sequence[Any], where: str) -> Any:
    """``"".join(pieces)``, the converter's concatenation; a single marker beside empty texts only is that marker. A
    marker beside other text has no rendering (the joined text is unknown): ``ViewError``, never a partial text."""
    if all(isinstance(p, str) for p in pieces):
        return "".join(pieces)
    marks = [p for p in pieces if _is_marker(p)]
    if marks and all(isinstance(p, str) or _is_marker(p) for p in pieces):
        if len(marks) == 1 and all(p == "" for p in pieces if isinstance(p, str)):
            return marks[0]
        raise ViewError(f"{where}: content not inlined is joined with other text, which the converter rules "
                        "cannot render")
    return "".join(pieces)  # raises TypeError on a piece that is not text, as the converter rule does


def _ordinal(record_id: object) -> tuple[str, int]:
    """Local-id order: ``m2`` < ``m10``; ids with the same prefix sort by their trailing number."""
    text = str(record_id)
    match = _ID_RE.search(text)
    return (text[: match.start(2)], int(match.group(2))) if match else (text, -1)


def _dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def _ext(record: Mapping[str, Any], prefix: str) -> Mapping[str, Any]:
    ext = record.get("ext")
    value = ext.get(prefix) if isinstance(ext, Mapping) else None
    return value if isinstance(value, Mapping) else {}


# ------------------------------------------------------------------------------------------------ render (adprov AER)
def render(aer: Any) -> dict[str, Any]:
    """The transcript/v1 document of an ``adprov.transcript_v1`` AER (C.15.3): order- and type-faithful."""
    doc = _Aer(aer)
    v1 = _ext(doc.header, "adprov").get("v1")
    v1 = v1 if isinstance(v1, Mapping) else {}
    out: dict[str, Any] = {"adprov_schema": SCHEMA_ID, "meta": _render_meta(doc, v1)}
    scored, discarded = _attempts(doc)
    out["turns"] = _render_turns(doc, scored)
    if discarded:
        out["discarded_attempts"] = [_render_discarded(doc, scope) for scope in discarded]
    elif v1.get("discarded_attempts_empty") is True:
        out["discarded_attempts"] = []
    doc.check_reserved(out)
    return out


def _render_meta(doc: _Aer, v1: Mapping[str, Any]) -> dict[str, Any]:
    keys = v1.get("meta_keys")
    if not isinstance(keys, list):
        keys = [m for m, optional in layout("meta") if not optional]
    sources = _meta_sources()
    null_renders = _meta_null_renders()
    meta: dict[str, Any] = {}
    for key in keys:
        if key in sources:
            value = _first(doc, sources[key], v1, key)
        else:
            value = doc.value(doc.header, f"/ext/adprov/meta_extra/{_esc(key)}")[1]
        if value is None and key in null_renders:
            value = null_renders[key]
        meta[str(key)] = value
    return meta


def _first(doc: _Aer, sources: Sequence[str], v1: Mapping[str, Any], key: str) -> Any:
    for source in sources:
        if source.startswith("handler:"):
            return _HANDLERS[source.partition(":")[2]](doc, v1)
        found, value = doc.resolve(source)
        if found:
            return value
    return None


def _esc(token: object) -> str:
    return str(token).replace("~", "~0").replace("/", "~1")


def _handler_injections(doc: _Aer, v1: Mapping[str, Any]) -> dict[str, Any]:
    fixtures = [f for f in doc.of_kind("fixture") if f.get("kind") == "injection_payload"]
    fixtures.sort(key=lambda f: _ordinal(f.get("id")))
    out: dict[str, Any] = {}
    for fixture in fixtures:
        out[str(fixture.get("vector"))] = doc.value(fixture, "/content")[1]
    return out


def _handler_model_config(doc: _Aer, v1: Mapping[str, Any]) -> dict[str, Any] | None:
    keys = v1.get("model_config_keys")
    if not isinstance(keys, list):
        return None
    sources = _model_config_sources()
    out: dict[str, Any] = {}
    for key in keys:
        if key in sources:
            out[str(key)] = _first(doc, sources[key], v1, key)
        else:
            out[str(key)] = doc.value(doc.header, f"/ext/adprov/model_config_extra/{_esc(key)}")[1]
    return out


def _handler_usage(doc: _Aer, v1: Mapping[str, Any]) -> dict[str, Any] | None:
    keys = v1.get("usage_keys")
    if not isinstance(keys, list):
        return None
    run = doc.by_id.get("run")
    mapping = usage_map()
    out: dict[str, Any] = {}
    for key in keys:
        extra = f"/ext/adprov/usage_extra/{_esc(key)}"
        if key in mapping:
            # the mapper types a known key only for a non-negative int; any other value is kept at usage_extra
            found, value = doc.value(run, f"/usage/{mapping[key]}")
            out[str(key)] = value if found else doc.value(run, extra)[1]
        else:
            out[str(key)] = doc.value(run, extra)[1]
    return out


def _handler_finish_reasons(doc: _Aer, v1: Mapping[str, Any]) -> Any:
    found, verbatim = doc.value(doc.header, "/ext/adprov/v1/finish_reasons")
    if found:  # a list that is not alignable, or a non-list value (an explicit null included) kept verbatim
        return list(verbatim) if isinstance(verbatim, list) else verbatim
    calls = [r for r in doc.of_kind("model_call") if r.get("role") == "agent"]
    calls.sort(key=lambda r: _ordinal(r.get("id")))
    return [doc.value(call, "/finish_reason")[1] for call in calls]


_HANDLERS: Final = {
    "injections": _handler_injections,
    "model_config": _handler_model_config,
    "usage": _handler_usage,
    "finish_reasons": _handler_finish_reasons,
}


def handler_names() -> frozenset[str]:
    """The ``handler:`` names the view implements (checked against the field table by the tests)."""
    return frozenset(_HANDLERS)


def _attempts(doc: _Aer) -> tuple[Mapping[str, Any] | None, list[Mapping[str, Any]]]:
    """The scored attempt scope and the discarded attempts (non-scored, with a known index) in index order."""
    scored: Mapping[str, Any] | None = None
    discarded: list[Mapping[str, Any]] = []
    for scope in doc.of_kind("scope"):
        if scope.get("kind") != "attempt":
            continue
        if scope.get("scored") is True:
            if scored is not None:
                raise ViewError("more than one scored attempt")
            scored = scope
        elif isinstance(scope.get("index"), int):
            discarded.append(scope)
    discarded.sort(key=lambda s: int(s["index"]))
    return scored, discarded


def _discarded_reply(doc: _Aer, message: Mapping[str, Any]) -> bool:
    """A message generated by a discarded model call (a reply the harness rejected): views exclude it by default
    (C.13.7, D.10.4). No ``transcript/v1`` import has one."""
    generator = doc.by_id.get(str(message.get("generated_by")))
    return generator is not None and generator.get("k") == "model_call" and generator.get("status") == "discarded"


def _messages_of(doc: _Aer, scope: Mapping[str, Any] | None) -> list[Mapping[str, Any]]:
    if scope is None:
        return []
    sid = scope.get("id")
    messages = [m for m in doc.of_kind("message") if m.get("scope") == sid and not _discarded_reply(doc, m)]
    messages.sort(key=lambda m: _ordinal(m.get("id")))
    return messages


def _render_turns(doc: _Aer, scope: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    return [_render_turn(doc, message) for message in _messages_of(doc, scope)]


def _render_discarded(doc: _Aer, scope: Mapping[str, Any]) -> dict[str, Any]:
    entry: dict[str, Any] = {"turns": _render_turns(doc, scope)}
    found, alignment = doc.value(scope, "/ext/adprov/reasoning_alignment")
    if found:
        entry["reasoning_alignment"] = alignment
    return entry


def _part_text(doc: _Aer, message: Mapping[str, Any], kind: str) -> tuple[bool, Any]:
    parts = message.get("parts")
    if not isinstance(parts, list):
        return False, None
    for k, part in enumerate(parts):
        if isinstance(part, Mapping) and doc.kind(message, k, part) == kind:
            # pre-round review #35: a part whose text aer/0.2 withholds (D-211) is still there; it renders null. A text
            # not inlined (an other part of this type, D-1063) renders the marker
            found, value = doc.text(message, k)
            return True, value if found else None
    return False, None


def _order(message: Mapping[str, Any], built: dict[str, Any], template: str, doc: _Aer) -> dict[str, Any]:
    """Apply ``ext.adprov.keys`` (a recorded non-canonical order) and ``ext.adprov.extra`` (unknown members)."""
    adprov = _ext(message, "adprov")
    keys = adprov.get("keys")
    extra = adprov.get("extra")
    if isinstance(extra, Mapping):
        for key in extra:
            built[str(key)] = doc.value(message, f"/ext/adprov/extra/{_esc(key)}")[1]
    if isinstance(keys, list):
        return {str(k): built[str(k)] for k in keys if str(k) in built}
    return {m: built[m] for m in layout_members(template) if m in built}


def _render_turn(doc: _Aer, message: Mapping[str, Any]) -> dict[str, Any]:
    role = message.get("role")
    if role == "assistant":
        return _render_assistant(doc, message)
    if role == "tool":
        return _render_tool(doc, message)
    built = {"role": role, "content": _part_text(doc, message, "text")[1]}
    template = "system_turn" if role == "system" else "user_turn" if role == "user" else "other_turn"
    return _order(message, built, template, doc)


def _render_assistant(doc: _Aer, message: Mapping[str, Any]) -> dict[str, Any]:
    built: dict[str, Any] = {"role": "assistant", "text": _part_text(doc, message, "text")[1]}
    found, reasoning = _part_text(doc, message, "reasoning")
    if found:
        built["reasoning"] = reasoning
    calls: list[dict[str, Any]] = []
    placeholders = _ext(message, "adprov").get("placeholder_args")
    parts = _list(message.get("parts"))
    has_calls = False
    for k, part in enumerate(parts):
        if not isinstance(part, Mapping) or part.get("t") != "tool_call":
            continue
        has_calls = True
        call: dict[str, Any] = {
            "id": doc.value(message, f"/parts/{k}/provider_call_id")[1],
            "function": part.get("name"),
            "args": doc.value(message, f"/parts/{k}/args")[1],
        }
        if isinstance(placeholders, Mapping) and str(k) in placeholders:
            call["placeholder_args"] = doc.value(message, f"/ext/adprov/placeholder_args/{k}")[1]
        calls.append(call)
    if has_calls or "tool_calls" in (_ext(message, "adprov").get("keys") or ()):
        built["tool_calls"] = calls
    found, refusal = _part_text(doc, message, "refusal")
    if found:
        built["refusal"] = refusal
    kinds = [doc.kind(message, k, part) for k, part in enumerate(parts) if isinstance(part, Mapping)]
    return _order(message, built, _assistant_template(kinds), doc)


def _assistant_template(kinds: Sequence[object]) -> str:
    """``assistant_turn``, or ``assistant_turn_log_reasoning`` when the reasoning part follows a tool-call or refusal
    part: the order of reasoning the baseline attached from the LLM element's side log, which a live AER carries as a
    part taken from the response after the native ones (``agentdojo.capture_reply_wire_fields@1``). An
    ``adprov.transcript_v1`` AER always lists reasoning before its calls and records any other order in
    ``ext.adprov.keys``, which takes precedence (:func:`_order`). ``kinds`` are the parts' kinds (:meth:`_Aer.kind`)."""
    if "reasoning" in kinds and any(k in ("tool_call", "refusal") for k in kinds[: kinds.index("reasoning")]):
        return "assistant_turn_log_reasoning"
    return "assistant_turn"


def _execution_of(doc: _Aer, message: Mapping[str, Any]) -> Mapping[str, Any] | None:
    """The tool execution behind a tool message: its generator, or the subject of the decision that generated it."""
    generator = doc.by_id.get(str(message.get("generated_by")))
    if generator is not None and generator.get("k") == "decision":
        generator = doc.by_id.get(str(generator.get("subject")))
    if generator is not None and generator.get("k") == "tool_execution":
        return generator
    return None


def _render_tool(doc: _Aer, message: Mapping[str, Any]) -> dict[str, Any]:
    parts = message.get("parts")
    part = parts[0] if isinstance(parts, list) and parts and isinstance(parts[0], Mapping) else {}
    adprov = _ext(message, "adprov")
    if "tool_call_id" in adprov:
        tool_call_id = doc.value(message, "/ext/adprov/tool_call_id")[1]
    else:
        call = doc.part(str(part.get("responds_to"))) if "responds_to" in part else None
        tool_call_id = call.get("provider_call_id") if isinstance(call, Mapping) else None
    execution = _execution_of(doc, message)
    content = doc.text(message, 0)[1]  # a content not inlined renders the marker (D-1063)
    if "content_sha256" in adprov:
        digest = doc.value(message, "/ext/adprov/content_sha256")[1]
    elif isinstance(content, str) or _is_marker(content):
        digest = _content_digest(content)
    else:
        raise ViewError(f"tool message {message.get('id')!s}: no text content to digest")
    built: dict[str, Any] = {
        "role": "tool",
        "tool_call_id": tool_call_id,
        "function": execution.get("name") if execution is not None else None,
        "args": doc.value(execution, "/args")[1] if execution is not None else {},
        "content": content,
        "content_sha256": digest,
        "error": doc.value(message, "/parts/0/error")[1],
    }
    if execution is not None:
        found_start, start = doc.value(execution, "/t/raw/start")
        found_end, end = doc.value(execution, "/t/raw/end")
        if found_start and found_end:
            built["started_at"], built["ended_at"] = start, end
    return _order(message, built, "tool_turn", doc)


# ------------------------------------------------------------------------------------------------ render_converted
def render_converted(aer: Any) -> dict[str, Any]:
    """The converted-tree transcript/v1 of an ``agentdojo.tracelogger`` AER (C.15.3; D.7.4 gate R; AD-07).

    It re-applies the baseline converter's documented field rules (``agentdojo_prov/convert_runs.py:138-208``) inside the
    view: model = model_id = pipeline name, a null attack renders ``"benign"``, unknown run times and versions render
    null, ``wall_clock_s = round(duration, 3)``, and every tool turn carries the ``"0"`` timing stub (erratum E8). None
    of these conventions is AER data.
    """
    doc = _Aer(aer)
    header = doc.header
    task = _dict(header.get("task"))
    pipeline = doc.value(header, "/ext/agentdojo/pipeline_name")[1]
    attack = task.get("attack_id")
    utility = doc.value(doc.judgement("utility"), "/value")[1]
    security = doc.value(doc.judgement("security"), "/value")[1]
    found, duration = doc.value(doc.by_id.get("run"), "/t/dur_s")
    meta: dict[str, Any] = {
        "model": pipeline,
        "model_id": pipeline,
        "suite": task.get("suite"),
        "user_task_id": task.get("task_id"),
        "injection_task_id": task.get("attack_target_id"),
        "attack_type": attack if attack is not None else BENIGN_LABEL,
        "injections": _handler_injections(doc, {}),
        "utility": None if utility is None else bool(utility),
        "security": None if security is None else bool(security),
        "started_at": None,
        "ended_at": None,
        "wall_clock_s": round(float(duration), 3) if found and duration is not None else None,
        "agentdojo_version": None,
        "benchmark_version": None,
        "source": CONVERTED_SOURCE,
        "pipeline_name": pipeline,
        "timing_stubbed": True,
    }
    run_error = doc.value(header, "/ext/agentdojo/error")[1]
    if run_error is not None:
        meta["run_error"] = run_error
    scored, _ = _attempts(doc)
    turns = [_converted_turn(doc, m) for m in _messages_of(doc, scored)]
    out = {"adprov_schema": SCHEMA_ID, "meta": meta, "turns": turns}
    doc.check_reserved(out)
    return out


# AgentDojo content-block types the converter's ``_split_blocks`` reads, per AER part kind
_BLOCK_TYPES: dict[str, frozenset[str]] = {"text": frozenset({"text"}), "reasoning": frozenset({"thinking", "redacted_thinking"})}


def _joined(doc: _Aer, message: Mapping[str, Any], kinds: Iterable[str]) -> tuple[bool, Any]:
    """``(any part of these kinds, concatenated non-null texts)``: the converter's ``_split_blocks`` over AER parts.
    A text or thinking block the importer kept verbatim (an ``agentdojo.unknown_block`` part, regeneration-batch item
    90) contributes its ``content`` as the converter reads it (``content or ""``). A text not inlined is its marker
    (:func:`_concat`; D-1063)."""
    wanted = set(kinds)
    blocks = frozenset().union(*(_BLOCK_TYPES.get(kind, frozenset()) for kind in wanted))
    parts = _list(message.get("parts"))
    seen, texts = False, []
    for k, part in enumerate(parts):
        if isinstance(part, Mapping) and doc.kind(message, k, part) in wanted:
            seen = True
            text = doc.text(message, k)[1]
            if isinstance(text, str) or _is_marker(text):
                texts.append(text)
        elif (blocks and isinstance(part, Mapping) and part.get("t") == "other"
              and part.get("type") == "agentdojo.unknown_block"):
            block = doc.value(message, f"/parts/{k}/value")[1]
            if isinstance(block, Mapping) and block.get("type") in blocks:
                seen = True
                body = block.get("content", "") or ""
                if isinstance(body, str) or _is_marker(body):
                    texts.append(body)
    return seen, _concat(texts, f"message {message.get('id')!s}")


def _converted_call(fid: Any, function: Any, args: Any, placeholder: Any = None) -> dict[str, Any]:
    """``transcript._serialize_function_call`` over plain values (``args or {}``; placeholders only when they differ)."""
    out: dict[str, Any] = {"id": fid, "function": function, "args": _args(args)}
    if placeholder is not None and placeholder != out["args"]:
        out["placeholder_args"] = placeholder
    return out


def _args(args: Any) -> Any:
    """The converter's ``args or {}`` as a dict; arguments not inlined as a whole stay their marker."""
    return args if _is_marker(args) else dict(args or {})


def _split_blocks(content: Any, where: str = "a native message") -> tuple[Any, Any]:
    """``transcript._split_blocks`` (converter rule): ``(text, reasoning)`` of a native content value. A content or a
    block's content not inlined is its marker (:func:`_concat`; D-1063)."""
    if not content:
        return "", ""
    if isinstance(content, str) or _is_marker(content):
        return content, ""
    text_parts: list[str] = []
    think_parts: list[str] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        body = block.get("content", "") or ""
        if block.get("type") == "text":
            text_parts.append(body)
        elif block.get("type") in ("thinking", "redacted_thinking"):
            think_parts.append(body)
    return _concat(text_parts, where), _concat(think_parts, where)


def _native_message_turn(msg: Any, where: str = "a native message") -> dict[str, Any]:
    """``transcript.message_to_turn`` on a message the importer kept verbatim (an ``agentdojo.unknown_message`` part)."""
    if not isinstance(msg, dict):
        return {"role": None, "content": ""}
    role = msg.get("role")
    text, reasoning = _split_blocks(msg.get("content"), where)
    if role in ("system", "user"):
        return {"role": role, "content": text}
    if role == "assistant":
        turn: dict[str, Any] = {"role": "assistant", "text": None if msg.get("content") is None else text}
        if reasoning:
            turn["reasoning"] = reasoning
        calls = msg.get("tool_calls") or []
        if calls:
            turn["tool_calls"] = [_converted_call(c.get("id"), c.get("function"), c.get("args"), c.get("placeholder_args"))
                                  if isinstance(c, dict) else {"id": None, "function": None, "args": {}} for c in calls]
        return turn
    if role == "tool":
        echo = msg.get("tool_call")
        scall = _converted_call(echo.get("id"), echo.get("function"), echo.get("args")) if isinstance(echo, dict) else {
            "id": None, "function": None, "args": {}}
        return {
            "role": "tool",
            "tool_call_id": msg.get("tool_call_id"),
            "function": scall.get("function"),
            "args": scall.get("args", {}),
            "content": text,
            "content_sha256": _content_digest(text),
            "error": msg.get("error"),
            "started_at": TIMING_STUB,
            "ended_at": TIMING_STUB,
        }
    return {"role": role, "content": text}


def _converted_turn(doc: _Aer, message: Mapping[str, Any]) -> dict[str, Any]:
    role = message.get("role")
    parts = _list(message.get("parts"))
    if len(parts) == 1 and isinstance(parts[0], Mapping) and parts[0].get("t") == "other" and \
            parts[0].get("type") == "agentdojo.unknown_message":
        try:  # the value is verbatim untrusted source JSON; the converter rules assume its types
            return _native_message_turn(doc.value(message, "/parts/0/value")[1], f"message {message.get('id')!s}")
        except (TypeError, ValueError, AttributeError) as exc:  # UnicodeEncodeError is a ValueError
            raise ViewError(f"message {message.get('id')!s}: /parts/0/value has a shape the converter rules "
                            f"cannot render ({type(exc).__name__})") from None
    if role == "assistant":
        # ``content: null``; a null-content text block (ext.agentdojo.null_text_blocks, item 77) is ``""`` to the converter
        null_content = "null_text_blocks" not in _ext(message, "agentdojo") and len(
            [p for p in parts if isinstance(p, Mapping) and p.get("t") == "text"]) == 1 and any(
            isinstance(p, Mapping) and p.get("t") == "text" and p.get("text") is None for p in parts
        )
        _, text = _joined(doc, message, ("text",))
        turn: dict[str, Any] = {"role": "assistant", "text": None if null_content else text}
        _, reasoning = _joined(doc, message, ("reasoning",))
        if reasoning:
            turn["reasoning"] = reasoning
        placeholders = _ext(message, "agentdojo").get("placeholder_args")
        calls = []
        for k, part in enumerate(parts):
            if isinstance(part, Mapping) and part.get("t") == "tool_call":
                placeholder = None
                if isinstance(placeholders, Mapping) and str(k) in placeholders:
                    placeholder = doc.value(message, f"/ext/agentdojo/placeholder_args/{k}")[1]
                calls.append(_converted_call(doc.value(message, f"/parts/{k}/provider_call_id")[1], part.get("name"),
                                             doc.value(message, f"/parts/{k}/args")[1], placeholder))
        if calls:
            turn["tool_calls"] = calls
        return turn
    if role == "tool":
        part = parts[0] if parts and isinstance(parts[0], Mapping) else {}
        if "tool_call_id" in _ext(message, "agentdojo"):  # the logged id, where the linked call does not give it
            tool_call_id = doc.value(message, "/ext/agentdojo/tool_call_id")[1]
        else:
            call = doc.part(str(part.get("responds_to"))) if "responds_to" in part else None
            tool_call_id = call.get("provider_call_id") if isinstance(call, Mapping) else None
        execution = _execution_of(doc, message)
        if "value" in part and "text" not in part and "/parts/0/value" not in doc.not_inlined(message):
            # a list the mapper kept verbatim (agentdojo.multi_block_tool_content); a text not inlined is _joined's
            try:  # untrusted source JSON, as for unknown_message: the converter rule assumes its types
                content = _split_blocks(doc.value(message, "/parts/0/value")[1], f"message {message.get('id')!s}")[0]
            except (TypeError, ValueError, AttributeError) as exc:
                raise ViewError(f"message {message.get('id')!s}: /parts/0/value has a shape the converter rules "
                                f"cannot render ({type(exc).__name__})") from None
        else:
            _, content = _joined(doc, message, ("tool_result",))
        return {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "function": execution.get("name") if execution is not None else None,
            "args": _args(doc.value(execution, "/args")[1] if execution is not None else None),
            "content": content,
            "content_sha256": _content_digest(content),
            "error": doc.value(message, "/parts/0/error")[1],
            "started_at": TIMING_STUB,
            "ended_at": TIMING_STUB,
        }
    _, content = _joined(doc, message, ("text",))
    return {"role": role, "content": content}


# ------------------------------------------------------------------------------------------------ serialise
def serialise(doc: Mapping[str, Any]) -> bytes:
    """``json.dumps(doc, indent=2)`` with Python defaults (``ensure_ascii=True``), UTF-8, no trailing newline.

    Exactly the baseline writer (``agentdojo_prov/transcript.py:282-283``; J.3.2). ``allow_nan`` stays at its default:
    the strict loader never lets a non-finite number into an AER, and ``decode_value`` restores ``-0.0`` faithfully.
    """
    return json.dumps(doc, indent=2).encode("utf-8")
