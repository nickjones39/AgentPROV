"""Catalogue authority (AD-14): a corpus's recorded rule catalogues and profiles compared with the installed package.

The package is the authority; a corpus ``rules/`` copy is a record that is digest-compared, never loaded (H.5.5, H.10.3(3),
G.5.7). Two findings (H.6.3, both reported in the command summary and never written into a sealed corpus):

* ``rules.mismatch``: the recorded digest, or the corpus ``rules/`` copy, differs from the package resource at the
  recorded version;
* ``rules.unavailable``: the installed package does not ship the recorded version;
* ``aer.rules.drift`` (D-460): the AER stage records a catalogue at a version the package ships, but with other bytes. The
  corpus was imported while that catalogue was edited in place (between ``afe7038`` and the D-31 bumps), so its AERs cite
  rules the shipped version may lack; it is checked at the commit that built it, not here (D-430).

:func:`check_sealed_rules` reads a **sealed** manifest (``rule_catalogues``, ``profiles.source``, ``profiles.semantics``
with their ``rules/`` paths); :func:`check_stage_rules` reads the digests ``derivation.json`` records (``aer``: ``rules``,
``rules_sha256``, ``profile``, ``profile_sha256``; ``sem``: ``profiles``; ``prov``: ``rules_sha256``), which a working
corpus has too. Neither writes anything.

The lookups that read adapter package data are injected as :class:`PackageResources` (M.5.2(1));
:func:`package_resources` builds the default from ``agentprov.adapters.profiles`` and
``agentprov.adapters.semantics_profiles`` (L4, below this L5 module).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from importlib import resources
from typing import Any, Final

from agentprov.aer.rules import load_catalogue
from agentprov.errors import AgentProvError
from agentprov.io.canonical import sha256_hex

__all__ = [
    "DRIFT",
    "MISMATCH",
    "UNAVAILABLE",
    "PackageResources",
    "RuleFinding",
    "check_sealed_rules",
    "catalogue_drift",
    "check_stage_rules",
    "package_resources",
    "semantics_label",
]

MISMATCH: Final = "rules.mismatch"
UNAVAILABLE: Final = "rules.unavailable"
DRIFT: Final = "aer.rules.drift"
#: D-460: the guidance every ``aer.rules.drift`` finding carries.
DRIFT_DETAIL: Final = "built against catalogue bytes that differ from the shipped v{version}; check at the building commit"
#: The id under which the sealed manifest records the PROV spec catalogue (corpus/package.py).
PROV_CATALOGUE_ID: Final = "aprov"


@dataclass(frozen=True, slots=True)
class RuleFinding:
    """One authority finding: ``code`` (``rules.mismatch`` / ``rules.unavailable``), the corpus path or catalogue it
    concerns (generated text, never corpus content) and a generated detail."""

    code: str
    subject: str
    detail: str


@dataclass(frozen=True)
class PackageResources:
    """Package lookups (injected; ``None`` from a lookup means "not shipped at that version").

    * ``source_profile(id, version)``: ``(sha256 hex, the profile's [source] table)`` (its pins, canonical repository);
    * ``semantics(ref)``: ``(sha256 hex, {file name: bytes})`` of the semantics profile ``<id>@<version>``.
    """

    source_profile: Callable[[str, int], tuple[str, Mapping[str, Any]] | None]
    semantics: Callable[[str], tuple[str, Mapping[str, bytes]] | None]


def package_resources() -> PackageResources:
    """The default lookups over the installed package (``agentprov.adapters`` package data only, AD-14)."""
    from agentprov.adapters.profiles import load_profile
    from agentprov.adapters.semantics_profiles import semantics_families
    from agentprov.sem.profiles import parse_profile_ref, profile_digest
    from agentprov.sem.types import sem_profile_dir

    def source_profile(profile_id: str, version: int) -> tuple[str, Mapping[str, Any]] | None:
        try:
            profile = load_profile(profile_id, version)  # an archived version too (D-31)
        except AgentProvError:
            return None
        if profile.version != version:
            return None
        source = profile.data.get("source")
        return profile.sha256, dict(source) if isinstance(source, Mapping) else {}

    def semantics(ref: str) -> tuple[str, Mapping[str, bytes]] | None:
        try:
            profile_id, version = parse_profile_ref(ref)
        except (AgentProvError, ValueError):
            return None
        root = resources.files("agentprov").joinpath("adapters")
        dirname = sem_profile_dir(profile_id, version)
        found = [f for f in semantics_families() if root.joinpath(f, "semantics", dirname).is_dir()]
        if len(found) != 1:
            return None
        files: dict[str, bytes] = {}
        stack = [(root.joinpath(found[0], "semantics", dirname), "")]
        while stack:
            node, prefix = stack.pop()
            for child in sorted(node.iterdir(), key=lambda c: c.name):
                if child.name.startswith((".", "_")):
                    continue
                if child.is_dir():
                    stack.append((child, f"{prefix}{child.name}/"))
                elif child.is_file():
                    files[f"{prefix}{child.name}"] = child.read_bytes()
        return profile_digest(files), files

    return PackageResources(source_profile=source_profile, semantics=semantics)


def semantics_label(profile_id: str, version: int, name: str) -> str:
    """The ``rules/`` label of one semantics profile file, as sealing writes it (corpus/package.py)."""
    return f"rules/{profile_id}-{version}.{name[: -len('.toml')].replace('/', '.')}.profile.toml"


def _catalogue_digest(namespace: str, version: int) -> str | None:
    if namespace == PROV_CATALOGUE_ID:
        from agentprov.prov.specs import load_spec

        from agentprov.prov.specs import archived_catalogue_sha256

        spec = load_spec()
        # an older aprov version is answered from its byte-exact archive (D-621, D-31: stored corpora record v1)
        return spec.catalogue_sha256 if spec.catalogue_version == version else archived_catalogue_sha256(version)
    try:
        return load_catalogue(namespace, version).digest
    except AgentProvError:
        return None


def prov_catalogue_version(stage: Mapping[str, Any] | None) -> int | None:
    """The ``aprov`` catalogue version a ``prov`` stage definition was built under (D-621 sibling): its recorded
    ``rules: {aprov: n}``, else the version whose bytes have the recorded ``rules_sha256`` (the current catalogue or a
    byte-exact archive; a digest identifies one version). ``None`` when neither says (unknown bytes)."""
    if not isinstance(stage, Mapping):
        return None
    rules = stage.get("rules")
    if isinstance(rules, Mapping):
        n = rules.get(PROV_CATALOGUE_ID)
        if isinstance(n, int) and not isinstance(n, bool):
            return n
    digest = _ref(stage.get("rules_sha256"))
    if digest is None:
        return None
    from agentprov.prov.specs import archived_catalogue_sha256, load_spec

    spec = load_spec()
    if digest == spec.catalogue_sha256:
        return spec.catalogue_version
    for n in range(spec.catalogue_version - 1, 0, -1):
        if archived_catalogue_sha256(n) == digest:
            return n
    return None


def prov_catalogue_ok(stage: Mapping[str, Any]) -> bool:
    """The ``prov`` stage's recorded ``rules_sha256`` is the shipped bytes of the version it was built under (current or
    archived); a stage without ``rules_sha256`` records nothing to compare."""
    recorded = _ref(stage.get("rules_sha256"))
    if recorded is None:
        return True
    version = prov_catalogue_version(stage)
    return version is not None and _catalogue_digest(PROV_CATALOGUE_ID, version) == recorded


def _ref(value: object) -> str | None:
    return value[len("sha256:"):] if isinstance(value, str) and value.startswith("sha256:") else None


def check_sealed_rules(
    manifest: Mapping[str, Any],
    read: Callable[[str], bytes | None],
    package: PackageResources,
) -> list[RuleFinding]:
    """Compare a sealed manifest's catalogues and profiles, and the ``rules/`` copies it names, with the package.

    ``read(label)`` returns the bytes of a corpus file, or ``None`` when it is absent (an absent copy is a mismatch: the
    manifest names it)."""
    out: list[RuleFinding] = []

    def compare(subject: str, recorded: object, expected: str | None, path: str | None) -> None:
        if expected is None:
            out.append(RuleFinding(UNAVAILABLE, subject, "the installed package does not ship the recorded version"))
            return
        if _ref(recorded) != expected:
            out.append(RuleFinding(MISMATCH, subject, "the recorded digest differs from the package resource"))
        if path is not None:
            data = read(path)
            if data is None:
                out.append(RuleFinding(MISMATCH, path, "the rules/ copy the manifest names is absent"))
            elif sha256_hex(data) != expected:
                out.append(RuleFinding(MISMATCH, path, "the rules/ copy differs from the package resource"))

    for entry in manifest.get("rule_catalogues") or ():
        if not isinstance(entry, Mapping):
            continue
        ns, version = str(entry.get("id")), entry.get("version")
        expected = _catalogue_digest(ns, version) if isinstance(version, int) else None
        compare(f"catalogue {ns}@{version}", entry.get("sha256"), expected, str(entry.get("path")) if entry.get("path") else None)
    profiles = manifest.get("profiles")
    profiles = profiles if isinstance(profiles, Mapping) else {}
    for entry in profiles.get("source") or ():
        if not isinstance(entry, Mapping):
            continue
        pid, version = str(entry.get("id")), entry.get("version")
        profile = package.source_profile(pid, version) if isinstance(version, int) else None
        compare(f"source profile {pid}@{version}", entry.get("sha256"), None if profile is None else profile[0],
                str(entry.get("path")) if entry.get("path") else None)
    for entry in profiles.get("semantics") or ():
        if not isinstance(entry, Mapping):
            continue
        pid, version = str(entry.get("id")), entry.get("version")
        subject = f"semantics profile {pid}@{version}"
        semantics = package.semantics(f"{pid}@{version}") if isinstance(version, int) else None
        if semantics is None or not isinstance(version, int):
            out.append(RuleFinding(UNAVAILABLE, subject, "the installed package does not ship the recorded version"))
            continue
        digest, files = semantics
        if _ref(entry.get("sha256")) != digest:
            out.append(RuleFinding(MISMATCH, subject, "the recorded digest differs from the package resource"))
        expected_files = {semantics_label(pid, version, name): data for name, data in files.items()}
        recorded_paths = sorted(str(p) for p in entry.get("paths") or ())
        if recorded_paths != sorted(expected_files):
            out.append(RuleFinding(MISMATCH, subject, "the rules/ copies the manifest names differ from the package files"))
        for label in recorded_paths:
            data = read(label)
            if data is None:
                out.append(RuleFinding(MISMATCH, label, "the rules/ copy the manifest names is absent"))
            elif label in expected_files and data != expected_files[label]:
                out.append(RuleFinding(MISMATCH, label, "the rules/ copy differs from the package resource"))
    return sorted(out, key=lambda f: (f.subject, f.code))


def catalogue_drift(stages: Mapping[Any, Mapping[str, Any]]) -> dict[str, int]:
    """The ``aer`` stage catalogues recorded at a version the package ships but with other bytes (D-460), ``{ns: version}``.

    Only a recorded digest that differs counts: a catalogue the package does not ship at that version is
    ``rules.unavailable``, and a stage without ``rules_sha256`` records nothing to compare."""
    aer = stages.get("aer")
    if aer is None:
        return {}
    rules_sha256 = aer.get("rules_sha256")
    recorded: Mapping[str, Any] = rules_sha256 if isinstance(rules_sha256, Mapping) else {}
    out: dict[str, int] = {}
    for ns, version in sorted(dict(aer.get("rules") or {}).items()):
        if not isinstance(version, int) or isinstance(version, bool) or recorded.get(ns) is None:
            continue
        digest = _catalogue_digest(str(ns), version)
        if digest is not None and recorded.get(ns) != "sha256:" + digest:
            out[str(ns)] = version
    return out


def check_stage_rules(stages: Mapping[Any, Mapping[str, Any]], package: PackageResources) -> list[RuleFinding]:
    """Compare the catalogue and profile digests ``derivation.json`` records with the package (the same comparison
    ``recompute`` makes before it derives; HL-T15)."""
    out: list[RuleFinding] = []
    aer = stages.get("aer")
    if aer is not None:
        rules_sha256 = aer.get("rules_sha256")
        recorded: Mapping[str, Any] = rules_sha256 if isinstance(rules_sha256, Mapping) else {}
        for ns, version in sorted(dict(aer.get("rules") or {}).items()):
            subject = f"catalogue {ns}@{version}"
            digest = _catalogue_digest(str(ns), int(version)) if isinstance(version, int) else None
            if digest is None:
                out.append(RuleFinding(UNAVAILABLE, subject, "the installed package does not ship the recorded version"))
            elif recorded.get(ns) not in (None, "sha256:" + digest):
                out.append(RuleFinding(DRIFT, subject, DRIFT_DETAIL.format(version=version)))
        profile = aer.get("profile")
        if isinstance(profile, str) and "@" in profile:
            pid, _, number = profile.rpartition("@")
            found = package.source_profile(pid, int(number)) if number.isdigit() else None
            if found is None:
                out.append(RuleFinding(UNAVAILABLE, f"source profile {profile}", "the installed package does not ship the "
                                       "recorded version"))
            elif aer.get("profile_sha256") not in (None, "sha256:" + found[0]):
                out.append(RuleFinding(MISMATCH, f"source profile {profile}", "the digest derivation.json records differs "
                                       "from the package's"))
    sem = stages.get("sem")
    if sem is not None:
        for ref, digest in sorted(dict(sem.get("profiles") or {}).items()):
            semantics = package.semantics(str(ref))
            if semantics is None:
                out.append(RuleFinding(UNAVAILABLE, f"semantics profile {ref}", "the installed package does not ship the "
                                       "recorded version"))
            elif digest != "sha256:" + semantics[0]:
                out.append(RuleFinding(MISMATCH, f"semantics profile {ref}", "the digest derivation.json records differs "
                                       "from the package's"))
    prov = stages.get("prov")
    if prov is not None and not prov_catalogue_ok(prov):  # an archived older version is verifiable (D-621 sibling)
        out.append(RuleFinding(MISMATCH, f"catalogue {PROV_CATALOGUE_ID}", "the PROV spec catalogue digest "
                               "derivation.json records is not the package's at the recorded version"))
    return sorted(set(out), key=lambda f: (f.subject, f.code))
