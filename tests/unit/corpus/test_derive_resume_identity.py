"""BF-32 (N.1.8(3)): an interrupted ``derive`` resumed with other semantics profiles is refused (exit 4), not merged.

``derived_from`` records the semantics profiles and the function digests of the recomputed layers, so a resume under
another ``--semantics-profile`` no longer matches and ``NEW.partial`` never holds two profiles' SEM side by side. The
source is an AER-only AgentDojo working corpus of ``derive_support``. Fixture text is never printed.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import derive_support as ds
import pytest

from agentprov.cli.main import main


@pytest.fixture(autouse=True)
def _home(monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory) -> None:
    monkeypatch.setenv("AGENTPROV_HOME", str(tmp_path_factory.mktemp("home")))
    monkeypatch.delenv("AGENTPROV_PROGRESS", raising=False)


def _run(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, str]:
    capsys.readouterr()
    code = main([*argv, "--json", "--progress", "off"])
    return code, capsys.readouterr().err


def _interrupted_derive(capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, src: Path, out: Path,
                        profile: str) -> None:
    from agentprov.corpus import derive

    real = derive.Derivation._finish_unit
    calls = {"n": 0}

    def flaky(self: Any, *args: Any, **kwargs: Any) -> Any:
        calls["n"] += 1
        if calls["n"] == 2:
            raise KeyboardInterrupt
        return real(self, *args, **kwargs)

    monkeypatch.setattr(derive.Derivation, "_finish_unit", flaky)
    code, _err = _run(capsys, "derive", "--corpus", str(src), "--out", str(out), "--in-process",
                      "--semantics-profile", profile)
    monkeypatch.setattr(derive.Derivation, "_finish_unit", real)
    assert code == 130 and len(ds.rows(ds.partial(out))) == 1


def test_a_resume_under_another_semantics_profile_is_refused(capsys, tmp_path, monkeypatch):
    src = ds.agentdojo_corpus(tmp_path, name="aer-only", count=2, until="aer")
    out = tmp_path / "new"
    _interrupted_derive(capsys, monkeypatch, src, out, "agentdojo.suites@2")
    derived_from = json.loads((ds.partial(out) / "corpus.json").read_text())["derived_from"]
    assert derived_from["semantics"] == ["agentdojo.suites@2"] and "sem" in derived_from["fn_digests"]
    code, err = _run(capsys, "derive", "--corpus", str(src), "--out", str(out), "--in-process",
                     "--semantics-profile", "agentdojo.suites@3")
    assert code == 4 and "corpus.derive.resume_mismatch" in err
    assert sorted(p.name for p in (ds.partial(out) / "sem").iterdir()) == ["agentdojo.suites-2"]


def test_a_resume_under_the_same_semantics_profile_still_resumes(capsys, tmp_path, monkeypatch):
    src = ds.agentdojo_corpus(tmp_path, name="aer-only", count=2, until="aer")
    out = tmp_path / "new"
    _interrupted_derive(capsys, monkeypatch, src, out, "agentdojo.suites@2")
    code, err = _run(capsys, "derive", "--corpus", str(src), "--out", str(out), "--in-process",
                     "--semantics-profile", "agentdojo.suites@2")
    assert code == 0, err
    assert len(ds.rows(ds.partial(out))) == 2
