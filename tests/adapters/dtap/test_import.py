"""The import pipeline with the DTap runner items (docs/architecture D.16.14 R1-R3; D.2.9; K.13): per-unit auxiliary
artefacts, the second pinned tree, pinned LFS objects, registrations, and byte-identical output across worker counts."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

import dtap_support as support
import pytest

from agentprov.adapters.runner.importer import PinnedObject
from agentprov.adapters.types import Origin


def _object(tmp: Path) -> PinnedObject:
    """A pinned object standing for the F21 pointer (a test object: F01's bytes; the real one is 12 MB)."""
    value = json.loads(support.runs_files()[support.F["F01"]])
    value["traj_info"]["duration"] = 1.5  # distinct bytes, so the object is not a copy of F01
    data = json.dumps(value).encode()
    path = tmp / "lfs-object.json"
    path.write_bytes(data)
    origin = Origin.hf("AI-Secure/DTap-Bench-Agent-Trajectories", support.RUNS_COMMIT, support.F["F21"])
    return PinnedObject(support.F["F21"], origin, str(path), hashlib.sha256(data).hexdigest(), len(data))


@pytest.fixture(scope="module")
def imported(tmp_path_factory: pytest.TempPathFactory) -> support.Imported:
    tmp = tmp_path_factory.mktemp("dtap-import")
    return support.run_import(tmp, support.runs_files(), support.tasks_files(), objects=[_object(tmp)])


def _register(imp: support.Imported) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for row in imp.register:
        out.setdefault(row["code"], []).append(row)
    return out


def test_every_candidate_has_one_disposition_and_every_execution_validates(imported):
    c = imported.report.counters
    assert c["degenerate"] == 0 and c["failed"] == 0 and imported.report.exit_code == 0
    assert c["mapped"] == c["validated"] == c["derived"] == c["annotated"] == len(imported.rows)
    assert c["seen"] == c["mapped"] + c["registered"] + c["duplicates"]
    assert {r["adapter"] for r in imported.rows} == {"dtap.trajectory@0.1.0"}


def test_r1_judge_is_a_supporting_artefact_of_its_directory(imported):
    heads = imported.headers()
    head = heads[support.F["F01"]]
    roles = [(a["role"], a["origin"]["path"].rsplit("/", 1)[-1]) for a in head["artifacts"]]
    assert roles == [("primary", "20260220_133459.json"), ("supporting", "judge_result.json"), ("supporting", "config.yaml")]
    judges = [p for p in heads if p.endswith("judge_result.json")]
    assert judges == [support.F["X02"]]  # only a judge-only directory makes a judge the primary artefact


def test_auxiliary_artefacts_carry_the_media_type_of_their_label(imported):
    """Sample-check fix b2: a judge, configuration or attempt file is typed by its label (``application/json``,
    ``application/yaml``), never ``application/octet-stream``; the same JSON has one media type whether it is a primary
    or another unit's supporting artefact, so a shared ``raw:`` entity does not vary in ``apv:mediaType``."""
    media: dict[str, set[str]] = {}
    roles: Counter[tuple[str, str]] = Counter()
    for head in imported.headers().values():
        for a in head["artifacts"]:
            media.setdefault(a["sha256"], set()).add(a["media"])
            roles[(a["role"], a["media"])] += 1
            suffix = a["origin"]["path"].rsplit(".", 1)[-1]
            assert a["media"] == {"json": "application/json", "yaml": "application/yaml"}[suffix], (a["role"], suffix)
    assert all(len(m) == 1 for m in media.values())
    assert {("supporting", "application/json"), ("supporting", "application/yaml")} <= set(roles)
    attempts = [a for a in imported.headers()[support.F["F20a"]]["artifacts"] if a["origin"]["path"] == support.F["F20b"]]
    assert [(a["role"], a["media"]) for a in attempts] == [("supporting", "application/json")]


def test_aux_media_by_label_suffix():
    from agentprov.adapters.runner.importer import aux_media

    assert aux_media("a/b/judge_result.json") == aux_media("a/B.JSON") == "application/json"
    assert aux_media("tasks:medical/x/config.yaml") == aux_media("c.yml") == "application/yaml"
    assert aux_media("screenshots/screenshot_001.png") == aux_media("noext") == "application/octet-stream"


def test_r2_configurations_come_from_the_tasks_pin(imported):
    head = imported.headers()[support.F["F03"]]
    config = head["artifacts"][2]
    assert config["origin"]["repo"] == support.TASKS_REPO and config["origin"]["commit"] == support.TASKS_COMMIT
    manifest = json.loads((imported.partial / "corpus.json").read_text(encoding="utf-8"))
    context = manifest["sources"][0]["snapshots"][0]["context"]
    assert context[0]["role"] == "tasks" and context[0]["stored"] == len(support.tasks_files())


def test_r3_lfs_pointer_registered_and_pinned_object_imported(imported):
    register = _register(imported)
    pointer = [r for r in register["select.not_execution_artefact"] if r["subject"].get("path") == support.F["F21"]]
    assert len(pointer) == 1 and pointer[0]["detail"] == "dtap.lfs_pointer"
    head = imported.headers()[support.F["F21"]]
    assert head["artifacts"][0]["origin"]["kind"] == "hf" and head["artifacts"][1]["origin"]["path"].endswith("judge_result.json")
    judge = support.F["F21"].rsplit("/", 1)[0] + "/judge_result.json"
    assert not [r for r in imported.register if r["subject"].get("path") == judge]  # consumed by the object's unit
    manifest = json.loads((imported.partial / "corpus.json").read_text(encoding="utf-8"))
    assert manifest["sources"][0]["snapshots"][0]["pinned_objects"][0]["label"] == support.F["F21"]


def test_a_resumed_import_keeps_the_pinned_objects_judge_consumed(tmp_path):
    """D-981: a second run over the same corpus (a resume; ``--retry-failed`` skips the same way) skips the pinned
    object's unit, and the judge file it consumed is still not registered as an auxiliary of a file that is not an
    execution (the w2b retry wrote such a row; a recompute's re-map drops it, an unexplained register difference)."""
    obj = _object(tmp_path)
    first = support.run_import(tmp_path, support.runs_files(), support.tasks_files(), objects=[obj])
    second = support.run_import(tmp_path, support.runs_files(), support.tasks_files(), objects=[obj])
    assert second.report.counters["skipped_resume"] == len(first.rows) and second.rows == first.rows
    judge = support.F["F21"].rsplit("/", 1)[0] + "/judge_result.json"
    assert not [r for r in second.register if r["subject"].get("path") == judge]
    assert second.register == first.register  # the resume adds and drops nothing


def test_synthetic_trajectory_and_its_judge_are_registered_not_imported(imported):
    register = _register(imported)
    d = support.F["F17"].rsplit("/", 1)[0]
    rows = {r["subject"]["path"]: r for r in register["select.not_execution_artefact"] if r["subject"].get("path", "").startswith(d)}
    assert rows[support.F["F17"]]["detail"] == "dtap.synthetic"
    assert rows[f"{d}/judge_result.json"]["detail"].startswith("dtap.synthetic")
    assert support.F["F17"] not in imported.headers()


def test_copies_collapse_into_one_execution_with_two_origins(imported):
    register = _register(imported)
    collapsed = {r["subject"]["path"].rsplit("/", 1)[-1] for r in register["dedup.collapsed"]}
    assert {"20260327_005714(1).json", "judge_result(1).json"} <= collapsed
    origins = (imported.partial / "raw" / "origins.jsonl").read_text(encoding="utf-8")
    assert "20260327_005714(1).json" in origins and "judge_result(1).json" in origins


def test_the_dtap_catalogue_is_declared_only_by_dtap_executions(imported):
    for row in imported.rows:
        head = json.loads(imported.aer(row["ex"]).split(b"\n", 1)[0])
        assert head["rules"] == {"aer": 1, "dtap": 3}  # catalogue version 3 (D-934)


def test_without_the_object_the_pointer_and_its_judge_are_registered(tmp_path):
    keep = support.F["F21"].rsplit("/", 1)[0]
    runs = {k: v for k, v in support.runs_files().items() if k.startswith(keep)}
    imp = support.run_import(tmp_path, runs, {})
    details = sorted(r["detail"] for r in imp.register if r["code"] == "select.not_execution_artefact")
    assert details == ["dtap.lfs_pointer", "dtap.lfs_pointer (auxiliary artefact of a file that is not an execution)"]
    assert imp.rows == []


def test_output_is_byte_identical_across_worker_counts(tmp_path):
    """K.13 / D.16.14 test 11: in process, one worker and three workers give the same corpus bytes."""
    runs = {k: v for k, v in support.runs_files().items()
            if any(k.startswith(support.F[f].rsplit("/", 1)[0]) for f in ("F01", "F03", "F06", "F17", "X04", "X02"))}
    tasks = support.tasks_files()
    trees = []
    for name, kwargs in (("inproc", {"in_process": True}), ("one", {"in_process": False, "workers": 1}),
                         ("three", {"in_process": False, "workers": 3, "batch_size": 2})):
        imp = support.run_import(tmp_path, runs, tasks, name=name, **kwargs)
        files = support.tree_bytes(imp.partial)
        manifest = json.loads(files.pop("corpus.json"))
        manifest["producer"].pop("isolation")
        snapshot = manifest["sources"][0]["snapshots"][0]
        snapshot.pop("origin")  # each run reads its own copy of the input trees (a local path)
        for context in snapshot["context"]:
            context.pop("origin")
        files["corpus.json"] = json.dumps(manifest, sort_keys=True).encode()
        trees.append(files)
    for other in trees[1:]:
        assert sorted(other) == sorted(trees[0])
        differ = [k for k in trees[0] if trees[0][k] != other[k]]
        assert differ == [], differ


def test_release_mode_import_validates(tmp_path):
    runs = {k: v for k, v in support.runs_files().items() if k.startswith(support.F["F07"].rsplit("/", 1)[0])}
    imp = support.run_import(tmp_path, runs, support.tasks_files(), mode="release", in_process=False, workers=1)
    assert imp.report.counters["validated"] == 1 and imp.report.exit_code == 0
    assert Counter(r["status"] for r in imp.rows) == Counter({"ok": 1})
