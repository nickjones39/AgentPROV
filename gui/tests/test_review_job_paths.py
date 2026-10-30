"""GR-20: a job's path values are absolute (``~`` expanded), so the CLI child (whose cwd is its job directory), the
single-writer and lock checks and Open in Viewer all name the same tree."""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

from agentprov_gui.jobs.commands import FORMS, FormError, build_spec
from agentprov_gui.jobs.manager import CliLocator, JobManager, SpawnRefused

FAKE = Path(__file__).parent / "fake" / "fake_cli.py"
_TILDE = "~" + "/"
_DD = "-" + "-"


def _after(argv: tuple[str, ...], option: str) -> str:
    return argv[argv.index(option) + 1]


def test_tilde_is_expanded_in_argv_writes_and_reads(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "h"
    monkeypatch.setenv("HOME", str(home))
    spec = build_spec(FORMS["derive"], {"corpus": _TILDE + "src", "out": _TILDE + "x"})
    assert _after(spec.argv, "--out") == str(home / "x")
    assert _after(spec.argv, "--corpus") == str(home / "src")
    assert spec.writes == (str(home / "x"),)
    assert spec.reads == (str(home / "src"),)
    assert not any(t.startswith("~") for t in spec.argv)
    deposit = build_spec(FORMS["package_deposit"], {"deposit": _TILDE + "d", "corpus": _TILDE + "a " + _TILDE + "b",
                                                    "metadata": _TILDE + "release.toml"})
    assert deposit.writes == (str(home / "d"),)
    assert str(home / "a") in deposit.argv and str(home / "b") in deposit.argv


@pytest.mark.parametrize(("form", "values"), [
    ("derive", {"corpus": "/c", "out": "corpora" + "/new"}),
    ("derive", {"corpus": "corpora" + "/old", "out": "/n"}),
    ("import", {"source": "demo", "corpus": "x"}),
    ("validate", {"corpus": "/c", "report": "r.json"}),
    ("package_deposit", {"deposit": "/d", "corpus": "/a rel", "metadata": "/m.toml"}),
])
def test_relative_form_paths_are_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, form: str,
                                         values: dict[str, str]) -> None:
    monkeypatch.chdir(tmp_path)
    with pytest.raises(FormError, match="absolute path"):
        build_spec(FORMS[form], values)


@pytest.mark.parametrize("extra", [
    _DD + "out rel/dir", _DD + "out=rel/dir", _DD + "report r.json", _DD + "trig=t", _DD + "cache-dir c",
    _DD + "out " + _TILDE + "x",
])
def test_relative_paths_in_additional_options_are_refused(extra: str) -> None:
    with pytest.raises(FormError, match="absolute path"):
        build_spec(FORMS["derive"], {"corpus": "/c", "out": "/n"}, extra=extra)


def test_absolute_paths_in_additional_options_pass() -> None:
    # D-654 made every import option a field; an option outside the table (a fake CLI's) still passes absolute values
    s = build_spec(FORMS["import"], {"source": "s", "corpus": "/c"}, extra=_DD + "x-spec=/s.toml " + _DD + "units 1")
    assert _DD + "x-spec=/s.toml" in s.argv


def test_the_lock_lands_on_the_tree_the_gui_checks(tmp_path: Path) -> None:
    corpus = tmp_path / "corpora" / "x"
    m = JobManager(tmp_path / "home", CliLocator(None, (sys.executable, str(FAKE))))
    spec = build_spec(FORMS["import"], {"source": "demo", "corpus": str(corpus)},
                      extra=f"{_DD}lock {corpus} {_DD}sleep 5")
    job = m.spawn(spec)
    try:
        end = time.monotonic() + 20
        lock = corpus.with_name("x.partial") / ".agentprov.lock"
        while not lock.exists() and time.monotonic() < end:
            time.sleep(0.05)
        assert lock.exists()
        assert not any(p.name == ".agentprov.lock" for p in job.directory.rglob("*"))
        with pytest.raises(SpawnRefused):
            m.spawn(build_spec(FORMS["import"], {"source": "demo", "corpus": str(corpus)}))
    finally:
        m.kill(job)


@pytest.mark.parametrize(("form", "values", "extra"), [  # GR-68: path options outside the form table
    ("validate", {"corpus": "/c"}, _DD + "x-aer rel" + "/x.aer.jsonl"),
    ("validate", {"corpus": "/c"}, _DD + "x-store ." + "/store"),
    ("validate", {"corpus": "/c"}, _DD + "x-aer=" + _TILDE + "x"),
    ("validate", {"corpus": "/c"}, _DD + "x-store .." + "/s"),
    ("validate", {"corpus": "/c"}, _DD + "x-card " + _TILDE + "card.md"),
])
def test_relative_values_of_other_options_are_refused(form: str, values: dict[str, str], extra: str) -> None:
    with pytest.raises(FormError, match="absolute path"):
        build_spec(FORMS[form], values, extra=extra)


@pytest.mark.parametrize("values", [  # D-654: --aer, --store and --card are fields now; a relative value is refused
    {"aer": "rel" + "/x.aer.jsonl"}, {"aer": "/a.jsonl docs" + "/x.jsonl"}, {"corpus": "/c", "store": "." + "/store"},
    {"corpus": "/c", "card": "card.md"},
])
def test_relative_values_of_path_fields_are_refused(values: dict[str, str]) -> None:
    with pytest.raises(FormError, match="absolute path"):
        build_spec(FORMS["validate"], values)


def test_path_fields_route_options_through_the_form() -> None:
    s = build_spec(FORMS["validate"], {"aer": "/a.jsonl /b.jsonl", "store": "/s", "card": "/c.md"})
    assert s.argv.count(_DD + "aer") == 2 and _after(s.argv, _DD + "store") == "/s"
    with pytest.raises(FormError, match="field"):
        build_spec(FORMS["validate"], {"corpus": "/c"}, extra=_DD + "aer /a.jsonl")


@pytest.mark.parametrize("value", ["rel" + "/LICENSE", "MIT=rel" + "/LICENSE", "MIT=LICENSE"])
def test_relative_licence_file_field_is_refused(value: str) -> None:
    with pytest.raises(FormError, match="absolute path"):
        build_spec(FORMS["package_seal"], {"corpus": "/c", "corpus_version": "1.0.0", "licence_file": value})


def test_licence_file_field_expands_tilde(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    values = {"corpus": "/c", "corpus_version": "1.0.0", "licence_file": "MIT=" + _TILDE + "L"}
    assert _after(build_spec(FORMS["package_seal"], values).argv, "--licence-file") == f"MIT={tmp_path / 'L'}"
    values["licence_file"] = "MIT=/L"
    assert _after(build_spec(FORMS["package_seal"], values).argv, "--licence-file") == "MIT=/L"


@pytest.mark.parametrize(("form", "values", "extra"), [  # plain words, KEY=VALUE selects and absolute paths still pass
    ("validate", {"corpus": "/c"}, _DD + "x-aer /a.jsonl " + _DD + "x-store=/s " + _DD + "x-card /c.md"),
    ("validate", {"corpus": "/c"}, _DD + "x-flag " + _DD + "x-card card.md"),
    ("import", {"source": "s", "corpus": "/c"}, _DD + "units 1 " + _DD + "fetch-ref main"),
    ("stats", {"corpus": "/c", "select": "model=openai" + "/gpt-4o,x"}, ""),
])
def test_words_and_absolute_values_still_pass(form: str, values: dict[str, str], extra: str) -> None:
    build_spec(FORMS[form], values, extra=extra)
