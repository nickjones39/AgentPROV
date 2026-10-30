"""GUI review GR-66: a control character (NUL included) in a stored ``paths/checkout`` or ``paths/corpus_roots`` used to
reach ``os.stat`` and ``os.scandir`` and crash MainWindow at start-up with ``ValueError``, before any window existed to
fix it. The value is now dropped (default used) on load, and refused on save."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

NUL = chr(0)
BEL = chr(7)


def _settings(tmp_path: Path) -> Any:
    from PySide6.QtCore import QSettings

    from agentprov_gui.settings import Settings

    return Settings(QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat))


@pytest.mark.parametrize(("key", "value"), [
    ("paths/checkout", "/tmp/a" + NUL + "b"),
    ("paths/checkout", "/tmp/a" + BEL + "b"),
    ("paths/corpus_roots", "/tmp/a" + NUL + "b"),
    ("paths/corpus_roots", ["/tmp/a" + NUL + "b"]),
])
def test_control_character_path_falls_back_and_mainwindow_builds(qapp: Any, tmp_path: Path, key: str, value: Any) -> None:
    from agentprov_gui.about import default_checkout
    from agentprov_gui.paths import default_corpus_roots
    from agentprov_gui.ui.mainwindow import MainWindow

    s = _settings(tmp_path)
    s.store.setValue(key, value)
    assert s.checkout == default_checkout() or key != "paths/checkout"
    assert s.corpus_roots == default_corpus_roots() or key != "paths/corpus_roots"
    w = MainWindow(s, cache_dir=tmp_path / "c", home=tmp_path / "home", jobs=False)
    w.close()


def test_control_character_path_is_refused_on_save(tmp_path: Path) -> None:
    s = _settings(tmp_path)
    s.checkout = Path("/tmp/ok")
    s.checkout = Path("/tmp/a" + NUL + "b")
    s.corpus_roots = [Path("/tmp/r" + NUL), Path("/tmp/good")]
    assert s.checkout == Path("/tmp/ok")
    assert s.corpus_roots == [Path("/tmp/good")]
