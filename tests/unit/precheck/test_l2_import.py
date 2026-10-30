"""The selection shim of ``tools/precheck/l2_import.py`` on synthetic labels: ``AnyOf`` is the OR of the escaped sampled
labels, the product matcher is untouched for every other glob and restored afterwards, the recorded marker string is
recognised on a replay, and the recipes cover every registry part."""

from __future__ import annotations

import json

import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[3] / "tools" / "precheck"


@pytest.fixture(scope="module")
def li():
    sys.path.insert(0, str(TOOLS))
    try:
        import l2_import

        yield l2_import
    finally:
        sys.path.remove(str(TOOLS))


def test_any_of_is_the_or_of_escaped_labels(li) -> None:
    from agentprov.adapters.runner import importer

    labels = ["runs/m [x]/a*.json", "runs/b?.json", "zip!/logs/c.eval"]
    any_of = li.AnyOf(labels)
    assert str(any_of).startswith("precheck:any-of:3:sha256:")
    original = importer._match
    seen: dict[str, object] = {}
    with li.any_of_matcher(any_of, seen):
        assert all(importer._match(label, any_of) for label in labels)
        assert not importer._match("runs/m x/a.json", any_of)
        assert not importer._match("runs/bb.json", any_of)
        assert importer._match("runs/b?.json", str(any_of))  # the recorded marker (a replay) is recognised
        assert importer._match("runs/x/y.json", "runs/**/*.json")  # every other glob: the product matcher
        assert not importer._match("other.txt", "runs/**/*.json")
    assert importer._match is original


def test_any_of_is_deterministic(li) -> None:
    assert str(li.AnyOf(["b", "a"])) == str(li.AnyOf(["a", "b"]))
    assert str(li.AnyOf(["a"])) != str(li.AnyOf(["b"]))


#: Wave 7 (phase 10j, merged 2026-10-15): every part has the phase-10j trial's recipe except the two DCA parts, whose
#: import is held (D-455; a url pin is not an archive input yet, R-10j-3): L1 only.
WAVE7_PENDING = {("dca-agentdojo", "v1"), ("dca-agentdojo", "drift")}  # fmt: skip
#: Registered after the pre-registered population, no recipe yet: phase 10o part C (its context pin waits D-530) and
#: phase 10q (memo-ozdincer, registered at its merge).
AWAITING_RECIPE = {("redcode-exec-qwencode", "qwen3coder"), ("memo-ozdincer-agentdojo", "head")}  # fmt: skip
#: environmentoptim-agentdojo · head left the registry (D-901: excluded), so it is no registry part any more.
WAVE7_PHASE10J = {("authority-caps-agentdojo", "head"), ("ipi-defenses-agentdojo", "head"), ("kavach-agentdojo", "main"),
                  ("kavach-agentdojo", "nav-fixer2"), ("kavach-agentdojo", "rearch-forcedformat-fix"),
                  ("drift1-agentdojo", "drift")}  # fmt: skip


def test_every_registry_part_has_a_recipe(li) -> None:
    from agentprov.adapters.registry import REGISTRY

    kinds = {(r.source_id, c.part): li.recipe_kind(r.source_id, c.part) for r in REGISTRY for c in r.capabilities}
    # every registry part has a recipe (or a recorded blocker): the committed population (manifest.json) and wave 7
    manifest = json.loads((Path(__file__).resolve().parents[3] / "docs/reports/precheck/manifest.json").read_text())
    population = {(p["source"], p["part"]) for p in manifest["parts"]}
    assert not [k for k, v in kinds.items() if v == "unknown" and k in population]
    assert not [k for k, v in kinds.items() if v == "unknown" and k not in AWAITING_RECIPE]
    assert {k for k in WAVE7_PENDING if kinds[k] == "blocked" and "D-455" in li.BLOCKED[k]} == WAVE7_PENDING
    assert {k for k in WAVE7_PHASE10J if kinds[k] == "phase10j"} == WAVE7_PHASE10J
    assert kinds[("mcphunt", "head")] == "blocked" and kinds[("dtap", "head")] == "dtap"
    assert kinds[("credleak-p15b", "head")] == "archive" and kinds[("gate-agentdojo", "head")] == "git-seeded"


def test_phase10j_part_pins_are_the_trial_driver_s(li) -> None:
    """Each wave-7 part reads its own pin (Kavach: three git pins), as phase10j_trial._pins assigns them."""
    from agentprov.adapters.profiles import load_profile

    trial = li.load_tool("agentdojo/phase10j_trial.py")
    kavach = dict(trial._pins(load_profile("kavach-agentdojo")))
    assert len({p["commit"] for p in kavach.values()}) == 3
    assert {k: p["commit"][:8] for k, p in kavach.items()} == {
        "main": "53df9545", "nav-fixer2": "f2dd7efa", "rearch-forcedformat-fix": "6b31a554"}
    caps = dict(trial._pins(load_profile("authority-caps-agentdojo")))["head"]
    assert caps["kind"] == "zenodo" and caps["sha256"] in trial.ARCHIVES


def test_redaction_pending_guard(li) -> None:
    from types import SimpleNamespace

    from agentprov.adapters.profiles import load_profile

    built = SimpleNamespace(profile=load_profile("environmentoptim-agentdojo", 1))  # v1 (archived) holds the arms
    ok = ["runs/gpt-5.4-2026-03-05/workspace/user_task_0/none/none.json"]
    assert li.redaction_pending_guard(built, ok) == 5  # the five D-255 globs of the profile
    held = ("runs/benign_injection/c/checkpoint_1/256/m/workspace/user_task_0/none/none.json",
            "runs/qwen3_5-9B_baseline/workspace/user_task_0/none/none.json")
    for label in held:
        with pytest.raises(SystemExit):
            li.redaction_pending_guard(built, [*ok, label])
    # v2 (regeneration-batch item 106) redacts the arms instead of holding them: nothing to guard
    assert li.redaction_pending_guard(SimpleNamespace(profile=load_profile("environmentoptim-agentdojo")), [*ok, *held]) == 0
    assert li.redaction_pending_guard(SimpleNamespace(profile=load_profile("drift1-agentdojo")), ok) == 0


def test_scratch_guard(li, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENTPROV_HOME", str(tmp_path))
    with pytest.raises(SystemExit):
        li.guard_scratch(tmp_path / "corpora" / "x")
    with pytest.raises(SystemExit):
        li.guard_scratch(tmp_path / "elsewhere" / "x")
    ok = tmp_path / "migration-work" / "precheck" / "c" / "l2-head"
    assert li.guard_scratch(ok) == ok


class _JudgeReader:
    """A DTap-shaped reader: a directory's trajectories are candidates, its judge file only where none is left; each
    trajectory reads its trajectory siblings (``auxiliary_for``)."""

    def iter_artefacts(self, tree, profile):
        by_dir: dict[str, list] = {}
        for c in tree.walk():
            by_dir.setdefault(c.label.rpartition("/")[0], []).append(c)
        for items in by_dir.values():
            traj = [c for c in items if c.label.endswith("traj.json")]
            yield from traj or [c for c in items if c.label.endswith("judge.json")]

    def auxiliary_for(self, label, listing):
        return {f"attempt:{n}": s for n, s in enumerate(x for x in listing.siblings(label)
                                                        if x != label and x.endswith("traj.json"))}


def _judge_tree(li, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, files: list[str]):
    from types import SimpleNamespace

    from agentprov.adapters.runner.importer import LocalTree

    for f in files:
        (tmp_path / f).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / f).write_text("{}", encoding="utf-8")
    monkeypatch.setattr(li, "_reader", lambda built: _JudgeReader())
    return SimpleNamespace(tree=LocalTree(tmp_path), profile=None)


def test_prune_repeats_until_the_candidates_are_the_sample(li, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Pre-round review: one prune round promoted every unsampled directory's judge file (DTap kept 66,026 of 133,851
    candidates for a 5-label sample). The prune now repeats until the reader's candidates are exactly the sample, and
    passes on only the sampled labels' R3 pinned objects (re-check RC-12)."""
    from types import SimpleNamespace

    built = _judge_tree(li, tmp_path, monkeypatch, [f"d{i}/{n}" for i in range(4) for n in ("traj.json", "judge.json")])
    built.pinned_objects = [SimpleNamespace(label=f"d{i}/traj.json") for i in (0, 2)]  # R3 objects (LFS) of two pointers
    out = li.prune_tree(built, ["d0/traj.json"])
    assert out == {"candidates": 4, "dropped": 6, "kept": 1, "rounds": 2, "pinned_objects_kept": 1,
                   "pinned_objects_dropped": 1}
    assert [o.label for o in built.pinned_objects] == ["d0/traj.json"]  # the unsampled unit's object is not passed on
    assert li.candidate_labels(built) == ["d0/traj.json"]
    assert sorted(c.label for c in built.tree.walk()) == ["d0/judge.json", "d0/traj.json"]  # its judge stays


def test_prune_refuses_to_drop_a_sampled_unit_s_input(li, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    built = _judge_tree(li, tmp_path, monkeypatch, ["d0/a.traj.json", "d0/b.traj.json", "d1/traj.json"])
    with pytest.raises(li.SampleMismatchError, match="inputs of 1 sampled unit"):
        li.prune_tree(built, ["d0/a.traj.json"])
    with pytest.raises(li.SampleMismatchError, match="not candidates"):
        li.prune_tree(_judge_tree(li, tmp_path, monkeypatch, []), ["d9/traj.json"])


def test_kexin_guard_follows_the_profile_s_model_id_redaction(li) -> None:
    """Pre-round review: the guard is skipped once the resolved profile redacts the model id (kexin v2, item 107, with
    the D-604 withholding); with profile v1 it still refuses a local-path-model log."""
    from types import SimpleNamespace

    from agentprov.adapters.profiles import load_profile

    redacting = SimpleNamespace(id="p", version=2, data={"family": {"inspect": {"redact": [
        {"id": "local_checkpoint_path", "scope": "model_id"}, {"id": "other", "scope": "text"}]}}})
    assert li.model_id_redactions(redacting) == ["local_checkpoint_path"]
    assert li.kexin_local_path_guard(SimpleNamespace(profile=redacting, tree=None), ["x.eval"]) is None  # tree unread
    assert li.model_id_redactions(SimpleNamespace(data={})) == []
    assert li.model_id_redactions(load_profile("kexin-xu-01-agentharm")) in ([], ["local_checkpoint_path"])


def test_dtap_tasks_context_tree_records_its_pin(li, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Re-check RC-12(c), verification V-6: the DTap recipe's ``ContextTree("tasks")`` carries the profile's ``tasks`` pin,
    which the manifest records for a re-map (D-530), as ``tools/dtap/import_dtap.py`` does. Synthetic home: the staged
    listing and the LFS fetch are stubbed (no staging, no network)."""
    from types import SimpleNamespace

    from agentprov.adapters.profiles import load_profile
    from agentprov.raw import fetch

    monkeypatch.setenv("AGENTPROV_HOME", str(tmp_path))
    monkeypatch.setattr(li, "_git_env_listing", lambda bare, commit: {})
    monkeypatch.setattr(fetch.Fetcher, "fetch", lambda self, recipe: SimpleNamespace(path=str(tmp_path / "x"),
                                                                                      sha256="sha256:" + "0" * 64, bytes=1))
    cap = next(c for c in li._capability_list("dtap") if c.part == "head")
    pins = [li._thaw(p) for p in load_profile(str(cap.profile)).data["source"]["pins"]]
    lfs = tmp_path / li.STAGING / "dtap" / "lfs-objects"
    lfs.mkdir(parents=True)
    for p in pins:
        if p["role"] == "lfs_object":
            (lfs / p["sha256"]).write_bytes(b"stub")
    built = li.build("dtap", "head", cache=tmp_path / "cache", input_path=None, scratch=tmp_path / "scratch")
    (context,) = built.context_trees
    tasks = next(p for p in pins if p["role"] == "tasks")
    assert context.role == "tasks" and context.pin == tasks and context.pin["commit"] == li.DTAP_TASKS_COMMIT
    assert built.pin == next(p for p in pins if p["role"] == "runs")
