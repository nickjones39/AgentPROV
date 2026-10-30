"""``[import] variant_labels`` is checked the same way for every family (D-480; invariant 5; CD-3).

A label may name a variant the profile does not declare in ``[import] variants`` only when the label is a part the
profile does not import itself: the entry then records which other part (served by another import) the variant belongs
to. The generic check used to exempt one DRIFT variant name instead.
"""

from __future__ import annotations

import pytest

from agentprov.adapters.profiles import load_profile, parse_profile
from agentprov.errors import ProfileError

TEMPLATE = """
[profile]
id = "foobench"
version = 1
format = "agentprov-source-profile/0.1"
source_id = "foobench"
family = "foobench"
parts = ["a"]
[source]
[licence]
[lineage]
[import]
variants = ["v1"]
variant_labels = {{ {labels} }}
"""


def _parse(labels: str):
    return parse_profile(TEMPLATE.format(labels=labels).encode())


@pytest.mark.parametrize("labels", ['"drift.k18.conversations" = "a"', '"v2" = "a"'])
def test_an_undeclared_variant_labelled_with_an_imported_part_is_refused(labels):
    with pytest.raises(ProfileError, match="variant_labels"):
        _parse(labels)


@pytest.mark.parametrize("labels", ['"v1" = "a"', '"v1" = "a", "v2" = "z"', '"drift.k18.conversations" = "z"'])
def test_declared_variants_and_labels_of_parts_imported_elsewhere_are_accepted(labels):
    assert _parse(labels).family == "foobench"


@pytest.mark.parametrize("version", [1, 2])
def test_the_agentdyn_profiles_still_load(version):
    profile = load_profile("agentdyn", version)
    assert profile.data["import"]["variant_labels"]["drift.k18.conversations"] == "d"
    assert "d" not in profile.parts
