"""D-703: ``agentprov settings`` and :mod:`agentprov.settings` (the store the CLI and the GUI share; MN N.2.17)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentprov import settings as S
from agentprov.cli.main import main


def test_the_schema_is_closed_and_typed(tmp_path: Path) -> None:
    with pytest.raises(S.SettingsError, match="unknown setting"):
        S.set("anything.goes", "x", home=tmp_path)
    assert S.set("devrun.samples", "7", home=tmp_path) == 7
    assert S.set("devrun.prov_conformance", "false", home=tmp_path) is False
    assert S.set("devrun.include", "agentdojo, autodojo/live", home=tmp_path) == ["agentdojo", "autodojo/live"]
    assert S.set("devrun.live.cost_cap", "2.5", home=tmp_path) == 2.5
    for key, bad in (("devrun.samples", "-1"), ("devrun.samples", "1e9"), ("devrun.sample_mode", "all"),
                     ("devrun.live.cost_cap", "nan"), ("devrun.prov_conformance", "maybe"),
                     ("devrun.include", "a;b"), ("compute.preset", "x\ny")):
        with pytest.raises(S.SettingsError):
            S.set(key, bad, home=tmp_path)
    assert S.items("devrun.", home=tmp_path) == {"devrun.include": ["agentdojo", "autodojo/live"],
                                                 "devrun.live.cost_cap": 2.5, "devrun.prov_conformance": False,
                                                 "devrun.samples": 7}


@pytest.mark.parametrize(("url", "ok"), [
    ("http://127.0.0.1:1235/v1", True), ("http://localhost:8000/v1", True), ("http://[::1]:8000/v1", True),
    ("http://192.168.1.20:1234/v1", True), ("https://10.0.0.5/v1", True), ("http://100.64.1.1/v1", True),
    ("http://example.com/v1", False), ("http://8.8.8.8/v1", False), ("http://user:pw@127.0.0.1/v1", False),
    ("http://127.0.0.1/v1?x=1", False), ("http://127.0.0.1/v1#f", False), ("ftp://127.0.0.1/", False),
    ("127.0.0.1:1234", False),
])
def test_local_base_urls_are_loopback_or_lan_literals(tmp_path: Path, url: str, ok: bool) -> None:
    assert (S.local_base_url(url) is None) is ok
    if ok:
        assert S.set("endpoints.lmstudio.base_url", url, home=tmp_path) == url
    else:
        with pytest.raises(S.SettingsError):
            S.set("endpoints.lmstudio.base_url", url, home=tmp_path)


def test_a_stored_value_that_no_longer_validates_reads_as_unset(tmp_path: Path) -> None:
    S.set("jobs.retention", 200, home=tmp_path)
    doc = json.loads((tmp_path / "settings.json").read_text())
    doc["values"]["jobs.retention"] = 5  # below the schema's minimum
    doc["values"]["no.such.key"] = 1
    (tmp_path / "settings.json").write_text(json.dumps(doc))
    assert S.get("jobs.retention", home=tmp_path) is None and S.items(home=tmp_path) == {}
    assert len(S.problems(home=tmp_path)) == 2


def test_a_malformed_file_is_refused_not_repaired(tmp_path: Path) -> None:
    (tmp_path / "settings.json").write_text('{"format": "agentprov-settings/0.1", "values": {}, "values": {}}')
    with pytest.raises(S.SettingsError, match="strict JSON"):
        S.items(home=tmp_path)


def test_the_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("AGENTPROV_HOME", str(tmp_path))

    def run(*argv: str) -> tuple[int, str]:
        capsys.readouterr()
        code = main(["settings", *argv, "--progress", "off"])
        return code, capsys.readouterr().out

    assert run("set", "devrun.live.call_cap", "5")[0] == 0
    assert run("get", "devrun.live.call_cap") == (0, "5\n")
    assert run("get", "devrun.keep", "--format", "json") == (0, "null\n")
    code, out = run("list", "--format", "json")
    assert code == 0 and json.loads(out) == {"format": "agentprov-settings/0.1", "values": {"devrun.live.call_cap": 5}}
    assert run("set", "endpoints.x.base_url", "http://example.com/v1")[0] == 2
    assert run("set", "nope", "1")[0] == 2
    code, out = run("list", "--schema", "--format", "json")
    assert code == 0 and json.loads(out)["format"] == "agentprov-settings-schema/0.1"
    assert run("unset", "devrun.live.call_cap")[0] == 0 and run("list", "--format", "json")[1].count("call_cap") == 0
    assert oct((tmp_path / "settings.json").stat().st_mode & 0o777) == "0o600"


def test_the_zenodo_keys_prefill_only_and_validate(tmp_path: Path) -> None:
    """D-880: the GUI's Zenodo pane. No token key exists: the tokens live in the OS keychain (``agentprov keys``)."""
    assert S.set("zenodo.target_preselect", "sandbox", home=tmp_path) == "sandbox"
    assert S.set("zenodo.communities", "agentprov, ai-safety_2", home=tmp_path) == ["agentprov", "ai-safety_2"]
    assert S.set("zenodo.concept_doi", "10.5281/zenodo.99999990", home=tmp_path) == "10.5281/zenodo.99999990"
    assert S.set("zenodo.creators.0.name", "Doe, Jane", home=tmp_path) == "Doe, Jane"
    assert S.set("zenodo.creators.0.orcid", "0000-0002-1694-233X", home=tmp_path) == "0000-0002-1694-233X"
    assert S.set("zenodo.creators.1.affiliation", "Lab", home=tmp_path) == "Lab"
    for key, bad in (("zenodo.target_preselect", "staging"), ("zenodo.communities", "Upper"),
                     ("zenodo.communities", "ok,-lead"), ("zenodo.concept_doi", "not-a-doi"),
                     ("zenodo.concept_doi", "10.5281/zenodo.20692312"),  # the AgentDojo-PROV concept (D-5)
                     ("zenodo.creators.0.orcid", "0000-0002-1694-233"), ("zenodo.creators.100.name", "x"),
                     ("zenodo.token", "x"), ("zenodo.creators.0.email", "x")):
        with pytest.raises(S.SettingsError):
            S.set(key, bad, home=tmp_path)
    assert not any("zenodo" in k.pattern and "token" in k.pattern for k in S.SCHEMA)
