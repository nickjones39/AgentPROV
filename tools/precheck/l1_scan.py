"""Level 1 of the corpus pre-check: a whole-population raw scan of one source part (docs/reports/precheck/README.md §3).

    uv run python tools/precheck/l1_scan.py --source S --part P [--corpus-id C] [--profile ID]
        (--input PATH [--lfs-dir DIR] | --git BARE [--commit SHA] [--tree PREFIX ...] | --use-pin [--cache DIR])
        [--whole-tree] [--no-verify-pin] [--pin-check] [--jobs N] [--limit N] [--emit-fp] [--no-aux]

Checks L1-01..L1-08 over every raw artefact the importer would select, **raw only** (no mapping, no corpus):

* **Enumeration = the importer's.** The tree is walked as the product does (``agentprov.ingest.paths.discover`` for a
  local tree, the pinned git tree of a bare repository read with ``git ls-tree``/``cat-file`` under
  ``GIT_NO_LAZY_FETCH``, an archive input opened with ``agentprov.ingest.archives`` through the profile's expand
  selection (``raw.members.Selection``, nested archives of ``[import] nested`` included, in memory only), and the
  candidate labels are the family reader's ``iter_artefacts`` over that listing, so every ``label`` equals the importer's
  candidate label (the string ``ImportFilters.include_paths`` matches). Everything else is counted by reason: stray,
  excluded (with the profile's select code and owner), context, auxiliary (included but not a primary), not selected,
  rejected by the ingest gate (its code), absent blob.
* **Parse (L1-02)** through ``agentprov.ingest`` (``strict_json_loads``, ``scan_jsonl``, ``open_json_stream``,
  ``open_zip``); when the strict parser stops and ``--lenient-classes`` is given (opt-in), an independent lenient pass on the same bounded bytes counts every class
  (one artefact can report several): duplicate_key, non_finite, big_int, lone_surrogate, bom, trailing_data,
  invalid_utf8, truncated, too_deep, too_large, other. ``big_int`` also counts parsed integers beyond I-JSON (2^53-1).
* **Generic walk (L1-03, L1-06, L1-07)** over every parsed value: string hazards, secret-like strings and account paths
  (**counts and normalised JSON pointers only, never values**), timestamps (presence, forms, parse failures,
  monotonicity within a unit along document order, date range).
* **Family hooks (L1-04, L1-05, L1-08)** in ``l1_families.py``: facets, stratum, trajectory fingerprint, outcomes,
  degenerate flags.

Outputs (the pre-registered interface): ``<scratch>/l1-units-<part>.jsonl`` (one row per selected artefact),
``<scratch>/l1-aux-<part>.jsonl`` (auxiliary JSON files, parse and hazard counts only), the summary
``docs/reports/precheck/data/<corpus_id>/l1-<part>.json`` (counts, normalised pointers and labels only) and, with
``--emit-fp``, ``<precheck root>/_fp/<source>.<part>.jsonl``. ``--limit N`` (smoke) writes the summary and rows into the
scratch directory with a ``.limitN`` suffix, never into the repository.

Nothing is extracted to disk, no raw byte is edited, no network is used (every git call runs with lazy fetch off), and
no value of a secret-like string or account path is written anywhere. Run anything heavy through
``tools/suite_queue.py --class import --cpu 2``.
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import datetime as dt
import hashlib
import io
import json
import math
import os
import re
import subprocess
import sys
import time
import tomllib
from collections import Counter, defaultdict
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import IO, Any, Final

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import l1_families as fam  # noqa: E402
from l2_common import guard_output  # noqa: E402
from l2_common import precheck_root as _precheck_root  # noqa: E402

from agentprov.errors import IngestError, IngestFinding  # noqa: E402
from agentprov.ingest.limits import MIB, IngestLimits  # noqa: E402
from agentprov.ingest.loaders import NO_VALUE, scan_jsonl, strict_json_loads  # noqa: E402

TOOL_VERSION: Final = 1
DATA_DIR: Final = REPO / "docs" / "reports" / "precheck" / "data"
I_JSON_MAX: Final = 2**53 - 1
TINY_BYTES: Final = 64
#: Mappers that declare ``consumes_context`` at 065b0d36 (their context globs join an archive input's expand selection;
#: read from the code once, so the scanner never imports a mapper; tests/unit/precheck checks it still holds).
CONSUMES_CONTEXT: Final = frozenset({"agentdojo.tracelogger", "autogen.runs"})
PARSE_CLASSES: Final = ("duplicate_key", "non_finite", "big_int", "lone_surrogate", "bom", "trailing_data",
                        "invalid_utf8", "truncated", "empty", "too_deep", "too_large", "other")  # fmt: skip
_STRAYS: Final = (".DS_Store",)
_GIT_ENV: Final = {"GIT_NO_LAZY_FETCH": "1", "GIT_ALLOW_PROTOCOL": "file", "GIT_CONFIG_NOSYSTEM": "1",
                   "GIT_CONFIG_GLOBAL": os.devnull, "GIT_TERMINAL_PROMPT": "0", "GIT_LFS_SKIP_SMUDGE": "1", "LC_ALL": "C"}  # fmt: skip
_GIT_HARDEN: Final = ["-c", f"core.hooksPath={os.devnull}", "-c", "protocol.allow=never", "-c", "protocol.file.allow=always"]
_LFS_PREFIX: Final = b"version https://git-lfs.github.com/spec/v1\n"
#: Bounds of the JSON-in-string probe (a decoded string of an already parsed artefact, at most 4 MiB).
_INNER_LIMITS: Final = IngestLimits().replace(max_json_bytes=4 * MIB)
_TOP: Final = 40  # pointers kept per class in the summary
#: Pin kinds whose file is an archive input of L1 (``raw.fetch.verify_download`` accepts all three).
DOWNLOAD_KINDS: Final = ("zenodo", "hf", "url")


def home() -> Path:
    return Path(os.environ.get("AGENTPROV_HOME") or Path.home() / ".agentprov")


def precheck_root() -> Path:
    return _precheck_root()


def shown_path(path: str | os.PathLike[str]) -> str:
    """A local path as written into a report: the user's home becomes ``~`` (no account name in any output)."""
    text = os.fspath(path)
    user_home = str(Path.home())
    return text.replace(user_home, "~") if user_home else text


def is_stray(label: str) -> bool:
    name = label.rsplit("/", 1)[-1].rsplit("!/", 1)[-1]
    return name in _STRAYS or name.startswith("._")


# ================================================================================================ parse classes
_CODE_CLASS: Final[Mapping[str, str]] = {
    "ingest.json.duplicate_key": "duplicate_key", "ingest.number.nonfinite": "non_finite",
    "ingest.number.digits": "big_int", "ingest.json.bom": "bom", "ingest.json.encoding": "invalid_utf8",
    "ingest.json.depth": "too_deep", "ingest.size.file": "too_large", "ingest.size.record": "too_large",
    "ingest.jsonl.line_too_long": "too_large", "ingest.json.lone_surrogate": "lone_surrogate",
    "ingest.json.elements": "too_large",
}  # fmt: skip
_ENCODED_SURROGATE: Final = re.compile(rb"\xed[\xa0-\xbf][\x80-\xbf]")
_WS: Final = re.compile(r"[ \t\r\n]*")


def code_class(code: str) -> str:
    return _CODE_CLASS.get(code, "other")


def lenient_classes(data: bytes, limits: IngestLimits) -> tuple[set[str], Any]:
    """Every parse class of ``data`` by an independent lenient pass (stdlib ``json`` with counting hooks), on bytes
    already bounded by the ingest limits. Returns ``(classes, value or NO_VALUE)``."""
    classes: set[str] = set()
    if len(data) > limits.max_json_bytes:
        return {"too_large"}, NO_VALUE
    if data.startswith(b"\xef\xbb\xbf"):
        classes.add("bom")
        data = data[3:]
    if _ENCODED_SURROGATE.search(data):
        classes.add("lone_surrogate")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        classes.add("invalid_utf8")
        text = data.decode("utf-8", "surrogateescape")
    max_digits = limits.max_int_digits

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        seen: dict[str, Any] = {}
        for key, value in items:
            if key in seen:
                classes.add("duplicate_key")
            seen[key] = value
        return seen

    def constant(_name: str) -> float:
        classes.add("non_finite")
        return 0.0

    def parse_int(literal: str) -> int:
        if len(literal.lstrip("-")) > max_digits:
            classes.add("big_int")
            return 0
        value = int(literal)
        if abs(value) > I_JSON_MAX:
            classes.add("big_int")
        return value

    def parse_float(literal: str) -> float:
        value = float(literal)
        if not math.isfinite(value):
            classes.add("non_finite")
            return 0.0
        return value

    decoder = json.JSONDecoder(object_pairs_hook=pairs, parse_constant=constant, parse_int=parse_int,
                               parse_float=parse_float)  # fmt: skip
    if not text.strip(" \t\r\n"):  # an empty (or whitespace-only) document is not a truncated one
        classes.add("empty")
        return classes, NO_VALUE
    start = _WS.match(text)
    begin = start.end() if start else 0
    try:
        value, end = decoder.raw_decode(text, begin)
    except json.JSONDecodeError as exc:
        tail = len(text.rstrip(" \t\r\n"))
        classes.add("truncated" if exc.pos >= tail or "Unterminated" in exc.msg else "other")
        return classes, NO_VALUE
    except RecursionError:
        classes.add("too_deep")
        return classes, NO_VALUE
    if text[end:].strip(" \t\r\n"):
        classes.add("trailing_data")
    return classes, value


@dataclass
class Parsed:
    value: Any = NO_VALUE
    primary: str = "ok"  # "ok" or the class the strict parser stopped on
    classes: set[str] = field(default_factory=set)


def parse_json(data: bytes, limits: IngestLimits, *, lenient: bool = False) -> Parsed:
    """Strict parse through ``agentprov.ingest``. On failure, only with ``lenient`` (``--lenient-classes``, opt-in: it
    re-parses rejected bytes with stdlib ``json``, outside ``agentprov.ingest``) the lenient pass for every class (value
    kept if it parses); otherwise the strict parser's class alone and no value."""
    found: list[IngestFinding] = []
    try:
        value = strict_json_loads(data, limits, findings=found)
    except IngestError as exc:
        if data.startswith(_LFS_PREFIX):
            return Parsed(NO_VALUE, "lfs_pointer", {"lfs_pointer"})
        primary = code_class(exc.code)
        if not lenient:
            return Parsed(NO_VALUE, primary, {primary})
        classes, value = lenient_classes(data, limits)
        if primary == "other" and classes:
            primary = sorted(classes)[0]
        return Parsed(value, primary, classes | {primary})
    classes = {code_class(f.code) for f in found}
    return Parsed(value, "ok", classes)


# ================================================================================================ hazard walk
_SAFE_KEY: Final = re.compile(r"[A-Za-z_@$][A-Za-z0-9_.:@$-]{0,63}")
_HEXISH: Final = re.compile(r"[0-9a-fA-F]{16,}|[0-9a-f-]{32,}")
_ASCII_CTRL: Final = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
#: Hazard code points as (first, last) ranges; built with chr() so the source holds no invisible character.
_HAZ_RANGES: Final = ((0x00, 0x08), (0x0B, 0x1F), (0x7F, 0x9F), (0x061C, 0x061C), (0x200B, 0x200F), (0x2028, 0x202E),
                      (0x2060, 0x2069), (0xFEFF, 0xFEFF), (0xFE00, 0xFE0F), (0xFFFD, 0xFFFD), (0xE000, 0xF8FF),
                      (0xD800, 0xDFFF), (0xE0000, 0xE007F), (0xE0100, 0xE01EF), (0xF0000, 0x10FFFF))  # fmt: skip
_HAZ: Final = re.compile("[" + "".join(re.escape(chr(a)) + "-" + re.escape(chr(b)) for a, b in _HAZ_RANGES) + "]")
#: Mojibake of UTF-8 read as Latin-1/CP1252: 'A-tilde' or 'A-circumflex' + a continuation-range character, and the
#: three-character sequence of a curly quote or dash ('a-circumflex', euro sign, ...).
_MOJIBAKE: Final = re.compile(
    chr(0xC3) + "[" + chr(0x80) + "-" + chr(0xBF) + "]|" + chr(0xC2) + "[" + chr(0xA0) + "-" + chr(0xBF) + "]|"
    + chr(0xE2) + chr(0x20AC) + "[" + chr(0x80) + "-" + chr(0xBF) + "".join(chr(c) for c in (
        0x152, 0x153, 0x160, 0x161, 0x178, 0x17D, 0x17E, 0x192, 0x2C6, 0x2DC, 0x2013, 0x2014, 0x2018, 0x2019, 0x201A,
        0x201C, 0x201D, 0x201E, 0x2020, 0x2021, 0x2022, 0x2026, 0x2030, 0x2039, 0x203A, 0x20AC, 0x2122)) + "]")
_RESIDUES: Final = (("escaped_newline", re.compile(r"\\[nrt]")), ("escaped_unicode", re.compile(r"\\u[0-9a-fA-F]{4}")),
                    ("escaped_quote", re.compile(r"\\\"")))  # fmt: skip
_ISO: Final = re.compile(r"(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})(?::(\d{2})(?:[.,](\d+))?)?\s?(Z|z|[+-]\d{2}(?::?\d{2})?)?")
_TIME_KEY: Final = re.compile(r"(?i)(?:^|[_-])(?:timestamp|time|ts|t|created|started|ended|completed|start|end|date"
                              r"|datetime)(?:_?at|_ts|_ms|_s)?$|^(?:created|started|ended|completed)_?at$")  # fmt: skip
#: Secret-like shapes (public rule ids in the gitleaks style; the precheck's own set: the product holds no general one).
SECRET_PATTERNS: Final[Mapping[str, re.Pattern[str]]] = {
    "aws-access-key-id": re.compile(r"(?<![A-Z0-9])(?:AKIA|ASIA)[0-9A-Z]{16}(?![A-Z0-9])"),
    "anthropic-api-key": re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}"),
    "openai-api-key": re.compile(r"(?<![A-Za-z0-9])sk-(?!ant-)(?:proj-|svcacct-)?[A-Za-z0-9_\-]{20,}"),
    "github-token": re.compile(r"(?<![A-Za-z0-9])gh[pousr]_[A-Za-z0-9]{30,}"),
    "slack-token": re.compile(r"(?<![A-Za-z0-9])xox[abposr]-[A-Za-z0-9\-]{10,}"),
    "google-api-key": re.compile(r"AIza[0-9A-Za-z_\-]{35}"),
    "stripe-key": re.compile(r"(?<![A-Za-z0-9])[sr]k_(?:live|test)_[A-Za-z0-9]{16,}"),
    "private-key-block": re.compile(r"-----BEGIN[A-Z ]{0,20} PRIVATE KEY-----"),
    "jwt": re.compile(r"(?<![A-Za-z0-9_\-])eyJ[A-Za-z0-9_\-]{10,}\.eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}"),
    "hf-token": re.compile(r"(?<![A-Za-z0-9])hf_[A-Za-z0-9]{34,}"),
    "generic-credential-assignment": re.compile(
        r"(?i)(?:api[_-]?key|secret|token|passw(?:or)?d)[\"']?\s{0,3}[:=]\s{0,3}[\"']?[A-Za-z0-9_\-/+=.]{16,}"),
}  # fmt: skip
_SECRET_PREFILTER: Final = re.compile(r"(?i)AKIA|ASIA|sk-|[sr]k_|gh[pousr]_|xox|AIza|PRIVATE KEY|eyJ|hf_|key|secret|token|passw")
ACCOUNT_PATTERNS: Final[Mapping[str, re.Pattern[str]]] = {
    "users-dir": re.compile(r"/Users/([^/\s\"'<>\\]{1,64})/"),
    "home-dir": re.compile(r"/home/([^/\s\"'<>\\]{1,64})/"),
    "windows-users": re.compile(r"(?i)[A-Za-z]:(?:\\\\|\\|/)+Users(?:\\\\|\\|/)+([^\\/\s\"'<>]{1,64})"),
    "tilde-user": re.compile(r"(?<![\w/~])~([a-z_][a-z0-9_.-]{1,31})/"),
}
#: Account names that are container or placeholder users, not a person's workstation account (classification only).
GENERIC_ACCOUNTS: Final = frozenset({"ubuntu", "user", "root", "runner", "app", "node", "admin", "agent", "dev", "test",
                                     "guest", "vscode", "jovyan", "circleci", "ec2-user", "sandbox", "username", "you",
                                     "yourname", "name", "me", "shared", "default", "docker", "work", "coder", "jenkins",
                                     "alice", "bob", "john", "jane", "example", "demo", "<user>", "user1", "myuser"})  # fmt: skip
_ACCOUNT_PREFILTER: Final = re.compile(r"/Users/|/home/|(?i:users)|~[a-z_]")
#: A key that is itself a secret-like token (``SECRET_PATTERNS`` without the assignment rule): never a pointer segment.
_SECRET_KEY: Final = re.compile("|".join(f"(?:{rx.pattern})" for name, rx in SECRET_PATTERNS.items()
                                         if name != "generic-credential-assignment"))
#: Row flags of L1-06 (per artefact; the summary holds the pointers): ``l2_sample --exclude-flag`` and the L2 redaction
#: join read them. Never a value, only the class.
L106_FLAGS: Final = (("account:local-path-model", "local_path_model"), ("account:this-machine-home", "operator_home"),
                     ("secret:", "secret_like"), ("withhold:", "withhold_rule"))  # fmt: skip


def pointer_part(key: Any) -> str:
    if not isinstance(key, str):
        return "<nonstr>"
    if (_HEXISH.fullmatch(key) or not _SAFE_KEY.fullmatch(key) or fam.LOCAL_PATH_MODEL.search(key)
            or fam.SECRETISH.search(key) or _SECRET_KEY.search(key) or "@" in key[1:]):  # e-mail-like keys too
        return "<key>"
    return key.replace("~", "~0").replace("/", "~1")


def char_class(c: str) -> str:
    o = ord(c)
    if c == "\x1b":
        return "esc"
    if c == "\r":
        return "cr"
    if o < 0x20 or o == 0x7F:
        return "c0"
    if o == 0x85:
        return "nel"
    if 0x80 <= o <= 0x9F:
        return "c1"
    if o in (0x2028, 0x2029):
        return "line_sep"
    if o in (0x061C, 0x200E, 0x200F) or 0x202A <= o <= 0x202E or 0x2066 <= o <= 0x2069:
        return "bidi"
    if 0x200B <= o <= 0x200D or 0x2060 <= o <= 0x2064 or o == 0xFEFF:
        return "zero_width"
    if 0xFE00 <= o <= 0xFE0F or 0xE0100 <= o <= 0xE01EF:
        return "variation_selector"
    if 0xE0000 <= o <= 0xE007F:
        return "tag"
    if 0xD800 <= o <= 0xDFFF:
        return "lone_surrogate"
    if o == 0xFFFD:
        return "fffd"
    if 0xE000 <= o <= 0xF8FF or o >= 0xF0000:
        return "pua"
    return "other_format"


@dataclass
class TsStat:
    count: int = 0
    forms: Counter[str] = field(default_factory=Counter)
    fail: int = 0
    min_date: str | None = None
    max_date: str | None = None
    units_non_monotone: int = 0
    units_with: int = 0

    def merge(self, other: TsStat) -> None:
        self.count += other.count
        self.forms.update(other.forms)
        self.fail += other.fail
        self.units_non_monotone += other.units_non_monotone
        self.units_with += other.units_with
        for d in (other.min_date, other.max_date):
            if d is not None:
                self.min_date = d if self.min_date is None or d < self.min_date else self.min_date
                self.max_date = d if self.max_date is None or d > self.max_date else self.max_date

    def to_json(self) -> dict[str, Any]:
        return {"count": self.count, "forms": dict(sorted(self.forms.items())), "parse_fail": self.fail,
                "min_date": self.min_date, "max_date": self.max_date, "units_with": self.units_with,
                "units_non_monotone": self.units_non_monotone}  # fmt: skip


def iso_value(text: str) -> tuple[str, float | None, str | None]:
    """``(form, seconds or None on a parse failure, date)`` of an ISO-8601-like timestamp string."""
    m = _ISO.fullmatch(text)
    assert m is not None
    y, mo, d, h, mi, s, frac, tz = m.groups()
    if tz is None:
        form = "naive"
    elif tz in ("Z", "z"):
        form = "Z"
    else:
        form = "utc_offset" if tz.replace(":", "").lstrip("+-").strip("0") == "" else "offset"
    try:
        micro = int((frac or "0")[:6].ljust(6, "0"))
        stamp = dt.datetime(int(y), int(mo), int(d), int(h), int(mi), int(s or 0), micro, tzinfo=dt.UTC)
        if tz not in (None, "Z", "z"):
            sign = -1 if tz[0] == "-" else 1
            digits = tz[1:].replace(":", "")
            offset = dt.timedelta(hours=int(digits[:2]), minutes=int(digits[2:4] or 0))
            stamp = stamp - sign * offset
    except (ValueError, OverflowError):
        return form, None, None
    return form, stamp.timestamp(), f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"


class Walker:
    """Counts of one artefact over every parsed value it holds (L1-03, L1-06, L1-07 and the I-JSON integer check)."""

    def __init__(self, withhold_rules: Sequence[Any], home_needles: Sequence[bytes]) -> None:
        self.ptr: Counter[str] = Counter()  # "<check>\t<class>\t<pointer>" -> strings
        self.strings: Counter[str] = Counter()  # "<check>\t<class>" -> strings in this artefact
        self.ts: dict[str, TsStat] = {}
        self.accounts: dict[str, set[str]] = defaultdict(set)  # pattern -> digests of named accounts (never names)
        self.withhold = [r for r in withhold_rules if getattr(r, "kind", None) in ("marker", "pattern")]
        self.home_needles = [n for n in home_needles if n]
        self.big_ints = 0
        #: set when the artefact's bytes were not UTF-8 and the lenient pass decoded them with ``surrogateescape``: the
        #: U+DC80..U+DCFF it produced are counted ``undecodable_byte``, not ``lone_surrogate``
        self.undecodable = False
        self._unit_ts: dict[str, list[float]] = {}

    def note(self, check: str, cls: str, pointer: str) -> None:
        self.ptr[f"{check}\t{cls}\t{pointer}"] += 1
        self.strings[f"{check}\t{cls}"] += 1

    # -------------------------------------------------------------------------- units (timestamp monotonicity)
    def begin_unit(self) -> None:
        self._unit_ts = {}

    def end_unit(self) -> bool | None:
        monotone: bool | None = None
        for pointer, values in self._unit_ts.items():
            stat = self.ts[pointer]
            stat.units_with += 1
            if len(values) >= 2:
                ok = all(a <= b for a, b in zip(values, values[1:], strict=False))
                monotone = ok if monotone is None else (monotone and ok)
                if not ok:
                    stat.units_non_monotone += 1
        self._unit_ts = {}
        return monotone

    # -------------------------------------------------------------------------- walk
    def walk(self, root: Any, prefix: str = "") -> None:
        stack: list[tuple[Any, str, Any]] = [(root, prefix, None)]
        while stack:
            node, pointer, key = stack.pop()
            if isinstance(node, dict):
                for k, v in reversed(list(node.items())):
                    if isinstance(k, str) and not k.isascii() or isinstance(k, str) and _ASCII_CTRL.search(k):
                        self._chars(k, pointer + "/<key-name>")
                    if isinstance(k, str) and (_SECRET_PREFILTER.search(k) or _ACCOUNT_PREFILTER.search(k)):
                        self._secrets(k, pointer + "/<key-name>")
                    stack.append((v, f"{pointer}/{pointer_part(k)}", k))
            elif isinstance(node, list):
                child = pointer + "/*"
                for v in reversed(node):
                    stack.append((v, child, key))
            elif isinstance(node, str):
                self._string(node, pointer, key)
            elif isinstance(node, bool) or node is None:
                continue
            elif isinstance(node, int):
                if abs(node) > I_JSON_MAX:
                    self.big_ints += 1
                    self.note("L1-02", "big_int", pointer)
                self._epoch(float(node), pointer, key)
            elif isinstance(node, float):
                if not math.isfinite(node):
                    self.note("L1-02", "non_finite", pointer)
                else:
                    self._epoch(node, pointer, key)

    def _chars(self, s: str, pointer: str) -> None:
        seen: set[str] = set()
        if s.isascii():
            for m in _ASCII_CTRL.finditer(s):
                seen.add(char_class(m.group()))
            if "esc" in seen and "\x1b[" in s:
                seen.add("ansi")
        else:
            for m in _HAZ.finditer(s):
                c = m.group()
                undecodable = self.undecodable and 0xDC80 <= ord(c) <= 0xDCFF
                seen.add("undecodable_byte" if undecodable else char_class(c))
            if "esc" in seen and "\x1b[" in s:
                seen.add("ansi")
            if _MOJIBAKE.search(s):
                seen.add("mojibake")
        for cls in seen:
            self.note("L1-03", cls, pointer)

    def _string(self, s: str, pointer: str, key: Any) -> None:
        if not s:
            return
        self._chars(s, pointer)
        if "\\" in s:
            for cls, rx in _RESIDUES:
                if rx.search(s):
                    self.note("L1-03", cls, pointer)
        stripped = s.strip()
        if len(stripped) >= 2 and stripped[0] in "{[" and stripped[-1] in "}]" and len(s) <= 4 * MIB:
            try:  # untrusted text: parsed only through agentprov.ingest (bounded), never stdlib json
                inner = strict_json_loads(stripped.encode("utf-8", "surrogatepass"), _INNER_LIMITS)
            except IngestError:
                inner = None
            if isinstance(inner, dict | list) and inner:
                self.note("L1-03", "json_in_string", pointer)
        self._secrets(s, pointer)
        if isinstance(key, str) and "model" in key.lower() and fam.LOCAL_PATH_MODEL.search(s):
            self.note("L1-06", "account:local-path-model", pointer)
        if self.withhold or self.home_needles:
            raw = s.encode("utf-8", "surrogatepass")
            for needle in self.home_needles:
                if needle in raw:
                    self.note("L1-06", "account:this-machine-home", pointer)
            for rule in self.withhold:
                hit = (rule.needle in raw) if rule.kind == "marker" else (rule.regex.search(raw) is not None)
                if hit:
                    self.note("L1-06", f"withhold:{rule.id}", pointer)
        if 16 <= len(s) <= 40 and s[4:5] == "-" and s[:4].isdigit() and _ISO.fullmatch(s):
            form, seconds, date = iso_value(s)
            self._ts(pointer, form, seconds, date)

    def _secrets(self, s: str, pointer: str) -> None:
        """L1-06 secret-like shapes and account paths of one string (a value or a key): class and pointer only."""
        if _SECRET_PREFILTER.search(s):
            for name, rx in SECRET_PATTERNS.items():
                if rx.search(s):
                    self.note("L1-06", "secret:" + name, pointer)
        if _ACCOUNT_PREFILTER.search(s):
            for name, rx in ACCOUNT_PATTERNS.items():
                for m in rx.finditer(s):
                    account = m.group(1)
                    if name == "users-dir" and account.lower() == "shared":
                        continue
                    kind = "generic" if account.lower() in GENERIC_ACCOUNTS else "named"
                    self.note("L1-06", f"account:{name}:{kind}", pointer)
                    if kind == "named":
                        self.accounts[name].add(hashlib.sha256(account.encode("utf-8", "surrogatepass")).hexdigest()[:16])

    def _epoch(self, value: float, pointer: str, key: Any) -> None:
        name = key if isinstance(key, str) else None
        if name is None or not _TIME_KEY.search(name):
            return
        if 1e9 <= value < 4.2e9:
            form, seconds = "epoch_s", value
        elif 1e12 <= value < 4.2e12:
            form, seconds = "epoch_ms", value / 1000.0
        else:
            return
        date = dt.datetime.fromtimestamp(seconds, dt.UTC).strftime("%Y-%m-%d")
        self._ts(pointer, form, seconds, date)

    def _ts(self, pointer: str, form: str, seconds: float | None, date: str | None) -> None:
        stat = self.ts.get(pointer)
        if stat is None:
            stat = self.ts[pointer] = TsStat()
        stat.count += 1
        stat.forms[form] += 1
        if seconds is None:
            stat.fail += 1
            return
        if date is not None:
            stat.min_date = date if stat.min_date is None or date < stat.min_date else stat.min_date
            stat.max_date = date if stat.max_date is None or date > stat.max_date else stat.max_date
        self._unit_ts.setdefault(pointer, []).append(seconds)


# ================================================================================================ fingerprints
def fingerprint(steps: Any) -> tuple[str | None, bool]:
    """sha256 of the JCS of a normalised step list (``None`` for no step); ``True`` when JCS could not represent it and
    the documented fallback (sorted-key ASCII JSON) was used."""
    if not steps:
        return None, False
    from agentprov.io.canonical import jcs_bytes

    try:
        return hashlib.sha256(jcs_bytes(steps)).hexdigest(), False
    except Exception:  # noqa: BLE001 - rfc8785 refuses lone surrogates, big ints, non-finite floats
        text = json.dumps(steps, sort_keys=True, ensure_ascii=True, separators=(",", ":"), allow_nan=True, default=repr)
        return hashlib.sha256(b"fallback:" + text.encode("ascii")).hexdigest(), True


# ================================================================================================ sources
@dataclass
class Entry:
    """One walked item: a file, a git blob or an archive member (``label`` is the importer's label: for an archive member
    its chain label; ``own`` is the label profile globs match)."""

    label: str
    size: int
    own: str
    disposition: str = "listed"  # listed | not_selected | rejected:<code> | nested | absent_blob
    sha1: str | None = None


class LocalSource:
    """A directory read in place (``agentprov.ingest.paths``), optionally restricted to the pin's tree prefixes."""

    kind: Final = "local"

    def __init__(self, root: Path, prefixes: Sequence[str] = (), limits: IngestLimits | None = None) -> None:
        self.root = Path(os.path.realpath(root))
        self.prefixes = [p.strip("/") for p in prefixes if p.strip("/")]
        self.limits = limits or IngestLimits()
        self.rejected: list[tuple[str, str]] = []
        self.skipped = 0

    def entries(self) -> list[Entry]:
        from agentprov.ingest.paths import discover

        out: list[Entry] = []
        roots = [(self.root / p, p + "/") for p in self.prefixes] if self.prefixes else [(self.root, "")]
        for base, pre in roots:
            if not base.is_dir():
                continue
            found = discover(base, self.limits)
            out += [Entry(pre + f.label, f.size, pre + f.label) for f in found.files]
            self.rejected += [(pre + r.label, r.code) for r in found.rejected]
            self.skipped += len(found.skipped)
        out.sort(key=lambda e: e.label.encode("utf-8"))
        return out

    def spec(self) -> dict[str, Any]:
        return {"kind": "local", "root": str(self.root)}


class GitSource:
    """The tree of a pinned commit in a bare repository (a fetch cache or a staging partial clone), read with
    ``git ls-tree``/``cat-file --batch`` with lazy fetch off; every blob's SHA-1 is recomputed."""

    kind: Final = "git"

    def __init__(self, bare: Path, commit: str, prefixes: Sequence[str] = ()) -> None:
        self.bare, self.commit, self.prefixes = Path(bare), commit, [p for p in prefixes if p]
        self.rejected: list[tuple[str, str]] = []
        self.skipped = 0

    def entries(self) -> list[Entry]:
        args = ["ls-tree", "-r", "-z", "--full-tree", self.commit]
        if self.prefixes:
            args += ["--", *self.prefixes]
        listing = git(self.bare, *args)
        rows: list[tuple[str, str, str]] = []
        for item in listing.split(b"\0"):
            if not item:
                continue
            head, raw_path = item.split(b"\t", 1)
            mode_b, kind, oid_b = head.split()
            if kind == b"blob":
                rows.append((raw_path.decode("utf-8", "surrogateescape"), oid_b.decode(), mode_b.decode()))
            elif kind == b"commit":
                self.rejected.append((raw_path.decode("utf-8", "surrogateescape"), "gitlink"))
        checked = git(self.bare, "cat-file", "--batch-check", data="".join(o + "\n" for _p, o, _m in rows).encode())
        out: list[Entry] = []
        for (path, oid, mode), line in zip(rows, checked.decode().splitlines(), strict=True):
            if mode == "120000":
                self.rejected.append((path, "ingest.path.symlink"))
                continue
            if is_stray(path):
                self.skipped += 1
            parts = line.split()
            if len(parts) < 3 or parts[1] == "missing":
                out.append(Entry(path, 0, path, "absent_blob", oid))
            else:
                out.append(Entry(path, int(parts[2]), path, "listed", oid))
        out.sort(key=lambda e: e.label.encode("utf-8"))
        return out

    def spec(self) -> dict[str, Any]:
        return {"kind": "git", "bare": str(self.bare), "commit": self.commit}


def git(repo: Path, *args: str, data: bytes | None = None) -> bytes:
    env = {k: v for k, v in os.environ.items() if k in ("PATH", "TMPDIR", "HOME")} | _GIT_ENV
    done = subprocess.run(["git", *_GIT_HARDEN, "-C", str(repo), *args], input=data, capture_output=True, env=env,  # noqa: S603, S607
                          check=False)  # fmt: skip
    if done.returncode != 0:
        raise SystemExit(f"git {args[0]} failed: {shown_path(done.stderr.decode('utf-8', 'replace')[:300])}")
    return done.stdout


class GitBlobReader:
    """A persistent ``cat-file --batch`` process (one per worker); ``read(oid)`` returns the blob with its SHA-1 checked."""

    def __init__(self, bare: str) -> None:
        env = {k: v for k, v in os.environ.items() if k in ("PATH", "TMPDIR", "HOME")} | _GIT_ENV
        self.proc = subprocess.Popen(["git", *_GIT_HARDEN, "-C", bare, "cat-file", "--batch"],  # noqa: S603, S607
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env)  # fmt: skip

    def read(self, oid: str) -> bytes:
        from agentprov.adapters.runner.importer import git_blob_sha1

        assert self.proc.stdin is not None and self.proc.stdout is not None
        self.proc.stdin.write(oid.encode("ascii") + b"\n")
        self.proc.stdin.flush()
        header = self.proc.stdout.readline().split()
        if len(header) < 3 or header[1] != b"blob":
            raise IngestError("ingest.path.special", "blob absent from the repository")
        size = int(header[2])
        data = self.proc.stdout.read(size)
        self.proc.stdout.read(1)
        if git_blob_sha1(data) != oid:
            raise IngestError("ingest.path.special", "blob SHA-1 mismatch")
        return data


@dataclass
class ArchiveFile:
    """One archive input: its container label (the pin's file name), the local file or the split parts ``(path, size)``."""

    label: str
    path: Path | None
    parts: list[tuple[Path, int]] | None = None


class ArchiveSource:
    """Archive inputs read through ``agentprov.ingest.archives`` with the profile's expand selection (members are never
    extracted: selected bytes are read into memory; a declared nested archive is opened from memory up to
    ``nested_cap`` bytes, above which it is counted ``nested_too_large`` and not walked)."""

    kind: Final = "archive"

    def __init__(self, files: Sequence[ArchiveFile], selection: Any, limits: IngestLimits, nested_cap: int) -> None:
        self.files, self.selection, self.limits, self.nested_cap = list(files), selection, limits, nested_cap
        self.rejected: list[tuple[str, str]] = []
        self.skipped = 0
        self.findings: Counter[str] = Counter()

    def _open(self, af: ArchiveFile) -> tuple[Any, list[IO[bytes]]]:
        from agentprov.ingest.archives import open_archive, open_split_zip
        from agentprov.ingest.paths import open_evidence

        if af.parts:
            handles = [open_evidence(str(p.parent), p.name, self.limits.replace(max_artefact_bytes=1 << 40)) for p, _s in af.parts]
            return open_split_zip(handles, [s for _p, s in af.parts], self.limits, release=False), handles
        assert af.path is not None
        handle = open_evidence(str(af.path.parent), af.path.name, self.limits.replace(max_artefact_bytes=1 << 40))
        return open_archive(handle, self.limits, release=False), [handle]

    def _walk(self, archive: Any, selection: Any, chain: tuple[str, ...], depth: int, allowance: int | None,
              want: set[str] | None) -> Iterator[tuple[Entry, bytes | IngestError | None]]:  # fmt: skip
        from agentprov.ingest.archives import iter_zip_members, open_archive
        from agentprov.raw.members import _compile

        matcher = _compile(selection.include)

        def include(label: str) -> bool:
            return (matcher is not None and matcher.match(label) is not None) or selection.child_for(label) is not None

        def raised(label: str) -> Any:
            child = selection.child_for(label)
            return child.raises if child is not None else None

        self.findings.update(f.code for f in getattr(archive, "findings", ()))
        for m in iter_zip_members(archive, include, self.limits, raised):
            own = m.label if m.label is not None else f"#{m.index}"
            label = "!/".join((*chain, own))
            if m.disposition == "rejected":
                yield Entry(label, m.file_size, own, f"rejected:{m.code}"), None
                continue
            if m.disposition == "not_selected":
                yield Entry(label, m.file_size, own, "not_selected"), None
                continue
            child = selection.child_for(own)
            if child is None:
                if want is None or label not in want:
                    yield Entry(label, m.file_size, own), None
                    continue
                try:
                    data: bytes | IngestError = archive.read_member(m)
                except IngestError as exc:
                    data = exc
                yield Entry(label, m.file_size, own), data
                continue
            yield Entry(label, m.file_size, own, "nested"), None
            if m.file_size > self.nested_cap:
                yield Entry(label, m.file_size, own, "rejected:nested_too_large_for_l1"), None
                continue
            try:
                inner = archive.read_member(m)
                allow = max(allowance or 0, child.raises.max_depth or 0) or None
                nested = open_archive(io.BytesIO(inner), self.limits, release=False, depth=depth + 1, max_depth=allow)
            except IngestError as exc:
                yield Entry(label, m.file_size, own, f"rejected:{exc.code}"), None
                continue
            yield from self._walk(nested, child.selection, (*chain, own), depth + 1, allow, want)
            del inner

    def entries(self) -> list[Entry]:
        out: list[Entry] = []
        for af in self.files:
            try:
                archive, handles = self._open(af)
            except IngestError as exc:
                self.rejected.append((af.label, exc.code))
                continue
            try:
                out += [e for e, _d in self._walk(archive, self.selection, (), 1, None, None)]
            finally:
                for h in handles:
                    h.close()
        for e in out:
            if e.disposition.startswith("rejected:"):
                self.rejected.append((e.label, e.disposition.split(":", 1)[1]))
        return out

    def stream(self, want: set[str]) -> Iterator[tuple[str, int, bytes | IngestError]]:
        for af in self.files:
            try:
                archive, handles = self._open(af)
            except IngestError:
                continue
            try:
                for e, data in self._walk(archive, self.selection, (), 1, None, want):
                    if data is not None and e.label in want:
                        yield e.label, e.size, data
            finally:
                for h in handles:
                    h.close()

    def spec(self) -> dict[str, Any]:
        return {"kind": "archive"}


# ================================================================================================ worker
_W: Scanner | None = None


def _init_worker(cfg: dict[str, Any]) -> None:
    global _W
    _W = Scanner(cfg)


def _work(task: tuple[str, int, bytes | IngestError | None, str | None, bool]) -> dict[str, Any]:
    assert _W is not None
    return _W.scan(*task)


class Scanner:
    """Scans one artefact (per process): parse, walk, family hook, fingerprints."""

    def __init__(self, cfg: Mapping[str, Any]) -> None:
        from agentprov.adapters.profiles import load_profile

        self.cfg = dict(cfg)
        self.profile = load_profile(cfg["profile_id"])
        imp = self.profile.data.get("import", {})
        self.dialect = str(imp.get("dialect"))
        self.hook = fam.HOOKS[self.dialect]
        family = self.profile.family_table()
        band = family.get("producer_band", {}) if isinstance(family, Mapping) else {}
        layout = imp.get("layout") or (family.get("layout") if isinstance(family, Mapping) else None)
        self.ctx = fam.Ctx(profile_id=self.profile.id, part=cfg["part"], layout=layout if isinstance(layout, str) else None,
                           variant_labels=dict(imp.get("variant_labels") or {}),
                           producer_band=tuple(band.get("inspect_ai", ())) if isinstance(band, Mapping) else ())  # fmt: skip
        self.limits = IngestLimits().replace(**cfg.get("limits", {}))
        self.lenient = bool(cfg.get("lenient"))
        self.strata = fam.strata_keys(self.profile.id, self.dialect)
        self.rules = withhold_rules(self.profile)
        self.home_needles = [n.encode() if isinstance(n, str) else n for n in cfg.get("home_needles", ())]
        self.source = cfg["source"]
        self.git: GitBlobReader | None = None
        self.lfs_dir = Path(cfg["lfs_dir"]) if cfg.get("lfs_dir") else None

    # -------------------------------------------------------------------------- reading
    def read(self, label: str, oid: str | None) -> bytes:
        src = self.source
        if src["kind"] == "local":
            from agentprov.ingest.paths import open_evidence

            with open_evidence(src["root"], label, self.limits) as handle:
                return handle.read()
        if src["kind"] == "git":
            if self.git is None:
                self.git = GitBlobReader(src["bare"])
            assert oid is not None
            return self.git.read(oid)
        raise RuntimeError("archive members are streamed by the main process")

    # -------------------------------------------------------------------------- scan
    def scan(self, label: str, size: int, data: bytes | IngestError | None, oid: str | None, aux: bool) -> dict[str, Any]:
        walker = Walker(self.rules, self.home_needles)
        row: dict[str, Any] = {"label": label, "sha256": None, "size": size, "kind": self._kind(label), "parse": "ok",
                               "n_units": 0, "facets": {}, "stratum": None, "fp": None,
                               "ts": {"present": False, "tz": [], "monotone": None}, "flags": []}  # fmt: skip
        out: dict[str, Any] = {"row": row, "aux": aux, "classes": [], "units": [], "sha1": None}
        if data is None:
            try:
                data = self.read(label, oid)
            except IngestError as exc:
                data = exc
        if isinstance(data, IngestError):
            row["parse"] = "unreadable:" + data.code
            row["flags"] = ["unreadable"]
            return self._finish(out, walker)
        if self.cfg.get("pin_check"):
            from agentprov.adapters.runner.importer import git_blob_sha1

            out["sha1"] = git_blob_sha1(data)
        row["sha256"] = hashlib.sha256(data).hexdigest()
        row["size"] = len(data)
        flags: list[str] = []
        if not data:
            flags.append("empty_file")
        elif len(data) < TINY_BYTES:
            flags.append("tiny")
        if data.startswith(_LFS_PREFIX) and self.lfs_dir is not None:
            resolved = self._lfs(data)
            if resolved is not None:
                flags.append("lfs_object_scanned")
                data = resolved
                row["sha256_object"] = hashlib.sha256(data).hexdigest()
        row["flags"] = flags
        if aux:
            self._scan_aux(data, label, out, walker)
        elif row["kind"] == "eval":
            self._scan_eval(data, label, out, walker)
        elif row["kind"] == "jsonl":
            self._scan_jsonl(data, label, out, walker)
        elif self.dialect == "mcphunt.traces":
            self._scan_stream(data, label, out, walker)
        else:
            self._scan_json(data, label, out, walker)
        return self._finish(out, walker)

    def _kind(self, label: str) -> str:
        name = label.rsplit("/", 1)[-1].lower()
        if name.endswith(".eval"):
            return "eval"
        if name.endswith(".jsonl"):
            return "jsonl"
        if self.dialect == "mcphunt.traces":
            return "jsonstream"
        return "json"

    def _lfs(self, pointer: bytes) -> bytes | None:
        m = re.search(rb"\noid sha256:([0-9a-f]{64})\n", pointer)
        if m is None or self.lfs_dir is None:
            return None
        name = m.group(1).decode()
        if not (self.lfs_dir / name).is_file():
            return None
        from agentprov.ingest.paths import open_evidence

        with open_evidence(str(self.lfs_dir), name, self.limits) as handle:
            data = handle.read()
        return data if hashlib.sha256(data).hexdigest() == name else None

    def _parse_into(self, data: bytes, out: dict[str, Any], walker: Walker | None = None) -> Parsed:
        parsed = parse_json(data, self.limits, lenient=self.lenient)
        if walker is not None and "invalid_utf8" in parsed.classes:
            walker.undecodable = True
        out["classes"] += sorted(parsed.classes)
        if out["row"]["parse"] == "ok" and parsed.primary != "ok":
            out["row"]["parse"] = parsed.primary
        return parsed

    def _unit(self, view: fam.UnitView, walker: Walker, out: dict[str, Any], monotone: bool | None) -> None:
        fp, fallback = fingerprint(view.steps)
        if fallback:
            view.flags.append("fp_fallback")
        out["units"].append({"locator": view.locator, "facets": view.facets, "fp": fp, "outcomes": view.outcomes,
                             "flags": view.flags, "variant": view.variant, "monotone": monotone})  # fmt: skip

    def _scan_aux(self, data: bytes, label: str, out: dict[str, Any], walker: Walker) -> None:
        name = label.rsplit("/", 1)[-1]
        if name.endswith(".jsonl"):
            for _n, _o, value, found in scan_jsonl(io.BytesIO(data), self.limits):
                out["classes"] += [code_class(f.code) for f in found if f.severity != "info" or "surrogate" in f.code]
                if value is not NO_VALUE:
                    walker.walk(value)
            return
        parsed = self._parse_into(data, out, walker)
        if parsed.value is not NO_VALUE:
            walker.begin_unit()
            walker.walk(parsed.value)
            walker.end_unit()
            for aux_name, reader in self.hook.aux_outcomes.items():
                if name == aux_name:
                    out["aux_outcomes"] = reader(parsed.value)

    def _scan_json(self, data: bytes, label: str, out: dict[str, Any], walker: Walker) -> None:
        parsed = self._parse_into(data, out, walker)
        row = out["row"]
        if parsed.value is NO_VALUE:
            if self.hook.unit is not None:  # the label's facets even for an unparseable file (no unit is counted)
                view = self.hook.unit(None, label, self.ctx)
                row["facets"] = view.facets
            row["flags"].append("unparsed")
            return
        if parsed.primary != "ok":  # the lenient value: walked and mapped by the hook, flagged (the importer refuses it)
            row["flags"].append("strict_parse_failed")
        if self.dialect == "credleak.cell":
            facets, flags = fam.credleak_cell_facets(parsed.value, label)
            row["facets"] = facets
            row["flags"] += flags
            runs = parsed.value.get("runs") if isinstance(parsed.value, Mapping) else None
            shell = {k: v for k, v in parsed.value.items() if k != "runs"} if isinstance(parsed.value, Mapping) else parsed.value
            walker.walk(shell)
            if not isinstance(runs, list) or not runs:
                row["flags"].append("zero_runs")
            for i, run in enumerate(runs if isinstance(runs, list) else ()):
                walker.begin_unit()
                walker.walk(run, "/runs/*")
                self._unit(fam.credleak_run_unit(run, i), walker, out, walker.end_unit())
            return
        walker.begin_unit()
        walker.walk(parsed.value)
        monotone = walker.end_unit()
        if self.dialect == "geminicli.stream_json":
            facets, flags = fam.geminicli_path_facets(label)
            view = fam.UnitView(facets=facets, flags=[*flags, "no_stream"], outcomes=fam.geminicli_verdict_outcomes(parsed.value))
            self._unit(view, walker, out, monotone)
            return
        assert self.hook.unit is not None
        self._unit(self.hook.unit(parsed.value, label, self.ctx), walker, out, monotone)

    def _scan_jsonl(self, data: bytes, label: str, out: dict[str, Any], walker: Walker) -> None:
        row = out["row"]
        lines = data.split(b"\n")
        values: list[Any] = []
        rows_mode = self.hook.jsonl_mode == "rows"
        facets: dict[str, str] = {}
        if self.dialect == "autogen.runs":
            facets, flags = fam.autogen_file_facets(label)
            row["flags"] += flags
        if not rows_mode:
            walker.begin_unit()
        non_run = 0
        for line_no, _offset, value, found in scan_jsonl(io.BytesIO(data), self.limits):
            errors = [f for f in found if f.severity == "error"]
            jsonl_cls = {"ingest.jsonl.crlf": "crlf", "ingest.jsonl.blank": "blank_line", "ingest.jsonl.nul": "nul",
                         "ingest.jsonl.no_final_newline": "no_final_newline"}  # fmt: skip
            for f in found:
                cls = jsonl_cls.get(f.code) or code_class(f.code)
                if f.severity != "info" or cls == "lone_surrogate":
                    out["classes"].append(cls)
            if errors and value is NO_VALUE and not self.lenient:
                if row["parse"] == "ok":
                    row["parse"] = code_class(errors[0].code)
                continue
            if errors and value is NO_VALUE:
                raw = lines[line_no] if line_no < len(lines) else b""
                classes, lenient = lenient_classes(raw.rstrip(b"\r"), self.limits)
                walker.undecodable |= "invalid_utf8" in classes
                out["classes"] += sorted(classes)
                if row["parse"] == "ok":
                    row["parse"] = code_class(errors[0].code) if code_class(errors[0].code) != "other" else (
                        sorted(classes)[0] if classes else "other")  # fmt: skip
                value = lenient
            if value is NO_VALUE:
                continue
            if rows_mode:
                walker.begin_unit()
                walker.walk(value)
                monotone = walker.end_unit()
                view = fam.autogen_row_unit(value, line_no)
                if view is None:
                    non_run += 1
                    continue
                self._unit(view, walker, out, monotone)
            else:
                walker.walk(value)
                values.append(value)
        if non_run:
            row["non_run_rows"] = non_run
        if not rows_mode:
            monotone = walker.end_unit()
            if self.dialect == "geminicli.stream_json":
                view = fam.geminicli_stream_unit(values, label)
            else:  # pragma: no cover - no other file-mode JSONL family
                view = fam.UnitView()
            if not data:
                view.flags.append("empty_stream")
            self._unit(view, walker, out, monotone)
        row["facets"] = facets

    def _scan_stream(self, data: bytes, label: str, out: dict[str, Any], walker: Walker) -> None:
        from agentprov.ingest.jsonstream import open_json_stream

        row = out["row"]
        segs = label.split("/")
        row["facets"] = {"split": fam.fv(segs[0] if len(segs) > 1 else None), "document": fam.fv(segs[-1].removesuffix(".json"))}
        limits = self.limits.replace(max_json_element_bytes=max(self.limits.max_json_element_bytes, 64 * MIB),
                                     max_jsonl_line_bytes=max(self.limits.max_jsonl_line_bytes, 64 * MIB))  # fmt: skip
        try:
            stream = open_json_stream(data, limits, arrays=("/traces",))
            out["classes"] += sorted({code_class(f.code) for f in stream.findings})
            walker.walk(stream.envelope)
            for item in stream:
                walker.begin_unit()
                walker.walk(item.value, "/traces/*")
                self._unit(fam.mcphunt_trace_unit(item.value, item.index), walker, out, walker.end_unit())
        except IngestError as exc:
            row["parse"] = code_class(exc.code)
            out["classes"].append(code_class(exc.code))

    def _scan_eval(self, data: bytes, label: str, out: dict[str, Any], walker: Walker) -> None:
        from agentprov.ingest.archives import iter_zip_members, open_zip

        row = out["row"]
        try:
            archive = open_zip(io.BytesIO(data), self.limits, release=False)
        except IngestError as exc:
            row["parse"] = "archive:" + exc.code.rsplit(".", 1)[-1]
            row["facets"] = fam.inspect_log_facets(None, label, self.ctx)[0]
            row["flags"].append("unreadable_container")
            return
        header: Any = None
        samples: list[tuple[str, Any]] = []
        members = sorted(iter_zip_members(archive), key=lambda m: (m.label or "", m.index))
        counts: Counter[str] = Counter()
        for m in members:
            if m.disposition != "selected" or m.label is None:
                counts["member_rejected"] += 1
                out["classes"].append("member_rejected")
                continue
            if not m.label.endswith(".json"):
                counts["member_other"] += 1
                continue
            try:
                raw = archive.read_member(m)
            except IngestError as exc:
                out["classes"].append(code_class(exc.code))
                counts["member_unreadable"] += 1
                continue
            parsed = self._parse_into(raw, out, walker)
            if parsed.value is NO_VALUE:
                counts["member_unparseable"] += 1
                continue
            if m.label == "header.json":
                header = parsed.value
                walker.walk(parsed.value, "header.json:")
            elif fam.is_sample_member(m.label):
                samples.append((m.label, parsed.value))
            else:
                prefix = "_journal:" if m.label.startswith("_journal/") else m.label + ":"
                walker.walk(parsed.value, prefix)
        facets, flags = fam.inspect_log_facets(header, label, self.ctx)
        row["facets"] = facets
        row["flags"] += flags
        row["members"] = dict(sorted(counts.items()))
        for member, value in samples:
            walker.begin_unit()
            walker.walk(value, "samples:")
            self._unit(fam.inspect_sample_unit(value, member, self.ctx), walker, out, walker.end_unit())
            if header is None:
                out["units"][-1]["flags"].append("no_header")

    # -------------------------------------------------------------------------- finish
    def _finish(self, out: dict[str, Any], walker: Walker) -> dict[str, Any]:
        row = out["row"]
        units = out["units"]
        row["n_units"] = len(units)
        if out["aux"]:
            row.pop("stratum", None)
        if len(units) == 1 and not units[0]["locator"]:
            u = units[0]
            row["facets"] = {**row["facets"], **u["facets"]}
            row["fp"] = u["fp"]
            row["flags"] += u["flags"]
            row["outcomes"] = u["outcomes"]
            if u["variant"]:
                row["variant"] = u["variant"]
            row["ts"]["monotone"] = u["monotone"]
        elif units:
            fps = [u["fp"] for u in units]
            row["fp"] = fingerprint(fps)[0] if any(fps) else None
            uf: dict[str, Counter[str]] = defaultdict(Counter)
            oc: dict[str, Counter[str]] = defaultdict(Counter)
            uflags: Counter[str] = Counter()
            monotone: bool | None = None
            for u in units:
                for k, v in u["facets"].items():
                    uf[k][v] += 1
                for k, v in u["outcomes"].items():
                    oc[k][json.dumps(v)] += 1
                uflags.update(u["flags"])
                if u["monotone"] is not None:
                    monotone = u["monotone"] if monotone is None else (monotone and u["monotone"])
            row["unit_facets"] = {k: dict(sorted(c.items())) for k, c in sorted(uf.items())}
            row["outcomes"] = {k: dict(sorted(c.items())) for k, c in sorted(oc.items())}
            row["unit_flags"] = dict(sorted(uflags.items()))
            row["ts"]["monotone"] = monotone
        if "aux_outcomes" in out:
            row["outcomes"] = out.pop("aux_outcomes")
        if walker.big_ints:  # parsed integers beyond I-JSON (the strict loader accepts them below its digit limit)
            out["classes"].append("big_int")
        classes = sorted(set(out["classes"]) - {"ok"})
        row["flags"] = sorted(set(row["flags"]) | {f"parse:{c}" for c in classes} | l106_flags(walker.strings))
        if not out["aux"]:
            row["stratum"] = fam.stratum_of(row["facets"], self.strata)
        row["ts"]["present"] = bool(walker.ts)
        row["ts"]["tz"] = sorted({f for s in walker.ts.values() for f in s.forms})
        out["walk"] = {"ptr": dict(walker.ptr), "strings": dict(walker.strings),
                       "ts": {p: s.to_json() for p, s in walker.ts.items()},
                       "accounts": {k: sorted(v) for k, v in walker.accounts.items()}}  # fmt: skip
        out["classes"] = classes
        return out


def l106_flags(strings: Mapping[str, int]) -> set[str]:
    """The artefact's L1-06 classes as row flags (``account_path_named``/``account_path_generic``, ``secret_like``,
    ``local_path_model``, ``operator_home``, ``withhold_rule``): class names only, never a value."""
    out: set[str] = set()
    for key, n in strings.items():
        check, _, cls = key.partition("\t")
        if check != "L1-06" or n <= 0:
            continue
        if cls.startswith("account:") and cls.endswith((":named", ":generic")):
            out.add("account_path_" + cls.rsplit(":", 1)[1])
            continue
        out |= {flag for prefix, flag in L106_FLAGS if cls.startswith(prefix)}
    return out


def withhold_rules(profile: Any) -> list[Any]:
    """The profile's ``[withhold]`` marker and pattern rules, compiled by the product (``corpus.withhold``)."""
    from agentprov.corpus.withhold import parse_policy

    def plain(value: Any) -> Any:  # the loaded profile is frozen (mappingproxy, tuples); the parser wants TOML types
        if isinstance(value, Mapping):
            return {k: plain(v) for k, v in value.items()}
        if isinstance(value, list | tuple):
            return [plain(v) for v in value]
        return value

    try:
        policy = parse_policy(plain(profile.data), profile_id=profile.id, profile_version=profile.version,
                              profile_sha256=profile.sha256)  # fmt: skip
    except Exception:  # noqa: BLE001 - an issue-only or malformed table: no byte rule to count
        return []
    return list(policy.rules) if policy is not None else []


# ================================================================================================ selection
@dataclass(frozen=True)
class _Cand:
    label: str
    size: int
    origin: Any = None


class _Listed:
    def __init__(self, items: Sequence[_Cand]) -> None:
        self._items = list(items)

    def walk(self) -> Iterator[_Cand]:
        return iter(self._items)

    def open(self, label: str, *, max_bytes: int) -> bytes:  # pragma: no cover - readers only walk
        raise RuntimeError("selection never opens a file")


def match(label: str, glob: str) -> bool:
    from agentprov.adapters.runner.importer import _match

    return bool(_match(label, glob))


def classify(entries: Sequence[Entry], profile: Any) -> dict[str, str]:
    """The disposition of every entry, as the importer decides it: ``selected`` (a reader candidate), ``context``,
    ``blob``, ``excluded:<code>[:<owner>]``, ``auxiliary`` (included, not a primary), ``stray``, ``not_selected``, or the
    walk's own disposition (``rejected:<code>``, ``nested``, ``absent_blob``)."""
    from agentprov.adapters.registry import READERS
    from agentprov.adapters.runner import resolve_factory

    imp = profile.data.get("import", {})
    dialect = str(imp.get("dialect"))
    reader = resolve_factory(READERS[dialect])()
    listed = [e for e in entries if e.disposition == "listed"]
    proxies = [_Cand(e.own, e.size) for e in listed]
    back = {id(p): e for p, e in zip(proxies, listed, strict=True)}
    chosen = {back[id(c)].label for c in reader.iter_artefacts(_Listed(proxies), profile)}
    # the per-unit auxiliaries the reader names (runner items R1/R2: judges, verdicts, siblings), same tree only
    named: set[str] = set()
    aux_for = getattr(reader, "auxiliary_for", None)
    if callable(aux_for):
        from agentprov.adapters.runner.importer import _AuxListing

        listing = _AuxListing([e.label for e in listed if not is_stray(e.label)], {})
        for label in chosen:
            named |= {ref for ref in aux_for(label, listing).values() if listing.exists(ref)}
    include = tuple(str(g) for g in imp.get("include", ()))
    excludes = [e for e in imp.get("exclude", ()) if isinstance(e, Mapping) and "glob" in e]
    context = tuple(str(g) for g in imp.get("context_artefacts", ()) if ":" not in str(g)) if dialect in CONSUMES_CONTEXT else ()
    blobs = tuple(str(g) for g in imp.get("blobs", ()))
    out: dict[str, str] = {}
    for e in entries:
        if e.disposition != "listed":
            hit = next((x for x in excludes if match(e.own, str(x["glob"]))), None) if e.disposition == "not_selected" else None
            out[e.label] = e.disposition + (f":excluded:{hit.get('code') or 'select.not_execution_artefact'}" if hit else "")
        elif is_stray(e.label):
            out[e.label] = "stray"
        elif e.label in chosen:
            out[e.label] = "selected"
        elif e.label in named:
            out[e.label] = "auxiliary"
        elif any(match(e.own, g) for g in context):
            out[e.label] = "context"
        elif any(match(e.own, g) for g in blobs):
            out[e.label] = "blob"
        elif (hit := next((x for x in excludes if match(e.own, str(x["glob"]))), None)) is not None:
            code = str(hit.get("code") or "select.not_execution_artefact")
            owner = hit.get("owner_corpus") or hit.get("owner")
            out[e.label] = f"excluded:{code}" + (f":{owner}" if code == "select.owned_elsewhere" and owner else "")
        elif any(match(e.own, g) for g in include):
            out[e.label] = "auxiliary"
        else:
            out[e.label] = "not_selected"
    return out


# ================================================================================================ resolution
def resolve(source: str, part: str, profile_id: str | None) -> tuple[Any, Any]:
    from agentprov.adapters.profiles import load_profile
    from agentprov.adapters.registry import get_source

    registration = get_source(source)
    cap = next((c for c in registration.capabilities if c.part == part), None)
    pid = profile_id or (cap.profile if cap is not None else None)
    if cap is not None and cap.via and profile_id is None:
        raise SystemExit(f"{source} · {part} is imported via {cap.via}: scan that part (or pass --profile)")
    if pid is None:
        raise SystemExit(f"no profile for {source} · {part}; pass --profile")
    profile = load_profile(pid)
    if str(profile.data.get("import", {}).get("dialect")) not in fam.HOOKS:
        raise SystemExit(f"profile {pid}: no L1 hook for dialect {profile.data.get('import', {}).get('dialect')}")
    return profile, cap


def pick_pin(profile: Any, part: str) -> dict[str, Any] | None:
    pins = [dict(p) for p in profile.data.get("source", {}).get("pins", ())]
    for predicate in (lambda p: p.get("part") == part and p.get("primary") is True, lambda p: p.get("role") == part,
                      lambda p: p.get("part") == part, lambda p: p.get("primary") is True):  # fmt: skip
        found = next((p for p in pins if predicate(p)), None)
        if found is not None:
            return found
    return None


def download_pins(profile: Any, part: str) -> list[dict[str, Any]]:
    """The download pins whose files are the part's archive inputs: the part's primary pins (every primary download pin of
    the part, e.g. RedCode's six trajectory zips, each with its own role since D-932). A ``url`` pin (Figshare 32657856, D-252) is a download pin too:
    ``verify_download`` checks it like the others, although the runner does not take it as an archive input yet
    (R-10j-3), so it is scanned here and imported nowhere."""
    pins = [dict(p) for p in profile.data.get("source", {}).get("pins", ())]
    first = pick_pin(profile, part)
    if first is None or first.get("kind") not in DOWNLOAD_KINDS:
        return []
    # D-932: the part's primary download pins whatever their role (RedCode's zips have one role each); a non-primary first
    # pin keeps the old rule (the pins of its role)
    if first.get("primary") is True:
        same = [p for p in pins if p.get("kind") in DOWNLOAD_KINDS and p.get("primary") is True
                and p.get("part", part) == first.get("part", part)]  # fmt: skip
    else:
        same = [p for p in pins if p.get("kind") in DOWNLOAD_KINDS and p.get("role") == first.get("role")
                and p.get("primary") is not True and p.get("part", part) == first.get("part", part)]  # fmt: skip
    return same or [first]


def registry_figure(source: str, part: str) -> dict[str, Any] | None:
    data = tomllib.loads((REPO / "tools" / "readme_corpora.toml").read_text(encoding="utf-8"))
    row = next((r for r in data.get("part", ()) if r.get("source") == source and r.get("part") == part), None)
    if row is None:
        return None
    return {k: row[k] for k in ("count", "unit", "basis", "evidence", "pointer", "where") if k in row}


def glob_roots(profile: Any) -> list[str]:
    """The literal leading directories of the profile's exclude and context globs (``src/agentdojo/defenses/drift/runs``
    of ``src/agentdojo/defenses/drift/runs/**``): walked besides the pin's tree so that owned-elsewhere and context files
    outside it are counted too."""
    imp = profile.data.get("import", {})
    globs = [str(e["glob"]) for e in imp.get("exclude", ()) if isinstance(e, Mapping) and "glob" in e]
    globs += [str(g) for g in imp.get("context_artefacts", ()) if ":" not in str(g)]
    roots: set[str] = set()
    for glob in globs:
        literal: list[str] = []
        for seg in glob.split("/")[:-1]:
            if any(c in seg for c in "*?["):
                break
            literal.append(seg)
        if literal:
            roots.add("/".join(literal))
    return sorted(roots)


def build_source(args: argparse.Namespace, profile: Any, part: str, limits: IngestLimits) -> tuple[Any, dict[str, Any]]:
    pin = pick_pin(profile, part)
    info: dict[str, Any] = {"pin": {k: pin.get(k) for k in ("kind", "role", "repo", "commit", "tree", "doi", "file",
                                                             "dataset", "revision", "sha256") if pin and k in pin}}  # fmt: skip
    if args.git:
        commit = args.commit or (pin or {}).get("commit")
        if not commit:
            raise SystemExit("--git needs --commit (the pin records none)")
        prefixes = args.tree or ([] if args.whole_tree else [str((pin or {}).get("tree") or "")])
        if prefixes and any(prefixes) and not args.tree:
            prefixes = minimal_prefixes([*prefixes, *glob_roots(profile)])
        info["input"] = {"mode": "git", "bare": shown_path(args.git), "commit": commit, "prefixes": prefixes}
        return GitSource(Path(args.git), commit, prefixes), info
    if args.use_pin:
        from agentprov.raw.fetch import Recipe, resolve_cache_dir

        if pin is None:
            raise SystemExit("the profile has no pin for this part")
        cache = resolve_cache_dir(args.cache)
        recipe = Recipe.from_pin(pin, canonical_repo=profile.data.get("source", {}).get("canonical_repo"))
        if pin.get("kind") == "git":
            assert recipe.commit is not None
            prefixes = [] if args.whole_tree else list(recipe.paths)
            if prefixes:
                prefixes = minimal_prefixes([*prefixes, *glob_roots(profile)])
            info["input"] = {"mode": "use-pin", "cache": shown_path(cache), "commit": recipe.commit, "prefixes": prefixes}
            return GitSource(recipe.cache_path(cache), recipe.commit, prefixes), info
        args.input = str(recipe.cache_path(cache))
    if not args.input:
        raise SystemExit("name the raw: --input PATH, --git BARE or --use-pin")
    path = Path(args.input).expanduser()
    downloads = download_pins(profile, part)
    if downloads:
        return archive_source(args, profile, downloads, path, limits, info)
    prefixes = args.tree or ([] if args.whole_tree or not pin or pin.get("kind") != "git" else [str(pin.get("tree") or "")])
    # the pin's tree is relative to the repository: when --input is that tree itself (adprov), walk the input whole
    prefixes = [p for p in prefixes if p and (path / p).is_dir()] if not args.tree else prefixes
    if prefixes and not args.tree:
        prefixes = minimal_prefixes([*prefixes, *(r for r in glob_roots(profile) if (path / r).is_dir())])
    info["input"] = {"mode": "local", "root": shown_path(path), "prefixes": prefixes}
    return LocalSource(path, prefixes, limits), info


def minimal_prefixes(prefixes: Iterable[str]) -> list[str]:
    """Drop every prefix another one already covers (so no file is walked twice)."""
    items = sorted({p.strip("/") for p in prefixes if p and p.strip("/")})
    return [p for p in items if not any(p != q and p.startswith(q + "/") for q in items)]


def archive_source(args: argparse.Namespace, profile: Any, pins: Sequence[Mapping[str, Any]], path: Path,
                   limits: IngestLimits, info: dict[str, Any]) -> tuple[ArchiveSource, dict[str, Any]]:  # fmt: skip
    from agentprov.ingest.paths import open_evidence
    from agentprov.raw.fetch import Recipe, is_split_pin, part_recipes, verify_download, verify_parts
    from agentprov.raw.members import Selection, nested_selection

    files: list[ArchiveFile] = []
    checked: list[dict[str, Any]] = []
    big = limits.replace(max_artefact_bytes=1 << 40)
    for pin in pins:
        relative = str(pin.get("file", pin.get("path")))
        name = relative.rsplit("/", 1)[-1]
        if is_split_pin(pin):
            directory = path if path.is_dir() else path.parent
            if "/" in relative and (directory / relative.rsplit("/", 1)[0]).is_dir():  # the pin's path below --input
                directory = directory / relative.rsplit("/", 1)[0]
            recipes = part_recipes(pin)
            parts = [(directory / str(r.file).rsplit("/", 1)[-1], int(r.size or 0)) for r in recipes]
            if not args.no_verify_pin:
                where = str(directory)

                def opener(n: str, where: str = where) -> IO[bytes]:
                    return open_evidence(where, n.rsplit("/", 1)[-1], big)

                verify_parts(opener, recipes)
            files.append(ArchiveFile(name, None, parts))
            checked.append({"file": name, "parts": len(parts), "verified": not args.no_verify_pin})
            continue
        local = path if path.is_file() else (path / relative if (path / relative).is_file() else path / name)
        if not local.is_file():
            if len(pins) == 1:
                raise SystemExit(f"archive input {name} not found under the --input path")
            checked.append({"file": name, "found": False})
            continue
        if not args.no_verify_pin:
            recipe = Recipe.from_pin(pin)
            with open_evidence(str(local.parent), local.name, big) as handle:
                verify_download(handle, local.name, recipe)
        files.append(ArchiveFile(name, local))
        checked.append({"file": name, "verified": not args.no_verify_pin})
    imp = profile.data.get("import", {})
    dialect = str(imp.get("dialect"))
    context = [str(g) for g in imp.get("context_artefacts", ()) if ":" not in str(g)] if dialect in CONSUMES_CONTEXT else []
    include = tuple(str(g) for g in (*imp.get("include", ()), *imp.get("blobs", ()), *context))
    nested = imp.get("nested")
    selection = nested_selection(include, nested) if nested else Selection(include=include)
    info["input"] = {"mode": "archive", "path": shown_path(path), "archives": checked, "nested_cap": args.nested_cap}
    return ArchiveSource(files, selection, limits, args.nested_cap), info


# ================================================================================================ aggregation
class Summary:
    def __init__(self, strata_keys: Sequence[str]) -> None:
        self.strata_keys = list(strata_keys)
        self.parse: Counter[str] = Counter()
        self.classes: Counter[str] = Counter()
        self.class_labels: dict[str, list[str]] = defaultdict(list)
        self.ptr: Counter[str] = Counter()
        self.artefacts_with: Counter[str] = Counter()
        self.ts: dict[str, TsStat] = {}
        self.accounts: dict[str, set[str]] = defaultdict(set)
        self.facets: dict[str, Counter[str]] = defaultdict(Counter)
        self.unit_facets: dict[str, Counter[str]] = defaultdict(Counter)
        self.strata: Counter[str] = Counter()
        self.strata_units: Counter[str] = Counter()
        self.flags: Counter[str] = Counter()
        self.unit_flags: Counter[str] = Counter()
        self.variants: Counter[str] = Counter()
        self.outcomes: dict[str, Counter[str]] = defaultdict(Counter)
        self.outcomes_by_stratum: dict[str, dict[str, Counter[str]]] = defaultdict(lambda: defaultdict(Counter))
        self.units = 0
        self.units_ts = Counter[str]()
        self.aux_parse: Counter[str] = Counter()
        self.aux_classes: Counter[str] = Counter()
        self.aux_ptr: Counter[str] = Counter()
        self.aux_files = 0

    def add(self, res: Mapping[str, Any]) -> None:
        row = res["row"]
        walk = res["walk"]
        if res["aux"]:
            self.aux_files += 1
            self.aux_parse[row["parse"]] += 1
            self.aux_classes.update(res["classes"])
            self.aux_ptr.update(walk["ptr"])
            for k, v in walk["accounts"].items():
                self.accounts[k].update(v)
            return
        self.parse[row["parse"]] += 1
        for c in res["classes"]:
            self.classes[c] += 1
            # the five smallest labels (code-point order), whatever order the workers finished in
            examples = self.class_labels[c]
            examples.append(row["label"])
            if len(examples) > 5:
                examples.sort()
                del examples[5:]
        self.ptr.update(walk["ptr"])
        for key in walk["strings"]:
            self.artefacts_with[key] += 1
        for pointer, stat in walk["ts"].items():
            st = TsStat(stat["count"], Counter(stat["forms"]), stat["parse_fail"], stat["min_date"], stat["max_date"],
                        stat["units_non_monotone"], stat["units_with"])  # fmt: skip
            self.ts.setdefault(pointer, TsStat()).merge(st)
        for k, v in walk["accounts"].items():
            self.accounts[k].update(v)
        for k, v in row["facets"].items():
            self.facets[k][v] += 1
        for k, counts in row.get("unit_facets", {}).items():
            for v, n in counts.items():
                self.unit_facets[k][v] += n
        n = max(row["n_units"], 0)
        self.units += n
        self.strata[row["stratum"]] += 1
        self.strata_units[row["stratum"]] += n
        self.flags.update(row["flags"])
        self.unit_flags.update(row.get("unit_flags", {}))
        if row.get("variant"):
            self.variants[row["variant"]] += 1
        for k, v in (row.get("outcomes") or {}).items():
            if isinstance(v, dict):
                for value, count in v.items():
                    self.outcomes[k][value] += count
                    if value in ("true", "false", "null"):
                        self.outcomes_by_stratum[row["stratum"]][k][value] += count
            else:
                text = json.dumps(v)
                self.outcomes[k][text] += 1
                if isinstance(v, bool) or v is None:
                    self.outcomes_by_stratum[row["stratum"]][k][text] += 1
        self.units_ts["with" if row["ts"]["present"] else "without"] += 1
        if row["ts"]["monotone"] is False:
            self.units_ts["artefacts_non_monotone"] += 1


def safe_label(label: str) -> str:
    """A label as written into the committed summary: one carrying a workstation path is replaced by its digest."""
    if fam._ACCOUNTISH.search(label) or not label.isprintable():
        return "#sha256:" + hashlib.sha256(label.encode("utf-8", "surrogatepass")).hexdigest()[:16]
    return label


def top_pointers(ptr: Counter[str], check: str) -> dict[str, Any]:
    by_class: dict[str, Counter[str]] = defaultdict(Counter)
    for key, n in ptr.items():
        if n <= 0:
            continue
        c, cls, pointer = key.split("\t", 2)
        if c == check:
            by_class[cls][pointer] += n
    return {cls: {"strings": sum(c.values()), "distinct_pointers": len(c),
                  "pointers": dict(ranked(c)[:_TOP])} for cls, c in sorted(by_class.items())}  # fmt: skip


def ranked(counter: Mapping[str, int]) -> list[tuple[str, int]]:
    """``(key, n)`` by descending n, ties by key: independent of the order the parallel workers finished in."""
    return sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))


def capped(counter: Counter[str], cap: int = 400) -> dict[str, int]:
    items = ranked(counter)
    out = dict(sorted(items[:cap]))
    if len(items) > cap:
        out["<other>"] = sum(n for _k, n in items[cap:])
    return out


# ================================================================================================ main
def run(args: argparse.Namespace) -> dict[str, Any]:
    started = time.perf_counter()
    profile, cap = resolve(args.source, args.part, args.profile)
    part = args.part
    corpus_id = args.corpus_id or (cap.corpus_id if cap is not None and cap.corpus_id else args.source)
    limits = IngestLimits()
    source, info = build_source(args, profile, part, limits)
    entries = source.entries()
    disposition = classify(entries, profile)
    imp = profile.data.get("import", {})
    dialect = str(imp.get("dialect"))
    primaries = sorted((e for e in entries if disposition[e.label] == "selected"), key=lambda e: e.label.encode("utf-8"))
    if args.limit:
        primaries = primaries[: args.limit]
    dirs = {e.label.rsplit("/", 1)[0] for e in primaries}
    aux = [] if args.no_aux else [e for e in entries if disposition[e.label] in ("auxiliary", "context")
                                  and e.own.lower().endswith((".json", ".jsonl"))
                                  and (not args.limit or e.label.rsplit("/", 1)[0] in dirs)]  # fmt: skip
    progress(f"{args.source} · {part}: {len(entries)} walked, {len(primaries)} selected, {len(aux)} auxiliary")

    needles: list[str] = []
    try:  # loaded by path (tools/ is not put on sys.path, so no module there can shadow another)
        from l2_common import personal_needles

        needles = [n.decode("utf-8", "replace") for n in personal_needles().get("home-path", [])]
    except Exception:  # noqa: BLE001 - the home-path check is optional
        needles = []
    cfg = {"profile_id": profile.id, "part": part, "source": source.spec(), "home_needles": needles,
           "lfs_dir": args.lfs_dir, "pin_check": bool(args.pin_check),
           "lenient": bool(args.lenient_classes)}  # fmt: skip
    oids = {e.label: e.sha1 for e in entries}
    results: list[dict[str, Any]] = []
    summary = Summary(fam.strata_keys(profile.id, dialect))
    sha1s: dict[str, str] = {}

    def tasks() -> Iterator[tuple[str, int, bytes | IngestError | None, str | None, bool]]:
        is_aux = {e.label: False for e in primaries} | {e.label: True for e in aux}
        if isinstance(source, ArchiveSource):
            for label, size, data in source.stream(set(is_aux)):
                yield label, size, data, None, is_aux[label]
            return
        for e in [*primaries, *aux]:
            yield e.label, e.size, None, oids.get(e.label), is_aux[e.label]

    variant_parts = bool(imp.get("variant_labels"))
    other_part: Counter[str] = Counter()

    def consume(res: dict[str, Any]) -> None:
        # an agentdyn-style part: a file whose variant belongs to another part is not this part's unit
        vp = res["row"]["facets"].get("variant_part") if variant_parts and not res["aux"] else None
        if vp is not None and vp != part:
            other_part[str(vp)] += 1
            return
        summary.add(res)
        if res.get("sha1"):
            sha1s[res["row"]["label"]] = res["sha1"]
        res.pop("walk", None)
        results.append(res)
        if len(results) % 500 == 0:
            progress(f"  {len(results)} scanned ({time.perf_counter() - started:.0f} s)")

    if args.jobs <= 1:
        scanner = Scanner(cfg)
        for task in tasks():
            consume(scanner.scan(*task))
    else:
        window = args.jobs * 4
        with cf.ProcessPoolExecutor(args.jobs, initializer=_init_worker, initargs=(cfg,)) as pool:
            pending: set[cf.Future[dict[str, Any]]] = set()
            for task in tasks():
                pending.add(pool.submit(_work, task))
                if len(pending) >= window:
                    done, pending = cf.wait(pending, return_when=cf.FIRST_COMPLETED)
                    for f in done:
                        consume(f.result())
            for f in cf.as_completed(pending):
                consume(f.result())

    unit_rows = sorted((r for r in results if not r["aux"]), key=lambda r: r["row"]["label"].encode("utf-8", "surrogatepass"))
    aux_rows = sorted((r for r in results if r["aux"]), key=lambda r: r["row"]["label"].encode("utf-8", "surrogatepass"))
    join_aux_outcomes(unit_rows, aux_rows, summary)
    scratch = Path(args.scratch).expanduser() if args.scratch else precheck_root() / corpus_id
    scratch.mkdir(parents=True, exist_ok=True)
    suffix = f".limit{args.limit}" if args.limit else ""
    rows_path = scratch / f"l1-units-{part}{suffix}.jsonl"
    with guard_output(rows_path).open("w", encoding="utf-8") as fh:
        for r in unit_rows:
            fh.write(json.dumps(r["row"], sort_keys=True) + "\n")
    with guard_output(scratch / f"l1-aux-{part}{suffix}.jsonl").open("w", encoding="utf-8") as fh:
        for r in aux_rows:
            fh.write(json.dumps(r["row"], sort_keys=True) + "\n")
    if args.emit_fp:
        fp_dir = scratch / "_fp" if args.scratch else precheck_root() / "_fp"
        fp_dir.mkdir(parents=True, exist_ok=True)
        with guard_output(fp_dir / f"{args.source}.{part}{suffix}.jsonl").open("w", encoding="utf-8") as fh:
            for r in unit_rows:
                row = r["row"]
                base = {"sha256": row["sha256"], "label": row["label"], "corpus_id": corpus_id, "stratum": row["stratum"],
                        "source": args.source, "part": part}
                if len(r["units"]) == 1 and not r["units"][0]["locator"]:
                    fh.write(json.dumps({"fp": row["fp"], **base}, sort_keys=True) + "\n")
                elif not r["units"]:
                    fh.write(json.dumps({"fp": None, **base}, sort_keys=True) + "\n")
                for u in r["units"] if r["units"] and r["units"][0]["locator"] else ():
                    fh.write(json.dumps({"fp": u["fp"], "unit": u["locator"], **base}, sort_keys=True) + "\n")

    report = build_summary(args, profile, cap, corpus_id, info, entries, disposition, source, primaries, aux_rows,
                           unit_rows, summary, other_part, sha1s, started)  # fmt: skip
    out_path = Path(args.summary_out) if args.summary_out else (
        scratch / f"l1-{part}{suffix}.json" if args.limit else DATA_DIR / corpus_id / f"l1-{part}.json")  # fmt: skip
    out_path.parent.mkdir(parents=True, exist_ok=True)
    guard_output(out_path).write_text(json.dumps(report, indent=1, sort_keys=False) + "\n", encoding="utf-8")
    progress(f"wrote {shown_path(out_path)} and {shown_path(rows_path)} in {time.perf_counter() - started:.1f} s")
    return report


def join_aux_outcomes(unit_rows: Sequence[dict[str, Any]], aux_rows: Sequence[dict[str, Any]], summary: Summary) -> None:
    """The outcome a directory's auxiliary file holds (a DTap judge, a gemini-cli verdict) joins the unit rows of that
    directory as ``aux.<name>`` (a judge-only or verdict-only primary already carries it)."""
    by_dir: dict[str, dict[str, Any]] = {}
    for r in aux_rows:
        outcomes = r["row"].get("outcomes")
        if outcomes:
            directory = r["row"]["label"].rpartition("/")[0]
            by_dir.setdefault(directory, {}).update({f"aux.{k}": v for k, v in outcomes.items()})
    for r in unit_rows:
        row = r["row"]
        joined = by_dir.get(row["label"].rpartition("/")[0])
        if not joined:
            continue
        row.setdefault("outcomes", {}).update(joined)
        for k, v in joined.items():
            text = json.dumps(v)
            summary.outcomes[k][text] += 1
            if isinstance(v, bool) or v is None:
                summary.outcomes_by_stratum[row["stratum"]][k][text] += 1


def build_summary(args: argparse.Namespace, profile: Any, cap: Any, corpus_id: str, info: dict[str, Any],
                  entries: Sequence[Entry], disposition: Mapping[str, str], source: Any, primaries: Sequence[Entry],
                  aux_rows: Sequence[Mapping[str, Any]], unit_rows: Sequence[Mapping[str, Any]], s: Summary,
                  other_part: Mapping[str, int], sha1s: Mapping[str, str], started: float) -> dict[str, Any]:  # fmt: skip
    disp: Counter[str] = Counter(disposition.values())
    excluded = {k.split(":", 1)[1]: n for k, n in disp.items() if k.startswith("excluded:")}
    rejected = Counter(code for _l, code in source.rejected)
    pin_check: dict[str, Any] | None = None
    if args.pin_check and isinstance(source, LocalSource) and sha1s:
        pin_check = pin_listing_check(profile, args.part, sha1s, args.cache)
    rows = [r["row"] for r in unit_rows]
    by_sha: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        if row["sha256"]:
            by_sha[row["sha256"]].append(row["label"])
    unit_fps: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for r in unit_rows:
        if len(r["units"]) == 1 and not r["units"][0]["locator"]:
            if r["row"]["fp"]:
                unit_fps[r["row"]["fp"]].append((r["row"]["label"], ""))
        else:
            for u in r["units"]:
                if u["fp"]:
                    unit_fps[u["fp"]].append((r["row"]["label"], u["locator"]))
    facet_of = {row["label"]: row["facets"] for row in rows}
    fp_groups = {fp: members for fp, members in unit_fps.items() if len(members) > 1}
    differing: Counter[str] = Counter()
    for members in fp_groups.values():
        labels = {lbl for lbl, _u in members}
        for key in {k for lbl in labels for k in facet_of.get(lbl, {})}:
            if len({facet_of.get(lbl, {}).get(key) for lbl in labels}) > 1:
                differing[key] += 1
    biggest = sorted(fp_groups.values(), key=len, reverse=True)[:20]
    report: dict[str, Any] = {
        "tool": "tools/precheck/l1_scan.py", "tool_version": TOOL_VERSION, "code_commit": code_commit(),
        "date": dt.datetime.now(dt.UTC).strftime("%Y-%m-%d"), "source": args.source, "part": args.part,
        "corpus_id": corpus_id, "limit": args.limit or None,
        "profile": {"id": profile.id, "version": profile.version, "sha256": profile.sha256},
        "dialect": str(profile.data.get("import", {}).get("dialect")), **info,
        "registry": {"import_status": getattr(cap, "import_status", None), "figure": registry_figure(args.source, args.part)},
        "strata_keys": s.strata_keys,
        "L1-01": {"walked": len(entries), "dispositions": dict(sorted(disp.items())), "excluded_by_code": excluded,
                  "rejected_by_code": dict(sorted(rejected.items())), "strays_skipped_by_walk": source.skipped,
                  "selected_artefacts": len(primaries), "scanned_artefacts": len(rows), "units": s.units,
                  "other_variant_part": dict(sorted(other_part.items())), "auxiliary_scanned": len(aux_rows),
                  "archive_findings": dict(sorted(getattr(source, "findings", {}).items())), "pin_check": pin_check},
        "L1-02": {"denominator_artefacts": len(rows), "by_primary_class": dict(sorted(s.parse.items())),
                  "artefacts_with_class": dict(sorted(s.classes.items())),
                  "example_labels": {k: [safe_label(x) for x in sorted(v)] for k, v in sorted(s.class_labels.items())},
                  "parsed_ints_beyond_i_json": top_pointers(s.ptr, "L1-02"),
                  "auxiliary": {"files": s.aux_files, "by_primary_class": dict(sorted(s.aux_parse.items())),
                                "with_class": dict(sorted(s.aux_classes.items()))}},
        "L1-03": {"denominator_artefacts": len(rows),
                  "artefacts_with": {k.split("\t", 1)[1]: n for k, n in sorted(s.artefacts_with.items()) if k.startswith("L1-03")},
                  "classes": top_pointers(s.ptr, "L1-03"), "auxiliary": top_pointers(s.aux_ptr, "L1-03")},
        "L1-04": {"byte_identical": {"groups": sum(1 for v in by_sha.values() if len(v) > 1),
                                     "artefacts_in_groups": sum(len(v) for v in by_sha.values() if len(v) > 1),
                                     "largest": [sorted(safe_label(x) for x in v)[:5] + ([f"+{len(v) - 5}"] if len(v) > 5 else [])
                                                 for v in sorted((v for v in by_sha.values() if len(v) > 1), key=len, reverse=True)[:10]]},
                  "trajectory_identical": {"groups": len(fp_groups), "units_in_groups": sum(len(v) for v in fp_groups.values()),
                                           "units_with_fp": sum(len(v) for v in unit_fps.values()),
                                           "distinct_fp": len(unit_fps), "facets_differing_in_groups": dict(sorted(differing.items())),
                                           "largest": [{"size": len(m), "labels": [safe_label(lbl) + (f"#{u}" if u else "")
                                                                                   for lbl, u in m[:5]]} for m in biggest]},
                  "cross_part": "tools/precheck/l1_xdup.py over the _fp files"},
        "L1-05": {"facets": {k: capped(c) for k, c in sorted(s.facets.items())},
                  "unit_facets": {k: capped(c) for k, c in sorted(s.unit_facets.items())},
                  "strata": {"n": len(s.strata), "artefacts": capped(s.strata, 1000), "units": capped(s.strata_units, 1000)}},
        "L1-06": {"denominator_artefacts": len(rows),
                  "artefacts_with": {k.split("\t", 1)[1]: n for k, n in sorted(s.artefacts_with.items()) if k.startswith("L1-06")},
                  "classes": top_pointers(s.ptr, "L1-06"), "auxiliary": top_pointers(s.aux_ptr, "L1-06"),
                  "named_accounts_distinct": {k: len(v) for k, v in sorted(s.accounts.items())},
                  "note": "counts and normalised pointers only; account names are never recorded (distinct counts by digest)"},
        "L1-07": {"artefacts": dict(sorted(s.units_ts.items())), "pointers": {p: st.to_json() for p, st in
                                                             sorted(s.ts.items(), key=lambda kv: (-kv[1].count, kv[0]))[:_TOP * 2]},
                  "distinct_pointers": len(s.ts)},
        "L1-08": {"denominator_artefacts": len(rows), "flags": dict(sorted(s.flags.items())),
                  "unit_flags": dict(sorted(s.unit_flags.items()))},
        "family": {"variants": dict(sorted(s.variants.items())),
                   "outcomes": {k: dict(sorted(c.items())) for k, c in sorted(s.outcomes.items())},
                   "outcomes_by_stratum": {st: {k: dict(sorted(c.items())) for k, c in sorted(v.items())}
                                           for st, v in sorted(s.outcomes_by_stratum.items())}},
        "elapsed_s": round(time.perf_counter() - started, 1), "jobs": args.jobs,
    }  # fmt: skip
    return report


def pin_listing_check(profile: Any, part: str, sha1s: Mapping[str, str], cache: str | None) -> dict[str, Any]:
    """For a local tree under a git pin whose commit is in the fetch cache: scanned files whose git blob SHA-1 equals the
    pin's entry, differ from it, or are not in the pin's tree."""
    from agentprov.raw.fetch import Fetcher, Recipe, resolve_cache_dir

    pin = pick_pin(profile, part)
    if not pin or pin.get("kind") != "git":
        return {"skipped": "no git pin"}
    try:
        recipe = Recipe.from_pin(pin, canonical_repo=profile.data.get("source", {}).get("canonical_repo"))
        entries, _ = Fetcher(resolve_cache_dir(cache)).git_tree(recipe)
    except Exception as exc:  # noqa: BLE001 - not cached: reported, not fatal
        return {"skipped": type(exc).__name__}
    listing = {e.path: e.oid for e in entries if e.is_blob}
    verdict = Counter("verified" if listing.get(label) == sha else ("mismatch" if label in listing else "not_in_pin")
                      for label, sha in sha1s.items())  # fmt: skip
    return dict(sorted(verdict.items()))


def code_commit() -> str | None:
    try:
        return subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"], capture_output=True, text=True,  # noqa: S603, S607
                              check=True).stdout.strip()  # fmt: skip
    except (OSError, subprocess.CalledProcessError):
        return None


def progress(text: str) -> None:
    print(text, file=sys.stderr, flush=True)


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--source", required=True)
    p.add_argument("--part", required=True)
    p.add_argument("--corpus-id")
    p.add_argument("--profile", help="source profile id (default: the registry part's)")
    src = p.add_mutually_exclusive_group()
    src.add_argument("--input", help="a local tree (clone, worktree, staged directory) or the archive input file/directory")
    src.add_argument("--git", help="a bare repository holding the pinned commit (fetch cache or staging clone; read only)")
    src.add_argument("--use-pin", action="store_true", help="read the pin from the fetch cache (--cache)")
    p.add_argument("--commit", help="with --git: the commit (default: the pin's)")
    p.add_argument("--tree", action="append", help="path prefix to walk (default: the pin's tree); repeatable")
    p.add_argument("--whole-tree", action="store_true", help="walk the whole tree, not only the pin's tree prefix")
    p.add_argument("--cache", help="fetch cache directory (default: the product's resolution)")
    p.add_argument("--lfs-dir", help="directory of Git LFS objects named by sha256 (DTap): scanned instead of the pointer")
    p.add_argument("--no-verify-pin", action="store_true", help="archive inputs: skip the size/MD5/SHA-256 check")
    p.add_argument("--pin-check", action="store_true", help="local tree: compare each file's git blob SHA-1 with the cached pin")
    p.add_argument("--nested-cap", type=int, default=768 * MIB, help="largest nested archive opened in memory (bytes)")
    p.add_argument("--jobs", type=int, default=2)
    p.add_argument("--lenient-classes", action="store_true",
                   help="opt-in: re-parse bytes the strict ingest loader rejected with stdlib json to count every parse "
                        "class (outside agentprov.ingest; default off: the strict loader's first class only)")
    p.add_argument("--limit", type=int, help="scan only the first N selected artefacts (smoke; outputs stay in scratch)")
    p.add_argument("--emit-fp", action="store_true", help="write <precheck root>/_fp/<source>.<part>.jsonl")
    p.add_argument("--no-aux", action="store_true", help="skip the auxiliary JSON files")
    p.add_argument("--summary-out", help="write the summary here instead of the default")
    p.add_argument("--scratch", help="write the unit/aux rows (and with --emit-fp the _fp file) here instead of "
                                     "<precheck root>/<corpus_id> (a smoke that must not leave the part's rows behind)")
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    run(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
