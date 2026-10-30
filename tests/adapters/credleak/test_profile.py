"""Profile (with its ``[withhold]`` policy), registry entry, rate exclusions and fixtures of the ``credleak`` family
(docs/architecture D.19.10-D.19.13, D.3; DECISIONS D-260, D-265, D-266)."""

from __future__ import annotations

import hashlib
import json
import tomllib
from importlib import resources

import credleak_support as support

from agentprov.adapters.profiles import load_profile

SRC = support.REPO / "src" / "agentprov" / "adapters" / "credleak"
PROFILE_BYTES = (SRC / "profiles" / "credleak-p15b.profile.toml").read_bytes()


def _policy():
    from agentprov.corpus.withhold import policy_of_profile

    return policy_of_profile(PROFILE_BYTES, profile_id="credleak-p15b", profile_version=2)


def test_profile_pins_licence_import_and_family_schema():
    profile = load_profile("credleak-p15b")
    assert (profile.family, profile.source_id, profile.parts) == ("credleak", "credleak-p15b", ("head",))
    (pin,) = profile.data["source"]["pins"]
    assert (pin["kind"], pin["doi"], pin["record"], pin["version"]) == ("zenodo", "10.5281/zenodo.22737462", 22737462, "v3")
    assert pin["sha256"] == "7e5f7e40b86abfda45a951602188d979a26db9148cd2646e8a17a404c575082a"
    assert (pin["size"], pin["md5"], pin["primary"]) == (11060394, "d25b9b5c27f5f41689c62decb3e20ffc", True)
    assert profile.data["licence"]["spdx"] == "CC-BY-4.0" and profile.data["licence"]["policy"] == "include"
    imp = profile.data["import"]
    assert imp["dialect"] == imp["mapper"] == "credleak.cell" and imp["variants"] == ("v1",)
    import jsonschema

    schema = json.loads((SRC / "family.schema.json").read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    family = tomllib.loads(PROFILE_BYTES.decode("utf-8"))["family"]["credleak"]
    assert list(jsonschema.Draft202012Validator(schema).iter_errors(family)) == []
    jsonschema.Draft202012Validator.check_schema(json.loads((SRC / "ext.schema.json").read_text(encoding="utf-8")))
    from agentprov.adapters.credleak.mapper import JUDGED

    assert tuple(family["judged"]) == JUDGED


def test_ext_members_are_declared(mapped):
    import jsonschema

    schema = json.loads((SRC / "ext.schema.json").read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(schema)
    for runs in mapped.values():
        for m in runs:
            for rec in m.records:
                ext = rec.get("ext", {}).get("credleak")
                if ext is not None:
                    assert list(validator.iter_errors(ext)) == [], (rec["k"], rec["id"])


def test_quirks_name_declared_rules():
    from agentprov.aer.rules import load_catalogue

    rules = set(load_catalogue("credleak", 1).rules)
    for quirk in tomllib.loads(PROFILE_BYTES.decode("utf-8"))["family"]["credleak"]["quirk"]:
        assert quirk["observed"] and set(quirk.get("rules", [])) <= rules, quirk["id"]


def test_the_withhold_policy_is_the_d265_policy():
    policy = _policy()
    assert policy is not None and policy.profile_sha256 == "sha256:" + hashlib.sha256(PROFILE_BYTES).hexdigest()
    assert [(r.id, r.kind, r.scope, r.reason) for r in policy.rules] == [
        ("account-path-home", "pattern", "object", "personal_data"),  # D-605 part 1
        ("account-path-users", "pattern", "object", "personal_data"),
        ("aws-key-shape", "pattern", "object", "secret"),
        ("canary-tag", "pattern", "object", "secret"),
        ("canary-tag-left", "pattern", "object", "secret"),
        ("sk-key-shape", "pattern", "object", "secret"),
    ]
    assert set(policy.scan_rules) >= {"aws-access-token", "anthropic-api-key", "openai-api-key"}


def test_no_fixture_cell_and_no_derived_file_of_a_fixture_hits_the_policy(mapped):
    """D-266: fixtures hold no planted value; D-265: no identifier the family writes trips a rule (so a clean run of a
    withheld cell stays released, D-235)."""
    from agentprov.corpus.withhold import scan_chunks
    from agentprov.sem.engine import dumps_sem

    rules = _policy().rules
    for entry in support.source_entries():
        assert scan_chunks([support.cell_bytes(entry)], rules) == frozenset(), entry["path"]
    for runs in mapped.values():
        for m in runs:
            for data in (m.data, dumps_sem(m.sem), m.prov.prov_json):
                assert scan_chunks([data], rules) == frozenset(), (m.label, m.index)


def test_the_tag_rule_spares_labels_with_the_tag_between_underscores():
    """raw/members.jsonl is released (D-231) and lists the deposit's two collector-log labels, which carry the tag
    between underscores; the rule must not match them, or no corpus of the deposit could pass the chain backstop."""
    from agentprov.corpus.withhold import scan_chunks

    rules = _policy().rules
    tag = "CAN" + "ARY"
    for label in (f"x/{tag}_DETECTED-cloudwatch.csv", f"x/EXTERNAL_{tag}_VALIDITY.md"):
        assert scan_chunks([json.dumps({"label": label}).encode()], rules) == frozenset()
    assert "canary-tag" in scan_chunks([f'{{"v": "{tag}-x"}}'.encode()], rules)
    assert scan_chunks([f'{{"v": "x{tag}_y"}}'.encode()], rules) == {"canary-tag-left"}  # the one-run form of step 15


def test_a_planted_sentinel_is_found_by_the_policy_in_raw_and_derived_bytes():
    from agentprov.corpus.withhold import scan_chunks

    rules = _policy().rules
    label = "p15b-run-data/01-injection-map/T1-file-document/test-model/run__T1__test-model__T1.9__2026.json"
    for kind, rule in (("tag", "canary-tag"), ("aws", "aws-key-shape"), ("sk", "sk-key-shape")):
        data = support.synthetic_cell(output=f"value: {support.sentinel(kind)}")
        assert rule in scan_chunks([data], rules)
        (m,) = support.map_cell(label, data, sem=False, prov=True)
        assert rule in scan_chunks([m.data], rules)  # the AER copies content verbatim: a derived hit escalates


def test_registry_entry_is_supported_lazy_and_cc_by_without_restriction():
    from agentprov.adapters.registry import MAPPERS, READERS, get_source
    from agentprov.adapters.runner import resolve_factory

    reg = get_source("credleak-p15b")
    (part,) = reg.capabilities
    assert part.part == "head" and part.import_status == "supported" and part.target_import_status == "supported"
    assert part.profile == "credleak-p15b" and part.semantics == ("credleak.tools@2",) and part.corpus_id == "credleak-p15b"
    assert reg.licence.spdx == "CC-BY-4.0" and reg.licence.restrictions == () and reg.licence.policy == "include"
    assert resolve_factory(READERS["credleak.cell"]).__name__ == "CredleakCellReader"
    assert resolve_factory(MAPPERS["credleak.cell"]).__name__ == "CredleakMapper"


def test_rate_exclusions_parse():
    doc = tomllib.loads(resources.files("agentprov").joinpath("adapters", "credleak", "rates.toml").read_text("utf-8"))
    assert doc["version"] == 1 and doc["family"] == "credleak"
    for entry in doc["exclusion"]:
        assert set(entry) == {"id", "profiles", "issue_codes", "judgement_origins", "rates", "basis"}
        assert entry["id"].startswith("credleak.rate.") and entry["profiles"] == ["credleak-p15b"] and entry["basis"]
        assert entry["issue_codes"] or entry["judgement_origins"], entry["id"]  # stats refuses an empty selector
    from agentprov.stats.exclusions import parse_exclusions  # the loader the seal and stats call

    data = resources.files("agentprov").joinpath("adapters", "credleak", "rates.toml").read_bytes()
    assert [e.id for e in parse_exclusions(data, "credleak")] == ["credleak.rate.invocation_error"]


def test_fixture_source_records_match_the_committed_bytes():
    for entry in support.source_entries():
        data = support.cell_bytes(entry)
        assert hashlib.sha256(data).hexdigest() == entry["sha256"] and len(data) == entry["size"]
        assert entry["label"].startswith(support.PREFIX) and entry["doi"] == "10.5281/zenodo.22737462"
    licence = support.REPO / "tests" / "fixtures" / "LICENSES" / "credleak-p15b-ATTRIBUTION.txt"
    assert "CC-BY-4.0" in licence.read_text(encoding="utf-8")
