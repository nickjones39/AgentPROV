"""Source profiles: the data a mapper needs about one source part (docs/architecture D.2.5, D.4; layer L4).

A profile is TOML shipped in the package at ``agentprov/adapters/<family>/profiles/<id>.profile.toml``, loaded through
:mod:`importlib.resources` only (never from a corpus or a user path in release mode). Its ``{id, version, sha256}`` is
recorded in every AER header it influenced (``execution.profile``; AD-03 R-3); ``sha256`` is the digest of the file
bytes and ``version`` is a monotonic integer bumped on any byte change (AD-18).

Phase-4 scope: the closed *generic* schema of D.4.2 is checked (required tables, the required ``[profile]`` keys, no
unknown top-level table, no ``[status]``); the ``[family.<ns>]`` part is handed to the family as data. The families'
closed ``family.schema.json`` files arrive with their importers (D.4.1).
"""

from __future__ import annotations

import re
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from types import MappingProxyType
from typing import Any, Final, Literal

from agentprov.errors import ProfileError
from agentprov.io.canonical import sha256_hex

__all__ = ["PROFILE_FORMAT", "SELECT_CODES", "SourceProfile", "load_profile", "load_profile_file", "parse_profile", "profile_families"]

PROFILE_FORMAT: Final = "agentprov-source-profile/0.1"
#: ``withhold``: the withholding policy (HL H.4.5; D-234), validated by ``agentprov.corpus.withhold`` when a corpus is
#: sealed (adapters/ sits below corpus/, so it is not validated here).
_TOP_LEVEL: Final = frozenset({"profile", "source", "licence", "lineage", "import", "family", "withhold"})
_REQUIRED: Final = ("profile", "source", "licence", "lineage")
#: ``via``: a profile whose import is served by another source's profile (D.4.4 ``autodojo-via-rope``) names it here.
_PROFILE_KEYS: Final = frozenset({"id", "version", "format", "source_id", "family", "parts", "title", "evidence", "via"})
#: The closed ``[import]`` table (D.4.2; D.6.12 item 6). ``native`` is the live profiles' native-log table (D.10.4a).
#: ``blobs`` (D-203): globs of files that hold blob payloads AER records reference by digest (``$blob``, C.11.5).
#: ``nested`` (D-382): ``[[import.nested]]`` archives inside an archive input, expanded under raise-only per-pattern limits.
#: ``map_rss_bytes`` (D-931): the memory cap of this source's ``map`` jobs, raise-only (the default map cap up to the
#: worker ceiling), for sources whose documents need more than the default under the host's watchdog margin.
#: ``prov_rss_bytes`` (D-935): the same for the source's ``prov`` and ``validate`` jobs (raise-only from the prov cap).
_IMPORT_KEYS: Final = frozenset({
    "dialect", "mapper", "variants", "rules", "include", "exclude", "layout", "layout_depth", "path_must_agree",
    "context_artefacts", "auxiliary", "opt_in_parts", "variant_labels", "native", "blobs", "limits", "nested",
    "account_path_exempt", "map_rss_bytes", "prov_rss_bytes",
})  # fmt: skip
#: Register codes an ``[import] exclude`` entry may carry (HL H.6.3 ``select.*``; D.2.8 case 4).
SELECT_CODES: Final = frozenset({"select.not_execution_artefact", "select.owned_elsewhere", "select.dialect_planned",
                                 "select.licence_blocked", "select.out_of_scope", "select.redaction_pending"})
_EXCLUDE_KEYS: Final = frozenset({"glob", "code", "owner", "owner_corpus", "note"})
_OPT_IN_KEYS: Final = frozenset({"part", "note"})
#: The closed ``[lineage]`` table: the owner's edges, declared once (D.4.2; HL H.7.3).
_LINEAGE_KEYS: Final = frozenset({"built_on", "vendored", "duplicates", "cited_by", "content_dedup", "owns", "excludes"})
_DUPLICATE_KEYS: Final = frozenset({"of", "part", "path", "relation", "owner"})
_RELATIONS: Final = frozenset({"byte_identical", "replicate", "mirror", "derived_conversion"})
_OWNER: Final = re.compile(r"(ext:)?[a-z][a-z0-9_-]*")


@dataclass(frozen=True, slots=True)
class SourceProfile:
    """A loaded, schema-checked source profile (immutable)."""

    id: str
    version: int
    sha256: str
    family: str
    source_id: str
    parts: tuple[str, ...]
    data: Mapping[str, Any] = field(repr=False)

    def header(self) -> dict[str, Any]:
        """The ``execution.profile`` member: ``{id, version, sha256}``."""
        return {"id": self.id, "sha256": self.sha256, "version": self.version}

    def family_table(self) -> Mapping[str, Any]:
        """The ``[family.<family>]`` table (empty when absent)."""
        family = self.data.get("family", {})
        table = family.get(self.family, {}) if isinstance(family, Mapping) else {}
        return table if isinstance(table, Mapping) else {}


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({k: _freeze(v) for k, v in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(v) for v in value)
    return value


def parse_profile(data: bytes, *, source: str = "<bytes>") -> SourceProfile:
    """Parse and check a profile's generic schema (D.4.2). :class:`~agentprov.errors.ProfileError` on any defect."""
    try:
        doc = tomllib.loads(data.decode("utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as exc:
        raise ProfileError(f"{source}: not valid TOML/UTF-8") from exc
    unknown = sorted(set(doc) - _TOP_LEVEL)
    if unknown:
        raise ProfileError(f"{source}: unknown top-level table(s) {unknown} (the registry is the only status store)")
    for table in _REQUIRED:
        if not isinstance(doc.get(table), dict):
            raise ProfileError(f"{source}: missing [{table}] table")
    head = doc["profile"]
    extra = sorted(set(head) - _PROFILE_KEYS)
    if extra:
        raise ProfileError(f"{source}: unknown [profile] key(s) {extra}")
    pid, version, fmt = head.get("id"), head.get("version"), head.get("format")
    family, source_id, parts = head.get("family"), head.get("source_id"), head.get("parts", [])
    if not isinstance(pid, str) or not pid:
        raise ProfileError(f"{source}: [profile] id must be a non-empty string")
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        raise ProfileError(f"{source}: [profile] version must be a positive integer (AD-18)")
    if fmt != PROFILE_FORMAT:
        raise ProfileError(f"{source}: [profile] format must be {PROFILE_FORMAT!r}")
    if not isinstance(family, str) or not isinstance(source_id, str):
        raise ProfileError(f"{source}: [profile] family and source_id must be strings")
    if not isinstance(parts, list) or not all(isinstance(p, str) for p in parts):
        raise ProfileError(f"{source}: [profile] parts must be an array of strings")
    fam = doc.get("family", {})
    if not isinstance(fam, dict) or not set(fam) <= {family}:
        raise ProfileError(f"{source}: [family.<ns>] tables other than [family.{family}] are not allowed")
    if "via" in head and (not isinstance(head["via"], str) or "import" in doc):
        raise ProfileError(f"{source}: [profile] via names the serving profile; such a profile has no [import] table")
    if "import" in doc:
        _check_import(doc["import"], source, parts)
    _check_lineage(doc["lineage"], source)
    return SourceProfile(
        id=pid,
        version=version,
        sha256=sha256_hex(data),
        family=family,
        source_id=source_id,
        parts=tuple(parts),
        data=_freeze(doc),
    )


def _strings(value: object) -> bool:
    return isinstance(value, list) and all(isinstance(v, str) and v for v in value)


def _check_import(imp: object, source: str, parts: list[str]) -> None:
    """The closed ``[import]`` table (D.4.2; D.6.12 item 6). ``parts`` are the profile's own parts (``[profile] parts``)."""
    if not isinstance(imp, dict):
        raise ProfileError(f"{source}: [import] must be a table")
    unknown = sorted(set(imp) - _IMPORT_KEYS)
    if unknown:
        raise ProfileError(f"{source}: unknown [import] key(s) {unknown}")
    for key in ("variants", "include", "path_must_agree", "context_artefacts", "blobs"):
        if key in imp and not _strings(imp[key]):
            raise ProfileError(f"{source}: [import] {key} must be an array of non-empty strings")
    if "map_rss_bytes" in imp:  # D-931: a raise-only memory cap for this source's map jobs, up to the worker ceiling
        from agentprov.io.workers import RSS_CAP_CEILING, WorkerLimits

        cap, floor = imp["map_rss_bytes"], WorkerLimits().for_kind("map").rss_bytes
        if not isinstance(cap, int) or isinstance(cap, bool) or not floor <= cap <= RSS_CAP_CEILING:
            raise ProfileError(f"{source}: [import] map_rss_bytes must be an integer in [{floor}, {RSS_CAP_CEILING}]")
    if "prov_rss_bytes" in imp:  # D-935: the prov and validate jobs' cap (tier 4 of a large PROV document)
        from agentprov.io.workers import RSS_CAP_CEILING, WorkerLimits

        cap, floor = imp["prov_rss_bytes"], WorkerLimits().for_kind("prov").rss_bytes
        if not isinstance(cap, int) or isinstance(cap, bool) or not floor <= cap <= RSS_CAP_CEILING:
            raise ProfileError(f"{source}: [import] prov_rss_bytes must be an integer in [{floor}, {RSS_CAP_CEILING}]")
    if "limits" in imp:  # D-323 (RB-2): the allowlist and ceilings live in agentprov.ingest.profile_limits
        from agentprov.ingest.profile_limits import check_profile_limits

        try:
            check_profile_limits(imp["limits"])
        except ValueError as exc:
            raise ProfileError(f"{source}: {exc}") from None
    for entry in imp.get("exclude", ()):
        if not isinstance(entry, dict) or not set(entry) <= _EXCLUDE_KEYS or not isinstance(entry.get("glob"), str):
            raise ProfileError(f"{source}: an [import] exclude entry is {{glob, code, owner?, owner_corpus?, note?}}")
        if entry.get("code") not in SELECT_CODES:
            raise ProfileError(f"{source}: exclude {entry['glob']!r}: code must be one of {sorted(SELECT_CODES)}")
        owned = entry["code"] == "select.owned_elsewhere"
        if owned != ("owner" in entry) or ("owner_corpus" in entry and not owned):
            raise ProfileError(f"{source}: exclude {entry['glob']!r}: an owner goes with select.owned_elsewhere, and only there")
        if owned and (not isinstance(entry["owner"], str) or _OWNER.fullmatch(entry["owner"]) is None):
            raise ProfileError(f"{source}: exclude {entry['glob']!r}: owner is a source id or ext:<name>")
    for entry in imp.get("opt_in_parts", ()):
        if not isinstance(entry, dict) or set(entry) - _OPT_IN_KEYS or not isinstance(entry.get("part"), str):
            raise ProfileError(f"{source}: an [import] opt_in_parts entry is {{part, note?}}")
    if "nested" in imp:
        # D-382: validated here (keys, ids, under chains, patterns, raise-only values under the fixed ceilings of
        # ingest/limits.py, depth allowance per level) by the same builder the importer uses
        from agentprov.raw.members import MembersError, nested_selection

        if not isinstance(imp["nested"], list) or not imp["nested"]:
            raise ProfileError(f"{source}: [import] nested is a non-empty array of tables")
        try:
            nested_selection((), imp["nested"])
        except MembersError as exc:
            raise ProfileError(f"{source}: {exc}") from None
    labels = imp.get("variant_labels", {})
    if not isinstance(labels, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in labels.items()):
        raise ProfileError(f"{source}: [import] variant_labels maps a variant to a part label")
    # D-480: a variant the profile does not declare may be labelled only with a part the profile does not import itself
    # (the entry records the other part, served by another import, that the variant belongs to); the same for every family
    if "variants" in imp and any(labels[v] in parts for v in set(labels) - set(imp["variants"])):
        raise ProfileError(f"{source}: [import] variant_labels gives a variant the profile does not declare one of its own parts")


def _check_lineage(lineage: object, source: str) -> None:
    """The closed ``[lineage]`` table (D.4.2): the owner's edges."""
    if not isinstance(lineage, dict):
        raise ProfileError(f"{source}: [lineage] must be a table")
    unknown = sorted(set(lineage) - _LINEAGE_KEYS)
    if unknown:
        raise ProfileError(f"{source}: unknown [lineage] key(s) {unknown}")
    for entry in lineage.get("duplicates", ()):
        if not isinstance(entry, dict) or set(entry) - _DUPLICATE_KEYS or not {"of", "path", "relation", "owner"} <= set(entry):
            raise ProfileError(f"{source}: a [lineage] duplicates entry is {{of, part?, path, relation, owner}}")
        if entry["relation"] not in _RELATIONS:
            raise ProfileError(f"{source}: [lineage] duplicates relation must be one of {sorted(_RELATIONS)}")
    if lineage.get("content_dedup", "never") != "never":
        raise ProfileError(f"{source}: [lineage] content_dedup is 'never' in v0.1 (AD-10 row 7)")


def profile_families() -> tuple[str, ...]:
    """The adapter families that ship a ``profiles/`` directory, sorted (D.1.1). Found as package data, so no adapter
    module is imported and a new family needs no core entry (DoD Q.3)."""
    root = resources.files("agentprov").joinpath("adapters")
    return tuple(sorted(
        child.name for child in root.iterdir()
        if child.is_dir() and not child.name.startswith(("_", ".")) and child.joinpath("profiles").is_dir()
    ))


def load_profile(profile_id: str, version: int | None = None) -> SourceProfile:
    """Load profile ``profile_id`` from package resources only (D.2.5).

    ``version`` selects an integer version: the current file if it has that version, else the archived file
    ``profiles/archive/<id>.profile.v<version>.toml`` (D-31: a bumped profile keeps its earlier versions, so a corpus
    recorded with one stays recomputable). ``None`` means the current one."""
    if not profile_id or "/" in profile_id or "\\" in profile_id or profile_id.startswith("."):
        raise ProfileError("a profile id is a bare name")
    if version is not None and (isinstance(version, bool) or not isinstance(version, int) or version < 1):
        raise ProfileError(f"profile {profile_id!r}: not an integer version: {version!r}")
    found = [
        family for family in profile_families()
        if resources.files("agentprov").joinpath("adapters", family, "profiles", f"{profile_id}.profile.toml").is_file()
    ]
    if len(found) > 1:
        raise ProfileError(f"profile {profile_id!r} is shipped by more than one family: {', '.join(found)}")
    for family in found:
        root = resources.files("agentprov").joinpath("adapters", family, "profiles")
        candidates = [(root.joinpath(f"{profile_id}.profile.toml"), f"profiles/{profile_id}")]
        if version is not None:
            name = f"{profile_id}.profile.v{version}.toml"
            candidates.append((root.joinpath("archive", name), f"profiles/archive/{name}"))
        for node, label in candidates:
            if not node.is_file():
                continue
            profile = parse_profile(node.read_bytes(), source=f"agentprov.adapters.{family}:{label}")
            if profile.id != profile_id or profile.family != family:
                raise ProfileError(f"profile {profile_id!r}: id or family does not match its location")
            if version is None or profile.version == version:
                return profile
        raise ProfileError(f"profile {profile_id!r} version {version} is not shipped")
    raise ProfileError(f"no profile {profile_id!r} is shipped in the package")


def load_profile_file(path: Path, *, mode: Literal["dev"]) -> SourceProfile:
    """Development only: a profile from a file (refused in release mode, D.2.5)."""
    if mode != "dev":
        raise ProfileError("profile files are accepted in dev mode only")
    return parse_profile(Path(path).read_bytes(), source=str(path))


def worker_caps(profile: SourceProfile) -> dict[str, int]:
    """The worker memory caps ``profile`` raises, by job kind (D-931 ``map``; D-935 ``prov`` and ``validate``)."""
    imp = profile.data.get("import", {})
    caps: dict[str, int] = {}
    if isinstance(imp.get("map_rss_bytes"), int):
        caps["map"] = int(imp["map_rss_bytes"])
    if isinstance(imp.get("prov_rss_bytes"), int):
        caps["prov"] = caps["validate"] = int(imp["prov_rss_bytes"])
    return caps
