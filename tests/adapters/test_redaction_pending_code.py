"""``select.redaction_pending`` (D-324, R-10p-5): an ``[import] exclude`` code for executions a profile holds back until a
pending redaction covers them (D-182). A known register code of stage ``select``, accepted by the profile schema, and
counted in ``selection_excluded`` like any exclude (HL H.6.3, H.6.1 R1)."""

from __future__ import annotations

from importlib import resources

import pytest

from agentprov.adapters.profiles import SELECT_CODES, parse_profile
from agentprov.corpus.register import RegisterEntry, RegisterError, is_known_code
from agentprov.errors import ProfileError

CODE = "select.redaction_pending"


def test_the_code_is_a_select_code_of_the_register():
    assert is_known_code(CODE) and CODE in SELECT_CODES
    entry = RegisterEntry(subject={"snapshot_id": "head", "path": "runs/a.json"}, code=CODE, severity="info",
                          stage="select", disposition="not_imported", detail="held back until the redaction lands")
    assert entry.to_json()["code"] == CODE
    with pytest.raises(RegisterError):  # the stage of a select code is select
        RegisterEntry(subject={"snapshot_id": "head", "path": "runs/a.json"}, code=CODE, severity="info", stage="map",
                      disposition="not_imported")


def test_a_profile_exclude_may_carry_it_and_an_unknown_code_is_still_refused():
    text = resources.files("agentprov").joinpath("adapters", "agentops", "profiles",
                                                 "agentops-bench-pilot.profile.toml").read_text("utf-8")
    anchor = next(line for line in text.splitlines(keepends=True) if 'code = "select.out_of_scope"' in line)
    held = '  { glob = "pilot_v1_seeded/x/y/clean/safety_001_run1.json", code = "select.redaction_pending", note = "D-182" },\n'
    parse_profile(text.replace(anchor, anchor + held, 1).encode(), source="t")
    with pytest.raises(ProfileError):
        parse_profile(text.replace(anchor, anchor + held.replace(CODE, "select.redaction_maybe"), 1).encode(), source="t")
