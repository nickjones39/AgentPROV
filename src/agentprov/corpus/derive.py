"""``derive`` and ``recompute``: re-derivation into a new corpus version (HL H.8; MN N.2.3, N.2.4; DECISIONS D-30, D-32,
D-37, D-43).

Both commands read a source corpus ``SRC`` (sealed, working or ``.partial``) **read-only** and write a *new* working
corpus ``NEW.partial``; nothing is ever written in place (PLAN rule 4). :class:`Derivation` is the engine; the CLI layer
(``agentprov.cli.derive``) opens the :class:`~agentprov.corpus.writer.CorpusWriter` of ``NEW`` and, for a re-map, calls
the public ``agentprov.adapters.runner.importer.import_source`` with a :class:`~agentprov.corpus.rawtree.StoredRawTree`
(``corpus/`` is L5 and may not import ``adapters.runner``, L6; M.5.2(1): the profile and catalogue lookups that need
``adapters`` are injected as :class:`Catalogues`).

**Stages** (D-30). ``expand``/``aer`` = *re-map*: the stored raw objects are mapped again through the importer (no
network; ``until="aer"``), and the layers above the AER follow here as in a re-derive. ``sem``/``prov``/``validation`` = *re-derive*: the stored AERs are
copied unchanged (their seals re-verified) and the T1 job kind ``prov`` (``adapters/runner/provjob.py``, submitted **by
name**) recomputes SEM, PROV and tiers 3-4 in batches over :class:`~agentprov.io.workers.WorkerPool`, consumed in index
order; the AER validator runs in the parent, as in the importer. ``views`` (``transcript-v1``) and ``compat``
(``adprov-v2.3-compat``, D-37) are computed in the parent from the AER. Layers that are not recomputed are carried
(copied byte for byte). The index is rebuilt with full H.3.1 rows (:func:`agentprov.corpus.facets.facet_members`, the
B2 completeness rule), ``derivation.json`` lists the recomputed stage definitions and keeps the carried ones, and the
working ``corpus.json`` gets ``derived_from`` and recomputed counts.

**Inputs first** (H.8.5; baseline R5). Before anything is written every raw object the source lists is re-hashed
(``raw.digest.mismatch`` refuses, :class:`RawDigestError`), and the recorded catalogue and profile digests are checked
against the package at the recorded versions (``rules.mismatch``, ``rules.unavailable``). Catalogues and profiles come
only from the package (AD-14); a corpus ``rules/`` copy is a record that is compared, never used.

**Reuse cache** (D-30 item 10). An execution whose sealed AER, ``sem``/``prov``/``validation`` stage digests (``fn_digest``),
interpreter, lockfile and declared catalogue/profile digests all equal the source's cannot get other SEM, PROV or
validation outputs, so they are carried instead of recomputed (``--out`` by default; never in ``--dry-run``;
``--no-reuse`` turns it off). ``derivation.json`` records ``reuse`` with the sorted recomputed execution ids.

**Raw objects** (D-32) are copied into ``NEW`` by default; ``link_raw`` hard-links them instead (falling back to a copy
across file systems).

**Comparison** (H.8.4). Per execution: the AER bytes and execution digest, the SEM digest per profile, the PROV file
sha256 per spec, the validation-row JCS digest and the view bytes; bytes and digests only, never parsed-object equality.
Classes: ``identical``; ``changed_explained`` (a declared version of the changed stage, or of a stage upstream of it,
differs: adapter, profile and catalogue versions, spec, options, format, mode, library versions; code digests are not
declared versions); ``unexplained_change`` (exit 1); ``failed``; ``unverified`` (a catalogue or profile version the
package does not ship). A code-digest-only change with identical outputs passes. Index-row deltas outside the outputs
(completeness, status, issues, ...) are counted separately as ``index_refreshed``. Corpus-level files (register,
origins, members) are compared too; an unexplained difference there also exits 1 (HL-T14).

**Round-trip cache** (D-550, :mod:`agentprov.validate.cache`). With a ``validation_cache`` (set by the caller), each
``prov`` job that validates gets the cache's entry for the source row's stored PROV digest as a hint (input 1). The
job uses it only if the PROV it derives has exactly that digest, under the job's own context. A job that ran the round
trip returns it, and the parent stores it against the bytes it writes. Outputs are the same with and without it.

**Determinism.** Outputs are byte-identical for every worker count and with ``in_process`` (except the recorded
``producer.isolation``); everything is ordered by execution id. No wall-clock time is written.

**Resume.** ``NEW.partial`` is resumable after an interruption: the first files written are a working ``corpus.json``
whose ``derived_from`` names the source manifest digest and the recomputed stages; a second run with the same
``derived_from`` reuses every execution whose index row records the same sealed AER (D.2.9: keyed on the AER, never on
file existence); any other ``derived_from`` is refused (exit 4).
"""

from __future__ import annotations

import contextlib
import dataclasses
import json
import logging
import os
import platform
import shutil
import tempfile
from collections import Counter
from collections.abc import Callable, Collection, Iterable, Mapping, Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

from agentprov.aer import AER_FORMAT_ID
from agentprov.aer.reader import AerDocument, load_aer_bytes
from agentprov.aer.rules import RuleRegistry, load_catalogue
from agentprov.aer.validate import AerValidator
from agentprov.corpus.authority import DRIFT, DRIFT_DETAIL, PackageResources, catalogue_drift
from agentprov.corpus.buildstep import BuildStepError, describe_steps, parse_steps
from agentprov.corpus.facets import FacetError, completeness_of, facet_members
from agentprov.corpus.index import (
    ExecutionEntry,
    IndexRow,
    RawRef,
    StageOutput,
)
from agentprov.corpus.layout import TRANSCRIPT_VIEW, WITHHELD, classify_relpath, shard
from agentprov.corpus.manifest import CORPUS_FORMATS as AER_OF_FORMAT, ONTOLOGY_VERSIONS
from agentprov.corpus.reader import CORPUS_FORMAT, CORPUS_FORMATS, WORKING, CorpusReader
from agentprov.corpus.register import RegisterEntry
from agentprov.corpus.selection import SELECTION_KEYS, snapshot_selections
from agentprov.corpus.stages import StageKey, has_stage, in_order, stage_map, stages_named
from agentprov.corpus.writer import CorpusWriter
from agentprov.errors import AgentProvError
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.profile_limits import apply_profile_limits
from agentprov.io.atomic import atomic_write_bytes
from agentprov.io.canonical import jcs_bytes, sha256_hex
from agentprov.io.workers import KIND_RSS_BYTES, Job, JobResult, WorkerLimits, WorkerPool, prov_charge
from agentprov.progress import NULL_PROGRESS, Progress, ProgressEvent
from agentprov.prov.specs import COMPAT_SPEC_ID, REGRESSION_ORACLE, SPEC_ID
from agentprov.raw.members import MemberLog, decode_members, encode_members
from agentprov.raw.origins import OriginLog
from agentprov.raw.store import RawObjectStore
from agentprov.sem.reader import load_sem_bytes
from agentprov.sem.types import SemDocument
from agentprov.stage_definitions import (
    PACKAGE_ROOT,
    SemanticsInfo,
    code_sha256,
    detail,
    lockfile_sha256,
    prov_stage_definition,
    sem_stage_definition,
    validation_stage_definition,
    versions,
    with_digest,
)
from agentprov.stage_scopes import aer_scope
from agentprov.versions import __version__

__all__ = [
    "COMMANDS",
    "STAGES",
    "Catalogues",
    "DeriveError",
    "DerivePlan",
    "DeriveRefusedError",
    "DeriveUnsupportedError",
    "Derivation",
    "RawDigestError",
    "RederiveReport",
    "SemanticsInfo",
    "TrigReport",
    "code_sha256",
    "compat_stage_definition",
    "declared_identity",
    "export_trig",
    "prov_stage_definition",
    "resolve_plan",
    "sem_stage_definition",
    "validation_stage_definition",
    "views_stage_definition",
    "with_digest",
]

_LOG = logging.getLogger(__name__)

COMMANDS: Final = ("derive", "recompute")
#: The stage names of ``--stages`` (H.8.5), in DAG order. ``compat`` is requested with ``--prov-spec``.
STAGES: Final = ("expand", "aer", "sem", "prov", "validation", "views")
_ORDER: Final = ("expand", "aer", "sem", "prov", "validation", "views", "compat")
_REMAP: Final = frozenset({"expand", "aer"})
_REDERIVE: Final = ("sem", "prov", "validation")
_UNTIL: Final = ("raw", "aer", "sem", "prov", "validation")
#: The stages each output depends on (H.8.1 DAG): a change is explained by a declared change of any of them.
_UPSTREAM: Final[Mapping[str, tuple[str, ...]]] = {
    "aer": ("expand", "aer"),
    "sem": ("expand", "aer", "sem"),
    "prov": ("expand", "aer", "sem", "prov"),
    "validation": ("expand", "aer", "sem", "prov", "validation"),
    "views": ("expand", "aer", "views"),
    "compat": ("expand", "aer", "views", "compat"),
}
#: Keys of a stage definition that are code digests, not declared versions (H.8.4(2)).
_CODE_KEYS: Final = frozenset({"fn_digest", "engine_code_sha256", "adapter_code_sha256"})
#: The transcript/v1 renderer of each adapter whose AER has the view (C.15.3; E.8.2): the AgentDojo family and adprov-v1.
VIEW_RENDERERS: Final[Mapping[str, str]] = {
    "adprov.transcript_v1": "render",
    "agentdojo.tracelogger": "render_converted",
}
#: Manifest members that belong to a sealed corpus only; a new working version drops them (H.2.2).
_SEALED_ONLY: Final = ("content_digest", "corpus_version", "datasheet", "digests", "files", "validation")
_SEVERITY_ORDER: Final = {"info": 0, "warning": 1, "error": 2}
DEFAULT_BATCH: Final = 256
#: The largest batch :func:`batch_for` picks: the parent holds about two batches of units at once (one staged, one running)
MAX_BATCH: Final = 1024


def batch_for(workers: int) -> int:
    """The batch size for ``workers`` T1 workers when none is given (perf round 2, D-895): 64 jobs per worker (one worker
    lifetime, ``WorkerPool.jobs_per_worker``), between :data:`DEFAULT_BATCH` and :data:`MAX_BATCH`. Every worker is
    retired at the end of a batch, so fewer, larger batches start fewer workers and wait for fewer batch tails: at
    ``--jobs 16`` a 1024-unit batch took ``recompute`` from 79.7 s to 64.1 s. A batch size never changes an output."""
    return min(MAX_BATCH, max(DEFAULT_BATCH, 64 * max(1, workers)))
#: D-554: the charge of a ``prov`` job whose PROV size is unknown (its RSS cap, D-55)
PROV_CAP: Final = KIND_RSS_BYTES["prov"]
#: The corpus files that account for an absent raw object (BF-20, CB-6); a derivation carries the two raw/ ones into NEW.
TOMBSTONES_FILE: Final = "raw/tombstones.jsonl"
REFERENCES_FILE: Final = "raw/REFERENCES.json"
#: D-430: why a recompute that writes refuses a corpus recorded under other versions than this package's.
DRIFT_REFUSAL: Final = ("the source corpus was built under other declared versions (profile, catalogue, record or corpus "
                        "format, vocabulary) than this package ships, so the output would mix versions (H.2.5); re-import to "
                        "upgrade, or recompute at the building commit (D-430)")
CLASSES: Final = ("identical", "changed_explained", "unexplained_change", "failed", "unverified")


# ================================================================================================ errors
class DeriveError(AgentProvError):
    """The derivation cannot proceed (``corpus.derive.*``; exit 1)."""

    code = "corpus.derive.error"
    exit_code = 1


class DeriveRefusedError(AgentProvError):
    """A guard refused (exit 4): output not disjoint, an output that exists, another derivation in ``NEW.partial``, a
    layer present at another version (``derive``; N.2.3(4))."""

    code = "corpus.derive.refused"
    exit_code = 4


class DeriveUnsupportedError(AgentProvError):
    """A capability this build does not have (exit 5): re-mapping a live corpus (D-43)."""

    code = "corpus.derive.unsupported"
    exit_code = 5


class RawDigestError(AgentProvError):
    """A raw object of the source does not hash to its address, or is missing (exit 1; nothing was derived)."""

    code = "raw.digest.mismatch"
    exit_code = 1


# ================================================================================================ stage definitions
# ultrareview pipeline nit: one implementation, shared with the importer (agentprov.stage_definitions)
_PACKAGE_ROOT: Final = PACKAGE_ROOT
_versions = versions
_lockfile_sha256 = lockfile_sha256
_detail = detail


def views_stage_definition() -> dict[str, Any]:
    """The ``views`` stage (``transcript-v1``, a function of the AER alone; H.8.1)."""
    return with_digest({
        "stage": "views", "fn": "view", "view": TRANSCRIPT_VIEW, "format": "agentprov-transcript/0.1",
        "engine": f"agentprov@{__version__}", "engine_code_sha256": "sha256:" + code_sha256(["views"]),
    })  # fmt: skip


def compat_stage_definition() -> dict[str, Any]:
    """The ``compat`` stage: the frozen ``adprov-v2.3-compat`` oracle over the transcript/v1 view (D-37; R-55)."""
    return with_digest({
        "stage": "compat", "fn": "provenance", "spec": COMPAT_SPEC_ID, "status": REGRESSION_ORACLE,
        "view": TRANSCRIPT_VIEW,
        "engine": f"agentprov@{__version__}", "engine_code_sha256": "sha256:" + code_sha256(["prov/compat", "views"]),
    })  # fmt: skip


def declared_identity(definition: Mapping[str, Any]) -> dict[str, Any]:
    """The declared versions of a stage definition (H.8.4(2)): everything but the code digests.

    Catalogue and profile digests recorded beside an integer version (``aer``: ``profile_sha256``, ``rules_sha256``;
    ``sem``: the digest values of ``profiles``) are not declared versions either: under the strict bump discipline (D-31)
    a content change needs a new integer version, so a digest change at the same version is unexplained (and reported as
    ``rules.mismatch``).

    ``limits_sha256`` is not a declared version either (D-31 addendum, user decision 2026-10-13, regen-plan F-1(b)): a
    change of the ingest limits is reported as a notice but explains no output difference, so a changed AER must be
    explained by a code, profile or catalogue version."""
    out = {k: v for k, v in definition.items() if k not in _CODE_KEYS and k != "limits_sha256"}
    if out.get("stage") == "aer":
        out.pop("profile_sha256", None)
        out.pop("rules_sha256", None)
    if out.get("stage") == "prov" and isinstance(out.get("rules"), Mapping):
        out.pop("rules_sha256", None)  # D-640: with its integer version recorded, the aprov digest is not a declared version
    if out.get("stage") == "sem" and isinstance(out.get("profiles"), Mapping):
        out["profiles"] = sorted(out["profiles"])
    return out


def _python() -> dict[str, str]:
    return {"implementation": platform.python_implementation(), "version": platform.python_version()}




# ================================================================================================ injection and plan
@dataclass(frozen=True)
class Catalogues:
    """Lookups that need ``adapters`` (L4/L6), injected by the CLI (M.5.2(1)). ``None``: not shipped at that version."""

    source_profile_sha256: Callable[[str, int], str | None]
    semantics: Callable[[str], SemanticsInfo | None]
    #: the version of the source profile this package ships as current (``None``: unknown, no drift reported; D-430)
    current_profile_version: Callable[[str], int | None] = lambda _profile_id: None
    #: the adapter family that ships a source profile (``None``: unknown; then nothing is reused, BF-33)
    profile_family: Callable[[str], str | None] = lambda _profile_id: None
    #: the worker memory caps a source profile ``(id, version)`` raises, by job kind (D-931, D-935; timing only)
    worker_caps: Callable[[str, int], Mapping[str, int]] = lambda _profile_id, _version: {}
    #: the ``[import] limits`` a source profile ``(id, version)`` declares (D-323; empty: none, or not shipped; D-1001)
    profile_limits: Callable[[str, int], Mapping[str, Any]] = lambda _profile_id, _version: {}


@dataclass(frozen=True)
class DerivePlan:
    """What one ``derive``/``recompute`` run does (built by :func:`resolve_plan`)."""

    command: str
    remap: bool  # expand + aer re-run through the importer (every downstream layer with it)
    rederive: bool  # sem/prov/validation recomputed by T1 ``prov`` jobs (without remap)
    until: str  # the last stage of the AER pipeline the run produces (importer ``until``)
    semantics: tuple[str, ...]  # semantics profile references
    views: bool  # transcript-v1 computed
    compat: bool  # adprov-v2.3-compat computed
    carry_views: bool
    carry_compat: bool
    mode: str  # dev | release: the validation mode (and the importer mode of a re-map)
    recomputed: tuple[str, ...]  # stage names, DAG order
    reused: tuple[str, ...]  # present stages carried by a derive
    jobs: int = 0
    in_process: bool = False
    link_raw: bool = False
    batch_size: int | None = None  # None: batch_for(the pool's worker count)
    show_diff: int = 0
    strict: bool = False
    reuse: bool = False  # carry SRC outputs whose reuse key is unchanged (see Derivation._reusable)
    prov_conformance: bool = True  # G2c-5: False skips tier 4 of a recomputed validation (dev mode only)


def _identities(definitions: Sequence[Mapping[str, Any]]) -> list[bytes]:
    return sorted(jcs_bytes(declared_identity(d)) for d in definitions)


def _fn_renames(olds: Sequence[Mapping[str, Any]], nows: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    """Old ``fn_digest`` -> new (64 hex) of the expansions that pair one to one by declared identity but differ in
    ``fn_digest`` (a code or limits change only; P-2). An identity recorded more than once on a side pairs nothing."""

    def by_identity(definitions: Sequence[Mapping[str, Any]]) -> dict[bytes, str | None]:
        out: dict[bytes, str | None] = {}
        for d in definitions:
            key, fn = jcs_bytes(declared_identity(d)), str(d.get("fn_digest") or "").removeprefix("sha256:")
            out[key] = None if key in out else fn
        return out

    before, after = by_identity(olds), by_identity(nows)
    return {a: b for key, a in before.items() if a and (b := after.get(key)) and a != b}


def _codes(definitions: Sequence[Mapping[str, Any]]) -> list[bytes]:
    return sorted(jcs_bytes({k: d.get(k) for k in sorted(_CODE_KEYS)}) for d in definitions)


def _until_of(stages: Mapping[Any, Any], manifest: Mapping[str, Any], *, mapped: bool = True) -> str:
    """The furthest stage the source holds (ultrareview pipeline #4): the recorded ``selection.until``, raised to every
    layer above the AER the derivation records, and to ``aer`` when the index holds an execution. The ``until`` an
    importer wrote was the last run's (a later ``import --until raw`` lowered it); a re-map under it mapped nothing."""
    selection = manifest.get("selection")
    until = selection.get("until") if isinstance(selection, Mapping) else None
    found = [str(until)] if until in _UNTIL else []
    found += [name for name in ("validation", "prov", "sem") if name in stages]
    if mapped or not found:
        found.append("aer")
    return max(found, key=_UNTIL.index)


def _semantics_of(manifest: Mapping[str, Any]) -> tuple[str, ...]:
    profiles = manifest.get("profiles")
    entries = profiles.get("semantics") if isinstance(profiles, Mapping) else None
    out: list[str] = []
    for entry in entries or ():
        if isinstance(entry, Mapping) and isinstance(entry.get("id"), str) and isinstance(entry.get("version"), int):
            out.append(f"{entry['id']}@{entry['version']}")
    return tuple(out)


def _stages_of(derivation: Mapping[str, Any] | None) -> dict[StageKey, dict[str, Any]]:
    """The stage definitions by name; ``expand`` by ``("expand", fn_digest)``, so several expansions are all kept (D-380)."""
    return stage_map(derivation)


def _mode_of(stages: Mapping[Any, Mapping[str, Any]]) -> str:
    """The source's mode: its validation stage's, or its ``aer`` stage's ``mode`` (a release-mode import records it
    whatever ``--until`` was; ultrareview pipeline #5)."""
    validation, aer = stages.get("validation"), stages.get("aer")
    recorded = [s.get("mode") for s in (validation, aer) if isinstance(s, Mapping)]
    return "release" if "release" in recorded else "dev"


def resolve_plan(
    source: CorpusReader,
    command: str,
    *,
    stages: Sequence[str] | None = None,
    prov_specs: Sequence[str] = (),
    views: Sequence[str] = (),
    semantics: Sequence[str] | None = None,
    jobs: int = 0,
    in_process: bool = False,
    link_raw: bool = False,
    batch_size: int | None = None,
    show_diff: int = 0,
    strict: bool = False,
    reuse: bool = False,
    catalogues: Catalogues | None = None,
    prov_conformance: bool = True,
) -> DerivePlan:
    """Turn the command line into a :class:`DerivePlan` (D-30). Raises ``ValueError`` (usage, exit 2),
    :class:`DeriveUnsupportedError` (exit 5) or :class:`DeriveRefusedError` (exit 4)."""
    if command not in COMMANDS:
        raise ValueError(f"unknown command {command!r}")
    manifest = source.manifest() or {}
    from agentprov.corpus.runstate import incomplete_snapshots

    incomplete = incomplete_snapshots(manifest)
    if incomplete:  # D-610: a re-map would map what the raw store holds, not what the corpus holds
        sid = sorted(incomplete)[0]
        raise DeriveRefusedError(
            f"snapshot {sid} of the source corpus is incomplete: an import run stopped before it ran to the end "
            f"({incomplete[sid]}); re-run the same import to the end first (D-610)", code="corpus.derive.incomplete")
    src_stages = _stages_of(source.derivation())
    until_src = _until_of(src_stages, manifest, mapped=next(iter(source.index()), None) is not None)
    sem_src = _semantics_of(manifest)
    has_rederive = {name: name in src_stages for name in _REDERIVE}
    has_views = "views" in src_stages
    has_compat = "compat" in src_stages or any(COMPAT_SPEC_ID in (r.prov or {}) for r in source.index())
    live = manifest.get("mode") == "live"
    for spec in prov_specs:
        if spec not in (SPEC_ID, COMPAT_SPEC_ID):
            raise ValueError(f"unknown provenance spec {spec!r}")
    for view in views:
        if view != TRANSCRIPT_VIEW:
            raise ValueError(f"unknown view {view!r}; transcript-v1 is the only view")
    if stages is not None:
        unknown = [s for s in stages if s not in STAGES]
        if unknown:
            raise ValueError(f"unknown stage {unknown[0]!r}; stages are {', '.join(STAGES)}")
    want_compat = COMPAT_SPEC_ID in prov_specs
    want_views = bool(views) or (stages is not None and "views" in stages)
    mode = _mode_of(src_stages)
    if not prov_conformance and mode == "release":
        raise ValueError("--skip-prov-conformance is a dev-mode option; this corpus was validated in release mode")
    common = {"jobs": jobs, "in_process": in_process, "link_raw": link_raw, "batch_size": None if batch_size is None else max(1, batch_size),
              "show_diff": max(0, show_diff), "strict": strict, "mode": mode, "reuse": reuse,
              "prov_conformance": prov_conformance}

    if command == "recompute":
        requested = set(stages) if stages is not None else (
            (set() if live else {"expand", "aer"}) | {n for n in _REDERIVE if has_rederive[n]}
            | ({"views"} if has_views else set()))  # a live corpus starts from its AERs by default (D-43)
        if want_compat and not has_compat:
            raise ValueError("the source has no adprov-v2.3-compat output to recompute; add it with derive --prov-spec")
        compat = has_compat and (stages is None or want_compat or bool(requested & _REMAP))
        remap = bool(requested & _REMAP)
        if remap and live:
            raise DeriveUnsupportedError(
                "a live corpus cannot be re-mapped: its AERs come from capture logs, not from a re-runnable import "
                "(D-43); recompute --stages sem,prov,validation re-derives the layers above the AER",
                code="corpus.derive.live_remap")
        for name in requested & set(_REDERIVE):
            if not has_rederive[name]:
                raise ValueError(f"the source has no {name} layer to recompute; add it with derive")
        if "views" in requested and not has_views:
            raise ValueError("the source has no views to recompute; add them with derive --views transcript-v1")
        rederive = bool(requested & set(_REDERIVE)) and not remap
        group = [n for n in _REDERIVE if has_rederive[n]] if (rederive or remap) else []
        views_now = has_views and ("views" in requested or remap)
        recomputed: list[str] = [n for n in ("expand", "aer") if remap and (n != "expand" or has_stage(src_stages, "expand"))]
        recomputed += group
        if views_now:
            recomputed.append("views")
        if compat:
            recomputed.append("compat")
        return DerivePlan(
            command=command, remap=remap, rederive=rederive, until=until_src, semantics=sem_src,
            views=views_now, compat=compat, carry_views=has_views and not views_now,
            carry_compat=has_compat and not compat, recomputed=tuple(recomputed), reused=(), **common)  # type: ignore[arg-type]

    # derive: add missing layers; present layers are reused (carried) when their declared versions match the package
    requested = set(stages) if stages is not None else set(_REDERIVE)
    if requested & _REMAP:
        raise ValueError("derive adds layers above the AER (sem, prov, validation, views); use recompute to re-map")
    missing = [n for n in _REDERIVE if n in requested and not has_rederive[n]]
    present = [n for n in _REDERIVE if n in requested and has_rederive[n]]
    refs = tuple(semantics) if semantics is not None else sem_src
    if catalogues is not None:
        # ultrareview pipeline #6: with the run's --skip-prov-conformance setting, so a skipped-tier-4 validation layer
        # matches a run under the same setting (as the resume and reuse checks do)
        current = _current_definitions(refs, mode, catalogues, prov_conformance=prov_conformance)
        for name in present:
            if name in current and declared_identity(src_stages[name]) != declared_identity(current[name]):
                raise DeriveRefusedError(
                    f"the {name} layer is present at another version than this build derives (N.2.3(4)); "
                    "use recompute --out to re-derive it", code="corpus.derive.version_mismatch")
    rederive = bool(missing)
    if rederive and not has_rederive["sem"] and semantics is None and not refs:
        _LOG.info("derive: no semantics profile recorded; the sem layer is not produced")
    group = list(_REDERIVE) if rederive else []
    added: list[str] = [n for n in group if n != "sem" or refs]
    views_now = want_views and not has_views
    compat_now = want_compat and not has_compat
    if views_now:
        added.append("views")
    if compat_now:
        added.append("compat")
    reused: list[str] = [n for n in present if n not in added]
    if want_views and has_views:
        reused.append("views")
    if want_compat and has_compat:
        reused.append("compat")
    return DerivePlan(
        command=command, remap=False, rederive=rederive, until="validation" if rederive else until_src,
        semantics=refs if rederive else sem_src, views=views_now, compat=compat_now,
        carry_views=has_views, carry_compat=has_compat, recomputed=tuple(added), reused=tuple(reused),
        **common)  # type: ignore[arg-type]


def _current_definitions(refs: Sequence[str], mode: str, catalogues: Catalogues, *,
                         prov_conformance: bool = True) -> dict[str, dict[str, Any]]:
    """The stage definitions this build derives. ``prov_conformance`` (G2c-5) is part of the validation stage's identity
    (its ``skipped`` checks), so a resume or a reuse under the other setting does not match (PR-7)."""
    out: dict[str, dict[str, Any]] = {}
    infos = [catalogues.semantics(ref) for ref in refs]
    if refs and all(info is not None for info in infos):
        out["sem"] = sem_stage_definition([i for i in infos if i is not None])
    out["prov"] = prov_stage_definition()
    out["validation"] = validation_stage_definition(refs, mode, prov_conformance=prov_conformance)
    return out


# ================================================================================================ report
@dataclass
class RederiveReport:
    """What :meth:`Derivation.finish` returns (H.8.5 ``RederiveReport``)."""

    command: str
    corpus_id: str
    counters: dict[str, int] = field(default_factory=dict)
    changes: list[dict[str, Any]] = field(default_factory=list)  # one per non-identical execution, sorted by ex
    details: list[dict[str, Any]] = field(default_factory=list)  # --show-diff
    corpus_changes: list[dict[str, Any]] = field(default_factory=list)  # register/origins/members deltas
    issues_by_code: dict[str, int] = field(default_factory=dict)
    failures: list[dict[str, Any]] = field(default_factory=list)
    notices: list[str] = field(default_factory=list)
    compat_written: bool = False
    compat_loaded: bool = False
    stage_changes: dict[str, bool] = field(default_factory=dict)
    recomputed: list[str] = field(default_factory=list)
    strict: bool = False

    @property
    def exit_code(self) -> int:
        c = self.counters
        bad = c.get("unexplained_change", 0) or c.get("failed", 0) or c.get("corpus_unexplained", 0)
        if self.strict and c.get("unverified", 0):
            bad = 1
        return 1 if bad else 0


@dataclass(slots=True)
class _Unit:
    """One execution between its AER and its index entry (re-derive and carry paths)."""

    row: IndexRow
    data: bytes
    aer: AerDocument
    codes: dict[str, str]  # register code -> severity for this ex
    aer_row: dict[str, Any]
    aer_ok: bool
    reuse_from: IndexRow | None = None  # the source row whose outputs are carried (reuse cache)


def _with_hint(params: Mapping[str, Any], hint: bool) -> dict[str, Any]:
    """A ``prov`` job's params, with ``fidelity.hint`` set when the job gets a staged hint (D-550)."""
    out = dict(params)
    if hint and isinstance(out.get("fidelity"), Mapping):
        out["fidelity"] = {**out["fidelity"], "hint": True}
    return out


# ================================================================================================ the engine
class Derivation:
    """The engine of ``derive`` and ``recompute`` (see the module docstring). One instance per run.

    ``validation_cache`` (D-550): the tier-4 round-trip cache (:class:`agentprov.validate.cache.DiskCache`), or
    ``None``; set by the caller before :meth:`rederive`.

    Sequence (the CLI drives it)::

        derivation = Derivation(reader, plan, catalogues=..., progress=...)
        derivation.check_inputs()                      # writes nothing; raises RawDigestError, DeriveRefusedError
        with CorpusWriter(NEW, ...) as writer:
            derivation.prepare(writer)                 # raw objects, origins, carried register rows, early manifest
            if plan.remap:
                report = import_source(..., tree=derivation.stored_tree(...), corpus=writer, **derivation.import_arguments())
            else:
                derivation.rederive(writer)
            result = derivation.finish(writer)         # views/compat, full index rows, derivation.json, corpus.json, comparison
    """

    def __init__(
        self,
        source: CorpusReader,
        plan: DerivePlan,
        *,
        catalogues: Catalogues,
        progress: Progress = NULL_PROGRESS,
        scope: Collection[str] | None = None,
        package: PackageResources | None = None,
    ) -> None:
        self.src = source
        self.plan = plan
        self.catalogues = catalogues
        self.progress = progress
        self.package = package
        #: ``verify --level rederive --sample`` (U4): only these executions are re-derived and compared, and the
        #: corpus-level files (register, origins, members) are not compared (they cover every execution).
        self.scope: frozenset[str] | None = None if scope is None else frozenset(scope)
        self.manifest: dict[str, Any] = dict(source.manifest() or {})
        self.src_derivation = source.derivation() or {}
        self.src_stages = _stages_of(self.src_derivation)
        self.src_rows: list[IndexRow] = [r for r in source.index() if self.scope is None or r.ex in self.scope]
        self.src_by_ex = {row.ex: row for row in self.src_rows}
        self.prov_cap = self._prov_cap()
        self.registry = RuleRegistry.default()
        self.notices: list[str] = []
        self.drift: list[str] = []  # D-430, set by check_inputs
        #: BF-20, CB-6: objects the source accounts for being absent (hex -> tombstoned | withheld | referenced) and the
        #: executions that need one of them (directly or through a container); set by :meth:`check_inputs`.
        self.absent: dict[str, str] = {}
        self.absent_ex: set[str] = set()
        #: RC-2: the input labels of every raw object those executions referenced (primary and auxiliary), as quoted JSON
        #: strings: the register rows a re-map writes for them by path subject are not reproduced either
        self.absent_labels: set[str] = set()
        self.withheld_ex: set[str] = set()
        self.issues: Counter[str] = Counter()
        self.failures: list[dict[str, Any]] = []
        self.counters: Counter[str] = Counter()
        self.compat_written = False
        self.compat_loaded = False
        self._unavailable: dict[tuple[str, int], bool] = {}
        self._profile_digests: dict[tuple[str, int], str] = {}
        self._derived_from: dict[str, Any] | None = None
        self._source_validation: dict[str, dict[str, Any]] | None = None
        self._codes_by_ex: dict[str, dict[str, str]] = {}
        self._stage_entries: dict[str, list[RegisterEntry]] | None = None
        self._reuse_global: bool | None = None
        #: RC-9: reused executions keep their SEM and PROV, and their validation is rebuilt without tier 4
        self._reuse_drop_tier4 = False
        self._reuse_header: dict[str, bool] = {}
        self.validation_cache: Any = None
        #: D-550: the staged hint of each staged AER (AER object digest -> hint object digest) and the hint objects'
        #: reference counts (two units could share a hint object; it is removed when the last one is finished)
        self._hints: dict[str, str] = {}
        self._hint_refs: Counter[str] = Counter()
        self._recomputed_ex: list[str] = []

    # -------------------------------------------------------------------------------------- inputs first
    def listed_objects(self) -> dict[str, bool]:
        """Every object the source lists: origin rows (members included) and index raw entries -> ``included``."""
        listed: dict[str, bool] = {}
        for origin_row in self.src.origins():
            listed[origin_row.sha256] = True
        for row in self.src_rows:
            for ref in row.raw:
                listed[ref.sha256] = listed.get(ref.sha256, False) or ref.included
        return dict(sorted(listed.items()))

    def check_inputs(self) -> None:
        """Re-hash every raw object the source lists and check the recorded catalogue and profile digests (H.8.5;
        baseline R5). Writes nothing. Raises :class:`RawDigestError` on a missing or tampered object."""
        store = self.src.raw_store()
        self.absent = self._accounted_absences()
        checked = 0
        for sha, included in self.listed_objects().items():
            if not store.has(sha):
                kind = self.absent.get(sha)
                if kind is not None:  # BF-20, CB-6: absent on purpose; the executions that need it are unverified
                    self.counters[f"{kind}_unavailable"] += 1
                    continue
                if included:
                    raise RawDigestError("a raw object the source lists is missing from its store", code="raw.object.missing")
                self.counters["referenced_unavailable"] += 1
                continue
            try:
                store.verify(sha)
            except AgentProvError:
                raise RawDigestError("a raw object of the source does not hash to its address; nothing was derived") from None
            checked += 1
        self.counters["raw_verified"] = checked
        self.absent_ex = self._executions_needing(set(self.absent))
        self.absent_labels = self._labels_of_executions(self.absent_ex)
        for kind in sorted(set(self.absent.values())):
            self.notices.append(f"raw objects {kind} by the source are absent: the executions that need them are "
                                "unverified, not re-derived (H.4.5(6))")
        self._check_rules()
        self.drift = self.version_drift()
        for line in self.drift:
            self.notices.append(f"version drift: {line}")
        if self.drift:  # D-430, D-780: the commit to recompute at, where the source records it
            self.notices.append(f"source {self.built_at()}")

    def built_at(self) -> str:
        """The source's building commits in one plain clause (``building commit not recorded`` before D-780)."""
        try:
            steps = parse_steps((self.manifest.get("producer") or {}).get("build_steps"))
        except BuildStepError:
            return "build_steps is malformed"
        return describe_steps(steps)

    def _accounted_absences(self) -> dict[str, str]:
        """The objects the source accounts for being absent (BF-20, CB-6): purged (``raw/tombstones.jsonl``), withheld by the
        sealed corpus version (``WITHHELD.json``) and referenced only (``raw/REFERENCES.json``), as ``hex -> kind``. Any
        other absence stays ``raw.object.missing``."""
        out: dict[str, str] = {}
        if self.src.exists(REFERENCES_FILE):
            from agentprov.raw.references import parse_references

            out.update((r.sha256, "referenced") for r in parse_references(self.src.read_bytes(REFERENCES_FILE), self.src.limits))
        if self.src.exists(WITHHELD):
            from agentprov.corpus.withheld import decode_withheld

            document = decode_withheld(self.src.read_bytes(WITHHELD), self.src.limits)
            out.update((sha, "withheld") for sha in document.objects)
            self.withheld_ex = set(document.execution_map)  # withheld executions have no released row
        if self.src.exists(TOMBSTONES_FILE):
            from agentprov.corpus.purge import decode_tombstones

            out.update((t.sha256, "tombstoned") for t in decode_tombstones(self.src.read_bytes(TOMBSTONES_FILE), self.src.limits))
        return out

    def _labels_of_executions(self, executions: set[str]) -> set[str]:
        """RC-2: the labels (``path``, member ``label`` or ``file`` of their recorded origins) of the raw objects that
        ``executions`` reference, each as its JCS string (the bytes the corpus rows hold). A re-map without an absent
        per-unit input disposes those files by path subject (DTap's judge file of a pointer whose LFS object was purged),
        which BF-20's digest and execution tokens do not cover.

        RC-14: only labels used exclusively by ``executions``. An input that another execution also references (a task's
        configuration) is checked as before, so a real change to it is never hidden. RC-16: the token is the JCS string
        (raw UTF-8), not an ASCII-escaped one, so a non-ASCII label matches its rows."""
        if not executions:
            return set()
        mine, shared = self._inputs_of(executions)

        def labels(objects: set[str]) -> set[str]:
            out: set[str] = set()
            for origin_row in self.src.origins():
                if origin_row.sha256 in objects:
                    data = origin_row.origin.data
                    label = data.get("path") or data.get("label") or data.get("file")
                    if isinstance(label, str) and label:
                        out.add(jcs_bytes(label).decode("utf-8"))
            return out

        return labels(mine - shared) - labels(shared)

    def _inputs_of(self, executions: set[str]) -> tuple[set[str], set[str]]:
        """The raw objects ``executions`` reference, and those any other execution references (RC-14, RC-13)."""
        mine = {ref.sha256 for row in self.src_rows if row.ex in executions for ref in row.raw}
        shared = {ref.sha256 for row in self.src_rows if row.ex not in executions for ref in row.raw}
        return mine, shared

    def _executions_needing(self, absent: set[str]) -> set[str]:
        """The executions whose raw objects, or a container they were expanded from (AD-12, transitively), are in
        ``absent``: a re-map cannot reproduce them and a re-derive cannot check them."""
        if not absent:
            return set()
        container = {m.sha256: m.container for m in self.src.members() if m.sha256 is not None}

        def gone(sha: str) -> bool:
            seen: set[str] = set()
            while sha not in seen:
                if sha in absent:
                    return True
                seen.add(sha)
                if sha not in container:
                    return False
                sha = container[sha]
            return False

        return {row.ex for row in self.src_rows if any(gone(ref.sha256) for ref in row.raw)}

    def exclude_absent(self, trees: Sequence[Any]) -> None:
        """Drop the stored inputs that are absent on purpose from the re-map trees (BF-20, CB-6). The executions that need
        them are not re-mapped; :meth:`compare` reports them ``unverified``."""
        # RC-13: an input used only by executions that need an absent object is left out too. They are not re-mapped
        # (unverified, as BF-20 has it for an absent primary), and none of their files is mapped as a unit of its own
        # (a purged DTap trajectory's judge file became a new judge-only execution)
        mine, shared = self._inputs_of(self.absent_ex)
        skip = set(self.absent) | (mine - shared)
        for tree in trees:
            tree.restrict([label for label in tree.labels if tree.sha256_of(label) not in skip])
            drop = getattr(tree, "drop_absent", None)  # PR-5: per-unit inputs (context trees, pinned objects; D-530)
            if drop is not None:
                drop(self.absent)

    def version_drift(self) -> list[str]:
        """The declared versions this build would record differently from the source, per recomputed stage (D-430).

        A re-map runs under the package's current source profile and catalogues, while the recorded semantics profiles
        are replayed: when the recorded ``aer`` profile or a recorded catalogue is not the current one, the output would
        mix versions. Recomputed SEM must read the catalogue versions the AER declares (H.2.5). A dry run reports these
        lines; a writing recompute refuses (:data:`DRIFT_REFUSAL`). Reproducing such a corpus byte for byte is done at
        the commit and lockfile that built it (HL "Derivation reproducibility"), not at this package."""
        out: list[str] = [f"aer: catalogue {ns} v{version} recorded with other bytes than the shipped v{version} ({DRIFT}; "
                          "built while the catalogue was edited in place, D-460)"
                          for ns, version in catalogue_drift(self.src_stages).items()]
        aer = self.src_stages.get("aer") or {}
        recorded = {str(ns): int(v) for ns, v in dict(aer.get("rules") or {}).items()}
        rules = dict(recorded)
        if self.plan.remap:
            profile = aer.get("profile")
            if isinstance(profile, str) and "@" in profile:
                pid, _, number = profile.rpartition("@")
                now = self.catalogues.current_profile_version(pid)
                if number.isdigit() and now is not None and now != int(number):
                    out.append(f"aer: source profile {pid} v{number} recorded, v{now} current")
            for ns, version in sorted(recorded.items()):
                try:
                    current = load_catalogue(ns).version
                except AgentProvError:
                    continue
                rules[ns] = current
                if current != version:
                    out.append(f"aer: catalogue {ns} v{version} recorded, v{current} current")
        if "sem" in self.plan.recomputed:
            for ref in self.plan.semantics:
                info = self.catalogues.semantics(ref)
                for ns, version in sorted((info.rules if info is not None else {}).items()):
                    if ns in rules and rules[ns] != version:
                        out.append(f"sem: {ref} reads catalogue {ns} v{version}, the AER would declare v{rules[ns]}")
        # P-1 (pre-round review): the record, corpus and vocabulary formats are declared versions too. A re-map of an
        # aer/0.1 corpus would write aer/0.2 records into an agentprov-corpus/0.2 corpus, and recomputed PROV states the
        # current apv vocabulary; neither is an upgrade mode (D-430: upgrading is a fresh re-import).
        src_format = str(self.manifest.get("format") or "")
        formats: list[str] = []  # re-check RC-18: the format and vocabulary lines come first (they decide the refusal)
        if self.plan.remap:
            recorded_aer = str(aer.get("format") or AER_OF_FORMAT.get(src_format, ""))
            if recorded_aer and recorded_aer != AER_FORMAT_ID:
                formats.append(f"aer: format {recorded_aer} recorded, {AER_FORMAT_ID} current")
            if src_format in CORPUS_FORMATS and src_format != CORPUS_FORMAT:
                formats.append(f"corpus: format {src_format} recorded, {CORPUS_FORMAT} current")
        if "prov" in self.plan.recomputed:
            from agentprov.corpus.authority import prov_catalogue_version
            from agentprov.prov.specs import load_spec
            from agentprov.prov.vocab import VOCAB_VERSION

            built, current = prov_catalogue_version(self.src_stages.get("prov")), load_spec().catalogue_version
            if built is not None and built != current:  # D-621 sibling: the aprov version is a declared version too
                out.append(f"prov: catalogue aprov v{built} recorded, v{current} current")

            recorded_vocab = ONTOLOGY_VERSIONS.get(src_format)
            if recorded_vocab is not None and recorded_vocab != VOCAB_VERSION:
                formats.append(f"prov: vocabulary apv {recorded_vocab} recorded (by {src_format}), apv {VOCAB_VERSION} current")
        return [*formats, *out]

    def _note(self, code: str, text: str) -> None:
        self.issues[code] += 1
        self.notices.append(f"{code}: {text}")

    def _catalogue_digest(self, namespace: str, version: int) -> str | None:
        try:
            return load_catalogue(namespace, version).digest
        except AgentProvError:
            return None

    def _check_rules(self) -> None:
        """``rules.mismatch`` / ``rules.unavailable`` (AD-14; HL-T15). Recompute always uses the package catalogues."""
        aer = self.src_stages.get("aer")
        if aer is not None:
            recorded: Mapping[str, Any] = aer["rules_sha256"] if isinstance(aer.get("rules_sha256"), Mapping) else {}
            for ns, version in sorted(dict(aer.get("rules") or {}).items()):
                digest = self._catalogue_digest(str(ns), int(version))
                if digest is None:
                    self._unavailable[(str(ns), int(version))] = True
                    self._note("rules.unavailable", f"catalogue {ns}@{version} is not shipped by this package")
                elif recorded.get(ns) not in (None, "sha256:" + digest):
                    self._note(DRIFT, f"catalogue {ns}@{version}: " + DRIFT_DETAIL.format(version=version))
            profile = aer.get("profile")
            if isinstance(profile, str) and "@" in profile:
                pid, _, number = profile.rpartition("@")
                sha = self.catalogues.source_profile_sha256(pid, int(number)) if number.isdigit() else None
                if sha is None:
                    self._note("rules.unavailable", f"source profile {profile} is not shipped by this package")
                elif aer.get("profile_sha256") != "sha256:" + sha:
                    self._note("rules.mismatch", f"source profile {profile}: the recorded digest differs from the package's")
        sem = self.src_stages.get("sem")
        if sem is not None:
            for ref, digest in sorted(dict(sem.get("profiles") or {}).items()):
                info = self.catalogues.semantics(str(ref))
                if info is None:
                    self._note("rules.unavailable", f"semantics profile {ref} is not shipped by this package")
                elif digest != "sha256:" + info.sha256:
                    self._note("rules.mismatch", f"semantics profile {ref}: the recorded digest differs from the package's")
        prov = self.src_stages.get("prov")
        if prov is not None:
            from agentprov.corpus.authority import prov_catalogue_ok

            # per recorded version, current or archived (D-621 sibling): an archived older aprov is verifiable
            if not prov_catalogue_ok(prov):
                self._note("rules.mismatch", f"{SPEC_ID}: the recorded aprov catalogue digest is not the package's at the "
                                             "recorded version")
        self._check_rules_copy()

    def _check_rules_copy(self) -> None:
        """A sealed corpus's ``rules/`` copy is a record: its digests are compared with the package (AD-14).

        A sealed manifest names every copy (``rule_catalogues``, ``profiles``); those are compared through
        :func:`agentprov.corpus.authority.check_sealed_rules`, which knows the file names sealing writes (U4)."""
        if self.src.sealed and isinstance(self.manifest.get("rule_catalogues"), list):
            from agentprov.corpus.authority import check_sealed_rules, package_resources

            def read(label: str) -> bytes | None:
                return self.src.read_bytes(label) if self.src.exists(label) else None

            for finding in check_sealed_rules(self.manifest, read, self.package or package_resources()):
                self._note(finding.code, f"{finding.subject}: {finding.detail}")
            return
        root = self.src.root / "rules"
        names: list[str] = []
        for directory, prefix in ((root, "rules/"), (root / "prov", "rules/prov/")):
            try:
                with os.scandir(directory) as it:
                    names += [prefix + e.name for e in it if e.is_file(follow_symlinks=False)]
            except (FileNotFoundError, NotADirectoryError):
                continue
        aer = self.src_stages.get("aer") or {}
        rules = dict(aer.get("rules") or {})
        for label in sorted(names):
            if classify_relpath(label) != "rules":
                continue
            data = self.src.read_bytes(label)
            name = label.rsplit("/", 1)[-1]
            expected: str | None
            if label.startswith("rules/prov/"):
                from agentprov.prov.specs import load_spec

                expected = load_spec().catalogue_sha256 if name == "agentprov-prov-0.1.toml" else None
            elif name.endswith(".rules.toml"):
                ns = name[: -len(".rules.toml")]
                expected = self._catalogue_digest(ns, int(rules[ns])) if ns in rules else None
            elif name.endswith(".profile.toml"):
                pid = name[: -len(".profile.toml")]
                profile = str(aer.get("profile") or "")
                expected = None
                if profile.rpartition("@")[0] == pid and profile.rpartition("@")[2].isdigit():
                    expected = self.catalogues.source_profile_sha256(pid, int(profile.rpartition("@")[2]))
            else:
                continue
            if expected is None:
                self._note("rules.unavailable", f"{label}: no package resource at the recorded version")
            elif sha256_hex(data) != expected:
                self._note("rules.mismatch", f"{label}: the corpus copy differs from the package resource")

    # -------------------------------------------------------------------------------------- derived_from and resume
    def derived_from(self) -> dict[str, Any]:
        if self._derived_from is None:
            manifest_sha = None
            if self.src.exists("corpus.json"):
                manifest_sha = "sha256:" + sha256_hex(self.src.read_bytes("corpus.json"))
            checksums = self.src.checksums_bytes() if self.src.sealed else None
            # BF-32 (N.1.8(3)): the semantics profiles and the function digests of the recomputed layers are part of what
            # a resume must match, so a resume under another --semantics-profile (or another build) is refused; and under
            # the other --skip-prov-conformance setting (PR-7: else the resumed NEW claims a tier 4 its first part skipped)
            current = _current_definitions(self.plan.semantics, self.plan.mode, self.catalogues,
                                           prov_conformance=self.plan.prov_conformance)
            self._derived_from = {
                "command": self.plan.command,
                "corpus_id": self.manifest.get("corpus_id"),
                "corpus_version": self.manifest.get("corpus_version"),
                "fn_digests": {name: current[name]["fn_digest"] for name in self.plan.recomputed if name in current},
                "manifest_sha256": manifest_sha,
                "recomputed": list(self.plan.recomputed),
                "root_digest": None if checksums is None else "sha256:" + sha256_hex(checksums),
                "semantics": list(self.plan.semantics),
                "state": self.src.state,
            }
        return self._derived_from

    def _base_manifest(self) -> dict[str, Any]:
        base = {k: v for k, v in self.manifest.items() if k not in _SEALED_ONLY}
        # a re-derivation keeps its source's corpus format (its AER records are unchanged); a re-map rewrites it with
        # the importer's manifest (aer/0.2 records, agentprov-corpus/0.2; D-212)
        kept = self.manifest.get("format")
        base.update({"format": kept if kept in CORPUS_FORMATS else CORPUS_FORMAT, "sealed": False, "state": "working",
                     "release": {"created": None, "status": "dev"}, "derived_from": self.derived_from()})
        return base

    # -------------------------------------------------------------------------------------- prepare
    def prepare(self, writer: CorpusWriter, *, stored_labels: Sequence[str] | None = None,
                unreproducible: Sequence[RegisterEntry] = ()) -> None:
        """Set ``NEW.partial`` up: refuse another derivation there, copy (or link) the raw objects, carry the origins,
        members and register rows that are not recomputed, and write the early working ``corpus.json``."""
        writer.plan_build_stages(self.plan.recomputed)  # D-780: this step wrote these stages; the carried ones are copies
        existing = writer.read_document(writer.layout.manifest)
        if existing is not None and existing.get("derived_from") != self.derived_from():
            raise DeriveRefusedError(
                "the output's .partial tree holds another derivation (another source, source version or stage set); "
                "choose another --out", code="corpus.derive.resume_mismatch")
        if existing is not None:
            self.notices.append("resuming an interrupted derivation in the existing .partial tree")
        writer.absent_ok = frozenset(self.absent)
        if self.plan.remap:
            if self.plan.link_raw:
                self._copy_objects(writer, self._non_member_objects())
            writer.register.extend(unreproducible)
        else:
            self._copy_objects(writer, list(self.listed_objects()))
            writer.origins = OriginLog(self.src.origins())
            writer.members = MemberLog(self.src.members())
            carried = [e for e in self.src.register() if not ("ex" in e.subject and self._recomputes_stage_entry(e))]
            writer.register.extend(carried)
            self._codes_by_ex = _codes_by_ex(carried)
        for label, target in ((TOMBSTONES_FILE, writer.layout.tombstones), (REFERENCES_FILE, writer.layout.references)):
            if self.src.exists(label):  # CB-6: the purge record and the references stay with NEW, byte for byte
                atomic_write_bytes(target, self.src.read_bytes(label))
        writer.write_document(writer.layout.manifest, self._base_manifest())

    def restamp(self, writer: CorpusWriter) -> None:
        """Put ``derived_from`` back into ``NEW``'s working ``corpus.json`` after the importer rewrote it (re-map), so an
        interrupted re-map stays resumable by the same command."""
        writer.plan_build_stages(self.plan.recomputed)
        current = writer.read_document(writer.layout.manifest) or self._base_manifest()
        if current.get("derived_from") != self.derived_from():
            writer.write_document(writer.layout.manifest, {**current, "derived_from": self.derived_from()})

    def _recomputes_stage_entry(self, entry: RegisterEntry) -> bool:
        """Whether a source register entry belongs to a stage this run recomputes (so it is dropped and re-derived)."""
        recomputed = set(self.plan.recomputed)
        if entry.stage in ("sem", "validate"):
            return bool(recomputed & {"sem", "prov", "validation"})
        if entry.stage == "prov":
            spec_compat = entry.detail.startswith(COMPAT_SPEC_ID + ":")
            return ("compat" in recomputed) if spec_compat else bool(recomputed & {"sem", "prov", "validation"})
        return False

    def _non_member_objects(self) -> list[str]:
        return sorted({row.sha256 for row in self.src.origins() if row.origin.kind not in ("member", "carved")})

    def _source_object(self, sha: str) -> Path:
        shard_dir = self.src.root / "raw" / "objects" / sha[:2]
        with os.scandir(shard_dir) as it:
            names = sorted(e.name for e in it if e.name.startswith(sha + ".") and e.is_file(follow_symlinks=False))
        if len(names) != 1:
            raise RawDigestError("a listed raw object is missing or ambiguous in the source store", code="raw.object.missing")
        label = f"raw/objects/{sha[:2]}/{names[0]}"
        if classify_relpath(label) != "raw_object":
            raise RawDigestError("a raw object name is outside the corpus grammar", code="raw.object.invalid")
        return shard_dir / names[0]

    def _copy_objects(self, writer: CorpusWriter, digests: Iterable[str]) -> None:
        """D-32: copy every object (re-hashed while copying), or hard-link it with ``link_raw``."""
        store: RawObjectStore = writer.store
        source_store = self.src.raw_store()
        linked = copied = 0
        fallback = False
        for sha in digests:
            if not source_store.has(sha):
                continue  # a referenced, not included, object (counted by check_inputs)
            path = self._source_object(sha)
            ext = path.name.split(".", 1)[1]
            if store.has(sha):
                continue
            if self.plan.link_raw and not fallback:
                target = store.path_for(sha, ext)
                target.parent.mkdir(parents=True, exist_ok=True)
                try:
                    os.link(path, target)
                    linked += 1
                    continue
                except OSError:
                    fallback = True
                    self.notices.append("--link-raw: hard links are not possible here; raw objects were copied (D-32)")
            with source_store.open(sha) as stream:
                try:
                    store.put_stream(stream, ext=ext, expected_sha256=sha, max_bytes=1 << 62)
                except AgentProvError:
                    raise RawDigestError("a raw object of the source does not hash to its address") from None
            copied += 1
        self.counters["raw_linked"] += linked
        self.counters["raw_copied"] += copied

    # -------------------------------------------------------------------------------------- re-map arguments
    def import_arguments(self, snapshot_id: str | None = None) -> dict[str, Any]:
        """The ``import_source`` keyword arguments that reproduce the source's import of one snapshot (recorded values
        only; the first snapshot by default). A corpus with several snapshots (D-202) is re-mapped by one call per
        snapshot, in the recorded order (:meth:`snapshot_ids`), each with its own part and pin.

        The caller adds ``filters`` (an ``ImportFilters`` built from :meth:`recorded_selection` of the same snapshot),
        ``limits``, ``workers``/``in_process``/``progress`` and the tree. The limit and sample are the snapshot's own
        (NF-36: each snapshot is replayed with the selection it was imported with)."""
        source = (self.manifest.get("sources") or [{}])[0]
        snapshots = [s for s in source.get("snapshots") or () if isinstance(s, Mapping)] or [{}]
        snapshot = next((s for s in snapshots if s.get("snapshot_id") == snapshot_id), snapshots[0])
        profile = source.get("profile") or {}
        pin = snapshot.get("pin")
        selection = self.snapshot_selection(snapshot.get("snapshot_id"))
        return {
            "profile_id": profile.get("id"),
            "part": snapshot.get("part") or (source.get("parts") or [None])[0],
            "snapshot_id": snapshot.get("snapshot_id"),
            "corpus_id": self.manifest.get("corpus_id"),
            # the re-map contract, once (ultrareview pipeline nit): the importer stops at the AER; SEM, PROV and
            # validation follow in Derivation.rederive, where unchanged AERs reuse (D-30)
            "until": "aer" if self.plan.until in ("sem", "prov", "validation") else self.plan.until,
            "semantics": list(self.plan.semantics),
            "mode": self.plan.mode,
            "pin": dict(pin) if isinstance(pin, Mapping) else None,
            "limit": selection.get("limit"),
            # D-529: a sampled corpus is re-mapped with its recorded sample (plain data: corpus/ imports no adapter)
            **({"sample": dict(sample)} if isinstance(sample := selection.get("sample"), Mapping) else {}),
            **({} if self.plan.prov_conformance else {"prov_conformance": False}),
        }

    def snapshot_selection(self, snapshot_id: str | None = None) -> dict[str, Any]:
        """The selection (``filters``, ``limit``, ``sample``) the snapshot was imported with (NF-36; the first snapshot
        by default): empty for a snapshot imported whole. A corpus that lists no snapshot keeps its top-level one."""
        source = (self.manifest.get("sources") or [{}])[0]
        ids = [str(s["snapshot_id"]) for s in source.get("snapshots") or ()
               if isinstance(s, Mapping) and isinstance(s.get("snapshot_id"), str)]
        if not ids:
            top = self.manifest.get("selection")
            return {k: top[k] for k in SELECTION_KEYS if isinstance(top, Mapping) and k in top}
        return snapshot_selections(self.manifest).get(snapshot_id if snapshot_id in ids else ids[0], {})

    def snapshot_ids(self) -> list[str]:
        """The recorded snapshot ids in import order (D-202): a re-map replays them in this order."""
        source = (self.manifest.get("sources") or [{}])[0]
        return [str(s["snapshot_id"]) for s in source.get("snapshots") or ()
                if isinstance(s, Mapping) and isinstance(s.get("snapshot_id"), str)]

    def source_id(self) -> str:
        source = (self.manifest.get("sources") or [{}])[0]
        value = source.get("source_id")
        if not isinstance(value, str):
            raise DeriveError("the source manifest names no source id; it cannot be re-mapped", code="corpus.derive.manifest")
        return value

    def recorded_selection(self, snapshot_id: str | None = None) -> dict[str, Any]:
        """The filters the snapshot was imported with (NF-36: its own; the first snapshot by default)."""
        filters = self.snapshot_selection(snapshot_id).get("filters")
        return dict(filters) if isinstance(filters, Mapping) else {}

    def recorded_limit_overrides(self) -> dict[str, Any]:
        """The ingest-limit overrides the import ran with: ``corpus.json``'s ``limits`` record. A sealed manifest has none
        (``corpus-0.2`` is closed), so they are rebuilt from the source profile (D-1001, :meth:`_rebuilt_limit_overrides`)."""
        limits = self.manifest.get("limits")
        if limits is None:
            return self._rebuilt_limit_overrides()
        overrides = limits.get("overrides") if isinstance(limits, Mapping) else None
        return dict(overrides) if isinstance(overrides, Mapping) else {}

    def _rebuilt_limit_overrides(self) -> dict[str, Any]:
        """D-1001: the defaults with the ``[import] limits`` of the profile every ``aer`` stage records, kept only when
        their digest equals the stage's recorded ``limits_sha256`` (one value for all ``aer`` stages). Anything else gives
        no overrides, so the importer still refuses a profile that raises a limit (``corpus.derive.limits_mismatch``)."""
        recorded = {(s.get("profile"), s.get("limits_sha256")) for s in stages_named(self.src_stages, "aer")}
        if len(recorded) != 1:
            return {}
        ((profile, digest),) = recorded
        if not isinstance(profile, str) or not isinstance(digest, str):
            return {}
        pid, _, version = profile.rpartition("@")
        declared = self.catalogues.profile_limits(pid, int(version)) if version.isdigit() else {}
        if not declared:
            return {}
        try:
            rebuilt = apply_profile_limits(IngestLimits(), declared)
        except ValueError:
            return {}
        if "sha256:" + sha256_hex(jcs_bytes(rebuilt.to_json())) != digest:
            return {}
        self.notices.append(f"corpus.json records no ingest limits; those of {profile} were rebuilt and match the aer "
                            "stage's limits_sha256 (D-1001)")
        return rebuilt.overrides()

    # -------------------------------------------------------------------------------------- re-derive / carry
    def _profile_digest_map(self, row: IndexRow) -> dict[tuple[str, int], str] | None:
        pid, _, number = row.profile.rpartition("@")
        key = (pid, int(number))
        if key not in self._profile_digests:
            sha = self.catalogues.source_profile_sha256(*key)
            if sha is None:
                return None
            self._profile_digests[key] = sha
        return {key: self._profile_digests[key]}

    def _validate_aer(self, writer: CorpusWriter, data: bytes, row: IndexRow) -> Any:
        validator = AerValidator(store=writer.store, catalogues=self.registry, mode=self.plan.mode,  # type: ignore[arg-type]
                                 profile_digests=self._profile_digest_map(row))
        for line in data.splitlines(keepends=True):
            validator.feed(line)
        return validator.finish()

    def _register(self, writer: CorpusWriter, unit: _Unit, code: str, severity: str, stage: str, detail: str) -> None:
        entry = RegisterEntry(subject={"ex": unit.row.ex}, code=code, severity=severity, stage=stage, disposition="failed",
                              detail=_detail(detail))
        writer.add_register(entry)
        unit.codes[code] = severity

    def _fail(self, ex: str, stage: str, code: str, detail: str) -> None:
        self.failures.append({"subject": {"ex": ex}, "stage": stage, "code": code, "detail": _detail(detail)})

    def _load_unit(self, writer: CorpusWriter, row: IndexRow) -> _Unit | None:
        """Copy one execution's AER (seal re-verified, digest checked against the index; after a re-map the AER is the
        one the importer wrote) and run the AER validator, unless the reuse cache carries the execution."""
        try:
            data = writer.layout.aer_path(row.ex).read_bytes() if self.plan.remap else self.src.aer_bytes(row)
            aer = load_aer_bytes(data, verify=True)
        except AgentProvError as exc:
            self._fail(row.ex, "aer", "corpus.read.aer", f"the stored AER cannot be read ({exc.code})")
            return None
        if aer.execution_digest != row.aer_digest:
            self._fail(row.ex, "aer", "corpus.read.digest", "the AER's execution digest differs from the index")
            return None
        if not self.plan.remap:
            writer.write_aer(row.ex, data)
        unit = _Unit(row, data, aer, dict(self._codes_by_ex.get(row.ex, {})), {}, True)
        if not self._derives:
            unit.aer_ok = row.stages.get("aer") == "ok"
            return unit
        source_row = self.src_by_ex.get(row.ex)
        if source_row is not None and self._reusable(aer, source_row):
            unit.reuse_from = source_row
            unit.aer_ok = source_row.stages.get("aer") == "ok"
            for entry in self._source_stage_entries().get(row.ex, ()):
                if self._reuse_drop_tier4 and _tier_failure(entry):
                    continue  # RC-9: the verdict is recomputed without tier 4 in _carry, which registers its failure
                writer.add_register(entry)
                unit.codes[entry.code] = max(entry.severity, unit.codes.get(entry.code, "info"),
                                             key=lambda level: _SEVERITY_ORDER.get(level, 1))
            return unit
        self._recomputed_ex.append(row.ex)
        report = self._validate_aer(writer, data, row)
        aer_ok = bool(report.passed if self.plan.mode == "release" else report.ok)
        unit.aer_ok = aer_ok
        unit.aer_row = {
            "errors": sorted({f.code for f in report.errors}),
            "mode": self.plan.mode,
            "skipped": sorted(report.skipped),
            "verdict": "pass" if aer_ok else "fail",
        }
        if not aer_ok:
            self._register(writer, unit, "validate.failed", "error", "validate",
                           "aer validator: " + ",".join(unit.aer_row["errors"] or unit.aer_row["skipped"]))
            self._fail(row.ex, "validate", "validate.failed", "the AER validator reported errors")
        return unit

    # -------------------------------------------------------------------------------------- reuse cache
    def _reusable(self, aer: AerDocument, source: IndexRow) -> bool:
        """The reuse key of D-30: SEM, PROV and validation of an execution cannot change, so the source outputs are
        carried, when (a) its sealed AER is the source's (same execution digest); (b) the ``sem``, ``prov`` and
        ``validation`` stage definitions of this build have the source's ``fn_digest`` (engine and spec
        versions, code digests, profiles, options, mode, libraries); (c) the interpreter and the lockfile digest equal
        the source's; (d) every rule catalogue and the source profile the AER header declares have, in this package,
        the digest the source recorded; and (e) the source row has every output this run produces. Content-addressed
        only: no time, size or mtime enters the decision."""
        if not self.plan.reuse:
            return False
        if self._reuse_global is None:
            self._reuse_global = self._reuse_corpus_key()
        if not self._reuse_global or source.aer_digest != aer.execution_digest:
            return False
        until = self.plan.until
        if until in ("prov", "validation") and (source.prov is None or SPEC_ID not in source.prov):
            return False
        if until == "validation" and source.validation is None:
            return False
        if self.plan.semantics and set(source.sem or {}) != set(self.plan.semantics):
            return False
        return self._reuse_header_ok(aer.header)

    def _reuse_corpus_key(self) -> bool:
        current = _current_definitions(self.plan.semantics, self.plan.mode, self.catalogues,
                                       prov_conformance=self.plan.prov_conformance)  # PR-7
        needed = ["prov", "validation"] if self.plan.until == "validation" else ["prov"] if self.plan.until == "prov" else []
        if self.plan.semantics:
            needed.append("sem")
        # RC-9: a --skip-prov-conformance recompute of a fully validated source still carries SEM and PROV (their
        # definitions match); only its validation rows are rebuilt without tier 4 (_carry). The other way round (a full
        # recompute of a skipped source) runs tier 4, so it reuses nothing: that is the run that clears the mark.
        full = _current_definitions(self.plan.semantics, self.plan.mode, self.catalogues)["validation"]
        drop = False
        for name in needed:
            old, now = self.src_stages.get(name), current.get(name)
            if old is None or now is None or old.get("fn_digest") != now.get("fn_digest"):
                if (name == "validation" and old is not None and not self.plan.prov_conformance
                        and old.get("fn_digest") == full.get("fn_digest")):
                    drop = True
                    continue
                return False
        self._reuse_drop_tier4 = drop
        return (self.src_derivation.get("python") == _python()
                and self.src_derivation.get("lockfile_sha256") == _lockfile_sha256()
                and self._aer_code_unchanged())

    def _aer_code_unchanged(self) -> bool:
        """BF-33 stop-gap (until D-451 widens each stage's code-digest scope to its import closure): reuse also needs the
        ``aer`` stage's recorded ``adapter_code_sha256`` and ``engine_code_sha256`` to equal this build's. The SEM, PROV and
        validation code imports modules outside its own digest scope (``adapters/<family>/citation.py``,
        ``aer/evidence.py``, ``aer/reader.py``, ...), and most of those sit under these two scopes. The ``aer`` scope is
        :func:`agentprov.stage_scopes.aer_scope` (D-451 addendum, BF-39), as the importer records it."""
        aer = next(iter(stages_named(self.src_stages, "aer")), None)
        if aer is None:
            return False
        profile = aer.get("profile")
        if not isinstance(profile, str) or "@" not in profile:
            return False
        family = self.catalogues.profile_family(profile.rpartition("@")[0])
        if family is None:
            return False
        return (aer.get("adapter_code_sha256") == "sha256:" + code_sha256([f"adapters/{family}"])
                and aer.get("engine_code_sha256") == "sha256:" + code_sha256(aer_scope(family)))

    def _reuse_header_ok(self, header: Mapping[str, Any]) -> bool:
        aer_stage = self.src_stages.get("aer") or {}
        recorded_rules = dict(aer_stage.get("rules") or {})
        recorded_digests = dict(aer_stage.get("rules_sha256") or {})
        for ns, version in sorted(dict(header.get("rules") or {}).items()):
            key = f"rules:{ns}@{version}"
            if key not in self._reuse_header:
                digest = self._catalogue_digest(str(ns), int(version))
                self._reuse_header[key] = (digest is not None and recorded_rules.get(ns) == version
                                           and recorded_digests.get(ns) == "sha256:" + digest)
            if not self._reuse_header[key]:
                return False
        profile = header.get("profile")
        if not isinstance(profile, Mapping):
            return False
        key = f"profile:{profile.get('id')}@{profile.get('version')}:{profile.get('sha256')}"
        if key not in self._reuse_header:
            sha = None
            if isinstance(profile.get("id"), str) and isinstance(profile.get("version"), int):
                sha = self.catalogues.source_profile_sha256(profile["id"], profile["version"])
            declared = str(profile.get("sha256") or "").removeprefix("sha256:")
            self._reuse_header[key] = sha is not None and sha == declared and \
                aer_stage.get("profile_sha256") == "sha256:" + sha
        return self._reuse_header[key]

    def _source_stage_entries(self) -> dict[str, list[RegisterEntry]]:
        """The source register rows of the ``sem``, ``prov`` (``agentprov-prov/0.1``) and ``validate`` stages, by ex."""
        if self._stage_entries is None:
            out: dict[str, list[RegisterEntry]] = {}
            for entry in self.src.register():
                ex = entry.subject.get("ex")
                if ex is None or entry.stage not in ("sem", "prov", "validate"):
                    continue
                if entry.stage == "prov" and entry.detail.startswith(COMPAT_SPEC_ID + ":"):
                    continue
                out.setdefault(ex, []).append(entry)
            self._stage_entries = out
        return self._stage_entries

    @property
    def _derives(self) -> bool:
        """SEM/PROV/validation are produced by this run (a re-derive, or a re-map that reaches past the AER)."""
        return (self.plan.rederive or self.plan.remap) and self._post_aer

    def _complete(self, row: IndexRow) -> bool:
        until = self.plan.until
        if until == "validation":
            return row.validation is not None
        if until == "prov":
            return row.prov is not None
        if until == "sem":
            return row.sem is not None or not self.plan.semantics
        return True

    @property
    def _post_aer(self) -> bool:
        until = self.plan.until
        return (until == "sem" and bool(self.plan.semantics)) or until in ("prov", "validation")

    def rederive(self, writer: CorpusWriter) -> None:
        """Re-derive (or carry) every execution of the source, in index order (see the module docstring). After a
        re-map the executions are those the importer wrote into ``NEW``."""
        if self.plan.remap:
            writer.flush()
            rows = writer.index.rows()
            self._codes_by_ex = _codes_by_ex(writer.register.entries())
        else:
            rows = self.src_rows
        self.progress.emit(ProgressEvent("start", total=len(rows), fields={
            "command": self.plan.command, "plan": ",".join(self.plan.recomputed) or "carry",
            "workers": self.plan.jobs}))
        scratch = Path(tempfile.mkdtemp(prefix="agentprov-derive-"))
        pool: WorkerPool | None = None
        try:
            scratch_store = RawObjectStore(scratch / "prov-inputs")
            charges: dict[str, int] = {}  # D-554: AER digest -> the prov job's memory charge (timing only)
            if self._derives:
                limits = WorkerLimits(kind_rss_bytes={**KIND_RSS_BYTES, "prov": self.prov_cap})  # D-935
                pool = WorkerPool(store_root=scratch_store.objects_dir, workers=self.plan.jobs, limits=limits,
                                  in_process=self.plan.in_process, release=self.plan.mode == "release",
                                  charge=lambda job, _root: charges.get(str(job.inputs[0]["sha256"]), self.prov_cap))
            batch_size = self.plan.batch_size or batch_for(pool.workers if pool is not None else 1)
            with ThreadPoolExecutor(max_workers=1, thread_name_prefix="agentprov-derive") as background:
                pending: tuple[list[tuple[_Unit, str | None]], Future[list[JobResult]]] | None = None
                for start in range(0, len(rows), batch_size):
                    units: list[_Unit] = []
                    for row in rows[start : start + batch_size]:
                        done = writer.has_execution(row.ex)
                        if done is not None and done.aer_digest == row.aer_digest and self._complete(done):
                            self.counters["resumed"] += 1
                            continue
                        unit = self._load_unit(writer, row)
                        if unit is not None:
                            units.append(unit)
                    staged = [(u, scratch_store.put(u.data, ext="jsonl").sha256
                               if pool is not None and u.aer_ok and u.reuse_from is None and not self._aer_only(u)
                               else None) for u in units]
                    for u, sha in staged:
                        if sha is not None:
                            charges[sha] = self._prov_charge(u.row)
                    self._stage_hints(scratch_store, staged)
                    future: Future[list[JobResult]] = background.submit(self._run_jobs, pool, staged, dict(self._hints))
                    if pending is not None:
                        self._finish_batch(writer, scratch_store, pending[0], pending[1].result())
                    pending = (staged, future)
                if pending is not None:
                    self._finish_batch(writer, scratch_store, pending[0], pending[1].result())
        finally:
            with contextlib.suppress(AgentProvError):
                writer.flush()
            shutil.rmtree(scratch, ignore_errors=True)

    def _prov_charge(self, row: IndexRow) -> int:
        """D-554: the memory charge of re-deriving ``row``, from its stored PROV size in the source corpus (prov-perf's
        model); the ``prov`` cap when the source has no PROV for it. Timing only: a charge never changes an output."""
        source = self.src_by_ex.get(row.ex)
        recorded = (source.prov_paths or {}).get(SPEC_ID) if source is not None else None
        if recorded is None:
            return self.prov_cap
        try:
            size = (self.src.root / recorded).stat().st_size
        except OSError:
            return self.prov_cap
        return prov_charge(size, cap=self.prov_cap)

    def _prov_cap(self) -> int:
        """D-935: the ``prov`` cap of the source's profile as its ``aer`` stage records it (``id@version``), else the
        default. Timing and admission only."""
        aer = next(iter(stages_named(self.src_stages, "aer")), None)
        profile = aer.get("profile") if aer is not None else None
        if not isinstance(profile, str) or "@" not in profile:
            return PROV_CAP
        pid, _, version = profile.rpartition("@")
        if not version.isdigit():
            return PROV_CAP
        return int(self.catalogues.worker_caps(pid, int(version)).get("prov", PROV_CAP))

    @staticmethod
    def _run_jobs_static(pool: WorkerPool | None, staged: Sequence[tuple[_Unit, str | None]], params: Mapping[str, Any],
                         hints: Mapping[str, str] | None = None) -> list[JobResult]:
        digests = [sha for _u, sha in staged if sha is not None]
        if pool is None or not digests:
            return []
        hints = hints or {}
        jobs = [Job(key=f"{n:09d}", kind="prov", params=_with_hint(params, sha in hints),
                    inputs=({"sha256": sha, "role": "aer"},
                            *(({"sha256": hints[sha], "role": "fidelity"},) if sha in hints else ())))
                for n, sha in enumerate(digests)]
        return pool.run(jobs)

    def _job_params(self) -> dict[str, Any]:
        until = self.plan.until
        params = {"spec": SPEC_ID, "strict": self.plan.mode == "release", "validate": until == "validation",
                  "semantics": list(self.plan.semantics), "derive": until in ("prov", "validation"),
                  **({} if self.plan.prov_conformance else {"conformance": False})}  # G2c-5: before the cache param
        if self.validation_cache is not None and params["validate"] and params.get("conformance", True):
            params["fidelity"] = {"collect": True, "hint": False}  # G2c-5: never for a run that skips tier 4
        return params

    def _run_jobs(self, pool: WorkerPool | None, staged: Sequence[tuple[_Unit, str | None]],
                  hints: Mapping[str, str] | None = None) -> list[JobResult]:
        return self._run_jobs_static(pool, staged, self._job_params(), hints)

    def _stage_hints(self, scratch: RawObjectStore, staged: Sequence[tuple[_Unit, str | None]]) -> None:
        """D-550: stage the cache's entry for each staged unit's expected PROV (the source row's stored digest)."""
        cache = self.validation_cache
        if cache is None or "fidelity" not in self._job_params():
            return
        for unit, sha in staged:
            source = self.src_by_ex.get(unit.row.ex)
            stored = (source.prov or {}).get(SPEC_ID) if source is not None else None
            if sha is None or stored is None or stored.digest is None:
                continue
            hint = cache.hint(stored.digest)
            if hint is not None:
                self._hints[sha] = scratch.put(hint, ext="json").sha256
                self._hint_refs[self._hints[sha]] += 1

    def _drop_hint(self, scratch: RawObjectStore, sha: str) -> None:
        hint = self._hints.pop(sha, None)
        if hint is None:
            return
        self._hint_refs[hint] -= 1
        if self._hint_refs[hint] <= 0:
            del self._hint_refs[hint]
            with contextlib.suppress(OSError):
                path = scratch.path_for(hint, "json")
                os.chmod(path, 0o600)
                path.unlink()

    def _finish_batch(self, writer: CorpusWriter, scratch: RawObjectStore, staged: Sequence[tuple[_Unit, str | None]],
                      results: Sequence[JobResult]) -> None:
        pending = iter(results)
        for unit, sha in staged:
            if not self._derives:
                self._carry(writer, unit)
                self.counters["carried"] += 1
                continue
            if unit.reuse_from is not None:
                self._carry(writer, unit, unit.reuse_from)
                self.counters["reused"] += 1
                continue
            self.counters["recomputed"] += 1
            if self._aer_only(unit):  # V-7: the source holds it at the AER only; recompute reproduces that
                self._index(writer, unit, sem=None, prov=None, validation=None, sem_docs={})
                continue
            result = next(pending) if sha is not None else None
            try:
                self._finish_unit(writer, unit, result)
            finally:
                if result is not None:
                    result.close()
                if sha is not None:
                    self._drop_hint(scratch, sha)
                    with contextlib.suppress(OSError):
                        path = scratch.path_for(sha, "jsonl")
                        os.chmod(path, 0o600)
                        path.unlink()

    # the importer's finish(), re-implemented over the stored AER (adapters/runner/importer.py _Pipeline.finish)
    def _aer_only(self, unit: _Unit) -> bool:
        """Pre-round verification V-7: ``recompute`` reproduces each execution's coverage. An execution the source holds
        at the AER only (a later ``import --until aer`` run of a corpus mapped further, which keeps its furthest
        ``until``) gets no SEM, PROV or validation in NEW; before, it gained them and the dry run still called it
        identical, because the comparison looks only at the layers the source row holds. ``derive`` adds layers by
        design and is unchanged."""
        if self.plan.command != "recompute":
            return False
        source = self.src_by_ex.get(unit.row.ex)
        return source is not None and not source.sem and not {s for s in (source.prov or {}) if s != COMPAT_SPEC_ID} \
            and source.validation is None

    def _finish_unit(self, writer: CorpusWriter, unit: _Unit, result: JobResult | None) -> None:
        semantics = self.plan.semantics
        until = self.plan.until
        sem: dict[str, StageOutput] | None = None
        prov: dict[str, StageOutput] | None = None
        validation: StageOutput | None = None
        sem_docs: dict[str, SemDocument] = {}
        row: dict[str, Any] = {"aer": unit.aer_row, "checks": {"aer.validator": unit.aer_row["verdict"]}}
        if self._post_aer:
            if result is None:
                sem = {ref: StageOutput("skipped") for ref in semantics} or None
                prov = {SPEC_ID: StageOutput("skipped")} if until in ("prov", "validation") else None
            else:
                sem, tier3, sem_docs = self._sem_result(writer, unit, result)
                row["checks"].update(tier3)
                if until in ("prov", "validation"):
                    prov, tier4 = self._prov_result(writer, unit, result)
                    if tier4 is not None:
                        row.update(spec=SPEC_ID, versions=tier4["versions"])
                        row["checks"].update(tier4["checks"])
        if until == "validation":
            verdicts = [unit.aer_row["verdict"]]
            if prov is not None and prov[SPEC_ID].state == "ok" and all(o.state == "ok" for o in (sem or {}).values()):
                verdicts.append(self._tier4_verdict(row))
            else:
                verdicts.append("fail")
            row["verdict"] = "pass" if set(verdicts) == {"pass"} else "fail"
            if row["verdict"] == "pass":
                self.counters["validated"] += 1
            elif unit.aer_ok and prov is not None and prov[SPEC_ID].state == "ok":
                release = self.plan.mode == "release"
                failing = sorted(k for k, v in row["checks"].items() if v == "fail" or (v == "skipped" and release))
                self._register(writer, unit, "validate.failed", "error", "validate", "tiers 3-4: " + ",".join(failing))
                self._fail(unit.row.ex, "validate", "validate.failed", "tier-3 or tier-4 checks failed")
            validation = StageOutput("ok" if row["verdict"] == "pass" else "failed", writer.add_validation(unit.row.ex, row))
        self._index(writer, unit, sem=sem, prov=prov, validation=validation, sem_docs=sem_docs)

    def _tier4_verdict(self, row: Mapping[str, Any]) -> str:
        statuses = [v for k, v in row["checks"].items() if k != "aer.validator"]
        bad = {"fail", "skipped"} if self.plan.mode == "release" else {"fail"}
        missing = not statuses and self.plan.prov_conformance  # ultrareview pipeline #2, as in the importer
        return "fail" if missing or any(s in bad for s in statuses) else "pass"

    def _sem_result(self, writer: CorpusWriter, unit: _Unit, result: JobResult
                    ) -> tuple[dict[str, StageOutput] | None, dict[str, str], dict[str, SemDocument]]:
        semantics = self.plan.semantics
        if not semantics:
            return None, {}, {}
        if not result.ok:
            code = result.error.code if result.error is not None else "worker.error"
            return {ref: self._sem_failed(writer, unit, ref, code) for ref in semantics}, {}, {}
        out: dict[str, StageOutput] = {}
        docs: dict[str, SemDocument] = {}
        for frame in result.json:
            if "sem_error" in frame:
                ref = str(frame["sem_error"]["profile"])
                out[ref] = self._sem_failed(writer, unit, ref, str(frame["sem_error"]["code"]))
        for member in result.members:
            if member.header.get("role") != "sem":
                continue
            ref, data = str(member.header["profile"]), member.read_bytes()
            try:
                doc = load_sem_bytes(data)
            except AgentProvError as exc:
                out[ref] = self._sem_failed(writer, unit, ref, exc.code)
                continue
            if doc.ex != unit.row.ex or doc.aer_digest != unit.aer.execution_digest:
                out[ref] = self._sem_failed(writer, unit, ref, "sem.aer_digest")
                continue
            writer.write_sem(ref, unit.row.ex, data)
            out[ref] = StageOutput("ok", doc.digest)
            docs[ref] = doc
        for ref in semantics:
            if ref not in out:
                out[ref] = self._sem_failed(writer, unit, ref, "sem.no_output")
        checks: dict[str, str] = {}
        for frame in result.json:
            if "sem_validation" in frame:
                checks.update(frame["sem_validation"]["checks"])
        self.counters["annotated"] += sum(1 for o in out.values() if o.state == "ok")
        return out, checks, docs

    def _sem_failed(self, writer: CorpusWriter, unit: _Unit, ref: str, code: str) -> StageOutput:
        self._register(writer, unit, "sem.failed", "error", "sem", f"{ref}: {code}")
        self._fail(unit.row.ex, "sem", "sem.failed", f"{ref}: {code}")
        return StageOutput("failed")

    def _prov_result(self, writer: CorpusWriter, unit: _Unit, result: JobResult
                     ) -> tuple[dict[str, StageOutput], dict[str, Any] | None]:
        if not result.ok:
            code = result.error.code if result.error is not None else "worker.error"
            return self._prov_failed(writer, unit, code), None
        errors = [frame["prov_error"] for frame in result.json if "prov_error" in frame]
        members = [m for m in result.members if m.header.get("role") == "prov"]
        if errors or not members:
            return self._prov_failed(writer, unit, str(errors[0]) if errors else "prov.no_output"), None
        data = members[0].read_bytes()
        digest = writer.write_prov(SPEC_ID, unit.row.ex, data)
        self.counters["derived"] += 1
        tier4 = next((frame["validation"] for frame in result.json if "validation" in frame), None)
        if self.validation_cache is not None:  # D-550: the job's completed round trip, checked against these bytes
            for frame in result.json:
                if "fidelity" in frame:
                    self.validation_cache.store_frame(data, frame["fidelity"])
        return {SPEC_ID: StageOutput("ok", digest)}, tier4

    def _prov_failed(self, writer: CorpusWriter, unit: _Unit, code: str) -> dict[str, StageOutput]:
        self._register(writer, unit, "prov.failed", "error", "prov", code)
        self._fail(unit.row.ex, "prov", "prov.failed", code)
        return {SPEC_ID: StageOutput("failed")}

    def _source_validation_rows(self) -> dict[str, dict[str, Any]]:
        if self._source_validation is None:
            self._source_validation = {row["ex"]: row for row in self.src.validation_results()}
        return self._source_validation

    def _carry(self, writer: CorpusWriter, unit: _Unit, source: IndexRow | None = None) -> None:
        """Copy the source's SEM, PROV (``agentprov-prov/0.1``) and validation outputs of one execution unchanged."""
        row = source if source is not None else unit.row
        sem_docs: dict[str, SemDocument] = {}
        for ref, out in (row.sem or {}).items():
            if out.digest is None:
                continue
            doc = self.src.read_sem(row, ref)
            writer.write_sem(ref, row.ex, self.src.read_bytes(self.src.layout.sem_relpath(ref, row.ex)))
            sem_docs[ref] = doc
        prov = {spec: out for spec, out in (row.prov or {}).items() if spec != COMPAT_SPEC_ID} or None
        for spec, out in (prov or {}).items():
            if out.digest is not None:
                writer.write_prov(spec, row.ex, self.src.prov_bytes(row, spec))
        validation = row.validation
        if validation is not None:
            body = self._source_validation_rows().get(row.ex)
            if body is not None and source is not None and self._reuse_drop_tier4:
                validation = self._rebuilt_validation(writer, unit, row, body, prov)
            elif body is not None:
                digest = writer.add_validation(row.ex, {k: v for k, v in body.items() if k != "ex"})
                validation = StageOutput(validation.state, digest)
        self._index(writer, unit, sem=None if row.sem is None else dict(row.sem), prov=prov, validation=validation,
                    sem_docs=sem_docs)

    def _rebuilt_validation(self, writer: CorpusWriter, unit: _Unit, row: IndexRow, body: Mapping[str, Any],
                            prov: Mapping[str, StageOutput] | None) -> StageOutput:
        """RC-9: the validation row a ``--skip-prov-conformance`` recompute writes for an execution whose SEM and PROV
        are carried from a fully validated source: the source row's AER-validator and tier-3 checks (the same
        definitions computed them), no tier-4 check, ``spec`` or ``versions``, and the verdict and register row
        :meth:`_finish_unit` gives such a row."""
        tier3 = tuple(f"{ref}:" for ref in self.plan.semantics)
        checks = {k: v for k, v in dict(body.get("checks") or {}).items() if k == "aer.validator" or k.startswith(tier3)}
        new: dict[str, Any] = {"aer": body.get("aer"), "checks": dict(sorted(checks.items()))}
        prov_ok = prov is not None and SPEC_ID in prov and prov[SPEC_ID].state == "ok"
        sem_ok = all(o.state == "ok" for o in (row.sem or {}).values())
        verdicts = [checks.get("aer.validator"), self._tier4_verdict(new) if prov_ok and sem_ok else "fail"]
        new["verdict"] = "pass" if set(verdicts) == {"pass"} else "fail"
        if new["verdict"] == "pass":
            self.counters["validated"] += 1
        elif unit.aer_ok and prov_ok:
            failing = sorted(k for k, v in checks.items() if v == "fail" or (v == "skipped" and self.plan.mode == "release"))
            self._register(writer, unit, "validate.failed", "error", "validate", "tiers 3-4: " + ",".join(failing))
            self._fail(row.ex, "validate", "validate.failed", "tier-3 or tier-4 checks failed")
        return StageOutput("ok" if new["verdict"] == "pass" else "failed", writer.add_validation(row.ex, new))

    # -------------------------------------------------------------------------------------- index entries
    def _index(self, writer: CorpusWriter, unit: _Unit, *, sem: Mapping[str, StageOutput] | None,
               prov: Mapping[str, StageOutput] | None, validation: StageOutput | None,
               sem_docs: Mapping[str, SemDocument]) -> None:
        row = unit.row
        extra = self._views_and_compat(writer, row, unit.aer, unit.codes)
        prov_all = dict(prov or {})
        prov_all.update(extra)
        entry = self._entry(row, unit.aer, unit.codes, sem=sem, prov=prov_all or None, validation=validation,
                            aer_state="ok" if unit.aer_ok else "failed", sem_docs=sem_docs)
        writer.index.discard(row.ex)  # a re-map's working row (written by the importer) is replaced
        writer.add_execution(entry)
        self.progress.emit(ProgressEvent("unit_done", unit=row.ex, status="derived", codes=tuple(sorted(unit.codes))))

    def _entry(self, row: IndexRow, aer: AerDocument, codes: Mapping[str, str], *, sem: Mapping[str, StageOutput] | None,
               prov: Mapping[str, StageOutput] | None, validation: StageOutput | None, aer_state: str,
               sem_docs: Mapping[str, SemDocument]) -> ExecutionEntry:
        header = aer.header
        seal_codes = {str(i.get("code")) for i in aer.seal.get("issues", ()) if isinstance(i, Mapping)}
        members = None
        if sem is not None and prov is not None and validation is not None:
            with_output = [spec for spec, out in prov.items() if out.digest is not None]
            ok_docs = {ref: doc for ref, doc in sem_docs.items() if (sem.get(ref) or StageOutput("failed")).state == "ok"}
            try:
                members = facet_members(aer, ok_docs, repeat=row.attempt, prov_specs=with_output)
            except (FacetError, AgentProvError, ValueError) as exc:
                self.counters["facets_failed"] += 1
                self._fail(row.ex, "index", "corpus.facet.invalid", f"facets not computed ({getattr(exc, 'code', 'value')})")
        else:
            self.counters["working_rows"] += 1
        artefacts = list(header.get("artifacts", ()))
        raw = tuple(RawRef(str(a["sha256"]), str(a["role"]), True) for a in artefacts) if artefacts else tuple(row.raw)
        return ExecutionEntry(
            ex=row.ex, mode=row.mode, unit=str(header.get("unit")), source_id=row.source_id,
            snapshot_ids=tuple(row.snapshot_ids), source_key=row.source_key, raw=raw, adapter=row.adapter,
            profile=row.profile, aer_digest=aer.execution_digest, stages={"raw": "ok", "aer": aer_state},
            completeness=completeness_of(aer),
            execution_observed=header.get("unit") != "outcome_only" and "no_execution_observed" not in seal_codes,
            issues=tuple(sorted(codes)), attempt=row.attempt, prov=None if prov is None else dict(prov),
            validation=validation, sem=None if sem is None else dict(sem), facet_members=members,
        )  # fmt: skip

    # -------------------------------------------------------------------------------------- views and compat
    def _views_and_compat(self, writer: CorpusWriter, row: IndexRow, aer: AerDocument,
                          codes: dict[str, str]) -> dict[str, StageOutput]:
        """``views/transcript-v1`` and the ``adprov-v2.3-compat`` graph of one execution: computed, carried or absent.
        Returns the compat stage (``{}`` when compat is neither computed nor carried)."""
        out: dict[str, StageOutput] = {}
        plan = self.plan
        src_row = self.src_by_ex.get(row.ex)
        view_bytes: bytes | None = None
        if plan.views or plan.compat:
            renderer = VIEW_RENDERERS.get(str((aer.header.get("adapter") or {}).get("id")))
            if renderer is None:
                if plan.compat:
                    out[COMPAT_SPEC_ID] = StageOutput("not_applicable")
            else:
                from agentprov.views import transcript_v1

                try:
                    document = getattr(transcript_v1, renderer)(aer)
                    view_bytes = transcript_v1.serialise(document)
                except AgentProvError as exc:
                    self._fail(row.ex, "views", "view.transcript_v1", f"the transcript/v1 view failed ({exc.code})")
                    document = None
                if plan.views and view_bytes is not None:
                    path = writer.layout.view_path(TRANSCRIPT_VIEW, row.ex)
                    path.parent.mkdir(parents=True, exist_ok=True)
                    atomic_write_bytes(path, view_bytes)
                if plan.compat:
                    out[COMPAT_SPEC_ID] = self._compat(writer, row, document, codes)
        if plan.carry_views and not plan.views and src_row is not None:
            label = self.src.layout.view_relpath(TRANSCRIPT_VIEW, row.ex)
            if self.src.exists(label):
                path = writer.layout.view_path(TRANSCRIPT_VIEW, row.ex)
                path.parent.mkdir(parents=True, exist_ok=True)
                atomic_write_bytes(path, self.src.read_bytes(label))
        if plan.carry_compat and not plan.compat and src_row is not None:
            stage = (src_row.prov or {}).get(COMPAT_SPEC_ID)
            if stage is not None:
                if stage.digest is not None:
                    writer.write_prov(COMPAT_SPEC_ID, row.ex, self.src.prov_bytes(src_row, COMPAT_SPEC_ID))
                    self.compat_loaded = True
                out[COMPAT_SPEC_ID] = stage
        return out

    def _compat(self, writer: CorpusWriter, row: IndexRow, document: Any, codes: dict[str, str]) -> StageOutput:
        from agentprov.prov.specs import load_compat_spec

        if document is None:
            self._compat_failed(writer, row, "view.transcript_v1", codes)
            return StageOutput("failed")
        spec = load_compat_spec()
        try:
            data = spec.serialise(spec.build(document))
        except Exception as exc:  # noqa: BLE001 - the frozen oracle may raise anything on unexpected input
            self._compat_failed(writer, row, type(exc).__name__, codes)
            return StageOutput("failed")
        self.compat_written = True
        return StageOutput("ok", writer.write_prov(COMPAT_SPEC_ID, row.ex, data))

    def _compat_failed(self, writer: CorpusWriter, row: IndexRow, why: str, codes: dict[str, str]) -> None:
        entry = RegisterEntry(subject={"ex": row.ex}, code="prov.failed", severity="error", stage="prov",
                              disposition="failed", detail=_detail(f"{COMPAT_SPEC_ID}: {why}"))
        writer.add_register(entry)
        codes["prov.failed"] = "error"
        self._fail(row.ex, "prov", "prov.failed", f"{COMPAT_SPEC_ID}: {why}")

    # -------------------------------------------------------------------------------------- after a re-map
    def complete_remap(self, writer: CorpusWriter) -> None:
        """After ``import_source`` wrote working rows: views/compat and full rows for every execution (index rebuild)."""
        writer.flush()
        if self._post_aer:
            self.rederive(writer)
            return
        reader = CorpusReader(writer.partial, state=WORKING, limits=self.src.limits)
        by_ex = _codes_by_ex(writer.register.entries())
        for row in list(writer.index.rows()):
            aer = reader.read_aer(row)
            sem_docs = reader.read_sem_all(row)
            codes = dict(by_ex.get(row.ex, {}))
            extra = self._views_and_compat(writer, row, aer, codes)
            prov = dict(row.prov or {})
            prov.update(extra)
            entry = self._entry(row, aer, codes, sem=None if row.sem is None else dict(row.sem), prov=prov or None,
                                validation=row.validation, aer_state=str(row.stages.get("aer", "ok")), sem_docs=sem_docs)
            writer.index.discard(row.ex)
            writer.add_execution(entry)
        writer.flush()

    # -------------------------------------------------------------------------------------- documents
    def _stage_definitions(self, writer: CorpusWriter) -> dict[StageKey, dict[str, Any]]:
        """The stages of ``NEW``: recomputed ones from this run, carried ones from the source (H.8.2). Every ``expand``
        definition is kept (D-380)."""
        out: dict[StageKey, dict[str, Any]] = {}
        written = _stages_of(writer.read_document(writer.layout.derivation)) if self.plan.remap else {}
        recomputed = set(self.plan.recomputed)
        for name in _ORDER:
            if name == "expand":
                chosen = written if name in recomputed else self.src_stages
                out.update({key: dict(d) for key, d in chosen.items() if isinstance(key, tuple) and key[0] == name})
                continue
            if name in recomputed:
                if name == "aer":
                    if name in written:
                        out[name] = written[name]
                    continue
                if name == "sem":
                    infos = [self.catalogues.semantics(ref) for ref in self.plan.semantics]
                    if all(i is not None for i in infos) and infos:
                        out[name] = sem_stage_definition([i for i in infos if i is not None])
                elif name == "prov":
                    out[name] = prov_stage_definition()
                elif name == "validation":
                    out[name] = validation_stage_definition(self.plan.semantics, self.plan.mode,
                                                            prov_conformance=self.plan.prov_conformance)
                elif name == "views":
                    out[name] = views_stage_definition()
                elif name == "compat":
                    out[name] = compat_stage_definition()
            elif name in self.src_stages:
                out[name] = self.src_stages[name]
        return out

    def _manifest(self, writer: CorpusWriter, stages: Mapping[Any, Any]) -> dict[str, Any]:
        base = self._base_manifest()
        # G2c-5: the mark follows the validation layer NEW holds. A recomputed one carries it only when skipped (a full
        # recompute clears it); a carried one keeps the source's mark (_SEALED_ONLY drops the key, so it is set here).
        from agentprov.corpus.conformance import conformance_skipped

        recomputed_validation = "validation" in self.plan.recomputed
        if (recomputed_validation and not self.plan.prov_conformance) or (
                not recomputed_validation and conformance_skipped(self.manifest)):
            base["validation"] = {"prov_conformance": "skipped"}
        if self.plan.remap:
            produced = writer.read_document(writer.layout.manifest) or {}
            for key in ("format", "adapters", "profiles", "formats", "limits", "selection", "partial", "mode", "corpus_id"):
                if key in produced:
                    base[key] = produced[key]
            if isinstance(produced.get("sources"), list):
                base["sources"] = _merge_sources(produced["sources"], self.manifest.get("sources"))
        if isinstance(base.get("selection"), Mapping):
            base["selection"] = {**base["selection"], "until": self.plan.until}
        if self.plan.rederive and self.plan.semantics:
            profiles = dict(base.get("profiles") or {})
            profiles["semantics"] = [{"id": ref.rpartition("@")[0], "version": int(ref.rpartition("@")[2])}
                                     for ref in self.plan.semantics]
            base["profiles"] = profiles
        rows = writer.index.rows()
        register = writer.register.entries()
        not_imported = Counter(e.code for e in register if e.disposition == "not_imported")
        sources = base.get("sources")
        if isinstance(sources, list) and sources and isinstance(sources[0], dict):
            snapshots = sources[0].get("snapshots")
            if isinstance(snapshots, list) and len(snapshots) == 1 and isinstance(snapshots[0], dict):
                counts = dict(snapshots[0].get("counts") or {})
                counts.update({"executions": len(rows), "not_imported": sum(not_imported.values())})
                snapshots[0] = {**snapshots[0], "counts": counts}
        formats = dict(base.get("formats") or {})
        if any(r.sem for r in rows):
            formats["sem"] = "sem/0.1"
        base["formats"] = formats
        prov_specs = sorted({spec for r in rows for spec, out in (r.prov or {}).items() if out.digest is not None},
                            key=lambda s: (s != SPEC_ID, s))
        base["prov_specs"] = prov_specs
        base["oracle_specs"] = [{"gate_report": None, "spec": COMPAT_SPEC_ID, "status": REGRESSION_ORACLE}] \
            if COMPAT_SPEC_ID in prov_specs else []
        producer = dict(base.get("producer") or {})
        producer.update({
            "agentprov_version": __version__,
            "python": _python(),
            "platform": {"system": platform.system(), "release": platform.release(), "machine": platform.machine()},
            "isolation": "in-process" if self.plan.in_process else "t1",
            "key_distributions": _versions("prov", "rdflib", "rfc8785", "pyyaml", "agentprov-capture"),
            "lockfile_sha256": _lockfile_sha256(),
        })
        base["producer"] = producer
        base["counts"] = {
            "executions": len(rows),
            "by_unit": dict(sorted(Counter(r.unit for r in rows).items())),
            "by_status": dict(sorted(Counter(r.status for r in rows).items())),
            "by_completeness": dict(sorted(Counter(r.completeness for r in rows).items())),
            "issues_by_code": dict(sorted(Counter(e.code for e in register).items())),
            "not_imported_by_code": dict(sorted(not_imported.items())),
            "members": writer.members.counts() if len(writer.members) else None,
        }
        return base

    def write_documents(self, writer: CorpusWriter) -> dict[StageKey, dict[str, Any]]:
        writer.plan_build_stages(self.plan.recomputed)
        stages = self._stage_definitions(writer)
        derivation: dict[str, Any] = {
            "format": "agentprov-derivation/0.1",
            "stages": in_order(stages, _ORDER),
            "lockfile_sha256": _lockfile_sha256(),
            "python": _python(),
        }
        if self._derives:
            derivation["reuse"] = self._reuse_record(writer)
        writer.write_document(writer.layout.derivation, derivation)
        writer.write_document(writer.layout.manifest, self._manifest(writer, stages))
        return stages

    def _reuse_record(self, writer: CorpusWriter) -> dict[str, Any]:
        """The reuse record of ``derivation.json``: whether the cache was on, and which executions this build
        recomputed (sorted; every other execution's SEM/PROV/validation was carried from the source)."""
        if not self.plan.reuse:
            return {"enabled": False}
        recomputed = sorted(set(self._recomputed_ex), key=lambda e: e.encode("ascii"))
        total = len(writer.index)
        return {"enabled": True, "recomputed": len(recomputed), "recomputed_executions": recomputed,
                "reused": total - len(recomputed)}

    # -------------------------------------------------------------------------------------- finish and compare
    def finish(self, writer: CorpusWriter) -> RederiveReport:
        """Write ``derivation.json`` and ``corpus.json``, compare ``NEW`` with the source and return the report."""
        writer.flush()
        new_stages = self.write_documents(writer)
        reader = CorpusReader(writer.partial, state=WORKING, limits=self.src.limits)
        report = self.compare(reader, new_stages)
        return report

    def compare(self, new: CorpusReader, new_stages: Mapping[Any, Mapping[str, Any]]) -> RederiveReport:
        """H.8.4 comparison of ``NEW`` with the source (see the module docstring)."""
        report = RederiveReport(command=self.plan.command, corpus_id=str(self.manifest.get("corpus_id") or ""),
                                strict=self.plan.strict)
        changed_stage: dict[str, bool] = {}
        for name in _ORDER:
            olds, nows = stages_named(self.src_stages, name), stages_named(new_stages, name)
            if olds and nows:
                # several expansions (D-380) compare as sets of declared identities and code digests (JCS order)
                changed_stage[name] = _identities(olds) != _identities(nows)
                if {d.get("limits_sha256") for d in olds} != {d.get("limits_sha256") for d in nows}:
                    self.notices.append(f"{name}: the ingest limits changed (limits_sha256); a notice only, it explains no "
                                        "output difference (D-31 addendum)")
                if not changed_stage[name] and _codes(olds) != _codes(nows):
                    self.notices.append(f"{name}: the code digest changed and every declared version is the same "
                                        "(a refactor passes only if every output is identical; H.8.4(2))")
            else:
                changed_stage[name] = False
        report.stage_changes = changed_stage
        report.recomputed = list(self.plan.recomputed)
        counts: Counter[str] = Counter({name: 0 for name in (*CLASSES, "index_refreshed")})
        new_rows = {row.ex: row for row in new.index() if self.scope is None or row.ex in self.scope}
        old_validation = {r["ex"]: r for r in self.src.validation_results()}
        shown = 0
        for ex in sorted(set(new_rows) | set(self.src_by_ex)):
            old_row, new_row = self.src_by_ex.get(ex), new_rows.get(ex)
            outputs, failed, unverified = self._compare_execution(new, old_row, new_row)
            if ex in self.absent_ex and (outputs or failed):  # H.4.5(6): it needs an object absent on purpose
                failed, unverified = False, True
            if failed:
                cls = "failed"
            elif not outputs:
                cls = "unverified" if unverified else "identical"
            elif ex in self.absent_ex:
                cls = "unverified"
            else:
                explained = all(any(changed_stage.get(s, False) for s in _UPSTREAM[o.split(":", 1)[0]]) for o in outputs)
                cls = "changed_explained" if explained else ("unverified" if unverified else "unexplained_change")
            counts[cls] += 1
            if old_row is not None and new_row is not None and _refreshed(old_row, new_row):
                counts["index_refreshed"] += 1
            if cls != "identical":
                report.changes.append({"ex": ex, "class": cls, "outputs": sorted(outputs)})
                if shown < self.plan.show_diff and outputs and old_row is not None and new_row is not None:
                    report.details.extend(self._details(new, old_row, new_row, outputs, old_validation))
                    shown += 1
        if self.scope is None:
            renames = _fn_renames(stages_named(self.src_stages, "expand"), stages_named(new_stages, "expand"))
            corpus_bad = self._compare_corpus_files(new, report, changed_stage, renames)
        else:
            corpus_bad = 0
            self.notices.append("a sample was re-derived: the corpus-level files (register, origins, members) were not "
                                "compared")
        counts["corpus_unexplained"] = corpus_bad
        counts["selected"] = len(self.src_rows)
        counts["stages_run"] = len(self.plan.recomputed)
        counts.update({k: v for k, v in self.counters.items() if k not in counts})
        report.counters = {k: int(v) for k, v in sorted(counts.items())}
        report.issues_by_code = dict(sorted(self.issues.items()))
        report.failures = sorted(self.failures, key=lambda f: (jcs_bytes(f["subject"]), f["stage"], f["code"]))
        report.notices = list(dict.fromkeys(self.notices))
        report.compat_written = self.compat_written
        report.compat_loaded = self.compat_loaded
        return report

    def _rules_unavailable(self, header: Mapping[str, Any]) -> bool:
        for ns, version in dict(header.get("rules") or {}).items():
            key = (str(ns), int(version))
            if key not in self._unavailable:
                self._unavailable[key] = self._catalogue_digest(*key) is None
            if self._unavailable[key]:
                return True
        return False

    def _compare_execution(self, new: CorpusReader, old: IndexRow | None, now: IndexRow | None
                           ) -> tuple[list[str], bool, bool]:
        """``(changed outputs, failed, unverified)`` of one execution."""
        if old is None or now is None:
            if old is not None:
                return ["aer"], True, False
            return ["aer"], False, False
        changed: list[str] = []
        if old.aer_digest != now.aer_digest or sha256_hex(self.src.aer_bytes(old)) != sha256_hex(new.aer_bytes(now)):
            changed.append("aer")
        for ref in sorted(set(old.sem or {}) | set(now.sem or {})) if old.sem is not None else ():
            a, b = (old.sem or {}).get(ref), (now.sem or {}).get(ref)
            if (a.digest if a else None) != (b.digest if b else None) or (a.state if a else None) != (b.state if b else None):
                changed.append(f"sem:{ref}")
        for spec in sorted(set(old.prov or {})):
            a, b = (old.prov or {}).get(spec), (now.prov or {}).get(spec)
            if (a.digest if a else None) != (b.digest if b else None) or (a.state if a else None) != (b.state if b else None):
                changed.append(("compat" if spec == COMPAT_SPEC_ID else "prov") + f":{spec}")
        if old.validation is not None:
            a_v, b_v = old.validation, now.validation
            if b_v is None or (a_v.digest, a_v.state) != (b_v.digest, b_v.state):
                changed.append("validation")
        label_old = self.src.layout.view_relpath(TRANSCRIPT_VIEW, old.ex)
        if self.src.exists(label_old):
            label_new = new.layout.view_relpath(TRANSCRIPT_VIEW, now.ex)
            if not new.exists(label_new) or sha256_hex(self.src.read_bytes(label_old)) != sha256_hex(new.read_bytes(label_new)):
                changed.append(f"views:{TRANSCRIPT_VIEW}")
        failed = any(_failed_states(now)[k] and not _failed_states(old)[k] for k in _failed_states(now))
        header = new.read_aer(now).header if changed else None
        unverified = header is not None and self._rules_unavailable(header)
        return changed, failed, unverified

    def _compare_corpus_files(self, new: CorpusReader, report: RederiveReport, changed: Mapping[str, bool],
                              renames: Mapping[str, str] | None = None) -> int:
        bad = 0
        pairs = (("raw/origins.jsonl", ("expand", "aer")), ("raw/members.jsonl", ("expand",)),
                 ("register.jsonl", tuple(_ORDER)))
        for label, explaining in pairs:
            old = self.src.read_bytes(label) if self.src.exists(label) else b""
            now = new.read_bytes(label) if new.exists(label) else b""
            if old == now:
                continue
            if label == "raw/members.jsonl" and renames:
                relabelled = self._relabel_members(old, renames)
                if relabelled == now:
                    self.notices.append(f"raw/members.jsonl: {len(old.splitlines())} row(s) differ only in the expand "
                                        "fn_digest of an expansion with the same declared versions (a code or limits "
                                        "change, every member identical: a refactor; H.8.4(2))")
                    continue
                old = relabelled
            explained = any(changed.get(s, False) for s in explaining)
            # BF-20, CB-6: lines about an object absent on purpose, or an execution that needs one, are not reproduced
            accounted = tuple(self.absent) + tuple(sorted(self.absent_ex | self.withheld_ex)) + tuple(sorted(self.absent_labels))
            # RC-13: compared as multisets, so a duplicated row is a difference; the order is not compared (a re-map
            # writes the rows it carries before the ones it re-derives)
            old_lines = Counter(line for line in old.splitlines() if not any(t.encode() in line for t in accounted))
            new_lines = Counter(line for line in now.splitlines() if not any(t.encode() in line for t in accounted))
            if old_lines == new_lines:
                continue
            report.corpus_changes.append({
                "file": label, "explained": explained,
                "removed": sum((old_lines - new_lines).values()), "added": sum((new_lines - old_lines).values()),
            })
            if not explained:
                bad += 1
        return bad

    def _relabel_members(self, data: bytes, renames: Mapping[str, str]) -> bytes:
        """``data`` with each row's ``fn_digest`` replaced by its paired new one (P-2); unparseable bytes stay as they
        are, so they are compared (and reported) unchanged; so do bytes that are not the canonical encoding of their rows
        (RC-7: re-encoding would hide the difference)."""
        try:
            rows = decode_members(data, self.src.limits)
        except AgentProvError:
            return data
        if encode_members(rows) != data:
            return data
        return encode_members(dataclasses.replace(r, fn_digest=renames.get(r.fn_digest, r.fn_digest)) for r in rows)

    def _details(self, new: CorpusReader, old: IndexRow, now: IndexRow, outputs: Sequence[str],
                 old_validation: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for output in outputs:
            kind, _, key = output.partition(":")
            try:
                if kind == "aer":
                    a, b = self.src.aer_bytes(old), new.aer_bytes(now)
                elif kind == "sem":
                    a = self.src.read_bytes(self.src.layout.sem_relpath(key, old.ex))
                    b = new.read_bytes(new.layout.sem_relpath(key, now.ex))
                elif kind in ("prov", "compat"):
                    a, b = self.src.prov_bytes(old, key), new.prov_bytes(now, key)
                elif kind == "validation":
                    a = jcs_bytes(old_validation.get(old.ex, {})) + b"\n"
                    b = jcs_bytes({r["ex"]: r for r in new.validation_results()}.get(now.ex, {})) + b"\n"
                else:
                    a = self.src.read_bytes(self.src.layout.view_relpath(TRANSCRIPT_VIEW, old.ex))
                    b = new.read_bytes(new.layout.view_relpath(TRANSCRIPT_VIEW, now.ex))
            except AgentProvError:
                out.append({"ex": old.ex, "output": output, "line": None, "old": None, "new": None, "semantic": []})
                continue
            line, first_old, first_new = _first_difference(a, b, pretty=kind in ("prov", "compat"))
            semantic: list[str] = []
            if kind in ("prov", "compat"):
                from agentprov.prov.diff import diff_documents

                with contextlib.suppress(ValueError):
                    semantic = diff_documents(json.loads(a), json.loads(b))[:20]
            out.append({"ex": old.ex, "output": output, "line": line, "old": first_old, "new": first_new,
                        "semantic": semantic})
        return out


def _tier_failure(entry: RegisterEntry) -> bool:
    """A source register row a tier-3 or tier-4 verdict wrote (not the AER validator's): RC-9 recomputes it."""
    return entry.code == "validate.failed" and entry.stage == "validate" and entry.detail.startswith("tiers 3-4:")


def _codes_by_ex(entries: Iterable[RegisterEntry]) -> dict[str, dict[str, str]]:
    """Register code -> severity of every execution subject (the most severe entry of a code wins)."""
    out: dict[str, dict[str, str]] = {}
    for entry in entries:
        ex = entry.subject.get("ex")
        if ex is None:
            continue
        codes = out.setdefault(ex, {})
        previous = codes.get(entry.code)
        if previous is None or _SEVERITY_ORDER.get(entry.severity, 1) > _SEVERITY_ORDER.get(previous, 1):
            codes[entry.code] = entry.severity
    return out


def _failed_states(row: IndexRow) -> dict[str, bool]:
    return {
        "aer": row.stages.get("aer") == "failed",
        "sem": any(o.state == "failed" for o in (row.sem or {}).values()),
        "prov": any(o.state == "failed" for o in (row.prov or {}).values()),
        "validation": row.validation is not None and row.validation.state == "failed",
    }


def _projection(row: IndexRow) -> dict[str, Any]:
    """The index members outside the stage outputs and the full-row members."""
    data = row.to_json()
    for key in ("digests", "paths", "stages", "cell", "ev", "facets", "logical_key", "oracles"):
        data.pop(key, None)
    return data


def _refreshed(old: IndexRow, new: IndexRow) -> bool:
    """``index_refreshed``: a row member outside the outputs differs (completeness, status, issues, ...), or both rows are
    full rows and their facets differ. A working row that becomes a full row is not a refresh by itself."""
    if _projection(old) != _projection(new):
        return True
    return old.facet_members is not None and new.facet_members is not None and \
        old.facet_members.to_json() != new.facet_members.to_json()


def _first_difference(old: bytes, new: bytes, *, pretty: bool) -> tuple[int | None, str | None, str | None]:
    """The first differing line (1-based) and the two lines (``None`` past the end). JSON documents are compared in a
    sorted, indented rendering so a long single-line document does not become one line."""
    if pretty:
        with contextlib.suppress(ValueError):
            old = json.dumps(json.loads(old), indent=1, sort_keys=True, ensure_ascii=True).encode("ascii")
            new = json.dumps(json.loads(new), indent=1, sort_keys=True, ensure_ascii=True).encode("ascii")
    a, b = old.split(b"\n"), new.split(b"\n")
    for number in range(max(len(a), len(b))):
        x = a[number] if number < len(a) else None
        y = b[number] if number < len(b) else None
        if x != y:
            return (number + 1, None if x is None else x.decode("utf-8", "replace")[:300],
                    None if y is None else y.decode("utf-8", "replace")[:300])
    return None, None, None


def _merge_sources(produced: Sequence[Any], recorded: Any) -> list[Any]:
    """The importer's ``sources`` with the recorded snapshot origin, pin verification (the snapshot's and each context
    tree's, by role; NF-26) and the counts a re-map cannot observe (``candidates``, ``selection_excluded``: files that were
    walked but never stored) carried from the source."""
    out = [dict(s) if isinstance(s, Mapping) else s for s in produced]
    if not out or not isinstance(recorded, list) or not recorded or not isinstance(recorded[0], Mapping):
        return out
    old_snapshots = {s.get("snapshot_id"): s for s in recorded[0].get("snapshots") or () if isinstance(s, Mapping)}
    first = out[0]
    if isinstance(first, dict) and isinstance(first.get("snapshots"), list):
        merged = []
        for snapshot in first["snapshots"]:
            old = old_snapshots.get(snapshot.get("snapshot_id")) if isinstance(snapshot, Mapping) else None
            if old is None:
                merged.append(snapshot)
                continue
            counts = dict(snapshot.get("counts") or {})
            for key in ("candidates", "selection_excluded"):
                if key in (old.get("counts") or {}):
                    counts[key] = old["counts"][key]
            carried = {**snapshot, "origin": old.get("origin"), "verification": old.get("verification"), "counts": counts}
            if isinstance(snapshot.get("context"), list):  # NF-26 (D-530): a context tree's pin verification, by role
                old_context = {c.get("role"): c for c in old.get("context") or () if isinstance(c, Mapping)}
                carried["context"] = [{**c, "verification": old_context[c.get("role")].get("verification")}
                                      if isinstance(c, Mapping) and c.get("role") in old_context else c
                                      for c in snapshot["context"]]
            merged.append(carried)
        first["snapshots"] = merged
    return out


# ================================================================================================ TriG (on demand)
@dataclass
class TrigReport:
    """What :func:`export_trig` wrote: file count, the listing digest and the serialiser versions (E.5.4(5))."""

    files: int
    listing_sha256: str
    versions: dict[str, str]
    failed: list[str]


def export_trig(reader: CorpusReader, out_dir: Path, *, spec: str = SPEC_ID) -> TrigReport:
    """Write ``<out_dir>/<ss>/<ex>.prov.trig`` for every execution with ``spec`` output, and ``<out_dir>/trig.sha256``
    (``<sha256>  <relpath>`` lines). Never part of a corpus (AD-10 row 3); the caller checks ``out_dir`` lies outside
    every corpus (G2, G8)."""
    from agentprov.prov.serialise.trig import TrigError, serialiser_versions, to_trig

    lines: list[str] = []
    failed: list[str] = []
    for row in reader.index():
        stage = (row.prov or {}).get(spec)
        if stage is None or stage.digest is None:
            continue
        try:
            data = to_trig(reader.prov_bytes(row, spec))
        except TrigError:
            failed.append(row.ex)
            continue
        relative = f"{shard(row.ex)}/{row.ex}.prov.trig"
        path = out_dir / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_bytes(path, data)
        lines.append(f"{sha256_hex(data)}  {relative}\n")
    listing = "".join(sorted(lines)).encode("ascii")
    out_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_bytes(out_dir / "trig.sha256", listing)
    return TrigReport(len(lines), "sha256:" + sha256_hex(listing), serialiser_versions(), failed)


# ------------------------------------------------------------------------------------------------ helpers for the CLI
def is_inside(a: Path, b: Path) -> bool:
    """Whether ``a`` is ``b`` or below it (both resolved)."""
    try:
        Path(os.path.realpath(a)).relative_to(os.path.realpath(b))
    except ValueError:
        return False
    return True
