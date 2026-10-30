"""The code each derivation stage runs, as the scope of its ``engine_code_sha256`` (D-451; HL H.8.2(2); DECISIONS D-30).

H.8.2(2) records, per stage, the digest of "the agentprov modules of that stage", and a stage output is reused (D-30)
only while that digest is unchanged. A fixed directory list missed the modules the stage code imports from elsewhere
(``adapters/agentdojo/citation.py`` decides derived versus inferred citations in ``agentdojo.suites``; ``aer/reader.py``
and ``aer/evidence.py`` feed the PROV engine), so a behaviour edit there was carried as "identical" by ``recompute
--out`` (bug pass BF-33). Each scope is now the stage's seed directories plus every file of the transitive
``agentprov`` import closure of those seeds that lies outside them, pinned below; ``tests/unit/test_stage_scopes.py``
recomputes the closures from the source (ast) and fails when one grows or a pinned file is no longer reached.

Data only (layer 0): :mod:`agentprov.corpus.derive` and :mod:`agentprov.adapters.runner.importer` read their scopes
from here, so the two stay equal by construction. The paths are relative to the ``agentprov`` package directory.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from types import MappingProxyType
from typing import Final

__all__ = ["PROV_EXCLUDE", "aer_scope", "prov_scope", "sem_scope", "validation_scope"]

#: Seeds of the three reused stages (the directory lists before D-451).
SEM_SEEDS: Final = ("sem", "adapters/semantics_profiles.py")
PROV_SEEDS: Final = ("prov", "vocab")
PROV_EXCLUDE: Final = ("prov/compat/",)  # the frozen compat oracle is its own stage
VALIDATION_SEEDS: Final = ("validate", "aer/validate.py", "aer/accounting.py", "sem/validate.py")
#: The ``aer`` stage (D-451 addendum, BF-39): both directories are hashed, but imports are followed only from the map
#: path (``job_map``, ``map_unit``, ``seal_outcome``) and ``aer/``. ``importer.py``, ``session.py``, ``live.py`` and
#: ``provjob.py`` orchestrate the later stages, whose code has its own digests.
AER_SEEDS: Final = ("adapters/runner", "aer")
AER_FOLLOW: Final = ("adapters/runner/__init__.py", "aer")

# ---------------------------------------------------------------------------------------- pinned closures (generated)
SEM_CLOSURE: Final[tuple[str, ...]] = (
    "aer/__init__.py",
    "aer/_structure.py",
    "aer/accounting.py",
    "aer/canon.py",
    "aer/evidence.py",
    "aer/ids.py",
    "aer/locators.py",
    "aer/reader.py",
    "aer/rules.py",
    "aer/types.py",
    "aer/validate.py",
    "errors.py",
    "ingest/limits.py",
    "ingest/loaders.py",
    "io/canonical.py",
    "io/jsonschema_subset.py",
)

PROV_CLOSURE: Final[tuple[str, ...]] = (
    "aer/__init__.py",
    "aer/_structure.py",
    "aer/accounting.py",
    "aer/canon.py",
    "aer/evidence.py",
    "aer/ids.py",
    "aer/locators.py",
    "aer/reader.py",
    "aer/rules.py",
    "aer/types.py",
    "aer/validate.py",
    "envinfo.py",
    "errors.py",
    "ingest/__init__.py",
    "ingest/archives.py",
    "ingest/jsonstream.py",
    "ingest/limits.py",
    "ingest/loaders.py",
    "ingest/names.py",
    "ingest/parts.py",
    "ingest/paths.py",
    "ingest/quote.py",
    "ingest/streams.py",
    "ingest/yamlsafe.py",
    "io/canonical.py",
    "sem/types.py",
)

VALIDATION_CLOSURE: Final[tuple[str, ...]] = (
    "aer/__init__.py",
    "aer/_structure.py",
    "aer/canon.py",
    "aer/evidence.py",
    "aer/ids.py",
    "aer/locators.py",
    "aer/reader.py",
    "aer/rules.py",
    "aer/types.py",
    "envinfo.py",
    "errors.py",
    "ingest/__init__.py",
    "ingest/archives.py",
    "ingest/jsonstream.py",
    "ingest/limits.py",
    "ingest/loaders.py",
    "ingest/names.py",
    "ingest/parts.py",
    "ingest/paths.py",
    "ingest/quote.py",
    "ingest/streams.py",
    "ingest/yamlsafe.py",
    "io/canonical.py",
    "io/jsonschema_subset.py",
    "prov/compat/adprov_v2_3/__init__.py",
    "prov/compat/adprov_v2_3/build_prov.py",
    "prov/compat/adprov_v2_3/labeling.py",
    "prov/compat/adprov_v2_3/prov_emit.py",
    "prov/compat/adprov_v2_3/serialise.py",
    "prov/compat/adprov_v2_3/validate.py",
    "prov/compat/adprov_v2_3/yaml_shim.py",
    "prov/evidence.py",
    "prov/iri.py",
    "prov/serialise/__init__.py",
    "prov/serialise/nquads.py",
    "prov/serialise/time.py",
    "prov/specs.py",
    "prov/vocab.py",
    "sem/reader.py",
    "sem/types.py",
)

AER_CLOSURE: Final[tuple[str, ...]] = (
    "adapters/profiles.py",
    "adapters/registry/__init__.py",
    "adapters/types.py",
    "envinfo.py",
    "errors.py",
    "host.py",
    "ingest/archives.py",
    "ingest/jsonspan.py",
    "ingest/limits.py",
    "ingest/loaders.py",
    "ingest/names.py",
    "ingest/parts.py",
    "ingest/paths.py",
    "ingest/profile_limits.py",
    "ingest/streams.py",
    "io/atomic.py",
    "io/canonical.py",
    "io/workers.py",
    "progress.py",
    "raw/carve.py",
    "raw/members.py",
    "raw/origins.py",
    "raw/store.py",
    "versions.py",
)

#: What each family imports from outside ``adapters/<family>/`` (its ``adapter_code_sha256``) and the aer core.
AER_FAMILY_CLOSURE: Final[Mapping[str, tuple[str, ...]]] = MappingProxyType({
    "adprov": (
        "adapters/code_verification.py",
        "adapters/protocols.py",
        "adapters/surrogates.py",
        "views/transcript_v1.py",
    ),
    "agentdojo": (
        "adapters/code_verification.py",
        "adapters/environment_load.py",
        "adapters/projection.py",
        "adapters/protocols.py",
        "adapters/surrogates.py",
        "ingest/__init__.py",
        "ingest/jsonstream.py",
        "ingest/quote.py",
        "ingest/sse.py",
        "ingest/yamlsafe.py",
        "io/jsonschema_subset.py",
        "sem/types.py",
    ),
    "agentops": (
        "adapters/protocols.py",
        "ingest/__init__.py",
        "ingest/jsonstream.py",
        "ingest/quote.py",
        "ingest/yamlsafe.py",
        "sem/profiles.py",
        "sem/types.py",
    ),
    "autogen": (
        "adapters/code_verification.py",
        "adapters/protocols.py",
        "sem/profiles.py",
        "sem/types.py",
    ),
    "credleak": (
        "adapters/protocols.py",
        "sem/profiles.py",
        "sem/types.py",
    ),
    "dtap": (
        "adapters/protocols.py",
        "ingest/__init__.py",
        "ingest/jsonstream.py",
        "ingest/quote.py",
        "ingest/yamlsafe.py",
        "sem/profiles.py",
        "sem/types.py",
    ),
    "foobench": (
        "adapters/protocols.py",
        "sem/profiles.py",
        "sem/types.py",
    ),
    "geminicli": (
        "adapters/protocols.py",
        "sem/profiles.py",
        "sem/types.py",
    ),
    "inspect": (
        "adapters/code_verification.py",
        "adapters/protocols.py",
        "adapters/surrogates.py",
        "ingest/quote.py",
        "sem/profiles.py",
        "sem/types.py",
    ),
    "mcphunt": (
        "adapters/protocols.py",
        "ingest/jsonstream.py",
        "sem/profiles.py",
        "sem/types.py",
    ),
    "openhands": (
        "adapters/code_verification.py",
        "adapters/protocols.py",
        "sem/profiles.py",
        "sem/types.py",
    ),
    "qwencode": (
        "adapters/protocols.py",
        "sem/profiles.py",
        "sem/types.py",
    ),
    "wirelog": (
        "adapters/protocols.py",
        "sem/profiles.py",
        "sem/types.py",
    ),
})

SEM_FAMILY_CLOSURE: Final[Mapping[str, tuple[str, ...]]] = MappingProxyType({
    "agentdojo": (
        "adapters/agentdojo/citation.py",
        "adapters/agentdojo/history_table.py",
        "adapters/agentdojo/layout.py",
        "adapters/agentdojo/profile.py",
        "adapters/agentdojo/quirks.py",
        "adapters/code_verification.py",
        "adapters/profiles.py",
        "envinfo.py",
        "host.py",
        "ingest/__init__.py",
        "ingest/archives.py",
        "ingest/jsonstream.py",
        "ingest/names.py",
        "ingest/parts.py",
        "ingest/paths.py",
        "ingest/profile_limits.py",
        "ingest/quote.py",
        "ingest/streams.py",
        "ingest/yamlsafe.py",
        "io/atomic.py",
        "io/workers.py",
        "progress.py",
        "raw/members.py",
        "raw/origins.py",
        "raw/store.py",
        "versions.py",
    ),
    "agentops": (
    ),
    "autogen": (
    ),
    "credleak": (
    ),
    "dtap": (
        "adapters/dtap/matcher.py",
    ),
    "foobench": (
    ),
    "geminicli": (
    ),
    "inspect": (
    ),
    "mcphunt": (
    ),
    "openhands": (
    ),
    "qwencode": (
    ),
    "wirelog": (
    ),
})


def sem_scope(families: Iterable[str]) -> list[str]:
    """The ``sem`` stage's scope for the semantics directories ``families`` (``adapters/<family>/semantics``)."""
    dirs = sorted(set(families))
    extra = sorted({f for d in dirs for f in SEM_FAMILY_CLOSURE.get(d.split("/")[1], ())} - set(SEM_CLOSURE))
    return [*SEM_SEEDS, *SEM_CLOSURE, *dirs, *extra]


def aer_scope(family: str) -> list[str]:
    """The ``aer`` stage's scope for a profile of ``family`` (``adapters/<family>`` itself is ``adapter_code_sha256``)."""
    return [*AER_SEEDS, *AER_CLOSURE, *AER_FAMILY_CLOSURE.get(family, ())]


def prov_scope() -> list[str]:
    """The ``prov`` stage's scope (with :data:`PROV_EXCLUDE`)."""
    return [*PROV_SEEDS, *PROV_CLOSURE]


def validation_scope() -> list[str]:
    """The ``validation`` stage's scope."""
    return [*VALIDATION_SEEDS, *VALIDATION_CLOSURE]
