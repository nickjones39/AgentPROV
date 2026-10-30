# ruff: noqa: B007, B905, UP031  (analysis script, committed as run; style-only)
"""Independent checkers for examination 2 (read-only; no corpus writes).

Everything here is written independently of the code under test:

* ``strict_parse``: stdlib ``json`` with hooks (duplicate keys, ``NaN``/``Infinity``, float overflow, integers beyond
  the I-JSON range, lone surrogates), strict UTF-8 decoding and a BOM check. It does not call
  ``agentprov.ingest.loaders``.
* ``jcs``: a second RFC 8785 serialiser (own ECMAScript number formatting, own UTF-16 key order, own string escaping).
  It does not call ``rfc8785`` or ``agentprov.io.canonical``.
* the string-content patterns of research brief A4 Part 3 (decoded-string regexes, byte prefilters);
* PROV graph helpers (formal arguments per relation, event-graph construction, Tarjan SCC).

No function prints corpus text. Exemplars are recorded as (execution id, normalised pointer, sha256 prefix).
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from typing import Any

I_JSON_MAX = 2**53 - 1


# ============================================================================================ strict parse (X01)
class StrictError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _const(name: str) -> Any:
    raise StrictError("nonfinite_constant")


def make_parser(flags: Counter) -> Any:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        d = dict(items)
        if len(d) != len(items):
            raise StrictError("duplicate_key")
        return d

    def pfloat(s: str) -> float:
        v = float(s)
        if math.isinf(v):
            raise StrictError("float_overflow")
        if v == 0.0 and s.lstrip().startswith("-"):
            flags["neg_zero_float_token"] += 1
        return v

    def pint(s: str) -> int:
        v = int(s)
        if v > I_JSON_MAX or v < -I_JSON_MAX:
            flags["int_beyond_ijson"] += 1
        if s.startswith("-") and v == 0:
            flags["neg_zero_int_token"] += 1
        return v

    def parse(text: str) -> Any:
        return json.loads(text, object_pairs_hook=pairs, parse_constant=_const, parse_float=pfloat, parse_int=pint)

    return parse


def strict_parse(data: bytes, flags: Counter) -> Any:
    """Parse one JSON text strictly; raise StrictError with a code. ``flags`` collects non-fatal observations."""
    if data.startswith(b"\xef\xbb\xbf"):
        raise StrictError("bom")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        raise StrictError("utf8_invalid") from None
    try:
        return make_parser(flags)(text)
    except StrictError:
        raise
    except RecursionError:
        raise StrictError("too_deep") from None
    except ValueError as exc:
        msg = str(exc)
        if "Extra data" in msg:
            raise StrictError("trailing_data") from None
        if "Invalid control character" in msg:
            raise StrictError("raw_control_char") from None
        raise StrictError("json_syntax") from None


# ============================================================================================ second JCS (X02)
_ESC_RE = re.compile(r'[\x00-\x1f"\\]')
_SHORT = {'"': '\\"', "\\": "\\\\", "\b": "\\b", "\f": "\\f", "\n": "\\n", "\r": "\\r", "\t": "\\t"}


def _esc(m: re.Match[str]) -> str:
    c = m.group()
    return _SHORT.get(c) or "\\u%04x" % ord(c)


class JcsError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def es_number(x: float) -> str:
    """ECMAScript Number::toString for a finite double (RFC 8785 section 3.2.2.3), written from the ES spec."""
    if x != x or x in (math.inf, -math.inf):
        raise JcsError("nonfinite")
    if x == 0:
        return "0"
    sign = "-" if x < 0 else ""
    r = repr(abs(x))  # shortest round-trip digits (correctly rounded, like ES)
    if "e" in r:
        mant, exp_s = r.split("e")
        exp = int(exp_s)
    else:
        mant, exp = r, 0
    if "." in mant:
        ip, fp = mant.split(".")
    else:
        ip, fp = mant, ""
    digits = ip + fp
    point = len(ip) + exp
    stripped = digits.lstrip("0")
    point -= len(digits) - len(stripped)
    digits = stripped.rstrip("0") or "0"
    k, n = len(digits), point
    if k <= n <= 21:
        s = digits + "0" * (n - k)
    elif 0 < n <= 21:
        s = digits[:n] + "." + digits[n:]
    elif -6 < n <= 0:
        s = "0." + "0" * (-n) + digits
    else:
        e = n - 1
        es = ("+" if e >= 0 else "-") + str(abs(e))
        s = digits + "e" + es if k == 1 else digits[0] + "." + digits[1:] + "e" + es
    return sign + s


def _u16(k: str) -> bytes:
    return k.encode("utf-16-be", "surrogatepass")


def jcs(value: Any, stats: Counter | None = None) -> bytes:
    """RFC 8785 bytes of ``value`` (a parsed JSON tree), independent implementation. Raises JcsError."""
    out: list[str] = []
    _emit(value, out, stats)
    try:
        return "".join(out).encode("utf-8")
    except UnicodeEncodeError:
        raise JcsError("lone_surrogate") from None


def _emit(v: Any, out: list[str], stats: Counter | None) -> None:
    if v is None:
        out.append("null")
    elif v is True:
        out.append("true")
    elif v is False:
        out.append("false")
    elif isinstance(v, str):
        out.append('"' + _ESC_RE.sub(_esc, v) + '"')
    elif isinstance(v, int):
        if v > I_JSON_MAX or v < -I_JSON_MAX:
            raise JcsError("int_range")
        out.append(str(v))
    elif isinstance(v, float):
        if stats is not None:
            stats["float_values"] += 1
            if v.is_integer():
                stats["float_integral_in_tree"] += 1
        out.append(es_number(v))
    elif isinstance(v, list):
        out.append("[")
        first = True
        for x in v:
            if not first:
                out.append(",")
            first = False
            _emit(x, out, stats)
        out.append("]")
    elif isinstance(v, dict):
        keys = list(v)
        if all(k.isascii() for k in keys):
            order = sorted(keys)
        else:
            order = sorted(keys, key=_u16)
            if stats is not None and order != sorted(keys):
                stats["objects_utf16_order_differs"] += 1
        out.append("{")
        first = True
        for k in order:
            if not first:
                out.append(",")
            first = False
            out.append('"' + _ESC_RE.sub(_esc, k) + '":')
            _emit(v[k], out, stats)
        out.append("}")
    else:
        raise JcsError("not_json")


# ============================================================================================ string patterns (A4 3.1)
P = {
    "C0_C1": re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]"),
    "NUL": re.compile(r"\x00"),
    "CR": re.compile(r"\r"),
    "SEPARATORS": re.compile(r"[\u2028\u2029\x85]"),
    "ESC_SEQ": re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07\x1b]*(?:\x07|\x1b\\)|[@-Z\\-_])"),
    "ESC_TEXT": re.compile(r"(?:\\x1[bB]|\\u001[bB]|\\033|\\e)\["),
    "BIDI": re.compile(r"[\u061c\u200e\u200f\u202a-\u202e\u2066-\u2069]"),
    "ZERO_WIDTH": re.compile(r"[\u00ad\u200b-\u200d\u2060-\u2064\ufeff\u180e\u034f\u115f\u1160\u3164\uffa0]"),
    "TAGS": re.compile(r"[\U000e0000-\U000e007f]"),
    "VARIATION": re.compile(r"[\ufe00-\ufe0f\U000e0100-\U000e01ef]"),
    "PUA_NONCH": re.compile(r"[\ue000-\uf8ff\ufdd0-\ufdef\ufffe\uffff\U000f0000-\U0010ffff]"),
    "FFFD": re.compile(r"\ufffd"),
    "SURROGATE": re.compile(r"[\ud800-\udfff]"),
    "MOJIBAKE": re.compile(r"(?:\u00c3[\u0080-\u00bf]|\u00c2[\u00a0-\u00bf]|\u00e2\u20ac[\u2122\u0153\u201c\u201d\u2013\u2014\u00a6]|\u00f0\u0178)"),
    "LIT_ESC": re.compile(r"\\(?:[nrtbfv0\"'/\\]|x[0-9A-Fa-f]{2}|u[0-9A-Fa-f]{4}|U[0-9A-Fa-f]{8})"),
    "LIT_ESC_2X": re.compile(r"\\\\(?:[nrt\"'\\]|x[0-9A-Fa-f]{2}|u[0-9A-Fa-f]{4})"),
    "LIT_U_SURR": re.compile(r"\\u[dD][89a-fA-F][0-9a-fA-F]{2}"),
    "YAML_DQ_ESC": re.compile(r"\\[_NLP0aeEv ]"),
    "WINPATH_CTRL": re.compile(r"(?i)(?<![a-z0-9])[a-z]:(?:[\x07-\x0d]|[\x85\xa0\u2028\u2029])[a-z0-9_.-]"),
    "WINPATH_OK": re.compile(r"(?i)(?<![a-z0-9])[a-z]:\\[^\s\"'<>|?*]+"),
    "ANGLE_U": re.compile(r"<U\+[0-9A-Fa-f]{4,6}>"),
    "ENTITY": re.compile(r"&(?:#[0-9]{1,7}|#[xX][0-9A-Fa-f]{1,6}|[A-Za-z][A-Za-z0-9]{1,31});"),
    "RENDER": re.compile(r"(?i)!\[[^\]\n]{0,200}\]\(|<script|<img\b|javascript:|<iframe|onerror="),
    "PY_REPR_HEAD": re.compile(r"\A\s*[\[{(]\s*[ubrUBR]?'[^'\n]{0,80}'\s*[:,\]})]"),
    "PY_OBJ": re.compile(r"<[A-Za-z_][\w.]*(?: object)? at 0x[0-9a-f]+>|<class '[\w.]+'>"),
    "PY_CALLS": re.compile(r"\b(?:datetime\.(?:datetime|date|timedelta)|Decimal|UUID)\('?\d?"),
    "PY_BYTES": re.compile(r"\bb'(?:[^'\\]|\\.){0,200}'"),
    "ID_TRAIL_NL": re.compile(r"\A[A-Za-z0-9_#.:@+/-]{1,200}\n\Z"),
    "ABS_PATH": re.compile(r"/Users/[^/\s\"']+|/home/[^/\s\"']+|/private/(?:tmp|var)/|/var/folders/|[A-Za-z]:\\\\?Users\\\\?|\.agentprov/|AGENTPROV_HOME"),
    "SECRET_SHAPE": re.compile(r"sk-[A-Za-z0-9_-]{20,}|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{36}|AIza[0-9A-Za-z_-]{35}|xox[baprs]-[A-Za-z0-9-]{10,}|-----BEGIN [A-Z ]*PRIVATE KEY"),
}

# byte prefilters (a superset of the decoded patterns they gate; the decoded walk is exact)
G = {
    "backslash": (re.compile(rb"\\\\"), ("LIT_ESC", "LIT_ESC_2X", "LIT_U_SURR", "YAML_DQ_ESC", "ESC_TEXT", "WINPATH_OK", "PY_BYTES", "ABS_PATH")),
    "ctrl": (re.compile(rb"\\u00[01]|\\[bf]|\x7f|\xc2[\x80-\x9f]"), ("C0_C1", "NUL", "ESC_SEQ", "WINPATH_CTRL")),
    "cr": (re.compile(rb"\\r"), ("CR",)),
    "sep": (re.compile(rb"\xe2\x80[\xa8\xa9]|\xc2\x85"), ("SEPARATORS", "WINPATH_CTRL")),
    "nbsp": (re.compile(rb"\xc2\xa0"), ("WINPATH_CTRL",)),
    "uni": (re.compile(
        rb"\xd8\x9c|\xe2\x80[\x8b-\x8f\xaa-\xae]|\xe2\x81[\xa0-\xa4\xa6-\xa9]|\xef\xbb\xbf|\xc2\xad|\xe1\xa0\x8e|\xcd\x8f"
        rb"|\xe1\x85[\x9f\xa0]|\xe3\x85\xa4|\xef\xbe\xa0|\xf3\xa0[\x80-\x87]|\xef\xb8[\x80-\x8f]|[\xee]|\xef[\x80-\xa3]"
        rb"|\xef\xb7[\x90-\xaf]|\xef\xbf[\xbd-\xbf]|[\xf3][\xb0-\xbf]|\xf4[\x80-\x8f]|\xc3[\x82\x83\xa2\xb0]"),
        ("BIDI", "ZERO_WIDTH", "TAGS", "VARIATION", "PUA_NONCH", "FFFD", "MOJIBAKE")),
    "jsonstr": (re.compile(rb'"(?:[ \t]|\\[nrt])*[\[{(]'), ("PY_REPR_HEAD", "@JSON_IN_STRING")),
    "quotedjson": (re.compile(rb'"\\"'), ("@JSON_IN_STRING",)),
    "py": (re.compile(rb"<[A-Za-z_][\w.]*(?: object)? at 0x|<class '|datetime\.|Decimal\(|UUID\(|\bb'"), ("PY_OBJ", "PY_CALLS", "PY_BYTES")),
    "angle": (re.compile(rb"<U\+[0-9A-Fa-f]{4}"), ("ANGLE_U",)),
    "entity": (re.compile(rb"&#?[A-Za-z0-9]{1,32};"), ("ENTITY",)),
    "render": (re.compile(rb"(?i)!\[|<script|<img|javascript:|<iframe|onerror="), ("RENDER",)),
    "idnl": (re.compile(rb'"[A-Za-z0-9_#.:@+/-]{1,200}\\n"'), ("ID_TRAIL_NL",)),
    "path": (re.compile(rb"/Users/|/home/|/private/(?:tmp|var)/|/var/folders/|:\\\\\\\\Users|Users\\\\\\\\|\.agentprov/|AGENTPROV_HOME"), ("ABS_PATH",)),
    "secret": (re.compile(rb"sk-[A-Za-z0-9_-]{20}|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{36}|AIza[0-9A-Za-z_-]{35}|xox[baprs]-|-----BEGIN [A-Z ]*PRIVATE"), ("SECRET_SHAPE",)),
}

# raw-byte counters on canonical files (A4 3.2): counted, not walked
B = {
    "NONCANON_ESC": re.compile(rb'(?<!\\)(?:\\\\)*\\(?:/|U|u(?![0-9a-f]{4})|u00[0-9a-f]{2}(?<!\\u001[0-9a-f])(?<!\\u000[0-7bBeE]))'),
    "UPPER_HEX_ESC": re.compile(rb"(?<!\\)(?:\\\\)*\\u[0-9a-f]{0,3}[A-F]"),
    "ESC_SURR": re.compile(rb"(?<!\\)(?:\\\\)*\\u[dD][89a-fA-F][0-9a-fA-F]{2}"),
    "UTF16_WRAP": re.compile(rb'\{"\$utf16":'),
    "LIT_WRAP": re.compile(rb'\{"\$lit":'),
    "INT_WRAP": re.compile(rb'\{"\$int":'),
    "FLOAT_WRAP": re.compile(rb'\{"\$float":'),
    "BLOB_REF": re.compile(rb'\{"\$blob":'),
    "LEX_HINTS": re.compile(rb'"lex":\{'),
    "PCT_ENC": re.compile(rb"%[0-9A-Fa-f]{2}"),
    "SPLITLINES_HAZARD": re.compile(rb"\xe2\x80[\xa8\xa9]|\xc2\x85"),  # raw in JCS lines; \x0b \x0c \x1c-\x1e are escaped by JCS
}


def sha16(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8", "surrogatepass")).hexdigest()[:16]


_DIG = re.compile(r"(?<=/)[0-9]+(?=/|$)")
_DATA_PARENTS = frozenset({"args", "args_effective", "ord", "content", "value", "params", "injections", "input", "output",
                           "result", "env", "data", "metadata", "returned", "state", "scores", "store", "lit", "$lit",
                           "unk", "evf", "raw", "extra", "headers", "kwargs", "arguments", "tools", "inputs"})
_SAFE_TOK = re.compile(r"[A-Za-z0-9_:.$@-]{1,48}")


def norm_tokens(tokens: list[str]) -> str:
    out: list[str] = []
    prev = ""
    for t in tokens:
        if t.isdigit():
            out.append("*")
        elif prev in _DATA_PARENTS or not _SAFE_TOK.fullmatch(t):
            out.append("~")
        else:
            out.append(t)
        prev = t
    return "/" + "/".join(out) if out else ""


# ============================================================================================ JSON-in-string (U08)
def classify_json_string(s: str, yaml_load: Any) -> tuple[str, str]:
    """(class, subclass) for a string that looks like JSON: json_ok / python_repr / yaml_ok / unparsed."""
    if len(s) > 200_000:
        return "skipped_long", ""
    flags: Counter = Counter()
    try:
        v = strict_parse(s.encode("utf-8", "surrogatepass"), flags)
        return "json_ok", type(v).__name__
    except StrictError as exc:
        code = exc.code
    except Exception:  # noqa: BLE001
        code = "other"
    if code in ("duplicate_key", "nonfinite_constant", "float_overflow"):
        return "json_nonstrict", code
    import ast

    try:
        if len(s) <= 100_000:
            v = ast.literal_eval(s)
            return "python_repr", type(v).__name__
    except (ValueError, SyntaxError, MemoryError, RecursionError, TypeError):
        pass
    try:
        v = yaml_load(s)
        if not isinstance(v, str):
            return "yaml_ok", type(v).__name__
    except Exception:  # noqa: BLE001
        pass
    try:
        json.loads(s)
    except json.JSONDecodeError as exc:
        if exc.pos >= len(s.rstrip()) - 1:
            return "unparsed", "truncated"
        if "escape" in exc.msg:
            return "unparsed", "bad_escape"
        return "unparsed", "other"
    except Exception:  # noqa: BLE001
        return "unparsed", "other"
    return "unparsed", "other"


def looks_json(s: str) -> bool:
    if len(s) < 2:
        return False
    a = s.lstrip()[:1]
    b = s.rstrip()[-1:]
    return (a == "{" and b == "}") or (a == "[" and b == "]") or (a == '"' and b == '"' and len(s.strip()) >= 2)


# ============================================================================================ PROV helpers
FORMALS: dict[str, tuple[str, ...]] = {
    "used": ("prov:activity", "prov:entity"),
    "wasGeneratedBy": ("prov:entity", "prov:activity"),
    "wasDerivedFrom": ("prov:generatedEntity", "prov:usedEntity", "prov:activity", "prov:generation", "prov:usage"),
    "wasInformedBy": ("prov:informed", "prov:informant"),
    "wasStartedBy": ("prov:activity", "prov:trigger", "prov:starter"),
    "wasEndedBy": ("prov:activity", "prov:trigger", "prov:ender"),
    "wasInvalidatedBy": ("prov:entity", "prov:activity"),
    "wasAssociatedWith": ("prov:activity", "prov:agent", "prov:plan"),
    "wasAttributedTo": ("prov:entity", "prov:agent"),
    "actedOnBehalfOf": ("prov:delegate", "prov:responsible", "prov:activity"),
    "wasInfluencedBy": ("prov:influencee", "prov:influencer"),
    "specializationOf": ("prov:specificEntity", "prov:generalEntity"),
    "alternateOf": ("prov:alternate1", "prov:alternate2"),
    "hadMember": ("prov:collection", "prov:entity"),
    "mentionOf": ("prov:specificEntity", "prov:generalEntity", "prov:bundle"),
}
ELEMENTS = ("entity", "activity", "agent")
NODE_ARGS = frozenset({"prov:activity", "prov:entity", "prov:generatedEntity", "prov:usedEntity", "prov:informed",
                       "prov:informant", "prov:trigger", "prov:starter", "prov:ender", "prov:agent", "prov:plan",
                       "prov:delegate", "prov:responsible", "prov:influencee", "prov:influencer", "prov:specificEntity",
                       "prov:generalEntity", "prov:alternate1", "prov:alternate2", "prov:collection"})


def scc(nodes: list[Any], adj: dict[Any, list[Any]]) -> list[list[Any]]:
    """Tarjan's SCC, iterative."""
    index: dict[Any, int] = {}
    low: dict[Any, int] = {}
    on: set[Any] = set()
    stack: list[Any] = []
    out: list[list[Any]] = []
    counter = 0
    for root in nodes:
        if root in index:
            continue
        work = [(root, iter(adj.get(root, ())))]
        index[root] = low[root] = counter
        counter += 1
        stack.append(root)
        on.add(root)
        while work:
            v, it = work[-1]
            advanced = False
            for w in it:
                if w not in index:
                    index[w] = low[w] = counter
                    counter += 1
                    stack.append(w)
                    on.add(w)
                    work.append((w, iter(adj.get(w, ()))))
                    advanced = True
                    break
                if w in on:
                    low[v] = min(low[v], index[w])
            if advanced:
                continue
            work.pop()
            if work:
                low[work[-1][0]] = min(low[work[-1][0]], low[v])
            if low[v] == index[v]:
                comp = []
                while True:
                    w = stack.pop()
                    on.discard(w)
                    comp.append(w)
                    if w == v:
                        break
                out.append(comp)
    return out


def nontrivial_cycles(edges: list[tuple[Any, Any]]) -> int:
    """Number of SCCs of size > 1 plus self-loops in a directed graph."""
    adj: dict[Any, list[Any]] = {}
    nodes: set[Any] = set()
    loops = 0
    for a, b in edges:
        if a == b:
            loops += 1
            continue
        adj.setdefault(a, []).append(b)
        nodes.add(a)
        nodes.add(b)
    return loops + sum(1 for c in scc(sorted(nodes, key=str), adj) if len(c) > 1)


def union_find_components(nodes: set[str], edges: list[tuple[str, str]]) -> int:
    parent = {n: n for n in nodes}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b in edges:
        if a in parent and b in parent:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb
    return len({find(n) for n in nodes})


def wilson(k: int, n: int, z: float = 1.959964) -> tuple[float, float]:
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def cp_upper_zero(n: int, alpha: float = 0.05) -> float:
    """One-sided Clopper-Pearson upper bound for 0 events in n trials."""
    return 1 - alpha ** (1 / n) if n else 1.0
