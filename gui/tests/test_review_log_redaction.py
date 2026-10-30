"""GR-16 (review G-F#3): ``gui.log`` has the S12 redaction filter for registered secret values (design §8.2).

The filter sits on the handler, so records from child loggers (``agentprov_gui.jobs`` and so on) are redacted too.
The secret is built from fragments at runtime; no key is ever held by the test.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from pathlib import Path

import pytest

from agentprov_gui import app


@pytest.fixture
def gui_log(tmp_path: Path) -> Iterator[Path]:
    root = logging.getLogger("agentprov_gui")
    before = list(root.handlers)
    level = root.level
    app._gui_log(tmp_path)
    yield tmp_path / "gui.log"
    for handler in root.handlers:
        if handler not in before:
            root.removeHandler(handler)
            handler.close()
    root.setLevel(level)
    app._SECRETS.clear()


def _read(path: Path) -> str:
    for handler in logging.getLogger("agentprov_gui").handlers:
        handler.flush()
    return path.read_text(encoding="utf-8")


def test_registered_secret_is_redacted_from_child_loggers(gui_log: Path) -> None:
    secret = "sk-" + "or-v1-" + "ab" * 16
    app.register_secret(secret)
    child = logging.getLogger("agentprov_gui.jobs")
    child.info("env %s", secret)
    child.info("x " + secret)
    child.info("tuple %s %d", "k=" + secret, 3)
    text = _read(gui_log)
    assert secret not in text
    assert text.count("[REDACTED]") == 3
    assert "tuple k=[REDACTED] 3" in text


def test_every_handler_has_the_filter(gui_log: Path) -> None:
    handlers = logging.getLogger("agentprov_gui").handlers
    assert handlers
    assert all(any(isinstance(f, app.RedactingFilter) for f in h.filters) for h in handlers)


def test_short_values_are_not_registered(gui_log: Path) -> None:
    app.register_secret("")
    app.register_secret("a" * 7)
    logging.getLogger("agentprov_gui.jobs").info("aaaaaaa plain")
    text = _read(gui_log)
    assert "aaaaaaa plain" in text
    assert "[REDACTED]" not in text


class _Unprintable:
    def __str__(self) -> str:
        raise ValueError("no str")

    __repr__ = __str__


def test_malformed_call_with_a_secret_neither_raises_nor_leaks(gui_log: Path,
                                                               capsys: pytest.CaptureFixture[str]) -> None:
    """GR-43: the filter never raises into the caller, and an unformattable record still has its secret removed
    (the stdlib's ``handleError`` would otherwise dump the raw arguments to stderr)."""
    secret = "sk-" + "or-v1-" + "cd" * 16
    app.register_secret(secret)
    child = logging.getLogger("agentprov_gui.jobs")
    child.info("count %d", "notanumber")
    child.info("%s %d", secret, "x")
    child.info("obj %s", _Unprintable())
    text = _read(gui_log)
    err = capsys.readouterr().err
    assert secret not in text
    assert secret not in err
    assert "[REDACTED]" in text
    assert text.count("<unformattable>") == 3


def test_exception_and_stack_text_are_redacted(gui_log: Path) -> None:
    """GR-43: tracebacks (``exc_info``) and ``stack_info`` go through the same redaction as the message."""
    secret = "sk-" + "or-v1-" + "ef" * 16
    app.register_secret(secret)
    child = logging.getLogger("agentprov_gui.jobs")
    try:
        raise RuntimeError("bad key " + secret)
    except RuntimeError:
        child.exception("job failed")
    child.info("stack", stack_info=True)
    text = _read(gui_log)
    assert secret not in text
    assert "RuntimeError: bad key [REDACTED]" in text
    assert "Stack (most recent call last)" in text
