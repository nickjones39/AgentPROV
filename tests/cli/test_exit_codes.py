"""Exit codes of MN N.1.3 (K.15 item 1, N.6 item 2): one test per code, plus precedence and the signal contract."""

from __future__ import annotations

import signal

import pytest

from agentprov.cli import checks, import_
from agentprov.cli.common import (
    EXIT_CODES,
    CliUsageError,
    UnsupportedCapability,
    exit_code_for,
    install_signal_handlers,
    outcome_for,
)
from agentprov.envinfo import InterpreterUnpatchedError
from agentprov.errors import AgentProvError, IngestError


def test_exit_0_ok(cli, valid_aer):
    run = cli("validate", str(valid_aer))
    assert run.code == 0, run.err


def test_exit_1_failures(cli, broken_aer):
    run = cli("validate", str(broken_aer))
    assert run.code == 1
    assert "FAILED" in run.err


def test_exit_2_usage_argparse(cli):
    assert cli("validate", "--no-such-option").code == 2


def test_exit_2_usage_invalid_combination(cli, tmp_path):
    run = cli("import", "agentdojo", "--snapshot", "2024-06", "--corpus", str(tmp_path / "c"), "--input", str(tmp_path), "--fetch")
    assert run.code == 2
    assert "mutually exclusive" in run.err


def test_exit_2_usage_missing_path(cli, tmp_path):
    run = cli("validate", str(tmp_path / "missing.aer.jsonl"))
    assert run.code == 2


def test_exit_3_environment(cli, tmp_path, monkeypatch):
    def refuse(ctx):
        raise InterpreterUnpatchedError("release mode refuses archive ingestion on this interpreter")

    monkeypatch.setattr(import_, "run_import", refuse)
    run = cli("import", "x", "--corpus", str(tmp_path / "c"), "--input", str(tmp_path), "--json")
    assert run.code == 3
    summary = run.json()
    assert summary["outcome"] == "environment" and summary["exit_code"] == 3
    assert "ingest.interpreter.unpatched" in summary["notices"][0]


def test_exit_4_refused(cli, tmp_path):
    run = cli("import", "agentdojo", "--snapshot", "2024-06", "--corpus", str(tmp_path / "c"), "--fetch", "--json")
    assert run.code == 4
    assert run.json()["outcome"] == "refused"
    assert "--allow-network" in run.err


def test_exit_4_refused_unpinned_input(cli, tmp_path):
    run = cli("import", "agentdojo", "--snapshot", "2024-06", "--corpus", str(tmp_path / "c"), "--input", str(tmp_path), "--json")
    assert run.code == 4 and run.json()["outcome"] == "refused"


def test_exit_5_unsupported(cli, tmp_path):
    # foobench has no import status in the registry (D.12): the status gate refuses it (N.3)
    run = cli("import", "foobench", "--corpus", str(tmp_path / "c"), "--input", str(tmp_path), "--json")
    assert run.code == 5
    summary = run.json()
    assert summary["outcome"] == "unsupported" and summary["refusal"]["id"] == "foobench"


def test_exit_70_internal_one_line_without_a_traceback(cli, tmp_path, monkeypatch):
    def boom(ctx):
        raise RuntimeError("kaboom\nwith a second line and \x1b[31mescape")

    monkeypatch.setattr(import_, "run_import", boom)
    run = cli("import", "x", "--corpus", str(tmp_path / "c"), "--input", str(tmp_path))
    assert run.code == 70
    assert "internal error: RuntimeError" in run.err
    assert "\x1b" not in run.err and "Traceback" not in run.err and "  at " not in run.err
    assert "<U+001B>" in run.err and "<U+000A>" in run.err
    assert "rerun with -v" in run.err


def test_exit_70_with_verbose_shows_frames_and_escapes_arguments(cli, tmp_path, monkeypatch):
    def boom(ctx):
        raise RuntimeError("bad \x1b[2J arg")

    monkeypatch.setattr(import_, "run_import", boom)
    run = cli("-v", "import", "x", "--corpus", str(tmp_path / "c"), "--input", str(tmp_path))
    assert run.code == 70
    assert "  at " in run.err and "boom" in run.err
    assert "\x1b" not in run.err


def test_exit_130_interrupted_still_writes_the_summary(cli, tmp_path, monkeypatch, check_summary):
    def interrupted(ctx):
        raise KeyboardInterrupt

    monkeypatch.setattr(import_, "run_import", interrupted)
    summary_file = tmp_path / "s.json"
    run = cli("import", "x", "--corpus", str(tmp_path / "c"), "--input", str(tmp_path), "--json", "--summary-json", str(summary_file))
    assert run.code == 130
    document = run.json()
    check_summary(document)
    assert document["outcome"] == "interrupted"
    assert summary_file.read_bytes() == run.out.encode()


@pytest.mark.parametrize("where", ["sink", "watcher"])
def test_a_first_signal_while_main_closes_the_sink_or_the_watcher_still_writes_the_summary(cli, tmp_path, monkeypatch, check_summary, where):
    """AU-CLIA-8: the teardown joins can block; a first SIGINT landing there ends the run as 130 with the summary written
    and the progress file closed with its end line, instead of escaping main()."""
    import json

    from agentprov.cli import control, feedback

    cls, name = (feedback.FeedbackSink, "close") if where == "sink" else (control.ControlWatcher, "close")
    original = getattr(cls, name)
    fired: list[int] = []

    def close(self, *args, **kwargs):
        if not fired:
            fired.append(1)
            # the user's Ctrl-C / the job manager's SIGTERM arrives now; raise_signal, not os.kill: on Windows
            # os.kill(pid, SIGINT) is TerminateProcess, which ended the pytest worker (0.2.0 Windows CI, shard 2)
            signal.raise_signal(signal.SIGINT)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(cls, name, close)
    summary_file, progress = tmp_path / "s.json", tmp_path / "p.jsonl"
    argv = ["--progress-file", str(progress), "--summary-json", str(summary_file), "--json"]
    if where == "watcher":
        argv += ["--control-file", str(tmp_path / "control.json")]
    run = cli(*argv, "settings", "list")
    assert fired and run.code == 130, run.err
    document = json.loads(summary_file.read_bytes())
    check_summary(document)
    assert document["outcome"] == "interrupted" and document["exit_code"] == 130
    assert "interrupted while finishing" in run.err
    last = json.loads(progress.read_bytes().splitlines()[-1])
    assert last["event"] == "end"


def test_a_first_signal_inside_the_sinks_join_ends_the_progress_file_with_130(cli, tmp_path, monkeypatch, check_summary):
    """AU-FR-4: ``FeedbackSink.close`` records the exit code before it joins the display thread, and the join is where it
    blocks; a first signal landing there made main's retry ``close(130)`` a no-op, so the progress file's end line kept
    the old exit code (0, ok) while the summary said 130, interrupted."""
    import json
    import threading

    original = threading.Thread.join
    fired: list[int] = []

    def join(self, *args, **kwargs):
        if self.name == "agentprov-feedback" and not fired:
            fired.append(1)
            raise KeyboardInterrupt  # the first Ctrl-C arrives while close waits for the display thread
        return original(self, *args, **kwargs)

    monkeypatch.setattr(threading.Thread, "join", join)
    summary_file, progress = tmp_path / "s.json", tmp_path / "p.jsonl"
    run = cli("--progress-file", str(progress), "--summary-json", str(summary_file), "--json", "settings", "list")
    assert fired and run.code == 130, run.err
    document = json.loads(summary_file.read_bytes())
    check_summary(document)
    assert document["outcome"] == "interrupted" and document["exit_code"] == 130
    last = json.loads(progress.read_bytes().splitlines()[-1])
    assert last["event"] == "end" and last["exit_code"] == 130 and last["outcome"] == "interrupted", last


def test_usage_beats_unsupported_in_the_preflight_order(cli, tmp_path):
    # `import x` without --corpus is a usage error even though the source would end in exit 5
    assert cli("import", "agentdojo", "--snapshot", "2024-06", "--input", str(tmp_path)).code == 2


def test_usage_and_refusal_beat_unsupported(cli, tmp_path):
    # 4 (network not allowed) is raised before the status gate (5)
    assert cli("import", "agentdojo", "--snapshot", "2024-06", "--corpus", str(tmp_path / "c"), "--fetch").code == 4


def test_exit_code_for_maps_typed_errors_and_unknown_codes():
    assert exit_code_for(KeyboardInterrupt()) == 130
    assert exit_code_for(CliUsageError("x")) == 2
    assert exit_code_for(UnsupportedCapability("x")) == 5
    assert exit_code_for(IngestError("ingest.size.file", "x")) == 1
    assert exit_code_for(InterpreterUnpatchedError("x")) == 3
    assert exit_code_for(AgentProvError("x")) == 70
    assert exit_code_for(AgentProvError("x", exit_code=42)) == 70  # not an N.1.3 code
    assert exit_code_for(AgentProvError("x", exit_code=0)) == 70  # an error never maps to success
    assert exit_code_for(ValueError("x")) == 70


def test_outcome_names_cover_every_exit_code():
    assert {outcome_for(c) for c in EXIT_CODES} == {
        "ok", "failures", "usage", "environment", "refused", "unsupported", "internal", "interrupted",
    }  # fmt: skip
    assert outcome_for(99) == "internal"


def test_first_signal_raises_keyboard_interrupt_and_handlers_are_restored():
    before = signal.getsignal(signal.SIGINT)
    with install_signal_handlers():
        assert signal.getsignal(signal.SIGINT) is not before
        with pytest.raises(KeyboardInterrupt):
            signal.raise_signal(signal.SIGINT)
    assert signal.getsignal(signal.SIGINT) is before


@pytest.mark.skipif(not hasattr(signal, "SIGHUP"), reason="the host has no SIGHUP")
def test_a_hang_up_takes_the_clean_interrupt_path_and_names_the_signal():
    from agentprov.cli.common import Interrupted

    before = signal.getsignal(signal.SIGHUP)
    with install_signal_handlers():
        with pytest.raises(Interrupted) as caught:
            signal.raise_signal(signal.SIGHUP)
    assert caught.value.signal_name == "SIGHUP" and isinstance(caught.value, KeyboardInterrupt)
    assert signal.getsignal(signal.SIGHUP) is before


@pytest.mark.skipif(not hasattr(signal, "SIGHUP"), reason="the host has no SIGHUP")
def test_an_inherited_ignored_hang_up_stays_ignored():
    previous = signal.signal(signal.SIGHUP, signal.SIG_IGN)  # what nohup hands the process
    try:
        with install_signal_handlers():
            assert signal.getsignal(signal.SIGHUP) == signal.SIG_IGN
            signal.raise_signal(signal.SIGHUP)  # ignored: nothing is raised
        assert signal.getsignal(signal.SIGHUP) == signal.SIG_IGN
    finally:
        signal.signal(signal.SIGHUP, previous)


def test_a_failing_command_does_not_leave_logging_configured(cli, broken_aer):
    import logging

    cli("validate", str(broken_aer))
    assert logging.getLogger("agentprov").handlers == []
    assert checks  # imported for the monkeypatching tests above


def test_output_flags_inside_a_sealed_corpus_are_refused_and_nothing_is_written(cli, tmp_path):
    """CC-22: --summary-json, --log-file and --progress-file could write a stray file into a sealed corpus."""
    sealed = tmp_path / "sealed"
    sealed.mkdir()
    (sealed / "corpus.json").write_text('{"sealed": true}')
    for flag in ("--summary-json", "--log-file", "--progress-file"):
        run = cli("info", "--format", "json", flag, str(sealed / "out.json"))
        assert run.code == 4 and "sealed corpus" in run.err, (flag, run.err)
        assert sorted(p.name for p in sealed.iterdir()) == ["corpus.json"], flag


def test_a_registered_key_is_redacted_before_the_text_is_cut():
    """CC-31: a key straddling the truncation point printed a partial prefix."""
    from agentprov.cli import common
    from agentprov.cli.common import register_secret, safe_text

    key = "sk-test-" + "Q7" * 20
    register_secret(key)
    try:
        shown = safe_text("x" * 280 + key, 300)
    finally:
        common._secrets.discard(key)
    assert key[:12] not in shown and "sk-test" not in shown


@pytest.mark.parametrize("argv", [
    ("import", "adprov-v1", "--corpus", "C", "--input", ".", "--dry-run", "--limit"),
    ("derive", "--corpus", "C", "--out", "D", "--jobs"),
    ("render", "--corpus", "C", "--limit"),
    ("verify", "--corpus", "C", "--jobs"),
    ("run", "agentdojo", "--jobs"),
    ("run", "agentdojo", "--max-attempts"),
    ("inspect", "C", "--max-chars"),
    ("migrate", "gate-a", "--workers"),
    ("package", "--corpus", "C", "--max-archive-bytes"),
    ("info", "--max-listed"),
], ids=lambda a: "-".join(a[:1] + a[-1:]))
def test_an_integer_option_beyond_the_json_integer_domain_is_a_usage_error(cli, argv):
    """CC-15: 2^53 and above passed parsing and then broke the JCS summary and start log line (exit 70)."""
    run = cli(*argv, str(2**53))
    assert run.code == 2 and "at most 9007199254740991" in run.err, run.err


def test_a_first_signal_inside_a_critical_section_is_raised_when_it_ends():
    """AU-RN-7: inside ``interrupts_deferred`` the first signal is held and raised as Interrupted at the end of the
    outermost section; a section ending with its own error keeps that error and drops the held signal."""
    from agentprov.cli.common import Interrupted, interrupts_deferred

    done: list[str] = []
    with install_signal_handlers():
        with pytest.raises(Interrupted) as caught:
            with interrupts_deferred():
                with interrupts_deferred():
                    signal.raise_signal(signal.SIGINT)
                    done.append("inner")
                done.append("outer")
    assert done == ["inner", "outer"] and caught.value.signal_name == "SIGINT"
    with install_signal_handlers():  # a fresh count: a second signal under one installation exits the process
        with pytest.raises(ValueError):
            with interrupts_deferred():
                signal.raise_signal(signal.SIGINT)
                raise ValueError("the section's own error")
        with interrupts_deferred():  # nothing is held over from the section that failed
            done.append("clean")
    assert done[-1] == "clean"
