"""``tools/gen_registry.py``: the registry as one module per source and family, with generated static lists (D-426).

Every test works on a copy of today's ``adapters/registry/__init__.py`` under ``tmp_path`` (the registry imports only
the standard library, so a stub ``agentprov`` package is enough). The real package is only read.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import gen_registry as gr
import pytest

REPO = Path(__file__).resolve().parents[3]
REAL_INIT = REPO / gr.PKG / "__init__.py"

pytestmark = pytest.mark.skipif(not REAL_INIT.is_file() or (REPO / gr.PKG / "_legacy_order.py").is_file(),
                                reason="the registry is already split (tests/repo checks the generated modules)")


def _copy(root: Path) -> Path:
    gr.isolated_copy(REAL_INIT.read_text(encoding="utf-8"), root / "src")
    return root / gr.PKG


def _import(root: Path, expr: str) -> object:
    code = (f"import json, sys; sys.path.insert(0, {str(root / 'src')!r}); "
            f"import agentprov.adapters.registry as r; print(json.dumps({expr}))")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def test_split_of_todays_registry_keeps_every_public_value(tmp_path: Path) -> None:
    before = gr.snapshot(gr.isolated_copy(REAL_INIT.read_text(encoding="utf-8"), tmp_path / "before"))
    pkg = _copy(tmp_path / "root")
    assert gr.main(["-C", str(tmp_path / "root"), "--check"]) == 0  # not migrated yet
    written = gr.split(tmp_path / "root")
    assert str(gr.PKG / "_sources.py") in written and str(gr.PKG / "_factories.py") in written
    assert gr.snapshot(tmp_path / "root" / "src") == before
    assert gr.main(["-C", str(tmp_path / "root"), "--check"]) == 0
    sources = sorted(p.stem for p in (pkg / "sources").glob("*.py") if p.stem != "__init__")
    assert len(sources) == len(before["REGISTRY"].split("SourceRegistration(")) - 1  # type: ignore[union-attr]
    assert {p.stem for p in (pkg / "families").glob("*.py")} >= {"agentdojo", "inspect", "__init__"}
    with pytest.raises(ValueError, match="already split"):
        gr.split(tmp_path / "root")


def test_generated_list_is_static(tmp_path: Path) -> None:
    _copy(tmp_path)
    gr.split(tmp_path)
    text = (tmp_path / gr.PKG / "_sources.py").read_text(encoding="utf-8")
    assert "importlib" not in text and "__import__" not in text and "glob" not in text
    assert all(line.startswith(("from ", '"""', "REGISTRY", "    ", ")")) or not line
               for line in text.splitlines())


def test_a_new_source_and_a_new_family(tmp_path: Path) -> None:
    pkg = _copy(tmp_path)
    gr.split(tmp_path)
    template = (pkg / "sources" / "glitch_agentdojo.py").read_text(encoding="utf-8")
    (pkg / "sources" / "aaa_new_source.py").write_text(template.replace('"glitch-agentdojo"', '"aaa-new-source"'),
                                                       encoding="utf-8")
    (pkg / "families" / "zfam.py").write_text('READERS = {"zfam.log": "agentprov.adapters.zfam.dialect:R"}\n'
                                              'MAPPERS = {"zfam.log": "agentprov.adapters.zfam.mapper:M"}\n',
                                              encoding="utf-8")
    assert gr.main(["-C", str(tmp_path), "--check"]) == 1
    assert gr.main(["-C", str(tmp_path), "--write"]) == 0
    assert gr.main(["-C", str(tmp_path), "--check"]) == 0
    ids = _import(tmp_path, "[x.source_id for x in r.REGISTRY]")
    assert isinstance(ids, list) and ids[-1] == "aaa-new-source" and ids[0] == "agentdojo"  # new after legacy
    readers = _import(tmp_path, "list(r.READERS)")
    assert isinstance(readers, list) and readers[-1] == "zfam.log"
    assert _import(tmp_path, "r.get_source('aaa-new-source').name") == "Glitch on AgentDojo (zanethomas1430-code/Glitch)"


def test_inconsistencies_are_refused(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    pkg = _copy(tmp_path)
    gr.split(tmp_path)
    (pkg / "families" / "zfam.py").write_text('READERS = {"inspect.eval": "agentprov.adapters.zfam.dialect:R"}\n'
                                              "MAPPERS = {}\n", encoding="utf-8")
    assert gr.main(["-C", str(tmp_path), "--write"]) == 2
    assert "defined by two families" in capsys.readouterr().out
    (pkg / "families" / "zfam.py").write_text('READERS = {"zfam.log": "agentprov.adapters.other.dialect:R"}\n'
                                              "MAPPERS = {}\n", encoding="utf-8")
    assert gr.main(["-C", str(tmp_path), "--write"]) == 2
    assert "names another family's module" in capsys.readouterr().out
    (pkg / "families" / "zfam.py").unlink()
    (pkg / "sources" / "rope.py").unlink()
    assert gr.main(["-C", str(tmp_path), "--check"]) == 2
    assert "legacy entries missing: rope" in capsys.readouterr().out


def test_a_split_that_would_change_values_writes_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pkg = _copy(tmp_path)
    real_plan = gr.plan_split

    def lossy(text: str) -> dict[str, str]:
        files = real_plan(text)
        files["sources/rope.py"] = files["sources/rope.py"].replace('"rope"', '"rope-renamed"', 1)
        return files

    monkeypatch.setattr(gr, "plan_split", lossy)
    with pytest.raises(ValueError, match="changes public names: REGISTRY"):
        gr.split(tmp_path)
    assert sorted(p.name for p in pkg.iterdir()) == ["__init__.py"]


def test_module_names() -> None:
    assert gr.module_name("adprov-v1") == "adprov_v1"
    assert gr.module_name("kexin-xu-01-agentharm") == "kexin_xu_01_agentharm"
    assert gr.module_name("2024-runs") == "s_2024_runs"
    assert gr.module_name("import") == "s_import"
    assert gr.family_of("agentprov.adapters.inspect.dialect:InspectEvalReader") == "inspect"
    with pytest.raises(ValueError):
        gr.family_of("os:system")
