"""Release-tree scan (G.9.4): run gitleaks over a sealed corpus and write ``<corpus>.release-scan.json``.

Usage::

    uv run python tools/release_scan.py CORPUS_DIR [--triage TRIAGE.toml] [--out PATH] [--gitleaks PATH] [--timeout S]

The deposit builder (``agentprov package --deposit``; ``agentprov.release.builder``) is offline and starts no process,
so the scan runs here, outside ``src/`` (M.5.3, G.11.1 row 15). The builder refuses a corpus unless a release scan for
the same root digest exists with every finding triaged and none ``real`` outside ``WITHHELD.json``.

* **gitleaks** (``gitleaks dir --redact``; v8.30.1 is the pinned scanner of v0.1, AD-10 row 19) is the one secret
  scanner. It never verifies a finding against a live service. It runs with an explicit configuration (the default rule
  set plus one anchored allowlist for AgentPROV's own content-addressed keys, ``_KEY_ALLOWLIST``; its digest is
  recorded) and an empty ignore path, so a ``.gitleaks.toml`` or ``.gitleaksignore`` inside scanned data cannot change the
  rules, and with ``--ignore-gitleaks-allow``, so a ``gitleaks:allow`` comment planted in third-party data cannot hide a
  finding. Its environment is reduced to ``PATH``, ``HOME`` (a temporary directory) and ``LC_ALL``. Its version is
  recorded; another version than the pin (``agentprov.release.metadata.GITLEAKS_VERSION``) is refused (exit 3), and
  the deposit builder refuses a scan document that records another gitleaks, configuration or path-scan version.
* **Key cuts** (D-310): gitleaks scans long lines in fragments and cuts a match at a fragment boundary, so a cut of an
  AgentPROV key (``onKey":"<key>"``, ``derivationKey":"<12 characters>``) escapes the uncut-only allowlist. A
  ``generic-api-key`` finding is dropped only when :func:`key_cut_explained` proves, against the file's own line, that
  every place on the line where the redacted match fits lies inside an exact AgentPROV key member (and the reported
  entropy confirms the value); otherwise it is reported. The number dropped is recorded (``key_cuts_resolved``), never which.
* **Home path and host name** (R-51): every file is searched for the user's home path and host name; each hit is a
  finding (rules ``home-path`` and ``host-name``).
* **Third-party account paths** (D-457): every file (raw-store objects, context and auxiliary files included, binary
  or not) is also searched for workstation account paths: ``/Users/<name>``, ``/home/<name>``, their JSON forms with
  an escaped slash ``\\/Users\\/<name>`` and ``\\/home\\/<name>``, ``C:\\Users\\<name>``, its JSON-escaped form
  ``C:\\\\Users\\\\<name>``, ``C:/Users/<name>`` (any drive letter, either case; ``Users`` in any case) and the WSL form
  ``/mnt/c/Users/<name>``. ``<name>`` is 1 to 64 of ``[A-Za-z0-9._-]``. It must be followed by a separator (``/``, or
  ``\\``, which also opens a JSON escape such as ``\\/`` or ``\\n``), a closing quote (``"`` or ``'``), whitespace, ``,``,
  ``:``, ``;``, ``)``, ``]``, ``}``, a NUL or the end of the file, so a bare home (``"HOME": "/Users/<name>"``) counts.
  ``/Users/`` and ``/home/`` (and their escaped forms) must start an absolute path (not preceded by a letter, digit,
  ``.``, ``_`` or ``-``), so a URL path (``https://example.com/home/page/``) is not one. A name on
  :data:`ACCOUNT_ALLOWLIST` (generic, non-identifying accounts and placeholders, case-insensitive; trailing dots, as at
  the end of a sentence, are ignored) or made of dots only is not reported, nor the operator's own home path when it
  is ``/Users/<name>`` or ``/home/<name>`` in that unescaped form, bare or not (that exact path is the ``home-path``
  rule's; its other forms, which ``home-path`` does not see, are ``account-path`` findings). **Not covered:** deeper
  roots such as ``/var/home/<name>`` (Fedora Silverblue) and ``/System/Volumes/Data/Users/<name>`` (the macOS data
  volume), which the boundary excludes, and the WSL form with escaped slashes. Each other hit is a finding of rule ``account-path``; archives are read decoded for it
  as below. It is triaged with the existing values: ``real`` when it identifies a person (it must then be withheld,
  ``personal_data``, so that ``WITHHELD.json`` names it), ``synthetic-benchmark`` for an account a benchmark made up,
  ``false-positive`` for text that is no account path, and ``pinned-account`` for a third-party account in a raw
  object that ships as pinned (D-186 (c); D-604 item 7, user decision 2026-10-21: raw files no exact withhold rule can
  target, while their derived records are redacted and the datasheet discloses them). ``pinned-account`` is valid only
  for an ``account-path`` finding in ``raw/``; the deposit builder refuses it anywhere else. Paths in raw-store context
  and auxiliary files count (user decision 2026-10-15).
* **Secret shapes** (D-600): every file is also searched for the token shapes of :data:`SECRET_SHAPES`, under gitleaks'
  own rule ids, so a ``[withhold]`` policy's ``scan_rules`` and the deposit builder's backstop (D-236) cover them:
  ``github-pat`` (``ghp_``), ``github-oauth`` (``gho_``), ``github-app-token`` (``ghu_``, ``ghs_``),
  ``github-refresh-token`` (``ghr_``), each with 36 of ``[0-9A-Za-z]``; ``github-fine-grained-pat`` (``github_pat_``
  and 82 of ``[0-9A-Za-z_]``); ``huggingface-access-token`` (``hf_`` and 34 of ``[A-Za-z0-9]``); and, with ids of
  AgentPROV's own (gitleaks 8.30.1 has no Langfuse rule), ``langfuse-secret-key`` and ``langfuse-public-key``
  (``sk-lf-`` or ``pk-lf-`` and a UUID, 8-4-4-4-12 hex digits). A shape may not follow a letter, digit or ``_``, nor
  be followed by a character of its own body, so a longer token holding one is not a hit. The search is the
  ``account-path`` rule's route: a literal is found, then the shape is matched anchored at it (bounded, no
  backtracking). gitleaks already reads stored files; the native rules exist for **archive members**, which gitleaks
  never sees (``--max-archive-depth 0``, D-450), and run on stored files too so that the scan of a member and of its
  stored copy agree. A native finding whose fingerprint gitleaks also reported is dropped, so nothing is reported
  twice. No entropy threshold applies (gitleaks uses one): a low-entropy shape is a finding, to be triaged.
* **E-mail addresses** (D-810): every address is a finding of rule ``email-address`` (shape and limits in
  :mod:`agentprov.corpus.personas`), in stored files and in decoded archive members; the finding records no address, local
  part or domain. A line is **cleared by a rule** only when every address on it is: (1) its domain is reserved by RFC 2606
  or RFC 6761 (``example.com``, ``example.net``, ``example.org``, ``.example``, ``.test``, ``.invalid``, ``.localhost``;
  ``test.com`` is a real domain and is not reserved): triaged ``false-positive``; (2) its digest, ``sha256`` of the ASCII
  lower-cased address, is in a persona file the corpus's own sealed spec names (``[scan] personas``, sealed under
  ``rules/personas/``; digests only, never addresses): triaged ``synthetic-benchmark``, ``basis: persona``. Anything else is
  untriaged and stops the builder. A public mail provider's address is never cleared by its domain, only by an exact
  entry. A human ``--triage`` entry decides its fingerprint over a rule (``real`` stays possible). The document's
  ``personas`` block records the sealed spec's sha256, which the deposit builder compares with ``files.spec``. Not found:
  addresses written with ``\\uXXXX`` escapes, obfuscated forms (``name at host dot com``), internationalised domains and
  addresses split by a line break. ``--list-addresses`` prints one line per distinct address (digest, domain class,
  findings, corpora, layers; never an address), without gitleaks and without an output file; ``tools/scan_personas.py``
  checks a corpus's digests against the benchmark's own upstream data.
* **Inside archives** (D-491): every file that is an archive by its magic bytes (the classification of D-450,
  :mod:`agentprov.corpus.withhold_scan`) is also read **decoded**, through the same bounded, extraction-free ``expand``
  job (T1 workers, the default G.3 limits) that the sealing scan uses, and its members' names and contents are searched
  for the same needles, account paths and secret shapes. Only the members the corpus does not store as objects of their own are read (``raw/members.jsonl``,
  each stored row confirmed by its ``member`` origin); a stored member is searched as its own file. Nested archives are
  read to ``max_archive_depth``, or the deeper level the corpus's source profiles declare (``[[import.nested]]``). A hit
  is reported against the archive's path as ``<path>#<member index>`` (the member's 0-based position in its archive;
  ``#3!0`` for a member of a nested archive), with the line inside the member, or line 0 for a hit in the member's
  name. An archive that cannot be read within the limits (a deferred codec, nesting past the depth, a corrupt or
  rejected archive or member, the scan budget) is an untriaged ``home-path-unscanned`` finding on line 0, so the scan
  fails closed. Nothing is extracted to disk; decoded members live in a scratch raw store under ``$AGENTPROV_HOME/tmp``
  only while they are read.
* **Never a matched value.** A finding records ``detector``, ``rule``, the corpus-relative ``path``, ``line`` and a
  ``fingerprint`` (``<path>:<rule>:<line>``); never the secret, the match or the line text. The home path and host name
  themselves are never written, nor an account name or path. The key-cut check holds the redacted match and the line in memory only.
* **Triage** is a human decision, read from ``--triage`` (TOML ``[[triage]]`` tables ``{fingerprint, triage, reason}``;
  ``triage`` is ``real``, ``synthetic-benchmark``, ``false-positive`` or ``home-path``). Untriaged findings are written
  with ``triage: null``; the builder refuses them. A triage file is reviewed per fingerprint **and per sealed root
  digest** (D-42): it carries a top-level ``root_digest = "sha256:<64 hex>"`` and the scan refuses it (exit 2) for any
  other corpus, because a fingerprint names a path, rule and line, not the bytes there; a later version needs its own
  reviewed file. The scan document records the triage file's root digest and sha256 (``triage``; ``null`` without one).
  ``tools/release_triage.py`` writes such a file from reviewed, value-blind class decisions (C-3, D-920).

Exit codes: 0 every finding triaged and none ``real``; 1 a finding is untriaged or ``real``; 2 usage; 3 gitleaks is
missing, not the pinned version, or failed.
"""

from __future__ import annotations

import argparse
import bisect
import functools
import hashlib
import json
import math
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import tomllib
from collections import Counter
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from agentprov.corpus.personas import (
    CLASS_RESERVED,
    EMAIL_AHEAD,
    EMAIL_BEHIND,
    EMAIL_PATTERN,
    address_digest,
    domain_class,
    find_addresses,
    parse_persona_file,
    persona_digests,
    sha256_label,
)
from agentprov.release.metadata import (
    GITLEAKS_CONFIG,
    GITLEAKS_CONFIG_SHA256,
    GITLEAKS_KEY_ALLOWLIST,
    GITLEAKS_VERSION,
    PATH_SCAN_TOOL,
    PATH_SCAN_VERSION,
)

FORMAT: Final = "agentprov-release-scan/0.1"
TRIAGE_VALUES: Final = frozenset({"real", "synthetic-benchmark", "false-positive", "home-path", "pinned-account",
                                  "model-generated"})
#: The rule of an archive the path scan could not read decoded (D-491): it fails closed, untriaged.
UNSCANNED_RULE: Final = "home-path-unscanned"
#: The rule of a third-party workstation account path (D-457; module docstring).
ACCOUNT_RULE: Final = "account-path"
#: The rule of an e-mail address (D-810; module docstring). While scanning, a hit of an address cleared by a rule is
#: ``email-address/reserved`` or ``email-address/persona``; :func:`_settle_emails` makes one ``email-address`` finding per
#: (file, line), cleared only when every address on the line is.
EMAIL_RULE: Final = "email-address"
#: The clearing bases of an ``email-address`` finding, strongest disclosure first (the order a line of mixed bases takes):
#: ``model-generated`` (triage ``model-generated``), ``benchmark-input`` and ``upstream-data`` (``synthetic-benchmark``),
#: ``file-name`` and ``reserved`` (``false-positive``).
EMAIL_BASES: Final = ("model-generated", "benchmark-input", "upstream-data", "file-name", "reserved")
_EMAIL_CLEARED: Final = {basis: f"{EMAIL_RULE}/{basis}" for basis in EMAIL_BASES}
_EMAIL_RULES: Final = frozenset({EMAIL_RULE, *_EMAIL_CLEARED.values()})
_EMAIL_REACH: Final = EMAIL_AHEAD + EMAIL_BEHIND + 2
REASON_RESERVED: Final = "address at a domain reserved by RFC 2606 and RFC 6761: no mailbox can exist there"
#: Account names that identify nobody, compared case-insensitively (D-457): CI and cloud images, containers and
#: notebooks, OS defaults and shared folders, and documentation placeholders. Placeholders with characters outside the
#: account-name class (``<user>``, ``$user``, ``%username%``) never match it; they are listed so that the list stays the
#: documented one if the class is ever widened.
ACCOUNT_ALLOWLIST: Final = frozenset({
    "user", "users", "ubuntu", "runner", "runneradmin", "root", "shared", "guest", "vscode", "codespace", "jovyan",
    "ec2-user", "admin", "administrator", "default", "public", "travis", "circleci", "appveyor", "vagrant", "docker",
    "app", "node", "nobody",
    "<user>", "<username>", "username", "$user", "%username%", "you", "me", "name", "example",
})  # fmt: skip
#: A redaction label in place of an account (D-604): the ``acct-{span12}`` every family redaction writes, including
#: controlarena-persistent from version 4, and the ``account-{span12}`` of its archived version 3, which the phase 10p
#: trials recorded (pre-round review #21). It names nobody, so the AER of a redacted corpus raises no ``account-path``
#: finding for it. Matched whole (``fullmatch``): lower-case hex, exactly 12 digits.
REDACTION_LABEL: Final = re.compile(rb"(?:acct|account)-[0-9a-f]{12}")
#: An account name: bounded, so a match is at most :data:`_ACCOUNT_SPAN` bytes and never backtracks badly.
_ACCOUNT_NAME: Final = rb"([A-Za-z0-9._-]{1,64})"
#: Not preceded by a path-name byte: the leading ``/`` must be the root of an absolute path, so ``/home/`` inside a URL
#: path (``https://example.com/home/page/``) or a deeper path (``/var/home/x/``) is not an account path.
_ROOT: Final = rb"(?<![A-Za-z0-9._-])"
_WIN_SEP: Final = rb"(?:\\\\?|/)"  # \ (a Windows path), \\ (the same path in a JSON string) or /
#: What may follow a name: a separator (``/``; ``\`` also opens a JSON escape such as ``\/``, ``\"`` or ``\n``), a
#: closing quote, whitespace, ``,``, ``:``, ``;``, ``)``, ``]``, ``}`` or NUL, so a bare home (``"/Users/<name>"``)
#: counts. The end of a file counts too: :func:`_chunk_hits` searches its last bytes once more with a NUL after them.
_END: Final = rb"""(?=[/\\"'\s,:;)\]}\x00])"""
_POSIX_ACCOUNT: Final = _ROOT + rb"/(Users|home)/" + _ACCOUNT_NAME + _END  # macOS and Linux
#: The same in a JSON string that escapes ``/`` as ``\/``; the escaped slash must start the path, as above.
_ESCAPED_ACCOUNT: Final = _ROOT + rb"\\/(?:Users|home)\\/" + _ACCOUNT_NAME + _END
_MNT_ACCOUNT: Final = _ROOT + rb"/mnt/[A-Za-z]/(?i:users)/" + _ACCOUNT_NAME + _END  # a Windows profile from WSL
_WIN_ACCOUNT: Final = rb"(?<![A-Za-z0-9])[A-Za-z]:" + _WIN_SEP + rb"(?i:users)" + _WIN_SEP + _ACCOUNT_NAME + _END
#: The whole rule as one pattern (the rule of the decoded scan's gate). :meth:`Accounts.offsets` runs the forms one by
#: one, anchored where a ``users``, ``/home/`` or ``\/home\/`` literal was found, which is many times faster on large
#: files.
_ACCOUNT_PATH: Final = re.compile(b"|".join((_POSIX_ACCOUNT, _ESCAPED_ACCOUNT, _MNT_ACCOUNT, _WIN_ACCOUNT)))
#: ``(pattern, bytes from a match's start to its users literal)``: 1 ``/``, 2 ``\/``, 7 ``/mnt/c/``, 3 ``C:\`` or
#: ``C:/``, 4 ``C:\\``.
_AT_USERS: Final = ((re.compile(_POSIX_ACCOUNT), 1), (re.compile(_ESCAPED_ACCOUNT), 2), (re.compile(_MNT_ACCOUNT), 7),
                    (re.compile(_WIN_ACCOUNT), 3), (re.compile(_WIN_ACCOUNT), 4))
#: ``(literal, pattern anchored at it)`` for the home forms.
_AT_HOME: Final = ((b"/home/", re.compile(_POSIX_ACCOUNT)), (b"\\/home\\/", re.compile(_ESCAPED_ACCOUNT)))
#: The longest account-path match plus the bytes its look-behind and look-ahead read (``/mnt/c/Users/`` and 64, plus
#: 2), with room to spare.
_ACCOUNT_SPAN: Final = 96
_NOT_AFTER: Final = rb"(?<![A-Za-z0-9_])"  # a secret shape does not continue a longer token
_UUID: Final = rb"[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}"
#: The native secret-shape rules (D-600; module docstring): ``(rule id, literal, pattern)``. Each pattern starts with its
#: literal (it is matched anchored where the literal was found) and has fixed-length parts only, so a match is bounded
#: and never backtracks. The ids are gitleaks' (8.30.1) where it has the rule.
SECRET_SHAPES: Final = (
    ("github-pat", b"ghp_", _NOT_AFTER + rb"ghp_[0-9A-Za-z]{36}(?![0-9A-Za-z])"),
    ("github-oauth", b"gho_", _NOT_AFTER + rb"gho_[0-9A-Za-z]{36}(?![0-9A-Za-z])"),
    ("github-app-token", b"ghu_", _NOT_AFTER + rb"ghu_[0-9A-Za-z]{36}(?![0-9A-Za-z])"),
    ("github-app-token", b"ghs_", _NOT_AFTER + rb"ghs_[0-9A-Za-z]{36}(?![0-9A-Za-z])"),
    ("github-refresh-token", b"ghr_", _NOT_AFTER + rb"ghr_[0-9A-Za-z]{36}(?![0-9A-Za-z])"),
    ("github-fine-grained-pat", b"github_pat_", _NOT_AFTER + rb"github_pat_[0-9A-Za-z_]{82}(?![0-9A-Za-z_])"),
    ("huggingface-access-token", b"hf_", _NOT_AFTER + rb"hf_[A-Za-z0-9]{34}(?![A-Za-z0-9])"),
    ("langfuse-secret-key", b"sk-lf-", _NOT_AFTER + rb"sk-lf-" + _UUID + rb"(?![0-9A-Za-z])"),
    ("langfuse-public-key", b"pk-lf-", _NOT_AFTER + rb"pk-lf-" + _UUID + rb"(?![0-9A-Za-z])"),
)
_SECRETS: Final = tuple((rule, literal, re.compile(pattern)) for rule, literal, pattern in SECRET_SHAPES)
SECRET_RULES: Final = frozenset(rule for rule, _literal, _pattern in SECRET_SHAPES)
#: The longest secret-shape match (``github_pat_`` and 82) plus the bytes its look-behind and look-ahead read, with
#: room to spare.
_SECRET_SPAN: Final = 100
#: The gitleaks configuration (the default rules plus one anchored allowlist for AgentPROV's own content-addressed keys,
#: user-approved; D-310) and the pinned versions live in :mod:`agentprov.release.metadata`, which the deposit builder's
#: check reads too (one copy): ``_KEY_ALLOWLIST``, ``_GITLEAKS_CONFIG``, ``GITLEAKS_CONFIG_SHA256``, ``GITLEAKS_VERSION``
#: and ``PATH_SCAN_VERSION`` are those, imported above.
_KEY_ALLOWLIST: Final = GITLEAKS_KEY_ALLOWLIST
_GITLEAKS_CONFIG: Final = GITLEAKS_CONFIG
_CHUNK: Final = 1 << 20
_MAX_REPORT_BYTES: Final = 256 << 20
_VERSION_RE: Final = re.compile(r"v?([0-9]+\.[0-9]+\.[0-9]+)")
_ROOT_DIGEST_RE: Final = re.compile(r"sha256:[0-9a-f]{64}")
#: An exact AgentPROV key member on a JCS line. It starts after ``{`` or ``,`` and ends before ``,`` or ``}``, so it is
#: never text inside a JSON string (whose quotes are escaped).
_KEY_MEMBER: Final = re.compile(rb'(?<=[{,])"(?:apv:derivationKey":"|subject_key":"ex_|logical_key":"lk_)[a-z2-7]{26}"'
                                rb"(?=[,}])")
_KEY_CUT_RULE: Final = "generic-api-key"
_REDACTED: Final = "REDACTED"
_MAX_LINE_BYTES: Final = 64 << 20
KEY_CUT_CHECK_VERSION: Final = "1"


class ScanError(Exception):
    """The scanner could not run or its output could not be read (exit 3)."""


@dataclass(frozen=True)
class Triage:
    """A reviewed triage file: the sealed root digest it was reviewed for, its sha256 and
    ``fingerprint -> (triage, reason)``."""

    root_digest: str
    sha256: str
    entries: Mapping[str, tuple[str, str]]


@dataclass(frozen=True, order=True)
class Finding:
    path: str
    rule: str
    line: int
    detector: str
    #: ``"reserved"`` or ``"persona"`` for an ``email-address`` finding every address of which was cleared by a rule
    #: (D-810), else ``None``; not part of the fingerprint
    basis: str | None = None

    @property
    def fingerprint(self) -> str:
        return f"{self.path}:{self.rule}:{self.line}"


Runner = Callable[[Sequence[str], Mapping[str, str], float | None], "subprocess.CompletedProcess[bytes]"]


def _run(argv: Sequence[str], env: Mapping[str, str], timeout: float | None) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(list(argv), env=dict(env), capture_output=True, check=False, timeout=timeout)


def _gitleaks(run: Runner, argv: Sequence[str], env: Mapping[str, str], timeout: float | None
              ) -> subprocess.CompletedProcess[bytes]:
    """``run`` with a timeout or another subprocess failure turned into :class:`ScanError` ("gitleaks failed", exit 3),
    never a traceback (whose exit 1 would read as "a finding is untriaged"). The argv, which names local paths, is not
    echoed."""
    try:
        return run(argv, env, timeout)
    except subprocess.TimeoutExpired as exc:
        raise ScanError(f"gitleaks {argv[1]} timed out after {exc.timeout:g} s (--timeout)") from None
    except subprocess.SubprocessError as exc:
        raise ScanError(f"gitleaks {argv[1]} failed ({type(exc).__name__})") from None


# ------------------------------------------------------------------------------------------------ gitleaks
def gitleaks_version(executable: str, *, run: Runner = _run) -> str:
    done = _gitleaks(run, [executable, "version"], _env(tempfile.gettempdir()), 60)
    match = _VERSION_RE.search(done.stdout.decode("ascii", "replace"))
    if done.returncode != 0 or match is None:
        raise ScanError("gitleaks version could not be read")
    if match.group(1) != GITLEAKS_VERSION:  # another version has other default rules (G.9.4; AD-10 row 19)
        raise ScanError(f"gitleaks {match.group(1)} is not the pinned scanner (gitleaks {GITLEAKS_VERSION}, G.9.4); "
                        f"install gitleaks {GITLEAKS_VERSION} or pass it with --gitleaks")
    return match.group(1)


def _env(home: str) -> dict[str, str]:
    return {"HOME": home, "LC_ALL": "C", "PATH": "/usr/bin:/bin"}


def run_gitleaks(executable: str, target: Path, *, archive_depth: int = 0, timeout: float | None = None,
                 run: Runner = _run, matches: dict[str, list[str]] | None = None,
                 redact: bool = True) -> tuple[list[Finding], int]:
    """``gitleaks dir --redact`` over ``target`` with a fixed configuration; returns the findings (paths relative to
    ``target``) and the number of key cuts resolved (:func:`parse_gitleaks_report`). ``matches`` and ``redact=False``
    are for ``tools/release_triage.py`` only (C-3): ``matches`` receives the report's ``Match`` per fingerprint, in
    memory; without ``redact`` the report is read from gitleaks' standard output (``--report-path -``), so an unredacted
    value is never written to a file, and ``Match`` is then the unredacted ``Secret``. No key cut is resolved then.

    ``archive_depth`` stays 0 by default on purpose (D-450): gitleaks' own archive extraction is not bounded by the G.3
    limits (ratio, member count and size, depth), so it never opens third-party archives. They are read decoded by
    AgentPROV's bounded ``expand`` path instead: the sealing scan and the ``chain`` and deposit-builder rescans
    (:mod:`agentprov.corpus.withhold_scan`), and the home-path and host-name search of :func:`path_scan` (D-491).

    gitleaks is given the resolved ``target`` (``os.path.realpath``): it reports ``File`` as the path it was given plus
    the path inside it, so a relative or symlinked argument would otherwise not map back into the tree."""
    target = Path(os.path.realpath(target))
    with tempfile.TemporaryDirectory(prefix="agentprov-release-scan-") as tmp:
        config = Path(tmp, "gitleaks.toml")
        config.write_text(_GITLEAKS_CONFIG, encoding="ascii")
        ignore = Path(tmp, "ignore")
        ignore.mkdir()
        report = Path(tmp, "report.json")
        argv = [executable, "dir", "--no-banner", "--no-color", *(["--redact"] if redact else []),
                "--ignore-gitleaks-allow", "--config", str(config), "--gitleaks-ignore-path", str(ignore),
                "--log-level", "error", "--exit-code", "0", "--max-archive-depth", str(archive_depth),
                "--report-format", "json", "--report-path", str(report) if redact else "-", str(target)]  # fmt: skip
        done = _gitleaks(run, argv, _env(tmp), timeout)
        if not redact:
            if done.returncode != 0:
                raise ScanError(f"gitleaks failed (exit {done.returncode})")
            if len(done.stdout) > _MAX_REPORT_BYTES:
                raise ScanError("the gitleaks report is larger than the limit")
            return parse_gitleaks_report(done.stdout, target, matches=matches, field="Secret")
        if done.returncode != 0 or not report.is_file():
            raise ScanError(f"gitleaks failed (exit {done.returncode})")
        if report.stat().st_size > _MAX_REPORT_BYTES:
            raise ScanError("the gitleaks report is larger than the limit")
        return parse_gitleaks_report(report.read_bytes(), target, matches=matches)


def parse_gitleaks_report(data: bytes, target: Path, *, matches: dict[str, list[str]] | None = None,
                          field: str = "Match") -> tuple[list[Finding], int]:
    """The findings of a gitleaks JSON report: ``File`` (made relative to ``target``), ``RuleID`` and ``StartLine``,
    less the ``generic-api-key`` findings that :func:`key_cut_explained` resolves as cuts of AgentPROV keys; returns them
    with the number of report entries so dropped. ``Line`` is never read; the redacted ``Secret`` and ``Match`` and the
    columns are read for the key-cut check only, in memory. With ``matches`` (C-3), each reported finding's ``field``
    (a string) is added to ``matches[fingerprint]``, in report order, in memory."""
    try:
        items = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ScanError("the gitleaks report is not JSON") from None
    if not isinstance(items, list):
        raise ScanError("the gitleaks report is not a JSON array")
    base = Path(os.path.realpath(target))
    entries: list[tuple[Finding, Path, dict[str, Any]]] = []
    for item in items:
        if not isinstance(item, dict):
            raise ScanError("a gitleaks finding is not an object")
        file, rule, line = item.get("File"), item.get("RuleID"), item.get("StartLine")
        if not isinstance(file, str) or not isinstance(rule, str) or not isinstance(line, int):
            raise ScanError("a gitleaks finding lacks File, RuleID or StartLine")
        path = Path(os.path.realpath(Path(file) if os.path.isabs(file) else base / file))
        try:
            relative = path.relative_to(base).as_posix()
        except ValueError:
            raise ScanError("a gitleaks finding names a file outside the scanned tree") from None
        if not re.fullmatch(r"[A-Za-z0-9._-]+(/[A-Za-z0-9._-]+)*", rule):
            raise ScanError("a gitleaks rule id is not a plain identifier")
        entries.append((Finding(_label(relative), rule, line, "gitleaks"), path, item))
    wanted: dict[Path, set[int]] = {}
    for finding, path, item in entries:
        if finding.rule == _KEY_CUT_RULE and item.get("EndLine") == finding.line:
            wanted.setdefault(path, set()).add(finding.line)
    lines = {(path, number): text for path, numbers in wanted.items()
             for number, text in _read_lines(path, numbers).items()}  # fmt: skip
    out, resolved = set(), 0
    for finding, path, item in entries:
        text = lines.get((path, finding.line))
        if finding.rule == _KEY_CUT_RULE and text is not None and key_cut_explained(text, item):
            resolved += 1
        else:
            out.add(finding)
            if matches is not None and isinstance(item.get(field), str):
                matches.setdefault(finding.fingerprint, []).append(item[field])
    return sorted(out), resolved


def key_cut_explained(line: bytes, item: Mapping[str, Any]) -> bool:
    """True only when a redacted gitleaks finding on ``line`` (the file's own bytes, without the line end) can only be
    (part of) an exact AgentPROV key member; any doubt is False, so the finding is reported.

    gitleaks reports columns from the start of its scan fragment, not of the line, so the position of a cut match is
    unknown; its length (``EndColumn - StartColumn + 1``, bytes), its redacted text (``<before>REDACTED<after>``) and the
    Shannon entropy of the secret are known. Every position on the line where ``<before>``, a value of the implied length
    and ``<after>`` fit is a place the match could be. Each must lie inside a member matched by :data:`_KEY_MEMBER`, and
    at least one must give a value with the reported entropy (so the inferred length is the one gitleaks saw)."""
    match, secret, entropy = item.get("Match"), item.get("Secret"), item.get("Entropy")
    start, end = item.get("StartColumn"), item.get("EndColumn")
    if (item.get("RuleID") != _KEY_CUT_RULE or item.get("StartLine") != item.get("EndLine") or secret != _REDACTED
            or not isinstance(match, str) or match.count(_REDACTED) != 1 or not isinstance(entropy, (int, float))
            or not isinstance(start, int) or not isinstance(end, int)):  # fmt: skip
        return False
    before, after = (part.encode("utf-8") for part in match.split(_REDACTED))
    length = end - start + 1
    value = length - len(before) - len(after)
    if not before or value < 1:
        return False
    starts, members = _key_members(line)
    confirmed = False
    at = line.find(before)
    while at >= 0:
        if at + length <= len(line) and line.startswith(after, at + len(before) + value):
            k = bisect.bisect_right(starts, at) - 1
            if k < 0 or at + length > members[k][1]:
                return False
            begin = at + len(before)
            confirmed = confirmed or abs(_entropy(line[begin:begin + value]) - entropy) < 1e-5
        at = line.find(before, at + 1)
    return confirmed


@functools.lru_cache(maxsize=4)
def _key_members(line: bytes) -> tuple[list[int], list[tuple[int, int]]]:
    """The spans of the exact key members on a line (disjoint, in order) and their starts; cached, because one long line
    can carry several cuts."""
    members = [m.span() for m in _KEY_MEMBER.finditer(line)]
    return [lo for lo, _ in members], members


def _entropy(data: bytes) -> float:
    """gitleaks' Shannon entropy of a secret (bits per character; ``data`` is ASCII inside a key member)."""
    return -sum(n / len(data) * math.log2(n / len(data)) for n in Counter(data).values())


def _read_lines(path: Path, numbers: set[int]) -> dict[int, bytes]:
    """The listed lines (1-based, without the line end) of a regular file, read in bounded pieces; a line longer than
    :data:`_MAX_LINE_BYTES` or a file that cannot be read gives nothing (its findings stay reported)."""
    out: dict[int, bytes] = {}
    if not numbers or path.is_symlink() or not path.is_file():
        return out
    last = max(numbers)
    number, size = 1, 0
    parts: list[bytes] = []
    try:
        with open(path, "rb") as stream:
            while number <= last:
                piece = stream.readline(_CHUNK)
                if number in numbers and size <= _MAX_LINE_BYTES:
                    parts.append(piece)
                    size += len(piece)
                if piece and not piece.endswith(b"\n"):
                    continue
                if parts and size <= _MAX_LINE_BYTES:
                    out[number] = b"".join(parts).removesuffix(b"\n")
                if not piece:
                    break
                number, size, parts = number + 1, 0, []
    except OSError:
        return {}
    return out


def _label(relative: str) -> str:
    """A corpus path is ASCII from a closed grammar; anything else is shown hashed, never verbatim."""
    if re.fullmatch(r"[A-Za-z0-9._/-]{1,200}", relative):
        return relative
    return "#sha256:" + hashlib.sha256(relative.encode("utf-8", "surrogateescape")).hexdigest()


# ------------------------------------------------------------------------------------------------ home path, host name
def personal_needles(home: str | None = None, host: str | None = None) -> dict[str, list[bytes]]:
    """``{rule: [needle bytes]}``: the home path and the host name (full and short; names shorter than four characters
    and ``localhost`` are skipped as too common to mean anything)."""
    home = home if home is not None else str(Path.home())
    host = host if host is not None else socket.gethostname()
    needles: dict[str, list[bytes]] = {"home-path": [], "host-name": []}
    if home and home not in ("/", "/root") and len(home) >= 4:
        needles["home-path"].append(home.encode("utf-8"))
    names = {host, host.split(".", 1)[0]} if host else set()
    needles["host-name"] = sorted(n.encode("utf-8") for n in names if len(n) >= 4 and n.lower() != "localhost")
    return needles


@dataclass(frozen=True)
class Accounts:
    """The account-path search (D-457): ``own`` holds the ``(root, name)`` of the operator's home path when it is
    ``/Users/<name>`` or ``/home/<name>``; that exact path is the ``home-path`` rule's, so it is not reported twice."""

    own: frozenset[tuple[bytes, bytes]] = frozenset()

    @classmethod
    def excluding(cls, homes: Iterable[bytes]) -> Accounts:
        own = set()
        for home in homes:
            match = re.fullmatch(rb"/(Users|home)/([A-Za-z0-9._-]{1,64})/?", home)
            if match is not None:
                own.add((match.group(1), match.group(2)))
        return cls(frozenset(own))

    def offsets(self, window: bytes, start: int) -> set[int]:
        """The offsets in ``window`` (from ``start``) of the account paths to report; never the name itself."""
        out: set[int] = set()
        lowered = window.lower()
        at = lowered.find(b"users", start)
        while at >= 0:
            for pattern, back in _AT_USERS:
                if at - back >= start and (match := pattern.match(window, at - back)) is not None:
                    self._judge(match, out)
            at = lowered.find(b"users", at + 1)
        for literal, pattern in _AT_HOME:
            at = window.find(literal, start)
            while at >= 0:
                if (match := pattern.match(window, at)) is not None:
                    self._judge(match, out)
                at = window.find(literal, at + 1)
        return out

    def _judge(self, match: re.Match[bytes], out: set[int]) -> None:
        """Report a match unless its name (less trailing dots, which may end a sentence) is generic, dots only or a D-604
        redaction label (``acct-<12 hex>`` or ``account-<12 hex>``), or it is the operator's own unescaped ``/Users`` or
        ``/home`` path (the one form ``home-path`` also finds)."""
        name = match.group(match.lastindex or 0).rstrip(b".")
        if not name or name.lower().decode("ascii") in ACCOUNT_ALLOWLIST or REDACTION_LABEL.fullmatch(name):
            return
        if match.lastindex == 2 and (match.group(1), name) in self.own:
            return
        out.add(match.start())


class Emails:
    """The e-mail search (D-810): every address is a hit, cleared only by a rule: its domain is reserved (RFC 2606 and
    6761), or its digest is in ``personas`` (the persona files of the corpus's own spec). Only digests are kept, and
    only when a ``sink`` is given (the helpers); an address is never stored, printed or written. ``where`` is the label
    of the file or member being read, set by the caller, for the sink."""

    def __init__(self, classes: Mapping[str, frozenset[str]] | None = None,
                 sink: Callable[[str, str, str, int], None] | None = None) -> None:
        self.classes = {c: frozenset(classes.get(c, ())) for c in EMAIL_BASES if c != "reserved"} if classes else {}
        self.sink = sink
        self.where = ""

    def judge(self, window: bytes, lo: int, hi: int, lines_before: int) -> set[tuple[str, int]]:
        """``(rule, line)`` for each address whose ``@`` is in ``window[lo:hi]``: ``email-address`` when no rule clears
        it, else ``email-address/<basis>``."""
        out: set[tuple[str, int]] = set()
        for _start, raw in find_addresses(window, lo, hi):
            at = _start + raw.index(b"@")
            line = lines_before + window.count(b"\n", 0, at) + 1
            domain = raw[raw.index(b"@") + 1:].decode("ascii")
            digest = address_digest(raw)
            kind = domain_class(domain)
            basis = "reserved" if kind == CLASS_RESERVED else next(
                (c for c, digests in self.classes.items() if digest in digests), None)
            out.add((_EMAIL_CLEARED[basis] if basis else EMAIL_RULE, line))
            if self.sink is not None:
                self.sink(digest, kind, self.where, line)
        return out


def _settle_emails(found: Iterable[Finding]) -> set[Finding]:
    """One ``email-address`` finding per (file, line): cleared (``basis``) only when every address on the line was."""
    kept: set[Finding] = set()
    groups: dict[tuple[str, int], set[str]] = {}
    for finding in found:
        if finding.rule == EMAIL_RULE or finding.rule in _EMAIL_CLEARED.values():
            groups.setdefault((finding.path, finding.line), set()).add(finding.rule)
        else:
            kept.add(finding)
    for (path, line), rules in groups.items():
        basis = None if EMAIL_RULE in rules else next(b for b in EMAIL_BASES if _EMAIL_CLEARED[b] in rules)
        kept.add(Finding(path, EMAIL_RULE, line, "agentprov-path-scan", basis))
    return kept


def path_scan(target: Path, needles: Mapping[str, Iterable[bytes]], *, accounts: bool = True, secrets: bool = True,
              decode: bool = True, max_depth: int | None = None, workers: int | None = None, in_process: bool = False,
              release: bool = True, emails: Emails | None = None) -> list[Finding]:
    """Search every regular file below ``target`` (no link followed) for the needles, with ``accounts`` (the default)
    for third-party account paths (D-457; the operator's own home path stays ``home-path``) and with ``secrets`` (the
    default) for the secret shapes (D-600); one finding per (file, rule, line). With ``decode`` (the default) every
    archive among them is also read decoded (D-491; module docstring): ``max_depth`` is the declared nesting allowance,
    ``workers`` the T1 worker count; ``in_process`` and ``release=False`` are for tests only. With ``emails`` (the tool
    supplies it) every e-mail address is also a finding, cleared as :class:`Emails` says (D-810)."""
    found: set[Finding] = set()
    pairs = [(rule, needle) for rule, items in needles.items() for needle in items if needle]
    search = Accounts.excluding(needles.get("home-path", ())) if accounts else None
    if not pairs and search is None and not secrets and emails is None:
        return []
    longest = max((len(n) for _, n in pairs), default=1)
    if search is not None:
        longest = max(longest, _ACCOUNT_SPAN)
    if secrets:
        longest = max(longest, _SECRET_SPAN)
    if emails is not None:
        longest = max(longest, _EMAIL_REACH)
    paths: dict[str, list[str]] = {}  # sha256 (bare hex) -> the files with those bytes (target-relative, posix)
    # D-810: a stored file's e-mail hits wait until the decoded scan has run; an archive it read is judged by its
    # decoded members only (compressed bytes match the address shape by chance, about once in 25 MB)
    held: dict[str, list[tuple[str, set[tuple[str, int]], list[tuple[str, str, str, int]]]]] = {}
    sink = emails.sink if emails is not None else None
    for directory, dirs, files in os.walk(target, followlinks=False):
        dirs.sort()
        for name in sorted(files):
            path = Path(directory, name)
            if path.is_symlink() or not path.is_file():
                continue
            relative = path.relative_to(target).as_posix()
            calls: list[tuple[str, str, str, int]] = []
            if emails is not None:
                emails.where = _label(relative)
                emails.sink = None if sink is None else (lambda *call: calls.append(call))  # noqa: B023
            hits, digest = _file_hits(path, pairs, longest, search, secrets, emails)
            mail = {hit for hit in hits if hit[0] in _EMAIL_RULES}
            for rule, line in hits - mail:
                found.add(Finding(_label(relative), rule, line, "agentprov-path-scan"))
            if mail or calls:
                held.setdefault(digest, []).append((relative, mail, calls))
            paths.setdefault(digest, []).append(relative)
    if emails is not None:
        emails.sink = sink
    opened: set[str] = set()
    if decode:
        decoded, opened = _archive_hits(target, paths, pairs, longest, search, secrets, max_depth=max_depth, workers=workers,
                                        in_process=in_process, release=release, emails=emails)  # fmt: skip
        found |= decoded
    for digest, entries in held.items():
        if digest in opened:
            continue
        for relative, mail, calls in entries:
            found.update(Finding(_label(relative), rule, line, "agentprov-path-scan") for rule, line in mail)
            for call in calls:
                if sink is not None:
                    sink(*call)
    return sorted(_settle_emails(found))


def _chunk_hits(chunks: Iterable[bytes], pairs: Sequence[tuple[str, bytes]], longest: int,
                search: Accounts | None = None, secrets: bool = False,
                emails: Emails | None = None) -> set[tuple[str, int]]:
    """``(rule, line)`` for every needle, with ``search`` every account path and with ``secrets`` every secret shape,
    in the concatenated ``chunks`` (a match may straddle two chunks). ``longest`` covers :data:`_ACCOUNT_SPAN` when
    ``search`` is given and :data:`_SECRET_SPAN` with ``secrets``: once the carry has been cut from a longer window, a
    match that starts at its first byte lies wholly in it and was judged, with the byte its look-behind reads, in the
    window before, so the search there starts at offset 1. A secret shape is judged only with the byte after it in the
    window (its look-ahead must see it); at the end of the file that byte is the NUL appended to the last bytes.
    Addresses (``emails``, D-810) are judged once each, by the absolute position of their ``@``: those at least
    :data:`~agentprov.corpus.personas.EMAIL_AHEAD` bytes before the end of the window (whole match and look-ahead inside
    it) in a window, the rest in the next, and the last ones at the end of the file; ``longest`` covers
    :data:`_EMAIL_REACH`, so the carry holds the local part of every address still to be judged."""
    hits: set[tuple[str, int]] = set()
    base = 0  # absolute offset of window[0]
    done = 0  # absolute offset before which every '@' was judged
    carry = b""
    trimmed = False  # bytes precede `carry`
    lines_before = 0  # newlines before the start of `carry`
    for chunk in chunks:
        if not chunk:
            continue
        window = carry + chunk
        for rule, needle in pairs:
            start = 0
            while (at := window.find(needle, start)) >= 0:
                hits.add((rule, lines_before + window.count(b"\n", 0, at) + 1))
                start = at + 1
        if search is not None:
            for at in search.offsets(window, 1 if trimmed else 0):
                hits.add((ACCOUNT_RULE, lines_before + window.count(b"\n", 0, at) + 1))
        if secrets:
            for rule, at in _secret_offsets(window, 1 if trimmed else 0):
                hits.add((rule, lines_before + window.count(b"\n", 0, at) + 1))
        if emails is not None and len(window) - EMAIL_AHEAD > max(0, done - base):
            lo, hi = max(0, done - base), len(window) - EMAIL_AHEAD
            hits |= emails.judge(window, lo, hi, lines_before)
            done = base + hi
        keep = max(longest - 1, 0)
        carry = window[-keep:] if keep and len(window) > keep else (window if keep else b"")
        base += len(window) - len(carry)
        trimmed = trimmed or len(window) > len(carry)
        lines_before += window.count(b"\n") - carry.count(b"\n")
    if carry and (search is not None or secrets or emails is not None):  # a match the end of the file ends: the last
        # bytes, a NUL after them
        last = carry + b"\x00"
        if emails is not None:
            hits |= emails.judge(last, max(0, done - base), len(last), lines_before)
        if search is not None:
            for at in search.offsets(last, 1 if trimmed else 0):
                hits.add((ACCOUNT_RULE, lines_before + carry.count(b"\n", 0, at) + 1))
        if secrets:
            for rule, at in _secret_offsets(last, 1 if trimmed else 0):
                hits.add((rule, lines_before + carry.count(b"\n", 0, at) + 1))
    return hits


def _secret_offsets(window: bytes, start: int) -> set[tuple[str, int]]:
    """``(rule, offset)`` of the secret shapes in ``window`` from ``start`` (D-600): each literal is found, then its
    shape matched there; a match that ends the window is left to the next window or the end-of-file pass, because its
    look-ahead has not seen the byte after it. Never the match itself."""
    out: set[tuple[str, int]] = set()
    for rule, literal, pattern in _SECRETS:
        at = window.find(literal, start)
        while at >= 0:
            if (match := pattern.match(window, at)) is not None and match.end() < len(window):
                out.add((rule, at))
            at = window.find(literal, at + 1)
    return out


def _file_chunks(path: Path) -> Iterator[bytes]:
    with open(path, "rb") as stream:
        while chunk := stream.read(_CHUNK):
            yield chunk


def _file_hits(path: Path, pairs: Sequence[tuple[str, bytes]], longest: int, search: Accounts | None,
               secrets: bool, emails: Emails | None = None) -> tuple[set[tuple[str, int]], str]:
    """The ``(rule, line)`` hits of one file and the sha256 of its bytes (one read)."""
    digest = hashlib.sha256()

    def chunks() -> Iterator[bytes]:
        for chunk in _file_chunks(path):
            digest.update(chunk)
            yield chunk

    return _chunk_hits(chunks(), pairs, longest, search, secrets, emails), digest.hexdigest()


def _archive_hits(target: Path, paths: Mapping[str, Sequence[str]], pairs: Sequence[tuple[str, bytes]], longest: int,
                  search: Accounts | None, secrets: bool, *, max_depth: int | None, workers: int | None,
                  in_process: bool, release: bool, emails: Emails | None = None) -> tuple[set[Finding], set[str]]:
    """The findings in the decoded members of the archives below ``target`` (D-491): ``<path>#<member locator>``, or
    ``home-path-unscanned`` on the path of an archive that could not be read; and the archives read whole (a member read,
    nothing left unscanned; bare hex), whose stored bytes the e-mail rule does not judge (D-810)."""
    from agentprov.corpus.withhold import Rule, _released_members
    from agentprov.corpus.withhold_scan import scan_archives

    def stream(label: str) -> Iterator[bytes]:
        return _file_chunks(target / label)

    located: set[tuple[str, str, str, int]] = set()  # (archive sha256, member locator, rule, line)
    opened: set[str] = set()  # archives with a member read

    def member_scan(root: str, locator: str, part: str, chunks: Iterable[bytes]) -> frozenset[str]:
        opened.add(root)
        if emails is not None:
            emails.where = f"{_label(paths[root][0])}#{locator}"
        hits = _chunk_hits(chunks, pairs, longest, search, secrets, emails)
        located.update((root, locator, rule, line if part == "data" else 0) for rule, line in hits)
        return frozenset(rule for rule, _line in hits)

    objects = {sha: labels[0] for sha, labels in paths.items()}
    labels = sorted(label for group in paths.values() for label in group)
    # One rule per needle rule, one for account paths and one per secret shape: the gate of scan_archives and the ids
    # member_scan returns; member_scan does the search.
    first: dict[str, bytes] = {}
    for rule, needle in pairs:
        first.setdefault(rule, needle)
    rules = [Rule(id=rule, kind="marker", scope="object", reason="home path or host name (R-51)", public_note="",
                  needle=needle, width=len(needle)) for rule, needle in first.items()]  # fmt: skip
    if search is not None:
        rules.append(Rule(id=ACCOUNT_RULE, kind="pattern", scope="object", reason="account path (D-457)", public_note="",
                          regex=_ACCOUNT_PATH, width=_ACCOUNT_SPAN))  # fmt: skip
    if secrets:
        rules.extend(Rule(id=rule, kind="pattern", scope="object", reason="secret shape (D-600)", public_note="",
                          regex=pattern, width=_SECRET_SPAN) for rule, _literal, pattern in _SECRETS)  # fmt: skip
    if emails is not None:
        rules.append(Rule(id=EMAIL_RULE, kind="pattern", scope="object", reason="e-mail address (D-810)", public_note="",
                          regex=EMAIL_PATTERN, width=_EMAIL_REACH))
    decoded = scan_archives(objects, stream, rules, release=release, workers=workers, in_process=in_process,
                            max_depth=max_depth, members=_released_members(labels, stream),
                            member_scan=member_scan)  # fmt: skip
    found = {Finding(f"{_label(label)}#{locator}", rule, line, "agentprov-path-scan")
             for sha, locator, rule, line in located for label in paths[sha]}  # fmt: skip
    found |= {Finding(_label(label), UNSCANNED_RULE, 0, "agentprov-path-scan")
              for sha in decoded.unscanned for label in paths[sha]}  # fmt: skip
    return found, opened - set(decoded.unscanned)


def declared_depth(root: Path) -> int | None:
    """The largest ``max_depth`` of the ``[[import.nested]]`` declarations of the source profiles a corpus records
    (``corpus.json`` ``profiles.source``; D-382), or ``None``: the decoded scan then opens archives as deep as the
    sealing scan does (D-452). A profile that cannot be read is skipped (the default depth applies: stricter)."""
    from agentprov.corpus.withhold import _declared_depth

    try:
        manifest = json.loads((root / "corpus.json").read_bytes())
    except (OSError, ValueError):
        return None
    refs = manifest.get("profiles", {}).get("source", []) if isinstance(manifest, dict) and isinstance(
        manifest.get("profiles"), dict) else []  # fmt: skip
    depths: list[int] = []
    for ref in refs if isinstance(refs, list) else []:
        relative = ref.get("path") if isinstance(ref, dict) else None
        if not isinstance(relative, str) or not re.fullmatch(r"[A-Za-z0-9._-]+(/[A-Za-z0-9._-]+)*", relative) or any(
                part in (".", "..") for part in relative.split("/")):  # fmt: skip
            continue
        path = root / relative
        try:
            if path.is_symlink() or not path.is_file():
                continue
            depth = _declared_depth(tomllib.loads(path.read_text(encoding="utf-8")))
        except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
            continue
        if depth is not None:
            depths.append(depth)
    return max(depths, default=None)


# ------------------------------------------------------------------------------------------------ triage and document
def load_triage(data: bytes) -> Triage:
    """A triage TOML file: a top-level ``root_digest`` (the sealed root digest it was reviewed for, D-42) and
    ``[[triage]]`` tables."""
    try:
        doc = tomllib.loads(data.decode("utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError):
        raise ValueError("the triage file is not UTF-8 TOML") from None
    if set(doc) - {"root_digest", "triage"} or not isinstance(doc.get("triage", []), list):
        raise ValueError("the triage file holds a root_digest and [[triage]] tables only")
    bound = doc.get("root_digest")
    if not isinstance(bound, str) or not _ROOT_DIGEST_RE.fullmatch(bound):
        raise ValueError('the triage file names no root_digest = "sha256:<64 hex>" (triage is per sealed root digest, '
                         "D-42)")
    out: dict[str, tuple[str, str]] = {}
    for entry in doc.get("triage", []):
        if not isinstance(entry, dict) or set(entry) != {"fingerprint", "triage", "reason"}:
            raise ValueError("a [[triage]] table is {fingerprint, triage, reason}")
        if entry["triage"] not in TRIAGE_VALUES or not isinstance(entry["reason"], str) or not entry["reason"].strip():
            raise ValueError("a triage is real|synthetic-benchmark|false-positive|home-path|pinned-account with a reason")
        if not isinstance(entry["fingerprint"], str) or entry["fingerprint"] in out:  # before any string method
            raise ValueError("a fingerprint is a string, triaged once")
        if entry["triage"] == "pinned-account" and not (entry["fingerprint"].startswith("raw/")
                                                        and ":account-path:" in entry["fingerprint"]):
            raise ValueError("pinned-account triages an account-path finding in raw/ only (D-604 item 7)")
        out[entry["fingerprint"]] = (entry["triage"], entry["reason"])
    return Triage(bound, hashlib.sha256(data).hexdigest(), out)


def check_triage_bound(triage: Triage | None, target: Mapping[str, Any]) -> None:
    """Refuse (``ValueError``) a triage file reviewed for another sealed root digest than the scanned one (D-42)."""
    if triage is not None and triage.root_digest != target.get("root_digest"):
        raise ValueError(f"the triage file was reviewed for root digest {triage.root_digest}, not "
                         f"{target.get('root_digest')}; review the findings of this sealed version in a new triage file "
                         "(D-42)")


#: What a clearing basis says in the scan document: the triage it gives and the reason text.
BASIS_TRIAGE: Final = {"reserved": "false-positive", "upstream-data": "synthetic-benchmark",
                       "benchmark-input": "synthetic-benchmark", "model-generated": "model-generated",
                       "file-name": "false-positive"}
_BASIS_TEXT: Final = {
    "upstream-data": "every address on the line is a persona found in the benchmark's own source data",
    "benchmark-input": "every address on the line was supplied by the benchmark in the run (first appearance in benchmark input)",
    "model-generated": "an address on the line appears only in model output: kept, disclosed, not a benchmark persona",
    "file-name": "not an address: a string with its shape (a file name) that a person reviewed",
}


def _basis_decision(finding: Finding, personas: Mapping[str, Any] | None) -> tuple[str, str] | None:
    """The triage a rule gives an ``email-address`` finding (D-810), or ``None``: a reserved-domain line is a
    ``false-positive``; a line cleared through the corpus's own persona files takes the triage of its class."""
    if finding.basis == "reserved":
        return "false-positive", REASON_RESERVED
    if finding.basis in BASIS_TRIAGE and personas is not None:
        return BASIS_TRIAGE[finding.basis], (f"{finding.basis} entry of this corpus (spec {personas['spec_sha256']}; "
                                             f"{personas['classes'][finding.basis]} digests): {_BASIS_TEXT[finding.basis]}")
    return None


def scan_document(target: Mapping[str, Any], tools: Sequence[Mapping[str, Any]], findings: Iterable[Finding],
                  triage: Triage | None, personas: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """The scan document. A human triage entry decides its fingerprint, a rule (``basis``) decides the rest of the
    ``email-address`` findings it clears; the row says ``basis`` only when a rule decided. ``personas`` records the
    spec and persona files the persona rule read (``spec_sha256`` is what the deposit builder compares with the sealed
    ``files.spec``)."""
    check_triage_bound(triage, target)
    rows = []
    by_triage: dict[str, int] = {}
    decisions = triage.entries if triage is not None else {}
    for finding in sorted(set(findings)):
        decided = decisions.get(finding.fingerprint)
        by_rule = None if decided else _basis_decision(finding, personas)
        decided = decided or by_rule
        rows.append({"basis": finding.basis if by_rule else None, "detector": finding.detector,
                     "fingerprint": finding.fingerprint, "line": finding.line,
                     "path": finding.path, "reason": decided[1] if decided else None,
                     "rule": finding.rule, "triage": decided[0] if decided else None})  # fmt: skip
        key = decided[0] if decided else "untriaged"
        by_triage[key] = by_triage.get(key, 0) + 1
    bound = None if triage is None else {"root_digest": triage.root_digest, "sha256": triage.sha256}
    return {"findings": rows, "format": FORMAT, "personas": None if personas is None else dict(personas),
            "summary": {"by_triage": dict(sorted(by_triage.items())), "findings": len(rows)}, "target": dict(target),
            "tools": [dict(t) for t in tools], "triage": bound}  # fmt: skip


class Personas:
    """The reviewed digests a sealed corpus clears (D-810), by class, read from its own tree: ``rules/corpus-spec.toml`` (its
    sha256 must equal ``files.spec`` of the manifest) names persona files by path and sha256; each is read from
    ``rules/personas/`` and checked. ``record`` is what the scan document records."""

    def __init__(self, spec_sha256: str, files: Sequence[Mapping[str, str]], classes: Mapping[str, frozenset[str]]) -> None:
        self.spec_sha256, self.files, self.classes = spec_sha256, list(files), dict(classes)

    @property
    def record(self) -> dict[str, Any]:
        return {"classes": {b: len(self.classes.get(b, ())) for b in EMAIL_BASES if b != "reserved"},
                "files": [dict(f) for f in self.files], "spec_sha256": self.spec_sha256}


def load_personas(root: Path) -> Personas:
    """The persona list of the sealed corpus at ``root``. Raises ``ValueError`` when the spec copy does not match the
    manifest or a persona file does not match the spec."""
    from agentprov.corpus.spec import CorpusSpecError, parse_spec

    try:
        manifest = json.loads((root / "corpus.json").read_bytes())
        recorded = manifest["files"]["spec"]["sha256"]
        spec_bytes = (root / "rules" / "corpus-spec.toml").read_bytes()
    except (OSError, ValueError, KeyError, TypeError):
        raise ValueError("the sealed corpus has no readable corpus.json files.spec and rules/corpus-spec.toml") from None
    if sha256_label(spec_bytes) != recorded:
        raise ValueError("rules/corpus-spec.toml does not match files.spec of corpus.json")
    try:
        spec = parse_spec(spec_bytes)
    except CorpusSpecError as exc:
        raise ValueError(f"the sealed corpus spec is not valid ({exc})") from None
    files = []
    contents: list[bytes] = []
    for relative, wanted in spec.persona_files:
        name = relative.rsplit("/", 1)[-1]
        try:
            data = (root / "rules" / "personas" / name).read_bytes()
        except OSError:
            raise ValueError(f"the persona file {name} the spec names is not in the sealed corpus") from None
        if sha256_label(data) != wanted:
            raise ValueError(f"the persona file {name} differs from the sha256 the spec records")
        try:
            parse_persona_file(data)
        except ValueError as exc:
            raise ValueError(f"the persona file {name} is not valid: {exc}") from None
        contents.append(data)
        files.append({"name": name, "sha256": wanted})
    try:
        classes = persona_digests(contents)
    except ValueError as exc:
        raise ValueError(str(exc)) from None
    return Personas(recorded, files, classes)


@dataclass
class AddressStat:
    """What the helpers know about one distinct address: its digest is the key; never the address."""

    klass: str
    findings: set[tuple[str, str, int]]  # (corpus, file or member label, line)
    stages: set[str]


def stage_of(where: str) -> str:
    """The layer a file label belongs to: its top directory (``raw``, ``aer``, ``sem``, ``prov``...), else ``other``."""
    head = where.split("#", 1)[0]
    return head.split("/", 1)[0] if "/" in head else "other"


def collect_addresses(target: Path, name: str, table: dict[str, AddressStat], *, workers: int | None = None,
                      in_process: bool = False, release: bool = True) -> int:
    """Read every file below ``target`` (stored files and decoded archive members, as the scan does) and add each distinct
    address to ``table`` as a digest with its class, the (file, line)s it is on and the layers; returns the number of
    archives that could not be read. Read-only; nothing about an address but its digest and class is kept."""

    def sink(digest: str, klass: str, where: str, line: int) -> None:
        stat = table.get(digest)
        if stat is None:
            stat = table[digest] = AddressStat(klass, set(), set())
        stat.findings.add((name, where, line))
        stat.stages.add(stage_of(where))

    found = path_scan(target, {}, accounts=False, secrets=False, max_depth=declared_depth(target), workers=workers,
                      in_process=in_process, release=release, emails=Emails(None, sink))
    return sum(1 for f in found if f.rule == UNSCANNED_RULE)


def list_addresses(targets: Sequence[Path], *, workers: int | None = None) -> int:
    """``--list-addresses``: one line per distinct address over ``targets`` (corpus trees, sealed or working):
    ``<digest> <class> findings=<n> corpora=<a,b> stages=<x,y>``. Never an address."""
    table: dict[str, AddressStat] = {}
    unread = 0
    for target in targets:
        name = target.name.removesuffix(".partial")
        unread += collect_addresses(Path(os.path.realpath(target)), name, table, workers=workers)
    for digest in sorted(table):
        stat = table[digest]
        print(f"{digest} {stat.klass} findings={len(stat.findings)} corpora={','.join(sorted({c for c, _, _ in stat.findings}))}"
              f" stages={','.join(sorted(stat.stages))}")
    print(f"release_scan: {len(table)} distinct address(es); {unread} archive(s) could not be read", file=sys.stderr)
    return 1 if unread else 0


def corpus_target(root: Path) -> dict[str, Any]:
    from agentprov.corpus.integrity import root_digest
    from agentprov.corpus.reader import CorpusReader

    reader = CorpusReader.open(root)
    if not reader.sealed or reader.used_partial:
        raise ValueError("the target is not a sealed corpus; seal it first (the scan is bound to the root digest)")
    manifest = reader.manifest() or {}
    return {"corpus_id": manifest.get("corpus_id"), "corpus_version": manifest.get("corpus_version"), "kind": "corpus",
            "root_digest": root_digest(reader.root)}


def native_findings(reported: Iterable[Finding], native: Iterable[Finding]) -> list[Finding]:
    """The path-scan findings less those whose fingerprint (``<path>:<rule>:<line>``) gitleaks already reported
    (D-600): a secret shape in a stored file is found by both, under the same rule id, and is reported once, as
    gitleaks'. A finding in an archive member (``<path>#<locator>``) never collides, because gitleaks does not read
    members."""
    seen = {finding.fingerprint for finding in reported}
    return [finding for finding in native if finding.fingerprint not in seen]


def scan(root: Path, *, gitleaks: str, triage: Triage | None = None, timeout: float | None = None,
         run: Runner = _run, needles: Mapping[str, Iterable[bytes]] | None = None,
         accounts: bool = True) -> dict[str, Any]:
    """Scan one sealed corpus and return its ``agentprov-release-scan/0.1`` document. A triage file reviewed for
    another root digest is refused (``ValueError``) before gitleaks runs. ``accounts=False`` (tests only) leaves out the
    account-path search (D-457). ``root`` is resolved first (``os.path.realpath``), so a relative path, ``.`` or a
    symlink scans and labels the same tree."""
    root = Path(os.path.realpath(root))
    target = corpus_target(root)
    check_triage_bound(triage, target)
    version = gitleaks_version(gitleaks, run=run)
    personas = load_personas(root)
    findings, resolved = run_gitleaks(gitleaks, root, timeout=timeout, run=run)
    findings += native_findings(findings, path_scan(root, personal_needles() if needles is None else needles,
                                                    accounts=accounts, max_depth=declared_depth(root),
                                                    emails=Emails(personas.classes)))
    gitleaks_tool = {"name": "gitleaks", "version": version, "config_sha256": GITLEAKS_CONFIG_SHA256,
                     "key_cuts_resolved": resolved,
                     "mode": "dir --redact --ignore-gitleaks-allow (default rules + the AgentPROV key allowlist + "
                             f"key-cut check {KEY_CUT_CHECK_VERSION})"}  # fmt: skip
    tools: list[dict[str, Any]] = [gitleaks_tool, {"name": PATH_SCAN_TOOL, "version": PATH_SCAN_VERSION,
                                                   "mode": "home path, host name, third-party account paths (D-457), "
                                                           "secret shapes (D-600) and e-mail addresses (D-810), in "
                                                           "stored bytes and in decoded unselected archive members "
                                                           "(D-491)"}]
    return scan_document(target, tools, findings, triage, personas.record)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="release_scan.py", description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("corpus", nargs="+", help="a sealed corpus directory (with --list-addresses: one or more corpus "
                                                  "trees, sealed or working)")
    parser.add_argument("--list-addresses", action="store_true",
                        help="print one line per distinct e-mail address: its digest, domain class, number of findings, "
                             "corpora and layers; never an address; no gitleaks, no output file (D-810)")
    parser.add_argument("--triage", help="TOML file: root_digest and [[triage]] {fingerprint, triage, reason}")
    parser.add_argument("--out", help="output path (default: <corpus>.release-scan.json beside the resolved corpus)")
    parser.add_argument("--gitleaks", help="the gitleaks executable (default: from PATH)")
    parser.add_argument("--timeout", type=float, help="gitleaks timeout in seconds")
    args = parser.parse_args(argv)
    if args.list_addresses:
        return list_addresses([Path(c) for c in args.corpus])
    if len(args.corpus) != 1:
        print("release_scan: scan one sealed corpus at a time", file=sys.stderr)
        return 2
    args.corpus = args.corpus[0]
    from agentprov.release.builder import scan_path_for

    # Resolved as the deposit builder resolves it (``scan_path_for(reader.root)``, a realpath), so the default output
    # is where the builder looks for it, also for a relative path, ``.`` or a symlink to the sealed directory.
    root = Path(os.path.realpath(args.corpus))
    try:
        out = Path(args.out) if args.out else scan_path_for(root)
    except ValueError as exc:  # the file-system root: no name to put the scan beside
        print(f"release_scan: {exc}", file=sys.stderr)
        return 2
    executable = args.gitleaks or shutil.which("gitleaks")
    if executable is None:
        print("release_scan: gitleaks is not installed (G.9.4)", file=sys.stderr)
        return 3
    try:
        triage = load_triage(Path(args.triage).read_bytes()) if args.triage else None
    except (OSError, ValueError) as exc:
        print(f"release_scan: {exc}", file=sys.stderr)
        return 2
    try:
        document = scan(root, gitleaks=os.path.abspath(executable), triage=triage, timeout=args.timeout)
    except ScanError as exc:
        print(f"release_scan: {exc}", file=sys.stderr)
        return 3
    except (ValueError, OSError) as exc:
        print(f"release_scan: {exc}", file=sys.stderr)
        return 2
    out.write_text(json.dumps(document, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    summary = document["summary"]
    print(f"release_scan: {summary['findings']} finding(s) {json.dumps(summary['by_triage'], sort_keys=True)}; "
          f"root digest {document['target']['root_digest']}; written to {out}", file=sys.stderr)
    untriaged = summary["by_triage"].get("untriaged", 0)
    return 1 if untriaged or summary["by_triage"].get("real", 0) else 0


if __name__ == "__main__":
    sys.exit(main())
