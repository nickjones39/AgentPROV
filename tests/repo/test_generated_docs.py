"""DECISIONS.md (index and parts), regen-batch.md and AGENTS.md match their fragments (``tools/gen_docs.py``, D-421).

Once a document is split into one file per entry, the document itself is generated. A branch that edited the
generated file, or merged main into a branch started before the split, fixes a failure here by running
``uv run python tools/gen_docs.py --adopt`` (moves direct edits into fragments) and then ``--write``. A document that
is not split yet passes.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


def _tool():
    sys.path.insert(0, str(REPO / "tools"))  # gen_docs imports _workflow from its own directory
    try:
        import gen_docs

        return gen_docs
    finally:
        sys.path.remove(str(REPO / "tools"))


GD = _tool()


@pytest.mark.parametrize("name", sorted(GD.TARGETS))
def test_each_generated_doc_matches_its_fragments(name: str) -> None:
    target = GD.TARGETS[name]
    if not GD.migrated(REPO, target):
        pytest.skip(f"{target.path} is not split yet")
    files = GD.generate_files(REPO, target)  # the file, or its index and parts (D-1003)
    stale = [p for p, text in files.items()
             if not (REPO / p).is_file() or (REPO / p).read_text(encoding="utf-8") != text]
    assert stale == [], (f"{', '.join(stale)} differ from {target.directory}: run "
                         f"`uv run python tools/gen_docs.py --adopt {name}` then `--write {name}`")
    assert GD.stray_parts(REPO, target, files) == [], f"run `uv run python tools/gen_docs.py --write {name}`"
