"""Synthetic sealed corpora for the local-priors tests (not collected).

Each corpus is imported from a slice of the committed, licence-cleared golden June-2024 AgentDojo logs (their text is
never printed) and sealed with the seal tests' inputs (``tests/unit/corpus/seal_support.py``) under its own corpus id,
so two corpora hold different executions. Nothing here reads ``$AGENTPROV_HOME`` or a real corpus.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for _path in (REPO / "tests" / "unit" / "corpus", REPO / "tests" / "adapters", REPO / "tests" / "unit" / "raw"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import import_support as support  # noqa: E402
import seal_support as ss  # noqa: E402


def _rows(partial: Path) -> list[str]:
    import json

    return [json.loads(line)["ex"] for line in (partial / "executions.jsonl").read_text(encoding="utf-8").splitlines()]


def working(dest: Path, first: int, count: int) -> list[str]:
    """Import logs ``first .. first + count - 1`` into the working corpus ``dest.partial``; returns its ex ids."""
    from agentprov.adapters.runner.importer import LocalTree, import_source
    from agentprov.corpus.writer import CorpusWriter

    tree = dest.parent.parent / "logs" / dest.name  # beside the corpora folder, not in it
    for entry in support.agentdojo_entries()[first:first + count]:
        support._write(tree, str(entry.origin["path"]), entry.native_bytes())
    with CorpusWriter(dest) as corpus:
        report = import_source("agentdojo", LocalTree(tree), corpus=corpus, part="2024-06", workers=1,
                               mode="release", pin_check=support.vouch(tree), pin=ss.PIN)
    assert report.exit_code == 0, report.counters
    return _rows(dest.with_name(dest.name + ".partial"))


def sealed(dest: Path, first: int, count: int, *, corpus_id: str, version: str = "0.1.0",
           withhold: int | None = None) -> list[str]:
    """A sealed corpus at ``dest`` of logs ``first .. first + count - 1``; ``withhold``: the index (in ex order) of an
    execution the spec's ``[withhold]`` table lists. Returns every ex id of the working corpus (withheld included)."""
    from agentprov.corpus.package import seal

    ex = working(dest, first, count)
    spec = ss.SPEC.replace('corpus_id = "mini-agentdojo"', f'corpus_id = "{corpus_id}"').replace(
        'corpus_version = "0.1.0"', f'corpus_version = "{version}"')
    if withhold is not None:
        spec += f'\n[withhold]\ndecided_by = "test"\nexecutions = ["{ex[withhold]}"]\n'
    changes = ss.CHANGES.replace('version = "0.1.0"', f'version = "{version}"')
    seal(dest, corpus_version=version, inputs=ss.inputs(spec=spec.encode(), changes=changes.encode()))
    return ex
