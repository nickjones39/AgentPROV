"""CA-24: the software version has one source, ``pyproject.toml`` ``[project].version`` via ``importlib.metadata``.

HL L.1.1 row 1. The ``expand`` stage records ``importlib.metadata.version("agentprov")`` (raw/members.py); every other
stage and ``producer.agentprov_version`` record ``versions.__version__``. A release bump done the L.1.1 way (pyproject
only) must not leave two engine versions in one corpus.
"""

from __future__ import annotations

import tomllib
from importlib import metadata
from pathlib import Path

import agentprov
from agentprov import versions
from agentprov.raw import members

PYPROJECT = Path(agentprov.__file__).resolve().parents[2] / "pyproject.toml"


def test_the_software_version_follows_the_installed_metadata(monkeypatch):
    monkeypatch.setattr(versions.metadata, "version", lambda name: "9.9.9" if name == "agentprov" else "0")
    assert versions._software_version() == "9.9.9"


def test_an_uninstalled_tree_falls_back_to_the_release_literal(monkeypatch):
    def missing(name: str) -> str:
        raise metadata.PackageNotFoundError(name)

    monkeypatch.setattr(versions.metadata, "version", missing)
    assert versions._software_version() == versions._UNINSTALLED_VERSION


def test_every_recorded_software_version_agrees():
    declared = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]["version"]
    assert declared == metadata.version("agentprov") == versions.__version__ == versions.VERSIONS["software"]
    assert members._engine_version() == versions.__version__
    assert versions._UNINSTALLED_VERSION == declared


def test_every_package_version_literal_equals_its_pyproject():
    """v0.1.1: the pyproject bump left ``__version__ = "0.1.0"`` in agentprov-capture, agentprov-backend and the GUI, so
    About and new capture logs named the old version. A package that keeps a literal keeps it equal to its pyproject."""
    import re

    root = PYPROJECT.parent
    packages = {"capture": "capture/src/agentprov_capture/__init__.py",
                "backends/shared": "backends/shared/src/agentprov_backend/__init__.py",
                "backends/inspect": "backends/inspect/src/agentprov_backend_inspect/__init__.py",
                "gui": "gui/src/agentprov_gui/__init__.py"}
    for project, init in packages.items():
        declared = tomllib.loads((root / project / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
        literal = re.search(r'^__version__ = "([^"]+)"', (root / init).read_text(encoding="utf-8"), re.M)
        assert literal is not None and literal.group(1) == declared, project
