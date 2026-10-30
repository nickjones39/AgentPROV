"""Tampering devices for the ``verify`` tests (``verify_support``; not collected).

They play an attacker who edits a sealed tree and then re-makes as much of its integrity data as the case says:
:func:`regenerate_checksums` rewrites only ``checksums.sha256``; :func:`reforge` applies the caller's index-row changes,
then recomputes the manifest's ``files``, ``digests`` and content digest, then the checksums. Each K.12.5 case is thus
detected by exactly the level the table names. Test devices only, never a way to build a corpus.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any


def root_digest(root: Path) -> str:
    from agentprov.corpus.integrity import root_digest as digest

    return digest(root)


def regenerate_checksums(root: Path) -> None:
    """The attacker rewrites ``checksums.sha256`` over the tampered files (nothing else)."""
    from agentprov.corpus.integrity import write_checksums

    (root / "checksums.sha256").unlink()
    write_checksums(root)


def rows(root: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in (root / "executions.jsonl").read_text("utf-8").splitlines()]


def write_jsonl(path: Path, items: list[dict[str, Any]]) -> None:
    from agentprov.io.canonical import jcs_bytes

    path.write_bytes(b"".join(jcs_bytes(item) + b"\n" for item in items))


def manifest(root: Path) -> dict[str, Any]:
    return json.loads((root / "corpus.json").read_text("utf-8"))


def reforge(root: Path, *, index: Callable[[dict[str, Any]], None] | None = None,
            change: Callable[[dict[str, Any]], None] | None = None) -> None:
    """A consistent forgery: apply ``index(row)`` to every index row, then recompute the manifest's ``files``,
    ``digests`` and content digest (``change(manifest)`` first), then ``checksums.sha256``."""
    from agentprov.corpus.integrity import content_digest
    from agentprov.corpus.layout import iter_tree
    from agentprov.corpus.manifest import digests_of, file_ref, raw_dispositions
    from agentprov.corpus.reader import SEALED, CorpusReader
    from agentprov.corpus.withheld import decode_withheld
    from agentprov.raw.references import parse_references

    if index is not None:
        items = rows(root)
        for item in items:
            index(item)
        write_jsonl(root / "executions.jsonl", items)
    m = manifest(root)
    if change is not None:
        change(m)
    for role, label in (("withheld", "WITHHELD.json"), ("references", "raw/REFERENCES.json")):
        if (root / label).is_file():  # a consistent forgery declares the optional ledgers too (D-163, D-237)
            m["files"].setdefault(role, {"bytes": 0, "lines": None, "path": label, "sha256": "sha256:" + "0" * 64})
    for ref in m["files"].values():
        ref.update(file_ref(ref["path"], (root / ref["path"]).read_bytes(), jsonl=ref["lines"] is not None))
    reader = CorpusReader(root, state=SEALED)
    withheld = decode_withheld((root / "WITHHELD.json").read_bytes()).objects if (root / "WITHHELD.json").is_file() else {}
    referenced = ({r.sha256 for r in parse_references((root / "raw" / "REFERENCES.json").read_bytes())}
                  if (root / "raw" / "REFERENCES.json").is_file() else set())
    raw_objects = raw_dispositions([label.rsplit("/", 1)[-1].split(".", 1)[0] for label, role, _ in iter_tree(root).files
                                    if role == "raw_object"], withheld, referenced)
    m["digests"] = digests_of(reader.index(), raw_objects, index_bytes=(root / "executions.jsonl").read_bytes(),
                              register_bytes=(root / "register.jsonl").read_bytes(),
                              members_bytes=(root / "raw" / "members.jsonl").read_bytes())
    m["content_digest"] = content_digest(m)
    (root / "corpus.json").write_bytes((json.dumps(m, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode())
    regenerate_checksums(root)


def first_file(root: Path, top: str) -> Path:
    return sorted(p for p in (root / top).rglob("*") if p.is_file())[0]
