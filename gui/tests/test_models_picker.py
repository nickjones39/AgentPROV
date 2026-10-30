"""Run Live's model picker (D-700; D-691, D-692, D-730..D-735): a client of ``agentprov models``.

* every picker call is an ``agentprov models`` argv whose options the CLI parser has, and the GUI's provider and
  public-list constants equal the core's;
* a key is passed only from the keychain (``--keychain``), never by letting the CLI read ``.env``: without a stored key
  only a public list (OpenRouter's) is fetched, and Refresh is otherwise disabled with the reason;
* the lists parse into choices (a remote or unservable local model is not usable; priced-but-unlisted provider models
  are offered), a stale cache says so, and malformed output is "no list";
* in the dialog, the picker fills from the list, Refresh asks for the R2 confirmation and fetches with
  ``--allow-network``, and Identity shows the local model's record.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

from agentprov_gui.jobs.manager import CliLocator, JobManager
from agentprov_gui.live import models as M
from agentprov_gui.live.plan import ENDPOINTS_REL, Endpoint
from test_cli_parity import cli_tree
from test_viewer import wait

FAKE = Path(__file__).parent / "fake" / "fake_cli.py"
OLLAMA = Endpoint("ollama", "http://127.0.0.1:11434/v1", None, None, None, True)
OMLX = Endpoint("omlx", "http://127.0.0.1:8000/v1", "OMLX_API_KEY", None, "OMLX_BASE_URL", True)  # D-827
OPENROUTER = Endpoint("openrouter", "https://openrouter.ai/api/v1", "OPENROUTER_API_KEY", None, None, False)
ANTHROPIC = Endpoint("anthropic", "https://api.anthropic.com", "ANTHROPIC_API_KEY", None, None, False)
CUSTOM = Endpoint("my-proxy", "https://proxy.example/v1", "PROXY_KEY", None, None, False)

LOCAL_DOC = {"format": M.LOCAL_FORMAT, "endpoints": [{
    "endpoint": "ollama", "base_url": OLLAMA.base_url, "status": "up",
    "server": {"kind_observed": "ollama", "version": "0.12.0"},
    "models": [{"id": "qwen3:8b", "params": "8B", "quantization": "Q4_K_M", "size_bytes": 5_200_000_000,
                "loaded": True, "tool_use": True, "remote": False, "servable": True},
               {"id": "cloud-model:latest", "remote": True, "servable": True}]}]}
PROVIDER_DOC = {"format": M.PROVIDER_FORMAT, "endpoint": "anthropic", "host": "api.anthropic.com",
                "fetched_at": "2026-10-20T08:00:00Z", "stale": True, "source": "cache",
                "models": [{"id": "claude-opus-5-5", "display_name": "Claude Opus 5.5", "price_status": "priced"}],
                "not_listed": [{"id": "claude-sonnet-5-5", "listed": False, "price_status": "priced"}]}
IDENTITY = {"format": M.IDENTITY_FORMAT, "model_id": "qwen3:8b", "endpoint": "ollama", "base_url": OLLAMA.base_url,
            "server": {"kind": "ollama", "version": "0.12.0"}, "identity_sha256": "sha256:" + "a" * 64,
            "files": {"method": "ollama_blobs", "label": "qwen3:8b", "weights_hashed": True, "files": [
                {"name": "model.gguf", "size": 5_200_000_000, "sha256": "b" * 64, "sha256_source": "computed"}]}}


@pytest.fixture(scope="module")
def models_options() -> set[str]:
    return set(cli_tree()["models"]["options"])


def _options(argv: list[str]) -> list[str]:
    return [a for a in argv if a.startswith("--")]


@pytest.mark.parametrize(("endpoint", "stored"), [(OLLAMA, False), (OMLX, False), (OMLX, True), (OPENROUTER, False),
                                                  (OPENROUTER, True),
                                                  (ANTHROPIC, True), (ANTHROPIC, False)])
def test_every_picker_call_is_a_models_command_the_cli_has(models_options: set[str], endpoint: Endpoint,
                                                           stored: bool) -> None:
    argvs = [M.list_argv(endpoint, key_stored=stored), M.refresh_argv(endpoint, key_stored=stored)]
    if endpoint.local:
        argvs.append(M.identity_argv(endpoint, "qwen3:8b", allow_lan=True, hash_weights=False))
    for argv in [a for a in argvs if a is not None]:
        assert argv[0] == "models" and set(_options(argv)) <= models_options, argv


def test_keys_come_from_the_keychain_only() -> None:
    assert M.list_argv(ANTHROPIC, key_stored=True)[-2:] == ["--refresh-if-stale", "--keychain"]
    assert "--refresh-if-stale" not in M.list_argv(ANTHROPIC, key_stored=False)  # the cache only: no .env read
    assert M.list_argv(OPENROUTER, key_stored=False)[-1] == "--refresh-if-stale"  # a public list, no key option
    assert M.refresh_argv(ANTHROPIC, key_stored=False) is None
    assert "keychain" in (M.refresh_blocked(ANTHROPIC, key_stored=False) or "")
    assert M.refresh_argv(OPENROUTER, key_stored=False) == ["models", "--endpoint", "openrouter", "--allow-network",
                                                            "--format", "json"]
    assert "--keychain" in M.refresh_argv(ANTHROPIC, key_stored=True)
    assert M.list_argv(CUSTOM, key_stored=True) is None and M.refresh_blocked(OLLAMA, key_stored=False)


def test_a_local_servers_optional_key_comes_from_the_keychain_only() -> None:
    """D-827: oMLX's optional key is read with --keychain (never .env), stored or not; no key option toward a LAN
    address or for a keyless server; a real run never needs it."""
    from agentprov_gui.live.runspec import key_names

    assert "--keychain" in M.list_argv(OMLX, key_stored=False) and "--keychain" in M.identity_argv(OMLX, "m")
    assert "--keychain" not in M.list_argv(OMLX, key_stored=True, allow_lan=True)
    assert "--keychain" not in M.identity_argv(OMLX, "m", allow_lan=True)
    assert "--keychain" not in M.list_argv(OLLAMA, key_stored=False)
    assert M.refresh_argv(OMLX, key_stored=True) is None  # a local server is asked directly
    assert key_names("OMLX_API_KEY", optional=True) == [] and key_names("OPENAI_API_KEY") == ["OPENAI_API_KEY"]


def test_the_gui_constants_equal_the_core() -> None:
    from agentprov.cli.live import providermodels as pm
    from agentprov.cli.models import MODELS_ENDPOINTS

    assert M.PROVIDER_ENDPOINTS == pm.PROVIDER_ENDPOINTS and set(M.PROVIDER_ENDPOINTS) <= set(MODELS_ENDPOINTS)
    public = tuple(e for e in pm.PROVIDER_ENDPOINTS if not pm.key_variable(e)[1])
    assert public == M.PUBLIC_MODEL_LISTS


def test_lists_parse_into_choices() -> None:
    local = M.parse_list(OLLAMA, 0, json.dumps(LOCAL_DOC).encode())
    assert local.state == "up" and local.usable_ids == ["qwen3:8b"] and "1 usable" in local.detail
    assert "loaded" in local.choices[0].note and "remote" in local.choices[1].note
    down = {"format": M.LOCAL_FORMAT, "endpoints": [{"endpoint": "ollama", "base_url": "x", "status": "down",
                                                     "reason": "connection_refused", "models": []}]}
    assert M.parse_list(OLLAMA, 0, json.dumps(down).encode()).detail.endswith("down (connection_refused)")
    provider = M.parse_list(ANTHROPIC, 0, json.dumps(PROVIDER_DOC).encode())
    assert provider.state == "stale" and provider.usable_ids == ["claude-opus-5-5", "claude-sonnet-5-5"]
    assert "over 24 h old" in provider.detail and "not in the provider's list" in provider.choices[1].note
    for out in (b"", b"not json", b"[1]", json.dumps({"format": "other"}).encode()):
        assert M.parse_list(ANTHROPIC, 0, out).choices == ()
    assert M.parse_list(OLLAMA, 3, b"", b"agentprov: error [x]: unreachable").state == "down"


def test_identity_records_parse_and_summarise() -> None:
    record = M.parse_identity(0, json.dumps(IDENTITY).encode())
    assert record is not None and any("weights hashed" in line for line in M.identity_lines(record))
    assert M.parse_identity(0, json.dumps({"format": "x"}).encode()) is None and M.parse_identity(3, b"{}") is None


def _repo(root: Path) -> Path:
    path = root / ENDPOINTS_REL
    path.parent.mkdir(parents=True)
    path.write_text('[endpoints.ollama]\nbase_url = "http://127.0.0.1:11434/v1"\nlocal = true\n\n'
                    '[endpoints.anthropic]\nbase_url = "https://api.anthropic.com"\napi_key_env = "ANTHROPIC_API_KEY"\n'
                    'api = "anthropic_messages"\nlocal = false\n', encoding="utf-8")
    return root


def _fake(calls: list[list[str]]) -> Any:
    def run(_manager: Any, argv: list[str], *, stdin_fd: int | None = None, timeout: float = 0) -> tuple[int, bytes, bytes]:
        calls.append(list(argv))
        if argv[0] == "models" and "--model-id" in argv:
            return 0, json.dumps(IDENTITY).encode(), b""
        if argv[0] == "models" and argv[2] == "ollama":
            return 0, json.dumps(LOCAL_DOC).encode(), b""
        if argv[0] == "models" and argv[2] == "anthropic":
            doc = dict(PROVIDER_DOC, stale="--allow-network" not in argv, source="network" if "--allow-network" in argv
                       else "cache")
            return 0, json.dumps(doc).encode(), b""
        return 127, b"", b"no CLI"
    return run


@pytest.fixture
def dialog(qapp: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    from agentprov_gui.live import keychain
    from agentprov_gui.live.runspec import RunSettings
    from agentprov_gui.ui.runlive import RunLiveDialog

    monkeypatch.setattr(keychain, "status", lambda cli: keychain.KeychainStatus(True, "FakeRing"))
    monkeypatch.setattr(keychain, "present", lambda cli, names: dict.fromkeys(names, True))
    calls: list[list[str]] = []
    manager = JobManager(tmp_path / "home", CliLocator(None, (sys.executable, str(FAKE))))
    preset = RunSettings(campaign="t", scripted=False, model="ollama", suites=("banking",), containment="vm")
    dlg = RunLiveDialog(manager, home=tmp_path / "home", checkout=_repo(tmp_path / "repo"), preset=preset,
                        run=_fake(calls))
    dlg.calls = calls
    yield dlg
    from PySide6.QtCore import QThreadPool

    QThreadPool.globalInstance().waitForDone(30_000)
    qapp.processEvents()
    dlg.close()


def test_the_picker_fills_from_agentprov_models_and_shows_identity(qapp: Any, dialog: Any) -> None:
    wait(qapp, lambda: "ollama" in dialog.model_lists)
    items = [dialog.model_id.itemText(i) for i in range(dialog.model_id.count())]
    assert items == ["qwen3:8b"]  # the remote model is not offered
    assert "usable here" in dialog.models_status.text()
    assert dialog.identity_btn.isVisibleTo(dialog) and not dialog.refresh_models_btn.isVisibleTo(dialog)
    dialog.model_id.setCurrentText("qwen3:8b")
    dialog._show_identity()
    wait(qapp, lambda: dialog.identity_dialog is not None)
    assert ["models", "--endpoint", "ollama", "--model-id", "qwen3:8b", "--format", "json"] in dialog.calls
    texts = [w.toPlainText() for w in dialog.identity_dialog.findChildren(type(dialog.details))]
    assert any('"identity_sha256"' in t for t in texts)
    dialog.identity_dialog.close()


def test_refresh_is_confirmed_and_fetches_with_the_keychain(qapp: Any, dialog: Any,
                                                            monkeypatch: pytest.MonkeyPatch) -> None:
    from PySide6.QtWidgets import QMessageBox

    dialog.endpoint.setCurrentText("anthropic")
    wait(qapp, lambda: "anthropic" in dialog.model_lists and dialog.keys_present)
    assert [dialog.model_id.itemText(i)
                                                        for i in range(dialog.model_id.count())] == ["claude-opus-5-5", "claude-sonnet-5-5"]
    assert dialog.refresh_models_btn.isEnabled() and "over 24 h old" in dialog.models_status.text()
    answers = [QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Ok]
    monkeypatch.setattr(QMessageBox, "exec", lambda self: answers.pop(0))
    before = len(dialog.calls)
    dialog._refresh_models()  # cancelled: nothing runs
    assert len(dialog.calls) == before
    dialog._refresh_models()
    wait(qapp, lambda: any("--allow-network" in c for c in dialog.calls))
    fetched = next(c for c in dialog.calls if "--allow-network" in c)
    assert fetched == ["models", "--endpoint", "anthropic", "--allow-network", "--keychain", "--format", "json"]
    wait(qapp, lambda: "network" in dialog.models_status.text())
