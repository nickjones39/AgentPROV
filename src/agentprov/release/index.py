"""The index-only umbrella deposit: ``agentprov package --index`` (HL H.10.7; D-941 L-5, D-947).

A release of several Zenodo records (one per licence class and harness family, D-941 L-1) is gathered by an umbrella
record. :func:`build_index` builds that umbrella as a deposit draft that holds **no corpus data**: the collection
``README.md``, ``COLLECTION-INDEX.json`` (``agentprov-collection-index/0.1``), one ``DATASHEET-<corpus_id>.md`` byte copy
per corpus whose licence class is not copyleft, ``deposit-metadata.json`` (``agentprov-deposit/0.1``, licence CC-BY-4.0) and ``DEPOSIT-MANIFEST.json`` of
format ``agentprov-index-manifest/0.1`` and kind ``index`` (the closed-world list of the documents with their sizes,
sha256 and md5). There are no archives. Like :mod:`agentprov.release.builder` it is offline: no network module, no
process (H.10.1(1)); nothing is uploaded or published.

**Inputs** (each refusal happens before anything is written):

* one draft receipt per part record (``--part``), as the draft-only uploader writes it beside the part's deposit
  directory (``<DIR>.zenodo-<target>-draft-receipt.json``, ``agentprov-zenodo-draft-receipt/0.2``, D-870). It must be
  ``complete``, record a reserved DOI and record id, and name its directory (``draft_dir``) by the receipt's own file
  name. All receipts belong to one target; no DOI, record, deposition or directory appears twice;
* the part's deposit directory, **beside the receipt** (``<receipt dir>/<draft_dir>``): only its ``DEPOSIT-MANIFEST.json``
  is read. Its size, sha256 and md5 must equal the receipt's entry for it, and the receipt's file list must equal the
  manifest's archives and documents (names, sizes, sha256, md5), so the manifest read is the one that was uploaded. It
  is a corpus deposit (``agentprov-deposit-manifest/0.1``) of one licence class, not mixed;
* every sealed corpus the parts hold (``--corpus``), and no other: each corpus appears in exactly one part. Its root
  digest is recomputed (sha256 of its ``checksums.sha256``), and ``corpus.json`` and ``DATASHEET.md`` must match their
  ``checksums.sha256`` entries, so every value read is anchored by that root digest. The corpus id, version, content
  digest, root digest and licence class must equal the part manifest's entry, and the datasheet the part's copy;
* ``release.toml`` (H.10.2) for the title, creators, keywords, preamble, version, concept DOI and related identifiers.
  Each part's reserved DOI is added as ``HasPart`` (the same pair the uploader's ``--cross-link`` writes, so linking
  again changes nothing).

**Copyleft corpora (D-949).** The index record is CC-BY-4.0, so it holds no datasheet of a corpus whose licence class
has a copyleft term (GPL, AGPL, LGPL): that corpus's row names the datasheet in its part record (``location: part``)
with its size, sha256 and md5, and the README links to the part record. Every other datasheet is copied
(``location: index``).

The full archive and chain verification of each corpus is the part deposit's (H.10.1(3)); the index does not repeat
it. A reserved DOI is registered only when its record is published; the index says so.

:func:`check_index_deposit` is the offline consistency check the uploader runs on an index deposit in place of
archive-mode ``verify``: closed world, every document's size, sha256 and md5, the index's shape, its datasheets and
its licence. Two builds from the same inputs are byte-identical (Q.20).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Final

from agentprov.corpus.integrity import parse_checksums
from agentprov.corpus.licences import is_copyleft
from agentprov.corpus.layout import DATASHEET, MANIFEST, PARTIAL_SUFFIX, assert_writable
from agentprov.corpus.manifest import validate_manifest
from agentprov.corpus.reader import CorpusReader
from agentprov.envinfo import refuse_advisory_manifest, require_patched_for_archive
from agentprov.errors import AgentProvError, IngestError
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.loaders import strict_json_loads
from agentprov.ingest.paths import open_evidence
from agentprov.io.atomic import atomic_swap_dir
from agentprov.release.builder import (
    DEPOSIT_MANIFEST,
    DEPOSIT_MANIFEST_FORMAT,
    DEPOSIT_METADATA,
    DepositError,
    DepositProducer,
    DepositRefusedError,
    Lint,
)
from agentprov.release.metadata import (
    DEPOSIT_METADATA_FORMAT,
    DepositMetadataError,
    LicenceClass,
    Related,
    ReleaseMetadata,
    class_text,
    licence_class,
    merge_related,
)

__all__ = [
    "COLLECTION_INDEX",
    "COLLECTION_INDEX_FORMAT",
    "INDEX_KIND",
    "INDEX_LICENCE",
    "INDEX_MANIFEST_FORMAT",
    "RECEIPT_FORMAT",
    "IndexCheck",
    "IndexReport",
    "build_index",
    "check_index_deposit",
    "datasheet_copied",
    "index_members",
    "is_index_manifest",
]

INDEX_MANIFEST_FORMAT: Final = "agentprov-index-manifest/0.1"
INDEX_KIND: Final = "index"
COLLECTION_INDEX: Final = "COLLECTION-INDEX.json"
COLLECTION_INDEX_FORMAT: Final = "agentprov-collection-index/0.1"
#: The index record's own licence (D-941: the umbrella is CC-BY-4.0); each corpus keeps its own, in its part record.
INDEX_LICENCE: Final = LicenceClass("CC-BY-4.0", ())
#: The uploader's receipt (D-870), read here as data: ``agentprov`` never imports the uploader (D-880).
RECEIPT_FORMAT: Final = "agentprov-zenodo-draft-receipt/0.2"
RECEIPT_FORMAT_0_1: Final = "agentprov-zenodo-draft-receipt/0.1"
#: target name -> host, as the uploader's ``TARGETS`` (a test pins the two equal)
RECEIPT_TARGETS: Final[Mapping[str, str]] = {"sandbox": "sandbox.zenodo.org", "production": "zenodo.org"}
_RECEIPT_SUFFIX: Final = "-draft-receipt.json"
_NAME: Final = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,199}")
_DOI: Final = re.compile(r"10\.[0-9]{4,9}/[A-Za-z0-9._;()/:-]+")
_SHA256: Final = re.compile(r"sha256:[0-9a-f]{64}")
_MD5: Final = re.compile(r"[0-9a-f]{32}")
_CHUNK: Final = 1 << 20
_NOT_PUBLISHED: Final = "Nothing has been uploaded or published."
_FIXED_DOCUMENTS: Final = ("README.md", COLLECTION_INDEX, DEPOSIT_METADATA)


def _refuse(message: str, code: str, exit_code: int = 4) -> DepositRefusedError:
    return DepositRefusedError(message, code=f"release.refused.index_{code}", exit_code=exit_code)


def _usage(message: str) -> DepositRefusedError:
    return DepositRefusedError(message, code="release.usage", exit_code=2)


def is_index_manifest(document: object) -> bool:
    """Whether a parsed ``DEPOSIT-MANIFEST.json`` is an index deposit's (format and kind)."""
    return (isinstance(document, Mapping) and document.get("format") == INDEX_MANIFEST_FORMAT
            and document.get("kind") == INDEX_KIND)


def _document_bytes(document: Mapping[str, Any]) -> bytes:
    """A deposit JSON document: sorted keys, two-space indentation, UTF-8, final LF (H.1.4(2); as the builder's)."""
    return (json.dumps(document, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def _digests(data: bytes) -> dict[str, Any]:
    return {"bytes": len(data), "md5": hashlib.md5(data, usedforsecurity=False).hexdigest(),
            "sha256": "sha256:" + hashlib.sha256(data).hexdigest()}


def _read_json(directory: Path, name: str, limits: IngestLimits, what: str) -> tuple[bytes, Any]:
    try:
        with open_evidence(directory, name, limits, allow_hardlinks=True) as stream:
            data = stream.read(limits.max_json_bytes + 1)
    except FileNotFoundError:
        raise _refuse(f"{what}: no such file", "missing") from None
    except (IngestError, OSError) as exc:
        code = exc.code if isinstance(exc, IngestError) else type(exc).__name__
        raise _refuse(f"{what} cannot be read ({code})", "unreadable") from None
    if len(data) > limits.max_json_bytes:
        raise _refuse(f"{what} is larger than the JSON limit", "unreadable")
    try:
        return data, strict_json_loads(data, limits)
    except IngestError as exc:
        raise _refuse(f"{what} is not strict JSON ({exc.code})", "unreadable") from None


# ================================================================================================ the parts
@dataclass
class _Part:
    receipt: Path
    record: str  # the part's deposit directory name (the receipt's draft_dir)
    target: str
    host: str
    reserved_doi: str
    record_id: int
    deposition_id: int
    title: str
    communities: list[str]
    manifest_sha256: str
    cls: LicenceClass
    corpora: list[Mapping[str, Any]]  # the part manifest's corpus entries
    datasheets: dict[str, str]  # DATASHEET-<id>.md -> sha256 in the part

    def entry(self, corpora: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        return {"communities": list(self.communities), "corpora": list(corpora),
                "deposit_manifest_sha256": self.manifest_sha256, "deposition_id": self.deposition_id,
                "licence_class": self.cls.to_json(), "record": self.record, "record_id": self.record_id,
                "reserved_doi": self.reserved_doi, "title": self.title}  # fmt: skip


def _file_rows(entries: object, what: str) -> dict[str, tuple[int, str, str]]:
    if not isinstance(entries, list):
        raise _refuse(f"{what} is not a list", "part")
    out: dict[str, tuple[int, str, str]] = {}
    for entry in entries:
        ok = (isinstance(entry, Mapping) and isinstance(entry.get("name"), str) and isinstance(entry.get("bytes"), int)
              and not isinstance(entry.get("bytes"), bool) and isinstance(entry.get("sha256"), str)
              and isinstance(entry.get("md5"), str))
        if not ok or _NAME.fullmatch(entry["name"]) is None or entry["name"] in out:
            raise _refuse(f"{what} holds a malformed or repeated file entry", "part")
        out[entry["name"]] = (entry["bytes"], entry["sha256"], entry["md5"])
    return out


def _open_part(path: Path, limits: IngestLimits) -> _Part:
    shown = path.name
    _, data = _read_json(path.parent, path.name, limits, f"the receipt {shown}")
    if not isinstance(data, Mapping):
        raise _refuse(f"{shown} is not a receipt", "receipt")
    if data.get("format") == RECEIPT_FORMAT_0_1:
        raise _refuse(f"{shown} is a {RECEIPT_FORMAT_0_1} receipt, which records no reserved DOI", "receipt")
    if data.get("format") != RECEIPT_FORMAT:
        raise _refuse(f"{shown} is not an {RECEIPT_FORMAT} receipt", "receipt")
    target, host = data.get("target"), data.get("host")
    if not isinstance(target, str) or RECEIPT_TARGETS.get(target) != host:
        raise _refuse(f"{shown} names no known target and host", "receipt")
    if data.get("status") != "complete":
        raise _refuse(f"{shown}: the draft is not complete; finish it with the uploader's --resume first", "incomplete")
    doi, recid, deposition = data.get("reserved_doi"), data.get("reserved_recid"), data.get("deposition_id")
    if not isinstance(doi, str) or _DOI.fullmatch(doi) is None:
        raise _refuse(f"{shown} records no reserved DOI", "receipt")
    for value, name in ((recid, "reserved_recid"), (deposition, "deposition_id")):
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise _refuse(f"{shown} records no {name}", "receipt")
    assert isinstance(recid, int) and isinstance(deposition, int)
    record = data.get("draft_dir")
    if not isinstance(record, str) or _NAME.fullmatch(record) is None:
        raise _refuse(f"{shown} names no usable deposit directory (draft_dir)", "receipt")
    if path.name != f"{record}.zenodo-{target}{_RECEIPT_SUFFIX}":
        raise _refuse(f"{shown} is not the receipt name of its own deposit directory {record} on {target}", "receipt")
    metadata = data.get("metadata")
    title = metadata.get("title") if isinstance(metadata, Mapping) else None
    if not isinstance(title, str) or not title.strip():
        raise _refuse(f"{shown} records no metadata title", "receipt")
    communities = [c for c in (data.get("communities") or []) if isinstance(c, str)]
    receipt_files = _file_rows(data.get("files"), f"{shown}: files")

    directory = path.parent / record
    try:
        info = directory.lstat()
    except OSError:
        raise _refuse(f"{shown}: its deposit directory {record} is not beside it", "part_missing") from None
    if not stat.S_ISDIR(info.st_mode):
        raise _refuse(f"{shown}: {record} beside it is not a directory (a link is refused too)", "part_missing")
    raw, manifest = _read_json(directory, DEPOSIT_MANIFEST, limits, f"{record}/{DEPOSIT_MANIFEST}")
    digests = _digests(raw)
    if receipt_files.get(DEPOSIT_MANIFEST) != (digests["bytes"], digests["sha256"], digests["md5"]):
        raise _refuse(f"{record}/{DEPOSIT_MANIFEST} is not the manifest the receipt {shown} uploaded", "part_changed")
    if not isinstance(manifest, Mapping) or manifest.get("format") != DEPOSIT_MANIFEST_FORMAT:
        raise _refuse(f"{record} is not a corpus deposit ({DEPOSIT_MANIFEST_FORMAT}); an index holds corpus deposits "
                      "only", "part")
    listed = {**_file_rows(manifest.get("archives"), f"{record}: archives"),
              **_file_rows(manifest.get("documents"), f"{record}: documents")}
    listed[DEPOSIT_MANIFEST] = (digests["bytes"], digests["sha256"], digests["md5"])
    if listed != receipt_files:
        raise _refuse(f"{shown}: the uploaded files differ from {record}/{DEPOSIT_MANIFEST}", "part_changed")
    if manifest.get("mixed_licence_classes") is not False:
        raise _refuse(f"{record} mixes licence classes; a Zenodo record holds one", "part")
    classes = manifest.get("licence_classes")
    if not isinstance(classes, list) or len(classes) != 1 or not isinstance(classes[0], Mapping):
        raise _refuse(f"{record} does not record exactly one licence class", "part")
    cls = _class(classes[0], record)
    corpora = manifest.get("corpora")
    if not isinstance(corpora, list) or not corpora or not all(isinstance(c, Mapping) for c in corpora):
        raise _refuse(f"{record} lists no corpus", "part")
    datasheets = {name: row[1] for name, row in listed.items() if name.startswith("DATASHEET-")}
    return _Part(path, record, target, str(host), doi, recid, deposition, title, sorted(communities),
                 str(digests["sha256"]), cls, list(corpora), datasheets)


def _class(value: Mapping[str, Any], where: str) -> LicenceClass:
    spdx, restrictions = value.get("spdx"), value.get("restrictions")
    if not isinstance(spdx, str) or not isinstance(restrictions, list) or not all(isinstance(r, str) for r in restrictions):
        raise _refuse(f"{where}: a licence class is malformed", "part")
    return LicenceClass(spdx, tuple(restrictions))


# ================================================================================================ the corpora
@dataclass
class _Corpus:
    root: Path
    corpus_id: str
    version: str
    title: str
    content_digest: str
    root_digest: str
    cls: LicenceClass
    datasheet: bytes


def _open_corpus(path: Path, limits: IngestLimits) -> _Corpus:
    try:
        reader = CorpusReader.open(path, limits=limits)
    except AgentProvError as exc:
        raise _refuse(f"{path.name}: not a readable sealed corpus ({exc.code})", "unsealed") from None
    if not reader.sealed or reader.used_partial:
        raise _refuse(f"{path.name}: only sealed corpora are indexed", "unsealed")
    manifest = reader.manifest()
    assert manifest is not None
    corpus_id, version = str(manifest.get("corpus_id")), str(manifest.get("corpus_version"))
    if (manifest.get("release") or {}).get("status") != "sealed":
        raise _refuse(f"{corpus_id}: release.status is not sealed", "unsealed")
    refuse_advisory_manifest(manifest)  # AD-16: exit 4
    issues = validate_manifest(manifest)
    if issues:
        raise DepositError(f"{corpus_id}: the manifest does not validate ({len(issues)} issue(s))",
                           code="release.failed.manifest")
    checksums = reader.checksums_bytes()
    if checksums is None:
        raise DepositError(f"{corpus_id}: the sealed corpus has no checksums.sha256", code="release.failed.verify")
    entries, findings = parse_checksums(checksums)
    if findings:
        raise DepositError(f"{corpus_id}: checksums.sha256 is malformed", code="release.failed.verify")
    listed = {e.path: e.sha256 for e in entries}
    datasheet = reader.read_bytes(DATASHEET)
    for label, data in ((MANIFEST, reader.read_bytes(MANIFEST)), (DATASHEET, datasheet)):
        if listed.get(label) != hashlib.sha256(data).hexdigest():
            raise DepositError(f"{corpus_id}: {label} does not match checksums.sha256", code="release.failed.verify")
    return _Corpus(path, corpus_id, version, str(manifest.get("title")), str(manifest.get("content_digest")),
                   "sha256:" + hashlib.sha256(checksums).hexdigest(), licence_class(manifest), datasheet)


def datasheet_copied(cls: LicenceClass) -> bool:
    """Whether the CC-BY-4.0 index holds a copy of a corpus's datasheet: not for a copyleft class (D-949)."""
    return not is_copyleft(cls.spdx)


def _corpus_row(corpus: _Corpus, archives: Sequence[str]) -> dict[str, Any]:
    name = f"DATASHEET-{corpus.corpus_id}.md"
    location = "index" if datasheet_copied(corpus.cls) else "part"
    return {"archives": list(archives), "content_digest": corpus.content_digest, "corpus_id": corpus.corpus_id,
            "corpus_version": corpus.version,
            "datasheet": {"location": location, "name": name, **_digests(corpus.datasheet)},
            "licence_class": corpus.cls.to_json(), "root_digest": corpus.root_digest, "title": corpus.title}  # fmt: skip


def _match(part: _Part, corpus: _Corpus) -> list[str]:
    """The archive names of ``corpus`` in ``part`` once every recorded value agrees; a refusal otherwise."""
    (entry,) = [e for e in part.corpora if e.get("corpus_id") == corpus.corpus_id]
    recorded = (entry.get("corpus_version"), entry.get("content_digest"), entry.get("root_digest"))
    if recorded != (corpus.version, corpus.content_digest, corpus.root_digest):
        raise _refuse(f"{corpus.corpus_id}: the sealed corpus is not the version, content digest or root digest the part "
                      f"record {part.record} holds", "corpus_mismatch")
    cls = entry.get("licence_class")
    if not isinstance(cls, Mapping) or _class(cls, part.record) != corpus.cls or corpus.cls != part.cls:
        raise _refuse(f"{corpus.corpus_id}: its licence class differs from the part record {part.record}'s",
                      "corpus_mismatch")
    sheet = part.datasheets.get(f"DATASHEET-{corpus.corpus_id}.md")
    if sheet != "sha256:" + hashlib.sha256(corpus.datasheet).hexdigest():
        raise _refuse(f"{corpus.corpus_id}: its datasheet differs from the part record {part.record}'s copy",
                      "corpus_mismatch")
    names = entry.get("archives")
    if not isinstance(names, list) or not names or not all(isinstance(n, str) for n in names):
        raise _refuse(f"{part.record}: the corpus entry of {corpus.corpus_id} names no archive", "part")
    return list(names)


# ================================================================================================ documents
@dataclass
class IndexReport:
    """The outcome of :func:`build_index`."""

    out: Path
    parts: list[dict[str, Any]]
    documents: list[dict[str, Any]]
    target: str
    notices: list[str] = field(default_factory=list)
    dry_run: bool = False

    @property
    def counters(self) -> dict[str, int]:
        return {"bytes": sum(d["bytes"] for d in self.documents), "corpora": sum(len(p["corpora"]) for p in self.parts),
                "documents": len(self.documents) + (0 if self.dry_run else 1), "parts": len(self.parts)}  # fmt: skip


def _description(metadata: ReleaseMetadata, parts: Sequence[Mapping[str, Any]], release_date: date) -> str:
    lines = []
    if metadata.description_preamble.strip():
        lines += [metadata.description_preamble.strip(), ""]
    n_corpora = sum(len(p["corpora"]) for p in parts)
    lines.append(f"This deposit draft is the index of an AgentPROV collection of {len(parts)} part record(s) holding "
                 f"{n_corpora} corpus version(s), prepared offline by agentprov package --index for the release date "
                 f"{release_date.isoformat()}. It holds no corpus data: {COLLECTION_INDEX} lists each part record's "
                 f"reserved DOI and each corpus's content digest and root digest, and a copy of each corpus's datasheet "
                 f"is included, except for corpora under a copyleft licence, whose datasheets stay in their part "
                 f"records. {_NOT_PUBLISHED}")
    for part in parts:
        cls = LicenceClass(part["licence_class"]["spdx"], tuple(part["licence_class"]["restrictions"]))
        corpora = ", ".join(f"{c['corpus_id']} {c['corpus_version']}" for c in part["corpora"])
        lines += ["", f"Part record {part['title']} (reserved DOI {part['reserved_doi']}; licence class "
                      f"{class_text(cls)}): {corpora}."]
    lines += ["", f"This index record is licensed {INDEX_LICENCE.spdx}. Each corpus keeps its own licence, stated in its "
                  "part record and its datasheet. A reserved DOI is registered only when its record is published.",
              "", "To verify a corpus: download its part record, compare each archive's sha256 or md5 with that record's "
                  "DEPOSIT-MANIFEST.json, and run agentprov verify on the archives with the root digest listed here "
                  "(archive mode, no extraction; H.5.5)."]
    return "\n".join(lines) + "\n"


def _readme(metadata: ReleaseMetadata, parts: Sequence[Mapping[str, Any]], documents: Sequence[str],
            producer: DepositProducer, release_date: date, related: Sequence[Related]) -> bytes:
    lines = [f"# {metadata.title}", "",
             f"Collection index (unpublished deposit draft) for the release date {release_date.isoformat()}, prepared "
             f"offline by AgentPROV {producer.agentprov_version} (commit `{producer.git_commit or 'unknown'}`) with "
             f"`agentprov package --index`. {_NOT_PUBLISHED} Publishing, which registers the DOIs, is a manual action.",
             "", f"This record holds **no corpus data**. Each corpus is in exactly one part record, listed below and in "
                 f"`{COLLECTION_INDEX}`. This index is licensed {INDEX_LICENCE.spdx}; each corpus keeps its own licence, "
                 "stated in its part record and its datasheet. Datasheets of corpora under a copyleft licence are not "
                 "copied here; they are in their part records.",
             "", "## Part records", "", "| Record | Reserved DOI | Licence class | Corpora |", "|---|---|---|---|"]
    for part in parts:
        cls = LicenceClass(part["licence_class"]["spdx"], tuple(part["licence_class"]["restrictions"]))
        corpora = ", ".join(f"`{c['corpus_id']}`" for c in part["corpora"])
        lines.append(f"| {part['title']} | `{part['reserved_doi']}` | {class_text(cls)} | {corpora} |")
    lines += ["", "A reserved DOI resolves only after its record is published.", "", "## Corpora", ""]
    for part in parts:
        for corpus in part["corpora"]:
            cls = LicenceClass(corpus["licence_class"]["spdx"], tuple(corpus["licence_class"]["restrictions"]))
            lines += [f"### {corpus['corpus_id']} {corpus['corpus_version']}", "",
                      f"- Title: {corpus['title']}",
                      f"- Part record: `{part['reserved_doi']}` ({part['title']})",
                      f"- Licence class: {class_text(cls)}",
                      f"- Content digest: `{corpus['content_digest']}`",
                      f"- Root digest: `{corpus['root_digest']}` (sha256 of `checksums.sha256`; H.5.4)",
                      (f"- Datasheet: `{corpus['datasheet']['name']}`" if corpus["datasheet"]["location"] == "index" else
                       f"- Datasheet: `{corpus['datasheet']['name']}` in the part record `{part['reserved_doi']}` "
                       f"(sha256 `{corpus['datasheet']['sha256']}`; not copied: copyleft licence class)"),
                      f"- Archives in the part record: {len(corpus['archives'])}", ""]
    if related:
        lines += ["## Related records", ""]
        lines += [f"- {r.relation} {r.scheme} `{r.identifier}`" for r in related]
        lines.append("")
    lines += ["## Files", "", "| File | |", "|---|---|"]
    lines += [f"| `{name}` | see `{DEPOSIT_MANIFEST}` |" for name in documents]
    lines += ["", "## Verifying a corpus", "",
              "1. Download the corpus's part record and check each archive's sha256 (or md5) against that record's "
              f"`{DEPOSIT_MANIFEST}`.",
              "2. Run `agentprov verify --release --root-digest <root digest>` on the part record's deposit directory, "
              "with the root digest listed here for each of its corpora. It reads the archives without extraction "
              "(archive mode, H.5.5).",
              "3. Compare each root digest with the one published outside the deposits: the annotation of the tag "
              "`corpus/<corpus_id>/v<version>` and the paper (REP-4). This index is itself a deposit, so it anchors "
              "a root digest only together with those.",
              "", "## Citation", "",
              "Cite a corpus by its part record's version DOI, its concept DOI and its root digest together (REP-4); "
              "cite the collection by this record's DOI. This draft's own DOI is assigned when the user publishes it.",
              ""]
    return "\n".join(lines).encode("utf-8")


def _metadata_document(metadata: ReleaseMetadata, related: Sequence[Related], documents: Sequence[str], description: str,
                       release_date: date, version: str, producer: DepositProducer) -> dict[str, Any]:
    """``deposit-metadata.json`` (``agentprov-deposit/0.1``, the corpus deposit's shape): one licence, CC-BY-4.0, which
    covers the index's documents and no corpus or archive."""
    return {
        "concept_doi": metadata.concept_doi,
        "creators": [c.to_json() for c in metadata.creators],
        "description": description,
        "format": DEPOSIT_METADATA_FORMAT,
        "keywords": list(metadata.keywords),
        "licences": [{**INDEX_LICENCE.to_json(), "archives": [], "corpora": [], "documents": list(documents)}],
        "mixed_licence_classes": {"allowed": False, "classes": 1, "flag": None},
        "notice": f"Prepared offline by agentprov package --index. {_NOT_PUBLISHED} The user maps this file onto the "
                  "repository's deposit form; it does not claim fidelity to any repository API (H.10.5).",
        "publication_date": release_date.isoformat(),
        "related_identifiers": [r.to_json() for r in related],
        "release_scans": [],
        "resource_type": "dataset",
        "root_digests": {},
        "software": {"name": "agentprov", **producer.to_json()},
        "status": "draft-unpublished",
        "title": metadata.title,
        "version": version,
        "version_doi": None,
    }  # fmt: skip


# ================================================================================================ build_index
def _check_out(out: Path, inputs: Sequence[Path]) -> Path:
    partial = out.with_name(out.name + PARTIAL_SUFFIX)
    if os.path.lexists(out) or os.path.lexists(partial):
        raise _refuse("the index directory (or its .partial) already exists; a deposit draft is never rewritten", "exists")
    if not out.parent.is_dir():
        raise _usage("the parent of the index directory does not exist")
    assert_writable(out.parent)
    real_out = Path(os.path.realpath(out.parent)) / out.name
    for path in inputs:
        real = Path(os.path.realpath(path))
        if real_out == real or real_out.is_relative_to(real) or real.is_relative_to(real_out):
            raise _refuse("the index directory overlaps an input corpus or part deposit (N.1.9)", "overlap")
    return partial


def build_index(
    parts: Sequence[str | os.PathLike[str]],
    corpora: Sequence[str | os.PathLike[str]],
    metadata: ReleaseMetadata,
    out: str | os.PathLike[str],
    *,
    release_date: date,
    producer: DepositProducer,
    lint: Lint | None = None,
    limits: IngestLimits | None = None,
    dry_run: bool = False,
) -> IndexReport:
    """Build the index-only umbrella deposit at ``out`` from part receipts and sealed corpora (module docstring).

    Raises :class:`DepositRefusedError` (exit 4; usage exit 2), :class:`DepositError` (exit 1),
    :class:`agentprov.release.metadata.DepositMetadataError` (exit 2), the licence-class and interpreter-guard errors.
    ``dry_run`` runs every check and writes nothing (N.1.6)."""
    require_patched_for_archive(release=True)  # package is release mode (G.3.8); no override
    if not parts:
        raise _usage("no part receipt given (--part)")
    if not corpora:
        raise _usage("no corpus given (--corpus)")
    limits = limits or IngestLimits()
    receipt_paths = [Path(p) for p in parts]
    corpus_paths = [Path(p) for p in corpora]
    if len({os.path.realpath(p) for p in receipt_paths}) != len(receipt_paths):
        raise _usage("a part receipt is given twice")
    if len({os.path.realpath(p) for p in corpus_paths}) != len(corpus_paths):
        raise _usage("a corpus is given twice")
    opened = [_open_part(p, limits) for p in receipt_paths]
    out_path = Path(out)
    partial = _check_out(out_path, [*corpus_paths, *(p.receipt.parent / p.record for p in opened)])
    if len({p.target for p in opened}) != 1:
        raise _refuse("the part receipts belong to different targets (sandbox and production)", "targets")
    for key, what in ((lambda p: p.reserved_doi, "reserved DOI"), (lambda p: p.record_id, "record id"),
                      (lambda p: p.deposition_id, "deposition"),
                      (lambda p: os.path.realpath(p.receipt.parent / p.record), "deposit directory"),
                      (lambda p: p.record, "record name")):
        values = [key(p) for p in opened]
        if len(set(values)) != len(values):
            raise _refuse(f"two part receipts name the same {what}", "duplicate")
    home: dict[str, _Part] = {}
    for part in opened:
        for entry in part.corpora:
            corpus_id = entry.get("corpus_id")
            if not isinstance(corpus_id, str):
                raise _refuse(f"{part.record}: a corpus entry has no corpus id", "part")
            if corpus_id in home:
                raise _refuse(f"{corpus_id} is in two part records ({home[corpus_id].record}, {part.record}); a corpus has "
                              "one home (D-941)", "duplicate")
            home[corpus_id] = part
    sealed = [_open_corpus(p, limits) for p in corpus_paths]
    ids = [c.corpus_id for c in sealed]
    if len(set(ids)) != len(ids):
        raise _usage("a corpus id appears twice among the --corpus directories")
    missing = sorted(set(home) - set(ids))
    extra = sorted(set(ids) - set(home))
    if missing:
        raise _refuse(f"{len(missing)} corpus(es) of the part records are not given with --corpus: "
                      f"{', '.join(missing[:5])}", "corpus_missing")
    if extra:
        raise _refuse(f"{len(extra)} --corpus director(ies) are in no part record: {', '.join(extra[:5])}", "corpus_extra")
    by_id = {c.corpus_id: c for c in sealed}
    rows: dict[str, list[dict[str, Any]]] = {p.record: [] for p in opened}
    for corpus_id in sorted(by_id):
        part = home[corpus_id]
        rows[part.record].append(_corpus_row(by_id[corpus_id], _match(part, by_id[corpus_id])))
    ordered = sorted(opened, key=lambda p: p.record.encode("utf-8"))
    part_rows = [p.entry(rows[p.record]) for p in ordered]
    versions = {c.version for c in sealed}
    if metadata.version is None and len(versions) > 1:
        raise DepositMetadataError("release.toml: version is required when the corpora carry different versions")
    version = metadata.version or next(iter(versions))
    target = ordered[0].target

    docs: dict[str, bytes] = {}
    for corpus_id in sorted(by_id):
        if datasheet_copied(by_id[corpus_id].cls):  # D-949: no copyleft datasheet under the CC-BY-4.0 index
            docs[f"DATASHEET-{corpus_id}.md"] = by_id[corpus_id].datasheet  # byte copies (H.10.3; never a deposit note)
    related = merge_related([metadata.related, [Related("HasPart", "DOI", p.reserved_doi,
                                                        f"part record {p.record}: reserved DOI (draft receipt)")
                                                for p in ordered]])
    names = sorted([*docs, *_FIXED_DOCUMENTS])
    description = _description(metadata, part_rows, release_date)
    docs[DEPOSIT_METADATA] = _document_bytes(_metadata_document(metadata, related, names, description, release_date,
                                                                version, producer))
    docs[COLLECTION_INDEX] = _document_bytes({
        "format": COLLECTION_INDEX_FORMAT,
        "licence": INDEX_LICENCE.to_json(),
        "notice": "Reserved DOIs are registered only when each record is published; the corpus digests are read from "
                  "the sealed corpora and equal their part records' deposit manifests.",
        "parts": part_rows,
        "producer": producer.to_json(),
        "release_date": release_date.isoformat(),
        "status": "draft-unpublished",
        "target": {"host": ordered[0].host, "name": target},
        "title": metadata.title,
        "version": version,
    })  # fmt: skip
    docs["README.md"] = _readme(metadata, part_rows, [*names, DEPOSIT_MANIFEST], producer, release_date, related)
    if lint is not None:
        violations = [*lint("README.md", docs["README.md"].decode("utf-8")),
                      *lint(f"{DEPOSIT_METADATA}#description", description)]
        if violations:
            shown = "; ".join(f"{code} at {where}: {detail}" for code, where, detail in violations[:5])
            raise DepositError(f"a generated index text fails the claims lint ({len(violations)}): {shown}",
                               code="release.failed.lint")
    documents = [{"name": name, **_digests(docs[name])} for name in sorted(docs)]
    notices = [f"{p.record}: reserved DOI {p.reserved_doi} on {p.target} (registered only when published)" for p in ordered]
    report = IndexReport(out_path, part_rows, documents, target, notices, dry_run=dry_run)
    if dry_run:
        return report
    manifest = {
        "collection_index": COLLECTION_INDEX,
        "counts": {"corpora": len(by_id), "parts": len(ordered)},
        "documents": documents,
        "format": INDEX_MANIFEST_FORMAT,
        "kind": INDEX_KIND,
        "licence_class": INDEX_LICENCE.to_json(),
        "producer": producer.to_json(),
        "release_date": release_date.isoformat(),
        "status": "draft-unpublished",
        "target": {"host": ordered[0].host, "name": target},
    }  # fmt: skip
    partial.mkdir()
    try:
        for name in sorted(docs):
            with open(partial / name, "xb") as handle:
                handle.write(docs[name])
        with open(partial / DEPOSIT_MANIFEST, "xb") as handle:
            handle.write(_document_bytes(manifest))
        atomic_swap_dir(partial, out_path)
    except BaseException:
        shutil.rmtree(partial, ignore_errors=True)
        raise
    return report


# ================================================================================================ the uploader's check
@dataclass
class IndexCheck:
    """What :func:`check_index_deposit` found: the consistency problems (empty: it passes) and the index's facts."""

    problems: list[str] = field(default_factory=list)
    target: str | None = None
    parts: int = 0
    corpora: int = 0


def _hash_file(directory: Path, name: str, limits: IngestLimits) -> dict[str, Any]:
    sha, md5, size = hashlib.sha256(), hashlib.md5(usedforsecurity=False), 0
    with open_evidence(directory, name, limits, allow_hardlinks=True) as stream:
        while chunk := stream.read(_CHUNK):
            sha.update(chunk)
            md5.update(chunk)
            size += len(chunk)
    return {"bytes": size, "md5": md5.hexdigest(), "sha256": "sha256:" + sha.hexdigest()}


def check_index_deposit(directory: str | os.PathLike[str], *, limits: IngestLimits | None = None) -> IndexCheck:
    """The offline check of an index deposit directory (H.10.7): closed world (the manifest's documents and the
    manifest, regular files only), every document's size, sha256 and md5, the index's shape (formats, kind, parts with
    distinct reserved DOIs, each corpus once), each datasheet copy against the index's digest and the licence
    CC-BY-4.0 in ``deposit-metadata.json``. Reads only the directory; never raises for a bad deposit (``problems``)."""
    path, limits = Path(directory), limits or IngestLimits()
    result = IndexCheck()
    problems = result.problems
    try:
        _, manifest = _read_json(path, DEPOSIT_MANIFEST, limits, DEPOSIT_MANIFEST)
        _, index = _read_json(path, COLLECTION_INDEX, limits, COLLECTION_INDEX)
        _, meta = _read_json(path, DEPOSIT_METADATA, limits, DEPOSIT_METADATA)
    except DepositRefusedError as exc:
        problems.append(str(exc))
        return result
    if not is_index_manifest(manifest) or manifest.get("status") != "draft-unpublished":
        problems.append(f"{DEPOSIT_MANIFEST} is not an unpublished {INDEX_MANIFEST_FORMAT} manifest of kind {INDEX_KIND}")
        return result
    if manifest.get("licence_class") != INDEX_LICENCE.to_json():
        problems.append(f"{DEPOSIT_MANIFEST}: the licence class is not {INDEX_LICENCE.spdx}")
    try:
        documents = _file_rows(manifest.get("documents"), f"{DEPOSIT_MANIFEST}: documents")
    except DepositRefusedError as exc:
        problems.append(str(exc))
        return result
    if DEPOSIT_MANIFEST in documents:
        problems.append(f"{DEPOSIT_MANIFEST} lists itself")
    try:
        present = sorted(os.listdir(path))
    except OSError as exc:
        problems.append(f"the directory cannot be listed ({type(exc).__name__})")
        return result
    for name in present:
        if not stat.S_ISREG((path / name).lstat().st_mode):
            problems.append("an entry of the directory is not a regular file (a link, a directory or a special file)")
    unlisted = sorted(set(present) - set(documents) - {DEPOSIT_MANIFEST})
    absent = sorted(set(documents) - set(present))
    if unlisted or absent:
        problems.append(f"the directory differs from {DEPOSIT_MANIFEST}: {len(unlisted)} unlisted, {len(absent)} absent")
    for name, row in sorted(documents.items()):
        if name in present and _SHA256.fullmatch(row[1]) and _MD5.fullmatch(row[2]):
            got = _hash_file(path, name, limits)
            if (got["bytes"], got["sha256"], got["md5"]) != row:
                problems.append(f"{name}: its size, sha256 or md5 differ from {DEPOSIT_MANIFEST}")
        elif name in present:
            problems.append(f"{name}: malformed digests in {DEPOSIT_MANIFEST}")
    if not isinstance(index, Mapping) or index.get("format") != COLLECTION_INDEX_FORMAT:
        problems.append(f"{COLLECTION_INDEX} is not an {COLLECTION_INDEX_FORMAT} document")
        return result
    raw_target = index.get("target")
    target: Mapping[str, Any] = raw_target if isinstance(raw_target, Mapping) else {}
    target_name = target.get("name")
    if (not isinstance(target_name, str) or RECEIPT_TARGETS.get(target_name) != target.get("host")
            or manifest.get("target") != target):
        problems.append(f"{COLLECTION_INDEX} names no known target, or another than {DEPOSIT_MANIFEST}")
    else:
        result.target = target_name
    parts = index.get("parts")
    if not isinstance(parts, list) or not parts or not all(isinstance(p, Mapping) for p in parts):
        problems.append(f"{COLLECTION_INDEX} lists no part record")
        return result
    dois: list[Any] = []
    sheets: list[str] = []
    ids: list[Any] = []
    for part in parts:
        doi = part.get("reserved_doi")
        if not isinstance(doi, str) or _DOI.fullmatch(doi) is None:
            problems.append(f"{COLLECTION_INDEX}: a part record has no reserved DOI")
        dois.append(doi)
        corpora = part.get("corpora")
        if not isinstance(corpora, list) or not corpora or not all(isinstance(c, Mapping) for c in corpora):
            problems.append(f"{COLLECTION_INDEX}: a part record lists no corpus")
            continue
        for corpus in corpora:
            sheet = corpus.get("datasheet") if isinstance(corpus.get("datasheet"), Mapping) else {}
            expected = f"DATASHEET-{corpus.get('corpus_id')}.md"
            ids.append(corpus.get("corpus_id"))
            raw_cls = corpus.get("licence_class") if isinstance(corpus.get("licence_class"), Mapping) else {}
            spdx = raw_cls.get("spdx")
            copied = not (isinstance(spdx, str) and is_copyleft(spdx))
            if not isinstance(sheet, Mapping) or sheet.get("name") != expected:
                problems.append(f"{COLLECTION_INDEX}: a corpus names no datasheet of its own")
            elif sheet.get("location") != ("index" if copied else "part"):
                problems.append(f"{expected}: a copyleft corpus's datasheet is linked, every other one copied (D-949)")
            elif copied:
                sheets.append(expected)
                if documents.get(expected) != (sheet.get("bytes"), sheet.get("sha256"), sheet.get("md5")):
                    problems.append(f"{expected}: the copy differs from the digest {COLLECTION_INDEX} records")
            for key in ("content_digest", "root_digest"):
                if not isinstance(corpus.get(key), str) or _SHA256.fullmatch(corpus[key]) is None:
                    problems.append(f"{COLLECTION_INDEX}: a corpus has no {key}")
    if len(set(dois)) != len(dois):
        problems.append(f"{COLLECTION_INDEX}: two part records share a reserved DOI")
    if len(set(map(str, ids))) != len(ids):
        problems.append(f"{COLLECTION_INDEX}: a corpus is in two part records")
    if sorted(documents) != sorted([*_FIXED_DOCUMENTS, *sheets]):
        problems.append(f"{DEPOSIT_MANIFEST}: documents is not exactly README.md, {COLLECTION_INDEX}, "
                        f"{DEPOSIT_METADATA} and one datasheet copy per corpus that is not copyleft")
    licences = meta.get("licences") if isinstance(meta, Mapping) else None
    if (not isinstance(licences, list) or len(licences) != 1 or not isinstance(licences[0], Mapping)
            or licences[0].get("spdx") != INDEX_LICENCE.spdx or licences[0].get("restrictions") != []
            or licences[0].get("archives") != [] or licences[0].get("corpora") != []):
        problems.append(f"{DEPOSIT_METADATA}: the licence is not {INDEX_LICENCE.spdx} over the index's own documents")
    result.parts, result.corpora = len(parts), len(ids)
    return result


def index_members(directory: str | os.PathLike[str], *, limits: IngestLimits | None = None) -> tuple[bytes, list[tuple[str, Any]]]:
    """The raw ``COLLECTION-INDEX.json`` of an index deposit directory and its part records as ``(reserved DOI,
    deposition id)`` pairs, for the uploader's cross-link membership check (D-949). Raises :class:`DepositRefusedError`
    when the file cannot be read or lists no part."""
    path, limits = Path(directory), limits or IngestLimits()
    raw, index = _read_json(path, COLLECTION_INDEX, limits, COLLECTION_INDEX)
    parts = index.get("parts") if isinstance(index, Mapping) else None
    if not isinstance(parts, list) or not parts or not all(isinstance(p, Mapping) for p in parts):
        raise _refuse(f"{COLLECTION_INDEX} lists no part record", "index")
    return raw, [(str(p.get("reserved_doi")), p.get("deposition_id")) for p in parts]
