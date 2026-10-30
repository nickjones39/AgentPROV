"""Wire-capture redaction (G.6.4; C.13.5): header allowlist with a hard denylist, URL scrubbing, the fail-closed
literal-value scan, and key-shaped patterns that are redacted on non-content surfaces and only flagged in content.

What is covered, in one place (the normative text is C.13.10 and G.6.4):

* **Headers** (:func:`filter_headers`): only allowlisted *values* survive (``redact_allowlist.toml`` plus the
  per-endpoint names of ``endpoints.toml``); the names of dropped headers are reported. The hard denylist
  (``authorization``, ``cookie``, ``x-api-key``, ..., and any name matching ``key|token|secret|auth|cookie|session|
  signature``) wins over every allowlist entry.
* **URLs** (:func:`scrub_url`): scheme, host, port, path and query-parameter *names* are kept; userinfo, query values
  and the fragment are dropped.
* **Literal values** (the :class:`Redactor` scan): every secret value the process holds is searched for in every
  string of every event and in every blob, on content and non-content surfaces alike, and replaced by
  ``"<redacted:secret>"``. A secret is matched in its plain form and in every JSON string spelling of it (each
  character literal or ``\\uXXXX`` in any hex case, ``\\/`` for ``/``, ``\\"``, ``\\\\``, ``\\n``..., surrogate pairs for
  non-BMP characters, mixed freely), and as a whole in percent-encoded form (``%XX`` and ``+``). It is *not* matched
  when transformed otherwise (base64, hex, HTML entities, case changes), when split across strings, or when
  JSON-escaped twice; the final scan of every written line (:meth:`Redactor.check_clean`) catches an escaped
  residue that the first pass missed and then fails closed.
* **Key-shaped patterns** (``sk-...``, ``AIza...``, ``hf_...``, ``gh?_...``, ``xox?-...``, ``AKIA...``, PEM headers)
  are redacted only on non-content surfaces (``NON_CONTENT_MEMBERS``, blobs of traceback/stderr media or flagged
  ``non_content``). In content they are reported as *flags*, never rewritten (benchmark content is evidence).
* The user's **home path** and **host name** are replaced by ``<home>`` and ``<host>`` on non-content surfaces.

Every replacement is reported as ``(location, rule)`` with ``rule`` = ``cap.secret.<kind>@1``; the writer turns these
into the event's ``redactions``. Scanning is fail-closed: any problem raises :class:`RedactionError` and the writer
writes nothing.
"""

from __future__ import annotations

import json
import re
import tomllib
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from functools import cache
from importlib import resources
from typing import Any, Final
from urllib.parse import quote, quote_plus

from .errors import RedactionError
from .events import is_blob_ref

__all__ = [
    "HOME_MARKER",
    "HOST_MARKER",
    "KINDS",
    "MARKER",
    "MIN_SECRET_LENGTH",
    "NON_CONTENT_MEDIA",
    "NON_CONTENT_MEMBERS",
    "NON_CONTENT_NOTE_KINDS",
    "SCRUB_NAME_RE",
    "URL_MARKER",
    "Allowlist",
    "BlobRedaction",
    "EventRedaction",
    "HeaderResult",
    "KeyPattern",
    "Redactor",
    "Secret",
    "filter_headers",
    "is_denied_header",
    "load_allowlist",
    "parse_allowlist",
    "rule_id",
    "scrub_url",
    "secrets_from_environ",
]

MARKER: Final = "<redacted:secret>"
URL_MARKER: Final = "<redacted:url>"
HOME_MARKER: Final = "<home>"
HOST_MARKER: Final = "<host>"

#: The redaction kinds; each is a rule ``cap.secret.<kind>@1`` of the ``cap`` catalogue.
KINDS: Final[tuple[str, ...]] = ("env_value", "file_value", "pattern", "url_component", "home_path", "host_name")

#: Values shorter than this are not scanned for (redacting a 3-character "secret" would destroy evidence); the names
#: of such secrets are exposed as ``Redactor.ignored`` so a caller can refuse to run with them.
MIN_SECRET_LENGTH: Final = 8
#: Pointer entries per (location kind, rule) before a blob's entries collapse to a single ``""`` pointer.
MAX_POINTERS: Final = 64
MAX_DEPTH: Final = 200

#: Event members that are non-content surfaces (exceptions, URLs, paths, runtime strings; G.6.4 table).
NON_CONTENT_MEMBERS: Final[Mapping[str, frozenset[str]]] = {
    "session.start": frozenset({"runtime"}),
    "llm.request": frozenset({"endpoint"}),
    "llm.response": frozenset({"exception", "reason"}),
    "tool.result": frozenset({"exception"}),
    "native.log": frozenset({"path"}),
    "error": frozenset({"where", "exception"}),
}
#: ``note`` kinds whose payload is a non-content surface (headers, environment, stderr, configuration).
NON_CONTENT_NOTE_KINDS: Final = frozenset({"wire_headers", "environment", "stderr", "config"})
#: Blob media types treated as non-content surfaces when the caller does not say (tracebacks, stderr).
NON_CONTENT_MEDIA: Final = frozenset({"text/x-python-traceback", "text/x-stderr"})

#: The K.3.4 scrub pattern for variable NAMES (verbatim).
SCRUB_NAME_RE: Final = re.compile(r"(?i)(api_key|token|secret|base_url|openrouter|anthropic|openai|gemini|hf_)")
#: Names matching the scrub pattern whose values are public configuration, not credentials (validated base URLs have no
#: userinfo or query, G.9.2; model ids are evidence); excluded by :func:`secrets_from_environ`.
_NOT_SECRET_NAME_RE: Final = re.compile(r"(?i)(_base_url|_model|_model_id|_home|_endpoint)$")


def rule_id(kind: str) -> str:
    """``cap.secret.<kind>@1`` for a redaction kind."""
    if kind not in KINDS:
        raise ValueError(f"unknown redaction kind {kind!r}")
    return f"cap.secret.{kind}@1"


# ---------------------------------------------------------------------------------------------------------------
# allowlist data


@dataclass(frozen=True, slots=True)
class KeyPattern:
    """A key-shaped pattern: ``find`` detects it, ``redact`` is what a non-content surface removes."""

    id: str
    find: re.Pattern[str]
    redact: re.Pattern[str]


@dataclass(frozen=True, slots=True)
class Allowlist:
    request_headers: frozenset[str]
    response_headers: frozenset[str]
    deny_names: frozenset[str]
    deny_regex: re.Pattern[str]
    patterns: tuple[KeyPattern, ...]


def _names(table: Mapping[str, Any], key: str) -> frozenset[str]:
    value = table.get(key)
    if not isinstance(value, list) or not all(isinstance(v, str) and v == v.lower() and v for v in value):
        raise RedactionError(f"allowlist: {key!r} must be a list of lower-case names", code="cap.redact.allowlist")
    return frozenset(value)


def parse_allowlist(data: Mapping[str, Any]) -> Allowlist:
    """Validate a parsed ``redact_allowlist.toml`` document (``RedactionError`` ``cap.redact.allowlist``)."""
    if data.get("version") != 1:
        raise RedactionError("allowlist: unsupported version", code="cap.redact.allowlist")
    headers = data.get("headers")
    if not isinstance(headers, Mapping):
        raise RedactionError("allowlist: missing [headers]", code="cap.redact.allowlist")
    deny = headers.get("denylist")
    if not isinstance(deny, Mapping) or not isinstance(deny.get("regex"), str):
        raise RedactionError("allowlist: missing [headers.denylist]", code="cap.redact.allowlist")
    patterns: list[KeyPattern] = []
    table = data.get("patterns", {})
    if not isinstance(table, Mapping):
        raise RedactionError("allowlist: [patterns] must be a table", code="cap.redact.allowlist")
    for pid in sorted(table):
        spec = table[pid]
        if not isinstance(spec, Mapping) or not isinstance(spec.get("regex"), str):
            raise RedactionError(f"allowlist: pattern {pid!r} needs a regex", code="cap.redact.allowlist")
        try:
            find = re.compile(spec["regex"])
            redact = re.compile(spec.get("redact_regex", spec["regex"]))
        except re.error:
            raise RedactionError(f"allowlist: pattern {pid!r} is not a valid regex", code="cap.redact.allowlist") from None
        patterns.append(KeyPattern(pid, find, redact))
    try:
        deny_regex = re.compile(deny["regex"])
    except re.error:
        raise RedactionError("allowlist: denylist regex is invalid", code="cap.redact.allowlist") from None
    return Allowlist(
        request_headers=_names(headers, "request"),
        response_headers=_names(headers, "response"),
        deny_names=_names(deny, "names"),
        deny_regex=deny_regex,
        patterns=tuple(patterns),
    )


@cache
def load_allowlist() -> Allowlist:
    """The packaged ``redact_allowlist.toml`` (read through ``importlib.resources``)."""
    raw = resources.files("agentprov_capture").joinpath("redact_allowlist.toml").read_bytes()
    return parse_allowlist(tomllib.loads(raw.decode("utf-8")))


# ---------------------------------------------------------------------------------------------------------------
# headers and URLs


def is_denied_header(name: str, allowlist: Allowlist | None = None) -> bool:
    """The hard denylist of G.6.4: listed names and any name matching the denylist regular expression."""
    al = allowlist or load_allowlist()
    lowered = name.lower()
    return lowered in al.deny_names or al.deny_regex.search(lowered) is not None


@dataclass(frozen=True, slots=True)
class HeaderResult:
    """``kept``: allowlisted headers (lower-case name -> value). ``dropped``: the names of every other header."""

    kept: dict[str, str]
    dropped: tuple[str, ...]


def filter_headers(
    headers: Mapping[str, str] | Iterable[tuple[str, str]],
    *,
    direction: str,
    endpoint: Any = None,
    allowlist: Allowlist | None = None,
) -> HeaderResult:
    """Keep the values of allowlisted headers only; report the names of the rest (G.6.4).

    ``direction`` is ``"request"`` or ``"response"``. ``endpoint`` is an ``agentprov_capture.endpoints.Endpoint``
    (or its shorthand name) whose declared header names extend the allowlist. The hard denylist wins over both.
    Repeated headers are joined with ``", "``. Values are returned as is; use :meth:`Redactor.filter_headers` to also
    run the literal-value scan over them.
    """
    if direction not in ("request", "response"):
        raise ValueError("direction must be 'request' or 'response'")
    al = allowlist or load_allowlist()
    allowed = set(al.request_headers if direction == "request" else al.response_headers)
    if endpoint is not None:
        if isinstance(endpoint, str):
            from .endpoints import get_endpoint

            endpoint = get_endpoint(endpoint)
        allowed |= set(endpoint.request_headers if direction == "request" else endpoint.response_headers)
    items = headers.items() if isinstance(headers, Mapping) else headers
    values: dict[str, list[str]] = {}
    for name, value in items:
        values.setdefault(str(name).lower(), []).append(str(value))
    kept: dict[str, str] = {}
    dropped: list[str] = []
    for name in sorted(values):
        if name in allowed and not is_denied_header(name, al):
            kept[name] = ", ".join(values[name])
        else:
            dropped.append(name)
    return HeaderResult(kept, tuple(dropped))


_URL_RE: Final = re.compile(
    r"(?P<scheme>[A-Za-z][A-Za-z0-9+.\-]*):(?://(?P<auth>[^/?#]*))?(?P<path>[^?#]*)(?:\?(?P<query>[^#]*))?(?:#(?P<frag>.*))?",
    re.DOTALL,
)
_URL_IN_TEXT: Final = re.compile(r"[A-Za-z][A-Za-z0-9+.\-]{1,15}://[^\s\"'<>\\`]+")
_URL_TRAIL: Final = ".,;:!?)]}"


def scrub_url(url: str) -> str:
    """Keep scheme, host, port, path and query-parameter *names*; drop userinfo, query values and the fragment.

    ``https://u:p@h:8443/p?key=S&alt=x#f`` becomes ``https://h:8443/p?key&alt``. ``ValueError`` if ``url`` is not
    URL-shaped.
    """
    match = _URL_RE.fullmatch(url)
    if match is None:
        raise ValueError("not a URL")
    out = match["scheme"] + ":"
    if match["auth"] is not None:
        out += "//" + match["auth"].rpartition("@")[2]
    out += match["path"]
    if match["query"] is not None:
        names = [part.split("=", 1)[0] for part in match["query"].split("&")]
        names = [n for n in names if n]
        if names:
            out += "?" + "&".join(names)
    return out


def _scrub_urls_in_text(text: str) -> str:
    def repl(match: re.Match[str]) -> str:
        raw = match[0]
        tail = ""
        while raw and raw[-1] in _URL_TRAIL:
            tail = raw[-1] + tail
            raw = raw[:-1]
        try:
            return scrub_url(raw) + tail
        except ValueError:
            return URL_MARKER + tail

    return _URL_IN_TEXT.sub(repl, text)


# ---------------------------------------------------------------------------------------------------------------
# secrets


@dataclass(frozen=True, slots=True)
class Secret:
    """A secret value the process holds. ``name`` is the variable (or key) name; ``kind`` is ``env_value`` (a variable
    passed into the worker) or ``file_value`` (read from ``--env-file`` or ``.env`` by the live CLI entry). The value
    never appears in ``repr`` or ``str`` (G.6.5)."""

    name: str
    value: str
    kind: str = "env_value"

    def __post_init__(self) -> None:
        if self.kind not in ("env_value", "file_value"):
            raise ValueError("a literal secret has kind env_value or file_value")
        if not isinstance(self.value, str):
            raise TypeError("a secret value is a str")

    def __repr__(self) -> str:
        return f"Secret(name={self.name!r}, kind={self.kind!r}, value='***')"

    __str__ = __repr__


def secrets_from_environ(environ: Mapping[str, str], *, kind: str = "env_value") -> list[Secret]:
    """Secrets in ``environ`` by the K.3.4 name pattern (:data:`SCRUB_NAME_RE`), minus names that carry public
    configuration (``*_BASE_URL``, ``*_MODEL``, ``*_MODEL_ID``, ``*_HOME``, ``*_ENDPOINT``). Empty values are skipped."""
    out = []
    for name in sorted(environ):
        value = environ[name]
        if value and SCRUB_NAME_RE.search(name) and not _NOT_SECRET_NAME_RE.search(name):
            out.append(Secret(name, value, kind))
    return out


_HEX_DIGITS: Final = "0123456789abcdefABCDEF"


def _hex_class(ch: str) -> str:
    return f"[{ch.lower()}{ch.upper()}]" if ch.isalpha() else ch


def _unicode_escape(unit: int) -> str:
    return "\\\\u" + "".join(_hex_class(d) for d in f"{unit:04x}")


_SHORT_ESCAPES: Final = {'"': '\\"', "\\": "\\\\", "/": "\\/", "\b": "\\b", "\f": "\\f", "\n": "\\n", "\r": "\\r", "\t": "\\t"}


def _char_regex(ch: str) -> str:
    alts = [re.escape(ch)]
    short = _SHORT_ESCAPES.get(ch)
    if short is not None:
        alts.append(re.escape(short))
    code = ord(ch)
    if code <= 0xFFFF:
        alts.append(_unicode_escape(code))
    else:
        offset = code - 0x10000
        alts.append(_unicode_escape(0xD800 + (offset >> 10)) + _unicode_escape(0xDC00 + (offset & 0x3FF)))
    return "(?:" + "|".join(alts) + ")"


def _percent_regex(encoded: str) -> str:
    parts: list[str] = []
    i = 0
    while i < len(encoded):
        if encoded[i] == "%" and i + 2 < len(encoded) and all(c in _HEX_DIGITS for c in encoded[i + 1 : i + 3]):
            parts.append("%" + _hex_class(encoded[i + 1]) + _hex_class(encoded[i + 2]))
            i += 3
        else:
            parts.append(re.escape(encoded[i]))
            i += 1
    return "".join(parts)


def _secret_regex(value: str) -> str:
    """Regex source matching ``value`` plain, in any JSON string spelling, or percent-encoded as a whole."""
    alts = ["".join(_char_regex(c) for c in value)]
    for encoded in dict.fromkeys((quote(value, safe=""), quote_plus(value))):
        if encoded != value:
            alts.append(_percent_regex(encoded))
    return "(?:" + "|".join(alts) + ")"


class _SecretScanner:
    """One compiled alternation over all scanned secrets (longest first); a single pass, so markers are never rescanned."""

    def __init__(self, secrets: Sequence[Secret]) -> None:
        self._secrets = sorted(secrets, key=lambda s: (-len(s.value), s.name))
        parts = [f"(?P<s{i}>{_secret_regex(s.value)})" for i, s in enumerate(self._secrets)]
        self._re = re.compile("|".join(parts)) if parts else None

    def sub(self, text: str) -> tuple[str, list[str]]:
        if self._re is None:
            return text, []
        kinds: list[str] = []

        def repl(match: re.Match[str]) -> str:
            kinds.append(self._secrets[int(match.lastgroup[1:])].kind)  # type: ignore[index]
            return MARKER

        return self._re.sub(repl, text), kinds

    def contains(self, text: str) -> bool:
        return self._re is not None and self._re.search(text) is not None


# ---------------------------------------------------------------------------------------------------------------
# JSON walking helpers


def _ptr_escape(token: str) -> str:
    return token.replace("~", "~0").replace("/", "~1")


def _iter_strings(root: Any, key_map: Callable[[str], str]) -> Iterator[tuple[str, str]]:
    """Every string (object keys and values) of a parsed JSON document with the JSON Pointer of its place. Pointer
    tokens are ``key_map(key)``: the pointer names the place in the *redacted* document, so it never carries a secret."""
    stack: list[tuple[str, Any, int]] = [("", root, 0)]
    while stack:
        pointer, node, depth = stack.pop()
        if depth > MAX_DEPTH:
            raise RedactionError("document nesting exceeds the redaction limit", code="cap.redact.depth")
        if isinstance(node, str):
            yield pointer, node
        elif isinstance(node, dict):
            for key, value in node.items():
                child = pointer + "/" + _ptr_escape(key_map(key))
                yield child, key
                stack.append((child, value, depth + 1))
        elif isinstance(node, list):
            for index, value in enumerate(node):
                stack.append((f"{pointer}/{index}", value, depth + 1))


@dataclass(frozen=True, slots=True)
class EventRedaction:
    """Redacted ``data`` plus the ``redactions`` entries (``field``/``p``/``rule``) and pattern flags
    (``field``/``p``/``pattern``) found while producing it."""

    data: dict[str, Any]
    redactions: tuple[dict[str, str], ...]
    flags: tuple[dict[str, str], ...]


@dataclass(frozen=True, slots=True)
class BlobRedaction:
    """Redacted blob bytes, ``(p, rule)`` redaction entries and ``(p, pattern id)`` flags."""

    data: bytes
    redactions: tuple[tuple[str, str], ...]
    flags: tuple[tuple[str, str], ...]


class Redactor:
    """The G.6.4 / C.13.5 redactor. Immutable after construction; ``CaptureLog`` applies it fail-closed.

    ``secrets``: the literal values to scan for (see :class:`Secret`, :func:`secrets_from_environ`); values shorter
    than :data:`MIN_SECRET_LENGTH` are not scanned and their names are listed in ``ignored``. ``home`` and ``host``:
    the user's home path and host name, replaced on non-content surfaces only.
    """

    def __init__(
        self,
        secrets: Iterable[Secret] = (),
        *,
        home: str | None = None,
        host: str | None = None,
        allowlist: Allowlist | None = None,
    ) -> None:
        self.allowlist = allowlist or load_allowlist()
        scanned: dict[str, Secret] = {}
        ignored: list[str] = []
        for secret in secrets:
            if len(secret.value) < MIN_SECRET_LENGTH:
                ignored.append(secret.name)
                continue
            if any(m in secret.value or secret.value in m for m in (MARKER, URL_MARKER, HOME_MARKER, HOST_MARKER)):
                raise RedactionError("a secret value overlaps a redaction marker", code="cap.redact.config")
            scanned.setdefault(secret.value, secret)
        self.ignored: tuple[str, ...] = tuple(sorted(ignored))
        self._scanner = _SecretScanner(list(scanned.values()))
        self._n_secrets = len(scanned)
        self._home = re.compile(re.escape(home.rstrip("/\\")) + r"(?![A-Za-z0-9._-])") if home and len(home) > 3 else None
        host_ok = host and len(host) >= 3 and host.lower() not in ("localhost",)
        self._host = (
            re.compile(r"(?<![A-Za-z0-9.-])" + re.escape(host) + r"(?![A-Za-z0-9-])", re.IGNORECASE) if host_ok and host else None
        )

    def __repr__(self) -> str:
        return f"Redactor(secrets={self._n_secrets}, ignored={len(self.ignored)})"

    # -- text -------------------------------------------------------------------------------------------------

    def _transform(self, text: str, non_content: bool) -> tuple[str, list[str]]:
        text, kinds = self._scanner.sub(text)
        if non_content:
            scrubbed = _scrub_urls_in_text(text)
            if scrubbed != text:
                kinds.append("url_component")
                text = scrubbed
            for pattern in self.allowlist.patterns:
                text, n = pattern.redact.subn(MARKER, text)
                if n:
                    kinds.append("pattern")
            if self._home is not None:
                text, n = self._home.subn(HOME_MARKER, text)
                if n:
                    kinds.append("home_path")
            if self._host is not None:
                text, n = self._host.subn(HOST_MARKER, text)
                if n:
                    kinds.append("host_name")
        return text, kinds

    def _find_patterns(self, text: str) -> list[str]:
        return [p.id for p in self.allowlist.patterns if p.find.search(text)]

    def scrub_text(self, text: str, *, non_content: bool = True) -> str:
        """``text`` after the literal scan and, for a non-content surface (the default: stderr, exception strings,
        environment dumps), URL scrubbing, key patterns and home/host replacement."""
        return self._transform(text, non_content)[0]

    def filter_headers(
        self, headers: Mapping[str, str] | Iterable[tuple[str, str]], *, direction: str, endpoint: Any = None
    ) -> HeaderResult:
        """:func:`filter_headers` plus the scan of the kept values (as a non-content surface)."""
        result = filter_headers(headers, direction=direction, endpoint=endpoint, allowlist=self.allowlist)
        return HeaderResult({n: self.scrub_text(v) for n, v in result.kept.items()}, result.dropped)

    def contains_secret(self, data: bytes | str) -> bool:
        """True if any scanned secret occurs in ``data`` in any covered spelling (plain, JSON-escaped, percent-encoded).
        The T0 re-scan of staged files (G.6.4, R-51) uses this; it never returns or logs the match."""
        text = data if isinstance(data, str) else data.decode("utf-8", "surrogateescape")
        return self._scanner.contains(text)

    def check_clean(self, data: bytes) -> None:
        """Final guard over bytes about to be written: raise if any scanned secret survives in any spelling."""
        if self.contains_secret(data):
            raise RedactionError("a secret survived redaction; nothing was written", code="cap.redact.residual")

    # -- events -----------------------------------------------------------------------------------------------

    def redact_event(self, type: str, data: Mapping[str, Any]) -> EventRedaction:  # noqa: A002 - the field is called `type`
        """Redact the ``data`` of an event of the given type. Returns a new dict; the input is not modified."""
        non_members = NON_CONTENT_MEMBERS.get(type, frozenset())
        note_non = type == "note" and data.get("kind") in NON_CONTENT_NOTE_KINDS
        entries: dict[tuple[str, str, str], None] = {}
        flags: dict[tuple[str, str, str], None] = {}
        out: dict[str, Any] = {}
        for key, value in data.items():
            if key == "redactions":
                out[key] = value
                continue
            out[key] = self._walk(value, note_non or key in non_members, key, "", entries, flags, 0)
        return EventRedaction(
            out,
            tuple({"field": f, "p": p, "rule": r} for f, p, r in entries),
            tuple({"field": f, "p": p, "pattern": pid} for f, p, pid in flags),
        )

    def _walk(
        self,
        node: Any,
        non_content: bool,
        field: str,
        pointer: str,
        entries: dict[tuple[str, str, str], None],
        flags: dict[tuple[str, str, str], None],
        depth: int,
    ) -> Any:
        if depth > MAX_DEPTH:
            raise RedactionError("event nesting exceeds the redaction limit", code="cap.redact.depth")
        if isinstance(node, str):
            new, kinds = self._transform(node, non_content)
            for kind in kinds:
                entries.setdefault((field, pointer, rule_id(kind)))
            if not non_content:
                for pid in self._find_patterns(new):
                    flags.setdefault((field, pointer, pid))
            return new
        if isinstance(node, dict):
            if is_blob_ref(node):
                return dict(node)
            out: dict[str, Any] = {}
            for key, value in node.items():
                new_key, kinds = self._transform(key, non_content) if isinstance(key, str) else (key, [])
                if new_key in out:
                    raise RedactionError("redaction made two object keys equal", code="cap.redact.key_collision")
                child = pointer + "/" + _ptr_escape(str(new_key))
                for kind in kinds:
                    entries.setdefault((field, child, rule_id(kind)))
                out[new_key] = self._walk(value, non_content, field, child, entries, flags, depth + 1)
            return out
        if isinstance(node, (list, tuple)):
            return [
                self._walk(item, non_content, field, f"{pointer}/{index}", entries, flags, depth + 1)
                for index, item in enumerate(node)
            ]
        return node

    # -- blobs ------------------------------------------------------------------------------------------------

    def redact_blob(self, data: bytes, media: str, *, non_content: bool | None = None) -> BlobRedaction:
        """Redact blob bytes. JSON media get JSON Pointers for each located string; anything else gets ``""``.

        ``non_content``: ``None`` decides by media (:data:`NON_CONTENT_MEDIA`); ``True`` for a traceback or stderr dump.

        A ``text/event-stream`` body (a streamed model reply, D-656) carries its text in pieces, one per delta event, so
        a value split across two deltas is not contiguous in the bytes. Its delta texts are also joined per content
        block and scanned: a secret found only in the joined text cannot be redacted in place, so the blob is refused
        (``cap.redact.split``; the session ends errored, fail-closed), and a key-shaped pattern found only there is
        flagged at ``""``.
        """
        non = non_content if non_content is not None else media in NON_CONTENT_MEDIA
        text = data.decode("utf-8", "surrogateescape")
        new, kinds = self._transform(text, non)
        found = [] if non else self._find_patterns(new)
        if media.split(";", 1)[0].strip().lower() == "text/event-stream":
            for joined in _sse_joined_texts(new):
                if self._scanner.contains(joined):
                    raise RedactionError("a secret is split across stream events; nothing was written",
                                         code="cap.redact.split")
                if not non:
                    found += [pid for pid in self._find_patterns(joined) if pid not in found]
        if not kinds and not found:
            return BlobRedaction(data, (), ())
        out = new.encode("utf-8", "surrogateescape") if kinds else data
        red: dict[tuple[str, str], None] = {}
        flg: dict[tuple[str, str], None] = {}
        located_kinds: dict[str, set[str]] = {}
        located_flags: dict[str, set[str]] = {}
        parsed: Any = None
        if "json" in media:
            try:
                parsed = json.loads(text)
            except (ValueError, RecursionError):
                parsed = None
        if parsed is not None:
            for pointer, string in _iter_strings(parsed, lambda k: self._transform(k, non)[0]):
                fixed, ks = self._transform(string, non)
                for kind in ks:
                    located_kinds.setdefault(kind, set()).add(pointer)
                if not non:
                    for pid in self._find_patterns(fixed):
                        located_flags.setdefault(pid, set()).add(pointer)
        for kind in dict.fromkeys(kinds):
            pointers = sorted(located_kinds.get(kind, ())) or [""]
            if len(pointers) > MAX_POINTERS:
                pointers = [""]
            for pointer in pointers:
                red.setdefault((pointer, rule_id(kind)))
        for pid in dict.fromkeys(found):
            pointers = sorted(located_flags.get(pid, ())) or [""]
            if len(pointers) > MAX_POINTERS:
                pointers = [""]
            for pointer in pointers:
                flg.setdefault((pointer, pid))
        return BlobRedaction(out, tuple(red), tuple(flg))


_SSE_DELTA_KEYS: Final = ("text", "partial_json", "thinking")
#: An event-stream line: CR, LF or CRLF only (``str.splitlines`` would also split on U+0085, U+2028 and U+2029,
#: which may sit inside a delta's text).
_SSE_LINE: Final = re.compile(r"([^\r\n]*)(?:\r\n|\r|\n|$)")


def _sse_joined_texts(text: str) -> list[str]:
    """The delta texts of an event stream joined per content block index (``content_block_delta`` events' ``text``,
    ``partial_json`` or ``thinking``). Lines end at CR, LF or CRLF only; an event's ``data:`` lines are joined with LF
    and dispatched at a blank line, as the stream format says. Lenient: data that is not JSON of that shape is skipped;
    this is a scan aid over bytes the redactor already scanned whole, never a reading of the stream."""
    pieces: dict[int, list[str]] = {}
    events: list[str] = []
    data: list[str] = []
    for match in _SSE_LINE.finditer(text):
        line = match.group(1)
        if line == "":
            if data:
                events.append("\n".join(data))
            data = []
            if match.end() == len(text):
                break
            continue
        if line.startswith("data:"):
            value = line[5:]
            data.append(value[1:] if value.startswith(" ") else value)
    if data:
        events.append("\n".join(data))
    for raw in events:
        try:
            payload = json.loads(raw)
        except (ValueError, RecursionError):
            continue
        if not isinstance(payload, dict) or payload.get("type") != "content_block_delta":
            continue
        index, delta = payload.get("index"), payload.get("delta")
        if not isinstance(index, int) or not isinstance(delta, dict):
            continue
        for key in _SSE_DELTA_KEYS:
            value = delta.get(key)
            if isinstance(value, str):
                pieces.setdefault(index, []).append(value)
    return ["".join(parts) for parts in pieces.values() if len(parts) > 1]
