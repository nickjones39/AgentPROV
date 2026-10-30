"""README.md's adapter-family and source tables match the registry (``tools/gen_readme_sources.py``).

A branch that adds a source, part or family fixes a failure here by running
``uv run python tools/gen_readme_sources.py --write``.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from agentprov.adapters.registry import READERS, REGISTRY

REPO = Path(__file__).resolve().parents[2]


def _tool():
    spec = importlib.util.spec_from_file_location("gen_readme_sources", REPO / "tools" / "gen_readme_sources.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_readme_source_tables_are_current():
    tool = _tool()
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    assert tool.splice(readme, tool.render()) == readme, "run: uv run python tools/gen_readme_sources.py --write"


def test_the_tables_name_every_sealed_or_live_part_and_no_other():
    """The README lists the parts this release has (Q16, 2026-10-30): those in a sealed corpus and the ``partial`` live
    parts. Planned, owned-elsewhere, compat-oracle and toy parts stay in ``agentprov info`` and the user guide."""
    tool = _tool()
    block = tool.render()
    families = set()
    for src in REGISTRY:
        for cap in src.capabilities:
            row = f"| `{src.family}` | `{src.source_id}` | `{cap.part}`"
            if cap.role == "source" and (cap.sealed or cap.live_status == "partial"):
                assert row in block
                families.add(src.family)
            else:
                assert row not in block
    for dialect, factory in READERS.items():
        assert (f"`{dialect}`" in block) == (tool._family_of_reader(factory) in families), dialect
    assert "planned" not in block and "owned elsewhere" not in block and "toy format" not in block


def test_a_partial_live_part_reads_live_tested_subset_in_the_readme_only():
    """Q17 (2026-10-30): a display label; the registry value stays ``partial``."""
    tool = _tool()
    block = tool.render()
    live = [(src, cap) for src in REGISTRY for cap in src.capabilities if cap.live_status == "partial"]
    assert live and all(cap.live_status == "partial" for _src, cap in live)
    for src, cap in live:
        line = next(x for x in block.splitlines() if x.startswith(f"| `{src.family}` | `{src.source_id}` | `{cap.part}`"))
        assert tool.LIVE_LABEL in line and "live partial" not in line
    assert "live partial" not in block
