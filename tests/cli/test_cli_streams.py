"""Streams, the summary document and output safety (MN N.1.4, N.1.13; N.6 item 1; K.15 items 1 and 5)."""

from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

from agentprov.cli.common import CommandResult, build_summary, normalised_options, redact_personal, safe_text


def test_stdout_is_machine_only_stderr_is_human(cli, valid_aer, check_summary):
    run = cli("validate", str(valid_aer), "--json")
    assert run.code == 0
    document = json.loads(run.out)  # stdout is exactly one JSON document
    check_summary(document)
    assert run.out.endswith("\n") and run.out.count("\n") == 1
    assert "passed" in run.err  # the human line is on stderr only


def test_summary_is_byte_stable_across_runs(cli, valid_aer):
    first = cli("validate", str(valid_aer), "--json")
    second = cli("validate", str(valid_aer), "--json")
    assert first.out == second.out != ""


def test_summary_holds_no_times_or_durations(cli, valid_aer):
    text = cli("validate", str(valid_aer), "--json").out
    for word in ("duration", "elapsed", "_s\"", "timestamp"):
        assert word not in text


def test_summary_json_file_is_the_same_bytes_as_stdout(cli, valid_aer, tmp_path):
    target = tmp_path / "out.json"
    run = cli("validate", str(valid_aer), "--json", "--summary-json", str(target))
    assert target.read_bytes() == run.out.encode("utf-8")
    assert [p.name for p in tmp_path.iterdir() if p.name.startswith(".")] == []  # atomic: no temp leftovers


def test_summary_json_without_json_writes_only_the_file(cli, valid_aer, tmp_path):
    target = tmp_path / "out.json"
    run = cli("validate", str(valid_aer), "--summary-json", str(target))
    assert run.out == "" and json.loads(target.read_text())["command"] == "validate"


def test_summary_json_into_a_missing_directory_is_a_usage_error(cli, valid_aer, tmp_path):
    run = cli("validate", str(valid_aer), "--summary-json", str(tmp_path / "nope" / "s.json"))
    assert run.code == 2


def test_summary_for_a_failure_validates_and_lists_failures_sorted(cli, broken_aer, check_summary):
    run = cli("validate", str(broken_aer), "--json")
    document = run.json()
    check_summary(document)
    assert document["exit_code"] == 1 and document["outcome"] == "failures"
    keys = [(f["subject"]["path"], f["stage"], f["code"]) for f in document["failures"]]
    assert keys == sorted(keys)
    assert document["counters"]["failed"] == 1 and document["issues_by_code"]


def test_max_listed_caps_failures_and_sets_the_truncation_flag():
    result = CommandResult(exit_code=1)
    result.failures = [
        {"subject": {"path": f"f{i:02d}"}, "stage": "aer", "code": "aer.x", "detail": ""} for i in reversed(range(7))
    ]
    document = build_summary(command="validate", exit_code=1, result=result, options={}, max_listed=3)
    assert [f["subject"]["path"] for f in document["failures"]] == ["f00", "f01", "f02"]
    assert document["failures_truncated"] is True
    document = build_summary(command="validate", exit_code=1, result=result, options={}, max_listed=7)
    assert document["failures_truncated"] is False and len(document["failures"]) == 7


def test_max_listed_zero_lists_nothing_but_says_so(cli, broken_aer):
    document = cli("validate", str(broken_aer), "--json", "--max-listed", "0").json()
    assert document["failures"] == [] and document["failures_truncated"] is True


def test_options_record_what_was_given_and_never_output_controls(cli, valid_aer):
    document = cli("validate", str(valid_aer), "--json", "--progress", "steps", "--log-format", "json", "-v").json()
    options = document["options"]
    assert options["files"] == [redact_personal(str(valid_aer))]  # $HOME is written <home>; a temp dir may sit under it
    for name in ("progress", "log_format", "verbose", "json", "show_content", "progress_file", "summary_json"):
        assert name not in options
    assert "feedback" not in options and "handler" not in options and "command" not in options


def test_normalised_options_write_home_as_placeholder(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    import argparse

    ns = argparse.Namespace(corpus=str(tmp_path / "corpus"), env_file=None, json=True)
    assert normalised_options(ns) == {"corpus": "<home>/corpus".replace("/", os.sep) if os.sep != "/" else "<home>/corpus"}


def test_home_and_host_are_redacted_on_non_content_surfaces(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setattr("platform.node", lambda: "lab-machine.example")
    assert redact_personal(f"see {tmp_path}/x/y and {tmp_path}") == "see <home>/x/y and <home>"
    assert redact_personal("running on lab-machine.example today") == "running on <host> today"
    assert redact_personal("lab-machine alone") == "<host> alone"
    assert redact_personal(f"{tmp_path}extra") == f"{tmp_path}extra"  # a longer name is not the home directory


def test_failures_report_home_as_placeholder(cli, monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    bad = tmp_path / "bad.aer.jsonl"
    bad.write_bytes(b"nope\n")
    run = cli("validate", str(bad), "--json")
    assert str(tmp_path) not in run.out and str(tmp_path) not in run.err
    assert run.json()["failures"][0]["subject"]["path"].startswith("<home>")


def test_untrusted_file_names_never_reach_the_terminal_raw(cli, tmp_path):
    evil = tmp_path / "evil\x1b[31m\u202eNAME.aer.jsonl"
    try:
        evil.write_bytes(b"not json\n")
    except OSError:
        pytest.skip("this host's file system rejects control characters in names")
    run = cli("validate", str(evil), "--json")
    assert run.code == 1
    for text in (run.err, run.out):
        assert "\x1b" not in text and "\u202e" not in text
    assert "<U+001B>" in run.err and "<U+202E>" in run.err
    assert "<U+001B>" in run.json()["failures"][0]["subject"]["path"]


def test_safe_text_is_one_line_escaped_and_truncated():
    text = safe_text("a\nb\tc\x1b[0m\u202e" + "z" * 600, max_chars=20)
    assert "\n" not in text and "\t" not in text and "\x1b" not in text and "\u202e" not in text
    assert text.startswith("a<U+000A>b<U+0009>c<U+001B>")
    assert "truncated" in text


def test_register_secret_values_are_redacted_in_display_text():
    from agentprov.cli import common

    common.register_secret("hunter2-token")
    try:
        assert safe_text("key=hunter2-token!") == "key=«redacted»!"
        common.register_secret("ab")  # too short to register
        assert safe_text("abcab") == "abcab"
    finally:
        common._secrets.clear()


def test_stdout_of_a_real_subprocess_is_only_the_summary(valid_aer):
    """K.15: real streams. The validator catalogue patch of ``valid_aer`` does not reach a subprocess, so this
    run validates a deliberately broken file and checks the stream split."""
    bad = valid_aer.with_name("worse.aer.jsonl")
    bad.write_bytes(b"{}\n")
    done = subprocess.run(
        [sys.executable, "-m", "agentprov", "validate", str(bad), "--json", "--progress", "off", "-q"],
        capture_output=True,
        timeout=60,
    )
    assert done.returncode == 1
    assert json.loads(done.stdout)["format"] == "agentprov-cli-summary/0.1"
    assert b"FAILED" in done.stderr and b"FAILED" not in done.stdout


def test_verify_archive_mode_escapes_the_archived_corpus_id_and_version(cli, tmp_path):
    """CC-1: the root-digest line of archive-mode ``verify`` carries the archived manifest's ``corpus_id`` and
    ``corpus_version``, which are untrusted: escape sequences and line breaks never reach the terminal (N.1.13)."""
    import hashlib
    import zipfile

    from agentprov.corpus.reader import CORPUS_FORMAT

    manifest = json.dumps({"corpus_id": "bad\x1b[2Jid\nFORGED LINE", "corpus_version": "2\x07", "sealed": True,
                           "format": CORPUS_FORMAT}).encode()
    meta = tmp_path / "y-v2.meta.zip"
    with zipfile.ZipFile(meta, "w") as archive:
        archive.writestr("y-v2/corpus.json", manifest)
        archive.writestr("y-v2/checksums.sha256", f"{hashlib.sha256(manifest).hexdigest()}  corpus.json\n")
    run = cli("verify", "--corpus", str(meta))
    assert "root digest" in run.err
    assert "\x1b" not in run.err and "\x07" not in run.err
    assert not any(line.startswith("FORGED LINE") for line in run.err.splitlines())
