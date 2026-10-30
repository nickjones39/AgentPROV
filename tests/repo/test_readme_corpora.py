"""The user guide's corpus listing (docs/user-guide/14-corpora.md) matches the registry, the profiles and the committed reports (``tools/gen_readme_corpora.py``).

A branch that adds a source, part, pin or count fixes a failure here by adding the part to ``tools/readme_corpora.toml``
(with the committed report that records its count) and running ``uv run python tools/gen_readme_corpora.py --write``.
"""

from __future__ import annotations

import ast
import importlib.util
import json
from pathlib import Path

import pytest

from agentprov.adapters.registry import REGISTRY

REPO = Path(__file__).resolve().parents[2]


def _tool():
    spec = importlib.util.spec_from_file_location("gen_readme_corpora", REPO / "tools" / "gen_readme_corpora.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_guide_corpus_listing_is_current():
    tool = _tool()
    page = (REPO / "docs" / "user-guide" / "14-corpora.md").read_text(encoding="utf-8")
    assert tool.splice(page, tool.render()) == page, "run: uv run python tools/gen_readme_corpora.py --write"


def test_the_readme_links_to_the_listing_instead_of_holding_it():
    tool = _tool()
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    assert tool.BEGIN not in readme and tool.END not in readme
    assert "docs/user-guide/14-corpora.md" in readme


def test_repository_links_in_the_listing_are_absolute():
    """The guide's website publishes only docs/user-guide/, so a link to another repository file must be absolute."""
    import re

    block = _tool().render()
    targets = re.findall(r"\]\(([^)]+)\)", block)
    assert targets and all(t.startswith(("https://", "http://")) for t in targets), [
        t for t in targets if not t.startswith(("https://", "http://"))][:5]


def test_every_registry_part_has_one_entry_and_every_corpus_is_listed():
    tool = _tool()
    entries, _ = tool.load_data()
    assert set(entries) == {(s.source_id, c.part) for s in REGISTRY for c in s.capabilities}
    block = tool.render()
    for src in REGISTRY:
        for cap in src.capabilities:
            assert f"`{src.source_id}` · `{cap.part}`" in block
            corpus_id = cap.sealed[0].corpus_id if cap.sealed else cap.corpus_id  # a sealed part under its sealed id
            if corpus_id and cap.role == "source":
                assert f"| `{corpus_id}` | `{src.source_id}` · `{cap.part}` |" in block


def test_every_count_is_recorded_in_its_committed_evidence_file():
    tool = _tool()
    entries, _ = tool.load_data()
    for entry in entries.values():
        tool.check_entry(entry)  # raises DataError on a mismatch
    counted = [e for e in entries.values() if "count" in e]
    assert counted and all(not e["evidence"].startswith(("/", "~")) for e in counted)


def test_a_count_that_disagrees_with_its_evidence_is_refused(tmp_path):
    tool = _tool()
    entries, _ = tool.load_data()
    pointed = next(e for e in entries.values() if "pointer" in e)
    with pytest.raises(tool.DataError, match="the listing says"):
        tool.check_entry({**pointed, "count": pointed["count"] + 1})
    texted = next(e for e in entries.values() if "count" in e and "pointer" not in e)
    with pytest.raises(tool.DataError, match="does not state"):
        tool.check_entry({**texted, "count": 987_654_321})
    with pytest.raises(tool.DataError, match="not a committed file"):
        tool.check_entry({**texted, "evidence": "../outside.json"})
    with pytest.raises(tool.DataError, match="where"):
        tool.check_entry({"source": "x", "part": "y"})


def test_the_inputs_are_repository_files_only():
    tree = ast.parse((REPO / "tools" / "gen_readme_corpora.py").read_text(encoding="utf-8"))
    modules = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    modules |= {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
    assert not modules & {"urllib", "http", "socket", "requests", "httpx", "os", "subprocess"}
    docstring = ast.get_docstring(tree, clean=False)
    strings = {n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)} - {docstring}
    assert not any("AGENTPROV_HOME" in s or ".agentprov" in s for s in strings)
    assert not {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)} & {"home", "expanduser", "environ"}
    rows = (REPO / "docs/reports/systematic-search/records-merged.jsonl").read_text(encoding="utf-8").splitlines()
    assert f"lists {len([r for r in rows if r.strip()]):,} distinct sources" in _tool().render()
    assert all(json.loads(r)["decision"] in {"included", "excluded"} for r in rows if r.strip())


def test_every_paper_identifier_in_a_profile_is_linked():
    import re

    from agentprov.adapters.profiles import load_profile

    block = _tool().render()
    for src in REGISTRY:
        ids = [c.profile for c in src.capabilities if c.profile]
        if not ids:
            continue
        paper = str(load_profile(ids[0]).data["source"].get("paper", ""))
        for arxiv in re.findall(r"arXiv:(\d{4}\.\d{4,5})", paper):
            assert f"[arXiv:{arxiv}](https://arxiv.org/abs/{arxiv})" in block


def test_paper_cells():
    cell = _tool().paper_cell
    assert cell("arXiv:2406.13352") == "[arXiv:2406.13352](https://arxiv.org/abs/2406.13352)"
    assert cell("none found (phase 10c)") == "none recorded"
    assert cell("") == "none recorded"
    assert cell("A Title (under review)") == "A Title (no identifier recorded)"
    assert cell("T (Zenodo concept 10.5281/zenodo.1)") == "T ([doi:10.5281/zenodo.1](https://doi.org/10.5281/zenodo.1))"
    assert cell("T | x") == "T \\| x (no identifier recorded)"


def test_web_found_papers_are_well_formed_and_marked():
    tool = _tool()
    papers = tool.load_papers()
    block = tool.render()
    for source_id, paper in papers.items():
        row = next(line for line in block.splitlines()  # the sources table: its second cell is a name, not a part
                   if line.startswith(f"| `{source_id}` | ") and " · " not in line.split(" | ")[1])
        assert f"[arXiv:{paper['arxiv']}](https://arxiv.org/abs/{paper['arxiv']})" in row
        assert "found by web search" in row and paper["found"].startswith("web search ")
