"""The ``sem``, ``prov`` and ``validation`` stage definitions (H.8.2) and their digest helpers, in one place.

The importer (:mod:`agentprov.adapters.runner.importer`, which records them) and ``derive``/``recompute``
(:mod:`agentprov.corpus.derive`, which compares, resumes and reuses against them) both build them here, so their
``fn_digest`` values are equal by construction (ultrareview pipeline nit; before, two copies were kept equal by a
test). Layer 3: the ``prov`` definition reads the spec and the engine options lazily.

``code_sha256(dirs)`` is ``sha256(JCS([[relpath, sha256(file)], ...]))`` over the ``.py``/``.toml``/``.json``/``.ttl``
files of the ``agentprov`` package directories ``dirs``, minus ``exclude`` prefixes, sorted by relpath, CRLF
normalised to LF (H.2.5, H.8.2(2); the ``expand`` stage's code digest uses the same construction).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path
from typing import Any, Final

from agentprov.io.canonical import jcs_bytes, sha256_hex
from agentprov.stage_scopes import PROV_EXCLUDE, prov_scope, sem_scope, validation_scope
from agentprov.versions import __version__

__all__ = [
    "PACKAGE_ROOT",
    "SemanticsInfo",
    "code_sha256",
    "detail",
    "lockfile_sha256",
    "prov_stage_definition",
    "sem_stage_definition",
    "validation_stage_definition",
    "versions",
    "with_digest",
]

#: the ``agentprov`` package directory the code digests are taken over
PACKAGE_ROOT: Final = Path(__file__).resolve().parent
#: the provenance spec the ``prov`` and ``validation`` stages name (``agentprov.prov.specs.SPEC_ID``, kept literal so
#: this module imports no ``prov`` code at import time)
_SPEC_ID: Final = "agentprov-prov/0.1"


def code_sha256(dirs: Sequence[str], exclude: Sequence[str] = ()) -> str:
    """The code digest of the package directories (or files) ``dirs`` (see the module docstring)."""
    entries: list[list[str]] = []
    for directory in dirs:
        base = PACKAGE_ROOT / directory
        files = [base] if base.is_file() else sorted(p for p in base.rglob("*") if p.is_file())
        for path in files:
            relpath = path.relative_to(PACKAGE_ROOT).as_posix()
            if path.suffix not in (".py", ".toml", ".json", ".ttl") or "__pycache__" in relpath:
                continue
            if any(relpath.startswith(prefix) for prefix in exclude):
                continue
            entries.append([relpath, sha256_hex(path.read_bytes().replace(b"\r\n", b"\n"))])
    return sha256_hex(jcs_bytes(sorted(entries)))


def with_digest(definition: Mapping[str, Any]) -> dict[str, Any]:
    """H.8.2(1): ``fn_digest = sha256(JCS(definition without fn_digest))``."""
    body = {k: v for k, v in definition.items() if k != "fn_digest"}
    return {**body, "fn_digest": "sha256:" + sha256_hex(jcs_bytes(body))}


def versions(*names: str) -> dict[str, str]:
    """The installed versions of distributions ``names`` (``absent`` when not installed)."""
    out: dict[str, str] = {}
    for name in names:
        try:
            out[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            out[name] = "absent"
    return out


def lockfile_sha256() -> str | None:
    """The digest of the core ``uv.lock`` of a source checkout, else ``None`` (an installed package has none)."""
    try:
        return "sha256:" + sha256_hex((PACKAGE_ROOT.parents[1] / "uv.lock").read_bytes())
    except OSError:
        return None


def detail(text: object) -> str:
    """A register ``detail``: generated text, one line, at most 200 characters, no control characters (H.6.2)."""
    cleaned = "".join(c if 0x20 <= ord(c) < 0x7F or ord(c) > 0x9F else " " for c in str(text))
    return cleaned[:200]


@dataclass(frozen=True, slots=True)
class SemanticsInfo:
    """What the ``sem`` stage definition needs of a semantics profile (``adapters.semantics_profiles`` is L4)."""

    ref: str  # "<id>@<version>"
    sha256: str  # hex
    rules: Mapping[str, int]
    family: str  # the adapter family that ships it ("adapters/<family>/semantics")


def sem_stage_definition(profiles: Sequence[SemanticsInfo]) -> dict[str, Any]:
    families = sorted({f"adapters/{p.family}/semantics" for p in profiles})
    return with_digest({
        "stage": "sem", "fn": "semantics", "format": "sem/0.1",
        "profiles": {p.ref: "sha256:" + p.sha256 for p in profiles},
        "rules": {ns: v for p in profiles for ns, v in sorted(p.rules.items())},
        "engine": f"agentprov@{__version__}",
        "engine_code_sha256": "sha256:" + code_sha256(sem_scope(families)),  # D-451
    })  # fmt: skip


def prov_stage_definition() -> dict[str, Any]:
    """The ``prov`` stage definition of ``agentprov-prov/0.1``."""
    from agentprov.prov.engine import ProvOptions
    from agentprov.prov.specs import load_spec

    spec = load_spec()
    return with_digest({
        "stage": "prov", "fn": "provenance", "spec": spec.id,
        "rules": {spec.catalogue_id: spec.catalogue_version},  # D-640: the aprov version is a declared version
        "rules_sha256": "sha256:" + spec.catalogue_sha256,
        "engine": f"agentprov@{__version__}",
        "engine_code_sha256": "sha256:" + code_sha256(prov_scope(), exclude=PROV_EXCLUDE),
        "options": ProvOptions().as_json(),
        "serialisers": versions("prov", "rdflib"),
    })  # fmt: skip


def validation_stage_definition(semantics: Sequence[str], mode: str, *, prov_conformance: bool = True) -> dict[str, Any]:
    """The ``validation`` stage definition. G2c-5: a skipped tier 4 is listed under ``skipped`` (only then), so a
    skipped run is never taken for, or reused as, a full one."""
    tier4 = ["tier4:" + _SPEC_ID]
    return with_digest({
        "stage": "validation", "fn": "validate",
        "checks": ["aer.validator", *(f"tier3:{ref}" for ref in semantics), *(tier4 if prov_conformance else [])],
        **({} if prov_conformance else {"skipped": tier4}),
        "mode": mode,
        "engine": f"agentprov@{__version__}",
        "engine_code_sha256": "sha256:" + code_sha256(validation_scope()),
        "libraries": versions("prov", "rdflib"),
    })  # fmt: skip
