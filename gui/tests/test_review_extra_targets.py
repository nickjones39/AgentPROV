"""GR-47: "Additional options" cannot repeat an option the form exposes as a field. Otherwise ``--out X`` or ``--corpus X``
typed there redirects the corpus the CLI writes or reads, while the single-writer and lock checks, the job label and
Open in Viewer keep naming the form's value."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from agentprov_gui.jobs.commands import FORMS, FormError, build_spec, form_options
from agentprov_gui.jobs.manager import CliLocator, JobManager, SpawnRefused

_DD = "-" + "-"
_BUSY = "/c/" + "bu" + "sy"

_CASES = [
    ("derive", {"corpus": "/c/src", "out": "/c/free"}, "out"),
    ("derive", {"corpus": "/c/src", "out": "/c/free"}, "trig"),
    ("derive", {"corpus": "/c/src", "out": "/c/free"}, "corpus"),
    ("recompute", {"corpus": "/c/src", "dry_run": False, "out": "/c/free"}, "out"),
    ("recompute", {"corpus": "/c/src", "dry_run": False}, "out"),
    ("recompute", {"corpus": "/c/src"}, "corpus"),
    ("import", {"source": "s", "corpus": "/c/free"}, "corpus"),
    ("package_seal", {"corpus": "/c/free", "corpus_version": "1.0.0"}, "corpus"),
    ("package_deposit", {"deposit": "/c/d", "corpus": "/c/sealed", "metadata": "/c/r.toml"}, "deposit"),
    ("package_index", {"index": "/c/i", "part": "/c/p.json", "corpus": "/c/sealed", "metadata": "/c/r.toml",
                       "release_date": "2026-10-29"}, "index"),
    ("purge", {"object": "sha256:" + "a" * 64, "reason": "secret", "corpus": "/c/free"}, "corpus"),
    ("render", {"corpus": "/c/src", "out": "/c/r"}, "out"),
    ("validate", {"corpus": "/c/src"}, "report"),
]


@pytest.mark.parametrize("sep", [" ", "="])
@pytest.mark.parametrize(("form", "values", "option"), _CASES)
def test_target_options_are_refused_in_additional_options(form: str, values: dict[str, object], option: str,
                                                          sep: str) -> None:
    with pytest.raises(FormError, match="field"):
        build_spec(FORMS[form], values, extra=_DD + option + sep + _BUSY)


_VALID: dict[str, dict[str, object]] = {
    "info": {}, "validate": {"corpus": "/c"}, "verify": {"corpus": "/c"}, "render": {"corpus": "/c"},
    "derive": {"corpus": "/c", "out": "/n"}, "recompute": {"corpus": "/c"}, "import": {"source": "s", "corpus": "/c"},
    "fetch": {}, "stats": {"corpus": "/c"}, "package_seal": {"corpus": "/c", "corpus_version": "1.0.0"},
    "package_deposit": {"deposit": "/d", "corpus": "/c", "metadata": "/r.toml"},
    "package_index": {"index": "/i", "part": "/p.json", "corpus": "/c", "metadata": "/r.toml", "release_date": "2026-10-29"},
    "purge": {"object": "sha256:" + "a" * 64, "reason": "secret", "corpus": "/c"},
    "backends_build": {"backend": "agentdojo"}, "inspect": {"target": "ex_a"}, "models": {},
    **{name: ({"gate_name": "A"} if name == "migrate_gate" else {}) for name in FORMS if name.startswith("migrate_")},
    "run": {"source": "agentdojo", "corpus": "/c", "campaign": "t", "suite": "banking", "llm_script": "/s.json"},
    "settings_list": {}, "settings_get": {"key": "devrun.keep"}, "settings_set": {"key": "devrun.keep", "value": "5"},
    "settings_unset": {"key": "devrun.keep"}, "keys_status": {}, "keys_list": {}, "keys_set": {"name": "OPENAI_API_KEY"},
    "keys_delete": {"name": "OPENAI_API_KEY"},
    "prices_refresh": {}, "prices_list": {}, "prices_get": {"endpoint": "openai", "model": "gpt-x"},
    "prices_set": {"endpoint": "openai", "model": "gpt-x", "input": "1", "output": "2"},
    "prices_unset": {"endpoint": "openai", "model": "gpt-x"},
    "estimate": {"source": "agentdojo", "suite": "banking", "llm_script": "/s.json"},
    "jobs_start": {"argv": ["info"]}, "jobs_list": {}, "jobs_show": {"job_id": "01a1"}, "jobs_follow": {"job_id": "01a1"},
    "jobs_stop": {"job_id": "01a1"}, "jobs_kill": {"job_id": "01a1"}, "jobs_drain": {"job_id": "01a1"},
    "jobs_resume": {"job_id": "01a1"}, "jobs_prune": {},
    "batch_create": {"stdin": True}, "batch_start": {"batch_id": "01a1"}, "batch_resume": {"batch_id": "01a1"},
    "batch_run": {"batch_id": "01a1"}, "batch_stop": {"batch_id": "01a1"}, "batch_list": {},
    "batch_show": {"batch_id": "01a1"},
    "devrun_plan": {}, "devrun_start": {}, "devrun_list": {}, "devrun_prune": {},
}


@pytest.mark.parametrize("form", [n for n, f in FORMS.items() if f.tool is None])
def test_every_field_option_is_refused_in_additional_options(form: str) -> None:
    """The field is the only route to an option the form exposes (bool flags too: ``--dry-run`` clears the writes)."""
    build_spec(FORMS[form], _VALID[form])
    for option in form_options(FORMS[form]):
        for extra in (option, option + "=/x", option + " /x"):
            with pytest.raises(FormError, match="field"):
                build_spec(FORMS[form], _VALID[form], extra=extra)


def test_other_options_still_pass() -> None:
    s = build_spec(FORMS["import"], {"source": "s", "corpus": "/c/free"}, extra=_DD + "progress-interval=3")
    assert _DD + "progress-interval=3" in s.argv and s.writes == ("/c/free",)  # a global, not an import field
    tool = build_spec(FORMS["ci_local"], {}, extra=_DD + "only core")  # GR-45: a tool form takes only its own options
    assert tool.argv[-2:] == (_DD + "only", "core")


def test_a_locked_tree_cannot_be_reached_through_additional_options(tmp_path: Path) -> None:
    busy, free = tmp_path / "c" / "busy", tmp_path / "c" / "free"
    partial = busy.with_name("busy.partial")
    partial.mkdir(parents=True)
    (partial / ".agentprov.lock").write_text('{"pid": 1, "host": "x", "started": "2026-01-01T00:00:00Z"}')
    fake = Path(__file__).parent / "fake" / "fake_cli.py"
    m = JobManager(tmp_path / "home", CliLocator(None, (sys.executable, str(fake))))
    with pytest.raises(SpawnRefused) as refused:  # D-704: the rule is `agentprov jobs start`'s
        m.spawn(build_spec(FORMS["derive"], {"corpus": str(tmp_path / "src"), "out": str(busy)}))
    assert refused.value.code == "jobs.writer.locked"
    with pytest.raises(FormError):
        build_spec(FORMS["derive"], {"corpus": str(tmp_path / "src"), "out": str(free)}, extra=f"{_DD}out {busy}")
