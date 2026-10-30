"""Live sessions into a working corpus: the product path of ``agentprov run`` after staging (MN N.2.1 behaviour 3; D.10.0;
D.10.4a item 2; HL H.1.1(2), H.6.1 R7; layer L6).

T0 has checked a staged session (``agentprov.cli.live.staging``: no-follow discovery, reported labels, re-hashing, the
secret scan). :class:`LiveSessionPipeline` then does exactly what ``agentprov import`` does for an expanded container,
on the same machinery (:class:`~agentprov.adapters.runner.importer._Pipeline`):

1. every staged file becomes a raw object with the origin ``capture {session}`` (C.3.12; H.2.3);
2. one T1 ``map`` job in ``container`` mode plans the session with the profile's reader (``agentprov.capture``,
   ``CaptureLogReader.plan``: the capture log is the primary item, blobs and the native log are auxiliary artefacts found
   by digest) and maps it with the profile's mapper (``agentdojo.capture``); the job reads the objects by digest from
   the corpus store, so mapping sees only stored bytes;
3. the parent seals the AER (write gate), validates it, writes the register rows of its seal issues, derives SEM and
   PROV and validates tiers 3-4 in T1 ``prov`` jobs, and writes the index row last, with ``mode: live`` and the capture
   ``attempt`` (H.3.1);
4. ``derivation.json`` and the working ``corpus.json`` with its ``live`` block are written by :meth:`write_documents`.

Every attempt is its own sealed execution (H.6.1 R7); nothing is overwritten. The seal's accounting verdict is returned
so that the caller can decide re-attempts (N.1.8(4)); accounting is never computed here (R-13).

**Native-log sessions** (``native_log=True``; D-666, the Inspect harness): step 2 differs. The session's mapped artefact
is the backend's native log (an Inspect ``.eval``, found by the profile's ``[import] include`` globs), a container that
goes through the versioned ``expand`` stage like an imported one and is planned and mapped by the profile's reader and
mapper into one execution per sample (``_map_expanded``, as an import maps a container). The capture log, which is the
cell's wire record, is stored beside it as a supporting raw object and not mapped (D-665 (b)). The AER says
``mode: import`` and so does its index row (D-666: the rows take the AER's mode): a live row names the capture log as
its primary artefact and carries the attempt (H.3.1), and here the primary artefact is the native log. The attempt stays
traceable through the native log's ``capture`` origin (the session id) and the campaign ledger. The session's outcome
for the campaign's ledger is the worst index status and accounting of its executions.
"""

from __future__ import annotations

import fnmatch
import platform
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from agentprov.adapters.profiles import load_profile
from agentprov.adapters.runner import iter_unit_frames, outcome_from_frames, summarise_unit_frames
from agentprov.adapters.runner.importer import (
    SPEC_ID,
    IdentityRefusedError,
    ImportFilters,
    _lockfile_sha256,
    _Pipeline,
    _registry_semantics,
    _split_ref,
    _versions,
    merge_aer_rules,
    code_sha256,
)
from agentprov.aer import AER_FORMAT_ID
from agentprov.corpus.reader import CORPUS_FORMAT
from agentprov.corpus.writer import CorpusWriter
from agentprov.ingest.limits import IngestLimits
from agentprov.io.workers import Job
from agentprov.progress import NULL_PROGRESS, Progress
from agentprov.raw.members import ContainerSpec, Selection
from agentprov.raw.origins import Origin
from agentprov.raw.store import ext_for_label
from agentprov.versions import __version__

__all__ = ["LiveSessionPipeline", "SessionOutcome", "check_live_identity"]


class _NoTree:
    """Live sessions are not discovered from a tree; the import pipeline's discovery is never called."""

    kind = "capture"
    explicit = True


@dataclass(frozen=True)
class SessionOutcome:
    """What one ingested session became."""

    session: str
    ex: str | None
    status: str | None  # the index row status (ok, ok_with_issues, failed), also before the flush; None: no execution
    accounting: str | None  # seal.accounting.status
    issues: tuple[str, ...]
    registered: tuple[str, ...]  # register codes of rows without an execution (plan rows, job failures)


class LiveSessionPipeline(_Pipeline):
    index_mode = "live"

    def __init__(
        self,
        corpus: CorpusWriter,
        *,
        source_id: str,
        part: str,
        profile_id: str,
        corpus_id: str,
        snapshot_id: str,
        mode: Literal["dev", "release"] = "dev",
        until: str = "validation",
        workers: int = 1,
        in_process: bool = False,
        limits: IngestLimits | None = None,
        progress: Progress = NULL_PROGRESS,
        semantics: Sequence[str] | None = None,
        prov_conformance: bool = True,
        native_log: bool = False,
    ) -> None:
        profile = load_profile(profile_id)
        if semantics is None:
            semantics = _registry_semantics(source_id, part, profile.id)
        super().__init__(
            source_id, _NoTree(), corpus, profile=profile, part=part, snapshot_id=snapshot_id, corpus_id=corpus_id,
            filters=ImportFilters(), limit=None, mode=mode, until=until, prov_specs=(SPEC_ID,), workers=workers,
            in_process=in_process, limits=limits or IngestLimits(), retry_failed=False, progress=progress,
            pin_check=None, resume_index=None, batch_size=1, dry_run=False, semantics=tuple(semantics),
            prov_conformance=prov_conformance,
        )  # fmt: skip
        self._attempts: dict[str, int] = {}
        self.sessions: list[str] = []
        self.native_log = native_log
        if native_log:
            self.index_mode = "import"  # the AER's mode (D-666); attempt_of() stays None for these rows

    def attempt_of(self, ex: str) -> int | None:
        return self._attempts.get(ex)

    # -------------------------------------------------------------------------------------- one session
    def ingest(
        self, session: str, attempt: int, files: Sequence[tuple[str, bytes]],
        extra: Sequence[tuple[str, str, str, str]] = (),
        origins: Mapping[str, Origin] | None = None,
    ) -> SessionOutcome:
        """Store, map, seal, derive, validate and index one staged session (module docstring, steps 1-3).

        ``files`` are ``(label, bytes)`` pairs that T0 has already checked. ``extra`` are register rows
        ``(code, severity, stage, detail)`` that T0 attaches to the session's execution (e.g. a reported digest that
        did not verify). ``origins`` names, per label, an origin T0 verified for a staged file (the AutoDojo cache: its
        pinned fork tree, D.11.3 rule 5): the member carries it and the session's ``capture`` origin is recorded as a
        mirror (C.3.12: one origin per artefact, the others in ``raw/origins.jsonl``)."""
        origin = Origin.capture(session)
        members: list[dict[str, Any]] = []
        seen: set[str] = set()
        for label, data in sorted(files):
            put = self.corpus.add_object(data, origin, ext=ext_for_label(label))
            if put.sha256 in seen:  # identical bytes under two labels: one object, one member
                continue
            seen.add(put.sha256)
            member_origin = (origins or {}).get(label, origin)
            if member_origin != origin:
                self.corpus.add_origin(put.sha256, member_origin)
            members.append({"label": label, "origin": member_origin.to_json(), "sha256": put.sha256, "size": len(data)})
        self.sessions.append(session)
        registered: list[str] = []
        if self.until == "raw" or not members:
            return SessionOutcome(session, None, None, None, (), ())
        if self.native_log:
            return self._ingest_native(session, members, extra)
        job = Job(key="000000000", kind="map", inputs=tuple({"sha256": m["sha256"], "role": "member"} for m in members),
                  params={**self._map_params(None), "mode": "container", "members": members})
        (result,) = self.map_pool.run([job])
        result = self._carved(result, {m["sha256"] for m in members})
        units = []
        try:
            if not result.ok:
                code = result.error.code if result.error is not None else "worker.error"
                subject = self._path_subject(session)
                self._register(subject, "map.adapter_defect", severity="error", stage="map", disposition="failed",
                               detail=f"session map job failed ({code})")
                if code.startswith("worker.limit."):
                    self._register(subject, code, severity="error", stage="map", disposition="failed",
                                   detail="the T1 job was stopped")
                self.counters["failed"] += 1
                self._fail(subject, "map", "map.adapter_defect", code)
                return SessionOutcome(session, None, None, None, (), ("map.adapter_defect",))
            summary = summarise_unit_frames(result.iter_json())  # D-414 pass 1
            summary.require_framing()  # what split_unit_frames raised, before any row is registered
            for row in summary.rows:
                path = f"{session}/{row['label']}" if row.get("label") else session
                self._register(self._path_subject(path), str(row["code"]), severity="info", stage="select",
                               disposition="not_imported", detail=str(row.get("detail", "")))
                self.counters["registered"] += 1
                registered.append(str(row["code"]))
            by_sha = {m["sha256"]: m for m in members}
            for head, frames in iter_unit_frames(result.iter_json()):  # pass 2: one unit's frames at a time
                member = by_sha[str(head["sha256"])]
                fallback = self._fallback(member["sha256"], int(member["size"]), origin)
                outcome = outcome_from_frames(frames)
                self._attempts[outcome.ex] = attempt
                unit = self._seal(outcome, fallback, f"{session}/{member['label']}", extra)
                if unit is not None:
                    self._attempts[unit.ex] = attempt
                    units.append(unit)
        finally:
            self._held = {}  # D-218: held members die with their result
            result.close()
        self.counters["seen"] += 1
        staged = self.submit_prov(units)
        self.finish(staged, self.run_prov(staged))
        if not units:
            return SessionOutcome(session, None, None, None, (), tuple(registered))
        unit = units[0]
        # rows are queued until flush (CorpusWriter.add_execution): the queued row carries the status flush will write
        index_row = self.corpus.has_execution(unit.ex) or self.corpus.pending_row(unit.ex)
        accounting = str(unit.seal.accounting.to_json().get("status"))
        return SessionOutcome(session, unit.ex, index_row.status if index_row is not None else None, accounting,
                              tuple(sorted(unit.codes)), tuple(registered))

    def _ingest_native(self, session: str, members: Sequence[dict[str, Any]],
                       extra: Sequence[tuple[str, str, str, str]]) -> SessionOutcome:
        """Step 2 of a native-log session (module docstring): expand and map its native logs."""
        globs = tuple(str(g) for g in (self.profile.data.get("import") or {}).get("include", ()))
        natives = [m for m in members if any(fnmatch.fnmatchcase(str(m["label"]), g) for g in globs)]
        for code, severity, stage, detail in extra:  # T0's rows: a reported digest that did not verify, at session level
            self._register(self._path_subject(session), code, severity=severity, stage=stage, disposition="sealed",
                           detail=detail)
        if not natives:
            self._register(self._path_subject(session), "select.not_execution_artefact", severity="info",
                           stage="select", disposition="not_imported", detail="the session holds no native log")
            self.counters["registered"] += 1
            return SessionOutcome(session, None, None, None, (), ("select.not_execution_artefact",))
        selection = Selection(include=self.reader.member_patterns(self.profile))
        specs: list[ContainerSpec] = []
        labels: dict[str, str] = {}
        for member in natives:
            path = f"{session}/{member['label']}"
            specs.append(ContainerSpec(str(member["sha256"]), self.snapshot_id, self._path_subject(path)["path"],
                                       (selection,)))
            labels[str(member["sha256"])] = path
        expanded = self.corpus.expand(specs, self.map_pool, limits=self.limits)
        units = self._map_expanded(specs, labels, expanded)
        self.counters["seen"] += 1
        staged = self.submit_prov(units)
        self.finish(staged, self.run_prov(staged))
        if not units:
            return SessionOutcome(session, None, None, None, (), ())
        statuses: list[str] = []
        accountings: list[str] = []
        codes: set[str] = set()
        for unit in units:
            row = self.corpus.has_execution(unit.ex) or self.corpus.pending_row(unit.ex)
            statuses.append(str(row.status) if row is not None else "failed")
            accountings.append(str(unit.seal.accounting.to_json().get("status")))
            codes.update(unit.codes)
        status = next((s for s in ("failed", "ok_with_issues", "ok") if s in statuses), statuses[0])
        accounting = next((a for a in ("inconsistent", "unverifiable", "consistent") if a in accountings), accountings[0])
        return SessionOutcome(session, units[0].ex, status, accounting, tuple(sorted(codes)), ())

    # -------------------------------------------------------------------------------------- documents
    def write_documents(self, live: Mapping[str, Any], *, producer_extra: Mapping[str, Any]) -> None:
        """``derivation.json`` (merged with an earlier invocation's) and the working ``corpus.json`` (H.2; a phase-8
        subset) with the ``live`` block (H.2.2 ``LiveBlock``)."""
        self.corpus.flush()
        previous = self.corpus.read_document(self.corpus.layout.derivation) or {}
        merged = {s.get("stage"): s for s in previous.get("stages", ()) if isinstance(s, dict)}
        recorded_aer = merged.get("aer")
        merged.update({s["stage"]: dict(s) for s in self.stage_definitions(None)})
        if "aer" in merged:  # ultrareview pipeline #3: the corpus's namespaces, not only this invocation's
            merged["aer"] = merge_aer_rules(recorded_aer, merged["aer"])
        order = ("aer", "sem", "prov", "validation")
        self.corpus.write_document(self.corpus.layout.derivation, {
            "format": "agentprov-derivation/0.1",
            "stages": [merged[name] for name in order if name in merged],
            "lockfile_sha256": _lockfile_sha256(),
            "python": {"implementation": platform.python_implementation(), "version": platform.python_version()},
        })  # fmt: skip
        rows = self.corpus.index.rows()
        register = self.corpus.register.entries()
        not_imported = Counter(e.code for e in register if e.disposition == "not_imported")
        profile_ref = {"id": self.profile.id, "version": self.profile.version, "sha256": "sha256:" + self.profile.sha256}
        manifest = {
            "format": CORPUS_FORMAT,
            "sealed": False,
            "state": "working",
            "corpus_id": self.corpus_id,
            "mode": "live",
            "partial": bool(live.get("partial", False)),
            "synthetic": bool(live.get("test_only", False)),
            "sources": [{
                "source_id": self.source_id, "parts": [self.part], "profile": profile_ref,
                "snapshots": [{
                    "snapshot_id": self.snapshot_id,
                    "origin": {"kind": "capture", "session_ids": sorted({str(s["session"]) for s in live.get("sessions", ())})},
                    "counts": {"candidates": len(live.get("sessions", ())), "executions": len(rows),
                               "not_imported": sum(not_imported.values()), "selection_excluded": 0},
                }],
            }],  # fmt: skip
            "profiles": {"source": [profile_ref],
                         "semantics": [{"id": i, "version": v} for i, v in (_split_ref(r) for r in self.semantics)]},
            "adapters": [{"id": self.mapper.mapper_id, "version": self.mapper.version,
                          "code_sha256": "sha256:" + code_sha256([f"adapters/{self.profile.family}"]),
                          "dialects": [self.dialect]}],
            "formats": {"corpus": CORPUS_FORMAT, "index": "agentprov-index/0.1",
                        "register": "agentprov-register/0.1", "aer": AER_FORMAT_ID,
                        "sem": "sem/0.1" if self.semantics and self._post_aer else None, "capture": "capture/0.1"},
            "producer": {
                "agentprov_version": __version__,
                "python": {"implementation": platform.python_implementation(), "version": platform.python_version()},
                "interpreter_advisory": None,  # live ingestion expands no archive or compressed stream (G.3.8)
                "platform": {"system": platform.system(), "release": platform.release(), "machine": platform.machine()},
                "isolation": "in-process" if self.map_pool.in_process else "t1",
                "key_distributions": _versions("prov", "rdflib", "rfc8785", "pyyaml", "agentprov-capture"),
                "lockfile_sha256": _lockfile_sha256(),
                **dict(producer_extra),
            },
            "live": dict(live),
            "limits": {"effective": self.limits.to_json(), "overrides": self.limits.overrides()},
            "counts": {
                "executions": len(rows),
                "by_unit": dict(sorted(Counter(r.unit for r in rows).items())),
                "by_status": dict(sorted(Counter(r.status for r in rows).items())),
                "by_completeness": dict(sorted(Counter(r.completeness for r in rows).items())),
                "issues_by_code": dict(sorted(Counter(e.code for e in register).items())),
                "not_imported_by_code": dict(sorted(not_imported.items())),
            },
            "release": {"status": "dev", "created": None},
            # G2c-5 (D-432): the same mark as an import's, only when tier 4 was skipped
            **({} if self.prov_conformance else {"validation": {"prov_conformance": "skipped"}}),
        }
        self.corpus.write_document(self.corpus.layout.manifest, manifest)


def check_live_identity(writer: CorpusWriter, pipeline: LiveSessionPipeline) -> dict[str, Any] | None:
    """G4 (N.1.9) for a live working corpus: same corpus id, source and mode, and the same function digests for every
    stage both runs define. Returns the existing manifest (``None`` for a new corpus)."""
    manifest = writer.read_document(writer.layout.manifest)
    if manifest is not None:
        source = (manifest.get("sources") or [{}])[0]
        if (manifest.get("corpus_id"), source.get("source_id"), manifest.get("mode")) != (
            pipeline.corpus_id, pipeline.source_id, "live"
        ):
            raise IdentityRefusedError(
                "the working corpus was begun with another corpus id, source or mode (G4); run into a new corpus directory"
            )
    derivation = writer.read_document(writer.layout.derivation)
    if derivation is not None:
        recorded = {s.get("stage"): s for s in derivation.get("stages", ()) if isinstance(s, dict)}
        for stage in pipeline.stage_definitions(None):
            before = recorded.get(stage["stage"])
            if before is None:
                continue
            if stage["stage"] == "aer":
                keys = ("adapter", "adapter_code_sha256", "profile", "profile_sha256", "engine_code_sha256", "limits_sha256")
                if any(before.get(k) != stage.get(k) for k in keys):
                    raise IdentityRefusedError("the working corpus was mapped with another adapter, profile, engine or limits (G4)")
            elif before.get("fn_digest") != stage["fn_digest"]:
                raise IdentityRefusedError(f"the working corpus was derived with another '{stage['stage']}' function (G4)")
    return manifest
