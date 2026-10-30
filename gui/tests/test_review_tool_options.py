"""GR-45: a tool form (tools/ci_local.py, whose argparse expands abbreviations) takes only the exact option strings it
declares, in Additional options and on resume. "--allow" would turn on the network at tier R1 and a second "-C" would
point the run at another checkout."""

from __future__ import annotations

import pytest

from agentprov_gui.jobs.commands import (
    _R2_FLAGS,
    FORMS,
    FormError,
    build_spec,
    form_options,
    resume_spec,
    tier_of_argv,
)

_DD = "-" + "-"
_ALLOW = _DD + "allow"
_C = "-" + "C"
_PROG = ("/py", "/co/tools/ci_local.py", _C, "/co")
_HOSTILE = (
    _ALLOW + "-net",
    _ALLOW,
    _DD + "a",
    f"{_C} /elsewhere",
    f"{_C}=/elsewhere",
    f"{_C}/elsewhere",
    _DD + "only=core " + _C + " /x",
    _DD,
    "-",
)


@pytest.mark.parametrize("extra", _HOSTILE)
def test_tool_form_refuses_undeclared_options(extra: str) -> None:
    with pytest.raises(FormError):
        build_spec(FORMS["ci_local"], {}, extra=extra)


@pytest.mark.parametrize("tail", [(_ALLOW,), (_DD + "a",), (_C, "/elsewhere"), (_C + "=/x",), (_ALLOW + "-net", "x")])
def test_tool_resume_refuses_undeclared_options(tail: tuple[str, ...]) -> None:
    with pytest.raises(FormError):
        resume_spec("ci_local", (*_PROG, *tail), "R1", "x", tool=_PROG)


def test_tool_form_takes_its_own_options() -> None:
    spec = build_spec(FORMS["ci_local"], {}, extra=f"{_DD}only core {_DD}skip=lint {_DD}strict")
    assert spec.argv == ("--json", "--only", "core", "--skip=lint", "--strict") and spec.tier == "R1"
    net = build_spec(FORMS["ci_local"], {}, extra=_DD + "allow-network")
    assert net.tier == "R2"
    built = build_spec(FORMS["ci_local"], {"only": "core", "allow_network": True})
    resumed = resume_spec("ci_local", (*_PROG, *built.argv), "R1", "x", tool=_PROG)
    assert resumed.argv == (*_PROG, *built.argv) and resumed.tier == "R2"


def test_tier_counts_r2_prefixes() -> None:
    for token in (_ALLOW, _DD + "a", _DD + "fetc", _DD + "i-consent", _ALLOW + "-net=1"):
        assert tier_of_argv([token], "R1") == "R2", token
    assert tier_of_argv([_DD, _DD + "allowed"], "R1") == "R1"  # the end marker, and not a prefix
    assert tier_of_argv([_ALLOW, _DD + "dry-run"], "R1") == "R2"
    # no option a form emits is itself a prefix of an R2 flag (it would raise the tier wrongly)
    emitted = {o for form in FORMS.values() for o in form_options(form)}
    assert not {o for o in emitted - set(_R2_FLAGS) if any(f.startswith(o) for f in _R2_FLAGS)}
