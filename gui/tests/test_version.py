"""The desktop app shows one version: ``agentprov_gui.__version__`` equals ``gui/pyproject.toml``'s, and the PyInstaller
spec stamps the bundle's Info.plist with it (v0.1.1: About still said 0.1.0 after the pyproject bump)."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import agentprov_gui

GUI = Path(__file__).resolve().parents[1]


def test_the_package_version_is_the_pyproject_version() -> None:
    declared = tomllib.loads((GUI / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    assert agentprov_gui.__version__ == declared


def test_the_bundle_takes_its_version_from_the_package() -> None:
    spec = (GUI / "packaging" / "agentprov-gui.spec").read_text(encoding="utf-8")
    assert not re.search(r'^VERSION = "', spec, re.M), "the spec must read agentprov_gui.__version__, not repeat it"
    namespace: dict[str, object] = {"GUI": GUI}
    line = spec[spec.index("VERSION = next("):]
    exec(line[: line.index("))\n") + 2], namespace)  # the spec's own expression, run on its own source
    assert namespace["VERSION"] == agentprov_gui.__version__
