"""The phase-10f SEAgent profile (D-150, D-156; phase-10e cards §3.1, D-144; docs/architecture D.4, D.5.4, D.6).

The logs are members of the Zenodo deposit zip (record 23218779). The runner does not yet import deposit archives whose
members are run logs, and the TraceLogger mapper reads the layout from the origin's ``/path``, which a ``member`` origin
does not have (routing D-156). Until then the real fixtures (``tests/fixtures/seagent/``, byte-identical members written
by ``tools/agentdojo/phase10f_fixtures.py``) are mapped under a development-only ``local`` origin whose path is the member
label, and their records are validated in development mode (release mode refuses a ``local`` origin by design). One test
checks the mapper half of D-156: under a ``member`` origin every fixture seals and validates in release mode. The logs
hold prompt-injection payloads: nothing here prints them.
"""

from __future__ import annotations

import hashlib
import json
import zlib

import pytest
from agentdojo_support import REPO

from agentprov.adapters.agentdojo import census, citation
from agentprov.adapters.agentdojo.dialect import TraceLoggerReader
from agentprov.adapters.agentdojo.identity import resolve
from agentprov.adapters.agentdojo.mapper import TraceLoggerMapper
from agentprov.adapters.agentdojo.profile import check_against_schema, family_schema, family_table
from agentprov.adapters.code_verification import TWIN_SUFFIX
from agentprov.adapters.profiles import load_profile
from agentprov.adapters.registry import get_source
from agentprov.adapters.runner import aer_bytes, map_unit
from agentprov.adapters.types import ArtefactRef, ExecutionUnit, Origin
from agentprov.aer.rules import RuleRegistry, load_catalogue
from agentprov.aer.validate import validate_records
from agentprov.ingest.limits import IngestLimits

PROFILE = "seagent-agentdojo"
FIXTURES = REPO / "tests" / "fixtures" / "seagent"
PREFIX = "seagent-ae/artifact/results/raw_data/agentdojo/"
ZIP_SHA256 = "e15a8f0fc869151ad3c8fab23bbb37384315745669b0aab7a5a0760c825764bd"
RUN = PREFIX + "{kind}/{arm}/{run}"


def _entries() -> list[dict]:
    source = FIXTURES / "SOURCE.json"
    if not source.is_file():
        pytest.skip("the SEAgent fixtures are absent")
    return list(json.loads(source.read_bytes()))


def _raw(entry: dict) -> bytes:
    raw = (FIXTURES / entry["path"]).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == entry["sha256"] and len(raw) == entry["size"]
    assert f"{zlib.crc32(raw) & 0xFFFFFFFF:08x}" == entry["crc32"]
    return raw


def _map(raw: bytes, label: str, origin: Origin):
    reader, mapper, profile = TraceLoggerReader(), TraceLoggerMapper(), load_profile(PROFILE)
    limits = IngestLimits()
    sniff = reader.sniff(raw, label=label, limits=limits)
    assert sniff.match, sniff.reasons
    artefact = ArtefactRef("a0", hashlib.sha256(raw).hexdigest(), len(raw), "application/json", origin, "primary",
                           mapper.prov_primary(sniff.flags))  # type: ignore[arg-type]
    item = next(reader.parse(raw, artefact, limits=limits))
    return map_unit(ExecutionUnit(item), mapper, profile)


def _d_rules_cited_at_d(records: list[dict]) -> list[str]:
    out = set()
    for record in records:
        for ref in record.get("rule", ()) or ():
            rid = str(ref).split("#", 1)[0]
            namespace = rid.split(".", 1)[0]
            if namespace not in citation.NAMESPACES or rid in citation.INDEPENDENT:
                continue
            entry = load_catalogue(namespace).get(rid)
            if entry is not None and entry.cls == "D":
                out.add(rid)
    return sorted(out)


# ------------------------------------------------------------------------------------------------ profile and registry
def test_profile_pin_licence_and_import_table():
    profile = load_profile(PROFILE)
    data = profile.data
    (pin,) = [p for p in data["source"]["pins"] if p.get("primary") is True]
    assert pin["kind"] == "zenodo" and pin["doi"] == "10.5281/zenodo.23218779" and pin["file"] == "seagent-acsac2026-ae-v2.zip"
    assert (pin["sha256"], pin["md5"], pin["size"]) == (ZIP_SHA256, "37d4b444e908d7164db8bbc891d720d9", 237707785)
    assert data["licence"]["spdx"] == "CC-BY-4.0" and data["licence"]["policy"] == "include" and data["licence"]["attribution"]
    imp = data["import"]
    assert tuple(imp["variants"]) == ("v1.k14",) and imp["dialect"] == imp["mapper"] == "agentdojo.tracelogger"
    assert dict(imp["rules"]) == {"aer": 1, "agentdojo": 2}
    assert profile.version == 2 and profile.parts == ("head",)  # D-591 (version 1 archived, D-31)


def test_registry_part_is_sealed_with_its_own_corpus():
    registration = get_source(PROFILE)
    (part,) = registration.capabilities
    assert part.part == "head" and part.profile == PROFILE and part.corpus_id == PROFILE
    assert part.import_status == "supported" and part.target_import_status == "supported"  # D-830, after the wave-2 seal
    assert part.caveat is not None and part.caveat.startswith(
        f"full pinned snapshot imported through agentprov import in wave 2 and sealed as {PROFILE} 0.1.0 ("
    )
    assert [s.corpus_id for s in part.sealed] == [PROFILE]
    assert part.semantics == ("agentdojo.suites@2",) and registration.licence.spdx == "CC-BY-4.0"  # D-31 and item 1
    assert registration.licence.attribution == tuple(load_profile(PROFILE).data["licence"]["attribution"])


def test_family_part_conforms_to_the_closed_schema_both_checkers():
    jsonschema = pytest.importorskip("jsonschema")
    table = family_table(load_profile(PROFILE))
    jsonschema.validate(table.data, family_schema())
    assert check_against_schema(table.data, family_schema()) == []


def test_every_quirk_rule_exists_and_every_observed_key_has_a_census_function():
    table = family_table(load_profile(PROFILE))
    for quirk in table.quirks:
        for rule in quirk.rules:
            entry = load_catalogue(rule.split(".", 1)[0]).get(rule)
            assert entry is not None and entry.citable, (quirk.id, rule)
    assert [p for p in census.compare(table, "head", {}) if "no census function" in p] == []


def test_no_harness_code_is_verified():
    table = family_table(load_profile(PROFILE))
    assert table.verified_code == () and table.harness["code_identity"] == "range"


@pytest.mark.parametrize(("run_dir", "pipeline", "model", "defences"), [
    (RUN.format(kind="security", arm="baseline", run="20251223124514-banking"), "deepseek-v3-250324", "deepseek-v3-250324", ()),
    (RUN.format(kind="security", arm="baseline", run="20251223124325-slack"), "deepseek-v3", "deepseek-v3", ()),
    (RUN.format(kind="security", arm="pvagent", run="20250729231343-banking"), "deepseek-v3-250324-seagent_mcp",
     "deepseek-v3-250324", ("pvagent",)),
    (RUN.format(kind="security", arm="seagent", run="20251212183115-banking"), "deepseek-v3-250324-seagent_mcp",
     "deepseek-v3-250324", ("seagent-initial",)),
    (RUN.format(kind="security", arm="seagent-RF", run="20251223114741-travel"), "deepseek-v3-seagent_mcp",
     "deepseek-v3", ("seagent-refined",)),
    (RUN.format(kind="perf", arm="agentspec", run="banking-260324194110"), "deepseek-v3-250324-agentspec",
     "deepseek-v3-250324", ("agentspec",)),
])
def test_identity_is_keyed_by_the_run_directory(run_dir, pipeline, model, defences):
    """D-104: the defence is a property of the arm; pvagent, seagent and seagent-RF share the pipeline name."""
    table = family_table(load_profile(PROFILE))
    found = resolve(table.identity, {"model_dir": run_dir}, pipeline, table.table_rows)
    assert (found.model, found.defences) == (model, defences)


# ------------------------------------------------------------------------------------------------ real fixtures
def test_fixtures_are_provenanced_and_licensed():
    entries = _entries()
    on_disk = {p.relative_to(FIXTURES).as_posix() for p in FIXTURES.rglob("*") if p.is_file()} - {"SOURCE.json"}
    assert on_disk == {e["path"] for e in entries}
    criteria = set()
    for e in entries:
        _raw(e)
        assert e["label"] == PREFIX + e["path"] and e["container_sha256"] == ZIP_SHA256
        assert e["doi"] == "10.5281/zenodo.23218779" and e["licence_class"] == "permissive" and e["criteria"]
        criteria.update(e["criteria"])
    assert {"benign", "prepass", "guard_warning", "no_tool_calls_key"} <= criteria
    assert {c for c in criteria if c.startswith("attacked:")} == {
        "attacked:baseline", "attacked:agentspec", "attacked:pvagent", "attacked:seagent", "attacked:seagent-RF"}
    text = (REPO / "tests" / "fixtures" / "LICENSES" / "SEAgent-CC-BY-4.0.txt").read_text(encoding="utf-8")
    assert "Attribution 4.0 International" in text[:600]


def test_real_fixtures_map_validate_and_cite_only_twins():
    """D.6.10 items 1 and 5 and D-24 on the real logs, under the scratch-only local origin (D-156)."""
    profile = load_profile(PROFILE)
    for entry in _entries():
        outcome = _map(_raw(entry), entry["label"], Origin.local(entry["label"]))
        assert not outcome.degenerate and outcome.records[0]["profile"] == profile.header()
        assert outcome.records[0]["dialect"]["variant"] == "v1.k14"
        report = validate_records(outcome.records, store=None, catalogues=RuleRegistry.default(), mode="dev")
        errors = [(f.code, f.pointer) for f in report.findings if f.severity == "error"
                  and not f.pointer.endswith("/origin/kind") and f.code != "aer.order.envelope"]
        assert errors == [], entry["path"]
        codes = {str(i["code"]) for i in outcome.issues}
        assert not codes & {"identity_unresolved", "agentdojo.undeclared_quirk", "agentdojo.path_field_mismatch"}
        assert _d_rules_cited_at_d(outcome.records) == [], entry["path"]
        assert any(TWIN_SUFFIX + "@" in str(ref) for r in outcome.records for ref in (r.get("rule", ()) or ()))
        if "guard_warning" in entry["criteria"]:  # the guard's warning is never attributed to the user
            assert "unattributed_additional_user_message" in codes
        if "no_tool_calls_key" in entry["criteria"]:  # PVAgent's call-less assistant messages: results stay unlinked
            assert {"agentdojo.unknown_message_shape", "orphan_tool_result"} <= codes


def test_member_origins_seal_and_validate_in_release_mode_d156():
    """D-156 part 2 (phase 10f F2; the deferrals session's member-origin interface, D-204): every real fixture under the
    ``member`` origin the expand stage writes (container sha256, label = the member's full name, method, crc32, size)
    maps, seals and validates in release mode. The layout locator reads the origin's ``/label`` (a member has no
    ``/path``), and the mapping is the one the scratch ``local`` origin gives, apart from the origin itself. The runner's
    archive-input trial import is the deferrals session's (part A); this is the mapper half."""
    from agentprov.aer.reader import load_aer_bytes

    for entry in _entries():
        raw = _raw(entry)
        origin = Origin.member(ZIP_SHA256, entry["label"], 8, entry["crc32"], entry["size"])
        outcome = _map(raw, entry["label"], origin)
        assert not outcome.degenerate, entry["path"]
        data, _info = aer_bytes(outcome)  # before D-156 part 2: AerWriteError aer.locator.dangling
        doc = load_aer_bytes(data)
        report = validate_records([*doc.records, doc.seal], store=None, catalogues=RuleRegistry.default(), mode="release")
        assert [(f.code, f.pointer) for f in report.findings if f.severity == "error"] == [], entry["path"]
        header = doc.header
        assert header["artifacts"][0]["origin"]["kind"] == "member"
        assert {"a": "a0", "o": "/label"} in header["src"] and {"a": "a0", "o": "/path"} not in header["src"]
        local = _map(raw, entry["label"], Origin.local(entry["label"]))
        assert outcome.records[0]["task"] == local.records[0]["task"], entry["path"]  # the identity read is the same
        # every other record is the local mapping's, the identity locator reading /label where a path origin has /path
        as_path = json.loads(json.dumps(outcome.records[1:]).replace('"o": "/label"', '"o": "/path"'))
        assert as_path == local.records[1:], entry["path"]