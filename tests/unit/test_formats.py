"""The closed set of format ids (HL L.1.1, L.1.2; MN M.1.2): readers fail closed."""

from __future__ import annotations

import pytest

from agentprov import formats
from agentprov.versions import VERSIONS


def test_the_l11_list_is_in_the_set():
    for format_id in ("aer/0.1", "aer/0.2", "sem/0.1", "capture/0.1", "agentprov-corpus/0.1", "agentprov-corpus/0.2", "agentprov-index/0.1",
                      "agentprov-register/0.1", "agentprov-derivation/0.1", "agentprov-raw-references/0.1",
                      "agentprov-withheld/0.1", "agentprov-deposit/0.1", "agentprov-cli-summary/0.1",
                      "agentprov-source-profile/0.1", "agentprov-rule-catalogue/0.1", "agentprov-transcript/0.1",
                      "agentprov-migration-gate/0.1", "agentprov-job/0.1", "agentprov-backend/0.1", "agentprov-run-plan/0.1"):
        assert formats.require_supported(format_id) == format_id
    assert {VERSIONS["aer"], VERSIONS["sem"], VERSIONS["capture"], VERSIONS["corpus_format"]} <= formats.FORMATS


@pytest.mark.parametrize("bad", ["aer/0.3", "agentprov-corpus/1.0", "agentprov-collection/0.1", "AER/0.1", "", None, 1, ["aer/0.1"]])
def test_anything_else_is_refused(bad):
    assert not formats.is_supported(bad)
    with pytest.raises(formats.UnsupportedFormatError) as exc:
        formats.require_supported(bad)
    assert exc.value.exit_code == 1 and (not isinstance(bad, str) or not bad or bad not in str(exc.value))


def test_expected_narrows_the_set():
    assert formats.require_supported("aer/0.1", expected=frozenset({"aer/0.1", "sem/0.1"})) == "aer/0.1"
    with pytest.raises(formats.UnsupportedFormatError) as exc:
        formats.require_supported("sem/0.1", expected="aer/0.1")
    assert exc.value.code == "format.unexpected"


def test_the_groups_are_disjoint_and_the_reserved_id_is_out():
    groups = [formats.RECORD_FORMATS, formats.CORPUS_LAYER_FORMATS, formats.SPEC_FORMATS, formats.AS_BUILT_FORMATS]
    assert sum(len(g) for g in groups) == len(formats.FORMATS)
    assert not formats.RESERVED_FORMATS & formats.FORMATS
