"""D-780: the building commit in corpus manifests (``corpus.buildstep``; HL H.2.7, H.8.4(5)).

Unit tests of the step rules and of the tracker that merges a process's record into the manifest it writes; the writer
(stages the process wrote, a manifest without a build step untouched); the manifest schema and validator (the optional key,
old manifests unchanged, ``agentprov-corpus/0.1`` frozen); an import, a derive and a recompute through the product path
with an injected commit (the commit and its history, the stages each step wrote, determinism across worker counts, a
dry run with no differences for a corpus rebuilt at the same commit, the drift notice that says where to recompute);
sealing (both commits, the dirty refusal, the absent reason, the datasheet line). The CLI helper that reads git is tested
in ``tests/cli/test_gitinfo.py``.
"""

from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path
from typing import Any

import derive_support as ds
import import_support as support  # noqa: E402
import pytest
import seal_support as ss

from agentprov.adapters.runner.importer import LocalTree, import_source
from agentprov.cli import gitinfo
from agentprov.cli.main import main
from agentprov.corpus import buildstep as bs
from agentprov.corpus import manifest as mf
from agentprov.corpus.package import PackageRefusedError, seal
from agentprov.corpus.writer import CorpusWriter, CorpusWriterError

X = "a" * 40
Y = "c" * 40
Z = "d" * 40
DIGEST = "sha256:" + "e" * 64


def step(command: str = "import", commit: str = X, clean: bool = True) -> bs.BuildStep:
    return bs.BuildStep(command, "0.1.0", git_commit=commit, git_tree_clean=clean)


def absent(command: str = "import") -> bs.BuildStep:
    return bs.BuildStep(command, "0.1.0", git_commit_absent_reason="not_a_source_checkout", distributions_sha256=DIGEST)


# ================================================================================================ the step rules
def test_a_step_is_a_commit_with_its_cleanliness_or_an_absent_reason_with_a_digest_never_both():
    assert step().identity() == {"agentprov_version": "0.1.0", "command": "import", "git_commit": X, "git_tree_clean": True}
    assert absent().identity() == {"agentprov_version": "0.1.0", "command": "import",
                                   "git_commit_absent_reason": "not_a_source_checkout", "distributions_sha256": DIGEST}
    for bad in (
        dict(command="import", agentprov_version="0.1.0"),
        dict(command="import", agentprov_version="0.1.0", git_commit=X),
        dict(command="import", agentprov_version="0.1.0", git_commit="unknown", git_tree_clean=True),
        dict(command="import", agentprov_version="0.1.0", git_commit=X.upper(), git_tree_clean=True),
        dict(command="import", agentprov_version="0.1.0", git_commit=X, git_tree_clean=True,
             git_commit_absent_reason="git_failed", distributions_sha256=DIGEST),
        dict(command="import", agentprov_version="0.1.0", git_commit_absent_reason="somewhere", distributions_sha256=DIGEST),
        dict(command="import", agentprov_version="0.1.0", git_commit_absent_reason="git_failed"),
        dict(command="seal", agentprov_version="0.1.0", git_commit=X, git_tree_clean=True),
        dict(command="import", agentprov_version="", git_commit=X, git_tree_clean=True),
    ):
        with pytest.raises(bs.BuildStepError):
            bs.BuildStep(**bad)


def test_a_record_lists_its_stages_sorted_without_repeats():
    assert step().record(["validation", "aer", "aer", "prov"])["stages"] == ["aer", "prov", "validation"]
    assert step().record([])["stages"] == []


def test_parse_steps_accepts_none_and_valid_lists_and_refuses_the_rest():
    assert bs.parse_steps(None) == []
    good = [step().record(["aer"]), step("derive", Y).record(["prov"])]
    assert bs.parse_steps(good) == good
    for bad in ("x", [1], [{**good[0], "stages": ["prov", "aer"]}], [{**good[0], "stages": ["bogus"]}],
                [{**good[0], "extra": 1}], [{k: v for k, v in good[0].items() if k != "stages"}]):
        with pytest.raises(bs.BuildStepError):
            bs.parse_steps(bad)


def test_describe_says_plainly_when_nothing_is_recorded():
    assert bs.describe_steps([]) == "building commit not recorded"
    text = bs.describe_steps([step().record(["aer", "sem"]), absent("derive").record(["prov"])])
    assert f"import at commit {X} wrote aer, sem" in text
    assert "derive at no git checkout (not_a_source_checkout; agentprov 0.1.0; distributions " + DIGEST in text


# ================================================================================================ the tracker
def test_the_tracker_replaces_its_own_entry_on_every_manifest_write():
    tracker = bs.StepTracker(step())
    tracker.note("aer")
    first = tracker.apply({"agentprov_version": "0.1.0"}, None)
    tracker.note("prov")
    second = tracker.apply({"agentprov_version": "0.1.0"}, first["build_steps"])
    assert first["build_steps"] == [step().record(["aer"])]
    assert second["build_steps"] == [step().record(["aer", "prov"])]  # once, with the stages written so far
    assert second["git_commit"] == X and second["git_tree_clean"] is True and "git_commit_absent_reason" not in second


def test_a_resumed_corpus_at_the_same_commit_adopts_its_step_and_another_commit_adds_one():
    earlier = [step().record(["aer", "sem"])]
    same = bs.StepTracker(step())
    same.note("prov")
    assert same.apply({}, earlier)["build_steps"] == [step().record(["aer", "prov", "sem"])]
    other = bs.StepTracker(step(commit=Y))
    other.note("prov")
    assert other.apply({}, earlier)["build_steps"] == [*earlier, step(commit=Y).record(["prov"])]


def test_a_derivation_hands_over_its_sources_steps_and_a_step_of_the_same_process_is_still_added():
    source = [step("recompute", Y).record(["aer", "prov"])]
    tracker = bs.StepTracker(step("recompute", Y))
    tracker.plan(["prov", "validation"])
    out = tracker.apply({"build_steps": source}, None)
    assert out["build_steps"] == [*source, step("recompute", Y).record(["prov", "validation"])]
    # a later write of the same process (the early working manifest is read back) does not add it twice
    again = tracker.apply({"build_steps": out["build_steps"]}, None)
    assert again["build_steps"] == out["build_steps"]
    assert tracker.apply({"build_steps": source}, None)["build_steps"] == out["build_steps"]


def test_the_commit_of_a_source_is_replaced_by_this_process_and_an_absent_reason_replaces_a_commit():
    out = bs.StepTracker(absent("derive")).apply({"git_commit": X, "git_tree_clean": True}, None)
    assert "git_commit" not in out and "git_tree_clean" not in out
    assert out["git_commit_absent_reason"] == "not_a_source_checkout"
    assert out["build_steps"][0]["distributions_sha256"] == DIGEST


def test_the_tracker_refuses_unknown_stages_and_a_malformed_history():
    with pytest.raises(bs.BuildStepError):
        bs.StepTracker(step()).plan(["aer", "nonsense"])
    with pytest.raises(bs.BuildStepError):
        bs.StepTracker(step()).apply({"build_steps": [{"command": "import"}]}, None)


# ================================================================================================ the writer
EX = "ex_" + "a" * 26


def test_the_writer_merges_the_commit_and_the_stages_it_wrote_into_the_manifest_only(tmp_path):
    with CorpusWriter(tmp_path / "c", build_step=step()) as writer:
        writer.write_aer(EX, b"{}\n")
        writer.write_document(writer.layout.manifest, {"producer": {"agentprov_version": "0.1.0"}})
        assert writer.read_document(writer.layout.manifest)["producer"]["build_steps"] == [step().record(["aer"])]
        writer.write_sem("agentdojo.suites@2", EX, b"{}\n")
        writer.write_prov("agentprov-prov/0.1", EX, b"{}\n")
        writer.write_prov("adprov-v2.3-compat", EX, b"{}\n")
        writer.add_validation(EX, {"verdict": "pass"})
        writer.write_document(writer.layout.manifest, {"producer": {"agentprov_version": "0.1.0"}})
        producer = writer.read_document(writer.layout.manifest)["producer"]
        assert producer["build_steps"] == [step().record(["aer", "compat", "prov", "sem", "validation"])]
        assert producer["git_commit"] == X and producer["git_tree_clean"] is True
        writer.write_document(writer.layout.derivation, {"producer": {}})  # only the manifest is touched
        assert writer.read_document(writer.layout.derivation) == {"producer": {}}


def test_the_writer_records_expand_only_when_it_expanded_something(tmp_path):
    with CorpusWriter(tmp_path / "c", build_step=step()) as writer:
        writer._note_stage("expand", False)
        assert writer._builds.written == set()


def test_a_writer_without_a_step_writes_the_manifest_as_given(tmp_path):
    with CorpusWriter(tmp_path / "c") as writer:
        writer.write_aer(EX, b"{}\n")
        writer.write_document(writer.layout.manifest, {"producer": {"agentprov_version": "0.1.0"}})
        assert writer.read_document(writer.layout.manifest) == {"producer": {"agentprov_version": "0.1.0"}}


def test_a_malformed_history_is_an_error_not_a_silent_reset(tmp_path):
    with pytest.raises(CorpusWriterError), CorpusWriter(tmp_path / "c", build_step=step()) as writer:
        writer.write_document(writer.layout.manifest, {"producer": {"build_steps": [{"command": "x"}]}})
    with pytest.raises(CorpusWriterError), CorpusWriter(tmp_path / "c2", build_step=step()) as writer:
        writer.write_document(writer.layout.manifest, {"producer": {}})
        data = json.loads(writer.layout.manifest.read_text())
        data["producer"]["build_steps"] = "not a list"  # the working manifest on disk is damaged
        writer.layout.manifest.write_text(json.dumps(data))
        writer.write_document(writer.layout.manifest, {"producer": {}})


# ================================================================================================ manifest and schema
@pytest.fixture(scope="module")
def sealed_manifest(tmp_path_factory) -> dict[str, Any]:
    root = ss.working_corpus(tmp_path_factory, tmp_path_factory.mktemp("manifest") / "mini")
    seal(root, corpus_version="0.1.0", inputs=ss.inputs())
    return json.loads((root / "corpus.json").read_text("utf-8"))


def test_a_manifest_built_without_the_key_still_validates_unchanged(sealed_manifest):
    assert "build_steps" not in sealed_manifest["producer"]
    assert mf.validate_manifest(sealed_manifest) == []


def test_the_key_is_optional_and_valid_in_corpus_0_2_and_checked(sealed_manifest):
    m = copy.deepcopy(sealed_manifest)
    m["producer"]["build_steps"] = [step().record(["aer"]), absent("derive").record(["prov"])]
    m["content_digest"] = mf.content_digest(m)
    assert [i for i in mf.validate_manifest(m) if "build_steps" in str(i)] == []
    bad = copy.deepcopy(m)
    bad["producer"]["build_steps"][0]["git_commit_absent_reason"] = "git_failed"  # a commit and a reason together
    assert any("build_steps/0" in str(i) for i in mf.validate_manifest(bad))
    worse = copy.deepcopy(m)
    worse["producer"]["build_steps"][1]["stages"] = ["not-a-stage"]
    assert mf.validate_manifest(worse)


def test_corpus_0_1_stays_frozen_and_has_no_build_steps(sealed_manifest):
    shape = mf.MANIFESTS["agentprov-corpus/0.1"].schema()["properties"]["producer"]["properties"]
    assert "build_steps" not in shape
    current = mf.MANIFESTS[mf.FORMAT].schema()["properties"]["producer"]
    assert "build_steps" in current["properties"] and "build_steps" not in current.get("required", [])
    assert mf.schema_bytes("agentprov-corpus/0.1") == mf.load_published_schema("agentprov-corpus/0.1")


# ================================================================================================ import, derive, recompute
def _import(tmp: Path, name: str, build: bs.BuildStep | None, **kwargs: Any) -> Path:
    tree_root = tmp / f"{name}-input"
    support.agentdojo_tree(tree_root, count=2)
    final = tmp / name
    kwargs.setdefault("in_process", True)
    pin = {"commit": support.C274885, "kind": "git", "role": "2024-06"}
    with CorpusWriter(final, build_step=build) as writer:
        import_source("agentdojo", LocalTree(tree_root), corpus=writer, part="2024-06",
                      pin_check=support.vouch(tree_root), pin=pin, **kwargs)
    return final


@pytest.fixture(scope="module")
def built(tmp_path_factory) -> Path:
    return _import(tmp_path_factory.mktemp("built"), "src", step())


def manifest_of(root: Path) -> dict[str, Any]:
    return json.loads((ds.partial(root) / "corpus.json").read_text("utf-8"))


def stage_names(root: Path) -> set[str]:
    return {s["stage"] for s in json.loads((ds.partial(root) / "derivation.json").read_text())["stages"]}


def cli(capsys, *argv: str) -> tuple[int, dict[str, Any]]:
    capsys.readouterr()
    code = main([*argv, "--json", "--progress", "off"])
    lines = capsys.readouterr().out.splitlines()
    return code, (json.loads(lines[-1]) if lines else {})


@pytest.fixture(autouse=True)
def _home(monkeypatch, tmp_path_factory) -> None:
    monkeypatch.setenv("AGENTPROV_HOME", str(tmp_path_factory.mktemp("home")))
    monkeypatch.delenv("AGENTPROV_PROGRESS", raising=False)


def at_commit(monkeypatch, commit: str, clean: bool = True) -> None:
    monkeypatch.setattr(gitinfo, "_facts", lambda: (commit, clean, None, None))


def test_an_import_records_its_commit_and_the_stages_it_wrote(built):
    producer = manifest_of(built)["producer"]
    assert producer["git_commit"] == X and producer["git_tree_clean"] is True
    (record,) = producer["build_steps"]
    assert record == step().record(stage_names(built))  # every stage of derivation.json, from the writer's own record
    assert {"aer", "prov", "validation"} <= set(record["stages"])


def test_an_import_without_a_step_records_nothing_and_still_validates(tmp_path):
    root = _import(tmp_path, "plain", None)
    assert "build_steps" not in manifest_of(root)["producer"] and "git_commit" not in manifest_of(root)["producer"]


def test_a_derive_that_rebuilds_only_the_later_stages_shows_the_aer_comes_from_the_import(capsys, monkeypatch, built, tmp_path):
    at_commit(monkeypatch, Y)
    out = tmp_path / "derived"
    code, summary = cli(capsys, "recompute", "--corpus", str(built), "--out", str(out), "--stages", "sem,prov,validation",
                        "--in-process")
    assert code == 0, summary
    producer = manifest_of(out)["producer"]
    first, second = producer["build_steps"]
    assert first == step().record(stage_names(built))  # the import, unchanged: it wrote the AER and everything else
    assert second == step("recompute", Y).record(["prov", "sem", "validation"])  # no "aer": that layer is the import's
    assert producer["git_commit"] == Y  # the top-level pair is the writer's


def test_a_derive_of_a_complete_corpus_wrote_no_stage_and_says_so(capsys, monkeypatch, built, tmp_path):
    at_commit(monkeypatch, Y)
    out = tmp_path / "derived"
    code, summary = cli(capsys, "derive", "--corpus", str(built), "--out", str(out), "--in-process")
    assert code == 0, summary
    first, second = manifest_of(out)["producer"]["build_steps"]
    assert first == step().record(stage_names(built)) and second == step("derive", Y).record([])


def test_a_recompute_that_remaps_says_it_rewrote_the_aer_too(capsys, monkeypatch, built, tmp_path):
    at_commit(monkeypatch, Z)
    out = tmp_path / "remapped"
    code, summary = cli(capsys, "recompute", "--corpus", str(built), "--out", str(out), "--in-process")
    assert code == 0, summary
    steps = manifest_of(out)["producer"]["build_steps"]
    assert [s["command"] for s in steps] == ["import", "recompute"] and steps[1]["git_commit"] == Z
    assert {"aer", "sem", "prov", "validation"} <= set(steps[1]["stages"])


def test_the_history_survives_two_derivations_in_a_row(capsys, monkeypatch, built, tmp_path):
    at_commit(monkeypatch, Y)
    first = tmp_path / "one"
    assert cli(capsys, "derive", "--corpus", str(built), "--out", str(first), "--in-process")[0] == 0
    at_commit(monkeypatch, Z)
    second = tmp_path / "two"
    assert cli(capsys, "derive", "--corpus", str(first), "--out", str(second), "--in-process")[0] == 0
    producer = manifest_of(second)["producer"]
    assert [(s["command"], s["git_commit"]) for s in producer["build_steps"]] == [
        ("import", X), ("derive", Y), ("derive", Z)]


def test_the_manifest_is_byte_identical_across_worker_counts_at_one_commit(capsys, monkeypatch, built, tmp_path):
    at_commit(monkeypatch, Y)
    a, b = tmp_path / "w1", tmp_path / "w2"
    assert cli(capsys, "recompute", "--corpus", str(built), "--out", str(a), "--jobs", "1")[0] == 0
    assert cli(capsys, "recompute", "--corpus", str(built), "--out", str(b), "--jobs", "2")[0] == 0
    assert (ds.partial(a) / "corpus.json").read_bytes() == (ds.partial(b) / "corpus.json").read_bytes()
    assert ds.tree_bytes(ds.partial(a)) == ds.tree_bytes(ds.partial(b))


def test_a_dry_run_reports_no_difference_for_a_corpus_rebuilt_at_the_same_commit(capsys, monkeypatch, built, tmp_path):
    at_commit(monkeypatch, Y)
    rebuilt = tmp_path / "rebuilt"
    assert cli(capsys, "recompute", "--corpus", str(built), "--out", str(rebuilt), "--in-process")[0] == 0
    code, summary = cli(capsys, "recompute", "--corpus", str(rebuilt), "--dry-run", "--in-process")
    counters = summary["counters"]
    assert code == 0 and counters["unexplained_change"] == counters["failed"] == counters["changed_explained"] == 0
    assert not [n for n in summary["notices"] if n.startswith("source ")]  # no drift: nothing to say about commits


def test_a_drift_report_names_the_commits_the_source_was_built_at(capsys, built, tmp_path):
    src = tmp_path / "aged"
    shutil.copytree(ds.partial(built), ds.partial(src), symlinks=True)
    from test_derive_drift import _record_v1

    _record_v1(src)
    code, summary = cli(capsys, "recompute", "--corpus", str(src), "--dry-run", "--in-process")
    assert code == 0
    assert any(n.startswith(f"source import at commit {X} wrote ") for n in summary["notices"])
    code, summary = cli(capsys, "recompute", "--corpus", str(src), "--out", str(tmp_path / "refused"), "--in-process")
    assert code == 4 and f"source import at commit {X} wrote " in json.dumps(summary)


def test_a_drift_report_on_a_corpus_without_steps_adds_only_the_plain_notice(capsys, tmp_path):
    src = _import(tmp_path, "old", None)
    from test_derive_drift import _record_v1

    _record_v1(src)
    code, summary = cli(capsys, "recompute", "--corpus", str(src), "--out", str(tmp_path / "refused"), "--in-process")
    assert code == 4 and "source building commit not recorded" not in json.dumps(summary)
    _, dry = cli(capsys, "recompute", "--corpus", str(src), "--dry-run", "--in-process")
    assert "source building commit not recorded" in dry["notices"]


# ================================================================================================ sealing
def _sealed(tmp_path_factory, steps: list[dict[str, Any]] | None, **inputs: Any) -> tuple[Path, dict[str, Any]]:
    root = ss.working_corpus(tmp_path_factory, tmp_path_factory.mktemp("seal") / "mini")
    if steps is not None:
        path = ds.partial(root) / "corpus.json"
        m = json.loads(path.read_text())
        m["producer"]["build_steps"] = steps
        path.write_text(json.dumps(m, sort_keys=True, indent=2) + "\n")
    seal(root, corpus_version="0.1.0", inputs=ss.inputs(**inputs))
    return root, json.loads((root / "corpus.json").read_text("utf-8"))


def test_the_sealed_manifest_carries_the_sealing_commit_and_every_building_commit(tmp_path_factory):
    steps = [step().record(["aer", "sem", "prov", "validation"]), step("derive", Y).record(["prov"])]
    root, m = _sealed(tmp_path_factory, steps)
    assert m["producer"]["git_commit"] == ss.COMMIT  # the sealing commit (H.2.7, unchanged)
    assert m["producer"]["build_steps"] == steps
    assert mf.validate_manifest(m) == []
    datasheet = (root / "DATASHEET.md").read_text("utf-8")
    assert f"- Building commit: import at commit `{X}`, which wrote aer, prov, sem, validation; derive at commit `{Y}`" in datasheet


def test_a_corpus_with_no_recorded_steps_seals_and_the_datasheet_says_so(tmp_path_factory):
    root, m = _sealed(tmp_path_factory, None)
    assert "build_steps" not in m["producer"]
    assert "- Building commit: building commit not recorded." in (root / "DATASHEET.md").read_text("utf-8")


def test_an_absent_reason_does_not_refuse_and_the_datasheet_shows_it_with_the_version_and_digest(tmp_path_factory):
    root, m = _sealed(tmp_path_factory, [absent().record(["aer"])])
    text = (root / "DATASHEET.md").read_text("utf-8")
    assert "with no git checkout (not_a_source_checkout; agentprov `0.1.0`; installed distributions `" + DIGEST + "`)" in text
    assert m["producer"]["build_steps"][0]["git_commit_absent_reason"] == "not_a_source_checkout"


def test_a_dirty_build_step_refuses_the_seal_and_writes_nothing(tmp_path_factory):
    with pytest.raises(PackageRefusedError, match="uncommitted changes") as caught:
        _sealed(tmp_path_factory, [step(clean=False).record(["aer"])])
    assert caught.value.code == "package.refused.build_dirty" and caught.value.exit_code == 4


def test_a_malformed_history_refuses_the_seal(tmp_path_factory):
    with pytest.raises(PackageRefusedError, match="build_steps is malformed"):
        _sealed(tmp_path_factory, [{"command": "import"}])


def test_the_building_commit_is_part_of_the_content_digest(tmp_path_factory):
    _, plain = _sealed(tmp_path_factory, None)
    _, with_steps = _sealed(tmp_path_factory, [step().record(["aer"])])
    assert plain["content_digest"] != with_steps["content_digest"]
