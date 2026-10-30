"""``agentprov.api``: the stable public facade for external consumers such as the paper package (MN M.6; O.3.5).

Stable within 0.1.x; stdlib and core dependencies only. Everything else in ``agentprov`` is internal and may change in
any 0.x release. The paper imports only this module, reads sealed corpora through it and builds its own data frames from
the plain rows :func:`rows` returns (R-34, R-64); the framework ships no ``analysis`` package (AD-10 row 1).

As built (phase 11, U6):

* :func:`open_corpus`, :func:`iter_executions`, :func:`statistics`, :func:`field_groups`, :func:`source_registry` and
  :func:`semantics_profile` are complete.
* :func:`verify_corpus` implements every H.5.5 level (``checksums``, ``chain``, ``rederive``; phase 11 U4) and returns
  the :class:`agentprov.corpus.verify.VerifyReport` of ``agentprov verify``; :func:`open_corpus` accepts the same levels.
* :func:`read_aer` takes a path, or a row together with ``corpus=`` (an index row alone does not locate its corpus).
* :func:`rows` serves every M.6 row set. ``lineage`` (D-541) is built from a sealed manifest's ``sources[]`` and
  ``raw/origins.jsonl``; a corpus whose manifest records no ``sources[].lineage`` (a working corpus) raises
  :class:`ApiUnavailable`.
* :func:`check_claim`, :func:`coverage_phrase` and :func:`lint_text` delegate to ``agentprov.adapters.registry.claims``
  (the one claims library, I.5.6). :func:`check_claim` forwards ``derivation``, ``location``, ``agent_executions_only``
  and ``phrase`` (D-540).
"""

from __future__ import annotations

import os
import tomllib
from collections.abc import Iterable, Iterator, Mapping, Sequence
from importlib import resources
from pathlib import Path
from typing import Any, Final, Literal

from agentprov.aer.reader import AerDocument, load_aer
from agentprov.corpus.index import IndexRow
from agentprov.corpus.verify import VerifyReport
from agentprov.errors import AgentProvError
from agentprov.formats import FORMATS
from agentprov.stats import StatsReport, compute
from agentprov.stats.fieldgroups import FieldGroup, evaluate
from agentprov.stats.fieldgroups import field_groups as _field_groups
from agentprov.stats.source import StatsCorpus, VerifyLevelUnavailable, normalise_select
from agentprov.stats.source import open_corpus as _open_corpus
from agentprov.stats.tables import DEFAULT_TABLES, prov_statements
from agentprov.versions import __version__

__all__ = [
    "FORMATS",
    "FRAME_NAMES",
    "ApiUnavailable",
    "Corpus",
    "FieldGroup",
    "StatsReport",
    "VerifyLevelUnavailable",
    "__version__",
    "check_claim",
    "coverage_phrase",
    "field_groups",
    "iter_executions",
    "lint_text",
    "open_corpus",
    "read_aer",
    "rows",
    "semantics_profile",
    "source_registry",
    "statistics",
    "verify_corpus",
]

#: An opened corpus (sealed or working).
Corpus = StatsCorpus
FRAME_NAMES: Final[tuple[str, ...]] = ("executions", "statements", "field_status", "validation", "profiles", "lineage")
_SPEC: Final = "agentprov-prov/0.1"


class ApiUnavailable(AgentProvError):
    """A public-API function whose implementation has not landed in this build (exit 5, ``unsupported``)."""

    code = "api.unavailable"
    exit_code = 5


# ------------------------------------------------------------------------------------------------ corpora
def open_corpus(root: str | os.PathLike[str], *,
                verify: Literal["none", "checksums", "chain", "rederive"] = "checksums") -> Corpus:
    """Open a sealed or working (``.partial``) corpus read-only (MN N.1.5).

    With ``verify="checksums"`` (the default) a sealed corpus must pass the ``checksums`` level of H.5.5, else
    :class:`agentprov.corpus.integrity.IntegrityError` is raised; ``"chain"`` and ``"rederive"`` run those levels of
    ``agentprov verify``. A working corpus cannot be verified and is opened with ``verification == "not_sealed"``."""
    return _open_corpus(root, verify=verify)


def verify_corpus(
    root: str | os.PathLike[str],
    *,
    level: Literal["checksums", "chain", "rederive"] = "chain",
    sample: int | None = None,
    seed: int | str | None = None,
    root_digests: Sequence[str] = (),
    release: bool = False,
) -> VerifyReport:
    """``agentprov verify`` in tree mode (H.5.5; MN N.2.6): every level, read-only. ``sample``/``seed`` draw a seeded
    sample of the executions for the per-execution checks and ``rederive`` (N.1.7); ``root_digests`` are digests
    published outside the corpus (D-39; required with ``release``). ``report.ok`` is true when every check passed;
    ``report.passed()`` applies the H.5.5 exit rule (unverified checks fail only in release mode)."""
    from agentprov.corpus.verify import verify_corpus as _verify
    from agentprov.stats.source import import_hooks

    return _verify(root, level=level, sample=sample, seed=seed, root_digests=tuple(root_digests), release=release,
                   import_hooks=import_hooks() if level == "rederive" else None)


def iter_executions(corpus: Corpus, *, select: Mapping[str, str | Sequence[str]] | None = None) -> Iterator[IndexRow]:
    """The corpus's index rows in ``ex`` order, filtered by ``select`` (keys of :data:`agentprov.stats.source.SELECT_KEYS`
    or ``issue``, ``facet.<name>``, ``cell.<member>``, ``outcome.<claim>``; a sequence value means any of its values)."""
    return corpus.iter_rows(normalise_select(select))


def read_aer(path_or_row: str | os.PathLike[str] | IndexRow, *, corpus: Corpus | None = None) -> AerDocument:
    """A seal-verified AER: from a file path, or from an index row of ``corpus`` (then also checked against the row's
    execution digest, the D9 chain)."""
    if isinstance(path_or_row, IndexRow):
        if corpus is None:
            raise ValueError("an index row is read through its corpus: read_aer(row, corpus=...)")
        return corpus.reader.read_aer(path_or_row)
    return load_aer(Path(os.fspath(path_or_row)))


# ------------------------------------------------------------------------------------------------ rows (R-34)
def _execution_row(corpus: Corpus, row: IndexRow) -> dict[str, Any]:
    out: dict[str, Any] = {
        "adapter": row.adapter,
        "aer_sha256": "sha256:" + row.aer_digest,
        "completeness": row.completeness,
        "corpus_id": corpus.corpus_id,
        "ex": row.ex,
        "execution_observed": row.execution_observed,
        "issues": list(row.issues),
        "mode": row.mode,
        "profile": row.profile,
        "prov_sha256": None,
        "raw_included": any(r.included for r in row.raw if r.role in ("primary", "capture_log")),
        "snapshot_ids": list(row.snapshot_ids),
        "source_id": row.source_id,
        "source_key": row.source_key,
        "status": row.status,
        "unit": row.unit,
    }
    stage = (row.prov or {}).get(_SPEC)
    if stage is not None and stage.digest is not None:
        out["prov_sha256"] = "sha256:" + stage.digest
    for profile, sem in sorted((row.sem or {}).items()):
        out[f"sem_sha256.{profile}"] = None if sem.digest is None else "sha256:" + sem.digest
    if row.facet_members is not None:
        for name, value in sorted(row.facet_members.facets.items()):
            if isinstance(value, Mapping):
                for member, item in sorted(value.items()):
                    if item is None or isinstance(item, str | int | bool):
                        out[f"{name}.{member}"] = item
            else:
                out[name] = value
    return out


def rows(corpus: Corpus, name: str) -> Iterator[Mapping[str, Any]]:
    """Plain rows of one row set of MN M.6 (:data:`FRAME_NAMES`); the paper builds its own frames from them."""
    if name == "executions":
        return (_execution_row(corpus, r) for r in corpus.iter_rows())
    if name == "statements":
        return _statement_rows(corpus)
    if name == "field_status":
        return _field_status_rows(corpus)
    if name == "validation":
        return iter(corpus.reader.validation_results())
    if name == "profiles":
        return _profile_rows()
    if name == "lineage":
        return iter(_lineage_rows(corpus))
    raise ValueError("unknown row set; one of " + ", ".join(FRAME_NAMES))


#: Declared code-lineage edges of a profile's ``[lineage]`` (the target ids are registry ids; no count).
_DECLARED: Final = ("built_on", "vendored", "cited_by", "owns", "excludes")


def _upstream_node(origin: Mapping[str, Any]) -> str:
    """The upstream artefact node of a snapshot origin (O.3.5 F5: ``repo@commit``)."""
    kind = origin.get("kind")
    if kind == "git":
        return f"{origin.get('repo')}@{origin.get('commit')}"
    if kind == "corpus":
        return f"{origin.get('corpus')}@{origin.get('version')}"
    if kind == "zenodo":
        return f"zenodo:{origin.get('doi')}/{origin.get('file')}"
    if kind == "hf":
        return f"hf:{origin.get('dataset')}@{origin.get('revision')}"
    return f"{kind}:" + ",".join(f"{k}={origin[k]}" for k in sorted(origin) if k != "kind")


def _lineage_rows(corpus: Corpus) -> list[dict[str, Any]]:
    """MN M.6 ``lineage`` (D-541): one row per edge, from the sealed manifest's ``sources[]`` (snapshots and the
    ``[lineage]`` recorded at sealing) and ``raw/origins.jsonl`` only (O.3.5 F5). Nodes are registry source ids
    (``<source>/<part>`` for a declared part) and upstream artefacts (``repo@commit``):

    * ``snapshot_of``: a source to the origin of each snapshot, ``n`` the snapshot's candidates;
    * the declared edges ``built_on``, ``vendored``, ``cited_by``, ``owns``, ``excludes``, ``n`` null;
    * each declared duplicate (``byte_identical``, ``replicate``, ``mirror``, ``derived_conversion``), ``n`` the raw
      objects of this corpus whose origin path the duplicate's ``path`` glob matches;
    * ``byte_identical`` from a source to itself, ``n`` the objects held under more than one origin (when any).

    :class:`ApiUnavailable` for a corpus whose manifest records no ``sources[].lineage`` (a working corpus)."""
    from agentprov.corpus.manifest import glob_match

    manifest = corpus.reader.manifest()
    sources = manifest.get("sources") if isinstance(manifest, Mapping) else None
    if not isinstance(sources, list) or not sources or not all(isinstance(s, Mapping) and "lineage" in s for s in sources):
        raise ApiUnavailable("the lineage row set needs a sealed manifest that records sources[].lineage (D-541)")
    origins = corpus.reader.origins()
    paths = [str(row.origin.data.get("path") or row.origin.data.get("label") or "") for row in origins]
    by_object: dict[str, int] = {}
    for row in origins:
        by_object[row.sha256] = by_object.get(row.sha256, 0) + 1
    shared = sum(1 for count in by_object.values() if count > 1)
    out: list[dict[str, Any]] = []
    for source in sources:
        sid, lineage = str(source["source_id"]), source["lineage"]
        for snapshot in source.get("snapshots", ()):
            out.append({"from_node": sid, "to_node": _upstream_node(snapshot.get("origin") or {}), "relation": "snapshot_of",
                        "n": int((snapshot.get("counts") or {}).get("candidates", 0)), "basis": "corpus.json"})
        for relation in _DECLARED:
            for target in lineage.get(relation, ()):
                out.append({"from_node": sid, "to_node": str(target), "relation": relation, "n": None,
                            "basis": "profile [lineage]"})
        for dup in lineage.get("duplicates", ()):
            node = str(dup["of"]) + (f"/{dup['part']}" if dup.get("part") else "")
            out.append({"from_node": sid, "to_node": node, "relation": str(dup["relation"]),
                        "n": sum(1 for path in paths if path and glob_match(path, str(dup["path"]))),
                        "basis": "profile [lineage]; raw/origins.jsonl"})
        if shared:
            out.append({"from_node": sid, "to_node": sid, "relation": "byte_identical", "n": shared,
                        "basis": "raw/origins.jsonl"})
    return sorted(out, key=lambda r: (r["from_node"], r["relation"], r["to_node"]))


def _statement_rows(corpus: Corpus) -> Iterator[Mapping[str, Any]]:
    from agentprov.prov.specs import load_spec

    rules = frozenset(load_spec().rules)
    for row in corpus.iter_rows():
        if _SPEC not in (row.prov_paths or {}):
            continue
        classified, _structural, _unknown = prov_statements(corpus.reader.read_prov(row, _SPEC), rules=rules)
        for (bundle, method, stype, evidence, rule), n in sorted(classified.items()):
            yield {"bundle": bundle, "evidence": evidence, "ex": row.ex, "method": method, "n": n, "rule": rule, "stype": stype}


def _field_status_rows(corpus: Corpus) -> Iterator[Mapping[str, Any]]:
    groups = _field_groups()
    for row in corpus.iter_rows():
        if row.unit != "agent_execution" or not row.execution_observed:
            continue
        status = evaluate(corpus.reader.read_aer(row).records, groups)
        for group in groups:
            if group.id in status.cells:
                cell, undeclared = status.cells[group.id]
                yield {"ex": row.ex, "group": group.id, "status": cell, "undeclared": undeclared}


def _profile_rows() -> Iterator[Mapping[str, Any]]:
    for reg in source_registry():
        for cap in reg.capabilities:
            yield {
                "caveat": cap.caveat, "evidence": cap.evidence, "family": reg.family, "import_status": cap.import_status,
                "licence_policy": reg.licence.policy, "licence_restrictions": list(reg.licence.restrictions),
                "licence_spdx": reg.licence.spdx, "live_status": cap.live_status, "mirror_of": cap.mirror_of,
                "name": reg.name, "owner": cap.owner, "part": cap.part, "profile": cap.profile, "role": cap.role,
                "source_id": reg.source_id, "target_import_status": cap.target_import_status, "via": cap.via,
            }  # fmt: skip


# ------------------------------------------------------------------------------------------------ statistics, data
def statistics(
    corpora: Sequence[Corpus],
    *,
    tables: Sequence[str] = DEFAULT_TABLES,
    prov_spec: str = _SPEC,
    select: Mapping[str, str | Sequence[str]] | None = None,
    per_execution: bool = False,
) -> StatsReport:
    """``agentprov stats`` (AD-10 as ruled): one result per corpus, never pooled (N.2.12)."""
    return compute(corpora, tables, prov_spec=prov_spec, select=select, per_execution=per_execution)


def field_groups() -> tuple[FieldGroup, ...]:
    """The field groups of ``stats/field_groups.toml``: id and AER JSON Pointers per group (O.3.5; R-57)."""
    return _field_groups()


def source_registry() -> tuple[Any, ...]:
    """The D.3 source registry (``SourceRegistration`` records); feeds the ``profiles`` rows."""
    from agentprov.adapters.registry import REGISTRY

    return tuple(REGISTRY)


def semantics_profile(id: str, version: int) -> Mapping[str, Any]:  # noqa: A002 - the M.6 signature
    """The package-resource data of a semantics profile at ``version`` (e.g. ``("agentdojo.suites", 1)``), read-only.

    Returns ``{"id", "version", "sha256", "files"}``: ``sha256`` is the profile digest (C.14.1), ``files`` maps each data
    file name to its parsed TOML table, or to ``{"sha256": …}`` for a non-TOML file. Imports no benchmark and no adapter
    module; the corpus ``rules/`` copy is never read (AD-14)."""
    import hashlib

    from agentprov.adapters.semantics_profiles import semantics_families
    from agentprov.sem.profiles import SemanticsProfileError, profile_digest
    from agentprov.sem.types import sem_profile_dir

    root = resources.files("agentprov").joinpath("adapters")
    dirname = sem_profile_dir(id, version)
    found = [f for f in semantics_families() if root.joinpath(f, "semantics", dirname).is_dir()]
    if len(found) != 1:
        raise SemanticsProfileError(f"semantics profile {id}@{version} is not shipped exactly once")
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
    parsed: dict[str, Any] = {}
    for name, data in sorted(files.items()):
        parsed[name] = tomllib.loads(data.decode("utf-8")) if name.endswith(".toml") else {"sha256": hashlib.sha256(data).hexdigest()}
    return {"files": parsed, "id": id, "sha256": profile_digest(files), "version": version}


# ------------------------------------------------------------------------------------------------ claims (I.5.6)
def _claims() -> Any:
    import importlib

    try:
        claims = importlib.import_module("agentprov.adapters.registry.claims")
    except ModuleNotFoundError:
        raise ApiUnavailable("the claims library (agentprov.adapters.registry.claims, I.5.6) is not in this build") from None
    return claims


def check_claim(source_ids: Iterable[str], tags: Iterable[str], *, derivation: Mapping[str, str] | None = None,
                location: str = "", agent_executions_only: bool = False, phrase: str | None = None) -> list[Any]:
    """``adapters.registry.claims.check_claim`` (I.5.6), every keyword forwarded (D-540)."""
    return list(_claims().check_claim(source_ids, tags, derivation=derivation, location=location,
                                      agent_executions_only=agent_executions_only, phrase=phrase))


def coverage_phrase(*args: Any, **kwargs: Any) -> Any:
    """``adapters.registry.claims.coverage_phrase``, re-exported unchanged (I.5.6; O.3.5)."""
    return _claims().coverage_phrase(*args, **kwargs)


def lint_text(*args: Any, **kwargs: Any) -> Any:
    """``adapters.registry.claims.lint_text``, re-exported unchanged (I.5.6; O.3.5)."""
    return _claims().lint_text(*args, **kwargs)
