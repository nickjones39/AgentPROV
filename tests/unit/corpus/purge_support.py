"""A small working corpus for the purge tests (``purge_support``; not collected).

``build_working`` writes ``<name>.partial`` with a real raw store (``RawObjectStore.put``), an index of three executions and
a ``raw/members.jsonl`` that expands a (fake) container into one member:

* ``leak`` is the object to purge; ``ex_leak`` cites it, ``ex_other`` cites ``other`` and ``ex_member`` cites the member;
* ``container`` expands to ``member``; purging the container makes ``ex_member`` an affected execution.

The leaked value is assembled at run time, so no source file holds it whole.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agentprov.corpus.dedup import source_key
from agentprov.corpus.index import IndexRow, RawRef, encode_index
from agentprov.corpus.layout import CorpusLayout
from agentprov.raw.members import MemberRow, encode_members
from agentprov.raw.store import RawObjectStore

SENTINEL = "SENTINEL-" + "credential-" + "value"
EX_LEAK = "ex_" + "a" * 26
EX_OTHER = "ex_" + "b" * 26
EX_MEMBER = "ex_" + "c" * 26


def _row(ex: str, sha: str, layout: CorpusLayout) -> IndexRow:
    return IndexRow(
        ex=ex, mode="import", unit="agent_execution", source_id="tstbench", snapshot_ids=("s1",),
        source_key=source_key(sha, {"p": ""}), raw=(RawRef(sha, "primary", True),), n_origins=1, adapter="tst.adapter@0.1.0",
        profile="tst-profile@1", aer_digest="ab" * 32, aer_path=layout.aer_relpath(ex), stages={"raw": "ok", "aer": "ok"},
        status="ok", completeness="unverifiable", execution_observed=True, issues=(), attempt=None,
    )  # fmt: skip


def build_working(partial: Path, *, sealed: bool = False) -> dict[str, Any]:
    """Write the corpus tree at ``partial`` (a ``<name>.partial`` path, or a plain path for a sealed one)."""
    layout = CorpusLayout(partial)
    store = RawObjectStore(layout.raw)
    leak = store.put(json.dumps({"key": SENTINEL}).encode(), ext="json")
    other = store.put(b'{"harmless": true}', ext="json")
    container = store.put(b"PK-container-bytes", ext="zip")
    member = store.put(json.dumps({"member": SENTINEL}).encode(), ext="json")
    rows = [_row(EX_LEAK, leak.sha256, layout), _row(EX_OTHER, other.sha256, layout), _row(EX_MEMBER, member.sha256, layout)]
    members = [MemberRow(container.sha256, "cd" * 32, "run.json", 8, "0" * 8, member.size, member.sha256, "selected")]
    files = {
        "corpus.json": json.dumps({"format": "agentprov-corpus/0.1", "corpus_id": "tst-corpus", "sealed": sealed,
                                   "state": "sealed" if sealed else "working"}).encode(),
        "executions.jsonl": encode_index(rows),
        "register.jsonl": b"",
        "raw/origins.jsonl": b"",
        "raw/members.jsonl": encode_members(members),
    }
    for label, data in files.items():
        path = partial.joinpath(*label.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return {"root": partial, "layout": layout, "leak": leak.sha256, "other": other.sha256, "container": container.sha256,
            "member": member.sha256}


def tree_text(root: Path) -> str:
    """Every file below ``root`` as text, for 'the value appears nowhere' checks."""
    return "\n".join(p.read_bytes().decode("utf-8", "replace") for p in sorted(root.rglob("*")) if p.is_file())
