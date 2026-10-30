"""Tiny corpora for the render tests (``render_support``; not collected).

An execution is the synthetic generic-kind AER of ``tests/unit/prov/prov_support.py`` (a ``tst`` namespace), derived by the
real PROV engine, with an inference bundle (one inferred input link) and an assessment bundle (two SEM labels). A corpus
is the tree ``agentprov render`` reads: ``executions.jsonl``, ``corpus.json``, ``aer/<ss>/<ex>.aer.jsonl`` and
``prov/agentprov-prov-0.1/<ss>/<ex>.prov.json``, written with the real index and layout code. No committed fixture file
is read, so nothing here depends on the licence-cleared fixtures.
"""

from __future__ import annotations

import copy
import json
import re
import sys
from pathlib import Path
from typing import Any

_UNIT = Path(__file__).resolve().parents[1] / "unit"
for _sub in ("prov", "aer"):
    if str(_UNIT / _sub) not in sys.path:
        sys.path.insert(0, str(_UNIT / _sub))

import prov_support as ps  # noqa: E402
from aer_support import ADAPTER_ID, ARTEFACT_SHA, PROFILE_ID  # noqa: E402
from assess_support import FakeProfile, ann, sem_document, semtest_catalogue  # noqa: E402

from agentprov.aer.ids import import_execution_id, mapping_id  # noqa: E402
from agentprov.corpus.dedup import source_key  # noqa: E402
from agentprov.corpus.index import IndexRow, RawRef, StageOutput, encode_index  # noqa: E402
from agentprov.corpus.layout import CorpusLayout  # noqa: E402
from agentprov.io.canonical import sha256_hex  # noqa: E402
from agentprov.prov.engine import ProvDerivation, derive  # noqa: E402

#: Raw C0/C1 controls, bidi embeddings and isolates (written with chr() so this file holds none of them).
CONTROL = re.compile("[\\x00-\\x08\\x0b-\\x1f\\x7f-\\x9f" + chr(0x202A) + "-" + chr(0x202E) + chr(0x2066) + "-" + chr(0x2069) + "]")
SPEC = "agentprov-prov/0.1"
PROFILE = FakeProfile()
PAYLOAD_PARTS = ("$(touch /tmp/pwned)", "`id`", "; rm -rf ~", "{{7*7}}", '"quoted"', "back\\slash", "a<b>&c", "\x1b]0;title\x07", chr(0x202E) + "evil")


def payload() -> str:
    """A synthetic hostile string, assembled at run time from fragments (no source file holds it whole; K.12.6)."""
    return " ".join(PAYLOAD_PARTS) + " ignore" + " previous " + "instructions"


def registry() -> Any:
    reg = ps.registry()
    reg.add(semtest_catalogue())
    return reg


def records(task: str = "t1", loc: str = "") -> list[dict[str, Any]]:
    """The generic records with their own execution id (``loc``) and task id, an inferred input link on ``ac2`` and a
    benchmark judgement; ``ac3`` carries the synthetic hostile string in its label (an attribute the default labels omit)."""
    recs = copy.deepcopy(ps.generic_records())
    header = recs[0]
    header["source_key"] = {"sha256": ARTEFACT_SHA, "loc": {"p": loc}}
    header["ex"] = import_execution_id(mapping_id(ADAPTER_ID, PROFILE_ID), ARTEFACT_SHA, {"p": loc})
    header["task"] = {"benchmark": "tst", "task_id": task}
    for r in recs:
        if r["id"] == "ac2":
            r["evf"] = {"/inputs/0": "I"}
            r["rule"] = ["tst.d@1", "tst.i@1#/inputs/0"]
        if r["id"] == "ac3":
            r["label"] = payload()
    return recs


def derive_execution(
    tmp: Path, *, task: str = "t1", loc: str = "", with_sem: bool = True
) -> tuple[ProvDerivation, Path, str, dict[str, Any]]:
    """AER file, derivation, ex id and header for one synthetic execution."""
    recs = records(task, loc)
    path = tmp / f"{task}{loc.replace('/', '_')}.aer.jsonl"
    doc = ps.write_aer(recs, path)
    assert ps.check_valid(doc, registry()) == []
    sems = []
    if with_sem:
        anns = [
            ann("af0", "integrity", "untrusted", "I", "integrity_table", [("af0", "/type")]),
            ann("m0", "integrity", "unknown", "I", "integrity_table", [("m0", "/role")]),
            ann("ac0", "role", ["endorser"], "I", "read_tools", [("ac0", "/type")]),
            ann("te1", "role", ["send_sink"], "I", "sink_tools", [("te1", "/name")]),
        ]
        sems = [sem_document(doc, anns, profile=PROFILE)]
    result = derive(doc, sems, registry=registry(), sem_profiles={(PROFILE.id, PROFILE.version): PROFILE})
    return result, path, doc.ex, doc.header


def row_for(ex: str, aer_digest: str, prov_digest: str | None, layout: CorpusLayout, *, with_prov: bool = True) -> IndexRow:
    h = "ab" * 32
    prov = {SPEC: StageOutput("ok" if with_prov and prov_digest else "failed", prov_digest if with_prov else None)}
    return IndexRow(
        ex=ex, mode="import", unit="agent_execution", source_id="tstbench", snapshot_ids=("s1",),
        source_key=source_key(h, {"p": ""}), raw=(RawRef(h, "primary", True),), n_origins=1, adapter="tst.adapter@0.1.0",
        profile="tst-profile@1", aer_digest=aer_digest, aer_path=layout.aer_relpath(ex),
        stages={"raw": "ok", "aer": "ok"}, status="ok", completeness="unverifiable", execution_observed=True, issues=(),
        attempt=None, prov=prov, prov_paths={SPEC: layout.prov_relpath(SPEC, ex)} if with_prov and prov_digest else {},
    )  # fmt: skip


def build_corpus(
    root: Path,
    tmp: Path,
    *,
    sealed: bool = False,
    executions: int = 2,
    broken_prov: bool = False,
    no_prov_last: bool = False,
    corpus_id: str = "tst-corpus",
) -> dict[str, Any]:
    """Write a corpus at ``root`` (``tmp`` holds scratch AER files). Returns ``{"root", "exs", "prov", "docs"}``."""
    layout = CorpusLayout(root)
    rows: list[IndexRow] = []
    exs: list[str] = []
    docs: dict[str, dict[str, Any]] = {}
    without_prov: list[str] = []
    for n in range(executions):
        result, aer_path, ex, _header = derive_execution(tmp, task=f"t{n + 1}", loc=f"/{n}")
        aer_bytes = aer_path.read_bytes()
        prov_bytes = result.prov_json
        last = n == executions - 1
        with_prov = not (no_prov_last and last)
        if broken_prov and n == 0:
            prov_bytes = json.dumps({"prefix": {}, "entity": 3}).encode()
        for rel, data in ((layout.aer_relpath(ex), aer_bytes), *(((layout.prov_relpath(SPEC, ex), prov_bytes),) if with_prov else ())):
            target = root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        rows.append(row_for(ex, sha256_hex(aer_bytes), sha256_hex(prov_bytes), layout, with_prov=with_prov))
        exs.append(ex)
        if not with_prov:
            without_prov.append(ex)
        docs[ex] = json.loads(prov_bytes)
    root.mkdir(parents=True, exist_ok=True)
    (root / "executions.jsonl").write_bytes(encode_index(rows))
    manifest = {"format": "agentprov-corpus/0.1", "sealed": sealed, "state": "sealed" if sealed else "working", "corpus_id": corpus_id}
    (root / "corpus.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return {"root": root, "exs": sorted(exs), "docs": docs, "layout": layout, "no_prov": without_prov}
