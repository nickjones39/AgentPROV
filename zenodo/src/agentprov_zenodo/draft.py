"""Zenodo draft-upload helper (HL H.10.1(2); D-5, D-790, D-870). Creates UNPUBLISHED drafts; the user presses Publish.

Usage::

    uv run python tools/zenodo_draft.py DEPOSIT_DIR --target sandbox|production --check
    uv run python tools/zenodo_draft.py DEPOSIT_DIR --target sandbox|production --create-draft [--root-digest sha256:HEX ...]
    uv run python tools/zenodo_draft.py DEPOSIT_DIR --target ... --create-draft --resume
    uv run python tools/zenodo_draft.py DEPOSIT_DIR --target ... --create-draft --new-version-of DEPOSITION_ID
    uv run python tools/zenodo_draft.py DEPOSIT_DIR --target ... --check|--create-draft --community SLUG [--community ...]
    uv run python tools/zenodo_draft.py --target ... --cross-link --umbrella RECEIPT --member RECEIPT [--member ...]

``DEPOSIT_DIR`` is a draft made by ``agentprov package --deposit`` (``agentprov.release.builder``). This script lives in
``tools/``, outside the installed package and outside ``agentprov.release``, because H.10.1(1) keeps every network library
and every upload call out of ``agentprov.release`` (a test asserts it). It uses the standard library only for the network
(``http.client``, ``ssl``) and reads the deposit through ``agentprov.release.verify`` and ``agentprov.ingest``.

What it does, in order:

1. **Offline checks, before any network access.** The directory is closed-world (the manifest's archives and documents,
   ``DEPOSIT-MANIFEST.json``, nothing else, regular files only); every file's size, sha256 and md5 equal the deposit
   manifest's; archive-mode ``verify`` (chain level, release mode) passes; the file count and sizes are within
   :data:`MAX_FILES` and :data:`MAX_TOTAL_BYTES`; ``deposit-metadata.json`` maps onto Zenodo's metadata.
2. **Consent.** ``--create-draft`` is required, standard input and output must be a terminal, and the user types a
   confirmation phrase after seeing the host, every file with its bytes and sha256, the title, version, licence and
   creators. There is no ``--yes``.
3. **A draft, never more.** ``POST /api/deposit/depositions``, ``PUT`` the metadata, ``PUT`` each file to the draft's
   bucket. Every request is checked against :data:`ALLOWED` (method plus path) **before** it is sent; a request outside it
   is refused. The allowlist holds no publish, edit, discard or delete request, so none can be made. A new AgentPROV
   version may use ``actions/newversion`` only on the concept DOI the deposit metadata records.
4. **Integrity.** After each upload the md5 Zenodo returns must equal the manifest's; after the last, the draft's file
   list is read back and compared with the manifest. A mismatch stops the run and is reported; nothing is deleted.
5. **A receipt** ``<deposit dir name>.zenodo-<target>-draft-receipt.json`` beside (never inside) the deposit directory.
   A second create is refused while it exists; ``--resume`` uploads only the missing files to the recorded draft.

**An index deposit (D-947).** ``DEPOSIT_DIR`` may also be the index-only umbrella of a collection, made by ``agentprov
package --index`` (``DEPOSIT-MANIFEST.json`` of format ``agentprov-index-manifest/0.1``, kind ``index``). It holds no
archive, so step 1 runs the closed-world and digest checks over its documents and
:func:`agentprov.release.index.check_index_deposit` in place of archive-mode ``verify``; ``--root-digest`` is refused
(the index lists the corpora's root digests; it holds no corpus), and so is an index built from another target's
receipts. The consent screen, the requests, the receipt, ``--community``, ``--resume`` and ``--cross-link`` (with the
index's receipt as ``--umbrella``) are unchanged.

**Communities and reserved DOIs (D-870).** ``--community SLUG`` (repeatable) sends ``communities: [{"identifier": SLUG}]``
in the draft's metadata; each community's curators accept or decline the request in Zenodo. Communities are a Zenodo
placement, not corpus metadata, so they come from the command line, not from the sealed ``deposit-metadata.json``. The
draft's reserved DOI (``metadata.prereserve_doi.doi``) is read from Zenodo's answers and recorded in the receipt
(:data:`RECEIPT_FORMAT` 0.2, with the metadata sent). ``prereserve_doi: true`` is sent with the metadata only while no
reserved DOI is known (the sandbox showed one on its drafts unasked); every later answer's DOI must equal the recorded
one, or the run stops. A resumed run reads the DOI back and never asks for another. A 0.1 receipt still blocks a second
create, but ``--resume`` and the cross-link step refuse it (it records no DOI).

**The cross-link step (D-870).** ``--cross-link --umbrella RECEIPT --member RECEIPT ...`` takes the receipts of a
collection's records (one per licence class or split) and, after the same typed confirmation, writes ``isPartOf`` the
umbrella's reserved DOI to every member and ``hasPart`` every member's to the umbrella. It ``PUT``s the metadata each
receipt recorded plus those links (deduplicated, so a re-run changes nothing) and reads them back. It reads every
deposition before it writes any, and refuses, with nothing written, a receipt that is not 0.2, records no reserved DOI,
is not ``complete`` or belongs to another target; a receipt given twice; a published deposition; a reserved DOI that
differs from the receipt's; and related identifiers changed outside this tool. It needs no request beyond :data:`ALLOWED`.

The token is read from the environment (``ZENODO_TOKEN`` for production, ``ZENODO_SANDBOX_TOKEN`` for the sandbox) or,
with ``--keychain``, from the OS keychain through the core's keychain helper (D-702, D-880), sent only in the
``Authorization`` header, held in :class:`Secret` (whose ``repr`` and ``str`` hide it), and removed from every
line this script prints. No traceback is printed. Redirects are never followed and proxies from the environment are never
used. Plain HTTP exists only for ``127.0.0.1`` through the ``test_base_url`` parameter of :func:`run`, which no
command-line option reaches.

Exit codes: 0 ok; 1 failed (an API error, an integrity mismatch, an incomplete draft); 2 usage or a missing precondition;
3 interpreter below the release floor; 4 refused; 5 unavailable (the server cannot be reached).
"""

from __future__ import annotations

import argparse
import hashlib
import html
import http.client
import json
import os
import re
import ssl
import stat
import sys
import urllib.parse
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final, TextIO

from agentprov.errors import AgentProvError
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.loaders import strict_json_loads
from agentprov.ingest.quote import escape_untrusted_line
from agentprov.release.builder import (
    DEPOSIT_MANIFEST,
    DEPOSIT_MANIFEST_FORMAT,
    DEPOSIT_METADATA,
    DepositRefusedError,
)
from agentprov.release.index import (
    COLLECTION_INDEX,
    INDEX_MANIFEST_FORMAT,
    check_index_deposit,
    index_members,
    is_index_manifest,
)
from agentprov.release.metadata import DEPOSIT_METADATA_FORMAT
from agentprov.release.verify import verify_deposit

EXIT_OK: Final = 0
EXIT_FAILED: Final = 1
EXIT_USAGE: Final = 2
EXIT_INTERPRETER: Final = 3
EXIT_REFUSED: Final = 4
EXIT_UNAVAILABLE: Final = 5

RECEIPT_FORMAT: Final = "agentprov-zenodo-draft-receipt/0.2"
#: The first receipt shape (D-790: no reserved DOI, no copy of the metadata). Read, never written: it still blocks a second
#: create, and ``--resume`` and ``--cross-link`` refuse it.
RECEIPT_FORMAT_0_1: Final = "agentprov-zenodo-draft-receipt/0.1"

#: The AgentDojo-PROV concept DOI (D-5): AgentPROV never deposits under it, as a new version or otherwise.
FORBIDDEN_CONCEPT_DOIS: Final = frozenset({"10.5281/zenodo.20692312"})
#: The record ids of those concepts on the production host, for the same refusal on the deposition itself.
FORBIDDEN_CONCEPT_RECIDS: Final = frozenset({"20692312"})

# --- Zenodo limits. Source: the REST API documentation (developers.zenodo.org, read 2026-10-23): "a limit of 50GB total in
# the record (and any given file), and up to 100 files in the record". UNCONFIRMED for the user: whether "GB" is 10**9 or
# 2**30 (the smaller is used), and whether the account's quota differs. Confirm in the sandbox trial.
MAX_FILES: Final = 100
MAX_TOTAL_BYTES: Final = 50 * 10**9
MAX_FILE_BYTES: Final = 50 * 10**9

#: The Zenodo licence id of each SPDX id this helper maps. Checked on 2026-10-23 against the sandbox's public licence
#: vocabulary (``GET /api/vocabularies/licenses``, 444 entries, whose ids are the lower-case SPDX ids; the legacy
#: ``/api/licenses/`` answers 301 to it). ``cc-zero`` of the REST documentation is **not** in that vocabulary, ``cc0-1.0``
#: is. ``GPL-3.0`` is SPDX's deprecated alias of ``GPL-3.0-only``. Not checked against production's vocabulary (same
#: software, separate deployment). Live trial of 2026-10-23: the deposit API accepted ``mit`` and read it back as
#: ``mit-license`` (Zenodo's own id); no other id has been sent to the deposit API yet. Any other class is refused rather
#: than guessed.
LICENCE_IDS: Final[Mapping[str, str]] = {
    "CC-BY-4.0": "cc-by-4.0", "CC-BY-SA-4.0": "cc-by-sa-4.0", "CC-BY-NC-4.0": "cc-by-nc-4.0",
    "CC-BY-NC-SA-4.0": "cc-by-nc-sa-4.0", "CC0-1.0": "cc0-1.0", "MIT": "mit", "Apache-2.0": "apache-2.0",
    "AGPL-3.0-only": "agpl-3.0-only", "GPL-3.0": "gpl-3.0-only", "GPL-3.0-only": "gpl-3.0-only",
    "GPL-3.0-or-later": "gpl-3.0-or-later",
}  # fmt: skip

#: The relation vocabulary of the Zenodo deposit metadata (the documentation's list, including its ``isOriginalFormof``).
ZENODO_RELATIONS: Final = frozenset({
    "isCitedBy", "cites", "isSupplementTo", "isSupplementedBy", "isContinuedBy", "continues", "isDescribedBy",
    "describes", "hasMetadata", "isMetadataFor", "isNewVersionOf", "isPreviousVersionOf", "isPartOf", "hasPart",
    "isReferencedBy", "references", "isDocumentedBy", "documents", "isCompiledBy", "compiles", "isVariantFormOf",
    "isOriginalFormof", "isIdenticalTo", "isAlternateIdentifier", "isReviewedBy", "reviews", "isDerivedFrom",
    "isSourceOf", "requires", "isRequiredBy", "isObsoletedBy", "obsoletes",
})  # fmt: skip

_FILE_NAME: Final = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,199}")
_SHA256: Final = re.compile(r"sha256:[0-9a-f]{64}")
_MD5: Final = re.compile(r"[0-9a-f]{32}")
_ROOT: Final = re.compile(r"sha256:[0-9a-f]{64}")
_DOI: Final = re.compile(r"10\.[0-9]{4,9}/[A-Za-z0-9._;()/:-]+")
#: A Zenodo community identifier (the community's URL slug).
_COMMUNITY: Final = re.compile(r"[a-z0-9][a-z0-9_-]{0,99}")
_CHUNK: Final = 1 << 20
_MAX_RESPONSE: Final = 4 << 20
_TIMEOUT: Final = 120.0
_API_LIMITS: Final = IngestLimits()

#: Every request this script may send: ``(method, fullmatch pattern of the path)``. Anything else is refused before a
#: socket is opened. There is deliberately no entry for publishing, editing, discarding or deleting.
ALLOWED: Final[tuple[tuple[str, re.Pattern[str]], ...]] = (
    ("POST", re.compile(r"/api/deposit/depositions")),
    ("GET", re.compile(r"/api/deposit/depositions/[0-9]{1,20}")),
    ("PUT", re.compile(r"/api/deposit/depositions/[0-9]{1,20}")),
    ("GET", re.compile(r"/api/deposit/depositions/[0-9]{1,20}/files")),
    ("POST", re.compile(r"/api/deposit/depositions/[0-9]{1,20}/actions/newversion")),
    ("PUT", re.compile(r"/api/files/[0-9a-fA-F-]{36}/[A-Za-z0-9][A-Za-z0-9._-]{0,199}")),
)
_BUCKET_PATH: Final = re.compile(r"/api/files/[0-9a-fA-F-]{36}")
_DEPOSITION_URL: Final = re.compile(r"/api/deposit/depositions/([0-9]{1,20})")


@dataclass(frozen=True)
class Target:
    name: str
    host: str
    token_variable: str


TARGETS: Final[Mapping[str, Target]] = {
    "sandbox": Target("sandbox", "sandbox.zenodo.org", "ZENODO_SANDBOX_TOKEN"),
    "production": Target("production", "zenodo.org", "ZENODO_TOKEN"),
}


# ================================================================================================ secrets and errors
class Secret:
    """The access token. ``repr`` and ``str`` never show it; only :meth:`header` and :meth:`redact` read it."""

    __slots__ = ("_value",)

    def __init__(self, value: str) -> None:
        self._value = value

    def __repr__(self) -> str:
        return "Secret(<redacted>)"

    __str__ = __repr__

    def header(self) -> str:
        return "Bearer " + self._value

    def redact(self, text: str) -> str:
        """``text`` with the token (and its URL-quoted form) replaced."""
        for form in {self._value, urllib.parse.quote(self._value, safe="")}:
            if form:
                text = text.replace(form, "<token redacted>")
        return text


class ToolError(Exception):
    """A refusal or failure with the exit code to return (the message is redacted again when printed)."""

    def __init__(self, message: str, exit_code: int = EXIT_FAILED) -> None:
        super().__init__(message)
        self.exit_code = exit_code


class Refusal(ToolError):
    def __init__(self, message: str, exit_code: int = EXIT_REFUSED) -> None:
        super().__init__(message, exit_code)


class ApiError(ToolError):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(f"Zenodo answered HTTP {status}: {message}", EXIT_FAILED)
        self.status = status


class Out:
    """The two output streams, with every line passed through the redactor first."""

    def __init__(self, stdout: TextIO, stderr: TextIO) -> None:
        self.stdout, self.stderr = stdout, stderr
        self.redact: Callable[[str], str] = lambda text: text

    def line(self, text: str = "") -> None:
        self.stdout.write(self.redact(text) + "\n")
        self.stdout.flush()

    def error(self, text: str) -> None:
        self.stderr.write(self.redact(text) + "\n")
        self.stderr.flush()


# ================================================================================================ the plan (offline)
@dataclass(frozen=True)
class PlannedFile:
    name: str
    bytes: int
    sha256: str  # "sha256:<hex>"
    md5: str  # hex

    def to_json(self) -> dict[str, Any]:
        return {"bytes": self.bytes, "md5": self.md5, "name": self.name, "sha256": self.sha256}


@dataclass(frozen=True)
class Plan:
    directory: Path
    files: tuple[PlannedFile, ...]
    metadata: dict[str, Any]  # the Zenodo ``metadata`` object
    not_sent: tuple[str, ...]  # related identifiers with no Zenodo relation (never silently dropped)
    concept_doi: str | None
    root_digests: tuple[str, ...] = field(default=())
    communities: tuple[str, ...] = field(default=())
    #: "deposit" (corpus archives, ``package --deposit``) or "index" (the collection index, ``package --index``; D-947)
    kind: str = "deposit"
    #: an index's part records and corpora (counts, for the consent screen)
    index_counts: tuple[int, int] = field(default=(0, 0))

    @property
    def total_bytes(self) -> int:
        return sum(f.bytes for f in self.files)


def _digests(path: Path) -> tuple[str, str, int]:
    sha, md5, size = hashlib.sha256(), hashlib.md5(usedforsecurity=False), 0
    with open(path, "rb") as handle:
        while chunk := handle.read(_CHUNK):
            sha.update(chunk)
            md5.update(chunk)
            size += len(chunk)
    return "sha256:" + sha.hexdigest(), md5.hexdigest(), size


def _load_json(path: Path) -> Any:
    try:
        return strict_json_loads(path.read_bytes(), _API_LIMITS)
    except (OSError, AgentProvError) as exc:
        raise Refusal(f"{path.name} cannot be read as strict JSON ({type(exc).__name__})") from None


def _listing(directory: Path) -> list[str]:
    """The names in ``directory``: regular files only, plain names (no link, no subdirectory)."""
    try:
        info = directory.lstat()
    except OSError:
        raise Refusal(f"{directory.name}: no such deposit directory", EXIT_USAGE) from None
    if not stat.S_ISDIR(info.st_mode):
        raise Refusal(f"{directory.name} is not a directory (a link is refused too)", EXIT_USAGE)
    names = []
    for entry in sorted(os.listdir(directory)):
        mode = (directory / entry).lstat().st_mode
        if not stat.S_ISREG(mode):
            raise Refusal(f"the deposit directory holds {escape_untrusted_line(entry)!r}, which is not a regular file")
        if _FILE_NAME.fullmatch(entry) is None:
            raise Refusal(f"the deposit directory holds a file with an unusable name {escape_untrusted_line(entry)!r}")
        names.append(entry)
    return names


def _expected_files(manifest: Any) -> dict[str, tuple[int, str, str]]:
    """``name -> (bytes, sha256, md5)`` from the deposit manifest's archives and documents (an index deposit's
    documents only: it has no archives, D-947)."""
    index = is_index_manifest(manifest)
    if not index and (not isinstance(manifest, dict) or manifest.get("format") != DEPOSIT_MANIFEST_FORMAT):
        raise Refusal(f"{DEPOSIT_MANIFEST} is not a {DEPOSIT_MANIFEST_FORMAT} (or {INDEX_MANIFEST_FORMAT}) document")
    if manifest.get("status") != "draft-unpublished":
        raise Refusal(f"{DEPOSIT_MANIFEST} status is not 'draft-unpublished'")
    out: dict[str, tuple[int, str, str]] = {}
    for key in (("documents",) if index else ("archives", "documents")):
        entries = manifest.get(key)
        if not isinstance(entries, list) or (key == "archives" and not entries):
            raise Refusal(f"{DEPOSIT_MANIFEST}: {key} is a list{' with at least one entry' if key == 'archives' else ''}")
        for entry in entries:
            ok = (isinstance(entry, dict) and isinstance(entry.get("name"), str) and isinstance(entry.get("bytes"), int)
                  and isinstance(entry.get("sha256"), str) and isinstance(entry.get("md5"), str))
            if not ok:
                raise Refusal(f"{DEPOSIT_MANIFEST}: a {key} entry is malformed")
            name = entry["name"]
            if _FILE_NAME.fullmatch(name) is None or name in out or name == DEPOSIT_MANIFEST:
                raise Refusal(f"{DEPOSIT_MANIFEST}: {key} names {escape_untrusted_line(name)!r} twice or unusably")
            if _SHA256.fullmatch(entry["sha256"]) is None or _MD5.fullmatch(entry["md5"]) is None:
                raise Refusal(f"{DEPOSIT_MANIFEST}: the digests of {escape_untrusted_line(name)!r} are malformed")
            out[name] = (entry["bytes"], entry["sha256"], entry["md5"])
    return out


def _check_limits(files: Sequence[PlannedFile]) -> None:
    if len(files) > MAX_FILES:
        raise Refusal(f"the deposit has {len(files)} files; Zenodo allows {MAX_FILES} per record (MAX_FILES, to be confirmed)")
    if any(f.bytes > MAX_FILE_BYTES for f in files):
        raise Refusal(f"a file exceeds {MAX_FILE_BYTES} bytes (MAX_FILE_BYTES, to be confirmed)")
    if sum(f.bytes for f in files) > MAX_TOTAL_BYTES:
        raise Refusal(f"the deposit exceeds {MAX_TOTAL_BYTES} bytes in total (MAX_TOTAL_BYTES, to be confirmed)")


def _text(value: Any, what: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise Refusal(f"{DEPOSIT_METADATA}: {what} is missing or not text")
    return value


def _html(text: str) -> str:
    paragraphs = [p for p in re.split(r"\n\s*\n", text.strip()) if p.strip()]
    return "".join("<p>" + html.escape(p.strip(), quote=False).replace("\n", "<br />") + "</p>" for p in paragraphs)


def _relation(datacite: str) -> str:
    mapped = datacite[:1].lower() + datacite[1:]
    return "isOriginalFormof" if mapped == "isOriginalFormOf" else mapped


def map_metadata(document: Any) -> tuple[dict[str, Any], tuple[str, ...], str | None]:
    """``(Zenodo metadata, related identifiers it cannot carry, the recorded concept DOI)`` from ``deposit-metadata.json``.

    Pure and offline. Refuses a document that is not an unpublished ``agentprov-deposit/0.1`` dataset, a deposit of more
    than one licence class (Zenodo holds one licence per record), a licence with no mapped Zenodo id and a
    ``version_doi`` (assigned at publication, never invented).
    """
    if not isinstance(document, dict) or document.get("format") != DEPOSIT_METADATA_FORMAT:
        raise Refusal(f"{DEPOSIT_METADATA} is not a {DEPOSIT_METADATA_FORMAT} document")
    if document.get("status") != "draft-unpublished" or document.get("version_doi") is not None:
        raise Refusal(f"{DEPOSIT_METADATA}: status is not 'draft-unpublished' or a version DOI is already set")
    if document.get("resource_type") != "dataset":
        raise Refusal(f"{DEPOSIT_METADATA}: resource_type is not 'dataset'")
    creators = []
    for entry in document.get("creators") or []:
        if not isinstance(entry, dict):
            raise Refusal(f"{DEPOSIT_METADATA}: a creator is not an object")
        creator = {"name": _text(entry.get("name"), "a creator name")}
        for key in ("affiliation", "orcid"):
            if isinstance(entry.get(key), str) and entry[key]:
                creator[key] = entry[key]
        creators.append(creator)
    if not creators:
        raise Refusal(f"{DEPOSIT_METADATA}: no creators")
    licences = document.get("licences")
    if not isinstance(licences, list) or len(licences) != 1 or not isinstance(licences[0], dict):
        raise Refusal("Zenodo holds one licence per record; this deposit has "
                      f"{len(licences) if isinstance(licences, list) else 'no'} licence classes (H.10.6)")
    spdx = licences[0].get("spdx")
    if not isinstance(spdx, str) or spdx not in LICENCE_IDS:
        raise Refusal(f"no Zenodo licence id is mapped for {escape_untrusted_line(str(spdx))}; add it to LICENCE_IDS after "
                      "checking GET /api/licenses/ (never guessed)")
    restrictions = [r for r in licences[0].get("restrictions") or [] if isinstance(r, str) and r]
    related, not_sent = [], []
    for entry in document.get("related_identifiers") or []:
        if not isinstance(entry, dict) or not isinstance(entry.get("identifier"), str):
            raise Refusal(f"{DEPOSIT_METADATA}: a related identifier is malformed")
        relation = _relation(str(entry.get("relation")))
        if relation in ZENODO_RELATIONS:
            related.append({"identifier": entry["identifier"], "relation": relation})
        else:
            not_sent.append(f"{entry.get('relation')} {entry['identifier']}")
    keywords = [k for k in document.get("keywords") or [] if isinstance(k, str) and k]
    metadata: dict[str, Any] = {
        "upload_type": "dataset",
        "title": _text(document.get("title"), "title"),
        "publication_date": _text(document.get("publication_date"), "publication_date"),
        "version": _text(document.get("version"), "version"),
        "description": _html(_text(document.get("description"), "description")),
        "creators": creators,
        "access_right": "open",
        "license": LICENCE_IDS[spdx],
        "keywords": keywords,
        "related_identifiers": related,
    }
    if restrictions:
        metadata["notes"] = _html("Use restrictions recorded in the corpus manifest: " + "; ".join(restrictions))
    concept = document.get("concept_doi")
    if concept is not None and (not isinstance(concept, str) or _DOI.fullmatch(concept) is None):
        raise Refusal(f"{DEPOSIT_METADATA}: concept_doi is not a DOI")
    return metadata, tuple(not_sent), concept


def build_plan(directory: Path, *, root_digests: Sequence[str] = (), release_verify: bool = True,
               communities: Sequence[str] = (), target: Target | None = None) -> Plan:
    """Every offline check of the module docstring. Raises :class:`Refusal` (or :class:`ToolError`); opens no socket.
    ``target`` is the run's target: an index deposit must have been built from that target's receipts (D-947)."""
    for digest in root_digests:
        if _ROOT.fullmatch(digest) is None:
            raise Refusal("--root-digest is sha256:<64 lower-case hex>", EXIT_USAGE)
    for slug in communities:
        if _COMMUNITY.fullmatch(slug) is None:
            raise Refusal(f"--community {escape_untrusted_line(slug)!r} is not a Zenodo community identifier (lower-case "
                          "letters, digits, '-' and '_')", EXIT_USAGE)
    if len(set(communities)) != len(communities):
        raise Refusal("a --community is given twice", EXIT_USAGE)
    names = _listing(directory)
    if DEPOSIT_MANIFEST not in names:
        raise Refusal(f"{directory.name} holds no {DEPOSIT_MANIFEST}: not a deposit draft", EXIT_USAGE)
    manifest = _load_json(directory / DEPOSIT_MANIFEST)
    index = is_index_manifest(manifest)
    if index and root_digests:
        raise Refusal("an index deposit holds no corpus: --root-digest belongs to corpus deposits (the index lists each "
                      f"corpus's root digest in {COLLECTION_INDEX})", EXIT_USAGE)
    expected = _expected_files(manifest)
    extra = sorted(set(names) - set(expected) - {DEPOSIT_MANIFEST})
    missing = sorted(set(expected) - set(names))
    if extra or missing:
        raise Refusal("the directory differs from the deposit manifest: "
                      f"{len(extra)} file(s) it does not list ({', '.join(map(escape_untrusted_line, extra[:5]))}), "
                      f"{len(missing)} listed file(s) absent ({', '.join(map(escape_untrusted_line, missing[:5]))})")
    files: list[PlannedFile] = []
    for name in sorted(expected):
        sha256, md5, size = _digests(directory / name)
        if (size, sha256, md5) != expected[name]:
            raise Refusal(f"{name}: its bytes, sha256 or md5 differ from {DEPOSIT_MANIFEST}")
        files.append(PlannedFile(name, size, sha256, md5))
    sha256, md5, size = _digests(directory / DEPOSIT_MANIFEST)
    files.append(PlannedFile(DEPOSIT_MANIFEST, size, sha256, md5))
    _check_limits(files)
    counts = (0, 0)
    if index:  # D-947: no archive to verify; the index's own consistency instead
        check = check_index_deposit(directory)
        if check.problems:
            raise Refusal(f"the index deposit does not pass its check ({len(check.problems)}): "
                          + "; ".join(escape_untrusted_line(p, max_chars=200) for p in check.problems[:5]))
        if target is not None and check.target != target.name:
            raise Refusal(f"the index was built from {check.target} receipts; it is uploaded to that target only")
        counts = (check.parts, check.corpora)
    else:
        try:
            result = verify_deposit(directory, level="chain", release=release_verify, root_digests=tuple(root_digests))
        except AgentProvError as exc:
            raise ToolError(f"archive-mode verify refused: {exc}", exc.exit_code if exc.exit_code in (2, 3, 4, 5) else EXIT_REFUSED) from None
        if not result.passed():
            codes = ", ".join(f"{code} x{n}" for code, n in result.codes().items()) or "failed"
            raise Refusal(f"archive-mode verify does not pass: {codes}")
    metadata_doc = _load_json(directory / DEPOSIT_METADATA)
    metadata, not_sent, concept = map_metadata(metadata_doc)
    if concept in FORBIDDEN_CONCEPT_DOIS:
        raise Refusal("the deposit metadata names the AgentDojo-PROV concept DOI: AgentPROV is never deposited under it (D-5)")
    if communities:
        metadata["communities"] = [{"identifier": slug} for slug in communities]
    return Plan(directory, tuple(files), metadata, not_sent, concept, tuple(root_digests), tuple(communities),
                "index" if index else "deposit", counts)


# ================================================================================================ the client
class Client:
    """A minimal HTTPS client for one host. Every request is checked against :data:`ALLOWED` before a socket opens."""

    def __init__(self, target: Target, secret: Secret, *, test_base_url: str | None = None,
                 timeout: float = _TIMEOUT) -> None:
        self.target, self._secret, self.timeout = target, secret, timeout
        if test_base_url is None:
            self.scheme, self.host, self.port = "https", target.host, 443
            self._context: ssl.SSLContext | None = ssl.create_default_context()  # verifies the chain and the host name
        else:
            parts = urllib.parse.urlsplit(test_base_url)
            if parts.scheme != "http" or parts.hostname != "127.0.0.1" or parts.port is None or parts.path not in ("", "/"):
                raise Refusal("the test base URL is http://127.0.0.1:PORT only")
            self.scheme, self.host, self.port = "http", "127.0.0.1", parts.port
            self._context = None

    @property
    def netloc(self) -> str:
        return self.host if self.scheme == "https" else f"{self.host}:{self.port}"

    @staticmethod
    def check_allowed(method: str, path: str) -> None:
        if any(m == method and pattern.fullmatch(path) for m, pattern in ALLOWED):
            return
        raise Refusal(f"refused before sending: {method} {escape_untrusted_line(path, max_chars=80)} is not an allowed request")

    def _connection(self) -> http.client.HTTPConnection:
        if self.scheme == "https":
            return http.client.HTTPSConnection(self.host, self.port, timeout=self.timeout, context=self._context,
                                               blocksize=_CHUNK)
        return http.client.HTTPConnection(self.host, self.port, timeout=self.timeout, blocksize=_CHUNK)

    def request(self, method: str, path: str, *, body: Any = None, upload: Path | None = None) -> Any:
        """One request; returns the parsed JSON object (``None`` for an empty body). ``body`` is a JSON document,
        ``upload`` a file streamed as ``application/octet-stream``."""
        self.check_allowed(method, path)
        headers = {"Authorization": self._secret.header(), "Accept": "application/json", "User-Agent": "agentprov-zenodo-draft"}
        data: Any = None
        if upload is not None:
            headers["Content-Type"] = "application/octet-stream"
            headers["Content-Length"] = str(upload.stat().st_size)
        elif body is not None:
            data = json.dumps(body, ensure_ascii=True).encode("ascii")
            headers["Content-Type"] = "application/json"
            headers["Content-Length"] = str(len(data))
        else:
            headers["Content-Length"] = "0"
        connection = self._connection()
        try:
            try:
                if upload is not None:
                    with open(upload, "rb") as handle:
                        connection.request(method, path, body=handle, headers=headers)
                        response = connection.getresponse()
                else:
                    connection.request(method, path, body=data, headers=headers)
                    response = connection.getresponse()
                payload = response.read(_MAX_RESPONSE + 1)
                status = response.status
            except (OSError, http.client.HTTPException) as exc:
                raise ToolError(f"cannot reach {self.netloc}: {type(exc).__name__}", EXIT_UNAVAILABLE) from None
        finally:
            connection.close()
        if len(payload) > _MAX_RESPONSE:
            raise ToolError("the response is larger than 4 MiB", EXIT_FAILED)
        if 300 <= status < 400:
            raise ToolError(f"Zenodo answered a redirect (HTTP {status}); redirects are never followed", EXIT_FAILED)
        parsed: Any = None
        if payload.strip():
            try:
                parsed = strict_json_loads(payload, _API_LIMITS)
            except AgentProvError:
                parsed = None
        if status >= 400:
            message = parsed.get("message") if isinstance(parsed, dict) else None
            # the token is removed before the message is cut, so a cut can never leave half of it
            raise ApiError(status, escape_untrusted_line(self._secret.redact(str(message or "no message")), max_chars=300))
        return parsed


# ================================================================================================ receipt
def receipt_path(directory: Path, target: Target) -> Path:
    """Beside the deposit directory, never inside it (the directory is checksummed)."""
    return directory.parent / f"{directory.name}.zenodo-{target.name}-draft-receipt.json"


class Receipt:
    def __init__(self, path: Path, data: dict[str, Any]) -> None:
        self.path, self.data = path, data

    @classmethod
    def read(cls, path: Path) -> Receipt | None:
        try:
            doc = strict_json_loads(path.read_bytes(), _API_LIMITS)
        except FileNotFoundError:
            return None
        except (OSError, AgentProvError):
            raise Refusal(f"{path.name} exists but cannot be read as strict JSON; check the web UI before removing it") from None
        if not isinstance(doc, dict) or doc.get("format") not in (RECEIPT_FORMAT, RECEIPT_FORMAT_0_1):
            raise Refusal(f"{path.name} is not a {RECEIPT_FORMAT} (or 0.1) receipt")
        return cls(path, doc)

    @classmethod
    def create(cls, path: Path, data: dict[str, Any]) -> Receipt:
        """Write the first receipt exclusively (a concurrent second run cannot also create one)."""
        try:
            handle = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            raise Refusal(f"{path.name} exists: a draft may already have been created") from None
        except OSError as exc:
            raise Refusal(f"cannot write the receipt {path.name} ({type(exc).__name__}); nothing was sent") from None
        with os.fdopen(handle, "wb") as out:
            out.write(_receipt_bytes(data))
        return cls(path, data)

    def save(self, now: datetime, **changes: Any) -> None:
        self.data.update(changes)
        self.data["updated"] = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        tmp = self.path.with_name("." + self.path.name + ".tmp")
        fd = os.open(tmp, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "wb") as out:
            out.write(_receipt_bytes(self.data))
        os.replace(tmp, self.path)


def _receipt_bytes(data: Mapping[str, Any]) -> bytes:
    return (json.dumps(data, sort_keys=True, indent=2, ensure_ascii=True) + "\n").encode("ascii")


# ================================================================================================ the run
@dataclass
class Context:
    out: Out
    client: Client
    plan: Plan
    target: Target
    receipt: Receipt
    now: Callable[[], datetime]


def _stamp(now: datetime) -> str:
    return now.strftime("%Y-%m-%dT%H:%M:%SZ")


def consent_text(plan: Plan, target: Target, *, resume_id: int | None, new_version_of: int | None) -> tuple[list[str], str]:
    """The screen the user confirms, and the phrase they must type."""
    meta = plan.metadata
    lines = [
        f"Target host: {target.host} ({target.name}; HTTPS, certificate verified)",
        f"Deposit directory: {plan.directory.name}",
        f"Title: {escape_untrusted_line(meta['title'])}",
        f"Version: {escape_untrusted_line(meta['version'])}",
        f"Licence: {meta['license']}",
        "Creators: " + "; ".join(escape_untrusted_line(c["name"]) for c in meta["creators"]),
        f"Files ({len(plan.files)}, {plan.total_bytes} bytes in total):",
    ]
    lines += [f"  {f.name}  {f.bytes} bytes  {f.sha256}" for f in plan.files]
    if plan.kind == "index":
        lines.append(f"Kind: collection index (no corpus data; {COLLECTION_INDEX} lists {plan.index_counts[0]} part "
                     f"record(s) and {plan.index_counts[1]} corpus version(s))")
    if plan.communities:
        lines.append("Communities (each one's curators accept or decline the request): " + ", ".join(plan.communities))
    if plan.not_sent:
        lines.append(f"Related identifiers NOT sent (no Zenodo relation): {len(plan.not_sent)}")
        lines += [f"  {escape_untrusted_line(item)}" for item in plan.not_sent]
    if new_version_of is not None:
        lines.append(f"A new version of deposition {new_version_of} (concept DOI {plan.concept_doi}).")
    if resume_id is not None:
        lines.append(f"Resumes draft {resume_id}: uploads only the files it lacks.")
    lines.append("This creates an unpublished draft; nothing is published.")
    phrase = (f"resume unpublished draft {resume_id} on {target.host}" if resume_id is not None
              else f"create unpublished draft on {target.host}")
    return lines, phrase


def _bucket(client: Client, deposition: Any) -> str:
    """The bucket path of a deposition, taken from the server's link only if it points at this host."""
    link = deposition.get("links", {}).get("bucket") if isinstance(deposition, dict) else None
    parts = urllib.parse.urlsplit(link if isinstance(link, str) else "")
    if (parts.scheme != client.scheme or parts.netloc != client.netloc or parts.query or parts.fragment
            or _BUCKET_PATH.fullmatch(parts.path) is None):
        raise ToolError("the draft's bucket link does not point at the target host; stopping", EXIT_FAILED)
    return parts.path


def _deposition_id(value: Any, what: str) -> int:
    if not isinstance(value, dict) or not isinstance(value.get("id"), int) or isinstance(value["id"], bool):
        raise ToolError(f"Zenodo's answer to {what} holds no deposition id", EXIT_FAILED)
    return int(value["id"])


def _html_url(client: Client, deposition: Any, deposition_id: int) -> str:
    link = deposition.get("links", {}).get("html") if isinstance(deposition, dict) else None
    parts = urllib.parse.urlsplit(link if isinstance(link, str) else "")
    if parts.scheme == client.scheme and parts.netloc == client.netloc and parts.path.startswith("/deposit/"):
        return urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
    return f"{client.scheme}://{client.netloc}/deposit/{deposition_id}"


def _draft_files(client: Client, deposition_id: int) -> dict[str, tuple[int, str]]:
    listing = client.request("GET", f"/api/deposit/depositions/{deposition_id}/files")
    if not isinstance(listing, list):
        raise ToolError("Zenodo's file list is not an array", EXIT_FAILED)
    out: dict[str, tuple[int, str]] = {}
    for entry in listing:
        if not isinstance(entry, dict) or not isinstance(entry.get("filename"), str):
            raise ToolError("Zenodo's file list holds a malformed entry", EXIT_FAILED)
        checksum = str(entry.get("checksum") or "").removeprefix("md5:")
        out[entry["filename"]] = (int(entry.get("filesize") or -1), checksum)
    return out


def _require_draft(deposition: Any) -> None:
    if not isinstance(deposition, dict) or deposition.get("submitted") is not False or deposition.get("state") == "done":
        raise Refusal("that deposition is already published (or its state is unknown); this tool only fills drafts")


def _reserved(answer: Any) -> tuple[str, int] | None:
    """The reserved DOI and record id a deposition answer holds (``metadata.prereserve_doi``), or ``None``."""
    meta = answer.get("metadata") if isinstance(answer, dict) else None
    entry = meta.get("prereserve_doi") if isinstance(meta, dict) else None
    if entry is None or entry is True or entry is False or entry == {}:  # a request echoed back, or an empty answer
        return None
    doi = entry.get("doi") if isinstance(entry, dict) else None
    recid = entry.get("recid") if isinstance(entry, dict) else None
    if (not isinstance(doi, str) or _DOI.fullmatch(doi) is None or not isinstance(recid, int)
            or isinstance(recid, bool)):
        raise ToolError("Zenodo's answer holds a malformed reserved DOI (metadata.prereserve_doi); stopping", EXIT_FAILED)
    return doi, recid


def _take_doi(ctx: Context, answer: Any) -> None:
    """Record the reserved DOI ``answer`` holds while the receipt has none; stop when it differs from the recorded one."""
    found = _reserved(answer)
    if found is None:
        return
    recorded = ctx.receipt.data.get("reserved_doi")
    if recorded is None:
        ctx.receipt.save(ctx.now(), reserved_doi=found[0], reserved_recid=found[1])
        ctx.out.line(f"Reserved DOI (registered only when you publish): {found[0]}")
    elif found[0] != recorded:
        ctx.receipt.save(ctx.now(), status="failed:reserved_doi_changed")
        raise ToolError(f"the draft's reserved DOI {found[0]} differs from the receipt's {recorded}; stopping, nothing "
                        "deleted. Check the draft in the web UI", EXIT_FAILED)


def _set_metadata(ctx: Context, deposition_id: int) -> None:
    """``PUT`` the metadata, asking for a reserved DOI only while none is known (never a second one), and record it."""
    body = dict(ctx.plan.metadata)
    if ctx.receipt.data.get("reserved_doi") is None:
        body["prereserve_doi"] = True
    answer = ctx.client.request("PUT", f"/api/deposit/depositions/{deposition_id}", body={"metadata": body})
    _take_doi(ctx, answer)
    ctx.receipt.save(ctx.now(), metadata_set=True)
    if ctx.receipt.data.get("reserved_doi") is None:
        ctx.receipt.save(ctx.now(), status="failed:no_reserved_doi")
        raise ToolError("Zenodo's answer holds no reserved DOI (metadata.prereserve_doi); stopping before the uploads, "
                        f"nothing deleted. Check the draft at {ctx.receipt.data['html_url']}, then --resume", EXIT_FAILED)


def _check_concept(plan: Plan, deposition: Any) -> None:
    """``newversion`` only on the concept DOI the release metadata records (D-5)."""
    if plan.concept_doi is None:
        raise Refusal("the deposit metadata records no concept_doi, so there is no AgentPROV concept to add a version to; "
                      "a first release is a new deposition (D-5)")
    recid = str(deposition.get("conceptrecid") or "") if isinstance(deposition, dict) else ""
    doi = str(deposition.get("conceptdoi") or "") if isinstance(deposition, dict) else ""
    if doi in FORBIDDEN_CONCEPT_DOIS or recid in FORBIDDEN_CONCEPT_RECIDS:
        raise Refusal("that deposition belongs to the AgentDojo-PROV concept; AgentPROV is never deposited under it (D-5)")
    if doi != plan.concept_doi:
        raise Refusal("that deposition's concept DOI is not the one the deposit metadata records; refusing to add a version")


def _upload(ctx: Context, bucket: str, present: Mapping[str, tuple[int, str]], *, overwrite: bool) -> None:
    """Upload every planned file the draft lacks; compare the md5 Zenodo returns with the manifest's after each."""
    total = len(ctx.plan.files)
    for index, planned in enumerate(ctx.plan.files, start=1):
        here = present.get(planned.name)
        if here is not None and here == (planned.bytes, planned.md5):
            _mark(ctx, planned.name)
            ctx.out.line(f"[{index}/{total}] {planned.name}: already in the draft with the same md5")
            continue
        if here is not None and not overwrite:
            ctx.receipt.save(ctx.now(), status="failed:checksum_mismatch")
            raise ToolError(f"{planned.name} is in the draft with other bytes or md5 than the manifest; stopping, nothing "
                            "deleted. Check the draft in the web UI", EXIT_FAILED)
        ctx.out.line(f"[{index}/{total}] uploading {planned.name} ({planned.bytes} bytes)")
        answer = ctx.client.request("PUT", f"{bucket}/{planned.name}", upload=ctx.plan.directory / planned.name)
        got = str((answer or {}).get("checksum") or "").removeprefix("md5:") if isinstance(answer, dict) else ""
        size = answer.get("size") if isinstance(answer, dict) else None
        if got != planned.md5 or size != planned.bytes:
            ctx.receipt.save(ctx.now(), status="failed:checksum_mismatch", mismatch=planned.name)
            raise ToolError(f"{planned.name}: Zenodo reports md5 {got or 'none'}, size {size}; the manifest says md5 "
                            f"{planned.md5}, size {planned.bytes}. Stopping; nothing was deleted", EXIT_FAILED)
        _mark(ctx, planned.name)


def _mark(ctx: Context, name: str) -> None:
    files = ctx.receipt.data["files"]
    for entry in files:
        if entry["name"] == name:
            entry["uploaded"] = True
    ctx.receipt.save(ctx.now(), files=files, status="uploading")


def _finish(ctx: Context, deposition_id: int, *, inherited_ok: bool) -> int:
    client, plan = ctx.client, ctx.plan
    deposition = client.request("GET", f"/api/deposit/depositions/{deposition_id}")
    _require_draft(deposition)
    _take_doi(ctx, deposition)
    have = _draft_files(client, deposition_id)
    want = {f.name: (f.bytes, f.md5) for f in plan.files}
    wrong = sorted(name for name, value in want.items() if have.get(name) != value)
    extra = sorted(set(have) - set(want))
    url = ctx.receipt.data["html_url"]
    if wrong or (extra and not inherited_ok):
        ctx.receipt.save(ctx.now(), status="failed:readback_mismatch")
        ctx.out.error(f"read-back mismatch: {len(wrong)} file(s) differ or are absent, {len(extra)} unexpected. "
                      f"Nothing was deleted. Check the draft at {url}")
        return EXIT_FAILED
    if extra:
        ctx.receipt.save(ctx.now(), status="inherited_files", inherited=extra)
        ctx.out.line(f"The draft holds {len(extra)} file(s) inherited from the previous version that are not part of this "
                     "deposit; this tool never deletes. Remove them in the web UI:")
        for name in extra:
            ctx.out.line(f"  {escape_untrusted_line(name)}")
        ctx.out.line(f"Draft created, NOT published. Review it at {url}, remove the inherited files, and press Publish yourself.")
        return EXIT_FAILED
    ctx.receipt.save(ctx.now(), status="complete")
    ctx.out.line(f"Draft created, NOT published. Review it at {url} and press Publish yourself.")
    return EXIT_OK


def _open_draft(ctx: Context, new_version_of: int | None) -> Any:
    """The new draft deposition: a fresh one, or the draft ``newversion`` makes on the recorded AgentPROV concept."""
    client, plan = ctx.client, ctx.plan
    if new_version_of is None:
        return client.request("POST", "/api/deposit/depositions", body={})
    previous = client.request("GET", f"/api/deposit/depositions/{new_version_of}")
    _check_concept(plan, previous)
    answer = client.request("POST", f"/api/deposit/depositions/{new_version_of}/actions/newversion")
    draft = answer.get("links", {}).get("latest_draft") if isinstance(answer, dict) else None
    parts = urllib.parse.urlsplit(draft if isinstance(draft, str) else "")
    match = _DEPOSITION_URL.fullmatch(parts.path)
    if parts.netloc != client.netloc or match is None:
        raise ToolError("Zenodo's new-version answer holds no draft link on the target host", EXIT_FAILED)
    return client.request("GET", f"/api/deposit/depositions/{int(match.group(1))}")


def create_draft(ctx: Context, *, new_version_of: int | None) -> int:
    client = ctx.client
    ctx.out.line(f"Connecting to {client.netloc}")
    try:
        deposition = _open_draft(ctx, new_version_of)
    except (ApiError, Refusal) as exc:
        # a clear rejection created nothing, so the pending receipt would only block a retry; an unclear failure (a lost
        # connection, an HTTP 5xx) keeps it, because a draft may exist
        if not isinstance(exc, ApiError) or exc.status < 500:
            ctx.receipt.path.unlink(missing_ok=True)
        raise
    deposition_id = _deposition_id(deposition, "create")
    _require_draft(deposition)
    bucket = _bucket(client, deposition)
    url = _html_url(client, deposition, deposition_id)
    ctx.receipt.save(ctx.now(), status="created", deposition_id=deposition_id, html_url=url)
    ctx.out.line(f"Draft {deposition_id} created (unpublished): {url}")
    _take_doi(ctx, deposition)
    _set_metadata(ctx, deposition_id)
    present = _draft_files(client, deposition_id)
    _upload(ctx, bucket, present, overwrite=new_version_of is not None)
    return _finish(ctx, deposition_id, inherited_ok=new_version_of is not None)


def resume_draft(ctx: Context) -> int:
    client, plan = ctx.client, ctx.plan
    data = ctx.receipt.data
    if data.get("format") != RECEIPT_FORMAT:
        raise Refusal(f"{ctx.receipt.path.name} is a {RECEIPT_FORMAT_0_1} receipt, which records no reserved DOI: finish "
                      "that draft in the web UI (or check it there and remove the receipt yourself)")
    deposition_id = data.get("deposition_id")
    if not isinstance(deposition_id, int):
        raise Refusal("the receipt records no deposition id (a create that never answered): check the web UI, then remove "
                      f"{ctx.receipt.path.name}")
    recorded = {f["name"]: (f["bytes"], f["sha256"], f["md5"]) for f in data.get("files", [])}
    if recorded != {f.name: (f.bytes, f.sha256, f.md5) for f in plan.files}:
        raise Refusal("the deposit directory no longer matches the receipt's file list; refusing to resume")
    if data.get("metadata") != plan.metadata:
        raise Refusal("the metadata this run would send differs from the receipt's; give the same --community options as "
                      "the create. Refusing to resume")
    deposition = client.request("GET", f"/api/deposit/depositions/{deposition_id}")
    _require_draft(deposition)
    _take_doi(ctx, deposition)  # read back, never reserved again
    bucket = _bucket(client, deposition)
    if not data.get("metadata_set") or data.get("reserved_doi") is None:
        _set_metadata(ctx, deposition_id)
    present = _draft_files(client, deposition_id)
    _upload(ctx, bucket, present, overwrite=data.get("kind") == "newversion")
    return _finish(ctx, deposition_id, inherited_ok=data.get("kind") == "newversion")


# ================================================================================================ cross-links (D-870)
@dataclass(frozen=True)
class Link:
    """One draft of a collection and the related identifiers the cross-link step adds to it."""

    role: str  # "umbrella" or "member"
    receipt: Receipt
    deposition_id: int
    doi: str
    adds: tuple[tuple[str, str], ...]  # (identifier, relation)

    @property
    def related(self) -> list[dict[str, str]]:
        """The receipt's recorded related identifiers with :attr:`adds` appended (each pair once)."""
        recorded = self.receipt.data["metadata"].get("related_identifiers") or []
        out = [dict(entry) for entry in recorded]
        seen = {(entry["identifier"], entry["relation"]) for entry in out}
        out += [{"identifier": i, "relation": r} for i, r in self.adds if (i, r) not in seen]
        return out


def _pairs(entries: Any, what: str) -> set[tuple[str, str]]:
    if not isinstance(entries, list) or not all(
            isinstance(e, dict) and isinstance(e.get("identifier"), str) and isinstance(e.get("relation"), str)
            for e in entries):
        raise ToolError(f"{what}: the related identifiers are malformed", EXIT_FAILED)
    return {(e["identifier"], e["relation"]) for e in entries}


def _check_index_membership(path: Path, umbrella: Receipt, members: Sequence[Receipt]) -> None:
    """D-949: when the umbrella is an index deposit (its receipt lists ``COLLECTION-INDEX.json``), the members must be
    exactly the part records the index lists, by reserved DOI and deposition, and the index read beside the receipt
    must be the file that was uploaded. A corpus-holding umbrella has no index and is not checked."""
    uploaded = {f.get("name"): f for f in umbrella.data.get("files") or [] if isinstance(f, dict)}
    if COLLECTION_INDEX not in uploaded:
        return
    directory = path.parent / str(umbrella.data.get("draft_dir"))
    try:
        raw, listed = index_members(directory)
    except DepositRefusedError as exc:
        raise Refusal(f"the umbrella is an index deposit, but its index beside the receipt cannot be read: {exc}") from None
    if "sha256:" + hashlib.sha256(raw).hexdigest() != uploaded[COLLECTION_INDEX].get("sha256"):
        raise Refusal(f"{COLLECTION_INDEX} beside the umbrella's receipt is not the file that was uploaded")
    want = set(listed)
    got = {(m.data["reserved_doi"], m.data["deposition_id"]) for m in members}
    if want != got:
        raise Refusal(f"the members are not the part records the umbrella's index lists: {len(want - got)} listed but not "
                      f"given, {len(got - want)} given but not listed")


def plan_links(target: Target, umbrella: Path, members: Sequence[Path]) -> list[Link]:
    """Offline: read and check every receipt; the umbrella first. Raises :class:`Refusal`; opens no socket."""
    paths = [umbrella, *members]
    if len({p.resolve() for p in paths}) != len(paths):
        raise Refusal("a receipt is given twice (the umbrella is not also a member)", EXIT_USAGE)
    receipts = []
    for path in paths:
        receipt = Receipt.read(path)
        if receipt is None:
            raise Refusal(f"{path.name}: no such receipt", EXIT_USAGE)
        data, name = receipt.data, path.name
        if data.get("format") != RECEIPT_FORMAT:
            raise Refusal(f"{name} is a {RECEIPT_FORMAT_0_1} receipt: it records no reserved DOI, so nothing can link to it")
        if data.get("target") != target.name or data.get("host") != target.host:
            raise Refusal(f"{name} belongs to another target")
        doi = data.get("reserved_doi")
        if not isinstance(doi, str) or _DOI.fullmatch(doi) is None:
            raise Refusal(f"{name} records no reserved DOI; every record of the collection needs one before linking")
        if not isinstance(data.get("deposition_id"), int) or isinstance(data["deposition_id"], bool):
            raise Refusal(f"{name} records no deposition id")
        if data.get("status") != "complete":
            raise Refusal(f"{name}: status {escape_untrusted_line(str(data.get('status')))}, not 'complete'; finish that "
                          "draft first (--resume)")
        if not isinstance(data.get("metadata"), dict):
            raise Refusal(f"{name} records no metadata")
        try:
            _pairs(data["metadata"].get("related_identifiers") or [], name)
        except ToolError:
            raise Refusal(f"{name}: the recorded related identifiers are malformed") from None
        receipts.append(receipt)
    ids = [r.data["deposition_id"] for r in receipts]
    dois = [r.data["reserved_doi"] for r in receipts]
    if len(set(ids)) != len(ids) or len(set(dois)) != len(dois):
        raise Refusal("two receipts name the same deposition or the same reserved DOI")
    _check_index_membership(umbrella, receipts[0], receipts[1:])
    links = [Link("umbrella", receipts[0], ids[0], dois[0], tuple((doi, "hasPart") for doi in dois[1:]))]
    links += [Link("member", r, i, d, ((dois[0], "isPartOf"),)) for r, i, d in zip(receipts[1:], ids[1:], dois[1:], strict=True)]
    return links


def cross_link_text(links: Sequence[Link], target: Target) -> tuple[list[str], str]:
    """The screen the user confirms before the cross-link step, and the phrase they must type."""
    lines = [f"Target host: {target.host} ({target.name}; HTTPS, certificate verified)",
             f"Cross-link {len(links)} unpublished drafts (drafts only; nothing is published):"]
    for link in links:
        title = escape_untrusted_line(str(link.receipt.data["metadata"].get("title")))
        lines.append(f"  {link.role:<8}  draft {link.deposition_id}  {link.doi}  {title}")
        lines += [f"    + {relation} {identifier}" for identifier, relation in link.adds]
    lines.append("Each draft's metadata is sent again as its receipt records it, with these links added: a change made in "
                 "the web UI to another metadata field of these drafts is replaced.")
    return lines, f"link {len(links)} unpublished drafts on {target.host}"


def cross_link(out: Out, client: Client, links: Sequence[Link], now: Callable[[], datetime]) -> int:
    """Read every draft, refuse before any write if one fails a check, then ``PUT`` and read back each one's links."""
    for link in links:
        deposition = client.request("GET", f"/api/deposit/depositions/{link.deposition_id}")
        if _deposition_id(deposition, "a read") != link.deposition_id:
            raise ToolError(f"Zenodo answered another deposition than {link.deposition_id}", EXIT_FAILED)
        _require_draft(deposition)
        reserved = _reserved(deposition)
        if reserved is None or reserved[0] != link.doi:
            raise Refusal(f"draft {link.deposition_id}: its reserved DOI is {reserved[0] if reserved else 'absent'}, the "
                          f"receipt records {link.doi}; nothing was written")
        foreign = _pairs(deposition["metadata"].get("related_identifiers") or [], f"draft {link.deposition_id}")
        foreign -= _pairs(link.related, link.receipt.path.name)
        if foreign:
            raise Refusal(f"draft {link.deposition_id} holds {len(foreign)} related identifier(s) this tool did not send "
                          "(changed in the web UI?); nothing was written. Check it, then create it again or link it by hand")
    for link in links:
        path = f"/api/deposit/depositions/{link.deposition_id}"
        client.request("PUT", path, body={"metadata": {**link.receipt.data["metadata"], "related_identifiers": link.related}})
        deposition = client.request("GET", path)
        reserved = _reserved(deposition)
        meta = deposition.get("metadata") if isinstance(deposition, dict) else None
        stored = _pairs((meta.get("related_identifiers") or []) if isinstance(meta, dict) else None,
                        f"draft {link.deposition_id}")
        if reserved is None or reserved[0] != link.doi or not set(link.adds) <= stored:
            link.receipt.save(now(), cross_links={"role": link.role, "adds": [list(a) for a in link.adds],
                                                  "status": "failed:readback_mismatch"})
            out.error(f"draft {link.deposition_id}: the links or the reserved DOI read back differ from what was sent. "
                      "Nothing was deleted. Check the draft in the web UI")
            return EXIT_FAILED
        link.receipt.save(now(), cross_links={"role": link.role, "adds": [list(a) for a in link.adds], "status": "linked"})
        out.line(f"Draft {link.deposition_id} ({link.role}, {link.doi}): {len(link.adds)} link(s) present")
    out.line("Drafts cross-linked, NOT published. Review each in the web UI and press Publish yourself.")
    return EXIT_OK


def _keychain_token(name: str) -> str:
    """The token ``name`` from the OS keychain (D-880), through the core's keychain helper process (D-702), into this process
    only: never a file, argv or the environment. Refuses when no allowed keychain holds it."""
    from agentprov import keys

    try:
        value = keys.read([name]).get(name, "")
    except keys.KeychainError as exc:
        raise Refusal(f"--keychain: the keychain gives no {name} ({exc.code}); store it with `agentprov keys set {name}` "
                      "or in the GUI's Settings > Keys", EXIT_USAGE) from None
    if not value:
        raise Refusal(f"--keychain: the keychain gives no {name}", EXIT_USAGE)
    return value


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create an UNPUBLISHED Zenodo draft from a deposit "
                                     "draft directory. The token is read from ZENODO_TOKEN (production) or "
                                     "ZENODO_SANDBOX_TOKEN (sandbox), or with --keychain from the OS keychain. Nothing "
                                     "is ever published by this tool.")
    parser.add_argument("deposit_dir", metavar="DEPOSIT_DIR", nargs="?",
                        help="the directory made by agentprov package --deposit, or the collection index made by "
                             "package --index (not with --cross-link)")
    parser.add_argument("--target", required=True, choices=sorted(TARGETS),
                        help="sandbox (sandbox.zenodo.org) or production (zenodo.org); there is no default")
    parser.add_argument("--create-draft", action="store_true",
                        help="explicitly allow creating an unpublished draft (needs a terminal and a typed confirmation)")
    parser.add_argument("--check", action="store_true", help="run the offline checks and show what would be sent; no token, "
                                                             "no network")
    parser.add_argument("--resume", action="store_true", help="upload only the missing files to the draft the receipt records")
    parser.add_argument("--new-version-of", type=int, metavar="DEPOSITION_ID",
                        help="a new version of the AgentPROV concept the deposit metadata records (the latest version's id)")
    parser.add_argument("--root-digest", action="append", default=[], metavar="sha256:HEX",
                        help="the corpus root digest published outside the deposit (release-mode verify needs one per corpus)")
    parser.add_argument("--community", action="append", default=[], metavar="SLUG",
                        help="ask a Zenodo community to include the draft (its identifier; repeatable; D-870)")
    parser.add_argument("--cross-link", action="store_true",
                        help="link the drafts of a collection by their reserved DOIs (drafts only; takes receipts, no "
                             "DEPOSIT_DIR; D-870)")
    parser.add_argument("--umbrella", metavar="RECEIPT", help="with --cross-link: the umbrella record's receipt (hasPart)")
    parser.add_argument("--keychain", action="store_true",
                        help="read the target's token from the OS keychain (agentprov keys set ZENODO_SANDBOX_TOKEN or "
                             "ZENODO_TOKEN; D-880) instead of the environment")
    parser.add_argument("--member", action="append", default=[], metavar="RECEIPT",
                        help="with --cross-link: a member record's receipt (isPartOf the umbrella); repeatable")
    return parser


def _isatty(stream: TextIO) -> bool:
    try:
        return stream.isatty()
    except (AttributeError, ValueError):
        return False


def run(
    argv: Sequence[str],
    *,
    environ: Mapping[str, str] | None = None,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
    input_fn: Callable[[str], str] | None = None,
    now: Callable[[], datetime] | None = None,
    test_base_url: str | None = None,
    release_verify: bool = True,
    interactive: Callable[[], bool] | None = None,
) -> int:
    """The tool. ``test_base_url``, ``release_verify`` and ``interactive`` exist for the test suite only: no command-line
    option reaches them, so a real run always talks to the allowlisted HTTPS host, verifies in release mode and needs a
    terminal."""
    out = Out(stdout or sys.stdout, stderr or sys.stderr)
    environ = os.environ if environ is None else environ
    clock = now or (lambda: datetime.now(UTC))
    secret: Secret | None = None
    try:
        try:
            args = _parser().parse_args(list(argv))
        except SystemExit as exc:
            return int(exc.code) if isinstance(exc.code, int) else EXIT_USAGE
        target = TARGETS[args.target]
        if args.cross_link:
            if (args.check or args.create_draft or args.resume or args.new_version_of is not None or args.root_digest
                    or args.community or args.deposit_dir is not None):
                raise Refusal("--cross-link takes only --target, --umbrella, --member and --keychain (receipts, no "
                              "DEPOSIT_DIR)", EXIT_USAGE)
            if args.umbrella is None or not args.member:
                raise Refusal("--cross-link needs --umbrella RECEIPT and at least one --member RECEIPT", EXIT_USAGE)
        elif args.umbrella is not None or args.member:
            raise Refusal("--umbrella and --member belong to --cross-link", EXIT_USAGE)
        elif args.check == args.create_draft:
            raise Refusal("give exactly one of --check (offline, nothing sent) or --create-draft (creates an unpublished "
                          "draft after a typed confirmation)", EXIT_USAGE)
        elif args.deposit_dir is None:
            raise Refusal("DEPOSIT_DIR is required", EXIT_USAGE)
        if args.resume and args.new_version_of is not None:
            raise Refusal("--resume and --new-version-of are different runs", EXIT_USAGE)
        if args.check and (args.resume or args.new_version_of is not None or args.keychain):
            raise Refusal("--check takes neither --resume, --new-version-of nor --keychain (it needs no token)", EXIT_USAGE)
        if args.create_draft or args.cross_link:
            tty = interactive() if interactive is not None else _isatty(stdin or sys.stdin) and _isatty(out.stdout)
            if not tty:
                raise Refusal("no terminal: the confirmation is interactive and has no --yes; run this in your own terminal",
                              EXIT_REFUSED)
            if args.keychain:
                token = _keychain_token(target.token_variable)
            else:
                token = environ.get(target.token_variable, "")
                if not token:
                    raise Refusal(f"{target.token_variable} is not set in the environment (the {target.name} token; it is "
                                  "never asked for or printed; --keychain reads it from the OS keychain)", EXIT_USAGE)
            if not token.isprintable() or any(c.isspace() for c in token):
                raise Refusal(f"{target.token_variable} does not look like a token (printable, no spaces)", EXIT_USAGE)
            secret = Secret(token)
            out.redact = secret.redact
        if args.cross_link:
            assert secret is not None
            links = plan_links(target, Path(str(args.umbrella)), [Path(m) for m in args.member])
            lines, phrase = cross_link_text(links, target)
            for line in lines:
                out.line(line)
            out.line(f"Type exactly  {phrase}  to continue, anything else cancels:")
            if (input_fn or input)("> ").strip() != phrase:
                raise Refusal("not confirmed; nothing was sent", EXIT_REFUSED)
            return cross_link(out, Client(target, secret, test_base_url=test_base_url), links, clock)
        directory = Path(str(args.deposit_dir))  # present: checked above
        plan = build_plan(directory, root_digests=args.root_digest, release_verify=release_verify,
                          communities=args.community, target=target)
        resume_id: int | None = None
        path = receipt_path(directory, target)
        existing = Receipt.read(path)
        if args.resume:
            if existing is None:
                raise Refusal(f"--resume needs a receipt ({path.name}) beside the deposit directory", EXIT_USAGE)
            if existing.data.get("target") != target.name:
                raise Refusal("the receipt belongs to another target")
            resume_id = existing.data.get("deposition_id") if isinstance(existing.data.get("deposition_id"), int) else None
        elif existing is not None and args.create_draft:
            raise Refusal(f"a receipt exists ({path.name}, status {escape_untrusted_line(str(existing.data.get('status')))}): "
                          "a draft was already created or attempted. Use --resume to finish it, or check the web UI and "
                          "remove the receipt yourself. No second deposition is created")
        lines, phrase = consent_text(plan, target, resume_id=resume_id, new_version_of=args.new_version_of)
        for line in lines:
            out.line(line)
        if args.check:
            out.line("Offline checks passed (--check): nothing was sent.")
            return EXIT_OK
        assert secret is not None
        out.line(f"Type exactly  {phrase}  to continue, anything else cancels:")
        answer = (input_fn or input)("> ")
        if answer.strip() != phrase:
            raise Refusal("not confirmed; nothing was sent", EXIT_REFUSED)
        client = Client(target, secret, test_base_url=test_base_url)
        if args.resume:
            assert existing is not None
            ctx = Context(out, client, plan, target, existing, clock)
            return resume_draft(ctx)
        receipt = Receipt.create(path, {
            "format": RECEIPT_FORMAT, "target": target.name, "host": target.host, "draft_dir": directory.name,
            "kind": "newversion" if args.new_version_of is not None else "new", "new_version_of": args.new_version_of,
            "concept_doi": plan.concept_doi, "deposition_id": None, "html_url": None, "metadata_set": False,
            "files": [{**f.to_json(), "uploaded": False} for f in plan.files], "created": _stamp(clock()),
            "updated": _stamp(clock()), "status": "pending",
            "reserved_doi": None, "reserved_recid": None, "communities": list(plan.communities),
            "metadata": plan.metadata, "cross_links": None,
        })
        return create_draft(Context(out, client, plan, target, receipt, clock), new_version_of=args.new_version_of)
    except ToolError as exc:
        out.error(f"zenodo_draft: {exc}")
        return exc.exit_code
    except Exception as exc:  # never a traceback: it could carry the request headers or the token's neighbours
        out.error(f"zenodo_draft: unexpected {type(exc).__name__}: {exc}")
        return EXIT_FAILED


def main() -> int:
    return run(sys.argv[1:])


if __name__ == "__main__":
    sys.exit(main())
