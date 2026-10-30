"""The phase-10f WhistleBench profile (D-150; phase-10e cards §3.2, D-144, D-147; docs/architecture D.9).

One complete pinned log is the real fixture (``tests/fixtures/inspect/whistlebench/``, written by
``tools/agentdojo/phase10f_fixtures.py``; K.4.1(5) oversize entry in ``tests/FIXTURES.json``, D-360). The logs hold
scenarios of corporate misconduct and the agents' e-mails, and are data: nothing here prints their content (R-42).
"""

from __future__ import annotations

import hashlib
import json
import tomllib
from pathlib import Path

import inspect_support as support
import pytest

from agentprov.adapters.profiles import load_profile
from agentprov.adapters.registry import get_source
from agentprov.aer.rules import RuleRegistry, load_catalogue
from agentprov.aer.validate import AerValidator
from agentprov.testing import golden

FIXTURE_DIR = support.REPO / "tests" / "fixtures" / "inspect" / "whistlebench"
COMMIT = "9c27637c3cf6dfb2c0d5801c7f3d91358cb587bc"
PROFILE_FILE = support.REPO / "src/agentprov/adapters/inspect/profiles/whistlebench.profile.toml"


def _toml() -> dict:
    return tomllib.loads(PROFILE_FILE.read_text(encoding="utf-8"))


def _entry() -> dict:
    source = FIXTURE_DIR / "SOURCE.json"
    if not source.is_file():
        pytest.skip("the whistlebench fixture is absent")
    (entry,) = json.loads(source.read_bytes())
    return entry


@pytest.fixture(scope="module")
def imported(tmp_path_factory: pytest.TempPathFactory) -> support.Imported:
    entry = _entry()
    data = (FIXTURE_DIR / entry["file"]).read_bytes()
    return support.import_log(data, tmp_path_factory.mktemp("whistlebench-raw"), path=entry["path"],
                              profile=load_profile("whistlebench"))


def test_profile_pin_licence_and_import_table():
    profile = load_profile("whistlebench")
    data = _toml()
    (pin,) = [p for p in data["source"]["pins"] if p.get("primary") is True]
    assert pin["kind"] == "git" and pin["commit"] == COMMIT and pin["tree"] == "final_runs"
    assert (pin["expected_files"], pin["expected_bytes"]) == (223, 523183391)
    assert data["licence"]["spdx"] == "MIT" and data["licence"]["policy"] == "include" and data["licence"]["attribution"]
    imp = data["import"]
    assert imp["dialect"] == imp["mapper"] == "inspect.eval" and imp["variants"] == ["v2"]
    family = data["family"]["inspect"]
    assert family["benchmark"] == "whistlebench" and family["no_attack"] is True
    assert family["producer_band"]["inspect_ai"] == ["0.3.130", "0.3.134.dev31+geb46eef8"] and family["log_versions"] == [2]
    assert profile.version == 2  # D-601 (D-31: version 1 under profiles/archive/)


def test_family_table_conforms_to_the_closed_schema():
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads((support.REPO / "src/agentprov/adapters/inspect/family.schema.json").read_bytes())
    jsonschema.validate(_toml()["family"]["inspect"], schema)


def test_quirk_rules_exist():
    for quirk in _toml()["family"]["inspect"].get("quirk", ()):
        for rule in quirk.get("rules", ()):
            entry = load_catalogue("inspect").get(rule)
            assert entry is not None and entry.citable, (quirk["id"], rule)


def test_registry_part_is_sealed_with_its_own_corpus_and_the_whistlebench_semantics():
    registration = get_source("whistlebench")
    (part,) = registration.capabilities
    assert part.profile == "whistlebench" and part.corpus_id == "whistlebench" and part.part == "final-runs"
    assert part.import_status == "supported" and part.target_import_status == "supported"  # D-830, after the wave-2 seal
    assert part.caveat is not None and part.caveat.startswith(
        "full pinned snapshot imported through agentprov import in wave 2 and sealed as whistlebench 0.1.0 ("
    )
    assert [s.corpus_id for s in part.sealed] == ["whistlebench"]
    assert part.semantics == ("inspect.whistlebench@2",)  # D-601 addenda
    assert registration.family == "inspect" and registration.licence.spdx == "MIT"


def test_the_fixture_is_the_pinned_blob_with_its_licence():
    entry = _entry()
    raw = (FIXTURE_DIR / entry["file"]).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == entry["sha256"] and golden.git_blob_sha1(raw) == entry["git_blob"]
    assert entry["commit"] == COMMIT and entry["size"] == len(raw) == 1420537 and entry["licence_class"] == "permissive"
    text = (support.REPO / "tests" / "fixtures" / "LICENSES" / "whistlebench-MIT.txt").read_text(encoding="utf-8")
    assert "MIT" in text[:200] or "Permission is hereby granted" in text


def test_every_sample_imports_seals_and_validates_in_release_mode(imported: support.Imported):
    profile = load_profile("whistlebench")
    assert len(imported.units) == 50 and imported.register == []
    for unit in imported.units:
        assert not unit.outcome.degenerate
        validator = AerValidator(store=imported.store, catalogues=RuleRegistry.default(), mode="release",
                                 profile_digests={(profile.id, profile.version): profile.sha256})
        for line in unit.data.splitlines(keepends=True):
            validator.feed(line)
        report = validator.finish()
        assert report.ok and report.passed, [(f.code, f.pointer) for f in report.errors]
        assert unit.header["profile"] == profile.header()


def test_no_attack_and_the_judge_runs_in_scorer_scopes(imported: support.Imported):
    for unit in imported.units:
        task = unit.header["task"]
        assert task.get("attack_id") is None
        judge_calls = [r for r in unit.records if r["k"] == "call" and r.get("by") == "judge"]
        assert all(r.get("in") for r in judge_calls)


def test_mapping_is_deterministic(imported: support.Imported, tmp_path: Path):
    entry = _entry()
    again = support.import_log((FIXTURE_DIR / entry["file"]).read_bytes(), tmp_path / "raw", path=entry["path"],
                               profile=load_profile("whistlebench"))
    assert [u.data for u in again.units] == [u.data for u in imported.units]
