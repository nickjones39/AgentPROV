"""SEC-23 (K.14, G.7): locked, wheel-only, cooled-off dependencies; no plugin loading; registry and profiles closed.

`uv lock --check` and osv-scanner are process controls in CI (jobs `core` and `dependencies`); this file proves the
properties that can be read from the repository itself.
"""

from __future__ import annotations

import ast
import re
import tomllib
from pathlib import Path

import pytest

from agentprov.errors import AgentProvError

ROOT = Path(__file__).resolve().parents[2]
LOCKS = ("uv.lock", "backends/shared/uv.lock", "backends/agentdojo/uv.lock", "backends/autodojo/uv.lock",
         "backends/agentdyn/uv.lock", "backends/inspect/envs/agentharm/uv.lock")
PROJECTS = (".", "backends/shared", "backends/agentdojo", "backends/autodojo", "backends/agentdyn", "backends/inspect",
            "backends/inspect/envs/agentharm")  # capture/ and zenodo/ are members of the root lock
EXCLUDE_NEWER = "2026-10-07T00:00:00Z"
#: Packages that are not wheels from the index, and why (G.7.1(5)).
NON_REGISTRY = {
    "agentprov": "the core itself (editable)",
    "agentprov-capture": "this repository's capture/ project",
    "agentprov-zenodo": "this repository's zenodo/ project, the draft-only uploader (D-880)",
    "agentprov-backend": "this repository's backends/shared/ project",
    "agentprov-backend-agentdojo": "the backend project (virtual)",
    "agentprov-backend-autodojo": "the backend project (virtual)",
    "agentprov-backend-agentdyn": "the backend project (virtual)",
    "agentprov-backend-inspect": "this repository's backends/inspect/ harness package (D-662)",
    "agentprov-backend-inspect-agentharm": "the inspect-agentharm environment project (virtual, D-662)",
    "agentdojo": "the AutoDojo fork or AgentDyn, each pinned to a full commit (D.11, D.11.10)",
}
COMMIT = re.compile(r"[#&]rev=[0-9a-f]{40}(?:#|$)|#[0-9a-f]{40}$")


def _lock(path: str) -> dict:
    return tomllib.loads((ROOT / path).read_text(encoding="utf-8"))


@pytest.mark.parametrize("lock", LOCKS)
def test_sec23_every_index_package_is_a_wheel_and_every_other_source_is_known(lock: str) -> None:
    for package in _lock(lock)["package"]:
        source = package.get("source", {})
        kind = next(iter(source), None)
        if kind == "registry":
            assert package.get("wheels"), f"{lock}: {package['name']} has no wheel (sdist builds run code)"
        else:
            assert package["name"] in NON_REGISTRY, f"{lock}: unexpected {kind} source {package['name']}"
            if kind == "git":
                assert COMMIT.search(source["git"]), f"{lock}: git source not pinned to a full commit"


@pytest.mark.parametrize("lock", LOCKS)
def test_sec23_locks_record_the_fixed_cooling_off_date(lock: str) -> None:
    assert _lock(lock)["options"]["exclude-newer"] == EXCLUDE_NEWER


@pytest.mark.parametrize("project", PROJECTS)
def test_sec23_projects_declare_the_same_fixed_exclude_newer(project: str) -> None:
    config = tomllib.loads((ROOT / project / "pyproject.toml").read_text(encoding="utf-8"))
    assert config["tool"]["uv"]["exclude-newer"] == EXCLUDE_NEWER


@pytest.mark.parametrize("lock", LOCKS)
def test_sec23_no_lock_carries_rdflib_plugin_entry_points_or_the_core_package_in_a_backend(lock: str) -> None:
    text = (ROOT / lock).read_text(encoding="utf-8")
    assert "rdf.plugins" not in text
    if lock != "uv.lock":
        assert not any(p["name"] == "agentprov" for p in _lock(lock)["package"])


def _sources(*roots: str) -> list[Path]:
    return sorted(p for root in roots for p in (ROOT / root).rglob("*.py"))


def test_sec23_no_module_loads_plugins_through_entry_points() -> None:
    offenders = []
    for path in _sources("src/agentprov", "capture/src", "backends/shared/src"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            name = node.attr if isinstance(node, ast.Attribute) else node.id if isinstance(node, ast.Name) else None
            if name == "entry_points":
                offenders.append(str(path.relative_to(ROOT)))
    assert offenders == []


def test_sec23_every_registry_factory_is_agentprov_namespaced_and_resolves() -> None:
    from agentprov.adapters.registry import MAPPERS, READERS
    from agentprov.adapters.runner import resolve_factory

    for path in [*READERS.values(), *MAPPERS.values()]:
        assert path.startswith("agentprov.adapters.") and ":" in path
        assert callable(resolve_factory(path))


@pytest.mark.parametrize("path", ["os:system", "subprocess:Popen", "agentprov_evil.x:Y", "agentprovx:Y",
                                  "agentprov.adapters.foobench.dialect", "agentprov.adapters.foobench.dialect:1x",
                                  "agentprov.adapters.foobench.dialect:Foo Bar", ""])
def test_sec23_factories_outside_the_namespace_are_refused_before_any_import(path: str,
                                                                            monkeypatch: pytest.MonkeyPatch) -> None:
    import agentprov.adapters.runner as runner

    monkeypatch.setattr(runner, "import_module", lambda name: pytest.fail(f"imported {name!r}"))
    with pytest.raises(AgentProvError) as exc:
        runner.resolve_factory(path)
    assert exc.value.code == "adapter.factory"


def test_sec23_profile_files_are_refused_outside_dev_mode(tmp_path: Path) -> None:
    from agentprov.adapters.profiles import load_profile_file
    from agentprov.errors import ProfileError

    file = tmp_path / "x.profile.toml"
    file.write_text("[profile]\n", encoding="utf-8")
    with pytest.raises(ProfileError):
        load_profile_file(file, mode="release")  # type: ignore[arg-type]
