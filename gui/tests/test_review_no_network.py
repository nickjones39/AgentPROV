"""GR-13 (S11, D-396): the no-network check is not bypassed by a dynamic import. Statically, a planted module
that imports socket through ``importlib`` or ``__import__`` is rejected; dynamically, a socket loaded through
importlib after psutil (D-545) already loaded it is attributed to its real importer, not to psutil."""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path

import pytest

import test_no_network as s11
from _ast_support import SRC

SOCK = "'soc' + 'ket'"
BYPASSES = {
    "import_module_computed": f"import importlib\nimportlib.import_module({SOCK})\n",
    "from_importlib": f"from importlib import import_module\nimport_module({SOCK})\n",
    "importlib_util": "import importlib.util\n",
    "dunder_import_computed": f"__import__({SOCK})\n",
    "builtins_dunder_import": f"import builtins\nbuiltins.__import__({SOCK})\n",
    "dunder_import_reference": "load = __import__\n",
    # GR-61: pkgutil, runpy and importlib.util import by string, here from inside a function body.
    "pkgutil_resolve_name": f"import pkgutil\ndef f():\n    pkgutil.resolve_name({SOCK})\n",
    "from_pkgutil_resolve_name": "from pkgutil import resolve_name\ndef f():\n    resolve_name('soc' 'ket')\n",
    "runpy_run_module": f"import runpy\ndef f():\n    runpy.run_module({SOCK})\n",
    "from_runpy_run_path": "from runpy import run_path\ndef f(p):\n    run_path(p)\n",
    "from_importlib_util_spec": "from importlib.util import spec_from_file_location\n",
}


def _plant(monkeypatch: pytest.MonkeyPatch, source: str) -> None:
    real = s11.modules

    def planted() -> Iterator[tuple[Path, ast.Module]]:
        yield from real()
        yield SRC / "planted.py", ast.parse(source)

    monkeypatch.setattr(s11, "modules", planted)


@pytest.mark.parametrize("case", sorted(BYPASSES))
def test_static_rejects_dynamic_import(case: str, monkeypatch: pytest.MonkeyPatch) -> None:
    _plant(monkeypatch, BYPASSES[case])
    with pytest.raises(AssertionError, match=r"planted\.py"):
        s11.test_static_no_network_imports()


def test_static_control_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    _plant(monkeypatch, "import json\njson.dumps({})\n")
    s11.test_static_no_network_imports()


def _probe(name: str, body: str) -> str:
    """Driver lines that run ``body`` as the module ``name`` (nothing is written to gui/src)."""
    return (
        f"probe = __import__('types').ModuleType({name!r})\n"
        f"sys.modules[{name!r}] = probe\n"
        f"exec(compile({body!r}, {name!r}, 'exec'), probe.__dict__)\n"
    )


def test_fresh_interpreter_attributes_importlib_socket() -> None:
    early = _probe("probe_early", f"import importlib\nimportlib.__import__({SOCK})\n")
    late = _probe("probe_late", f"import importlib\nimportlib.import_module({SOCK})\n")
    loaded, importers = s11.fresh_interpreter_imports(before=early, after=late)
    bad = s11.network_violations(loaded, importers)
    assert "socket imported by probe_early" in bad, importers
    assert "socket imported by probe_late" in bad, importers


SOCK_NAME = "soc" + "ket"
#: GR-60: socket reached through a tolerated importer's namespace (psutil, D-545; objc, D-448) loads nothing new,
#: so only the static check can see it.
REEXPORTS = {
    "from_psutil_private": f"from psutil._common import {SOCK_NAME} as s\n",
    "psutil_private_chain": f"import psutil\ns = psutil._common.{SOCK_NAME}\n",
    "from_psutil_import_private": f"from psutil import _common\ns = _common.{SOCK_NAME}\n",
    "psutil_public_reexport": f"import psutil as p\ns = p.{SOCK_NAME}\n",
    "from_psutil_reexport": f"from psutil import {SOCK_NAME}\n",
    "from_objc_private": f"from objc._convenience import {SOCK_NAME}\n",
    "objc_private_chain": "import objc\nm = objc._convenience\n",
}


@pytest.mark.parametrize("case", sorted(REEXPORTS))
def test_static_rejects_reexported_socket(case: str, monkeypatch: pytest.MonkeyPatch) -> None:
    _plant(monkeypatch, REEXPORTS[case])
    with pytest.raises(AssertionError, match=r"planted\.py"):
        s11.test_static_no_network_imports()


def test_static_allows_public_psutil(monkeypatch: pytest.MonkeyPatch) -> None:
    _plant(monkeypatch, "import psutil\npsutil.Process(1).create_time()\npsutil.virtual_memory()._asdict()\n")
    s11.test_static_no_network_imports()
