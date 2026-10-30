"""Profile-raised ingest limits (D-323, RB-2): ``[import] limits`` in a source profile, checked by ``agentprov.ingest``.

Only :data:`~agentprov.ingest.profile_limits.PROFILE_RAISABLE` fields may be declared, each from its G.3.2 default up to its
ceiling (raise-only); a defective table fails the profile load. On an import the declared raise is applied to the
effective limits (and recorded as an override in ``corpus.json``); a ``recompute`` replaying ``corpus.json`` must find
the recorded values equal to the declaration (``corpus.derive.limits_mismatch`` otherwise; never a silent pick).
Limits are read from the objects, never hard-coded (K.5.6).
"""

from __future__ import annotations

from importlib import resources

import pytest

from agentprov.adapters.profiles import parse_profile
from agentprov.errors import AgentProvError, ProfileError
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.profile_limits import PROFILE_RAISABLE, apply_profile_limits, check_profile_limits

FIELD = "max_json_element_bytes"
DEFAULT = getattr(IngestLimits(), FIELD)
CEILING = PROFILE_RAISABLE[FIELD]


def test_the_allowlist_is_raise_only_and_capped():
    assert check_profile_limits({FIELD: DEFAULT + 1}) == {FIELD: DEFAULT + 1}
    assert check_profile_limits({FIELD: CEILING}) == {FIELD: CEILING}
    assert check_profile_limits({}) == {}
    for bad in ({FIELD: DEFAULT - 1}, {FIELD: CEILING + 1}, {FIELD: True}, {FIELD: "64MiB"},
                {"max_jsonl_line_bytes": DEFAULT + 1}, {"rss_bytes": 1}, [FIELD]):
        with pytest.raises(ValueError):
            check_profile_limits(bad)


def test_apply_profile_limits_applies_the_raise_and_refuses_a_conflict():
    raised = apply_profile_limits(IngestLimits(), {FIELD: CEILING})
    assert getattr(raised, FIELD) == CEILING and raised.overrides() == {FIELD: CEILING}
    assert apply_profile_limits(raised, {FIELD: CEILING}) == raised  # idempotent
    with pytest.raises(ValueError):
        apply_profile_limits(IngestLimits().replace(**{FIELD: DEFAULT + 7}), {FIELD: CEILING})


def _profile_text(limits_line: str) -> bytes:
    text = resources.files("agentprov").joinpath("adapters", "credleak", "profiles",
                                                 "credleak-p15b.profile.toml").read_text("utf-8")
    assert "\n[import]\n" in text
    return text.replace("\n[import]\n", f"\n[import]\n{limits_line}\n", 1).encode()


def test_the_profile_load_checks_the_table():
    profile = parse_profile(_profile_text(f"limits = {{ {FIELD} = {CEILING} }}"), source="t")
    assert dict(profile.data["import"]["limits"]) == {FIELD: CEILING}
    for bad in (f"limits = {{ {FIELD} = {CEILING + 1} }}", f"limits = {{ {FIELD} = {DEFAULT - 1} }}",
                f"limits = {{ max_member_bytes = {CEILING} }}", f"limits = {CEILING}"):
        with pytest.raises(ProfileError):
            parse_profile(_profile_text(bad), source="t")


def test_import_applies_and_recompute_compares():
    from agentprov.adapters.runner.importer import _profile_limits

    raising = parse_profile(_profile_text(f"limits = {{ {FIELD} = {CEILING} }}"), source="t")
    plain = parse_profile(_profile_text(""), source="t")
    same = raising.version
    applied = _profile_limits(IngestLimits(), raising, recorded_under=None)
    assert getattr(applied, FIELD) == CEILING
    assert _profile_limits(applied, raising, recorded_under=same) == applied  # replay of what the import recorded
    assert _profile_limits(IngestLimits(), plain, recorded_under=same) == IngestLimits()
    for limits, profile in ((IngestLimits(), raising), (applied, plain)):  # changed under the same profile version
        with pytest.raises(AgentProvError) as mismatch:
            _profile_limits(limits, profile, recorded_under=same)
        assert mismatch.value.code == "corpus.derive.limits_mismatch"
    # under another profile version the bump explains the change (D-31): the current declaration applies
    assert _profile_limits(IngestLimits(), raising, recorded_under=same - 1) == applied
    assert _profile_limits(applied, plain, recorded_under=same - 1) == IngestLimits()
    with pytest.raises(AgentProvError) as conflict:
        _profile_limits(IngestLimits().replace(**{FIELD: DEFAULT + 7}), raising, recorded_under=None)
    assert conflict.value.code == "adapter.limits_conflict"


def test_the_profile_limits_live_outside_the_expand_stage_identity():
    """The allowlist is its own module so that no ``expand`` hashed module changes (``raw.members.EXPAND_MODULES``): a
    container corpus's ``expand`` identity is unaffected by D-323."""
    from agentprov.raw.members import EXPAND_MODULES

    assert "ingest/profile_limits.py" not in EXPAND_MODULES and "ingest/limits.py" in EXPAND_MODULES
    assert not hasattr(IngestLimits, "with_profile")
