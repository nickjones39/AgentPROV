"""``v1.k14`` and ``v1.k14.incomplete`` as import variants of the TraceLogger mapper (docs/architecture D.6.5-D.6.7,
D.6.12; phase 10).

Synthetic logs are written the way AgentDojo >= 0.1.30 writes them (content as one text block, the three K14 version
fields, ``placeholder_args`` on every call); the real ``head`` fixtures (``tests/fixtures/agentdojo/head/``, byte-identical
blobs of ``ethz-spylab/agentdojo@089ed468``, MIT) are loaded programmatically and never printed (R-42).
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
from typing import Any

import pytest
from agentdojo_support import SYSTEM, base_log, log_bytes, map_bytes, map_log, profile_with

from agentprov.adapters.agentdojo.dialect import classify
from agentprov.adapters.profiles import load_profile
from agentprov.adapters.types import Origin
from agentprov.testing import golden

REPO_URL = "https://github.com/ethz-spylab/agentdojo"
HEAD = "089ed468cf3ed0322acc66b0211f26d9d90dbf60"
REPO = Path(__file__).resolve().parents[3]
FIXTURES = REPO / "tests" / "fixtures" / "agentdojo" / "head"
HEAD_DIGESTS = Path(__file__).resolve().parent / "head_aer_digests.json"
REGEN = "AGENTPROV_REGEN_AGENTDOJO_AER"
DEFAULT_SHA = "a021a92b114c523250d0e52b18adc0aa7b41db7c7628b579b2b8db1df9361837"


def _blocks(text: str | None) -> list[dict[str, Any]]:
    return [{"type": "text", "content": text}]


def v1_log(**overrides: Any) -> dict[str, Any]:
    """The synthetic ``base_log`` as AgentDojo 0.1.35 writes it (D.6.2 K14; content blocks; placeholder_args)."""
    doc = copy.deepcopy(base_log())
    for message in doc["messages"]:
        if message["role"] in ("system", "user", "tool"):
            message["content"] = _blocks(message["content"])
        elif message["content"] is not None:
            message["content"] = _blocks(message["content"])
        for call in message.get("tool_calls") or ():
            call["placeholder_args"] = None
        if message["role"] == "tool":
            message["tool_call"]["placeholder_args"] = None
    doc["messages"][-1]["tool_calls"] = []
    doc.update(benchmark_version="v1.2.1", evaluation_timestamp="2025-07-25 11:07:03", agentdojo_package_version="unknown")
    doc.update(overrides)
    return doc


def _ok(m: Any) -> None:
    report = m.validate()
    assert report.ok and report.passed, [(f.code, f.pointer) for f in report.errors]


def test_v1_k14_maps_with_the_version_fields():
    m = map_log(v1_log())
    _ok(m)
    assert m.header["dialect"]["variant"] == "v1.k14" and not m.outcome.degenerate
    bench = m.get("bench")
    assert bench["version"] == "v1.2.1" and bench["evf"]["/version"] == "O" and bench["src"] == [{"a": "a0", "p": "/benchmark_version"}]
    assert bench["unk"] == {"/code": "not_recorded"} and "code" not in bench  # "unknown" is a sentinel (C.7.3)
    assert "ext" not in bench  # upstream: the label is the suite version (version_label_semantics = suite_version)
    run = m.get("run")
    assert run["t"]["start_naive"] == "2025-07-25T11:07:03" and run["t"]["raw"]["start"] == "2025-07-25 11:07:03"
    assert run["unk"]["/t/start"] == "ambiguous" and run["rule"] == ["agentdojo.naive_local_timestamp@1#/t/start"]
    te = m.get("te0")
    assert te["args_effective"] == te["args"] and "agentdojo.args_are_effective@1#/args_effective" in te["rule"]
    assert m.get("m3")["parts"][0]["text"] == "done"  # the tool output wrapped in one text block (D.10.4a)
    assert "agentdojo.args_are_effective@1" in m.get("m2")["rule"]
    assert m.get("m2")["ext"]["agentdojo"]["placeholder_args"] == {"1": None}


def test_v1_k14_package_version_is_a_distribution_version_not_code():
    m = map_log(v1_log(agentdojo_package_version="0.1.35"))
    _ok(m)
    bench = m.get("bench")
    assert bench["code"] == {"dist": "agentdojo", "dist_version": "0.1.35"} and bench["unk"] == {"/code/commit": "not_recorded"}


def test_v1_k14_incomplete_variant():
    doc = v1_log()
    for key in ("utility", "security", "duration"):
        del doc[key]
    assert classify(doc).variant == "v1.k14.incomplete"
    m = map_log(doc)
    _ok(m)
    assert m.header["dialect"]["variant"] == "v1.k14.incomplete" and not m.of_kind("judgement")
    assert m.issues("incomplete_run")[0]["ids"] == ["run"]
    run = m.get("run")
    assert "dur_s" not in run["t"] and run["t"]["start_naive"] == "2025-07-25T11:07:03"
    assert run["unk"] == {"/status": "not_recorded", "/t/end": "not_recorded", "/t/start": "ambiguous"}
    assert m.get("te0")["args_effective"] == m.get("te0")["args"]  # the quirk applies to the incomplete variant too


def test_system_prompt_variant_label():
    """D.6.6 system row (D.6.12 item 9): the pinned digest labels the system message of a v1 log; an unknown text gives
    the info issue. Since D-207 (regen-batch item 17) the default variant applies to v0.k11 logs too."""
    text = "You are a helpful assistant."
    digest = hashlib.sha256(text.encode()).hexdigest()
    profile = profile_with({DEFAULT_SHA: digest})
    m = map_log(v1_log(), profile=profile)
    _ok(m)
    m0 = m.get("m0")
    assert m0["ext"]["agentdojo"]["system_prompt_variant"] == "agentdojo_default"
    assert m0["evf"]["/ext/agentdojo/system_prompt_variant"] == "D"
    assert "agentdojo.system_prompt_variant_digest@1#/ext/agentdojo/system_prompt_variant" in m0["rule"]
    unknown = map_log(v1_log())  # the shipped digest is the real default prompt's, not this text's
    _ok(unknown)
    assert "ext" not in unknown.get("m0")
    assert unknown.issues("agentdojo.system_prompt_unrecognised")[0]["ids"] == ["m0"]
    v0 = map_log(base_log(), profile=profile)  # the same text in a v0.k11 log (D-207)
    _ok(v0)
    assert v0.get("m0")["ext"]["agentdojo"]["system_prompt_variant"] == "agentdojo_default"
    assert v0.get("m0")["evf"]["/ext/agentdojo/system_prompt_variant"] == "D"
    v0_unknown = map_log(base_log())
    assert "ext" not in v0_unknown.get("m0")
    assert v0_unknown.issues("agentdojo.system_prompt_unrecognised")[0]["ids"] == ["m0"]


SPOT_SHA = "2954962b7689663e8083fd5872aa5b1368437f16cc16cec7c0121d603a13eb03"
SPOT_JUNE_SHA = "d9524c738d6b735b847035fc33208a91252282826ef6e25050ffb8d1a78426b5"


@pytest.mark.parametrize(("pinned", "label"), [(SPOT_SHA, "agentdojo_default_spotlighting"),
                                               (SPOT_JUNE_SHA, "agentdojo_default_spotlighting_2024_06")])
def test_spotlighting_variants_apply_to_their_run_directory_only(pinned: str, label: str):
    """D-207: the two spotlighting_with_delimiting texts label v0.k11 logs of that run directory only; the same text
    elsewhere is unrecognised, and a v1.k14 log of that directory is outside both variants' selector."""
    profile = profile_with({pinned: hashlib.sha256(SYSTEM.encode()).hexdigest()})
    spot = "gpt-4o-2024-05-13-spotlighting_with_delimiting"
    inside = map_log(base_log(pipeline_name=spot), pipeline_dir=spot, profile=profile)
    _ok(inside)
    assert inside.get("m0")["ext"]["agentdojo"]["system_prompt_variant"] == label
    outside = map_log(base_log(), profile=profile)
    assert "ext" not in outside.get("m0") and outside.issues("agentdojo.system_prompt_unrecognised")
    v1 = map_log(v1_log(pipeline_name=spot), pipeline_dir=spot, profile=profile)
    assert "ext" not in v1.get("m0") and v1.issues("agentdojo.system_prompt_unrecognised")


def test_local_model_tag_count():
    """D.6.6 local-model row: tags counted in declared pipelines only; more tags than calls is an issue."""
    doc = v1_log(pipeline_name="local")
    doc["messages"][2]["content"] = _blocks("<function=send_money>{}</function> <function=get_iban>{}</function>")
    doc["messages"][4]["content"] = _blocks("<function=get_balance>{}</function>")
    m = map_log(doc, pipeline_dir="Meta-SecAlign-70B")
    _ok(m)
    assert m.get("m2")["ext"]["agentdojo"]["local_model_tag_count"] == 2
    assert m.get("m4")["ext"]["agentdojo"]["local_model_tag_count"] == 1
    assert sorted(i for issue in m.issues("agentdojo.local_parse_drop_possible") for i in issue["ids"]) == ["m2", "m4"]
    other = map_log(doc, pipeline_dir="gpt-4o-2024-05-13")
    assert "local_model_tag_count" not in (other.get("m2").get("ext") or {}).get("agentdojo", {})
    assert not other.issues("agentdojo.local_parse_drop_possible")


def test_structural_twins_cite_the_unverified_timestamp_rule():
    profile = profile_with({'  { commit = "089ed468cf3ed0322acc66b0211f26d9d90dbf60", applies = { variant = ["v1.k14", "v1.k14.incomplete"] }, '
                            'note = "the head pin, in the 0.1.30+ family that writes v1.k14" },\n': ""})
    m = map_log(v1_log(), profile=profile)
    _ok(m)
    assert m.get("run")["rule"] == ["agentdojo.naive_local_timestamp_unverified@1#/t/start"]
    shipped = map_log(v1_log())  # the head pin is verified for v1.k14: the D rule, while the June-2024-only rules are twins
    assert shipped.get("run")["rule"] == ["agentdojo.naive_local_timestamp@1#/t/start"]
    assert shipped.get("mc0")["ev"] == shipped.get("te0")["ev"] == "I"
    assert "agentdojo.args_are_effective@1#/args_effective" in shipped.get("te0")["rule"]  # cited at 0.1.35 (a75aba76)


def test_v1_mapping_is_deterministic():
    raw = log_bytes(v1_log())
    path = "runs/gpt-4o-2024-05-13/banking/user_task_1/important_instructions/injection_task_2.json"
    assert map_bytes(raw, path).data == map_bytes(raw, path).data


# ------------------------------------------------------------------------------------------------ real head fixtures
def _fixtures() -> list[dict[str, Any]]:
    if not (FIXTURES / "SOURCE.json").is_file():
        pytest.skip("the head fixtures are not present")
    return list(json.loads((FIXTURES / "SOURCE.json").read_bytes()))


def _map_fixture(entry: dict[str, Any]) -> Any:
    raw = (FIXTURES / entry["sample_file"]).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == entry["sha256"] and golden.git_blob_sha1(raw) == entry["git_blob_sha1"]
    origin = Origin.git(REPO_URL, HEAD, entry["original_path"], entry["git_blob_sha1"])
    return map_bytes(raw, entry["original_path"], origin=origin)


def test_head_fixtures_cover_every_variant_and_follow_k41():
    entries = _fixtures()
    variants = set()
    for entry in entries:
        assert entry["commit_or_revision"] == HEAD and entry["licence_class"] == "permissive" and entry["synthetic"] is False
        assert entry["sample_file"] == entry["original_path"] and entry["original_path"].startswith("runs/")
        variants.add(classify(json.loads((FIXTURES / entry["sample_file"]).read_bytes())).variant)
    assert variants == {"v0.k11", "v1.k14", "v1.k14.incomplete"}
    on_disk = {p.relative_to(FIXTURES).as_posix() for p in FIXTURES.rglob("*") if p.is_file() and p.name != "SOURCE.json"}
    assert on_disk == {e["sample_file"] for e in entries}


def test_head_fixtures_map_validate_and_keep_their_aer_bytes():
    """D.6.10 items 1 and 5 for the head part: every real head fixture maps, validates in release mode, carries the
    expected D.6.12 facts, and its AER bytes are pinned (regenerate with ``AGENTPROV_REGEN_AGENTDOJO_AER=1``)."""
    produced: dict[str, str] = {}
    profile = load_profile("agentdojo-upstream")
    for entry in _fixtures():
        m = _map_fixture(entry)
        _ok(m)
        assert not m.outcome.degenerate and m.header["profile"] == profile.header()
        assert m.header["artifacts"][0]["prov_primary"] == "native"
        variant = m.header["dialect"]["variant"]
        if variant.startswith("v1.k14"):
            assert m.get("m0")["ext"]["agentdojo"]["system_prompt_variant"] == "agentdojo_default"
            assert m.get("bench")["version"] == "v1.2.1" and m.get("bench")["unk"]["/code"] == "not_recorded"
        else:
            assert m.get("bench")["unk"] == {"/code": "not_recorded", "/version": "not_recorded"}
            m0 = m.get("m0")
            if m0 is not None and m0.get("role") == "system":  # D-207: every v0.k11 system text is a pinned variant
                spot = "-spotlighting_with_delimiting/" in entry["original_path"]
                expected = {"agentdojo_default_spotlighting", "agentdojo_default_spotlighting_2024_06"} if spot \
                    else {"agentdojo_default"}
                assert m0["ext"]["agentdojo"]["system_prompt_variant"] in expected, entry["original_path"]
        assert not m.issues("agentdojo.system_prompt_unrecognised"), entry["original_path"]
        produced[entry["original_path"]] = golden.sha256_hex(m.data)
    if os.environ.get(REGEN):
        HEAD_DIGESTS.write_text(json.dumps(dict(sorted(produced.items())), indent=2) + "\n", encoding="utf-8")
    expected = json.loads(HEAD_DIGESTS.read_text(encoding="utf-8"))
    assert sorted(k for k, v in produced.items() if expected.get(k) != v) == []
    assert set(expected) == set(produced)


def test_head_fixture_with_dropped_local_calls_and_the_incomplete_run():
    for entry in _fixtures():
        m = _map_fixture(entry)
        if m.header["dialect"]["variant"] == "v1.k14.incomplete":
            assert m.issues("incomplete_run") and not m.of_kind("judgement")
            assert m.records[-1]["k"] != "judgement"
        if entry["original_path"].endswith("slack/user_task_17/none/none.json"):
            assert m.issues("agentdojo.local_parse_drop_possible")
