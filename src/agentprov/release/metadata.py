"""Deposit metadata: ``release.toml``, licence classes (D-42), release-scan results and ``deposit-metadata.json``.

Pure functions over parsed documents; :mod:`agentprov.release.builder` does the IO. Nothing here touches the network or
starts a process (H.10.1(1)).

**``release.toml``** (H.10.2) is supplied by the user; the builder never infers creators from git. Closed tables::

    title = "…"                       # required
    description_preamble = "…"        # required (may be empty)
    keywords = ["…"]                  # required (may be empty)
    version = "0.1.0"                 # optional; required when the corpora carry different versions
    concept_doi = "10.5281/zenodo.…"  # optional: absent on the first release (H.10.5(1))
    [[creators]]                      # at least one
    name = "…"
    orcid = "0000-0000-0000-0000"     # optional
    affiliation = "…"                 # optional
    [[related]]                       # optional
    identifier = "…"
    scheme = "DOI"                    # DataCite relatedIdentifierType
    relation = "IsSupplementTo"       # DataCite relationType

**Licence classes (D-42; AD-20(b), D-25, H.10.6).** A corpus's class is ``(licences.derived.spdx, sorted
licences.restrictions)``, read from the sealed manifest and checked equal to its ``licences.class``. Classes compare by
exact SPDX id, so GPL-3.0 and AGPL-3.0 (and ``-only`` / ``-or-later``) are distinct classes. A copyleft or
non-commercial source licence is never relicensed: the derived licence equals the source's. Copyleft and
non-commercial are family tests on each term of the SPDX expression (``GPL-2.0+``, ``… WITH …-exception``,
``PolyForm-Noncommercial-…``), and any such term fails closed, even in an ``OR`` expression. A non-commercial class
(``…-NC-…``, ``…Noncommercial…``) is admitted only in a corpus whose id ends ``-nc`` and whose licence policy is ``nc_partition``, and an
``-nc`` corpus only with a non-commercial class. One deposit holds one class; ``--allow-mixed-licence-classes`` admits
several (recorded in the metadata and the datasheet copies), except that a non-commercial class is never mixed with
another class (H.4.2: a separately licensed ``-nc`` corpus **and deposit**).

**Release scans (G.9.4).** ``<corpus>.release-scan.json`` (``agentprov-release-scan/0.1``), written by
``tools/release_scan.py`` (gitleaks), must name the corpus's root digest, record the pinned scanners (gitleaks
:data:`GITLEAKS_VERSION` with the committed configuration's ``config_sha256``, and ``agentprov-path-scan``
:data:`PATH_SCAN_VERSION`), and triage every
finding (``real``, ``synthetic-benchmark``, ``false-positive``, ``home-path``, each with a reason); a ``real`` finding is
admitted only when ``WITHHELD.json`` names its fingerprint. A matched value is never recorded.
"""

from __future__ import annotations

import hashlib
import re
import tomllib
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final

from agentprov.corpus.licences import is_copyleft, is_non_commercial
from agentprov.errors import AgentProvError

__all__ = [
    "DEPOSIT_METADATA_FORMAT",
    "DEPOSIT_NOTE_HEADER",
    "GITLEAKS_CONFIG",
    "GITLEAKS_CONFIG_SHA256",
    "GITLEAKS_KEY_ALLOWLIST",
    "GITLEAKS_VERSION",
    "PATH_SCAN_TOOL",
    "PATH_SCAN_VERSION",
    "RELATION_TYPES",
    "RELEASE_SCAN_FORMAT",
    "SCHEMES",
    "TRIAGE_VALUES",
    "Creator",
    "DepositMetadataError",
    "LicenceClass",
    "LicenceClassError",
    "Related",
    "ReleaseMetadata",
    "ScanRefusedError",
    "ScanSummary",
    "check_licence_classes",
    "check_release_scan",
    "check_withhold_scan",
    "class_text",
    "corpus_related",
    "datasheet_copy",
    "licence_class",
    "merge_related",
    "parse_release_toml",
]

DEPOSIT_METADATA_FORMAT: Final = "agentprov-deposit/0.1"
RELEASE_SCAN_FORMAT: Final = "agentprov-release-scan/0.1"
#: G.9.4 triage values. ``pinned-account`` (D-604 item 7) is a third-party account path in a raw object that ships as
#: pinned (D-186 (c)): valid only for an ``account-path`` finding in ``raw/``.
TRIAGE_VALUES: Final = frozenset({"real", "synthetic-benchmark", "false-positive", "home-path", "pinned-account",
                                  "model-generated"})
#: D-810: the clearing bases of an ``email-address`` finding and the triage each fits. ``model-generated`` is a triage of its
#: own (kept and disclosed, never ``synthetic-benchmark``); ``benchmark-input`` and ``upstream-data`` are both
#: ``synthetic-benchmark`` and stay apart as bases.
BASIS_TRIAGE: Final = {"reserved": "false-positive", "upstream-data": "synthetic-benchmark",
                       "benchmark-input": "synthetic-benchmark", "model-generated": "model-generated",
                       "file-name": "false-positive"}
PINNED_ACCOUNT: Final = "pinned-account"

# The pinned release scanners (G.9.4; AD-10 row 19). ``tools/release_scan.py`` imports them, so the scan it writes and
# the check here (:func:`check_release_scan`) share one copy. The tool refuses another gitleaks; the deposit builder
# refuses a scan document that records another gitleaks, another rule set or another path-scan version.
#: gitleaks, the one secret scanner of v0.1.
GITLEAKS_VERSION: Final = "8.30.1"
#: The one committed exception to the default rules (user-approved 2026-10-11; narrowed by D-310, 2026-10-13): gitleaks'
#: ``generic-api-key`` reads AgentPROV's own content-addressed keys as API keys (``apv:derivationKey`` in every PROV
#: bundle, 26 lower-case base32 characters; ``subject_key`` in the register, ``ex_`` and 26; ``logical_key`` in the
#: index, ``lk_`` and 26). The allowlist is matched against the whole match (``regexTarget = "match"``, anchored), so it
#: hides exactly an uncut ``<field>":"<key>"`` and nothing else on the line: a secret elsewhere in the same JSONL record
#: is still reported. A match cut at a fragment boundary is not hidden here (a suffix such as ``ionKey`` or ``ct_key``
#: also ends ``sessionKey`` or ``project_key``); ``tools/release_scan.py`` resolves cuts against the file instead
#: (``key_cut_explained``).
GITLEAKS_KEY_FIELDS: Final = ('derivationKey":"', 'subject_key":"ex_', 'logical_key":"lk_')
GITLEAKS_KEY_ALLOWLIST: Final = "^(" + "|".join(GITLEAKS_KEY_FIELDS) + ')[a-z2-7]{26}"$'
#: The gitleaks configuration the scan runs with: the default rules plus the allowlist above.
GITLEAKS_CONFIG: Final = (
    "[extend]\nuseDefault = true\n\n"
    "[[allowlists]]\n"
    'description = "AgentPROV content-addressed keys (apv:derivationKey, subject_key, logical_key)"\n'
    'regexTarget = "match"\n'
    "regexes = ['''" + GITLEAKS_KEY_ALLOWLIST + "''']\n"
)
#: Recorded in the scan document (``config_sha256`` of the gitleaks entry), so a deposit shows which rule set it used.
GITLEAKS_CONFIG_SHA256: Final = hashlib.sha256(GITLEAKS_CONFIG.encode("ascii")).hexdigest()
#: The tool name and version of ``tools/release_scan.py``'s own search. 2: unselected archive members are read decoded
#: (D-491); 3: account paths (D-457); 4: secret shapes (D-600); 5: e-mail addresses (D-810); 6: a JSON escape before an
#: address is not its local part, and an archive read decoded is not judged by its stored bytes (D-810).
PATH_SCAN_TOOL: Final = "agentprov-path-scan"
PATH_SCAN_VERSION: Final = "6"

#: DataCite relationType vocabulary (DataCite Metadata Schema 4.6).
RELATION_TYPES: Final = frozenset({
    "IsCitedBy", "Cites", "IsSupplementTo", "IsSupplementedBy", "IsContinuedBy", "Continues", "IsDescribedBy",
    "Describes", "HasMetadata", "IsMetadataFor", "HasVersion", "IsVersionOf", "IsNewVersionOf", "IsPreviousVersionOf",
    "IsPartOf", "HasPart", "IsPublishedIn", "IsReferencedBy", "References", "IsDocumentedBy", "Documents",
    "IsCompiledBy", "Compiles", "IsVariantFormOf", "IsOriginalFormOf", "IsIdenticalTo", "IsReviewedBy", "Reviews",
    "IsDerivedFrom", "IsSourceOf", "IsRequiredBy", "Requires", "IsObsoletedBy", "Obsoletes", "IsCollectedBy", "Collects",
    "HasTranslation", "IsTranslationOf",
})  # fmt: skip
#: DataCite relatedIdentifierType vocabulary (4.6) as accepted here.
SCHEMES: Final = frozenset({
    "ARK", "arXiv", "bibcode", "CSTR", "DOI", "EAN13", "EISSN", "Handle", "IGSN", "ISBN", "ISSN", "ISTC", "LISSN", "LSID",
    "PMID", "PURL", "RRID", "UPC", "URL", "URN", "w3id",
})  # fmt: skip

_DOI: Final = re.compile(r"10\.[0-9]{4,9}/[A-Za-z0-9._;()/:-]+")
_ORCID: Final = re.compile(r"[0-9]{4}-[0-9]{4}-[0-9]{4}-[0-9]{3}[0-9X]")
_SEMVER: Final = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?")
_ARXIV: Final = re.compile(r"arXiv:([0-9]{4}\.[0-9]{4,5}(?:v[0-9]+)?)")
_URL: Final = re.compile(r"https://[A-Za-z0-9.-]+(?:/[A-Za-z0-9._~%/-]*)?")
_COMMIT: Final = re.compile(r"[0-9a-f]{40}")
_MAX_TEXT: Final = 20_000


class DepositMetadataError(AgentProvError):
    """``release.toml`` is malformed (exit 2, usage: the user's input file)."""

    code = "release.metadata"
    exit_code = 2


class LicenceClassError(AgentProvError):
    """A licence-class rule refused the deposit (D-42; exit 4)."""

    code = "release.refused.licence_class"
    exit_code = 4


# ================================================================================================ release.toml
@dataclass(frozen=True)
class Creator:
    name: str
    orcid: str | None = None
    affiliation: str | None = None

    def to_json(self) -> dict[str, Any]:
        return {"affiliation": self.affiliation, "name": self.name, "orcid": self.orcid}


@dataclass(frozen=True, order=True)
class Related:
    """One related identifier (DataCite vocabulary); ``origin`` says where it came from (never invented)."""

    relation: str
    scheme: str
    identifier: str
    origin: str = "release.toml"

    def to_json(self) -> dict[str, Any]:
        return {"identifier": self.identifier, "origin": self.origin, "relation": self.relation, "scheme": self.scheme}


@dataclass(frozen=True)
class ReleaseMetadata:
    """The parsed ``release.toml`` (H.10.2)."""

    title: str
    creators: tuple[Creator, ...]
    keywords: tuple[str, ...] = ()
    description_preamble: str = ""
    concept_doi: str | None = None
    version: str | None = None
    related: tuple[Related, ...] = field(default_factory=tuple)


def _text(value: object, where: str, *, allow_empty: bool = False, max_len: int = 500) -> str:
    if not isinstance(value, str) or (not allow_empty and not value.strip()) or len(value) > max_len:
        raise DepositMetadataError(f"release.toml: {where} is a non-empty string of at most {max_len} characters")
    if any(ord(c) < 32 and c not in "\n\t" for c in value):
        raise DepositMetadataError(f"release.toml: {where} holds a control character")
    return value


def _closed(table: Mapping[str, Any], where: str, required: set[str], optional: set[str]) -> None:
    missing = required - set(table)
    extra = set(table) - required - optional
    if missing or extra:
        raise DepositMetadataError(f"release.toml: {where} needs {sorted(required)} and may hold {sorted(optional)}; "
                                   f"missing {sorted(missing)}, unknown {sorted(extra)}")


def parse_release_toml(data: bytes) -> ReleaseMetadata:
    """Parse ``release.toml`` strictly (closed tables; DOIs, ORCIDs and the DataCite vocabularies checked)."""
    try:
        doc = tomllib.loads(data.decode("utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError):
        raise DepositMetadataError("release.toml is not valid UTF-8 TOML") from None
    _closed(doc, "the top level", {"title", "creators", "keywords", "description_preamble"},
            {"concept_doi", "version", "related"})
    title = _text(doc["title"], "title", max_len=300)
    if not isinstance(doc["creators"], list) or not doc["creators"]:
        raise DepositMetadataError("release.toml: [[creators]] needs at least one entry")
    creators = []
    for i, entry in enumerate(doc["creators"]):
        if not isinstance(entry, dict):
            raise DepositMetadataError(f"release.toml: creators[{i}] is a table")
        _closed(entry, f"creators[{i}]", {"name"}, {"orcid", "affiliation"})
        orcid = entry.get("orcid")
        if orcid is not None and (not isinstance(orcid, str) or _ORCID.fullmatch(orcid) is None):
            raise DepositMetadataError(f"release.toml: creators[{i}].orcid is an ORCID iD 0000-0000-0000-000X")
        affiliation = entry.get("affiliation")
        creators.append(Creator(_text(entry["name"], f"creators[{i}].name"), orcid,
                                None if affiliation is None else _text(affiliation, f"creators[{i}].affiliation")))
    keywords = doc["keywords"]
    if not isinstance(keywords, list):
        raise DepositMetadataError("release.toml: keywords is an array of strings")
    words = tuple(_text(k, "a keyword", max_len=100) for k in keywords)
    if len(set(words)) != len(words):
        raise DepositMetadataError("release.toml: keywords are unique")
    preamble = _text(doc["description_preamble"], "description_preamble", allow_empty=True, max_len=_MAX_TEXT)
    concept = doc.get("concept_doi")
    if concept is not None and (not isinstance(concept, str) or _DOI.fullmatch(concept) is None):
        raise DepositMetadataError("release.toml: concept_doi is a DOI 10.NNNN/…")
    version = doc.get("version")
    if version is not None and (not isinstance(version, str) or _SEMVER.fullmatch(version) is None):
        raise DepositMetadataError("release.toml: version is SemVer")
    related = []
    for i, entry in enumerate(doc.get("related", [])):
        if not isinstance(entry, dict):
            raise DepositMetadataError(f"release.toml: related[{i}] is a table")
        _closed(entry, f"related[{i}]", {"identifier", "scheme", "relation"}, set())
        scheme, relation = entry["scheme"], entry["relation"]
        if scheme not in SCHEMES:
            raise DepositMetadataError(f"release.toml: related[{i}].scheme is a DataCite relatedIdentifierType")
        if relation not in RELATION_TYPES:
            raise DepositMetadataError(f"release.toml: related[{i}].relation is a DataCite relationType")
        identifier = _text(entry["identifier"], f"related[{i}].identifier", max_len=300)
        if scheme == "DOI" and _DOI.fullmatch(identifier) is None:
            raise DepositMetadataError(f"release.toml: related[{i}].identifier is not a DOI")
        related.append(Related(relation, scheme, identifier))
    return ReleaseMetadata(title, tuple(creators), words, preamble, concept, version, tuple(sorted(set(related))))


# ================================================================================================ licence classes (D-42)
@dataclass(frozen=True, order=True)
class LicenceClass:
    """``(derived spdx, sorted restrictions)`` (H.2.10 ``class``; AD-20(b))."""

    spdx: str
    restrictions: tuple[str, ...]

    @property
    def non_commercial(self) -> bool:
        return is_non_commercial(self.spdx)

    def to_json(self) -> dict[str, Any]:
        return {"restrictions": list(self.restrictions), "spdx": self.spdx}

    def label(self) -> str:
        return self.spdx + ("" if not self.restrictions else f" + {len(self.restrictions)} restriction(s)")


def licence_class(manifest: Mapping[str, Any]) -> LicenceClass:
    """The licence class of one sealed corpus, with the per-corpus D-42 rules (raises :class:`LicenceClassError`).

    * the class recorded in ``licences.class`` equals ``(derived.spdx, sorted restrictions)``;
    * redistribution is permitted and the raw policy is not ``withhold`` (H.4.1) — checked by the builder too;
    * a copyleft (GPL/AGPL/LGPL) or non-commercial source licence is not relicensed: derived spdx == source spdx (D-25);
    * non-commercial ⇔ ``-nc`` corpus id ⇔ licence policy ``nc_partition`` (D-25, H.4.1(2)).
    """
    corpus_id = str(manifest.get("corpus_id"))
    lic = manifest.get("licences")
    if not isinstance(lic, Mapping):
        raise LicenceClassError(f"{corpus_id}: the manifest has no licences block")
    derived = lic.get("derived") or {}
    spdx = derived.get("spdx")
    restrictions = lic.get("restrictions")
    if not isinstance(spdx, str) or not spdx or not isinstance(restrictions, list) or not all(
            isinstance(r, str) for r in restrictions):
        raise LicenceClassError(f"{corpus_id}: licences.derived.spdx or licences.restrictions is missing")
    cls = LicenceClass(spdx, tuple(sorted(set(restrictions))))
    recorded = lic.get("class") or {}
    if recorded.get("spdx") != cls.spdx or tuple(recorded.get("restrictions") or ()) != cls.restrictions:
        raise LicenceClassError(f"{corpus_id}: licences.class differs from (derived spdx, sorted restrictions) (H.2.10)")
    policy = (lic.get("policy") or {})
    if lic.get("redistribution") == "not-permitted" or policy.get("raw_policy") == "withhold" or policy.get(
            "licence_policy") == "forbidden":
        raise LicenceClassError(f"{corpus_id}: the licence does not permit redistribution (raw policy withhold; H.4.1)",
                                code="release.refused.withhold")
    for raw in lic.get("raw") or ():
        source_spdx = raw.get("spdx") if isinstance(raw, Mapping) else None
        # Fail closed: any copyleft or non-commercial term forces derived == source, also inside an OR expression. A
        # dual licence such as ``GPL-2.0-or-later OR MIT`` may lawfully be taken as MIT, but the manifest does not say
        # which alternative was elected; record the elected licence as the source spdx to relicense under it.
        guarded = isinstance(source_spdx, str) and (is_copyleft(source_spdx) or is_non_commercial(source_spdx))
        if guarded and source_spdx != spdx:
            raise LicenceClassError(f"{corpus_id}: a copyleft or non-commercial source licence ({source_spdx}) is not "
                                    f"relicensed; the derived licence must be {source_spdx} (D-25)")
    nc_id = corpus_id.endswith("-nc")
    if cls.non_commercial and not nc_id:
        raise LicenceClassError(f"{corpus_id}: a non-commercial class belongs to a separately licensed -nc corpus "
                                "(D-25, H.4.1)", code="release.refused.nc_partition")
    if nc_id and not cls.non_commercial:
        raise LicenceClassError(f"{corpus_id}: an -nc corpus carries a non-commercial licence class (D-25)",
                                code="release.refused.nc_partition")
    if cls.non_commercial and (policy.get("licence_policy") != "nc_partition"
                               or lic.get("redistribution") != "permitted-non-commercial"):
        raise LicenceClassError(f"{corpus_id}: a non-commercial class needs licence policy nc_partition and "
                                "redistribution permitted-non-commercial (H.4.1)", code="release.refused.nc_partition")
    return cls


def check_licence_classes(classes: Mapping[str, LicenceClass], *, allow_mixed: bool) -> list[LicenceClass]:
    """D-42 across the corpora of one deposit (``corpus_id -> class``): one class, unless ``allow_mixed``; a
    non-commercial class is never mixed. Returns the distinct classes, sorted."""
    distinct = sorted(set(classes.values()))
    if len(distinct) <= 1:
        return distinct
    shown = "; ".join(f"{cid}: {cls.label()}" for cid, cls in sorted(classes.items()))
    if any(c.non_commercial for c in distinct):
        raise LicenceClassError("a non-commercial (-nc) corpus is deposited alone with its licence class; "
                                f"--allow-mixed-licence-classes does not cover it (H.4.2, D-25): {shown}",
                                code="release.refused.nc_partition")
    if not allow_mixed:
        raise LicenceClassError(f"the corpora belong to different licence classes ({shown}); one deposit holds one "
                                "class (AD-20(b), D-42). Build one deposit per class, or pass "
                                "--allow-mixed-licence-classes if record-level multi-licence support was verified",
                                code="release.refused.mixed_licence_classes")
    return distinct


#: The header of the note appended to every datasheet copy of a mixed-licence-class deposit (D-490).
DEPOSIT_NOTE_HEADER: Final = "## Deposit note (added by the deposit builder; not part of the sealed corpus)"


def class_text(cls: LicenceClass) -> str:
    """A licence class as the deposit documents print it: the SPDX id, then any restrictions, each quoted."""
    return cls.spdx + ("" if not cls.restrictions else "; restrictions: " + " ".join(f'"{r}"' for r in cls.restrictions))


def datasheet_copy(datasheet: bytes, own: LicenceClass, classes: Sequence[LicenceClass], mixed: bool) -> bytes:
    """The deposit copy ``DATASHEET-<corpus_id>.md`` of a sealed ``DATASHEET.md`` (H.10.3; D-490, D-620).

    Without mixed licence classes it is the sealed bytes. With them it is the sealed text (trailing line feeds folded
    into one) followed by the deposit note naming the corpus's own class ``own`` and the deposit's ``classes``. The
    builder writes it and archive-mode ``verify`` rebuilds and compares it, so both use this one function."""
    if not mixed:
        return datasheet
    note = ["", "---", "", DEPOSIT_NOTE_HEADER, "",
            "This corpus was deposited together with corpora of other licence classes under "
            "`--allow-mixed-licence-classes` (AD-20(b)). Its own licence class is " + class_text(own) + ". The "
            "classes in the deposit are: " + "; ".join(class_text(c) for c in classes) + ".", ""]
    return datasheet.rstrip(b"\n") + b"\n" + "\n".join(note).encode("utf-8")


# ================================================================================================ release scans (G.9.4)
@dataclass(frozen=True)
class ScanSummary:
    """What the deposit records about one corpus's release scan (never a matched value)."""

    corpus_id: str
    root_digest: str
    tools: tuple[tuple[str, str], ...]  # (name, version)
    findings: int
    by_triage: Mapping[str, int]
    scan_sha256: str
    #: findings cleared by a rule, by basis (D-810): ``benchmark-input`` and ``upstream-data`` are counted apart
    by_basis: Mapping[str, int] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {"by_basis": dict(sorted(self.by_basis.items())), "by_triage": dict(sorted(self.by_triage.items())),
                "corpus_id": self.corpus_id, "findings": self.findings,
                "root_digest": self.root_digest, "scan_sha256": self.scan_sha256,
                "tools": [{"name": n, "version": v} for n, v in self.tools]}  # fmt: skip


class ScanRefusedError(AgentProvError):
    """The release scan is absent, stale, untriaged or has a ``real`` finding (G.9.4; exit 4)."""

    code = "release.refused.scan"
    exit_code = 4


def check_release_scan(doc: object, *, corpus_id: str, root_digest: str, withheld_fingerprints: Iterable[str],
                       scan_sha256: str, spec_sha256: str | None = None) -> ScanSummary:
    """Check one ``agentprov-release-scan/0.1`` document against the corpus (G.9.4); raise :class:`ScanRefusedError`.

    A finding a rule decided carries ``basis`` (D-810): :data:`BASIS_TRIAGE` says the triage each fits (``reserved`` and
    ``file-name`` ``false-positive``; ``upstream-data`` and ``benchmark-input`` ``synthetic-benchmark``;
    ``model-generated`` its own triage), and every basis but ``reserved`` is valid only when the document records the
    persona files of this very corpus: ``personas.spec_sha256`` equals ``spec_sha256``, the digest of the spec the corpus sealed (``files.spec``)."""
    if not isinstance(doc, Mapping) or doc.get("format") != RELEASE_SCAN_FORMAT:
        raise ScanRefusedError(f"{corpus_id}: the release scan is not an {RELEASE_SCAN_FORMAT} document")
    target = doc.get("target")
    if not isinstance(target, Mapping) or target.get("kind") != "corpus" or target.get("corpus_id") != corpus_id:
        raise ScanRefusedError(f"{corpus_id}: the release scan names another target")
    if target.get("root_digest") != root_digest:
        raise ScanRefusedError(f"{corpus_id}: the release scan is for another root digest; re-run tools/release_scan.py "
                               "on the sealed corpus", code="release.refused.scan_stale")
    tools = doc.get("tools")
    if not isinstance(tools, list) or not tools or not all(
            isinstance(t, Mapping) and isinstance(t.get("name"), str) and isinstance(t.get("version"), str) and t["version"]
            for t in tools):
        raise ScanRefusedError(f"{corpus_id}: the release scan records no scanner versions")
    names = {t["name"] for t in tools}
    if "gitleaks" not in names:
        raise ScanRefusedError(f"{corpus_id}: the release scan did not run gitleaks (the one secret scanner of v0.1)")
    # The pinned scanners (G.9.4; AD-10 row 19): another gitleaks has other default rules, another configuration other
    # allowlists, and an older path scan lacks searches (account paths D-457, secret shapes D-600). Recorded values are
    # never echoed.
    pinned = {"gitleaks": GITLEAKS_VERSION, PATH_SCAN_TOOL: PATH_SCAN_VERSION}
    for name, version in pinned.items():
        entries = [t for t in tools if t["name"] == name]
        if len(entries) != 1 or entries[0]["version"] != version:
            raise ScanRefusedError(f"{corpus_id}: the release scan did not run {name} {version} once, the pinned scanner "
                                   "of v0.1 (G.9.4); re-run tools/release_scan.py with it",
                                   code="release.refused.scan_tools")
    if next(t for t in tools if t["name"] == "gitleaks").get("config_sha256") != GITLEAKS_CONFIG_SHA256:
        raise ScanRefusedError(f"{corpus_id}: the release scan's gitleaks configuration is not the committed rule set "
                               f"(config_sha256 {GITLEAKS_CONFIG_SHA256}; G.9.4)", code="release.refused.scan_tools")
    findings = doc.get("findings")
    if not isinstance(findings, list):
        raise ScanRefusedError(f"{corpus_id}: the release scan has no findings array")
    withheld = set(withheld_fingerprints)
    by_triage: dict[str, int] = {}
    by_basis: dict[str, int] = {}
    untriaged = real = misplaced = 0
    personas = doc.get("personas")
    for finding in findings:
        if not isinstance(finding, Mapping) or not isinstance(finding.get("fingerprint"), str):
            raise ScanRefusedError(f"{corpus_id}: a release-scan finding has no fingerprint")
        triage, reason = finding.get("triage"), finding.get("reason")
        basis = finding.get("basis")
        if basis is not None:
            if BASIS_TRIAGE.get(str(basis)) != triage or finding.get("rule") != "email-address":
                raise ScanRefusedError(f"{corpus_id}: a release-scan finding names a clearing basis it does not fit "
                                       "(D-810)", code="release.refused.scan_basis")
            by_basis[str(basis)] = by_basis.get(str(basis), 0) + 1
            if basis != "reserved" and not (spec_sha256 is not None and isinstance(personas, Mapping)
                                           and personas.get("spec_sha256") == spec_sha256):
                raise ScanRefusedError(f"{corpus_id}: a release-scan finding is cleared by a persona list that is not the "
                                       "one this corpus sealed in its spec (D-810)", code="release.refused.scan_personas")
        if triage not in TRIAGE_VALUES or not isinstance(reason, str) or not reason.strip():
            untriaged += 1
            continue
        by_triage[str(triage)] = by_triage.get(str(triage), 0) + 1
        if triage == "real" and finding["fingerprint"] not in withheld:
            real += 1
        if triage == PINNED_ACCOUNT and not (finding.get("rule") == "account-path"
                                             and str(finding.get("path", "")).startswith("raw/")):
            misplaced += 1  # only a raw object ships as pinned; a derived record must be redacted (D-604)
    if untriaged:
        raise ScanRefusedError(f"{corpus_id}: {untriaged} release-scan finding(s) are not triaged (G.9.4)",
                               code="release.refused.scan_untriaged")
    if misplaced:
        raise ScanRefusedError(f"{corpus_id}: {misplaced} release-scan finding(s) are triaged pinned-account outside an "
                               "account-path finding in raw/ (D-604 item 7)", code="release.refused.scan_pinned")
    if real:
        raise ScanRefusedError(f"{corpus_id}: {real} release-scan finding(s) are triaged real and not withheld "
                               "(WITHHELD.json; G.9.4, G.9.5)", code="release.refused.scan_real")
    return ScanSummary(corpus_id, root_digest, tuple(sorted((t["name"], t["version"]) for t in tools)), len(findings),
                       by_triage, scan_sha256, by_basis)


def check_withhold_scan(doc: Mapping[str, Any], scan_rules: Iterable[str]) -> int:
    """The number of release-scan findings whose rule a ``[withhold]`` policy names (``scan_rules``) and that are not
    triaged ``false-positive`` (D-236). Such a finding is a candidate withheld value the policy missed; it never passes
    as ``synthetic-benchmark``."""
    names = set(scan_rules)
    return sum(1 for finding in doc.get("findings") or () if isinstance(finding, Mapping)
               and finding.get("rule") in names and finding.get("triage") != "false-positive")


# ================================================================================================ related identifiers
def corpus_related(manifest: Mapping[str, Any], source_tables: Mapping[str, Mapping[str, Any]]) -> list[Related]:
    """Related identifiers recorded in a sealed corpus (never invented, H.10.5): the source's concept DOI
    (``[source].concept_doi`` of the digest-checked profile copy) and its paper's arXiv id, the pinned git origin of each
    snapshot as a commit URL, the DOIs of its alternative origins, the pinned origin of each context tree (D-221: a git
    commit URL or a Zenodo DOI), and arXiv ids in ``licences.attribution``."""
    corpus_id = str(manifest.get("corpus_id"))
    out: set[Related] = set()
    origin_tag = f"corpus {corpus_id}"
    for source in manifest.get("sources") or ():
        table = source_tables.get(str(source.get("source_id"))) or {}
        concept = table.get("concept_doi")
        if isinstance(concept, str) and _DOI.fullmatch(concept):
            out.add(Related("IsDerivedFrom", "DOI", concept, f"{origin_tag}: source profile concept_doi"))
        paper = table.get("paper")
        if isinstance(paper, str):
            for match in _ARXIV.finditer(paper):
                out.add(Related("References", "arXiv", f"arXiv:{match.group(1)}", f"{origin_tag}: source profile paper"))
        for snapshot in source.get("snapshots") or ():
            origin = snapshot.get("origin") or {}
            repo, commit = origin.get("repo"), origin.get("commit")
            if origin.get("kind") == "git" and isinstance(repo, str) and _URL.fullmatch(repo) and isinstance(
                    commit, str) and _COMMIT.fullmatch(commit):
                out.add(Related("IsDerivedFrom", "URL", f"{repo.rstrip('/')}/tree/{commit}",
                                f"{origin_tag}: snapshot {snapshot.get('snapshot_id')} origin"))
            for alt in snapshot.get("alt_origins") or ():
                doi = alt.get("doi") if isinstance(alt, Mapping) else None
                if isinstance(doi, str) and _DOI.fullmatch(doi):
                    out.add(Related("IsDerivedFrom", "DOI", doi,
                                    f"{origin_tag}: snapshot {snapshot.get('snapshot_id')} alternative origin"))
            for context in snapshot.get("context") or ():  # D-221: a context tree's own pinned origin
                corigin = context.get("origin") if isinstance(context, Mapping) else None
                if not isinstance(corigin, Mapping):
                    continue
                what = f"{origin_tag}: snapshot {snapshot.get('snapshot_id')} context {context.get('role')}"
                crepo, ccommit, cdoi = corigin.get("repo"), corigin.get("commit"), corigin.get("doi")
                if corigin.get("kind") == "git" and isinstance(crepo, str) and _URL.fullmatch(crepo) and isinstance(
                        ccommit, str) and _COMMIT.fullmatch(ccommit):
                    out.add(Related("IsDerivedFrom", "URL", f"{crepo.rstrip('/')}/tree/{ccommit}", what))
                elif corigin.get("kind") == "zenodo" and isinstance(cdoi, str) and _DOI.fullmatch(cdoi):
                    out.add(Related("IsDerivedFrom", "DOI", cdoi, what))
    for line in (manifest.get("licences") or {}).get("attribution") or ():
        if isinstance(line, str):
            for match in _ARXIV.finditer(line):
                out.add(Related("References", "arXiv", f"arXiv:{match.group(1)}", f"{origin_tag}: licences.attribution"))
    return sorted(out)


def merge_related(groups: Sequence[Iterable[Related]]) -> list[Related]:
    """One entry per (relation, scheme, identifier); the first origin (sorted) is kept."""
    seen: dict[tuple[str, str, str], Related] = {}
    for item in sorted(r for group in groups for r in group):
        seen.setdefault((item.relation, item.scheme, item.identifier), item)
    return [seen[k] for k in sorted(seen)]
