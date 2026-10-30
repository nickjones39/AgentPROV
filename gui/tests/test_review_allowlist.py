"""GR-12 (D-391): the core allowlist lint is not bypassed by a whole-package import, an attribute chain or a
dynamic import. Each planted module is added to the scanned sources; at least one allowlist test must reject it."""

from __future__ import annotations

import ast
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

import test_core_allowlist as allowlist
from _ast_support import SRC

PKG = "agentprov" + ".corpus"
CLI = "agentprov" + ".cli"
WRITER = PKG + ".writer"

BYPASSES = {
    "bare_package_import": f"import {PKG}\n{PKG}.CorpusWriter\n",
    "package_alias_chain": f"import {PKG} as c\nc.writer.CorpusWriter\n",
    "import_module_literal": f"import importlib\nimportlib.import_module({CLI!r})\n",
    "dunder_import_literal": f"__import__({WRITER!r})\n",
    "import_module_computed": f"import importlib\nimportlib.import_module({'agentprov'!r} + {'.cli'!r})\n",
    "dunder_import_name": "name = 'x'\n__import__(name)\n",
    "from_importlib_computed": "from importlib import import_module\nimport_module(''.join(['a']))\n",
    "chain_off_allowed_import": f"import agentprov.versions\n{WRITER}.CorpusWriter\n",
    # GR-61: other stdlib routes that import a module named by a string, called inside a function body.
    "resolve_name_literal": f"import pkgutil\ndef f():\n    pkgutil.resolve_name({CLI!r})\n",
    "resolve_name_attr": f"from pkgutil import resolve_name\ndef f():\n    resolve_name({WRITER + ':CorpusWriter'!r})\n",
    "run_module_literal": f"import runpy\ndef f():\n    runpy.run_module({CLI!r}, run_name='__main__')\n",
    "run_path_computed": "import runpy\ndef f(p):\n    runpy.run_path(p)\n",
    "find_spec_literal": f"from importlib.util import find_spec\ndef f():\n    find_spec({CLI!r})\n",
}
CONTROLS = {
    "from_allowed_module": "from agentprov.corpus.reader import CorpusReader\n",
    "from_package_allowed_name": "from agentprov.render import style\n",
    "from_agentprov_allowed": "from agentprov import versions\n",
    "allowed_import_chain": "import agentprov.versions\nagentprov.versions.SOFTWARE\n",
    "allowed_import_alias": "import agentprov.corpus.reader as r\nr.CorpusReader\n",
}


def _tests() -> list[Callable[[], None]]:
    return [getattr(allowlist, n) for n in sorted(dir(allowlist)) if n.startswith("test_")]


def _plant(monkeypatch: pytest.MonkeyPatch, source: str) -> None:
    real = allowlist.modules

    def planted() -> Iterator[tuple[Path, ast.Module]]:
        yield from real()
        yield SRC / "planted.py", ast.parse(source)

    monkeypatch.setattr(allowlist, "modules", planted)


def _failures(source: str, monkeypatch: pytest.MonkeyPatch) -> list[str]:
    _plant(monkeypatch, source)
    failed = []
    for test in _tests():
        try:
            test()
        except AssertionError:
            failed.append(test.__name__)
    return failed


@pytest.mark.parametrize("case", sorted(BYPASSES))
def test_bypass_is_rejected(case: str, monkeypatch: pytest.MonkeyPatch) -> None:
    assert _failures(BYPASSES[case], monkeypatch), f"{case} passes every D-391 allowlist test"


@pytest.mark.parametrize("case", sorted(CONTROLS))
def test_allowlisted_import_still_passes(case: str, monkeypatch: pytest.MonkeyPatch) -> None:
    assert _failures(CONTROLS[case], monkeypatch) == []
