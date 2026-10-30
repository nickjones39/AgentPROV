"""Settings › Local models (D-828): ``local_models.<endpoint>.<model id>.*`` through ``agentprov settings``.

The pane reads the stored values, keeps every model's edits while the user switches, saves only what changed, lists a
server's models with ``agentprov models`` (a keyed local server's key from the keychain only, D-827) and finds a
model's folder with ``agentprov models --find-folders``. A fake CLI answers; nothing is run.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]  # the checkout: its endpoints.toml names the local endpoints
ALIAS = "DeepSeek-V4.1-Flash-1017-Abliterated-MLX:128k"
STORED = {f"local_models.omlx.{ALIAS}.active_params_b": 13.0,
          f"local_models.omlx.{ALIAS}.model_dir": "/models/deepseek",
          "local_models.lmstudio.qwen3-8b.context_tokens": 40960}


class FakeCli:
    def __init__(self, folders: list[str]) -> None:
        self.calls: list[list[str]] = []
        self.folders = folders

    def __call__(self, argv: Any) -> tuple[int, bytes, bytes]:
        argv = list(argv)
        self.calls.append(argv)
        if argv[:2] == ["settings", "list"]:
            return 0, json.dumps({"values": STORED}).encode(), b""
        if "--find-folders" in argv:
            doc = {"format": "agentprov-model-folders/0.1", "folders": [{"path": p, "source": "omlx"}
                                                                        for p in self.folders]}
            return 0, json.dumps(doc).encode(), b""
        if argv[:1] == ["models"]:
            doc = {"format": "agentprov-local-models/0.1", "endpoints": [{
                "endpoint": "omlx", "base_url": "http://127.0.0.1:8000/v1", "status": "up",
                "server": {"kind_observed": "openai_generic"},
                "models": [{"id": ALIAS, "servable": True}, {"id": "Qwen-Q4", "servable": True}]}]}
            return 0, json.dumps(doc).encode(), b""
        return 1, b"", b"unexpected"


def _settle(qapp: Any) -> None:
    from PySide6.QtCore import QThreadPool

    QThreadPool.globalInstance().waitForDone(30_000)
    qapp.processEvents()


@pytest.fixture
def pane(qapp: Any) -> Any:
    from agentprov_gui.ui.settings_panes import LocalModelsPane

    cli = FakeCli(["/models/qwen-q4"])
    p = LocalModelsPane(REPO, cli=cli)
    _settle(qapp)
    p.endpoint.setCurrentText("omlx")
    yield p
    p.deleteLater()


def test_stored_values_show_and_edits_are_kept_across_models(pane: Any, qapp: Any) -> None:
    assert pane.isEnabled() and "omlx" in [pane.endpoint.itemText(i) for i in range(pane.endpoint.count())]
    pane.model.setEditText(ALIAS)
    assert (pane.active.text(), pane.folder.text()) == ("13", "/models/deepseek")
    pane.active.setText("21.5")
    pane.model.setEditText("Qwen-Q4")
    assert pane.active.text() == "" and pane.folder.text() == ""
    pane.size_gb.setText("111.3")
    pane.context.setText("abc")  # not an integer: left out (reads as unset)
    values = pane.values()
    assert values[f"local_models.omlx.{ALIAS}.active_params_b"] == 21.5
    assert values["local_models.omlx.Qwen-Q4.model_size_gb"] == 111.3
    assert "local_models.omlx.Qwen-Q4.context_tokens" not in values
    assert values["local_models.lmstudio.qwen3-8b.context_tokens"] == 40960  # another endpoint's value is kept


def test_no_field_hides_a_qwidget_method(pane: Any) -> None:
    """D-828 follow-up: the weight-size field was ``self.size``, which hid ``QWidget.size()`` (mypy method-assign)."""
    from PySide6.QtCore import QSize
    from PySide6.QtWidgets import QWidget

    assert isinstance(pane.size(), QSize)
    for attr, _field in pane.FIELDS:
        assert not callable(getattr(QWidget, attr, None)), attr


def test_clear_unsets_one_model(pane: Any) -> None:
    pane.model.setEditText(ALIAS)
    pane.clear_model()
    values = pane.values()
    assert not any(k.startswith(f"local_models.omlx.{ALIAS}.") for k in values)


def test_a_relative_folder_or_a_bad_id_is_never_saved(pane: Any) -> None:
    pane.model.setEditText("Qwen-Q4")
    pane.folder.setText("relative/folder")
    assert "local_models.omlx.Qwen-Q4.model_dir" not in pane.values()
    pane.model.setEditText("bad id with spaces")
    assert not pane.folder.isEnabled() and not pane.find_btn.isEnabled()


def test_find_folder_and_list_models_are_agentprov_models_calls(pane: Any, qapp: Any) -> None:
    pane.model.setEditText("Qwen-Q4")
    pane.find_folder()
    _settle(qapp)
    assert pane.folder.text() == "/models/qwen-q4"
    assert ["models", "--endpoint", "omlx", "--model-id", "Qwen-Q4", "--find-folders", "--format",
            "json"] in pane.cli.calls
    pane.list_models()
    _settle(qapp)
    listed = [c for c in pane.cli.calls if c[:1] == ["models"] and "--find-folders" not in c][-1]
    assert "--keychain" in listed  # oMLX's optional key: the keychain only, never .env (D-827)
    assert {pane.model.itemText(i) for i in range(pane.model.count())} >= {ALIAS, "Qwen-Q4"}
    assert pane.values()["local_models.omlx.Qwen-Q4.model_dir"] == "/models/qwen-q4"
