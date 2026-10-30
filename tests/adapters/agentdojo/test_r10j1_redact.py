"""Regeneration-batch item 105 (R-10j-1; D-476, D-510 (A)): the TraceLogger and DRIFT builds apply a profile's
``pipeline_name`` redaction. The logged name is rewritten wherever the AER holds it, including inside
``artifacts[0].origin.path``, and identity reads the redacted directory label. A synthetic log under a made-up account
directory; the profile is a test variant of agentdojo-upstream that declares the rule."""

from __future__ import annotations

import json
import re

from agentdojo_support import C274885, PROFILE_PATH, REPO_URL, map_bytes, new_log, path_of

from agentprov.adapters.agentdojo.redact import RULE, parse_redact_rules, redact_value
from agentprov.adapters.profiles import parse_profile
from agentprov.adapters.semantics_profiles import load_semantics_profile
from agentprov.adapters.types import Origin
from agentprov.aer.reader import load_aer_bytes
from agentprov.aer.rules import RuleRegistry
from agentprov.prov.engine import derive
from agentprov.sem.engine import annotate
from agentprov.testing import golden

ACCOUNT = "zq7synthetic"
NAME = f"_ceph_ssd_students_{ACCOUNT}_qwen3_5-4B"
RULE_TABLE = '''
[[family.agentdojo.redact]]
id = "ceph_home"
scope = "pipeline_name"
pattern = '^_ceph_ssd_students_(?P<span>[^_/]+)_(?P<leaf>qwen3_5(?:-[0-9]+B)?)$'
replacement = "_ceph_ssd_students_{span12}_{leaf}"
note = "test variant: a munged cluster home path"
'''


def _profile():
    text = PROFILE_PATH.read_text(encoding="utf-8")
    assert "rules = { aer = 1, agentdojo = 2 }" in text
    text = text.replace("rules = { aer = 1, agentdojo = 2 }", "rules = { aer = 1, agentdojo = 2, rescont = 1 }") + RULE_TABLE
    return parse_profile(text.encode("utf-8"), source="test-variant")


def _map():
    doc = new_log(pipeline_name=NAME)
    path = path_of(doc)
    assert f"runs/{NAME}/" in path
    raw = json.dumps(doc, indent=4).encode("utf-8")
    return map_bytes(raw, path, profile=_profile(), origin=Origin.git(REPO_URL, C274885, path, golden.git_blob_sha1(raw)))


def _leaks(data: bytes) -> list[str]:
    return [form for form in (ACCOUNT, NAME, f"~1{NAME}~1") if form.encode() in data]


def _label() -> str:
    rules = parse_redact_rules(_profile().data["family"]["agentdojo"]["redact"], "t")
    return redact_value(rules, "pipeline_name", NAME, salt=_profile().id)[0]


def test_the_logged_name_and_the_origin_path_are_redacted():
    m = _map()
    report = m.validate()
    assert report.ok, [(f.code, f.pointer) for f in report.errors]
    label = _label()
    assert re.fullmatch(r"_ceph_ssd_students_[0-9a-f]{12}_qwen3_5-4B", label)
    assert m.header["ext"]["agentdojo"]["pipeline_name"] == label
    assert f"runs/{label}/" in m.header["artifacts"][0]["origin"]["path"]
    assert _leaks(m.data) == []
    assert "rescont.value_redacted" in m.codes
    assert m.header["ns"]["rescont"].startswith("https://")
    assert any(RULE in str(r) for r in m.header.get("rule", ()))


def test_identity_reads_the_redacted_directory_and_name():
    """Both the directory facet and the logged name are redacted before identity.resolve, so they still agree."""
    assert "agentdojo.pipeline_name_mismatch" not in _map().codes


def test_no_account_reaches_sem_or_prov_and_a_remap_is_byte_identical():
    m = _map()
    aer = load_aer_bytes(m.data)
    sem = annotate(aer, load_semantics_profile("agentdojo.suites", 2))
    prov = derive(aer, [sem], registry=RuleRegistry.default(),
                  sem_profiles={("agentdojo.suites", 2): load_semantics_profile("agentdojo.suites", 2)})
    assert _leaks(json.dumps([sem.header, *sem.records, sem.seal]).encode()) == [] and _leaks(prov.prov_json) == []
    assert _map().data == m.data


def test_a_profile_without_a_rule_is_unchanged():
    doc = new_log(pipeline_name=NAME)
    path = path_of(doc)
    raw = json.dumps(doc, indent=4).encode("utf-8")
    m = map_bytes(raw, path, origin=Origin.git(REPO_URL, C274885, path, golden.git_blob_sha1(raw)))
    assert m.header["ext"]["agentdojo"]["pipeline_name"] == NAME and "rescont.value_redacted" not in m.codes


def test_a_rule_whose_scope_the_build_does_not_apply_is_refused():
    """Bug pass NF-12: the TraceLogger build applies ``pipeline_name`` only, so a ``model_id`` rule would be ignored
    silently; the profile is refused instead (fail closed)."""
    import pytest

    from agentprov.adapters.agentdojo.profile import family_table
    from agentprov.errors import ProfileError

    text = PROFILE_PATH.read_text(encoding="utf-8").replace(
        "rules = { aer = 1, agentdojo = 2 }", "rules = { aer = 1, agentdojo = 2, rescont = 1 }")
    text += RULE_TABLE.replace('scope = "pipeline_name"', 'scope = "model_id"')
    with pytest.raises(ProfileError, match="does not apply"):
        family_table(parse_profile(text.encode("utf-8"), source="test-variant"))
    assert family_table(_profile()) is not None
