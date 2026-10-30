"""D-7 / G.3.10: the no-follow primitives live in ONE place (``ingest/paths.py``). Every open of evidence or store objects
goes through ``open_evidence``; no other source file names ``O_NOFOLLOW`` or opens relative to a directory descriptor."""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SOURCES = [*(REPO / "src").rglob("*.py"), *(REPO / "capture" / "src").rglob("*.py")]
HELPER = REPO / "src" / "agentprov" / "ingest" / "paths.py"


def outside_the_helper():
    return [p for p in SOURCES if p != HELPER and "__pycache__" not in p.parts]


def test_the_scan_covers_the_source_tree():
    assert HELPER.exists() and len(outside_the_helper()) > 30


def test_no_source_file_outside_the_helper_names_o_nofollow():
    offenders = [str(p.relative_to(REPO)) for p in outside_the_helper() if "O_NOFOLLOW" in p.read_text(encoding="utf-8")]
    assert offenders == [], "use agentprov.ingest.paths.open_evidence, the one no-follow opener: " + ", ".join(offenders)


def test_no_source_file_outside_the_helper_opens_relative_to_a_descriptor():
    offenders = []
    for path in outside_the_helper():
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call) and any(kw.arg == "dir_fd" for kw in node.keywords):
                offenders.append(f"{path.relative_to(REPO)}:{node.lineno}")
    assert offenders == [], "dir_fd is the helper's business: " + ", ".join(offenders)
