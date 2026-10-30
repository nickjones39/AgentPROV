"""Licence classes in deposits (D-42; AD-20(b), D-25, H.10.6; DoD Q.28; K.17 item 5).

The class of a corpus is ``(licences.derived.spdx, sorted licences.restrictions)``. One deposit holds one class unless
``--allow-mixed-licence-classes`` (recorded in the metadata and the datasheet copies); a non-commercial class is never
mixed and lives only in an ``-nc`` corpus under ``nc_partition``; copyleft and non-commercial source licences are never
relicensed. The matrix runs on manifests (fast, every row) and end to end on sealed test corpora.
"""

from __future__ import annotations

import json

import pytest
import release_support as rs

from agentprov.release.builder import DEPOSIT_MANIFEST, DEPOSIT_METADATA
from agentprov.release.metadata import LicenceClass, LicenceClassError, check_licence_classes, licence_class

CLAUSE = rs.AGENTHARM_CLAUSE


def _m(corpus_id: str, spdx: str, restrictions=(), *, source_spdx: str | None = None, policy: str = "include",
       redistribution: str | None = None) -> dict:
    restrictions = sorted(restrictions)
    if redistribution is None:
        redistribution = "permitted-non-commercial" if "-NC" in spdx else "permitted"
    return {"corpus_id": corpus_id, "licences": {
        "class": {"restrictions": restrictions, "spdx": spdx},
        "derived": {"basis": "inherit", "decided_by": "test", "spdx": spdx, "text_path": "LICENSES/DERIVED.txt"},
        "policy": {"licence_policy": policy, "raw_policy": "withhold" if policy == "forbidden" else "include"},
        "raw": [{"source_id": "s", "spdx": source_spdx if source_spdx is not None else spdx}],
        "redistribution": redistribution, "restrictions": restrictions}}  # fmt: skip


def _classes(*manifests: dict) -> dict[str, LicenceClass]:
    return {m["corpus_id"]: licence_class(m) for m in manifests}


# ------------------------------------------------------------------------------------------------ the matrix
@pytest.mark.parametrize(("a", "b"), [
    (_m("survey-runs", "CC-BY-4.0"), _m("survey-agentharm", "CC-BY-4.0", [CLAUSE])),  # restricted use is its own class
    (_m("rope", "MIT"), _m("gpl-source", "GPL-3.0-only")),
    (_m("gpl-source", "GPL-3.0-only"), _m("agpl-source", "AGPL-3.0-only")),  # D-25: each its own class
    (_m("gpl-only", "GPL-3.0-only"), _m("gpl-later", "GPL-3.0-or-later")),  # exact SPDX ids
], ids=["cc-by-vs-restricted", "mit-vs-gpl", "gpl-vs-agpl", "gpl-only-vs-or-later"])  # fmt: skip
def test_different_classes_are_refused_without_the_flag(a, b):
    classes = _classes(a, b)
    with pytest.raises(LicenceClassError) as exc:
        check_licence_classes(classes, allow_mixed=False)
    assert exc.value.code == "release.refused.mixed_licence_classes" and exc.value.exit_code == 4
    assert len(check_licence_classes(classes, allow_mixed=True)) == 2


def test_the_same_class_is_accepted():
    assert check_licence_classes(_classes(_m("rope", "MIT"), _m("agentdyn-a", "MIT")), allow_mixed=False) == [
        LicenceClass("MIT", ())]
    same = _classes(_m("a", "CC-BY-4.0", [CLAUSE, "z clause"]), _m("b", "CC-BY-4.0", ["z clause", CLAUSE]))
    assert len(check_licence_classes(same, allow_mixed=False)) == 1  # restrictions compare sorted


def test_a_non_commercial_class_outside_an_nc_corpus_is_refused():
    with pytest.raises(LicenceClassError) as exc:
        licence_class(_m("stac", "CC-BY-NC-4.0", policy="nc_partition"))
    assert exc.value.code == "release.refused.nc_partition"
    with pytest.raises(LicenceClassError):
        licence_class(_m("plain-nc", "MIT"))  # an -nc corpus needs a non-commercial class
    with pytest.raises(LicenceClassError):
        licence_class(_m("stac-nc", "CC-BY-NC-4.0", policy="include"))  # and the nc_partition policy


def test_an_nc_corpus_is_deposited_alone_even_with_the_flag():
    nc = _m("stac-nc", "CC-BY-NC-4.0", policy="nc_partition")
    assert licence_class(nc) == LicenceClass("CC-BY-NC-4.0", ())
    with pytest.raises(LicenceClassError) as exc:
        check_licence_classes(_classes(nc, _m("rope", "MIT")), allow_mixed=True)
    assert exc.value.code == "release.refused.nc_partition"


def test_copyleft_and_nc_sources_are_never_relicensed():
    with pytest.raises(LicenceClassError):
        licence_class(_m("gpl-source", "MIT", source_spdx="GPL-3.0-only"))
    with pytest.raises(LicenceClassError):
        licence_class(_m("x-nc", "CC-BY-4.0", source_spdx="CC-BY-NC-4.0", policy="nc_partition"))


def test_withhold_and_forbidden_are_refused():
    with pytest.raises(LicenceClassError) as exc:
        licence_class(_m("ciaware", "MIT", policy="forbidden", redistribution="not-permitted"))
    assert exc.value.code == "release.refused.withhold"


def test_a_recorded_class_that_does_not_recompute_is_refused():
    m = _m("a", "MIT", ["x"])
    m["licences"]["class"]["restrictions"] = []
    with pytest.raises(LicenceClassError):
        licence_class(m)


# ------------------------------------------------------------------------------------------------ end to end
def test_mit_and_gpl_corpora_are_refused_together(tmp_path_factory, tmp_path):
    mit = rs.sealed(tmp_path_factory, tmp_path / "c", "mini-mit")
    gpl = rs.sealed(tmp_path_factory, tmp_path / "c", "mini-gpl", "GPL-3.0-only")
    assert rs.manifest(gpl)["licences"]["class"] == {"restrictions": [], "spdx": "GPL-3.0-only"}
    with pytest.raises(LicenceClassError) as exc:
        rs.build([mit, gpl], tmp_path / "out")
    assert exc.value.code == "release.refused.mixed_licence_classes"
    assert not (tmp_path / "out").exists()


def test_gpl_and_agpl_corpora_are_refused_together(tmp_path_factory, tmp_path):
    gpl = rs.sealed(tmp_path_factory, tmp_path / "c", "mini-gpl", "GPL-3.0-only")
    agpl = rs.sealed(tmp_path_factory, tmp_path / "c", "mini-agpl", "AGPL-3.0-only")
    with pytest.raises(LicenceClassError):
        rs.build([gpl, agpl], tmp_path / "out")


def test_an_nc_class_under_a_plain_id_is_refused(tmp_path_factory, tmp_path):
    nc = rs.sealed(tmp_path_factory, tmp_path / "c", "mini-noncommercial", "CC-BY-NC-4.0")
    with pytest.raises(LicenceClassError) as exc:
        rs.build([nc], tmp_path / "out")
    assert exc.value.code == "release.refused.nc_partition"


def test_a_restricted_use_corpus_is_its_own_class(tmp_path_factory, tmp_path):
    plain = rs.sealed(tmp_path_factory, tmp_path / "c", "mini-ccby", "CC-BY-4.0")
    restricted = rs.sealed(tmp_path_factory, tmp_path / "c", "mini-ccby-restricted", "CC-BY-4.0")
    rs.restamp(restricted, rs.add_restriction)
    with pytest.raises(LicenceClassError):
        rs.build([plain, restricted], tmp_path / "out")
    rs.build([restricted], tmp_path / "alone")  # deposited alone, it is fine
    assert json.loads((tmp_path / "alone" / DEPOSIT_METADATA).read_text())["licences"][0]["restrictions"] == [CLAUSE]


def test_the_same_class_from_two_corpora_is_one_deposit(tmp_path_factory, tmp_path):
    a = rs.sealed(tmp_path_factory, tmp_path / "c", "mini-mit")
    b = rs.sealed(tmp_path_factory, tmp_path / "c", "mini-mit-two")
    report = rs.build([b, a], tmp_path / "out")
    assert [c["corpus_id"] for c in report.corpora] == ["mini-mit", "mini-mit-two"]  # sorted, whatever the order given
    dm = json.loads((tmp_path / "out" / DEPOSIT_MANIFEST).read_text())
    assert dm["licence_classes"] == [{"corpora": ["mini-mit", "mini-mit-two"], "restrictions": [], "spdx": "MIT"}]


def test_the_override_is_recorded_in_metadata_and_datasheet_copies(tmp_path_factory, tmp_path):
    mit = rs.sealed(tmp_path_factory, tmp_path / "c", "mini-mit")
    gpl = rs.sealed(tmp_path_factory, tmp_path / "c", "mini-gpl", "GPL-3.0-only")
    report = rs.build([mit, gpl], tmp_path / "out", allow_mixed_licence_classes=True)
    assert report.mixed_licence_classes
    meta = json.loads((tmp_path / "out" / DEPOSIT_METADATA).read_text())
    assert meta["mixed_licence_classes"] == {"allowed": True, "classes": 2, "flag": "--allow-mixed-licence-classes"}
    assert [lic["spdx"] for lic in meta["licences"]] == ["GPL-3.0-only", "MIT"]
    for corpus in (mit, gpl):
        copy = (tmp_path / "out" / f"DATASHEET-{corpus.name}.md").read_bytes()
        original = (corpus / "DATASHEET.md").read_bytes()
        assert copy.startswith(original.rstrip(b"\n")) and b"--allow-mixed-licence-classes" in copy
        assert (corpus / "DATASHEET.md").read_bytes() == original  # the sealed corpus is never modified
    assert json.loads((tmp_path / "out" / DEPOSIT_MANIFEST).read_text())["mixed_licence_classes"] is True


# ------------------------------------------------------------------------------------------------ SPDX families (CB-15)
@pytest.mark.parametrize("source", [
    "GPL-2.0+", "LGPL-2.1+", "GPL-2.0-with-classpath-exception", "GPL-3.0-only WITH GCC-exception-3.1",
    "GPL-3.0-or-later", "GPL-3.0-only", "AGPL-3.0-only", "(MIT AND LGPL-2.1-only)",
    "GPL-2.0-or-later OR MIT",  # fail closed: the guard cannot tell which alternative was elected
])  # fmt: skip
def test_every_copyleft_family_id_is_never_relicensed(source):
    with pytest.raises(LicenceClassError) as exc:
        licence_class(_m("src", "MIT", source_spdx=source))
    assert exc.value.code == "release.refused.licence_class"
    assert licence_class(_m("src", source)) == LicenceClass(source, ())  # inheriting the source licence is fine


@pytest.mark.parametrize("source", ["MIT", "Apache-2.0", "CC-BY-4.0", "LGPLLR"])
def test_permissive_sources_may_be_relicensed(source):
    assert licence_class(_m("src", "MIT", source_spdx=source)) == LicenceClass("MIT", ())


@pytest.mark.parametrize(("spdx", "nc"), [
    ("PolyForm-Noncommercial-1.0.0", True), ("CC-BY-NC-4.0", True), ("CC-BY-NC-SA-4.0", True),
    ("Non-Commercial-Example", True), ("MIT", False), ("Apache-2.0", False), ("CC-BY-4.0", False),
    ("GPL-3.0-or-later", False), ("NCSA", False),
])  # fmt: skip
def test_non_commercial_is_a_family_test(spdx, nc):
    assert LicenceClass(spdx, ()).non_commercial is nc


def test_a_polyform_noncommercial_licence_is_non_commercial():
    spdx = "PolyForm-Noncommercial-1.0.0"
    with pytest.raises(LicenceClassError) as exc:
        licence_class(_m("plain", spdx, redistribution="permitted"))
    assert exc.value.code == "release.refused.nc_partition"
    nc = _m("plain-nc", spdx, policy="nc_partition", redistribution="permitted-non-commercial")
    assert licence_class(nc).non_commercial
    with pytest.raises(LicenceClassError) as exc:
        licence_class(_m("x-nc", "CC-BY-NC-4.0", source_spdx=spdx, policy="nc_partition"))
    assert exc.value.code == "release.refused.licence_class"  # never relicensed, even to another NC licence
    with pytest.raises(LicenceClassError) as exc:
        check_licence_classes(_classes(nc, _m("rope", "MIT")), allow_mixed=True)
    assert exc.value.code == "release.refused.nc_partition"
