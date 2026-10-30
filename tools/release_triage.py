"""Release-scan triage writer (C-3; G.9.4, D-42): reviewed class decisions -> ``<corpus>.release-triage.toml``.

Usage::

    uv run python tools/release_triage.py CORPUS_DIR --decisions DECISIONS.toml [--scan SCAN.json] [--suites DIR ...]
        [--out PATH] [--gitleaks PATH] [--timeout S]
    uv run python tools/release_triage.py CORPUS_DIR --report [--scan SCAN.json] [--suites DIR ...] [--gitleaks PATH]
    uv run python tools/release_triage.py CORPUS_DIR --list-secrets [--scan SCAN.json] [--suites DIR ...] [--show]

A sealed corpus's release scan (``tools/release_scan.py``) leaves its ``gitleaks`` and ``account-path`` findings
untriaged: a person decides them. They are decided **by class, never by value** (pre-release check 4): a gitleaks finding
by its rule, the key name in front of the redacted match and its origin; an account path by the per-corpus ordinal of its
account name. This tool computes those classes on the sealed tree, applies a reviewed decisions file to them and writes
the ``[[triage]]`` file that ``release_scan.py --triage`` reads, bound to the sealed root digest (D-42). The file goes
beside the sealed tree as ``<corpus>.release-triage.toml``, next to ``<corpus>.release-scan.json`` (D-609), outside the
checksummed tree; a path inside it is refused.

* **Input scan.** ``--scan`` (default ``<corpus>.release-scan.json`` beside the corpus) is the corpus's scan document
  without a triage file. Its root digest must be the corpus's and its tools the pinned ones; only its findings with
  ``triage: null`` get an entry (a rule-cleared ``email-address`` finding keeps its rule).
* **Origin of a gitleaks finding** (check 4b). gitleaks runs again on the sealed tree, redacted (the pinned scanner and
  configuration of ``release_scan.py``; its fingerprints must equal the scan document's), only for the key names.
  ``upstream-data``: a 16+ character token of the finding's line (for ``private-key``, the ``-----BEGIN ... PRIVATE
  KEY-----`` header) occurs in the benchmark's own suite data (``--suites``, files up to 32 MiB). ``benchmark-input``:
  an AER record the benchmark supplies (``k`` in :data:`INPUT_KINDS` or ``role`` in :data:`INPUT_ROLES`).
  ``model-generated``: any other AER record (an assistant message, a tool call, a state change after a call). A PROV,
  SEM or raw-object copy takes the origin of its execution's AER findings with the same rule and key: their one origin,
  or, for one execution with several, the n-th copy in the file pairs with the n-th AER finding when the counts are
  equal; failing that, the same with the rule alone (a copy's line can carry other report entries than its AER line);
  failing both, check 4b's own rule: the n-th copy takes the n-th AER finding in line order (key, then rule alone), as
  for a PROV document whose one line copies an execution's findings of several origins. ``unclassified``: none of these. A line with several report entries has their key names joined with ``+``, sorted
  (gitleaks' report order is not fixed, so no one entry is taken).
* **Ordinal of an account path** (check 4c; the post-check's method). The distinct account names of the scan's
  ``account-path`` findings are numbered ``#1, #2, ...`` in order of first appearance, files in label order and offsets
  in file order (trailing dots stripped; the same names ``release_scan.Accounts`` reports). A finding in an archive
  member (``<archive>#<locator>``, D-491) is read from the member decoded, as the scan read it (its name first, line 0,
  then its data), in memory only. Names are held in memory only: neither a name nor a digest of one is written or
  printed.
* **Decisions** (TOML, ``format = "agentprov-triage-decisions/0.1"``; value-blind, so it can be reviewed and kept in the
  repository): a ``root_digest``, ``[[secret]]`` rows ``{rule, key, origin, triage, findings, reason}`` and
  ``[[account]]`` rows ``{ordinal, triage, hits, reason}``. ``triage`` is ``synthetic-benchmark``, ``model-generated`` or
  ``false-positive`` (never ``real``: that is a person's entry, written by hand); an ``[[account]]`` row may also give
  ``pinned-account`` (D-604 item 7: a third-party account in a raw object that ships as pinned), only for an ordinal
  whose hits are all ``raw-object`` (the deposit builder accepts it in ``raw/`` only). ``findings`` (a gitleaks class) and
  ``hits`` (an ordinal's matches by area, ``aer``/``prov``/``sem``/``raw-object``/...) are the counts the review saw; any
  other count is refused, nothing is written, so a decision never lands on a class it was not made for. An account
  finding whose line holds several ordinals takes the first triage of :data:`ACCOUNT_ORDER` among theirs and names each.
* **Never a value.** Fingerprints, rules, key names (a plain identifier of at most 40 characters, else ``(none)``),
  origins, ordinals and counts only. ``--report`` prints the classes and their counts as JSON, which is what a person
  reviews to write the decisions file. ``--list-secrets`` prints one line per distinct gitleaks value: an HMAC-SHA256
  under a random per-run key (16 hex; comparable within one run, never across runs), its rule, keys, origins, findings
  and layers. Only with ``--show``, and only when standard output is a terminal (the user's own), does it add the
  value, fenced by :func:`agentprov.ingest.quote.quote_untrusted`; values come from a second, unredacted gitleaks run
  read from its standard output, never from a file.

Exit codes: 0 written and every finding of the scan triaged (or a report printed); 1 written, but findings remain
untriaged; 2 usage, a refused input or a decision whose count differs (nothing written); 3 gitleaks failed.
"""

from __future__ import annotations

import argparse
import bisect
import hashlib
import hmac
import json
import os
import re
import secrets
import shutil
import sys
import tomllib
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

sys.path.insert(0, str(Path(__file__).resolve().parent))
import release_scan as rs  # noqa: E402

DECISIONS_FORMAT: Final = "agentprov-triage-decisions/0.1"
TRIAGE_SUFFIX: Final = ".release-triage.toml"
#: The triages a decision may give (C-3): ``real`` is never written by a tool.
DECISION_TRIAGES: Final = frozenset({"synthetic-benchmark", "model-generated", "false-positive"})
#: An ``[[account]]`` row may also give ``pinned-account`` (D-604 item 7), for an ordinal found in raw objects only.
ACCOUNT_TRIAGES: Final = DECISION_TRIAGES | {"pinned-account"}
#: An account finding with several ordinals on its line takes the first of their triages in this order.
ACCOUNT_ORDER: Final = ("pinned-account", "model-generated", "synthetic-benchmark", "false-positive")
ORIGINS: Final = ("upstream-data", "benchmark-input", "model-generated", "unclassified")
INPUT_KINDS: Final = frozenset({"execution", "fixture", "scope", "actor"})
INPUT_ROLES: Final = frozenset({"user", "tool", "system", "environment"})
NO_KEY: Final = "(none)"
_TOKEN: Final = re.compile(rb"[A-Za-z0-9+/=_-]{16,}")
_KEY: Final = re.compile(r"""([A-Za-z_][A-Za-z0-9_.-]{0,40})["']?\s*[:=>]+\s*["']?[^"']*REDACTED""")
_IDENT: Final = re.compile(r"[A-Za-z_][A-Za-z0-9_.-]{0,40}")
_PRIVATE_HEADER: Final = re.compile(rb"-----BEGIN[A-Z ]*PRIVATE KEY-----")
_EX: Final = re.compile(r"(ex_[a-z2-7]{26})")
_SUITE_FILE_MAX: Final = 32 << 20


class Refused(Exception):
    """An input is refused or a decision does not fit (exit 2; nothing written)."""


# ------------------------------------------------------------------------------------------------ inputs
def default_scan_path(root: Path) -> Path:
    from agentprov.release.builder import scan_path_for

    return scan_path_for(root)


def triage_path_for(root: Path) -> Path:
    """``<corpus>.release-triage.toml``: beside the sealed tree, next to its scan document (D-609)."""
    return root.with_name(root.name + TRIAGE_SUFFIX)


def load_scan(path: Path, target: Mapping[str, Any]) -> dict[str, Any]:
    """The scan document of the sealed corpus ``target``: its format, root digest and pinned tools are checked."""
    try:
        doc = json.loads(path.read_bytes())
    except (OSError, ValueError):
        raise Refused("the scan document cannot be read as JSON") from None
    if not isinstance(doc, dict) or doc.get("format") != rs.FORMAT or not isinstance(doc.get("findings"), list):
        raise Refused(f"the scan document is not {rs.FORMAT}")
    if (doc.get("target") or {}).get("root_digest") != target["root_digest"]:
        raise Refused(f"the scan document is for root digest {(doc.get('target') or {}).get('root_digest')}, not "
                      f"{target['root_digest']} (D-42)")
    tools = {t.get("name"): t for t in doc.get("tools") or () if isinstance(t, dict)}
    gitleaks, path_scan = tools.get("gitleaks") or {}, tools.get(rs.PATH_SCAN_TOOL) or {}
    if (gitleaks.get("version"), gitleaks.get("config_sha256"), path_scan.get("version")) != (
            rs.GITLEAKS_VERSION, rs.GITLEAKS_CONFIG_SHA256, rs.PATH_SCAN_VERSION):  # fmt: skip
        raise Refused("the scan document records other scanners than the pinned ones; scan again (D-620)")
    return doc


@dataclass(frozen=True)
class SecretDecision:
    rule: str
    key: str
    origin: str
    triage: str
    findings: int
    reason: str


@dataclass(frozen=True)
class AccountDecision:
    ordinal: int
    triage: str
    hits: Mapping[str, int]
    reason: str


@dataclass(frozen=True)
class Decisions:
    root_digest: str
    sha256: str
    secrets: tuple[SecretDecision, ...]
    accounts: tuple[AccountDecision, ...]


def load_decisions(data: bytes) -> Decisions:
    """A decisions file (module docstring). Raises :class:`Refused` on anything else."""
    try:
        doc = tomllib.loads(data.decode("utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError):
        raise Refused("the decisions file is not UTF-8 TOML") from None
    if doc.get("format") != DECISIONS_FORMAT or set(doc) - {"format", "root_digest", "secret", "account"}:
        raise Refused(f"the decisions file is {DECISIONS_FORMAT}: format, root_digest, [[secret]] and [[account]] only")
    bound = doc.get("root_digest")
    if not isinstance(bound, str) or not rs._ROOT_DIGEST_RE.fullmatch(bound):
        raise Refused('the decisions file names no root_digest = "sha256:<64 hex>" (D-42)')

    def common(row: Any, keys: set[str], what: str, triages: frozenset[str] = DECISION_TRIAGES) -> dict[str, Any]:
        if not isinstance(row, dict) or set(row) != keys:
            raise Refused(f"a [[{what}]] row is {{{', '.join(sorted(keys))}}}")
        if row["triage"] not in triages:
            raise Refused(f"a [[{what}]] triage is one of {', '.join(sorted(triages))}")
        if not isinstance(row["reason"], str) or not row["reason"].strip():
            raise Refused(f"a [[{what}]] row needs a reason")
        return row

    found: list[SecretDecision] = []
    for row in doc.get("secret", []):
        row = common(row, {"rule", "key", "origin", "triage", "findings", "reason"}, "secret")
        if (not isinstance(row["rule"], str) or not isinstance(row["key"], str) or row["origin"] not in ORIGINS
                or not isinstance(row["findings"], int) or isinstance(row["findings"], bool) or row["findings"] < 1):
            raise Refused("a [[secret]] row has a rule, a key, an origin of "
                          f"{', '.join(ORIGINS)} and a positive count of findings")
        found.append(SecretDecision(row["rule"], row["key"], row["origin"], row["triage"], row["findings"], row["reason"]))
    if len({(d.rule, d.key, d.origin) for d in found}) != len(found):
        raise Refused("a (rule, key, origin) class is decided once")
    accounts: list[AccountDecision] = []
    for row in doc.get("account", []):
        row = common(row, {"ordinal", "triage", "hits", "reason"}, "account", ACCOUNT_TRIAGES)
        hits = row["hits"]
        if (not isinstance(row["ordinal"], int) or isinstance(row["ordinal"], bool) or row["ordinal"] < 1
                or not isinstance(hits, dict) or not hits
                or not all(isinstance(v, int) and not isinstance(v, bool) and v > 0 for v in hits.values())):
            raise Refused("an [[account]] row has an ordinal >= 1 and hits = {area = count, ...}")
        if row["triage"] == "pinned-account" and set(hits) != {"raw-object"}:
            raise Refused("pinned-account is for an ordinal found in raw objects only (D-604 item 7)")
        accounts.append(AccountDecision(row["ordinal"], row["triage"], dict(sorted(hits.items())), row["reason"]))
    if len({d.ordinal for d in accounts}) != len(accounts):
        raise Refused("an ordinal is decided once")
    return Decisions(bound, hashlib.sha256(data).hexdigest(), tuple(found), tuple(accounts))


def suite_blob(dirs: Sequence[Path]) -> tuple[bytes, int]:
    """The bytes of every regular file (up to 32 MiB, no link followed) below the suite-data directories, joined, and
    the number of files; read only, searched with ``in``."""
    parts: list[bytes] = []
    for top in dirs:
        for directory, subdirs, files in os.walk(top, followlinks=False):
            subdirs.sort()
            for name in sorted(files):
                path = Path(directory, name)
                if not path.is_symlink() and path.is_file() and path.stat().st_size <= _SUITE_FILE_MAX:
                    parts.append(path.read_bytes())
    return b"\n".join(parts), len(parts)


# ------------------------------------------------------------------------------------------------ classes
def area(label: str) -> str:
    """The layer of a corpus label as check 4 counts it: ``raw-object`` for ``raw/objects/``, else its top directory."""
    head = label.split("#", 1)[0]
    if head.startswith("raw/objects/"):
        return "raw-object"
    return head.split("/", 1)[0] if "/" in head else "top-level"


def key_name(matches: Iterable[str]) -> str:
    """The key name in front of the redacted value (``password`` in ``"password": "REDACTED"``), when it is a plain
    identifier; the names of several report entries of one fingerprint are joined with ``+``."""
    names = set()
    for match in matches:
        found = _KEY.search(match)
        names.add(found.group(1) if found and _IDENT.fullmatch(found.group(1)) else NO_KEY)
    return "+".join(sorted(names)) if names else NO_KEY


def executions_of_raw(root: Path) -> dict[str, set[str]]:
    """``raw object sha256 (bare hex) -> execution ids`` from the index rows' raw references."""
    out: dict[str, set[str]] = defaultdict(set)
    with open(root / "executions.jsonl", "rb") as stream:
        for line in stream:
            if line.strip():
                row = json.loads(line)
                for ref in row.get("raw") or ():
                    if isinstance(ref, dict) and isinstance(ref.get("sha256"), str):
                        out[ref["sha256"].removeprefix("sha256:")].add(row.get("ex"))
    return out


def _executions(label: str, of_raw: Mapping[str, set[str]]) -> set[str]:
    found = _EX.search(label)
    if found:
        return {found.group(1)}
    if label.startswith("raw/objects/"):
        return set(of_raw.get(Path(label).name.split(".", 1)[0], ()))
    return set()


@dataclass(frozen=True)
class SecretClass:
    fingerprint: str
    rule: str
    key: str
    origin: str
    layer: str


def secret_classes(root: Path, findings: Sequence[rs.Finding], matches: Mapping[str, Sequence[str]], blob: bytes
                   ) -> list[SecretClass]:
    """The origin of each gitleaks finding (module docstring), AER findings first so that their copies can follow them."""
    of_raw = executions_of_raw(root)
    wanted: dict[str, set[int]] = defaultdict(set)
    for f in findings:
        if "#" not in f.path:
            wanted[f.path].add(f.line)
    lines = {(label, n): text for label, numbers in wanted.items()
             for n, text in rs._read_lines(root / label, numbers).items()}  # fmt: skip
    per_file = Counter((f.path, f.rule) for f in findings)
    per_key = Counter((f.path, f.rule, key_name(matches.get(f.fingerprint, ()))) for f in findings)
    aer_origin: dict[tuple[str, ...], list[str]] = {}
    copies: Counter[tuple[str, ...]] = Counter()

    def follow(path: str, executions: set[str], pair: tuple[str, ...], count: int, strict: bool = True) -> str | None:
        """The origin a copy takes from its executions' AER findings of ``pair`` (rule, or rule and key); ``strict``
        pairs the n-th copy with the n-th AER finding only when the counts are equal."""
        lists = [aer_origin.get((ex, *pair), []) for ex in sorted(executions)]
        seen = {o for found in lists for o in found}
        if len(seen) == 1:
            return seen.pop()
        if len(lists) == 1 and lists[0] and (count == len(lists[0]) or not strict):
            nth = copies[(str(strict), path, *pair)]
            copies[(str(strict), path, *pair)] += 1
            return lists[0][nth] if nth < len(lists[0]) else None
        return None

    out = []
    for f in sorted(findings, key=lambda f: (not f.path.startswith("aer/"), f.path, f.line)):
        line = lines.get((f.path, f.line), b"")
        key = key_name(matches.get(f.fingerprint, ()))
        origin = None
        if f.rule == "private-key":
            head = _PRIVATE_HEADER.search(line)
            if head is not None and head.group(0) in blob:
                origin = "upstream-data"
        elif any(token in blob for token in _TOKEN.findall(line)):
            origin = "upstream-data"
        if origin is None and f.path.startswith("aer/") and line:
            try:
                record = json.loads(line)
            except ValueError:
                record = None
            if isinstance(record, dict):
                benchmark = record.get("k") in INPUT_KINDS or record.get("role") in INPUT_ROLES
                origin = "benchmark-input" if benchmark else "model-generated"
        executions = _executions(f.path, of_raw)
        if origin is not None and f.path.startswith("aer/"):
            for ex in executions:
                aer_origin.setdefault((ex, f.rule, key), []).append(origin)
                aer_origin.setdefault((ex, f.rule), []).append(origin)
        if origin is None:
            origin = (follow(f.path, executions, (f.rule, key), per_key[(f.path, f.rule, key)])
                      or follow(f.path, executions, (f.rule,), per_file[(f.path, f.rule)])
                      or follow(f.path, executions, (f.rule, key), per_key[(f.path, f.rule, key)], strict=False)
                      or follow(f.path, executions, (f.rule,), per_file[(f.path, f.rule)], strict=False)
                      or "unclassified")
        out.append(SecretClass(f.fingerprint, f.rule, key, origin, area(f.path)))
    return out


@dataclass
class Ordinals:
    """The account names of a corpus's ``account-path`` findings as ordinals; the names stay inside this object."""

    by_finding: dict[str, set[int]] = field(default_factory=dict)  # fingerprint -> ordinals on its line
    hits: dict[int, Counter[str]] = field(default_factory=dict)  # ordinal -> matches by area
    in_suite: dict[int, tuple[bool, bool]] = field(default_factory=dict)  # ordinal -> (name, path) in the suite data


def member_bytes(root: Path, labels: Iterable[str], *, workers: int | None = None, in_process: bool = False,
                 release: bool = True) -> dict[str, tuple[bytes, bytes]]:
    """``<archive label>#<locator> -> (member name, member data)`` for the archive-member labels among ``labels``, read
    decoded as the scan read them (D-491: :func:`agentprov.corpus.withhold_scan.scan_archives`, the same depth and the
    same stored members skipped), in memory only. A member the decoded read does not reach is left out."""
    from agentprov.corpus.withhold import Rule, _released_members
    from agentprov.corpus.withhold_scan import scan_archives

    wanted: dict[str, set[str]] = defaultdict(set)
    for label in labels:
        if "#" in label:
            archive, locator = label.split("#", 1)
            wanted[archive].add(locator)
    if not wanted:
        return {}
    objects = {Path(archive).name.split(".", 1)[0]: archive for archive in wanted}
    if not all(archive.startswith("raw/objects/") and rs._ROOT_DIGEST_RE.fullmatch("sha256:" + sha)
               for sha, archive in objects.items()):  # fmt: skip
        raise Refused("an archive-member finding names a file that is not a stored raw object")

    def stream(label: str) -> Iterable[bytes]:
        return rs._file_chunks(root / label)

    parts: dict[str, dict[str, bytes]] = defaultdict(dict)

    def member_scan(sha: str, locator: str, part: str, chunks: Iterable[bytes]) -> frozenset[str]:
        data = b"".join(chunks)
        if locator in wanted[objects[sha]]:
            parts[f"{objects[sha]}#{locator}"][part] = data
        return frozenset()

    listed = [label for label in ("raw/members.jsonl", "raw/origins.jsonl") if (root / label).is_file()]
    rule = Rule(id=rs.ACCOUNT_RULE, kind="pattern", scope="object", reason="account path (D-457)", public_note="",
                regex=rs._ACCOUNT_PATH, width=rs._ACCOUNT_SPAN)
    scan_archives(objects, stream, [rule], release=release, workers=workers, in_process=in_process,
                  max_depth=rs.declared_depth(root), members=_released_members(listed, stream),
                  member_scan=member_scan)  # fmt: skip
    return {label: (got.get("name", b""), got.get("data", b"")) for label, got in parts.items()}


def account_ordinals(root: Path, labels: Iterable[str], blob: bytes = b"",
                     members: Mapping[str, tuple[bytes, bytes]] | None = None) -> Ordinals:
    """Number the account names in ``labels`` (the ``account-path`` findings' files) by first appearance. An
    archive-member label (``<archive>#<locator>``) is read from ``members`` (:func:`member_bytes`): its name first (the
    scan's line 0), then its data."""
    search = rs.Accounts.excluding(rs.personal_needles().get("home-path", ()))
    order: dict[bytes, int] = {}
    out = Ordinals()
    for label in sorted(set(labels)):
        if "#" in label:
            if members is None or label not in members:
                continue  # not read: its findings stay untriaged
            name_bytes, data = members[label]
            texts = [(name_bytes + b"\x00", True), (data + b"\x00", False)]  # the NUL ends a match at the end, as the scan's
        else:
            texts = [((root / label).read_bytes(), False)]
        for data, is_name in texts:
            newlines = [m.start() for m in re.finditer(b"\n", data)]
            for start in sorted(search.offsets(data, 0)):
                match = rs._ACCOUNT_PATH.match(data, start)
                if match is None:
                    continue
                name = match.group(match.lastindex or 0).rstrip(b".")
                n = order.setdefault(name, len(order) + 1)
                out.hits.setdefault(n, Counter())[area(label)] += 1
                line = 0 if is_name else bisect.bisect_left(newlines, start) + 1
                out.by_finding.setdefault(f"{label}:{rs.ACCOUNT_RULE}:{line}", set()).add(n)
    for name, n in order.items():
        word = re.compile(rb"(?<![A-Za-z0-9])" + re.escape(name) + rb"(?![A-Za-z0-9])")
        out.in_suite[n] = (bool(blob) and word.search(blob) is not None,
                           (b"/home/" + name in blob) or (b"/Users/" + name in blob))
    return out


# ------------------------------------------------------------------------------------------------ the triage file
@dataclass
class Plan:
    entries: dict[str, tuple[str, str]]  # fingerprint -> (triage, reason)
    left: Counter[str]  # untriaged findings no decision covers, by rule
    errors: list[str]  # decisions whose count differs


def plan_triage(untriaged: Sequence[Mapping[str, Any]], classes: Sequence[SecretClass], ordinals: Ordinals,
                decisions: Decisions) -> Plan:
    """The entries the decisions give the scan's untriaged findings, and every count that differs."""
    errors: list[str] = []
    by_fp = {c.fingerprint: c for c in classes}
    rows = {(d.rule, d.key, d.origin): d for d in decisions.secrets}
    seen: Counter[tuple[str, str, str]] = Counter((c.rule, c.key, c.origin) for c in classes)
    for cls, secret in sorted(rows.items()):
        if seen[cls] != secret.findings:
            errors.append(f"[[secret]] {secret.rule} / {secret.key} / {secret.origin}: {seen[cls]} finding(s), the "
                          f"decision says {secret.findings}")
    accounts = {a.ordinal: a for a in decisions.accounts}
    for n, account in sorted(accounts.items()):
        hits = dict(sorted(ordinals.hits.get(n, Counter()).items()))
        if hits != dict(account.hits):
            errors.append(f"[[account]] #{n}: hits {json.dumps(hits, sort_keys=True)}, the decision says "
                          f"{json.dumps(dict(account.hits), sort_keys=True)}")
    entries: dict[str, tuple[str, str]] = {}
    left: Counter[str] = Counter()
    for row in untriaged:
        fp, rule = row["fingerprint"], row["rule"]
        decided: tuple[str, str] | None = None
        if row.get("detector") == "gitleaks" and fp in by_fp:
            c = by_fp[fp]
            decision = rows.get((c.rule, c.key, c.origin))
            if decision is not None:
                decided = decision.triage, f"{decision.reason} [C-3: rule {c.rule}, key {c.key}, origin {c.origin}]"
        elif rule == rs.ACCOUNT_RULE and fp in ordinals.by_finding:
            ns = sorted(ordinals.by_finding[fp])
            if all(n in accounts for n in ns):
                triage = next(t for t in ACCOUNT_ORDER if any(accounts[n].triage == t for n in ns))
                decided = triage, "; ".join(f"account #{n} ({accounts[n].triage}): {accounts[n].reason}" for n in ns) + (
                    " [C-3: account ordinal]")
        if decided is None:
            left[rule] += 1
        else:
            entries[fp] = decided
    return Plan(entries, left, errors)


def _toml_string(text: str) -> str:
    return json.dumps(text, ensure_ascii=True)  # a JSON string with ASCII escapes is a TOML basic string


def render_triage(root_digest: str, entries: Mapping[str, tuple[str, str]], header: Sequence[str]) -> str:
    lines = [f"# {line}" for line in header]
    lines += [f"root_digest = {_toml_string(root_digest)}", ""]
    for fp in sorted(entries):
        triage, reason = entries[fp]
        lines += ["[[triage]]", f"fingerprint = {_toml_string(fp)}", f"triage = {_toml_string(triage)}",
                  f"reason = {_toml_string(reason)}", ""]
    return "\n".join(lines)


def _write(path: Path, text: str) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


# ------------------------------------------------------------------------------------------------ main
@dataclass
class Inputs:
    root: Path
    target: dict[str, Any]
    scan: dict[str, Any]
    classes: list[SecretClass]
    ordinals: Ordinals
    suite_files: int
    suite_sha256: str


def gather(root: Path, scan_path: Path, suites: Sequence[Path], gitleaks: str, *, timeout: float | None = None,
           run: rs.Runner = rs._run, workers: int | None = None, in_process: bool = False,
           release: bool = True) -> Inputs:
    """Read the scan document, run gitleaks (redacted) for the key names, and compute the classes and ordinals
    (archive members read decoded: ``workers`` T1 readers; ``in_process`` and ``release=False`` are for tests only)."""
    target = rs.corpus_target(root)
    scan = load_scan(scan_path, target)
    rs.gitleaks_version(gitleaks, run=run)
    matches: dict[str, list[str]] = {}
    findings, _resolved = rs.run_gitleaks(gitleaks, root, timeout=timeout, run=run, matches=matches)
    reported = {r["fingerprint"] for r in scan["findings"] if r.get("detector") == "gitleaks"}
    if {f.fingerprint for f in findings} != reported:
        raise Refused("gitleaks reports other findings on this tree than the scan document; scan it again")
    blob, files = suite_blob(suites)
    labels = [r["path"] for r in scan["findings"] if r.get("rule") == rs.ACCOUNT_RULE]
    members = member_bytes(root, labels, workers=workers, in_process=in_process, release=release)
    return Inputs(root, target, scan, secret_classes(root, findings, matches, blob),
                  account_ordinals(root, labels, blob, members), files, hashlib.sha256(blob).hexdigest())


def report(inputs: Inputs) -> dict[str, Any]:
    """``--report``: the classes and their counts (what a person reviews to write the decisions file); no value."""
    groups: dict[tuple[str, str, str], Counter[str]] = {}
    for c in inputs.classes:
        groups.setdefault((c.rule, c.key, c.origin), Counter())[c.layer] += 1
    return {"root_digest": inputs.target["root_digest"], "suite_files": inputs.suite_files,
            "secret": [{"rule": r, "key": k, "origin": o, "findings": sum(n.values()), "layers": dict(sorted(n.items()))}
                       for (r, k, o), n in sorted(groups.items())],
            "account": [{"ordinal": n, "hits": dict(sorted(h.items())), "findings": sum(1 for s in inputs.ordinals.by_finding.values() if n in s),
                         "name_in_suite": inputs.ordinals.in_suite[n][0], "path_in_suite": inputs.ordinals.in_suite[n][1]}
                        for n, h in sorted(inputs.ordinals.hits.items())]}  # fmt: skip


def list_secrets(inputs: Inputs, gitleaks: str, *, show: bool, timeout: float | None = None,
                 run: rs.Runner = rs._run) -> list[str]:
    """``--list-secrets``: one line per distinct value of the scan's gitleaks findings (module docstring)."""
    values: dict[str, list[str]] = {}
    rs.run_gitleaks(gitleaks, inputs.root, timeout=timeout, run=run, matches=values, redact=False)
    salt = secrets.token_bytes(32)
    table: dict[str, dict[str, Any]] = {}
    for c in inputs.classes:
        for value in set(values.get(c.fingerprint, ())):
            tag = hmac.new(salt, value.encode("utf-8", "surrogateescape"), hashlib.sha256).hexdigest()[:16]
            row = table.setdefault(tag, {"value": value, "rules": set(), "keys": set(), "origins": set(),
                                         "findings": set(), "layers": set()})
            row["rules"].add(c.rule)
            row["keys"].add(c.key)
            row["origins"].add(c.origin)
            row["findings"].add(c.fingerprint)
            row["layers"].add(c.layer)
    out = []
    for tag, row in sorted(table.items()):
        line = (f"{tag} rule={','.join(sorted(row['rules']))} keys={','.join(sorted(row['keys']))} "
                f"origins={','.join(sorted(row['origins']))} findings={len(row['findings'])} "
                f"layers={','.join(sorted(row['layers']))}")
        if show:
            from agentprov.ingest.quote import quote_untrusted

            line += "\n" + quote_untrusted(row["value"], f"gitleaks value {tag}")
        out.append(line)
    return out


def main(argv: Sequence[str] | None = None, *, run: rs.Runner = rs._run) -> int:
    parser = argparse.ArgumentParser(prog="release_triage.py", description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("corpus", help="a sealed corpus directory")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--decisions", help=f"the reviewed decisions file ({DECISIONS_FORMAT})")
    mode.add_argument("--report", action="store_true", help="print the classes and their counts as JSON; write nothing")
    mode.add_argument("--list-secrets", action="store_true",
                      help="one line per distinct gitleaks value: a per-run HMAC, rule, keys, origins, counts; no value")
    parser.add_argument("--show", action="store_true", help="with --list-secrets: add each value (a terminal only)")
    parser.add_argument("--scan", help="the corpus's scan document (default: <corpus>.release-scan.json beside it)")
    parser.add_argument("--suites", action="append", default=[], help="a directory of the benchmark's own suite data")
    parser.add_argument("--out", help="the triage file (default: <corpus>.release-triage.toml beside the corpus)")
    parser.add_argument("--gitleaks", help="the gitleaks executable (default: from PATH)")
    parser.add_argument("--timeout", type=float, help="gitleaks timeout in seconds")
    args = parser.parse_args(argv)
    if args.show and not args.list_secrets:
        parser.error("--show goes with --list-secrets")
    if args.show and not sys.stdout.isatty():
        print("release_triage: --show prints values to a terminal only (run it in your own terminal)", file=sys.stderr)
        return 2
    root = Path(os.path.realpath(args.corpus))
    out = Path(os.path.realpath(args.out)) if args.out else triage_path_for(root)
    if out == root or root in out.parents:
        print("release_triage: the triage file goes beside the sealed corpus, never inside it", file=sys.stderr)
        return 2
    executable = args.gitleaks or shutil.which("gitleaks")
    if executable is None:
        print("release_triage: gitleaks is not installed (G.9.4)", file=sys.stderr)
        return 3
    try:
        decisions = load_decisions(Path(args.decisions).read_bytes()) if args.decisions else None
        if decisions is not None and decisions.root_digest != rs.corpus_target(root)["root_digest"]:
            raise Refused(f"the decisions were reviewed for root digest {decisions.root_digest}, not this corpus (D-42)")
        inputs = gather(root, Path(args.scan) if args.scan else default_scan_path(root), [Path(s) for s in args.suites],
                        os.path.abspath(executable), timeout=args.timeout, run=run)
        if args.report:
            print(json.dumps(report(inputs), indent=1, sort_keys=True))
            return 0
        if args.list_secrets:
            lines = list_secrets(inputs, os.path.abspath(executable), show=args.show, timeout=args.timeout, run=run)
            print("\n".join(lines))
            print(f"release_triage: {len(lines)} distinct value(s)", file=sys.stderr)
            return 0
        assert decisions is not None
        untriaged = [r for r in inputs.scan["findings"] if r.get("triage") is None]
        plan = plan_triage(untriaged, inputs.classes, inputs.ordinals, decisions)
        if plan.errors:
            raise Refused("decisions that do not fit this corpus (nothing written):\n  " + "\n  ".join(plan.errors))
    except rs.ScanError as exc:
        print(f"release_triage: {exc}", file=sys.stderr)
        return 3
    except (Refused, ValueError, OSError) as exc:
        print(f"release_triage: {exc}", file=sys.stderr)
        return 2
    header = [f"Release-scan triage of {inputs.target['corpus_id']} {inputs.target['corpus_version']} "
              "(tools/release_triage.py, C-3; reviewed per sealed root digest, D-42).",
              f"decisions sha256:{decisions.sha256}; scan findings {len(inputs.scan['findings'])}, untriaged "
              f"{len(untriaged)}; suite data {inputs.suite_files} file(s), sha256:{inputs.suite_sha256}."]
    _write(out, render_triage(inputs.target["root_digest"], plan.entries, header))
    left = sum(plan.left.values())
    print(f"release_triage: {len(plan.entries)} entr(y/ies) written to {out}; {left} finding(s) left untriaged"
          f"{' ' + json.dumps(dict(sorted(plan.left.items()))) if left else ''}", file=sys.stderr)
    return 1 if left else 0


if __name__ == "__main__":
    sys.exit(main())
