"""Semantics-profile references and digests (C.14.1; D.1 "Semantics profile"; C.20(2)).

A semantics profile ``<id>`` at integer ``<version>`` is shipped by exactly one adapter family as package data:

    agentprov/adapters/<family>/semantics/<id>-<version>/      # data files (TOML tables, schemas, …)
    agentprov/adapters/<family>/semantics/__init__.py           # build_profile(profile_id, version, files, sha256)

Discovery and loading (:func:`agentprov.adapters.semantics_profiles.load_semantics_profile`) live in the adapters layer
(L4): it imports ``agentprov.adapters.<family>.semantics``, which ``sem`` and ``prov`` (L2) must not do (MN M.5.1).
Callers hand profile objects down to the SEM engine and to ``derive``. There is no core name table, so a new
family's profile needs no core change (invariant 5; DoD Q.3).

The profile digest is computed here, over the data files only, so every family digests the same way::

    sha256( JCS( { "<relative path>": "<hex sha256 of the file bytes>", … } ) )

Code changes of a profile are covered by its integer version (AD-18) and by the engine code digest that
``derivation.json`` records (H.8.2).
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Final

from agentprov.errors import AgentProvError
from agentprov.io.canonical import sha256_hex

__all__ = [
    "SemanticsProfileError",
    "parse_profile_ref",
    "profile_digest",
]

_REF_RE: Final = re.compile(r"(?P<id>[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*)@(?P<version>[1-9][0-9]*)")


class SemanticsProfileError(AgentProvError):
    """A semantics profile is not shipped, is shipped twice, or does not match its directory."""

    code = "sem.profile_unavailable"
    exit_code = 1


def parse_profile_ref(ref: str) -> tuple[str, int]:
    """``"agentdojo.suites@1"`` → ``("agentdojo.suites", 1)``."""
    match = _REF_RE.fullmatch(ref)
    if match is None:
        raise SemanticsProfileError(f"not a semantics profile reference: {ref!r}")
    return match["id"], int(match["version"])


def profile_digest(files: Mapping[str, bytes]) -> str:
    """The profile digest over its data files (module docstring)."""
    from agentprov.aer.canon import dumps_line

    listing = {name: sha256_hex(data) for name, data in sorted(files.items())}
    return sha256_hex(dumps_line(listing)[:-1])
