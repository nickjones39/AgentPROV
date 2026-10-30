"""A small working corpus of stored AERs for the gate D tests (``gate_d_support``; not collected).

``build_corpus`` writes ``<name>.partial`` from golden work items: the AER file, its SEM and PROV outputs (produced with the
engines, so the index digests equal a re-derivation), a real raw store holding the source bytes (tier-2 locators resolve
against it) and an index whose rows classify as one of the J.3.5 trees.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

from agentprov.adapters.runner.provjob import PROFILES
from agentprov.aer.reader import load_aer_bytes
from agentprov.corpus.dedup import source_key
from agentprov.corpus.index import IndexRow, RawRef, StageOutput, encode_index
from agentprov.corpus.layout import CorpusLayout
from agentprov.io.canonical import sha256_hex
from agentprov.migration.gate_d_worker import NATIVE_PROFILE, WorkItem
from agentprov.prov.engine import derive
from agentprov.raw.store import RawObjectStore
from agentprov.sem.engine import annotate, dumps_sem

SPEC = "agentprov-prov/0.1"
TREES = {
    "release": ("adprov-v1", ("release",), "adprov.transcript_v1@0.1.0", "adprov-v1@2"),
    "converted": ("adprov-v1", ("converted",), "adprov.transcript_v1@0.1.0", "adprov-v1@2"),
    "native": ("agentdojo", ("2024-06",), "agentdojo.tracelogger@0.1.0", "agentdojo-upstream@2"),
    # not a J.3.5 tree: an upstream import of another snapshot classifies as ``other``
    "other": ("agentdojo", ("2025-01",), "agentdojo.tracelogger@0.1.0", "agentdojo-upstream@2"),
}


def build_corpus(partial: Path, items: Sequence[WorkItem], tree: str, *, corpus_id: str = "tst") -> list[IndexRow]:
    """Write the corpus tree at ``partial``; ``items`` are golden work items (they carry ``aer`` and ``raw`` bytes)."""
    source_id, snapshots, adapter, profile = TREES[tree]
    layout = CorpusLayout(partial)
    store = RawObjectStore(layout.raw)
    sem_profile = PROFILES[NATIVE_PROFILE]
    rows: list[IndexRow] = []
    files: dict[str, bytes] = {}
    for item in items:
        assert item.aer is not None and item.raw is not None
        doc = load_aer_bytes(item.aer)
        put = store.put(item.raw, ext="json")
        sem = annotate(doc, sem_profile)
        prov = derive(doc, [sem], sem_profiles={(sem_profile.id, sem_profile.version): sem_profile}, check_aer=False)
        ex = doc.ex
        files[layout.aer_relpath(ex)] = item.aer
        files[layout.sem_relpath(NATIVE_PROFILE, ex)] = dumps_sem(sem)
        files[layout.prov_relpath(SPEC, ex)] = prov.prov_json
        rows.append(
            IndexRow(
                ex=ex, mode="import", unit=str(doc.header["unit"]), source_id=source_id, snapshot_ids=snapshots,
                source_key=source_key(put.sha256, {"p": ""}), raw=(RawRef(put.sha256, "primary", True),), n_origins=1,
                adapter=adapter, profile=profile, aer_digest=doc.execution_digest, aer_path=layout.aer_relpath(ex),
                stages={"raw": "ok", "aer": "ok"}, status="ok", completeness="unverifiable", execution_observed=True,
                issues=(), attempt=None, prov={SPEC: StageOutput("ok", sha256_hex(prov.prov_json))},
                prov_paths={SPEC: layout.prov_relpath(SPEC, ex)}, validation=StageOutput("ok", "33" * 32),
                sem={NATIVE_PROFILE: StageOutput("ok", sem.digest)}, sem_paths={NATIVE_PROFILE: layout.sem_relpath(NATIVE_PROFILE, ex)},
            )  # fmt: skip
        )
    rows.sort(key=lambda r: r.ex)
    files["corpus.json"] = json.dumps(
        {"format": "agentprov-corpus/0.1", "corpus_id": corpus_id, "sealed": False, "state": "working"}
    ).encode()
    files["executions.jsonl"] = encode_index(rows)
    files["register.jsonl"] = b""
    files["raw/origins.jsonl"] = b""
    files["raw/members.jsonl"] = b""
    for label, data in files.items():
        path = partial.joinpath(*label.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return rows
