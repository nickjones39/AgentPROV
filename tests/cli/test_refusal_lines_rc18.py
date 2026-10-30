"""Pre-round re-check RC-18: a refusal of many reason lines keeps its leading lines, names what it leaves out, and prints
every line on stderr as a line of its own (never as ``<U+000A>`` escapes in one long line)."""

from __future__ import annotations

import argparse

from agentprov.cli.main import _REFUSAL_LINES, _result_from_exception
from agentprov.corpus.derive import DeriveRefusedError


def _refused(lines: list[str]):
    exc = DeriveRefusedError("\n".join(lines), code="corpus.derive.version_drift")
    return _result_from_exception(exc, argparse.Namespace(command="recompute"))


def test_an_overlong_refusal_names_the_lines_it_leaves_out():
    lines = ["refused:"] + [f"drift {n}" for n in range(30)]
    refusal = _refused(lines).refusal
    assert refusal is not None and len(refusal.lines) == _REFUSAL_LINES
    assert list(refusal.lines[:-1]) == lines[:_REFUSAL_LINES - 1]
    assert refusal.lines[-1] == f"... and {len(lines) - _REFUSAL_LINES + 1} more line(s); see stderr"


def test_a_refusal_that_fits_is_kept_whole():
    lines = ["refused:"] + [f"drift {n}" for n in range(_REFUSAL_LINES - 1)]
    refusal = _refused(lines).refusal
    assert refusal is not None and list(refusal.lines) == lines


def test_each_reason_line_is_its_own_stderr_line_and_the_notice_keeps_the_first_whole():
    first = "refused: " + "x" * 400
    result = _refused([first, "aer: format aer/0.1 recorded, aer/0.2 current"])
    errors = [text for kind, text in result.messages if kind == "error"]
    assert errors == [f"agentprov: error [corpus.derive.version_drift]: {first}",
                      "  aer: format aer/0.1 recorded, aer/0.2 current"]
    assert not any("<U+000A>" in text for text in errors)
    assert result.notices == [f"error corpus.derive.version_drift: {first}"]  # no longer cut at 300 characters
