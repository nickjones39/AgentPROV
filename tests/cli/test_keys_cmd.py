"""D-702: ``agentprov keys`` and ``run --keychain`` (MN N.2.17). No test touches a real keychain: the helper is a stub
that keeps its "keychain" in a temporary JSON file, speaking the real helper's protocol. The real helper's own rules
are in ``tests/cli/test_keys_helper.py``."""

from __future__ import annotations

import io
import json
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, NamedTuple

import pytest

SECRET = "sk-" + "stub-" + "0123456789abcdef"  # built from fragments; never a real key

STUB = r'''
import json, sys
store_path = sys.argv[1]
try:
    store = json.load(open(store_path))
except FileNotFoundError:
    store = {}
req = json.loads(sys.stdin.read())
op = req["op"]
def out(o): sys.stdout.write(json.dumps(o) + "\n")
if op == "status":
    out({"ok": True, "backend": "StubRing", "allowed": True})
elif op == "has":
    out({"ok": True, "present": {n: n in store for n in req["names"]}})
elif op == "set":
    store[req["name"]] = req["value"]; json.dump(store, open(store_path, "w")); out({"ok": True})
elif op == "delete":
    store.pop(req["name"], None); json.dump(store, open(store_path, "w")); out({"ok": True})
elif op == "emit":
    if any(n not in store for n in req["names"]):
        sys.exit(3)
    sys.stdout.write(json.dumps({**req["values"], **{n: store[n] for n in req["names"]}}) + "\n")
'''


class Run(NamedTuple):
    code: int
    out: str
    err: str


@pytest.fixture
def stub(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    from agentprov import keys

    script = tmp_path / "stub_helper.py"
    script.write_text(STUB)
    store = tmp_path / "keychain.json"
    monkeypatch.setattr(keys, "helper_argv", lambda: [sys.executable, "-I", str(script), str(store)])
    monkeypatch.setenv("AGENTPROV_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("AGENTPROV_NO_KEYCHAIN")  # the stub helper stands in for the keychain here
    return store


@pytest.fixture
def cli(capsys: pytest.CaptureFixture[str]) -> Callable[..., Run]:
    from agentprov.cli.main import main

    def run(*argv: str, stdin: bytes | None = None) -> Run:
        capsys.readouterr()
        if stdin is not None:
            sys.stdin = io.TextIOWrapper(io.BytesIO(stdin))
        try:
            code = main(list(argv))
        finally:
            sys.stdin = sys.__stdin__
        out, err = capsys.readouterr()
        return Run(code, out, err)

    return run


def test_status_and_list_show_names_only(stub: Path, cli: Callable[..., Run]) -> None:
    stub.write_text(json.dumps({"OPENROUTER_API_KEY": SECRET}))
    status = cli("keys", "status", "--format", "json", "--progress", "off")
    assert status.code == 0 and json.loads(status.out) == {"allowed": True, "backend": "StubRing"}
    listed = cli("keys", "list", "--format", "json", "--progress", "off")
    rows = {r["name"]: r["stored"] for r in json.loads(listed.out)["keys"]}
    assert rows["OPENROUTER_API_KEY"] is True and rows["OPENAI_API_KEY"] is False
    assert SECRET not in listed.out + listed.err


def test_set_reads_stdin_only_and_never_echoes(stub: Path, cli: Callable[..., Run], tmp_path: Path) -> None:
    summary = tmp_path / "summary.json"
    log = tmp_path / "log.jsonl"
    run = cli("keys", "set", "DEEPSEEK_API_KEY", "--stdin", "--progress", "off", "--summary-json", str(summary),
              "--log-file", str(log), stdin=SECRET.encode() + b"\n")
    assert run.code == 0, run.err
    assert json.loads(stub.read_text()) == {"DEEPSEEK_API_KEY": SECRET}
    for text in (run.out, run.err, summary.read_text(), log.read_text()):
        assert SECRET not in text


@pytest.mark.parametrize(("argv", "code"), [
    (("keys", "set", "HOME_SECRET_TOKEN", "--stdin"), 2),  # not a key variable of endpoints.toml
    (("keys", "set", "DEEPSEEK_API_KEY"), 2),  # not interactive and no --stdin: never from argv
    (("keys", "delete", "DEEPSEEK_API_KEY"), 4),  # not interactive and no --yes
])
def test_refusals(stub: Path, cli: Callable[..., Run], argv: tuple[str, ...], code: int) -> None:
    run = cli(*argv, "--progress", "off", stdin=b"")
    assert run.code == code, run.err


def test_the_zenodo_tokens_are_key_names_too(stub: Path, cli: Callable[..., Run]) -> None:
    """D-880: the draft-only uploader's tokens can be kept in the keychain (``agentprov-zenodo --keychain``)."""
    for name in ("ZENODO_SANDBOX_TOKEN", "ZENODO_TOKEN"):
        assert cli("keys", "set", name, "--stdin", "--progress", "off", stdin=SECRET.encode() + b"\n").code == 0
    listed = cli("keys", "list", "--format", "json", "--progress", "off")
    rows = {r["name"]: r["stored"] for r in json.loads(listed.out)["keys"]}
    assert rows["ZENODO_SANDBOX_TOKEN"] is True and rows["ZENODO_TOKEN"] is True
    assert SECRET not in listed.out + listed.err


def test_delete_with_yes(stub: Path, cli: Callable[..., Run]) -> None:
    stub.write_text(json.dumps({"OPENAI_API_KEY": SECRET}))
    assert cli("keys", "delete", "OPENAI_API_KEY", "--yes", "--progress", "off").code == 0
    assert json.loads(stub.read_text()) == {}


# ---------------------------------------------------------------------------------------------- run --keychain
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "integration"))


@pytest.fixture
def keychain_run(stub: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> list[dict[str, str]]:
    """A real-model run fed by ``--keychain``: the planned gate admits it as if scripted, ``.env`` is never read, and
    the probe records the T2 environment instead of calling."""
    from agentprov.cli import run as run_mod
    from live_fake import make_fake_env, repo_root

    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.chdir(repo_root())
    make_fake_env(home, "ok")
    gate = run_mod._live_capability
    monkeypatch.setattr(run_mod, "_live_capability", lambda source, result, *, scripted: gate(source, result, scripted=True))

    def no_dotenv(*a: Any, **k: Any) -> None:
        raise AssertionError(".env was read although --keychain was given")

    monkeypatch.setattr(run_mod, "_read_env_file", no_dotenv)
    seen: list[dict[str, str]] = []

    def probe(argv: Any, env_for: Any, *a: Any, **k: Any) -> dict[str, Any]:
        seen.append(env_for(Path("/nonexistent-t2home")))
        raise run_mod.LiveRefused("probe reached (test stop)", code="cli.refused.test_stop")

    monkeypatch.setattr(run_mod, "_preflight", probe)
    return seen


RUN = ("run", "agentdojo", "--preflight-only", "--model", "deepseek", "--model-id", "placeholder-model",
       "--containment", "vm", "--keychain", "--i-consent-to-api-costs", "--progress", "off")


@pytest.mark.skipif(os.name == "nt", reason="the fake environment uses a POSIX venv layout")
def test_run_keychain_hands_the_key_to_the_worker_only(keychain_run: list[dict[str, str]], stub: Path,
                                                       cli: Callable[..., Run]) -> None:
    stub.write_text(json.dumps({"DEEPSEEK_API_KEY": SECRET}))
    run = cli(*RUN, "--json")
    assert run.code == 4 and "probe reached" in run.err, run.err
    (env,) = keychain_run
    assert env["DEEPSEEK_API_KEY"] == SECRET
    assert SECRET not in run.out + run.err


@pytest.mark.skipif(os.name == "nt", reason="the fake environment uses a POSIX venv layout")
def test_run_keychain_without_the_key_names_the_variable(keychain_run: list[dict[str, str]], stub: Path,
                                                         cli: Callable[..., Run]) -> None:
    run = cli(*RUN)
    assert run.code == 3 and "DEEPSEEK_API_KEY is not in the keychain" in run.err and not keychain_run


@pytest.mark.parametrize("extra", [("--env-stdin",), ("--env-file", "/x.env")])
def test_run_keychain_is_exclusive(stub: Path, cli: Callable[..., Run], extra: tuple[str, ...]) -> None:
    run = cli(*RUN, *extra, stdin=b"{}")
    assert run.code == 2 and "exclusive" in run.err, run.err


# ---------------------------------------------------------------------------------------------- the default order
@pytest.fixture
def default_run(keychain_run: list[dict[str, str]], monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """The same run without a key source: the keychain (the stub) first, then a stand-in .env (never the real one)."""
    from agentprov.cli import run as run_mod

    dotenv: dict[str, Any] = {"values": {}, "reads": 0}

    def fake_env_file(args: Any, root: Path) -> dict[str, str]:
        dotenv["reads"] += 1
        return dict(dotenv["values"])

    monkeypatch.setattr(run_mod, "_read_env_file", fake_env_file)
    dotenv["seen"] = keychain_run
    return dotenv


DEFAULT = tuple(a for a in RUN if a != "--keychain")


@pytest.mark.skipif(os.name == "nt", reason="the fake environment uses a POSIX venv layout")
def test_the_default_takes_the_key_from_the_keychain_first(default_run: dict[str, Any], stub: Path,
                                                            cli: Callable[..., Run]) -> None:
    stub.write_text(json.dumps({"DEEPSEEK_API_KEY": SECRET}))
    default_run["values"] = {"DEEPSEEK_API_KEY": "dotenv-" + "value-1", "DEEPSEEK_MODEL": "m"}
    run = cli(*DEFAULT, "--json")
    assert run.code == 4 and "probe reached" in run.err, run.err
    (env,) = default_run["seen"]
    assert env["DEEPSEEK_API_KEY"] == SECRET  # the keychain wins over .env
    assert SECRET not in run.out + run.err and "dotenv-value" not in run.out + run.err


@pytest.mark.skipif(os.name == "nt", reason="the fake environment uses a POSIX venv layout")
def test_the_default_falls_back_to_dotenv(default_run: dict[str, Any], stub: Path, cli: Callable[..., Run]) -> None:
    value = "dotenv-" + "value-2"
    default_run["values"] = {"DEEPSEEK_API_KEY": value}
    run = cli(*DEFAULT, "--json")
    (env,) = default_run["seen"]
    assert env["DEEPSEEK_API_KEY"] == value
    assert value not in run.out + run.err


@pytest.mark.skipif(os.name == "nt", reason="the fake environment uses a POSIX venv layout")
def test_the_default_without_either_names_both_places(default_run: dict[str, Any], stub: Path,
                                                      cli: Callable[..., Run]) -> None:
    run = cli(*DEFAULT)
    assert run.code == 3 and "in neither the OS keychain" in run.err and "nor .env" in run.err
    assert not default_run["seen"]


@pytest.mark.skipif(os.name == "nt", reason="the fake environment uses a POSIX venv layout")
def test_an_unavailable_keychain_is_a_notice_and_dotenv_is_used(default_run: dict[str, Any], stub: Path,
                                                                cli: Callable[..., Run],
                                                                monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENTPROV_NO_KEYCHAIN", "1")
    stub.write_text(json.dumps({"DEEPSEEK_API_KEY": SECRET}))  # not reached: the keychain is off
    default_run["values"] = {"DEEPSEEK_API_KEY": "dotenv-" + "value-3"}
    run = cli(*DEFAULT, "--json")
    (env,) = default_run["seen"]
    assert env["DEEPSEEK_API_KEY"] == "dotenv-value-3"
    assert "dotenv-value-3" not in run.out + run.err


@pytest.mark.skipif(os.name == "nt", reason="the fake environment uses a POSIX venv layout")
def test_an_explicit_env_file_is_the_only_source(default_run: dict[str, Any], stub: Path, cli: Callable[..., Run],
                                                 tmp_path: Path) -> None:
    stub.write_text(json.dumps({"DEEPSEEK_API_KEY": SECRET}))
    env_file = tmp_path / "x.env"
    env_file.write_text("")
    run = cli(*DEFAULT, "--env-file", str(env_file))
    assert run.code == 3 and "is not in the given source" in run.err and not default_run["seen"]


@pytest.mark.parametrize(("stored", "dotenv", "source", "notice"), [
    ({"DEEPSEEK_API_KEY": SECRET}, {"DEEPSEEK_API_KEY": "d", "DEEPSEEK_MODEL": "m"}, SECRET, "from the OS keychain"),
    ({}, {"DEEPSEEK_API_KEY": "d"}, "d", "from .env (not in the OS keychain)"),
])
def test_default_key_values_order_and_notices(stub: Path, monkeypatch: pytest.MonkeyPatch, stored: dict[str, str],
                                              dotenv: dict[str, str], source: str, notice: str) -> None:
    import argparse

    from agentprov.cli import run as run_mod
    from agentprov.cli.common import CommandResult

    stub.write_text(json.dumps(stored))
    monkeypatch.setattr(run_mod, "_read_env_file", lambda args, root: dict(dotenv))
    result = CommandResult()
    args = argparse.Namespace(llm_script=None, model="deepseek", endpoint=None, env_file=None)
    values = run_mod._default_key_values(args, Path("/nonexistent-root"), result)
    assert values["DEEPSEEK_API_KEY"] == source and values.get("DEEPSEEK_MODEL") == dotenv.get("DEEPSEEK_MODEL")
    assert any(notice in n for n in result.notices)
    assert not any(SECRET in n or "d" == n for n in result.notices)  # names only, never a value


@pytest.mark.skipif(os.name == "nt", reason="the fake environment uses a POSIX venv layout")
@pytest.mark.parametrize("source", [("--keychain",), ()])
def test_an_uncapped_api_run_reads_no_key(keychain_run: list[dict[str, str]], stub: Path, cli: Callable[..., Run],
                                          monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
                                          source: tuple[str, ...]) -> None:
    """D-721/D-725 before D-702: an API-endpoint run without both caps is refused before any key source is read."""
    from agentprov import keys

    def no_read(*a: Any, **k: Any) -> None:
        raise AssertionError("a key was read for an uncapped API run")

    monkeypatch.setattr(keys, "read", no_read)
    run = cli("run", "agentdojo", "--model", "deepseek", "--model-id", "placeholder-model", "--containment", "vm",
              "--corpus", str(tmp_path / "corpus"), "--campaign", "t", "--suite", "banking",
              "--i-consent-to-api-costs", "--progress", "off", *source)
    assert run.code == 4 and "caps" in run.err and "a key was read" not in run.err, run.err


@pytest.mark.parametrize(("platform", "env", "words"), [
    ("linux", {}, "no D-Bus session"),
    ("linux", {"DBUS_SESSION_BUS_ADDRESS": "unix:path=/x"}, "no Secret Service is answering"),
    ("win32", {}, "Windows Credential Manager"),
    ("darwin", {}, "macOS login keychain"),
    ("sunos5", {}, "no allowed keychain"),
    ("linux", {"AGENTPROV_NO_KEYCHAIN": "1"}, "turned off"),
])
def test_unavailable_reason_names_the_cause_and_the_fallback(platform: str, env: dict[str, str], words: str) -> None:
    """G5 P-1: a host without a keychain is told why (per OS) and where keys come from instead."""
    from agentprov import keys

    reason = keys.unavailable_reason(platform, env)
    assert words in reason and "--env-file" in reason


def test_status_without_a_keychain_gives_the_reason(cli: Callable[..., Run], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENTPROV_NO_KEYCHAIN", "1")
    status = cli("keys", "status", "--format", "json", "--progress", "off")
    doc = json.loads(status.out)
    assert status.code == 4 and doc["allowed"] is False and "turned off" in doc["reason"]
    text = cli("keys", "status", "--progress", "off")
    assert "turned off" in text.out
