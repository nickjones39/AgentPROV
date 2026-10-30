"""Small working corpora for the ``derive``/``recompute`` tests (``derive_support``; not collected).

Each builder imports committed, licence-cleared fixtures (the golden native AgentDojo logs, the released golden
transcript/v1 pairs, the survey AgentHarm ``.eval`` log) into ``<tmp>/<name>.partial`` through the product import path
(``import_source``, in-process, no network) and returns the corpus directory ``<tmp>/<name>``. Fixture text is never
printed.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

_ADAPTERS = Path(__file__).resolve().parents[2] / "adapters"
if str(_ADAPTERS) not in sys.path:
    sys.path.insert(0, str(_ADAPTERS))

import import_support as support  # noqa: E402

from agentprov.adapters.runner.importer import LocalTree, PinCheck, import_source, listing_sha256  # noqa: E402
from agentprov.corpus.writer import CorpusWriter  # noqa: E402
from agentprov.io.canonical import sha256_hex  # noqa: E402

BASELINE = "579a908354b93361efe0905ffb7623256aa96a06"


def agentdojo_corpus(tmp: Path, *, name: str = "agentdojo", count: int | None = 3, **kwargs: Any) -> Path:
    tree_root = tmp / f"{name}-input"
    support.agentdojo_tree(tree_root, count=count)
    final = tmp / name
    kwargs.setdefault("in_process", True)
    pin = {"commit": support.C274885, "kind": "git", "role": "2024-06"}
    with CorpusWriter(final) as writer:
        import_source("agentdojo", LocalTree(tree_root), corpus=writer, part="2024-06",
                      pin_check=support.vouch(tree_root), pin=pin, **kwargs)
    return final


def adprov_corpus(tmp: Path, *, name: str = "adprov", count: int | None = None, **kwargs: Any) -> Path:
    """The released golden v1 pairs (the first ``count`` by label) under a listing pin over exactly those files."""
    tree_root = tmp / f"{name}-input"
    labels = support.adprov_tree(tree_root)
    for label in sorted(labels)[count:] if count is not None else ():
        (tree_root / label).unlink()
        del labels[label]
    for dirpath, _dirs, _files in sorted(os.walk(tree_root), reverse=True):
        if dirpath != str(tree_root) and not os.listdir(dirpath):
            os.rmdir(dirpath)
    pairs = [(label, sha256_hex((tree_root / label).read_bytes())) for label in labels]
    pin = {"role": "release", "tree": "corpus/corpus-prov", "commit": BASELINE, "kind": "listing",
           "listing_sha256": listing_sha256(pairs), "expected_files": len(pairs)}
    from agentprov.adapters.adprov.dialect import TranscriptV1Reader

    check = PinCheck("listing", pin, listing_origin=TranscriptV1Reader.listing_origin)
    final = tmp / name
    kwargs.setdefault("in_process", True)
    with CorpusWriter(final) as writer:
        import_source("adprov-v1", LocalTree(tree_root), corpus=writer, part="release", pin_check=check, pin=pin, **kwargs)
    return final


def inspect_corpus(tmp: Path, *, name: str = "inspect", **kwargs: Any) -> Path:
    tree_root = tmp / f"{name}-input"
    support.inspect_tree(tree_root)
    final = tmp / name
    kwargs.setdefault("in_process", True)
    pin = {"commit": support.SURVEY_COMMIT, "kind": "git", "repo": support.SURVEY, "role": "git", "tree": "agentharm/results"}
    with CorpusWriter(final) as writer:
        import_source("agent-security-tools-survey", LocalTree(tree_root), corpus=writer, part="agentharm",
                      pin_check=support.vouch(tree_root, repo=support.SURVEY, commit=support.SURVEY_COMMIT), pin=pin,
                      **kwargs)
    return final


def adprov_graph_digests(count: int | None = None) -> set[str]:
    """sha256 of the stored baseline graphs of the first ``count`` released golden pairs (by label)."""
    entries: dict[str, Any] = {}
    for entry in support.golden.v1_pairs():
        if entry.tree == "release":
            stem = str(entry.origin["corpus_relpath"]).removeprefix("corpus/corpus-prov/") + ".transcript.json"
            entries[stem] = entry
    chosen = sorted(entries)[:count] if count is not None else sorted(entries)
    return {sha256_hex(entries[label].graph_bytes()) for label in chosen}


def partial(final: Path) -> Path:
    return final.with_name(final.name + ".partial")


def tree_bytes(root: Path) -> dict[str, bytes]:
    return support.tree_bytes(root)


def rows(root: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in (root / "executions.jsonl").read_text().splitlines()]


def rewrite_row(root: Path, ex: str, change: Any) -> None:
    """Apply ``change(row) -> row`` to one index row and rewrite ``executions.jsonl`` canonically."""
    from agentprov.io.canonical import jcs_bytes

    out = []
    for row in rows(root):
        out.append(change(row) if row["ex"] == ex else row)
    (root / "executions.jsonl").write_bytes(b"".join(jcs_bytes(r) + b"\n" for r in out))

