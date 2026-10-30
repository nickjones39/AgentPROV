"""CLI contract (MN N.6 item 1; K.15 item 1): the registered commands, global options, parser settings, ``--version``;
and the public Python API ``agentprov.api`` (MN M.6, ``test_public_api``)."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import pytest

_STATS_TESTS = Path(__file__).resolve().parents[1] / "unit" / "stats"
if str(_STATS_TESTS) not in sys.path:
    sys.path.insert(0, str(_STATS_TESTS))

import stats_support as ss  # noqa: E402

from agentprov import api  # noqa: E402
from agentprov.cli.main import COMMANDS, build_parser, main  # noqa: E402
from agentprov.testing import fs_guard  # noqa: E402

#: The fifteen commands of MN N.2 (phase 11 as built).
N2_COMMANDS = {
    "run", "import", "fetch", "derive", "recompute", "validate", "verify", "inspect", "info",
    "backends", "package", "stats", "render", "migrate", "purge",
}  # fmt: skip
N2_ALIASES = {"convert": "import", "sources": "info"}
#: Application commands added after N.2's fifteen by later decisions (MN N.2.17; reverse CLI parity D-700).
APP_COMMANDS = {"settings", "models", "keys", "prices", "estimate", "jobs", "batch", "devrun"}  # D-703; D-691; D-702; D-701; D-704

#: Every option of the N.1.2 table.
GLOBAL_OPTIONS = {
    "--version", "-v", "--verbose", "-q", "--quiet", "--log-format", "--log-file", "--log-content", "--progress",
    "--progress-format", "--progress-file", "--show-content", "--content-chars", "--json", "--summary-json",
    "--max-listed", "--no-colour", "--no-color", "--break-stale-lock",
}  # fmt: skip


def _subparsers(parser: argparse.ArgumentParser) -> dict[str, argparse.ArgumentParser]:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return dict(action.choices)
    raise AssertionError("no subparsers")


def _option_strings(parser: argparse.ArgumentParser) -> set[str]:
    return {o for action in parser._actions for o in action.option_strings}


def _walk(parser: argparse.ArgumentParser):
    """The root parser and every subcommand parser."""
    yield parser
    yield from _subparsers(parser).values()


def _primary_commands() -> set[str]:
    return {name for name in _subparsers(build_parser()) if name not in N2_ALIASES}


# U4 adds `verify`. When it lands, delete this decorator: the test then pins the exact set of the fifteen N.2 commands.
def test_the_registered_commands_are_exactly_the_fifteen_of_n2():
    assert _primary_commands() == N2_COMMANDS | APP_COMMANDS
    assert set(COMMANDS) == N2_COMMANDS | APP_COMMANDS
    assert len(N2_COMMANDS) == 15 and not N2_COMMANDS & APP_COMMANDS


def test_the_registered_commands_match_the_declared_set_and_aliases():
    subs = _subparsers(build_parser())
    primary = _primary_commands()
    assert primary == set(COMMANDS)
    assert primary <= N2_COMMANDS | APP_COMMANDS
    assert N2_COMMANDS - {"verify"} <= primary  # all of N.2 except the command U4 adds
    assert "diff" not in subs  # deferred (AD-10)
    for alias, target in N2_ALIASES.items():
        assert alias in subs and subs[alias] is subs[target]


def test_no_deferred_flag_exists_anywhere():
    for parser in _walk(build_parser()):
        strings = _option_strings(parser)
        assert "--allow-unpatched-interpreter" not in strings
        assert "--outcome-replay" not in strings
        if parser.prog.endswith(" info"):
            assert "--card" not in strings  # `info --card` is deferred (AD-10)


def test_allow_abbrev_is_off_everywhere():
    for parser in _walk(build_parser()):
        assert parser.allow_abbrev is False


def test_global_options_exist_on_the_root_and_every_command():
    root = build_parser()
    assert GLOBAL_OPTIONS <= _option_strings(root)
    for name, sub in _subparsers(root).items():
        assert GLOBAL_OPTIONS <= _option_strings(sub), name


@pytest.mark.parametrize("command", [None, *COMMANDS])
def test_every_help_exits_zero(cli, command):
    run = cli(*([command] if command else []), "--help")
    assert run.code == 0
    assert "usage:" in run.out
    assert run.err == ""


def test_abbreviations_are_usage_errors(cli):
    run = cli("run", "agentdojo", "--dry")
    assert run.code == 2
    run = cli("import", "x", "--corp", "c")
    assert run.code == 2


def test_no_command_is_a_usage_error(cli):
    run = cli()
    assert run.code == 2
    assert "a command is required" in run.err


def test_unknown_command_suggests_and_exits_2(cli):
    run = cli("inf")
    assert run.code == 2
    assert "invalid choice" in run.err


def test_global_options_before_and_after_the_command_are_equivalent(cli, host_probe):
    before = cli("-v", "--json", "info")
    after = cli("info", "-v", "--json")
    assert before.code == after.code == 0
    assert before.out == after.out
    assert before.json()["command"] == "info"


def test_global_option_defaults(cli, host_probe):
    from agentprov.cli.common import GLOBAL_DEFAULTS, add_global_options, apply_global_defaults

    ns = argparse.Namespace()
    apply_global_defaults(ns)
    assert ns.max_listed == 100 and ns.verbose == 0 and ns.quiet is False
    assert ns.log_format == "text" and ns.content_chars is None and ns.progress is None
    assert set(GLOBAL_DEFAULTS) >= {"json", "summary_json", "show_content", "no_colour", "break_stale_lock"}
    assert callable(add_global_options)


def test_verbose_and_quiet_conflict(cli, host_probe):
    run = cli("info", "-v", "-q")
    assert run.code == 2


@pytest.mark.parametrize("value", ["0", "2001", "x", "-5"])
def test_content_chars_out_of_range_is_a_usage_error(cli, value):
    assert cli("info", "--content-chars", value).code == 2


def test_content_chars_maximum_is_accepted(cli, host_probe):
    assert cli("info", "--content-chars", "2000").code == 0


def test_no_color_alias(cli, host_probe):
    assert cli("info", "--no-color").code == 0
    assert cli("info", "--no-colour").code == 0


def test_version_text(cli):
    run = cli("--version")
    assert run.code == 0
    lines = run.out.splitlines()
    assert lines[0] == "agentprov 0.1.0"
    for token in ("aer/0.2", "sem/0.1", "capture/0.1", "agentprov-prov/0.1", "apv 0.2.0", "agentprov-corpus/0.2"):
        assert token in lines[1]
    assert lines[2].startswith("python ") and "interpreter_advisory:" in lines[2]
    assert run.err == ""


def test_version_after_a_subcommand(cli):
    assert cli("info", "--version").out.startswith("agentprov 0.1.0")


def test_version_reports_the_interpreter_advisory(cli, monkeypatch):
    monkeypatch.setattr("agentprov.envinfo._running_version", lambda: (3, 14, 7))
    line = cli("--version").out.splitlines()[2]
    assert "interpreter_advisory: below 3.14.8" in line and "CVE-2026-15310" in line


def test_python_dash_m_agentprov_matches_the_console_entry():
    done = subprocess.run([sys.executable, "-m", "agentprov", "--version"], capture_output=True, text=True, timeout=60)
    assert done.returncode == 0
    assert done.stdout.startswith("agentprov 0.1.0\nformats: aer/0.2")
    assert done.stderr == ""


def test_main_returns_an_int_and_never_exits(cli):
    assert isinstance(main(["--version"]), int)
    assert isinstance(main(["nonsense"]), int)


RUN_OPTIONS = {
    "--corpus", "--campaign", "--corpus-id", "--plan", "--spec", "--suite", "--benchmark-version", "--user-tasks",
    "--attack", "--injection-tasks", "--benign", "--defence", "--defense", "--model", "--endpoint", "--model-id",
    "--llm-script", "--llm-element", "--model-display-name", "--temperature", "--reasoning-effort", "--repeats",
    "--max-attempts", "--retry-inconsistent", "--allow-mixed-config", "--env-file", "--allow-custom-endpoint",
    "--i-consent-to-api-costs", "--containment", "--limit", "--jobs", "--start-stagger", "--dry-run",
    "--autodojo-cache", "--autodojo-variant", "--preflight-only", "--canary", "--temperature-policy",
    "--allow-text-tool-calls", "--preset", "--m5ultra", "--model-dir", "--model-size-gb", "--active-params-b",
    "--context-tokens", "--kv-gb-per-trace", "--server-max-concurrency",
}  # fmt: skip
IMPORT_OPTIONS = {
    "--corpus", "--input", "--fetch", "--allow-network", "--profile", "--pin", "--snapshot", "--spec", "--corpus-id",
    "--verify-against-pin", "--suite", "--attack", "--pipeline", "--variant", "--select", "--limit", "--until",
    "--prov-spec", "--retry-failed", "--release", "--cache-dir", "--jobs", "--in-process", "--allow-hardlinks",
    "--dry-run", "--max-file-bytes", "--max-json-depth",
}  # fmt: skip
VALIDATE_OPTIONS = {
    "--aer", "--store", "--corpus", "--tiers", "--prov-spec", "--strict", "--release", "--report", "--sample", "--seed",
    "--card", "--jobs", "--dry-run",
}  # fmt: skip


@pytest.mark.parametrize(
    ("command", "expected"), [("run", RUN_OPTIONS), ("import", IMPORT_OPTIONS), ("validate", VALIDATE_OPTIONS)]
)
def test_every_documented_option_exists(command, expected):
    assert expected <= _option_strings(_subparsers(build_parser())[command])


def test_option_defaults_of_n2():
    subs = _subparsers(build_parser())
    run_defaults = subs["run"].parse_args(["agentdojo"])
    assert run_defaults.jobs is None  # resolved by `run`: 1, or computed with a local preset; 0 is a usage error
    assert run_defaults.start_stagger is None and run_defaults.m5ultra is False and run_defaults.dry_run is False
    imp = subs["import"].parse_args(["x"])
    assert imp.jobs == 0 and imp.select == [] and imp.prov_spec == [] and imp.release is False
    val = subs["validate"].parse_args([])
    assert val.jobs == 0 and val.aer == [] and val.files == [] and val.tiers is None


# ---------------------------------------------------------------------------------------- agentprov.api (MN M.6)

M6_NAMES = {
    "__version__", "FORMATS", "open_corpus", "verify_corpus", "iter_executions", "read_aer", "rows", "FRAME_NAMES",
    "statistics", "field_groups", "semantics_profile", "source_registry", "check_claim", "coverage_phrase", "lint_text",
}  # fmt: skip


@pytest.fixture
def corpus(tmp_path):
    ss.standard_corpus(tmp_path / "c.partial")
    return tmp_path / "c"


def test_public_api():
    assert M6_NAMES <= set(api.__all__)
    for name in api.__all__:
        assert hasattr(api, name), name
    assert api.FRAME_NAMES == ("executions", "statements", "field_status", "validation", "profiles", "lineage")
    assert "agentprov-stats/0.1" in api.FORMATS and api.__version__ == "0.1.0"


def test_api_imports_only_core():
    code = ("import sys, agentprov.api; bad = {m.split('.')[0] for m in sys.modules} & {'pandas', 'numpy', 'pyarrow', "
            "'agentdojo', 'inspect_ai', 'openai', 'httpx', 'pydot', 'pyshacl', 'dotenv'}; print(sorted(bad))")  # fmt: skip
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True).stdout.strip()
    assert out == "[]"


def test_corpus_access(corpus, tmp_path):
    with fs_guard.unchanged(tmp_path / "c.partial"):
        opened = api.open_corpus(corpus)
        rows = list(api.iter_executions(opened))
        assert len(rows) == 7 and [r.ex for r in rows] == sorted(r.ex for r in rows)
        assert len(list(api.iter_executions(opened, select={"unit": "agent_execution"}))) == 5
        doc = api.read_aer(rows[0], corpus=opened)
        assert doc.ex == rows[0].ex
        assert api.read_aer(opened.root / rows[0].aer_path).ex == rows[0].ex
        with pytest.raises(ValueError):
            api.read_aer(rows[0])
        executions = list(api.rows(opened, "executions"))
        assert len(executions) == 7 and {e["corpus_id"] for e in executions} == {"tst-stats"}
        assert {"ex", "unit", "execution_observed", "completeness", "status", "issues", "aer_sha256"} <= set(executions[0])
        statements = list(api.rows(opened, "statements"))
        assert sum(r["n"] for r in statements) == 5 * sum(ss.EXPECTED_STATEMENTS.values())  # per-execution grain
        field_status = list(api.rows(opened, "field_status"))
        assert len({r["ex"] for r in field_status}) == 4  # observed agent executions only
        assert list(api.rows(opened, "validation")) == []
        report = api.statistics([opened], tables=("counts",))
        assert report.to_json()["corpora"][0]["population"]["n_executions"] == 4


def test_registry_data():
    profiles = list(api.rows(None, "profiles"))  # type: ignore[arg-type]
    assert profiles and {"source_id", "part", "import_status", "licence_policy"} <= set(profiles[0])
    assert {r.source_id for r in api.source_registry()} >= {"agentdojo", "rope"}
    data = api.semantics_profile("agentdojo.suites", 1)
    assert data["id"] == "agentdojo.suites" and data["sha256"] and data["files"]
    assert [g.id for g in api.field_groups()][:2] == ["ctx", "tooldefs"]


def test_unavailable_parts_say_so(corpus):
    opened = api.open_corpus(corpus)
    with pytest.raises(api.ApiUnavailable) as exc:
        list(api.rows(opened, "lineage"))
    assert "sources[].lineage" in str(exc.value)  # D-541: a working corpus records no lineage; a sealed one serves it
    assert "until that module exists" not in (api.__doc__ or "")  # the claims library is in this build
    chain = api.verify_corpus(corpus)  # the M.6 default level is chain (phase 11, U4)
    assert chain.level == "chain" and "checksums.absent" in chain.codes()  # a working tree has no checksums: unverified
    assert not chain.passed(release=True)  # the hand-built corpus stores no raw objects: the chain level says so
    report = api.verify_corpus(corpus, level="checksums")
    assert not report.ok and report.codes() == {"checksums.absent": 1}  # a working tree has no checksums
    try:
        api.coverage_phrase()
    except api.ApiUnavailable:
        pass  # the claims library (U3) is not in this build
    except TypeError:
        pass  # it is, and wants arguments


def test_cli_startup_loads_no_command_engine():
    """pipeline-perf (D-411): building the parser loads no migration engine; ``migrate`` imports it when it runs.
    ``--help`` output is unchanged (the parser is built exactly as before)."""
    code = ("import sys, agentprov.cli.main as m; m.build_parser(); print(sorted(n for n in sys.modules "
            "if n == 'agentprov.migration' or n.startswith('agentprov.migration.')))")  # fmt: skip
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True).stdout.strip()
    assert out == "[]"
