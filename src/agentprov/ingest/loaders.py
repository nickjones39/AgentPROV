"""Strict JSON and JSONL loaders for untrusted bytes (docs/architecture G.3.3; A2; K.5.6).

* :func:`strict_json_loads` takes **bytes**, never ``str``: it enforces a byte cap, rejects a BOM, decodes strictly as
  UTF-8 (no UTF-16/32 auto-detection), pre-scans the nesting depth without recursion, rejects duplicate keys,
  ``NaN``/``Infinity`` and overflowing floats, caps integer digit counts before ``int()`` runs, and re-checks depth with an
  iterative walk. Every violation is an :class:`~agentprov.errors.IngestError` with a closed ``ingest.*`` code.
* :func:`iter_jsonl` reads a binary stream, splits on LF (0x0A) only, caps each line, and yields
  ``(line_no, byte_offset, value)`` with a 0-based ``line_no``. ``str.splitlines()`` and text-mode reading are never
  used (they split on U+2028, U+2029, U+0085 and bare CR).

The parse MUST run in the worker's main thread: CPython's recursion and stack behaviour differs in threads (G.3.3 rule 6).

Depth is the maximum container nesting: ``[[]]`` has depth 2 and a scalar has depth 0. Depth 256 is accepted and 257 is
rejected (``max_json_depth``).
"""

from __future__ import annotations

import dataclasses
import json
import math
import re
from collections.abc import Iterator
from typing import IO, Any, Final

from agentprov.errors import IngestError, IngestFinding, Severity
from agentprov.ingest.limits import IngestLimits

PROFILE_STRICT: Final = "strict"
PROFILE_LENIENT_BOM: Final = "lenient-bom"
PROFILE_PYTHON_JSON: Final = "python-json"
JSON_PROFILES: Final = (PROFILE_STRICT, PROFILE_LENIENT_BOM, PROFILE_PYTHON_JSON)

#: JSONL profiles. ``strict`` rejects CRLF, blank lines and a BOM; ``lenient`` strips CR and BOM and skips blank lines,
#: recording a finding each time; ``python-json`` is ``strict`` framing with the ``python-json`` number profile.
JSONL_PROFILES: Final = (PROFILE_STRICT, "lenient", PROFILE_PYTHON_JSON)

_BOM: Final = b"\xef\xbb\xbf"
_CHUNK: Final = 64 * 1024
_NONFINITE_NAMES: Final = {"NaN": "NaN", "Infinity": "Infinity", "-Infinity": "-Infinity"}

# Strings are skipped; brackets are structural; a quote that opens no complete string stops the scan (the document is
# not valid JSON, and the parser rejects it without recursing past what was counted).
_TOKEN: Final = re.compile(rb'"[^"\\]*(?:\\.[^"\\]*)*"|([\[\]{}])|(")', re.DOTALL)
_SURROGATE_ESCAPE: Final = re.compile(rb"\\u[dD][89a-fA-F]")
#: D-412: skip the depth prescan and walk where a byte count proves they cannot raise (see strict_json_loads). False
#: restores the unconditional checks; the differential tests compare the two.
_DEPTH_FAST_PATH = True
#: D-416: the G.3.2 defaults, built once (IngestLimits is frozen) instead of on every call without ``limits``.
_DEFAULT_LIMITS: Final = IngestLimits()


def _prescan_depth(data: bytes, max_depth: int) -> None:
    """Byte-level depth pre-scan: tracks string and escape state, never recurses (G.3.3 rule 4)."""
    depth = 0
    for m in _TOKEN.finditer(data):
        bracket = m.group(1)
        if bracket is None:
            if m.group(2) is not None:
                return  # unterminated string: not valid JSON, `json.loads` rejects it
            continue
        if bracket in (b"[", b"{"):
            depth += 1
            if depth > max_depth:
                raise IngestError(
                    "ingest.json.depth", "nesting exceeds the depth limit", offset=m.start(), limit=max_depth
                )
        else:
            depth -= 1


def _walk(root: Any, max_depth: int, *, check_surrogates: bool) -> int:
    """Iterative depth check (no recursion, G.3.3 rule 7). Returns the number of strings with a lone surrogate."""
    lone = 0
    stack: list[tuple[Any, int]] = [(root, 0)]
    while stack:
        node, depth = stack.pop()
        if isinstance(node, dict):
            children: Any = node.values()
            if check_surrogates:
                lone += sum(_has_lone_surrogate(key) for key in node)
        elif isinstance(node, list):
            children = node
        else:
            continue
        depth += 1
        if depth > max_depth:
            raise IngestError("ingest.json.depth", "nesting exceeds the depth limit", limit=max_depth)
        for child in children:
            if isinstance(child, dict | list):
                stack.append((child, depth))
            elif check_surrogates and isinstance(child, str):
                lone += _has_lone_surrogate(child)
    return lone


def _has_lone_surrogate(text: str) -> int:
    if text.isascii():
        return 0
    try:
        text.encode("utf-8")
    except UnicodeEncodeError:
        return 1
    return 0


def _no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise IngestError("ingest.json.duplicate_key", "duplicate object key")
        out[key] = value
    return out


def strict_json_loads(
    data: bytes,
    limits: IngestLimits | None = None,
    *,
    profile: str = PROFILE_STRICT,
    record: bool = False,
    findings: list[IngestFinding] | None = None,
    nonfinite_objects: list[Any] | None = None,
) -> Any:
    """Parse one JSON document from untrusted ``data`` (G.3.3).

    ``nonfinite_objects`` (``python-json`` profile only): when a list is given, every ``{"$float": ...}`` object the
    profile makes of a non-finite constant is appended to it, so that a caller can tell those objects, by identity, from
    one-key ``{"$float": ...}`` objects that are literally in the source (RH-1 review R2-3).

    ``profile`` is ``strict`` (default), ``lenient-bom`` (strips a UTF-8 BOM and records a finding) or ``python-json``
    (maps ``NaN``/``Infinity``/``-Infinity`` to ``{"$float": ...}`` and records a finding, C.11.3). ``record=True`` bounds
    the document by ``max_jsonl_line_bytes`` and reports ``ingest.size.record`` instead of ``max_json_bytes`` and
    ``ingest.size.file``. Findings (an escaped lone surrogate, the stripped BOM, mapped constants) are appended to
    ``findings`` when a list is given; they never reject.

    Raises :class:`~agentprov.errors.IngestError` with a closed code and nothing else.
    """
    if not isinstance(data, bytes | bytearray | memoryview):
        raise TypeError("strict_json_loads takes bytes: decode nothing before the loader runs")
    if profile not in JSON_PROFILES:
        raise ValueError(f"unknown JSON profile: {profile!r}")
    limits = limits or _DEFAULT_LIMITS
    data = bytes(data)

    cap = limits.max_jsonl_line_bytes if record else limits.max_json_bytes
    if len(data) > cap:
        raise IngestError(
            "ingest.size.record" if record else "ingest.size.file",
            f"document of {len(data)} bytes exceeds the limit",
            limit=cap,
        )
    sink: list[IngestFinding] = findings if findings is not None else []

    if data.startswith(_BOM):
        if profile != PROFILE_LENIENT_BOM:
            raise IngestError("ingest.json.bom", "UTF-8 byte order mark", offset=0)
        data = data[len(_BOM) :]
        sink.append(IngestFinding("ingest.json.bom", "warning", offset=0, detail="UTF-8 BOM stripped"))

    if (len(data) >= 1 and data[0] == 0) or (len(data) >= 2 and data[1] == 0):
        # Valid JSON never has NUL as one of its first two bytes: this is UTF-16 or UTF-32 (RFC 4627 sec. 3 sniff).
        raise IngestError("ingest.json.encoding", "UTF-16 or UTF-32 input", offset=0)
    try:
        text = data.decode("utf-8")  # strict; bytes only, so `json` never auto-detects UTF-16/32
    except UnicodeDecodeError as exc:
        raise IngestError("ingest.json.encoding", "invalid UTF-8", offset=exc.start) from None

    # D-412: depth fast path. The prescan's counter rises only on structural '[' or '{' bytes, each at its own offset, so
    # it never exceeds k, the count of every '[' and '{' byte (inside strings too; a UTF-8 continuation byte is >= 0x80).
    # With k <= max_json_depth the prescan cannot raise and is skipped. The walk below is bounded the same way, except
    # that parse_constant builds a one-level {"$float": ...} dict from no bracket byte (profile python-json): that adds 1.
    # The bound holds only while no parse hook builds any other container.
    brackets = data.count(b"[") + data.count(b"{")
    fast = _DEPTH_FAST_PATH
    if not fast or brackets > limits.max_json_depth:
        _prescan_depth(data, limits.max_json_depth)

    max_digits = limits.max_int_digits
    mapped: list[str] = []

    def parse_int(literal: str) -> int:
        if len(literal) - (literal[0] == "-") > max_digits:
            raise IngestError("ingest.number.digits", "integer literal has too many digits", limit=max_digits)
        try:
            return int(literal)
        except ValueError:  # only if max_int_digits was raised above CPython's own int/str limit
            raise IngestError("ingest.number.digits", "integer literal too long to convert", limit=max_digits) from None

    def parse_float(literal: str) -> float:
        value = float(literal)
        if not math.isfinite(value):
            raise IngestError("ingest.number.nonfinite", "float literal overflows")
        return value

    python_json = profile == PROFILE_PYTHON_JSON

    def parse_constant(name: str) -> Any:
        if not python_json:
            raise IngestError("ingest.number.nonfinite", "NaN or Infinity literal")
        mapped.append(name)
        made = {"$float": _NONFINITE_NAMES[name]}
        if nonfinite_objects is not None:
            nonfinite_objects.append(made)
        return made

    try:
        value = json.loads(
            text,
            object_pairs_hook=_no_duplicates,
            parse_constant=parse_constant,
            parse_float=parse_float,
            parse_int=parse_int,
        )
    except json.JSONDecodeError as exc:
        raise IngestError("ingest.json.syntax", "malformed JSON", offset=exc.pos) from None
    except RecursionError:
        raise IngestError("ingest.json.depth", "parser stack exhausted", limit=limits.max_json_depth) from None

    check_surrogates = _SURROGATE_ESCAPE.search(data) is not None
    lone = 0
    if not fast or check_surrogates or brackets + (1 if mapped else 0) > limits.max_json_depth:
        lone = _walk(value, limits.max_json_depth, check_surrogates=check_surrogates)
    if check_surrogates and isinstance(value, str):
        lone += _has_lone_surrogate(value)
    if lone:
        sink.append(
            IngestFinding(
                "ingest.json.lone_surrogate", "info", detail=f"{lone} string(s) with an escaped lone surrogate"
            )
        )
    if mapped:
        sink.append(
            IngestFinding(
                "ingest.number.nonfinite", "warning", detail=f"{len(mapped)} non-finite constant(s) mapped to $float"
            )
        )
    return value


# --------------------------------------------------------------------------------------------------------------
# JSONL
# --------------------------------------------------------------------------------------------------------------


def _read_line(fp: IO[bytes], max_line: int) -> tuple[bytes, int, bool]:
    """Read one LF-terminated line without ever holding more than ``max_line + 1`` bytes.

    Returns ``(line, consumed, too_long)`` where ``line`` is the line including its LF (empty at EOF) and ``consumed``
    the number of bytes taken from the stream. A line longer than ``max_line`` (not counting its LF) comes back with
    ``too_long=True``, and the rest of it is read and discarded in bounded chunks.
    """
    raw = fp.readline(max_line + 1)
    if not isinstance(raw, bytes):
        raise TypeError("iter_jsonl needs a binary stream")
    consumed = len(raw)
    if len(raw) > max_line and not raw.endswith(b"\n"):
        tail = raw
        while tail and not tail.endswith(b"\n"):
            tail = fp.readline(_CHUNK)
            consumed += len(tail)
        return raw, consumed, True
    return raw, consumed, False


def _json_profile_for(profile: str) -> str:
    return {PROFILE_STRICT: PROFILE_STRICT, "lenient": PROFILE_LENIENT_BOM, PROFILE_PYTHON_JSON: PROFILE_PYTHON_JSON}[
        profile
    ]


def scan_jsonl(
    fp: IO[bytes],
    limits: IngestLimits | None = None,
    *,
    profile: str = PROFILE_STRICT,
) -> Iterator[tuple[int, int, Any, tuple[IngestFinding, ...]]]:
    """Frame and parse a JSONL stream, reporting per-line issues instead of raising (G.3.3; D.2.8).

    Yields ``(line_no, byte_offset, value, findings)`` for every line. ``value`` is parsed JSON, or the sentinel
    :data:`NO_VALUE` when the line was rejected or is blank. ``findings`` holds every issue of that line (severity
    ``error`` means the line was rejected). Lines after a bad line are still processed. The stream is read in binary mode
    and split on LF only.
    """
    if profile not in JSONL_PROFILES:
        raise ValueError(f"unknown JSONL profile: {profile!r}")
    limits = limits or _DEFAULT_LIMITS
    lenient = profile == "lenient"
    json_profile = _json_profile_for(profile)
    max_line = limits.max_jsonl_line_bytes
    offset = 0
    line_no = 0
    while True:
        raw, consumed, too_long = _read_line(fp, max_line)
        if not raw:
            return
        start = offset
        offset += consumed
        yield (line_no, start, *_parse_line(raw, too_long, line_no, start, limits, lenient, json_profile))
        line_no += 1


def _parse_line(
    raw: bytes,
    too_long: bool,
    line_no: int,
    start: int,
    limits: IngestLimits,
    lenient: bool,
    json_profile: str,
) -> tuple[Any, tuple[IngestFinding, ...]]:
    issues: list[IngestFinding] = []

    def note(code: str, severity: Severity, detail: str) -> None:
        issues.append(IngestFinding(code, severity, line_no, start, detail))

    if too_long:
        note("ingest.jsonl.line_too_long", "error", f"line exceeds {limits.max_jsonl_line_bytes} bytes")
        return NO_VALUE, tuple(issues)

    has_lf = raw.endswith(b"\n")
    body = raw[:-1] if has_lf else raw
    if not has_lf:
        note("ingest.jsonl.no_final_newline", "warning", "missing final newline")
    rejected = False
    if b"\x00" in body:
        note("ingest.jsonl.nul", "error", "NUL byte in line")
        rejected = True
    if line_no == 0 and body.startswith(_BOM):
        if lenient:
            note("ingest.json.bom", "warning", "UTF-8 BOM stripped")
            body = body[len(_BOM) :]
        else:
            note("ingest.json.bom", "error", "UTF-8 byte order mark")
            rejected = True
    if body.endswith(b"\r"):
        if lenient:
            note("ingest.jsonl.crlf", "warning", "CRLF line ending stripped")
            body = body[:-1]
        else:
            note("ingest.jsonl.crlf", "error", "CRLF line ending")
            rejected = True
    if not body.strip(b" \t\r"):
        note("ingest.jsonl.blank", "warning" if lenient else "error", "blank line")
        return NO_VALUE, tuple(issues)
    if rejected:
        return NO_VALUE, tuple(issues)

    found: list[IngestFinding] = []
    try:
        value = strict_json_loads(body, limits, profile=json_profile, record=True, findings=found)
    except IngestError as exc:
        issues.append(IngestFinding(exc.code, "error", line_no, start, exc.reason))
        return NO_VALUE, tuple(issues)
    issues.extend(dataclasses.replace(f, line=line_no, offset=start) for f in found)
    return value, tuple(issues)


class _NoValue:
    __slots__ = ()

    def __repr__(self) -> str:
        return "NO_VALUE"

    def __bool__(self) -> bool:
        return False


#: Marker for a JSONL line that produced no value (rejected or blank).
NO_VALUE: Final = _NoValue()


def iter_jsonl(
    fp: IO[bytes],
    limits: IngestLimits | None = None,
    *,
    profile: str = PROFILE_STRICT,
    issues: list[IngestFinding] | None = None,
) -> Iterator[tuple[int, int, Any]]:
    """Yield ``(line_no, byte_offset, value)`` for every parsed line of a binary JSONL stream (G.3.3; K.5.6).

    ``line_no`` is 0-based and ``byte_offset`` is the offset of the start of the line. With an ``issues`` list, every
    finding is appended and bad lines are skipped, so the remaining lines are still mapped (D.2.8). Without it the
    iterator fails closed: the first finding of severity ``warning`` or ``error`` raises its
    :class:`~agentprov.errors.IngestError` (with ``line`` and ``offset``), so nothing is silently accepted.
    """
    for line_no, start, value, found in scan_jsonl(fp, limits, profile=profile):
        if issues is not None:
            issues.extend(found)
        else:
            for finding in found:
                if finding.severity != "info":
                    raise finding.to_error()
        if value is not NO_VALUE:
            yield line_no, start, value

