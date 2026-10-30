"""D-1001: a sealed ``corpus.json`` has no ``limits`` record (``corpus-0.2`` is closed), so ``recompute`` rebuilds the
ingest-limit overrides from the source profile its ``aer`` stage records and keeps them only when their digest equals the
stage's ``limits_sha256``. Otherwise it keeps the defaults, and the importer refuses a profile that raises a limit
(``corpus.derive.limits_mismatch``, D-323), as before.
"""

from __future__ import annotations

from typing import Any

import pytest

from agentprov.corpus.derive import Catalogues, Derivation
from agentprov.errors import AgentProvError
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.profile_limits import PROFILE_RAISABLE, apply_profile_limits
from agentprov.io.canonical import jcs_bytes, sha256_hex

FIELD = "max_json_element_bytes"
CEILING = PROFILE_RAISABLE[FIELD]
RAISED = apply_profile_limits(IngestLimits(), {FIELD: CEILING})
#: mcphunt-w2b's ``aer`` stage (sealed 2026-10-29): the limits of ``mcphunt@3``'s raise over the defaults
MCPHUNT_LIMITS_SHA256 = "sha256:f4058f07777d6ce292ed790b271e6d7081e5b052366b4342eb700a7d77aae2a3"


def digest(limits: IngestLimits) -> str:
    return "sha256:" + sha256_hex(jcs_bytes(limits.to_json()))


def derivation(manifest: dict[str, Any], stages: list[dict[str, Any]], declared: dict[str, Any]) -> Derivation:
    """A :class:`Derivation` with only what :meth:`~Derivation.recorded_limit_overrides` reads."""
    d = object.__new__(Derivation)
    d.manifest = manifest
    d.src_stages = {("aer", i) if i else "aer": s for i, s in enumerate(stages)}  # type: ignore[assignment]
    d.notices = []
    d.catalogues = Catalogues(source_profile_sha256=lambda _p, _v: None, semantics=lambda _r: None,
                              profile_limits=lambda pid, v: declared if (pid, v) == ("p", 3) else {})
    return d


def aer(limits_sha256: str, profile: str = "p@3") -> dict[str, Any]:
    return {"stage": "aer", "profile": profile, "limits_sha256": limits_sha256}


def test_a_working_manifest_keeps_its_recorded_overrides():
    d = derivation({"limits": {"overrides": {FIELD: CEILING}}}, [aer("sha256:" + "0" * 64)], {})
    assert d.recorded_limit_overrides() == {FIELD: CEILING} and not d.notices
    assert derivation({"limits": {}}, [aer(digest(RAISED))], {FIELD: CEILING}).recorded_limit_overrides() == {}


def test_a_sealed_manifest_rebuilds_the_overrides_when_the_digest_matches():
    d = derivation({}, [aer(digest(RAISED))], {FIELD: CEILING})
    assert d.recorded_limit_overrides() == {FIELD: CEILING}
    assert len(d.notices) == 1 and "D-1001" in d.notices[0]


@pytest.mark.parametrize("stages, declared", [
    ([aer(digest(IngestLimits()))], {FIELD: CEILING}),  # the import ran at the defaults
    ([aer(digest(RAISED.replace(**{FIELD: CEILING - 1})))], {FIELD: CEILING}),  # another value was recorded
    ([aer(digest(RAISED), profile="p@2")], {FIELD: CEILING}),  # the profile version the catalogue does not raise
    ([aer(digest(RAISED)), aer(digest(IngestLimits()))], {FIELD: CEILING}),  # two aer stages disagree
    ([], {FIELD: CEILING}),  # no aer stage
    ([aer(digest(RAISED))], {}),  # the profile declares nothing
])
def test_without_a_matching_digest_nothing_is_rebuilt(stages, declared):
    d = derivation({}, stages, declared)
    assert d.recorded_limit_overrides() == {} and not d.notices


def test_the_importer_accepts_the_rebuilt_limits_and_still_refuses_a_mismatch():
    from agentprov.adapters.profiles import load_profile
    from agentprov.adapters.runner.importer import _profile_limits
    from agentprov.cli.derive import _limits

    profile = load_profile("mcphunt", 3)
    declared = dict(profile.data["import"]["limits"])
    matching = derivation({}, [aer(MCPHUNT_LIMITS_SHA256)], declared).recorded_limit_overrides()
    replayed = _limits(matching)
    assert digest(replayed) == MCPHUNT_LIMITS_SHA256
    assert _profile_limits(replayed, profile, recorded_under=3) == replayed
    other = derivation({}, [aer(digest(IngestLimits()))], declared).recorded_limit_overrides()
    with pytest.raises(AgentProvError) as refused:
        _profile_limits(_limits(other), profile, recorded_under=3)
    assert refused.value.code == "corpus.derive.limits_mismatch"


def test_the_cli_catalogue_reads_a_profile_versions_declared_limits():
    from agentprov.cli.derive import catalogues

    injected = catalogues()
    assert dict(injected.profile_limits("mcphunt", 3)) == {FIELD: 64 * 2**20}
    assert digest(apply_profile_limits(IngestLimits(), injected.profile_limits("mcphunt", 3))) == MCPHUNT_LIMITS_SHA256
    assert injected.profile_limits("mcphunt", 999) == {} and injected.profile_limits("no-such-profile", 1) == {}
