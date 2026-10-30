"""A test module imported by its bare name must be the only module of that name under ``tests/`` (bug pass BF-36).

``import test_withhold_e2e`` resolved to whichever directory came first on ``sys.path`` in the worker: credleak's
``test_runner_multi_execution.py`` got geminicli's module (same name) whenever both ran in one xdist worker, and failed
sealing with the wrong spec. A name that exists twice is loaded by path under a unique module name instead
(``importlib.util.spec_from_file_location``, as ``tests/prov/conftest.py`` does).
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

TESTS = Path(__file__).resolve().parents[2]
_BARE = re.compile(r"^\s*(?:import (test_\w+)|from (test_\w+) import)\b", re.MULTILINE)
#: Names still imported bare although they are not unique (none: BF-35 loads test_semantics by path).
_PENDING: set[str] = set()


def test_every_test_module_imported_by_name_is_unique():
    names = Counter(p.stem for p in TESTS.rglob("test_*.py"))
    imported = {m.group(1) or m.group(2): p.relative_to(TESTS).as_posix()
                for p in TESTS.rglob("*.py") for m in _BARE.finditer(p.read_text(encoding="utf-8"))}
    ambiguous = {name: where for name, where in imported.items() if names[name] > 1 and name not in _PENDING}
    assert ambiguous == {}
