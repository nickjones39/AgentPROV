"""The ``inspect.whistlebench@1`` semantics profile (D-601 addendum, user decision 2026-10-21; docs/architecture D.9.14,
C.14.1-C.14.4; H.2.5).

The profile reads only the AER: every tool is fail-closed (``inspect.untabulated_tool@1``, class I) and no judgement gets
an outcome (the scorer code is not available at the pin). Checked over synthetic WhistleBench-band AERs and the committed
pinned log: the SEM validates in release mode (tier 3), cites only the inspect catalogue at the version the AER declares
(one catalogue version per corpus), and PROV derived with it passes tier 4. Nothing here prints log content (R-42).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import inspect_support as support
import pytest

from agentprov.adapters.inspect.semantics import build_profile
from agentprov.adapters.profiles import load_profile
from agentprov.adapters.registry import get_source
from agentprov.adapters.semantics_profiles import load_semantics_profile
from agentprov.aer.reader import AerDocument, load_aer_bytes
from agentprov.aer.rules import RuleRegistry, load_catalogue
from agentprov.sem.engine import annotate, dumps_sem
from agentprov.sem.profiles import SemanticsProfileError, profile_digest
from agentprov.sem.types import SemanticsProfile
from agentprov.sem.validate import validate_sem_document

SEMANTICS = support.REPO / "src" / "agentprov" / "adapters" / "inspect" / "semantics" / "inspect.whistlebench-1"
FIXTURE_DIR = support.REPO / "tests" / "fixtures" / "inspect" / "whistlebench"
RULE = "inspect.untabulated_tool@1"


def profile() -> SemanticsProfile:
    return load_semantics_profile("inspect.whistlebench", 1)


def _synthetic(tmp_path: Path, sid: str = "s1") -> AerDocument:
    imported = support.import_log(support.build_eval(support.synthetic_header("0.3.130"),
                                                     {f"{sid}_epoch_1.json": support.basic_sample(sid)}),
                                  tmp_path, profile=load_profile("whistlebench"))
    (unit,) = imported.units
    assert not unit.outcome.degenerate
    return load_aer_bytes(unit.data)


@pytest.fixture(scope="module")
def committed(tmp_path_factory: pytest.TempPathFactory) -> list[AerDocument]:
    source = FIXTURE_DIR / "SOURCE.json"
    if not source.is_file():
        pytest.skip("the whistlebench fixture is absent")
    (entry,) = json.loads(source.read_bytes())
    imported = support.import_log((FIXTURE_DIR / entry["file"]).read_bytes(), tmp_path_factory.mktemp("wb-sem"),
                                  path=entry["path"], profile=load_profile("whistlebench"))
    return [load_aer_bytes(u.data) for u in imported.units]


def test_the_profile_is_found_by_convention_and_cites_the_inspect_catalogue_version_2():
    prof = profile()
    assert isinstance(prof, SemanticsProfile)
    assert (prof.id, prof.version, dict(prof.rules), dict(prof.ns), prof.taint_policy) == \
        ("inspect.whistlebench", 1, {"inspect": 2}, {}, None)
    files = {p.name: p.read_bytes() for p in SEMANTICS.iterdir() if p.is_file()}
    assert set(files) == {"tables.toml"} and prof.sha256 == profile_digest(files)
    assert files["tables.toml"].count(b"EMPTY ON PURPOSE") == 2  # no tool and no scorer is tabulated
    assert load_catalogue("inspect").version == 2


def test_the_aer_declares_the_catalogue_version_it_cites(tmp_path):
    (part,) = get_source("whistlebench").capabilities
    assert part.semantics == ("inspect.whistlebench@2",)  # version 1 stays shipped, as recorded (D-601 addendum 2)
    doc = _synthetic(tmp_path)
    assert doc.header["rules"]["inspect"] == profile().rules["inspect"]  # H.2.5: one catalogue version per corpus


def test_every_tool_is_fail_closed_and_no_outcome_is_claimed(tmp_path, committed):
    for doc in [_synthetic(tmp_path), *committed]:
        anns = list(profile().annotate(doc))
        roles = {a.target: a.value for a in anns if a.type == "role"}
        integrity = {a.target: a.value for a in anns if a.type == "integrity"}
        assert {a.type for a in anns} <= {"role", "integrity"}  # no outcome, channel, marker or author
        for te in doc.of_kind("tool_execution"):
            assert roles.pop(te["id"]) == ["unknown"]
        for msg in doc.of_kind("message"):
            for i, part in enumerate(msg["parts"]):
                target = f"{msg['id']}#{i}"
                if part["t"] == "tool_call":
                    assert roles.pop(target) == ["unknown"]
                elif part["t"] == "tool_result":
                    assert integrity.pop(target) == "unknown"
        assert roles == {} and integrity == {}
        assert doc.of_kind("judgement")  # the judgements exist; the profile reads no claim from them
        assert {r for a in anns for r in a.rule} == ({RULE} if anns else set())
        assert all(a.ev == "I" for a in anns)


def test_the_cited_rule_is_class_i_active_and_in_the_declared_catalogue_version():
    entry = load_catalogue("inspect", 2).get(RULE)
    assert entry is not None and entry.citable and entry.status == "active" and entry.cls == "I"
    source = (support.REPO / "src/agentprov/adapters/inspect/semantics/whistlebench.py").read_text(encoding="utf-8")
    import re
    assert set(re.findall(r'"(inspect\.[a-z_]+@[0-9]+)"', source)) == {
        RULE, "inspect.tool_table@1", "inspect.unknown_tool@1", "inspect.scorer_letter_table@1"}  # @2's (addendum 2)


def test_the_sem_validates_in_release_mode_and_prov_passes_tier_4(tmp_path, committed):
    from agentprov.prov.engine import derive
    from agentprov.validate import validate_prov

    prof = profile()
    for doc in [_synthetic(tmp_path), *committed[:10]]:
        sem = annotate(doc, prof)
        assert json.loads(dumps_sem(sem).split(b"\n", 1)[0])["rules"] == {"inspect": 2}
        report = validate_sem_document(sem, doc, catalogues=RuleRegistry.default(), mode="release", profile=prof)
        assert report.ok, [(f.code, f.pointer) for f in report.errors]
        result = derive(doc, [sem], sem_profiles={(prof.id, prof.version): prof})
        prov = validate_prov(result.prov_json, doc, sems=[sem])
        assert prov.ok, [(o.id, sorted(o.codes())) for o in prov.outcomes if o.status == "fail"]


def test_annotate_is_deterministic(tmp_path):
    doc = _synthetic(tmp_path)
    again = _synthetic(tmp_path / "again")  # an independent mapping of the same log
    assert dumps_sem(annotate(doc, profile())) == dumps_sem(annotate(again, profile()))
    assert list(profile().annotate(doc)) == list(profile().annotate(doc))


@pytest.mark.parametrize("tables", [
    b'[tool_policy]\nknown_tools = ["write_file"]\nrole = ["unknown"]\nintegrity = "unknown"\n',
    b'[tool_policy]\nknown_tools = []\nrole = ["unknown"]\nintegrity = "trusted"\n',
    b'[tool_policy]\nknown_tools = []\nrole = ["unknown"]\nintegrity = "unknown"\n[[scorer]]\njudgement = "refusal"\n',
])
def test_a_table_that_claims_more_than_fail_closed_is_refused(tables: bytes):
    with pytest.raises(SemanticsProfileError):
        build_profile("inspect.whistlebench", 1, {"tables.toml": tables}, "0" * 64)


def test_an_unknown_version_is_refused():
    data: dict[str, Any] = {"tables.toml": (SEMANTICS / "tables.toml").read_bytes()}
    with pytest.raises(SemanticsProfileError):
        build_profile("inspect.whistlebench", 2, data, "0" * 64)
