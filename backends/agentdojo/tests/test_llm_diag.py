"""The gateway LLM's progress lines on stderr never carry raw provider text (escaping audit F-07)."""

from __future__ import annotations

from agentprov_backend import _llm


class _Completion:
    """A completion with no choices and a provider ``error`` member that is a bare string."""

    choices: list = []

    def __init__(self, error: str) -> None:
        self.model_extra = {"error": error}


def test_diag_escapes_control_bidi_and_tag_characters(capsys):
    hostile = "\x1b[31mred\x1b[0m \u202e \u2066 \U000e0041\nsecond line"
    failure = _llm.upstream_failure(_Completion(hostile))
    _llm._diag(f"[upstream-error] attempt 1/3: sleeping 12s  ({failure})")
    err = capsys.readouterr().err
    assert err.endswith("\n") and err.count("\n") == 1  # one line
    assert err.isascii() and "\x1b" not in err
    assert "\\u001b[31mred" in err and "\\u202e" in err and "\\u2066" in err and "\\U000e0041" in err
