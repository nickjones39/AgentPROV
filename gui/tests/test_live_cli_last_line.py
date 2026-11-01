"""Review UC-15: ``last_line`` gave the CLI's closing ``INFO agentprov.cli: end command=...`` log line, so every message
box built from it (assist, settings, models, keys) showed the log line instead of the reason."""

from __future__ import annotations

from agentprov_gui.live.cli import last_line

STDERR = (b'INFO agentprov.cli: start command=assist agentprov=0.1.1 options={"format":"json"}\n'
          b"agentprov: error [cli.environment.keychain]: the keychain cannot be read (keychain.unavailable)\n"
          b"INFO agentprov.cli: end command=assist exit_code=3 outcome=environment counters={}\n")


def test_the_reason_is_shown_not_the_closing_log_line() -> None:
    assert last_line(STDERR) == "agentprov: error [cli.environment.keychain]: the keychain cannot be read (keychain.unavailable)"


def test_debug_lines_are_skipped_and_other_lines_kept() -> None:
    err = b"agentprov: refused: not loopback\nDEBUG agentprov.cli.assist: detail\n\n"
    assert last_line(err) == "agentprov: refused: not loopback"
    assert last_line(b"WARNING agentprov.cli: slow\n") == "WARNING agentprov.cli: slow"
    assert last_line(b"INFO agentprov.cli: end command=x exit_code=0\n") == ""
    assert last_line(b"") == ""
