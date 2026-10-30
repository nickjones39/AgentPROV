"""Reviewed e-mail addresses as digests, and the e-mail rule's shared pieces (D-810; HL H.1.6 ``[scan]``, G.9.4).

Benchmarks invent people (an assistant's user, a victim, an attacker) with e-mail addresses, models invent or copy
more, and agent-security corpora quote all of them in every layer. The release scan (``tools/release_scan.py``) reports
every address it finds; a corpus clears the ones a person reviewed through a **persona file**, which holds **digests,
never addresses** (the repository will be public, and some benchmarks' content must not be quoted):
``"sha256:" + hex(sha256(normalised address))``. A digest matches exactly and reveals nothing about an address that is not
already known.

**Normalisation** (:func:`normalise_address`): the address exactly as the scan matched it (``local@domain``; ASCII by
construction), with the ASCII letters lower-cased. Nothing else changes: no trimming of ``+tags`` or dots, no Unicode
folding (the scan matches ASCII only). A local part longer than 64 characters is taken as its last 64. A local part
that starts right after a backslash does not begin with a JSON escape: in ``\nname@host.org`` (a newline before the
address, as JSON stores it) or ``\u003cname@host.org`` (``<``), and in the double-escaped ``\\n`` of a JSON string inside
JSON (there only ``n``, ``r``, ``t`` and ``uXXXX``), the escape is not part of the local part, so the digest is that of the
decoded address. A local part that would be empty without it is kept as read (still a finding).

**Persona file** (``agentprov-personas/0.1``, TOML, closed)::

    format = "agentprov-personas/0.1"
    id = "agentdojo-v1"
    [[group]]                      # upstream-data and file-name: one group per evidence file
    class = "upstream-data"        # optional (default); see the classes below
    source_id = "agentdojo"
    repo = "https://github.com/ethz-spylab/agentdojo"     # or: doi = "10.5281/zenodo.NNN"
    commit = "<40 hex>"            # the pinned commit the file was read at (a doi pin: none)
    file = "src/agentdojo/default_suites/v1/workspace/injection_tasks.py"
    addresses = ["sha256:<64 hex>", ...]                   # sorted, unique

    [[group]]                      # benchmark-input and model-generated: one group per corpus, an entry per address
    class = "model-generated"
    source_id = "agentdojo"
    repo = "..."; commit = "..."   # the corpus's pinned source
    corpus_id = "agentdojo-upstream-2024-06"
    entries = [{ address = "sha256:...", ex = "ex_...", record = "m12", pointer = "/parts/0/text", actor_kind = "llm_agent" }]

**Classes**, each with its own release-scan triage and basis (G.9.4); the builder and the datasheet keep them apart:

* ``upstream-data``: an address of the benchmark's fictional people, found in the benchmark's own source files (suite
  definitions, task files, fixtures) at a pinned commit; evidence is that file. Triage ``synthetic-benchmark``, basis
  ``upstream-data``.
* ``benchmark-input``: an address that is not in the benchmark's source files but that the benchmark supplied in the run:
  its first appearance in each execution's AER is in benchmark input (a user or task message, a tool result, an
  injection, an environment or header field). Evidence is the AER location of that first appearance (execution id,
  record id, JSON pointer inside the record) and the actor kind. Triage ``synthetic-benchmark``, basis ``benchmark-input``.
* ``model-generated``: an address that appears only in model output (an assistant message or a tool call's arguments)
  and never earlier in benchmark input: invented, copied or mangled by the model. Kept, disclosed in the datasheet with
  counts, **never** ``synthetic-benchmark``. Evidence as for ``benchmark-input``. Triage ``model-generated``.
* ``withhold``: an address that must not be released: it appears only in model output, at a public mail provider, so it may
  be a third party's real address (never a benchmark persona, and withheld whatever the outcome of the execution). It is
  **not** cleared by the release scan; sealing withholds the executions whose AER holds it (G.9.5). Evidence as for
  ``model-generated``.
* ``withhold-object``: an address in no AER and no derived record, only in raw objects that no execution indexes (an
  object the import stores but does not map, such as a run of a part it does not import). Withholding by execution
  cannot reach it, so sealing withholds **the objects** that hold it (the same ``address`` rule; no execution is
  affected). Evidence is the first such object's sha256 (``entries = [{ address, object }]``). Not cleared by the scan.
* ``file-name``: a match that is not an address at all, a file name such as ``icon@2x.png`` with the shape of one.
  Triage ``false-positive``, basis ``file-name``. There is no denylist of extensions (a real address at a country
  domain such as ``.py`` or ``.md`` would pass unseen): each is cleared **by digest, for the corpus whose spec names the
  file**, after a person looked at it. Its evidence names the file of the corpus's own pinned source that holds it.

A digest has exactly one class in the files a spec names. The corpus spec references a persona file by relative path and
sha256 (``[scan] personas``). The spec's own digest is recorded in the sealed manifest (``files.spec``) and the persona file
is sealed under ``rules/personas/``, so the list that cleared a release scan is bound to the corpus's root digest. A list
clears a corpus only through its own spec.

This module is pure: bytes in, values out, no I/O.
"""

from __future__ import annotations

import hashlib
import re
import tomllib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Final

__all__ = [
    "CLASS_FREEMAIL",
    "CLASS_OTHER",
    "CLASS_RESERVED",
    "CORPUS_CLASSES",
    "EMAIL_AHEAD",
    "GROUP_CLASSES",
    "OBSERVED_CLASSES",
    "EMAIL_BEHIND",
    "EMAIL_PATTERN",
    "PERSONA_FORMAT",
    "PERSONA_NAME_RE",
    "PersonaError",
    "PersonaFile",
    "WITHHOLD_CLASSES",
    "address_digest",
    "domain_class",
    "find_addresses",
    "is_reserved_domain",
    "normalise_address",
    "parse_persona_file",
    "persona_digests",
    "sha256_label",
]

PERSONA_FORMAT: Final = "agentprov-personas/0.1"
#: A persona file's basename (also its name under ``rules/personas/``).
PERSONA_NAME_RE: Final = re.compile(r"[a-z0-9][a-z0-9_.-]{0,80}\.personas\.toml")
CLASS_RESERVED: Final = "reserved"
CLASS_FREEMAIL: Final = "public-freemail"
CLASS_OTHER: Final = "other"

#: The characters of a local part the scan recognises, and how many before the ``@`` it reads.
_LOCAL: Final = re.compile(rb"[A-Za-z0-9._%+-]")
#: A JSON escape whose letters are local-part characters (``\n``, ``\t``, ``\r``, ``\b``, ``\f``, ``\uXXXX``): after a
#: backslash it is not the start of a local part.
_ESCAPE: Final = re.compile(rb"[ntrbf]|u[0-9A-Fa-f]{4}")
#: After an even run of backslashes (an escaped backslash, as a JSON string inside JSON stores an escape) only the common
#: escapes count; ``\\\\bob`` is a backslash and ``bob``.
_ESCAPE_TWICE: Final = re.compile(rb"[ntr]|u[0-9A-Fa-f]{4}")
EMAIL_BEHIND: Final = 64
#: The match is bounded: a domain is at most 13 labels of 63 characters and a TLD of 2 to 24 letters (about 920 bytes),
#: and the look-ahead reads one more. Fixed repetition counts, so a hostile run of label characters or dots is matched in
#: time linear in its length, never quadratic.
EMAIL_AHEAD: Final = 1024
#: ``@`` preceded by a local-part character (the look-behind), then the domain. Matched anchored at the ``@``.
EMAIL_PATTERN: Final = re.compile(
    rb"(?<=[A-Za-z0-9._%+-])@[A-Za-z0-9-]{1,63}(?:\.[A-Za-z0-9-]{1,63}){0,12}\.[A-Za-z]{2,24}(?![A-Za-z0-9-])")

#: RFC 2606 and RFC 6761 only: names that cannot be a real mailbox. ``test.com`` and the like are registered domains and
#: are **not** reserved.
_RESERVED_NAMES: Final = frozenset({"example.com", "example.net", "example.org"})
_RESERVED_TLDS: Final = frozenset({"example", "test", "invalid", "localhost"})
#: Public mail providers: an address there is never judged by its domain.
_FREEMAIL: Final = frozenset({
    "gmail.com", "googlemail.com", "outlook.com", "hotmail.com", "live.com", "msn.com", "yahoo.com", "ymail.com",
    "proton.me", "protonmail.com", "pm.me", "icloud.com", "me.com", "mac.com", "aol.com", "gmx.com", "gmx.net",
    "mail.com", "zoho.com", "yandex.com", "qq.com", "163.com", "126.com", "fastmail.com", "tutanota.com",
})  # fmt: skip

_DIGEST: Final = re.compile(r"sha256:[0-9a-f]{64}")
_HEX40: Final = re.compile(r"[0-9a-f]{40}")
_DOI: Final = re.compile(r"10\.[0-9]{4,9}/[A-Za-z0-9._;()/:-]+")
_ID: Final = re.compile(r"[a-z0-9][a-z0-9_.-]{0,63}")
_REPO: Final = re.compile(r"https://[A-Za-z0-9.-]+/[A-Za-z0-9_.~/-]+")
_FILE: Final = re.compile(r"[^\x00-\x1f\x7f]{1,300}")
_CONTROL: Final = re.compile(r"[\x00-\x1f\x7f]")


class PersonaError(ValueError):
    """A persona file is malformed or does not match what the spec says of it."""


def normalise_address(raw: bytes) -> str:
    """The normalised form of a matched address (see the module docstring); ``raw`` is ASCII."""
    return raw.decode("ascii").lower()


def sha256_label(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def address_digest(raw: bytes) -> str:
    """``"sha256:" + hex`` of the normalised address."""
    return sha256_label(normalise_address(raw).encode("ascii"))


def is_reserved_domain(domain: str) -> bool:
    d = domain.lower().rstrip(".")
    return d in _RESERVED_NAMES or d.rsplit(".", 1)[-1] in _RESERVED_TLDS


def domain_class(domain: str) -> str:
    d = domain.lower().rstrip(".")
    if is_reserved_domain(d):
        return CLASS_RESERVED
    return CLASS_FREEMAIL if d in _FREEMAIL else CLASS_OTHER


def find_addresses(window: bytes, lo: int = 0, hi: int | None = None) -> list[tuple[int, bytes]]:
    """``(offset of the local part, address bytes as matched)`` for every address whose ``@`` lies in ``[lo, hi)`` of
    ``window``. The local part is the run of local-part characters before the ``@`` (at most :data:`EMAIL_BEHIND`)."""
    out: list[tuple[int, bytes]] = []
    end = len(window) if hi is None else hi
    at = window.find(b"@", lo, end)
    while at >= 0:
        match = EMAIL_PATTERN.match(window, at)
        if match is not None:
            start = at
            while start > 0 and at - start < EMAIL_BEHIND and _LOCAL.match(window, start - 1):
                start -= 1
            slashes = 0
            while start - slashes > 0 and window[start - slashes - 1] == 0x5C:
                slashes += 1
            if slashes and (esc := (_ESCAPE if slashes % 2 else _ESCAPE_TWICE).match(window, start)) is not None \
                    and esc.end() < at:  # a JSON escape before the address is not its local part
                start = esc.end()
            out.append((start, window[start:match.end()]))
        at = window.find(b"@", at + 1, end)
    return out


GROUP_CLASSES: Final = ("upstream-data", "benchmark-input", "model-generated", "file-name", "withhold", "withhold-object")
#: Classes whose group holds ``entries`` (one AER location per address) instead of ``addresses`` of one file.
OBSERVED_CLASSES: Final = ("benchmark-input", "model-generated", "withhold")
#: Classes evidenced by a corpus's own records (an AER location, or a raw object): a group names its ``corpus_id`` and
#: applies to that corpus only.
CORPUS_CLASSES: Final = (*OBSERVED_CLASSES, "withhold-object")
#: The classes sealing withholds (G.9.5): by execution (``withhold``) or by raw object (``withhold-object``).
WITHHOLD_CLASSES: Final = ("withhold", "withhold-object")
_EX: Final = re.compile(r"ex_[a-z0-9-]{26,36}")
_RECORD: Final = re.compile(r"[A-Za-z0-9_.#!-]{1,40}")
_KIND: Final = re.compile(r"[a-z][a-z_]{1,29}")


@dataclass(frozen=True)
class PersonaFile:
    """A parsed persona file: its id, its groups (evidence and digests) and the digests of each class (``by_class``)."""

    id: str
    groups: tuple[Mapping[str, Any], ...]
    by_class: Mapping[str, frozenset[str]]

    @property
    def digests(self) -> frozenset[str]:
        """The ``upstream-data`` digests."""
        return self.by_class.get("upstream-data", frozenset())

    @property
    def file_names(self) -> frozenset[str]:
        return self.by_class.get("file-name", frozenset())


def _closed(table: Mapping[str, Any], where: str, required: set[str], optional: Iterable[str] = ()) -> None:
    keys = set(table)
    if missing := required - keys:
        raise PersonaError(f"{where}: missing {sorted(missing)}")
    if extra := keys - required - set(optional):
        raise PersonaError(f"{where}: unknown key(s) {sorted(extra)} (a persona file is closed)")


def parse_persona_file(data: bytes) -> PersonaFile:
    """Parse and check a persona file. Raises :class:`PersonaError`; the message never quotes the file's values."""
    try:
        doc = tomllib.loads(data.decode("utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError):
        raise PersonaError("a persona file is UTF-8 TOML") from None
    _closed(doc, "persona file", {"format", "id", "group"})
    if doc["format"] != PERSONA_FORMAT:
        raise PersonaError(f"a persona file has format {PERSONA_FORMAT}")
    if not isinstance(doc["id"], str) or _ID.fullmatch(doc["id"]) is None:
        raise PersonaError("persona file id is [a-z0-9][a-z0-9_.-]*")
    groups = doc["group"]
    if not isinstance(groups, list) or not groups:
        raise PersonaError("a persona file has at least one [[group]]")
    by_class: dict[str, set[str]] = {c: set() for c in GROUP_CLASSES}
    for i, group in enumerate(groups):
        where = f"group[{i}]"
        if not isinstance(group, dict):
            raise PersonaError(f"{where} is a table")
        klass = group.get("class", "upstream-data")
        if klass not in GROUP_CLASSES:
            raise PersonaError(f"{where}.class is one of {GROUP_CLASSES}")
        observed = klass in CORPUS_CLASSES
        _closed(group, where, {"source_id", "entries" if observed else "addresses"} | ({"corpus_id"} if observed else {"file"}),
                {"repo", "commit", "doi", "class"})
        if not isinstance(group["source_id"], str) or _ID.fullmatch(group["source_id"]) is None:
            raise PersonaError(f"{where}.source_id is a registry id")
        if observed:
            if not isinstance(group["corpus_id"], str) or _ID.fullmatch(group["corpus_id"]) is None:
                raise PersonaError(f"{where}.corpus_id is a corpus id")
        elif not isinstance(group["file"], str) or _FILE.fullmatch(group["file"]) is None:
            raise PersonaError(f"{where}.file names the evidence file")
        git = "repo" in group or "commit" in group
        if git == ("doi" in group):
            raise PersonaError(f"{where} pins the evidence by (repo, commit) or by doi, one of them")
        if git and (not isinstance(group.get("repo"), str) or _REPO.fullmatch(group["repo"]) is None
                    or not isinstance(group.get("commit"), str) or _HEX40.fullmatch(group["commit"]) is None):
            raise PersonaError(f"{where}: repo is an https URL and commit 40 lower-case hex")
        if not git and (not isinstance(group["doi"], str) or _DOI.fullmatch(group["doi"]) is None):
            raise PersonaError(f"{where}.doi is a DOI")
        if observed:
            digests = _entries(group["entries"], where, objects=klass == "withhold-object")
        else:
            digests = group["addresses"]
            if (not isinstance(digests, list) or not digests
                    or not all(isinstance(a, str) and _DIGEST.fullmatch(a) for a in digests)):
                raise PersonaError(f"{where}.addresses are 'sha256:<64 hex>' digests, at least one (never an address)")
            if digests != sorted(set(digests)):
                raise PersonaError(f"{where}.addresses are sorted and unique")
        by_class[klass].update(digests)
    seen: set[str] = set()
    for digests_of in by_class.values():
        if seen & digests_of:
            raise PersonaError("a digest is in groups of two classes")
        seen |= digests_of
    return PersonaFile(doc["id"], tuple(groups), {c: frozenset(v) for c, v in by_class.items()})


def _entries(value: Any, where: str, *, objects: bool = False) -> list[str]:
    """The digests of an observed group's ``entries`` after checking each entry's evidence (never quoting a value)."""
    if not isinstance(value, list) or not value:
        raise PersonaError(f"{where}.entries is a non-empty array of {{address, ex, record, pointer, actor_kind}} "
                           "(withhold-object: {address, object})")
    digests: list[str] = []
    for j, entry in enumerate(value):
        here = f"{where}.entries[{j}]"
        if not isinstance(entry, dict):
            raise PersonaError(f"{here} is a table")
        if objects:  # withhold-object: the raw object that holds the address
            _closed(entry, here, {"address", "object"})
            if not (isinstance(entry["address"], str) and _DIGEST.fullmatch(entry["address"]) is not None
                    and isinstance(entry["object"], str) and _DIGEST.fullmatch(entry["object"]) is not None):
                raise PersonaError(f"{here}: address and object are sha256 digests (the address, and the raw object that "
                                   "holds it)")
            digests.append(entry["address"])
            continue
        _closed(entry, here, {"address", "ex", "record", "pointer", "actor_kind"})
        ok = (isinstance(entry["address"], str) and _DIGEST.fullmatch(entry["address"]) is not None
              and isinstance(entry["ex"], str) and _EX.fullmatch(entry["ex"]) is not None
              and isinstance(entry["record"], str) and _RECORD.fullmatch(entry["record"]) is not None
              and isinstance(entry["pointer"], str) and len(entry["pointer"]) <= 300 and not _CONTROL.search(entry["pointer"])
              and "@" not in entry["pointer"]
              and (entry["pointer"] == "" or entry["pointer"].startswith("/"))
              and isinstance(entry["actor_kind"], str) and _KIND.fullmatch(entry["actor_kind"]) is not None)
        if not ok:
            raise PersonaError(f"{here}: address is a sha256 digest, ex an execution id, record an AER record id, pointer a JSON "
                               "pointer and actor_kind an actor kind (the evidence of the first appearance)")
        digests.append(entry["address"])
    if digests != sorted(set(digests)):
        raise PersonaError(f"{where}.entries are sorted by address, one per address")
    return digests


def persona_digests(files: Iterable[bytes]) -> dict[str, frozenset[str]]:
    """The digests of each class over several persona files' bytes; a digest in two classes is refused."""
    out: dict[str, set[str]] = {c: set() for c in GROUP_CLASSES}
    for data in files:
        for klass, digests in parse_persona_file(data).by_class.items():
            out[klass] |= digests
    seen: set[str] = set()
    for members in out.values():
        if seen & members:
            raise PersonaError("a digest has two classes in the persona files of one corpus")
        seen |= members
    return {c: frozenset(v) for c, v in out.items()}
