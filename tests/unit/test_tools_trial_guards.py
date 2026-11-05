"""The trial-import scripts refuse to write into the real corpora directory (audit AU-TRS-9).

``phase10d_trial.py import`` compared the unresolved path as a string (a relative path or a symlink passed), and every
trial script looked only under ``~/.agentprov``, never ``$AGENTPROV_HOME``. Each script's guard is now one resolved
``is_relative_to`` check against both. The scripts are loaded by path; nothing is imported or written.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO = Path(__file__).resolve().parents[2]
GUARDS = {  # script -> guard function
    "tools/agentdojo/phase10d_trial.py": "refuse_real_corpora",
    "tools/agentdojo/phase10q_trial.py": "_refuse_real_corpora",
    "tools/inspect/phase10h_trial.py": "_refuse_real_corpora",
    "tools/inspect/phase10p_trial.py": "_refuse_real_corpora",
    "tools/autogen/phase10n_trial.py": "_refuse_real_corpora",
    "tools/geminicli/trial_import.py": "_refuse_real_corpora",
    "tools/qwencode/trial_import.py": "_refuse_real_corpora",
}


def _load(rel: str) -> ModuleType:
    name = "_trial_guard_" + rel.replace("/", "_").removesuffix(".py")
    if name in sys.modules:
        return sys.modules[name]
    path = REPO / rel
    sys.path.insert(0, str(path.parent))
    try:
        spec = importlib.util.spec_from_file_location(name, path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(path.parent))
    return module


def test_phase10j_uses_the_phase10d_guard() -> None:
    assert "d10.refuse_real_corpora(corpus)" in (REPO / "tools" / "agentdojo" / "phase10j_trial.py").read_text()


@pytest.mark.parametrize("rel", sorted(GUARDS))
def test_guard_refuses_relative_symlinked_and_agentprov_home_paths(rel, tmp_path, monkeypatch) -> None:
    guard = getattr(_load(rel), GUARDS[rel])
    home, custom = tmp_path / "home", tmp_path / "volume"
    for corpora in (home / ".agentprov" / "corpora", custom / "corpora"):
        corpora.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AGENTPROV_HOME", str(custom))
    (tmp_path / "link").symlink_to(custom / "corpora")
    monkeypatch.chdir(custom)
    for refused in (Path("corpora/trial"), tmp_path / "link" / "trial", custom / "corpora" / "x",
                    home / ".agentprov" / "corpora" / "y", Path("~/.agentprov/corpora/z")):
        with pytest.raises(SystemExit, match="never write"):
            guard(refused)
    for allowed in (custom / "corpora-scratch" / "t", tmp_path / "scratch" / "t", Path("staging/t")):
        guard(allowed)
