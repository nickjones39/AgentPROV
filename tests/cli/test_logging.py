"""Logging (MN N.1.12): library loggers only, one stderr handler, JCS JSON lines, redaction, content gating."""

from __future__ import annotations

import io
import json
import logging

import pytest

from agentprov.cli.common import configure_logging, format_exception_safe, register_secret
from agentprov.io.canonical import jcs_bytes

log = logging.getLogger("agentprov.test.logging")


@pytest.fixture
def handle():
    handles = []

    def make(level=logging.INFO, fmt="text", file=None, **kw):
        stream = io.StringIO()
        handles.append(configure_logging(level, fmt, file, stream=stream, **kw))
        return stream

    yield make
    for h in reversed(handles):
        h.close()


def test_text_format_is_level_logger_message_with_context(handle):
    out = handle()
    log.info("imported %d units", 3, extra={"ex": "ex_abc", "stage": "map", "code": "map.x", "ignored": "nope"})
    assert out.getvalue() == "INFO agentprov.test.logging: imported 3 units [ex=ex_abc stage=map code=map.x]\n"


def test_json_format_is_one_jcs_object_per_line_with_the_documented_keys(handle):
    out = handle(fmt="json")
    log.warning("careful", extra={"cell": "c1", "source_key": "sha256:ab#{}"})
    line = out.getvalue().rstrip("\n")
    obj = json.loads(line)
    assert set(obj) == {"ts", "level", "logger", "msg", "cell", "source_key"}
    assert obj["level"] == "WARNING" and obj["logger"] == "agentprov.test.logging" and obj["msg"] == "careful"
    assert obj["ts"].endswith("Z") and "T" in obj["ts"]
    assert line.encode() == jcs_bytes(obj)  # RFC 8785


def test_levels_default_info_verbose_debug_quiet_warning(handle):
    out = handle(level=logging.WARNING)
    log.info("hidden")
    log.warning("shown")
    assert out.getvalue().count("\n") == 1 and "shown" in out.getvalue()
    out2 = handle(level=logging.DEBUG)
    log.debug("now visible")
    assert "now visible" in out2.getvalue()


def test_file_handler_logs_debug_json_lines_while_stderr_stays_at_its_level(handle, tmp_path):
    path = tmp_path / "run.log"
    out = handle(level=logging.WARNING, file=str(path))
    log.debug("only in the file")
    log.warning("in both")
    assert "only in the file" not in out.getvalue() and "in both" in out.getvalue()
    for h in logging.getLogger("agentprov").handlers:
        h.flush()
    lines = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert [r["msg"] for r in lines] == ["only in the file", "in both"]
    assert all(r["level"] in ("DEBUG", "WARNING") for r in lines)


def test_there_is_exactly_one_stderr_handler_plus_the_optional_file_and_close_restores(tmp_path):
    logger = logging.getLogger("agentprov")
    before = (list(logger.handlers), logger.level, logger.propagate)
    handle = configure_logging(logging.INFO, "text", None, stream=io.StringIO())
    assert len(logger.handlers) == 1 and logger.propagate is False
    handle.close()
    assert (list(logger.handlers), logger.level, logger.propagate) == before
    handle = configure_logging(logging.INFO, "text", str(tmp_path / "x.log"), stream=io.StringIO())
    assert len(logger.handlers) == 2 and logger.level == logging.DEBUG
    handle.close()
    assert list(logger.handlers) == before[0]


def test_messages_are_escaped_and_single_line(handle):
    out = handle()
    log.info("tool said %s", "line1\nline2 \x1b[31mred\x1b[0m \u202e")
    text = out.getvalue()
    assert text.count("\n") == 1
    assert "\x1b" not in text and "\u202e" not in text and "<U+001B>" in text and "<U+000A>" in text


def test_personal_paths_and_host_are_redacted_in_log_lines(handle, monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setattr("platform.node", lambda: "workstation-7.lab")
    out = handle()
    log.info("reading %s on workstation-7.lab", tmp_path / "corpus")
    assert "<home>" in out.getvalue() and "<host>" in out.getvalue()
    assert str(tmp_path) not in out.getvalue() and "workstation-7" not in out.getvalue()


def test_registered_credential_values_are_redacted(handle):
    from agentprov.cli import common

    register_secret("sk-test-VALUE-123456")
    try:
        out = handle(fmt="json")
        log.info("sending header Authorization: Bearer sk-test-VALUE-123456")
        assert "sk-test-VALUE-123456" not in out.getvalue() and "«redacted»" in json.loads(out.getvalue())["msg"]
    finally:
        common._secrets.clear()


def test_content_extras_are_hidden_unless_log_content_at_debug(handle):
    hidden = handle(level=logging.DEBUG)
    log.debug("model reply", extra={"content": "SECRET PROMPT TEXT"})
    assert "SECRET" not in hidden.getvalue()
    shown = handle(level=logging.DEBUG, log_content=True)
    log.debug("model reply", extra={"content": "SECRET PROMPT TEXT" + "x" * 500})
    text = shown.getvalue()
    assert "SECRET PROMPT TEXT" in text and "truncated" in text  # capped at 200 characters
    info_out = handle(level=logging.INFO, log_content=True)
    log.info("not a debug record", extra={"content": "STILL HIDDEN"})
    assert "STILL HIDDEN" not in info_out.getvalue()


def test_exception_arguments_are_escaped_and_frames_appear_only_at_debug(handle):
    def boom():
        raise ValueError("bad \x1b[2J payload", "second\narg")

    try:
        boom()
    except ValueError as exc:
        info_out = handle(level=logging.INFO)
        log.error("failed", exc_info=exc)
        debug_out = handle(level=logging.DEBUG)
        log.error("failed", exc_info=exc)
    assert "\x1b" not in info_out.getvalue() + debug_out.getvalue()
    assert "ValueError: bad <U+001B>[2J payload, second<U+000A>arg" in info_out.getvalue()
    assert "  at " not in info_out.getvalue()
    assert "  at " in debug_out.getvalue() and "in boom" in debug_out.getvalue()


def test_format_exception_safe_follows_the_cause_chain_once():
    try:
        try:
            raise KeyError("inner\x00")
        except KeyError as inner:
            raise RuntimeError("outer") from inner
    except RuntimeError as exc:
        text = format_exception_safe(exc, frames=False)
    assert text.splitlines() == ["RuntimeError: outer", "KeyError: inner<U+0000>"]


def test_unknown_level_is_rejected():
    with pytest.raises(ValueError):
        configure_logging("NOPE")


def test_libraries_never_configure_handlers():
    """N.1.12(1): no module under src/agentprov outside cli/ installs a handler or calls basicConfig."""
    import ast
    from pathlib import Path

    root = Path(__file__).resolve().parents[2] / "src" / "agentprov"
    offenders = []
    for path in root.rglob("*.py"):
        if "cli" in path.relative_to(root).parts[:1]:
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Attribute) and node.attr in ("basicConfig", "addHandler", "StreamHandler", "FileHandler"):
                offenders.append(f"{path.relative_to(root)}:{node.lineno}")
    assert offenders == []
