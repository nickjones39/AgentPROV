"""Discovery of semantics profiles by convention (C.14.1; D.1 "Semantics profile"; C.20(2)); adapters layer (L4).

A semantics profile ``<id>`` at integer ``<version>`` is shipped by exactly one adapter family as package data:

    agentprov/adapters/<family>/semantics/<id>-<version>/      # data files (TOML tables, schemas, …)
    agentprov/adapters/<family>/semantics/__init__.py           # build_profile(profile_id, version, files, sha256)

The directory is found without importing any family; then ``agentprov.adapters.<family>.semantics`` is imported and
its ``build_profile`` called. There is no core name table, so a new family's profile needs no core change (invariant 5;
DoD Q.3). This module lives in the adapters layer because it imports families: ``sem`` and ``prov`` (L2) receive
profile objects from their callers (MN M.5.1). Release mode loads profiles only from package resources, never from a
corpus copy (AD-14). The digest is :func:`agentprov.sem.profiles.profile_digest` over the data files.
"""

from __future__ import annotations

import importlib
import re
from importlib import resources
from importlib.resources.abc import Traversable
from typing import Final

from agentprov.sem.profiles import SemanticsProfileError, profile_digest
from agentprov.sem.types import SemanticsProfile, sem_profile_dir

__all__ = ["load_all_semantics_profiles", "load_semantics_profile", "semantics_families"]

_ID_RE: Final = re.compile(r"[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*")
_DIR_RE: Final = re.compile(r"(?P<id>[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*)-(?P<version>[1-9][0-9]*)")
_MAX_FILES: Final = 256


def semantics_families() -> tuple[str, ...]:
    """The adapter families that ship a ``semantics/`` directory, sorted. Found as package data (no import)."""
    root = resources.files("agentprov").joinpath("adapters")
    return tuple(sorted(
        child.name for child in root.iterdir()
        if child.is_dir() and not child.name.startswith(("_", ".")) and child.joinpath("semantics").is_dir()
    ))


def _collect(node: Traversable, prefix: str, out: dict[str, bytes]) -> None:
    for child in sorted(node.iterdir(), key=lambda c: c.name):
        if child.name.startswith((".", "_")):
            continue
        name = f"{prefix}{child.name}"
        if child.is_dir():
            _collect(child, f"{name}/", out)
        elif child.is_file():
            if len(out) >= _MAX_FILES:
                raise SemanticsProfileError(f"semantics profile directory holds more than {_MAX_FILES} files")
            out[name] = child.read_bytes()


def load_semantics_profile(profile_id: str, version: int) -> SemanticsProfile:
    """Load ``profile_id`` at ``version`` from package resources only.

    :class:`SemanticsProfileError` when no family, or more than one, ships ``semantics/<id>-<version>/``, or when the
    family's ``build_profile`` returns a profile whose id, version or digest differ from the directory's.
    """
    if _ID_RE.fullmatch(profile_id) is None or isinstance(version, bool) or not isinstance(version, int) or version < 1:
        raise SemanticsProfileError(f"not a semantics profile id and version: {profile_id!r}@{version!r}")
    dirname = sem_profile_dir(profile_id, version)
    root = resources.files("agentprov").joinpath("adapters")
    found = [
        family for family in semantics_families()
        if root.joinpath(family, "semantics", dirname).is_dir()
    ]
    if not found:
        raise SemanticsProfileError(f"semantics profile {profile_id}@{version} is not shipped")
    if len(found) > 1:
        raise SemanticsProfileError(f"semantics profile {profile_id}@{version} is shipped by {found}")
    family = found[0]
    files: dict[str, bytes] = {}
    _collect(root.joinpath(family, "semantics", dirname), "", files)
    digest = profile_digest(files)
    module = importlib.import_module(f"agentprov.adapters.{family}.semantics")
    build = getattr(module, "build_profile", None)
    if build is None:
        raise SemanticsProfileError(f"agentprov.adapters.{family}.semantics has no build_profile()")
    profile = build(profile_id, version, files, digest)
    if (profile.id, profile.version, profile.sha256) != (profile_id, version, digest):
        raise SemanticsProfileError(f"{family}.semantics built {profile.id}@{profile.version} for {dirname}")
    return profile


def load_all_semantics_profiles() -> dict[str, SemanticsProfile]:
    """Every shipped profile, keyed ``<id>@<version>`` (a T1 worker loads them before its audit hook, G.4.4)."""
    root = resources.files("agentprov").joinpath("adapters")
    out: dict[str, SemanticsProfile] = {}
    for family in semantics_families():
        for child in sorted(root.joinpath(family, "semantics").iterdir(), key=lambda c: c.name):
            match = _DIR_RE.fullmatch(child.name)
            if child.is_dir() and match is not None:
                out[f"{match['id']}@{match['version']}"] = load_semantics_profile(match["id"], int(match["version"]))
    return dict(sorted(out.items()))
