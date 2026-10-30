"""Injection-marker normalisers of ``agentdojo.suites@1`` (docs/architecture C.14.3 ``injection_marker``; EF E.7.3).

A normaliser turns a tool output (and a registered payload) into comparable forms. The registry holds three, each a rule
of the ``agentdojo`` catalogue cited as the marker's ``normaliser``:

``agentdojo.yaml_norm@1``
    The AgentDojo-PROV v2.3 marker, ported exactly from the baseline at ``579a908``
    (``agentdojo_prov/build_prov.py`` l. 144-304: ``_SIMPLE_ESCAPES``, ``_ESCAPE``, ``_unescape``, ``_norm_match``,
    ``_content_forms``, ``_REPR_ESCAPE``, ``_PREFIX``, ``_decoded_forms``, ``_norm_payload``, ``payload_marker``). Fast
    forms undo YAML scalar escaping in every reading; when a payload's first 40 characters are visible but no payload
    is, the output is parsed as YAML (through :func:`agentprov.ingest.yamlsafe.safe_load`, the same parser the frozen
    compat port reaches through its shim) and its strings, with Python-repr escapes undone, are searched. v2.3 called
    a YAML parse failure "not present"; here it is a **rejection**.
``agentdojo.pyrepr_norm@1``
    The output read as Python ``repr`` text: string-literal escapes (``\\n``, ``\\'``, ``\\xNN``, ``\\uNNNN``, …) undone,
    whitespace collapsed. Text-level, so it never rejects.
``agentdojo.json_norm@1``
    The output parsed as strict JSON (:func:`agentprov.ingest.loaders.strict_json_loads`, bounded), its strings joined
    and whitespace-collapsed. Rejects anything that is not one JSON document.

:func:`marker_statuses` applies them for one output and every payload (the rule ``agentdojo.injection_marker_yaml@1``):
the YAML normaliser decides; only when it *rejects* (the decoded reading was needed and YAML failed) are the
Python-repr and JSON readings tried, and a payload neither finds is ``ambiguous``
(``agentdojo.injection_marker_ambiguous@1``). ``present`` for some payload therefore holds exactly when v2.3's
``payload_marker`` returned ``True``, except where YAML rejected the output and a fallback reading found the payload
(v2.3: ``False``). Pure functions; no I/O.

``agentdojo.yaml_norm@2`` (``agentdojo.suites@2`` on; regeneration-batch item 8, F-10) is ``yaml_norm@1`` reading only
the escapes YAML or a Python repr defines (``\\'``): any other escape (``\\q``, a short ``\\u12``) keeps its backslash instead of decoding to its letter,
which v2.3 did and which could make a payload ``present`` that differs from the output in that letter. Callers select it
with ``strict=True``. :func:`longest_payload_run` serves item 6 (C3): the longest run of a payload, at least
:data:`PREFIX_CHARS` characters, that an ``absent`` payload shows in the output's readings.

``agentdojo.autodojo_payload_unescape@1`` (``agentdojo.suites@2`` only; regeneration-batch item 1, B1) is not an output
normaliser but a payload-side reading: for a fixture whose AutoDojo cache link holds, the profile also compares the
payload with AutoDojo's ``_yaml_escape`` undone (:func:`autodojo_unescape`) under the same output readings.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Final

from agentprov.errors import IngestError
from agentprov.ingest import yamlsafe
from agentprov.ingest.loaders import strict_json_loads

YAML_NORM: Final = "agentdojo.yaml_norm@1"
YAML_NORM_STRICT: Final = "agentdojo.yaml_norm@2"
AUTODOJO_UNESCAPE: Final = "agentdojo.autodojo_payload_unescape@1"
PYREPR_NORM: Final = "agentdojo.pyrepr_norm@1"
JSON_NORM: Final = "agentdojo.json_norm@1"

#: v2.3 ``_PREFIX`` (``build_prov.py`` l. 238): characters of a payload whose presence triggers the parsed fallback.
PREFIX_CHARS: Final = 40

# ---------------------------------------------------------------------------------------------- v2.3 port (yaml_norm)
# build_prov.py l. 148-164 (579a908): YAML's single-character escapes and one double-quoted escape.
_SIMPLE_ESCAPES: Final = {
    "0": "\x00", "a": "\x07", "b": "\x08", "t": "\t", "n": "\n", "v": "\x0b", "f": "\x0c",
    "r": "\r", "e": "\x1b", "N": "\x85", "_": "\xa0", "L": "\u2028", "P": "\u2029",
}
_ESCAPE: Final = re.compile(
    r"\\(?:(\n[ \t]*)|(u[0-9a-fA-F]{4}|x[0-9a-fA-F]{2}|U[0-9a-fA-F]{8}|.))", re.DOTALL)
_WS: Final = re.compile(r"\s+")
# build_prov.py l. 237
_REPR_ESCAPE: Final = re.compile(r"\\([ntr'\"\\])")


def _unescape(m: re.Match[str]) -> str:
    if m.group(1) is not None:  # ``\`` + newline + indent: a fold
        return ""
    e = m.group(2)
    if len(e) > 1:  # \uXXXX, \xXX, \UXXXXXXXX
        code = int(e[1:], 16)
        return chr(code) if code <= 0x10FFFF else m.group(0)
    return _SIMPLE_ESCAPES.get(e, e)


#: The single-character escapes ``yaml_norm@2`` reads: YAML's (YAML 1.1 double-quoted scalars: the simple ones plus space,
#: ``"``, ``/``, ``\\`` and tab) and Python's ``\\'`` (the outputs the readings serve include Python reprs, examination 2
#: A05; without it the strict reading lost real payloads behind an escaped apostrophe). With the ``\\x``/``\\u``/``\\U``
#: hex forms and line folding.
_YAML_SINGLE: Final = frozenset(_SIMPLE_ESCAPES) | {" ", '"', "/", "\\", "\t", "'"}


def _unescape_strict(m: re.Match[str]) -> str:
    """``yaml_norm@2``: as :func:`_unescape`, but an escape neither YAML nor a Python repr defines keeps its backslash
    (F-10)."""
    if m.group(1) is not None:
        return ""
    e = m.group(2)
    if len(e) > 1:
        code = int(e[1:], 16)
        return chr(code) if code <= 0x10FFFF else m.group(0)
    if e in _SIMPLE_ESCAPES:
        return _SIMPLE_ESCAPES[e]
    return e if e in _YAML_SINGLE else m.group(0)


def _norm_match(s: str, undouble: bool = True, levels: int = 1, strict: bool = False) -> str:
    """build_prov.py l. 167-209: undo YAML escapes (``levels`` times), un-double ``''``, collapse whitespace."""
    for _ in range(levels):
        s = _ESCAPE.sub(_unescape_strict if strict else _unescape, s)
    if undouble:
        s = s.replace("''", "'")
    return _WS.sub(" ", s).strip()


def norm_payload(s: str) -> str:
    """build_prov.py l. 272-285 ``_norm_payload``: the payload side, whitespace collapsed and nothing else."""
    return _WS.sub(" ", s).strip()


def content_forms(content: str, strict: bool = False) -> tuple[str, ...]:
    """build_prov.py l. 212-234 ``_content_forms``: the content in every reading of its escaping (``strict``:
    ``yaml_norm@2``)."""
    a, b = _norm_match(content, strict=strict), _norm_match(content, undouble=False, strict=strict)
    a2 = _norm_match(content, levels=2, strict=strict)
    b2 = _norm_match(content, undouble=False, levels=2, strict=strict)
    raw = norm_payload(content)
    return tuple(dict.fromkeys((a, b, a2, b2, raw, raw.replace("''", "'"))))


class Rejected(Exception):
    """A normaliser could not read the output in its format (C.14.3: the marker is then ``ambiguous``)."""


def _strings(doc: Any) -> list[str]:
    """build_prov.py l. 256-267 ``walk``: the strings of a parsed document, dict values and list items in order."""
    parts: list[str] = []
    stack: list[Any] = [doc]
    while stack:  # iterative, same order as the recursive walk
        x = stack.pop()
        if isinstance(x, str):
            parts.append(x)
        elif isinstance(x, dict):
            stack.extend(reversed(list(x.values())))
        elif isinstance(x, list):
            stack.extend(reversed(x))
    return parts


def yaml_decoded_form(content: str) -> str:
    """build_prov.py l. 241-269 ``_decoded_forms``: YAML-parsed strings with repr escapes undone, normalised.

    :class:`Rejected` where v2.3 returned ``()`` (any parse failure, including the bounded parser's guards).
    """
    try:
        doc = yamlsafe.safe_load(content)
    except Exception as exc:  # noqa: BLE001 - v2.3 ``except Exception``: not YAML
        raise Rejected(type(exc).__name__) from None
    joined = " ".join(_strings(doc))
    return norm_payload(_REPR_ESCAPE.sub(lambda m: {"n": " ", "t": " ", "r": " "}.get(m.group(1), m.group(1)), joined))


_AUTODOJO_ESCAPE: Final = re.compile(r'\\([\\"nt])')
_AUTODOJO_SIMPLE: Final = {"\\": "\\", '"': '"', "n": "\n", "t": "\t"}


def autodojo_unescape(payload: str) -> str:
    """The inverse of AutoDojo's ``_yaml_escape`` (``hooks.autodojo.yaml_escape``: backslash, then ``"``, newline and
    tab), read left to right; exact on the escape's image, which a linked payload is (``cache_match``)."""
    return _AUTODOJO_ESCAPE.sub(lambda m: _AUTODOJO_SIMPLE[m.group(1)], payload)


# ---------------------------------------------------------------------------------------------- fallback readings
_PY_ESCAPE: Final = re.compile(r"\\(x[0-9a-fA-F]{2}|u[0-9a-fA-F]{4}|U[0-9a-fA-F]{8}|[0-7]{1,3}|.)", re.DOTALL)
_PY_SIMPLE: Final = {"\n": "", "\\": "\\", "'": "'", '"': '"', "a": "\x07", "b": "\x08", "f": "\x0c", "n": "\n",
                     "r": "\r", "t": "\t", "v": "\x0b"}


def _py_unescape(m: re.Match[str]) -> str:
    e = m.group(1)
    if e[0] in "xuU" and len(e) > 1:
        code = int(e[1:], 16)
        return chr(code) if code <= 0x10FFFF else m.group(0)
    if e[0] in "01234567":
        return chr(int(e, 8))
    return _PY_SIMPLE.get(e, m.group(0))  # an unknown escape keeps its backslash, as Python does


def pyrepr_form(content: str) -> str:
    """``agentdojo.pyrepr_norm@1``: Python string-literal escapes undone, whitespace collapsed. Never rejects."""
    return norm_payload(_PY_ESCAPE.sub(_py_unescape, content))


def json_form(content: str) -> str:
    """``agentdojo.json_norm@1``: strict JSON (bounded), strings joined and whitespace-collapsed; :class:`Rejected`."""
    try:
        doc = strict_json_loads(content.encode("utf-8", "surrogatepass"))
    except (IngestError, UnicodeError) as exc:
        raise Rejected(type(exc).__name__) from None
    return norm_payload(" ".join(_strings(doc)))


#: The fallback readings, in the order they are tried after a YAML rejection.
FALLBACKS: Final[tuple[tuple[str, Callable[[str], str]], ...]] = ((PYREPR_NORM, pyrepr_form), (JSON_NORM, json_form))
#: The registry: every normaliser this profile may cite (version 1), and per profile version (item 8: ``@2`` strict).
NORMALISERS: Final = (YAML_NORM, PYREPR_NORM, JSON_NORM)
NORMALISERS_OF: Final = {1: NORMALISERS, 2: (YAML_NORM_STRICT, PYREPR_NORM, JSON_NORM)}


# ---------------------------------------------------------------------------------------------- statuses
@dataclass(frozen=True, slots=True)
class MarkerResult:
    """The marker of one (output, payload) pair: ``status`` and the normaliser that decided it."""

    status: str  # present | absent | ambiguous | gap
    normaliser: str


def marker_statuses(content: str, payloads: Sequence[str | None], strict: bool = False) -> list[MarkerResult]:
    """The marker status of ``content`` for each registered payload (``None`` or empty: ``gap``).

    Exactly v2.3's ``payload_marker`` (build_prov.py l. 288-304) per payload: present if the normalised payload occurs
    in a fast form; else, when **any** payload's first :data:`PREFIX_CHARS` characters occur in a fast form (v2.3's
    cell-level trigger), present iff it occurs in the YAML-decoded form; else absent. A YAML rejection on that path
    tries :data:`FALLBACKS`; a payload no reading finds is ``ambiguous``. ``strict`` reads the fast forms with
    ``yaml_norm@2`` and cites it (item 8).
    """
    yaml_rule = YAML_NORM_STRICT if strict else YAML_NORM
    norms = [norm_payload(p) if isinstance(p, str) else "" for p in payloads]
    live = [n for n in norms if n]
    forms = content_forms(content, strict)
    triggered = any(n[:PREFIX_CHARS] in c for n in live for c in forms)
    decoded: str | None = None
    rejected = False
    if triggered and not all(any(n in c for c in forms) for n in live):
        try:
            decoded = yaml_decoded_form(content)
        except Rejected:
            rejected = True
    fallback_forms: list[tuple[str, str]] = []
    if rejected:
        for name, fn in FALLBACKS:
            try:
                fallback_forms.append((name, fn(content)))
            except Rejected:
                continue
    out: list[MarkerResult] = []
    for n in norms:
        if not n:
            out.append(MarkerResult("gap", yaml_rule))
        elif any(n in c for c in forms):
            out.append(MarkerResult("present", yaml_rule))
        elif not triggered:
            out.append(MarkerResult("absent", yaml_rule))
        elif decoded is not None:
            out.append(MarkerResult("present" if n in decoded else "absent", yaml_rule))
        else:
            found = next((name for name, form in fallback_forms if n in form), None)
            out.append(MarkerResult("present", found) if found else MarkerResult("ambiguous", yaml_rule))
    return out


def longest_payload_run(content: str, payload: str, strict: bool = False) -> int | None:
    """Item 6 (C3): the length of the longest run of the normalised ``payload`` that occurs in a fast form of
    ``content``, when it is at least :data:`PREFIX_CHARS` characters; else ``None``.

    Exact and linear in practice: any common run of length ``L >= 2k`` contains a payload window of ``k + 1`` characters
    starting at a multiple of ``k`` (``k = PREFIX_CHARS // 2``); each window's occurrences are extended both ways."""
    n = norm_payload(payload)
    if len(n) < PREFIX_CHARS:
        return None
    k = PREFIX_CHARS // 2
    best = 0
    for form in content_forms(content, strict):
        for start in range(0, len(n) - k, k):
            window = n[start:start + k + 1]
            at = form.find(window)
            while at >= 0:
                left = 0
                while start - left > 0 and at - left > 0 and n[start - left - 1] == form[at - left - 1]:
                    left += 1
                right = k + 1
                while start + right < len(n) and at + right < len(form) and n[start + right] == form[at + right]:
                    right += 1
                best = max(best, left + right)
                at = form.find(window, at + 1)
    return best if best >= PREFIX_CHARS else None


def payload_span(text: str, payload: str) -> tuple[int, int] | None:
    """Where ``payload`` stands in ``text`` (half-open, in code points = Unicode scalar values of an AER string).

    The first verbatim occurrence; else the first occurrence that differs from the payload only in whitespace runs
    (``\\s+`` between the payload's whitespace-separated tokens, so the span covers original text whose whitespace
    collapse equals the normalised payload); else ``None`` (found only in an escape-decoded reading, whose offsets do not
    map back to the text).
    """
    if not payload:
        return None
    start = text.find(payload)
    if start >= 0:
        return start, start + len(payload)
    tokens = payload.split()
    if not tokens:
        return None
    match = re.search(r"\s+".join(re.escape(t) for t in tokens), text)
    return (match.start(), match.end()) if match else None
