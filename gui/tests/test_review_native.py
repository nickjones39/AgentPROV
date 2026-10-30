"""GR-14 (S15, D-448): the native-layer lint confines ctypes, cffi and shiboken6 as well as PyObjC, and sees string
imports. Each planted module is added to the scanned sources under the given path; the S15 lint must reject it unless
the family is imported from its own platform module."""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path

import pytest

import test_lint_native as s15
from _ast_support import SRC

CT = "c" + "types"
OBJC = "'ob' 'jc'"
BYPASSES = {
    "import_ctypes": ("ui/x.py", f"import {CT}\n"),
    "from_ctypes": ("ui/x.py", f"from {CT} import windll\n"),
    "import_private_ctypes": ("ui/x.py", f"import _{CT}\n"),
    "import_cffi": ("ui/x.py", "import cffi\n"),
    "import_cffi_backend": ("ui/x.py", "import _cffi_backend\n"),
    "import_shiboken6": ("ui/x.py", "import shiboken6\n"),
    "from_shiboken6": ("ui/x.py", "from shiboken6 import Shiboken\n"),
    "import_module_objc": ("ui/x.py", f"import importlib\nimportlib.import_module({OBJC})\n"),
    "dunder_import_appkit": ("ui/x.py", "__import__('App' 'Kit')\n"),
    "ctypes_in_macos": ("platform/macos.py", f"import {CT}\n"),
    "objc_in_windows": ("platform/windows.py", "import objc\n"),
}
CONTROLS = {
    "ctypes_in_windows": ("platform/windows.py", f"import {CT}\nfrom {CT} import windll\n"),
    "objc_in_macos": ("platform/macos.py", "import objc\n"),
    "plain_import": ("ui/x.py", "import json\n"),
}


def _plant(monkeypatch: pytest.MonkeyPatch, path: str, source: str) -> None:
    real = s15.modules

    def planted() -> Iterator[tuple[Path, ast.Module]]:
        yield from real()
        yield SRC / path, ast.parse(source)

    monkeypatch.setattr(s15, "modules", planted)


@pytest.mark.parametrize("case", sorted(BYPASSES))
def test_native_import_outside_its_module_is_rejected(case: str, monkeypatch: pytest.MonkeyPatch) -> None:
    path, source = BYPASSES[case]
    _plant(monkeypatch, path, source)
    with pytest.raises(AssertionError, match=path):
        s15.test_pyobjc_only_in_the_native_module()


@pytest.mark.parametrize("case", sorted(CONTROLS))
def test_native_import_in_its_module_passes(case: str, monkeypatch: pytest.MonkeyPatch) -> None:
    _plant(monkeypatch, *CONTROLS[case])
    s15.test_pyobjc_only_in_the_native_module()
