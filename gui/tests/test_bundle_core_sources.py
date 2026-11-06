"""D-1130 review (B1): the bundle's own agentprov records code digests and library versions in the corpora it writes,
so the bundle carries the core's source files and the metadata of the distributions a corpus records.
``build_bundle.check_core_sources`` compares them with the build environment on fixture trees of every OS; the spec's
list of distributions is the core's; and the entry point imports the CLI only for a CLI call (D-391)."""

from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

import pytest

GUI = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(GUI / "tools"))

import build_bundle as bb  # noqa: E402
from agentprov.cli import frozen  # noqa: E402

SPEC = GUI / "packaging" / "agentprov-gui.spec"
ENTRY = GUI / "packaging" / "entry.py"
VERSION = "1.2.3"


def _touch(path: Path, data: bytes = b"") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def _package(root: Path) -> Path:
    pkg = root / "src" / "agentprov"
    _touch(pkg / "__init__.py", b"x = 1\n")
    _touch(pkg / "prov" / "engine.py", b"def f():\r\n    return 1\r\n")
    _touch(pkg / "prov" / "rules.toml", b"[a]\n")
    _touch(pkg / "schemas" / "s.json", b"{}\n")
    _touch(pkg / "vocab" / "apv.ttl", b"@prefix x: <y> .\n")
    _touch(pkg / "docs" / "user-guide" / "README.md", b"guide\n")  # never bundled: not compared
    _touch(pkg / "prov" / "__pycache__" / "engine.cpython-314.pyc", b"\0")  # bytecode: not compared
    return pkg


def _bundle(root: Path, pkg: Path, platform: str) -> Path:
    app = bb.bundle_path(root / "dist", platform)
    res = bb._resources(app, platform)
    for path in pkg.rglob("*"):
        rel = path.relative_to(pkg).as_posix()
        if path.is_file() and not rel.startswith("docs/") and "__pycache__" not in rel:
            data = path.read_bytes()
            _touch(res / "agentprov" / rel, data.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n") if platform == "win32" else data)
    for name in frozen.RECORDED_DISTRIBUTIONS:
        (res / f"{bb._dist_key(name)}-{VERSION}.dist-info").mkdir(parents=True)
    return app


def _check(app: Path, pkg: Path, platform: str) -> list[str]:
    return bb.check_core_sources(app, platform, package=pkg, version=lambda name: VERSION)


@pytest.mark.parametrize("platform", ["darwin", "win32", "linux"])
def test_a_bundle_with_the_build_environments_sources_and_metadata_passes(tmp_path: Path, platform: str) -> None:
    pkg = _package(tmp_path)
    assert _check(_bundle(tmp_path, pkg, platform), pkg, platform) == []


@pytest.mark.parametrize("platform", ["darwin", "linux"])
def test_a_missing_differing_or_extra_source_file_is_named(tmp_path: Path, platform: str) -> None:
    pkg = _package(tmp_path)
    app = _bundle(tmp_path, pkg, platform)
    res = bb._resources(app, platform) / "agentprov"
    (res / "prov" / "engine.py").unlink()
    (res / "prov" / "rules.toml").write_bytes(b"[b]\n")
    _touch(res / "extra.py", b"")
    assert _check(app, pkg, platform) == ["missing: agentprov/prov/engine.py", "differs: agentprov/prov/rules.toml",
                                          "extra: agentprov/extra.py"]


def test_a_bundle_of_bytecode_only_fails_as_the_d1130_bundle_did(tmp_path: Path) -> None:
    pkg = _package(tmp_path)
    app = _bundle(tmp_path, pkg, "darwin")
    for path in (bb._resources(app, "darwin") / "agentprov").rglob("*.py"):
        path.unlink()
    assert {p.split(":")[0] for p in _check(app, pkg, "darwin")} == {"missing"}


def test_missing_or_other_metadata_is_named(tmp_path: Path) -> None:
    pkg = _package(tmp_path)
    app = _bundle(tmp_path, pkg, "linux")
    res = bb._resources(app, "linux")
    (res / f"prov-{VERSION}.dist-info").rmdir()
    (res / f"rdflib-{VERSION}.dist-info").rename(res / "rdflib-7.0.0.dist-info")
    assert _check(app, pkg, "linux") == [f"metadata: prov {VERSION} missing from the bundle",
                                         f"metadata: rdflib {VERSION} missing from the bundle (has 7.0.0)"]


def test_macos_metadata_linked_from_frameworks_counts(tmp_path: Path) -> None:
    pkg = _package(tmp_path)
    app = _bundle(tmp_path, pkg, "darwin")
    res = bb._resources(app, "darwin")
    (app / "Contents" / "Frameworks").mkdir(parents=True)
    (res / f"pyyaml-{VERSION}.dist-info").rename(app / "Contents" / "Frameworks" / f"PyYAML-{VERSION}.dist-info")
    assert _check(app, pkg, "darwin") == []


def test_the_real_core_package_has_every_digested_file_and_the_check_reads_it(tmp_path: Path) -> None:
    import agentprov

    pkg = Path(agentprov.__file__).resolve().parent
    problems = bb.check_core_sources(_bundle(tmp_path, _package(tmp_path), "linux"), "linux", package=pkg,
                                     version=lambda name: VERSION)
    assert "differs: agentprov/__init__.py" in problems and "missing: agentprov/stage_definitions.py" in problems


def test_the_spec_records_the_cores_list_of_distributions() -> None:
    tree = ast.parse(SPEC.read_text(encoding="utf-8"))
    found = [node.value for node in ast.walk(tree) if isinstance(node, ast.Assign)
             and any(isinstance(t, ast.Name) and t.id == "RECORDED_DISTRIBUTIONS" for t in node.targets)]
    assert len(found) == 1 and ast.literal_eval(found[0]) == frozen.RECORDED_DISTRIBUTIONS
    text = SPEC.read_text(encoding="utf-8")
    assert 'collect_data_files("agentprov", excludes=["docs/**"], include_py_files=True)' in text
    assert "copy_metadata(dist)" in text


def test_the_entry_point_knows_the_cli_forms_without_importing_the_cli() -> None:
    tree = ast.parse(ENTRY.read_text(encoding="utf-8"))
    value = next(node.value for node in ast.walk(tree) if isinstance(node, ast.Assign)
                 and any(isinstance(t, ast.Name) and t.id == "CLI_FIRST" for t in node.targets))
    assert isinstance(value, ast.Call)
    assert set(ast.literal_eval(value.args[0])) == {frozen.CLI_FLAG, frozen.KEYCHAIN_FLAG, "-m", "-c",
                                                     *frozen.PYTHON_FLAGS}
    top = [n for n in tree.body if isinstance(n, ast.Import | ast.ImportFrom)]
    assert all(not (isinstance(n, ast.ImportFrom) and (n.module or "").startswith("agentprov")) for n in top)


_DRIVER = """
import importlib.util, sys, types
stub = types.ModuleType("agentprov_gui.app")
stub.main = lambda argv: 0
import agentprov_gui
sys.modules["agentprov_gui.app"] = stub
spec = importlib.util.spec_from_file_location("entry", sys.argv[1])
entry = importlib.util.module_from_spec(spec)
spec.loader.exec_module(entry)
sys.argv = ["AgentPROV", *sys.argv[2:]]
code = entry.run()
print(code, sorted(m for m in sys.modules if m == "agentprov.cli" or m.startswith("agentprov.cli.")))
"""


@pytest.mark.parametrize(("argv", "cli"), [([], False), (["corpus.json"], False), (["--cli", "--version"], True)])
def test_the_gui_process_never_loads_the_cli(argv: list[str], cli: bool) -> None:
    done = subprocess.run([sys.executable, "-I", "-c", _DRIVER, str(ENTRY), *argv], capture_output=True, text=True,
                          env={**os.environ, "QT_QPA_PLATFORM": "offscreen"}, timeout=120, check=False)
    assert done.returncode == 0, done.stderr
    last = done.stdout.strip().splitlines()[-1]
    assert last.startswith("0 ")
    assert ("agentprov.cli.frozen" in last) is cli


def test_the_smoke_step_recognises_the_bundles_refusal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    seen: list[str] = []
    code = frozen._cli(["derive", "--corpus", "c", "--out", "o"], load=lambda n: None, err=seen.append,
                       problem=lambda: "the core's source files")
    assert code == 3 and seen and seen[0].startswith(bb.SOURCES_REFUSAL)
