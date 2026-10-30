"""The ``dtap.trajectory`` reader (docs/architecture D.16.1, D.16.2): path grammar, file classes, sniff outcomes,
discovery and the per-unit auxiliary plan (runner items R1/R2)."""

from __future__ import annotations

import json

import dtap_support as support
import pytest

from agentprov.adapters.dtap.dialect import (
    FLAG_DEBUG,
    FLAG_JUDGE_ONLY,
    LFS_HEADER,
    DtapTrajectoryReader,
    config_path,
    file_class,
    parse_path,
    state_form,
)
from agentprov.adapters.runner.importer import _AuxListing
from agentprov.adapters.types import CandidateArtefact, Origin
from agentprov.ingest.limits import IngestLimits

LIMITS = IngestLimits()


def test_path_grammar_benign_subcategory_malicious_and_prefix():
    f = parse_path("openaisdk/gpt-5.2/code/benign/math/57/20260220_133459.json")
    assert f is not None and (f.framework, f.model, f.domain, f.split, f.subcategory, f.task_dir) == (
        "openaisdk", "gpt-5.2", "code", "benign", "math", "57")
    assert f.task_path == "benign/math/57" and f.file_stem == "20260220_133459" and f.threat is None
    g = parse_path("openclaw/gpt-5.2/telecom/malicious/indirect/privacy_leak_email/007/20260221_052816.json")
    assert g is not None and (g.threat, g.risk_category, g.task_path) == (
        "indirect", "privacy_leak_email", "malicious/indirect/privacy_leak_email/007")
    # a local origin carries the whole path: the grammar is matched at the framework segment
    h = parse_path("/home/u/x/claudesdk/claude-opus-4-6/macos/benign/1/20260425_035217.json")
    assert h is not None and h.relpath.startswith("claudesdk/")
    for bad in ("openaisdk/gpt/code/other/1/a.json", "openaisdk/gpt/code/malicious/sideways/r/1/a.json", "x/y.json"):
        assert parse_path(bad) is None


def test_config_path_rule_maps_direct_prompt_and_control_to_direct():
    assert config_path(parse_path(support.F["F09"])) == "finance/malicious/direct/churning/9/config.yaml"  # type: ignore[arg-type]
    assert config_path(parse_path(support.F["F10"])) == "medical/malicious/direct/excessive-test/014/config.yaml"  # type: ignore[arg-type]
    assert config_path(parse_path(support.F["F01"])) == "code/benign/math/57/config.yaml"  # type: ignore[arg-type]


@pytest.mark.parametrize(("name", "cls"), [
    ("20260220_133459.json", "timestamp"), ("20260327_005714(1).json", "copy"), ("20260322_232404_3.json", "rerun"),
    ("trajectory.json", "trajectory"), ("partial_trajectory.json", "partial"), ("judge_result.json", "judge"),
    ("judge_result(1).json", "judge_copy"), ("red_teaming_agent_20260212_201310.json", "red_teaming"),
    ("notes.json", "other_json"), ("screenshot_001.png", "other"),
])
def test_file_classes(name, cls):
    assert file_class(name) == cls


def test_state_forms_never_evaluate():
    assert state_form({"a": 1}) == "object" and state_form([1]) == "array" and state_form(None) == "null"
    assert state_form("{'type': 'text'}") == "python_repr" and state_form("[{'a': 1}]") == "python_repr"
    assert state_form("{not json") == "brace_text" and state_form('{"a": 1}') == "json_text"
    assert state_form("plain") == "text" and state_form(3) == "integer"


def test_sniff_outcomes_of_every_d162_row():
    reader = DtapTrajectoryReader()
    runs = support.runs_files()
    ok = reader.sniff(runs[support.F["F12"]], label="", limits=LIMITS)
    assert ok.match and ok.variant == "v1" and FLAG_DEBUG in ok.flags
    judge = reader.sniff(runs[support.F["X02"]], label="", limits=LIMITS)
    assert judge.match and FLAG_JUDGE_ONLY in judge.flags
    pointer = reader.sniff(runs[support.F["F21"]], label="", limits=LIMITS)
    assert not pointer.match and pointer.reasons == ("dtap.lfs_pointer",) and runs[support.F["F21"]].startswith(LFS_HEADER)
    synthetic = reader.sniff(runs[support.F["F17"]], label="", limits=LIMITS)
    assert not synthetic.match and synthetic.reasons == ("dtap.synthetic",)
    red = reader.sniff(json.dumps({"task_info": {}, "attack_config": {}, "attack_result": {}, "attack_trajectory": []}).encode(),
                       label="", limits=LIMITS)
    assert not red.match and red.reasons == ("dtap.red_teaming_log",)
    broken = reader.sniff(b'{"task_info": ', label="", limits=LIMITS)
    assert not broken.match and broken.reasons[0].startswith("ingest.")
    assert reader.register_detail(("dtap.synthetic",)) == "dtap.synthetic"
    assert reader.register_detail(("dtap.sniff.keys",)) is None and reader.register_detail(("ingest.json.syntax",)) is None


def test_synthetic_is_not_an_execution():
    """D-29 item 1: a synthetic trajectory is valid JSON of another kind: the runner registers it (detail dtap.synthetic)."""
    from agentprov.adapters.runner import NotOfDialect, map_artefact_total

    data = support.runs_files()[support.F["F17"]]
    with pytest.raises(NotOfDialect) as info:
        map_artefact_total(data, Origin.local("/x/" + support.F["F17"]), profile_id=support.PROFILE)
    assert info.value.detail == "dtap.synthetic"


def test_lfs_pointer_is_registered():
    from agentprov.adapters.runner import NotOfDialect, map_artefact_total

    data = support.runs_files()[support.F["F21"]]
    with pytest.raises(NotOfDialect) as info:
        map_artefact_total(data, Origin.local("/x/" + support.F["F21"]), profile_id=support.PROFILE)
    assert info.value.detail == "dtap.lfs_pointer"


class _Tree:
    def __init__(self, labels):
        self.labels = labels

    def walk(self):
        return iter(CandidateArtefact(label, 1, Origin.local("/x/" + label)) for label in self.labels)

    def open(self, label, *, max_bytes):  # pragma: no cover - discovery never opens
        raise AssertionError


def test_discovery_yields_trajectories_and_judge_only_judges_with_copies_after_plain_files():
    from agentprov.adapters.profiles import load_profile

    d = "openaisdk/gpt-5.1/legal/malicious/direct_prompt/fabricated_evidence/20"
    labels = [f"{d}/20260327_005714(1).json", f"{d}/20260327_005714.json", f"{d}/judge_result.json", f"{d}/judge_result(1).json",
              "openaisdk/gpt-5.2/research/malicious/direct/Biosecurity_Risks/42/judge_result.json",
              "openaisdk/gpt-5.1/telecom/malicious/direct/x/007/red_teaming_agent_1.json",
              "openaisdk/gpt-5.1/telecom/malicious/direct/x/007/judge_result.json", "README.md", ".gitattributes",
              "openaisdk/gpt-5.1/macos/benign/3/screenshots/screenshot_001.png", "openaisdk/gpt-5.1/macos/benign/3/20260101_000000.json"]
    chosen = [c.label for c in DtapTrajectoryReader().iter_artefacts(_Tree(labels), load_profile(support.PROFILE))]
    assert chosen == [
        f"{d}/20260327_005714.json", f"{d}/20260327_005714(1).json",
        "openaisdk/gpt-5.1/macos/benign/3/20260101_000000.json",
        "openaisdk/gpt-5.1/telecom/malicious/direct/x/007/judge_result.json",  # only a red-teaming log beside it
        "openaisdk/gpt-5.2/research/malicious/direct/Biosecurity_Risks/42/judge_result.json",
    ]


def test_auxiliary_plan_names_judge_copy_attempts_and_configuration():
    runs, tasks = support.runs_files(), support.tasks_files()
    listing = _AuxListing(runs, {"tasks": list(tasks)})
    reader = DtapTrajectoryReader()
    plan = reader.auxiliary_for(support.F["F20a"], listing)
    d = support.F["F20a"].rsplit("/", 1)[0]
    assert plan["judge"] == f"{d}/judge_result.json" and plan["attempt:0"] == support.F["F20b"]
    assert plan["config"] == "tasks:telecom/malicious/indirect/credential_takeover/011/config.yaml"
    copies = reader.auxiliary_for(support.F["X04"], listing)
    assert copies["copy:judge"].endswith("judge_result(1).json") and copies["attempt:0"].endswith("(1).json")
    assert "config" not in reader.auxiliary_for(support.F["F15"], listing)  # no configuration at the path
    assert reader.auxiliary_for(support.F["X02"], listing) == {}  # a judge-only primary has no auxiliary


def test_parse_yields_one_item_with_the_whole_file_locator():
    from agentprov.adapters.types import ArtefactRef

    data = support.runs_files()[support.F["F01"]]
    ref = ArtefactRef("a0", "0" * 64, len(data), "application/json", Origin.local("/x/" + support.F["F01"]))
    items = list(DtapTrajectoryReader().parse(data, ref, limits=LIMITS))
    assert len(items) == 1 and items[0].locator.key() == {"p": ""} and set(items[0].value) == {"task_info", "traj_info", "trajectory"}
