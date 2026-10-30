"""A small library-level ``agentprov import`` for the security suites: synthetic AgentDojo trees, no fixtures, no network.

The pin check vouches for every file it is given (the pipeline mechanics are under test, not the pin), exactly as
``tests/adapters/runner/test_import_pipeline.py`` does.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import import_support as support

from agentprov.adapters.runner.importer import ImportReport, LocalTree, import_source
from agentprov.corpus.writer import CorpusWriter

#: Every file a working corpus may hold (HL H.1.2, H.1.3): fixed names, sharded records and digest-named objects.
SHARD = r"[0-9a-f]{2}"
EX = r"ex_[a-z2-7]{26}"
SHA = r"[0-9a-f]{64}"
ALLOWED_PATHS = re.compile(
    "|".join([
        r"corpus\.json", r"executions\.jsonl", r"register\.jsonl", r"derivation\.json", r"checksums\.sha256",
        r"index\.jsonl", r"\.agentprov\.lock", r"validation/[a-z0-9._-]+\.jsonl?",
        r"raw/origins\.jsonl", r"raw/members\.jsonl", r"raw/REFERENCES\.json",
        rf"raw/objects/{SHARD}/{SHA}\.[a-z0-9]+",
        rf"aer/{SHARD}/{EX}\.aer\.jsonl",
        rf"sem/[a-z0-9._-]+/{SHARD}/{EX}\.sem\.jsonl",
        rf"prov/[a-z0-9._-]+/{SHARD}/{EX}\.prov\.json",
    ])
)


@dataclass
class Imported:
    report: ImportReport
    partial: Path

    def rows(self, name: str) -> list[dict[str, Any]]:
        path = self.partial / name
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []

    def aers(self) -> dict[str, bytes]:
        return {r["ex"]: (self.partial / r["paths"]["aer"]).read_bytes() for r in self.rows("executions.jsonl")}

    def files(self) -> list[str]:
        return sorted(p.relative_to(self.partial).as_posix() for p in self.partial.rglob("*") if p.is_file())


def run_import(tmp: Path, files: dict[str, bytes], *, name: str = "c", part: str = "2024-06", **kwargs: Any) -> Imported:
    """Write ``files`` (relative POSIX label -> bytes) under ``tmp/in-<name>`` and import them as AgentDojo ``part``."""
    root = tmp / f"in-{name}"
    for rel, data in files.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    kwargs.setdefault("in_process", True)
    kwargs.setdefault("pin_check", support.vouch(root))
    out = tmp / name
    with CorpusWriter(out) as corpus:
        tree = LocalTree(root, limits=kwargs.get("limits"))  # the CLI hands the same limits to the tree (N.2.2)
        report = import_source("agentdojo", tree, corpus=corpus, part=part, **kwargs)
    return Imported(report, out.with_name(out.name + ".partial"))
