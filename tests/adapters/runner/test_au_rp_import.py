"""2026-11-05 review findings of the importer, runner and raw layers (``AU-RP-4..6``, ``AU-NC-1``, ``AU-NC-2``; D-1063,
regen-batch item 183): each test reproduces one finding over small synthetic AgentDojo-shaped logs (built here, never
read from a source) and pins the fix."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import import_support as support

from agentprov.adapters.runner.importer import LocalTree, import_source
from agentprov.corpus.writer import CorpusWriter


def _log(task: str, *, text: str = "hello") -> dict[str, Any]:
    """A minimal native AgentDojo log."""
    messages = [{"role": "system", "content": "sys"}, {"role": "user", "content": "do it"},
                {"role": "assistant", "content": text, "tool_calls": None}]
    return {"suite_name": "banking", "pipeline_name": "scripted-fake", "user_task_id": task, "injection_task_id": None,
            "attack_type": None, "injections": {}, "messages": messages, "error": None, "utility": True,
            "security": True, "duration": 1.25, "agentdojo_package_version": "0.1.35", "benchmark_version": "v1.2.2",
            "evaluation_timestamp": "2026-10-07 14:00:12"}


def _label(task: str) -> str:
    return f"runs/scripted-fake/banking/{task}/none/none.json"


def _tree(root: Path, files: dict[str, Any]) -> Path:
    for rel, value in files.items():
        path = root.joinpath(*rel.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(value if isinstance(value, bytes) else json.dumps(value).encode())
    return root


def _snapshot(partial: Path) -> dict[str, Any]:
    return json.loads((partial / "corpus.json").read_text())["sources"][0]["snapshots"][0]


def _import(root: Path, out: Path, **kwargs: Any) -> Any:
    with CorpusWriter(out) as corpus:
        return import_source("agentdojo", LocalTree(root), corpus=corpus, part="2024-06", pin_check=support.vouch(root),
                             in_process=True, until="aer", **kwargs)


def _rows(report: Any, code: str) -> list[dict[str, Any]]:
    return [r for r in report.register if r["code"] == code]


# ------------------------------------------------------------------------------------------------ AU-RP-6
def test_a_memory_error_while_mapping_is_the_worker_limit_never_an_adapter_defect(tmp_path, monkeypatch):
    """Before, map_unit's ``except Exception`` caught the MemoryError of a mapper under the T1 address-space limit: the
    job succeeded with an ``adapter.defect`` degenerate AER and no ``worker.limit.rss`` row, while the same exhaustion
    in the reader was ``worker.limit.rss`` (G.4.6, G.4.12, H.6.3)."""
    from agentprov.adapters.agentdojo.mapper import TraceLoggerMapper

    original = TraceLoggerMapper.map

    def exhausted(self: Any, unit: Any, ctx: Any) -> Any:
        value = unit.primary.value
        if isinstance(value, dict) and value.get("user_task_id") == "user_task_1":
            raise MemoryError
        return original(self, unit, ctx)

    monkeypatch.setattr(TraceLoggerMapper, "map", exhausted)
    root = _tree(tmp_path / "in", {_label(f"user_task_{i}"): _log(f"user_task_{i}") for i in range(2)})
    report = _import(root, tmp_path / "c")
    assert report.counters["degenerate"] == 1
    (limit,) = _rows(report, "worker.limit.rss")
    (defect,) = _rows(report, "map.adapter_defect")  # the degenerate AER's seal issue, as for any over-limit job
    assert limit["disposition"] == defect["disposition"] == "failed" and defect["detail"] == "worker.limit.rss"
    assert limit["subject"] == defect["subject"]
    partial = tmp_path / "c.partial"
    executions = [json.loads(line) for line in (partial / "executions.jsonl").read_bytes().splitlines()]
    assert len(executions) == 2
    details = set()
    for e in executions:
        seal = json.loads((partial / e["paths"]["aer"]).read_bytes().splitlines()[-1])
        details |= {str(i.get("detail")) for i in seal.get("issues", []) if i.get("code") == "adapter_defect"}
    assert details == {"worker.limit.rss"}


# ------------------------------------------------------------------------------------------------ AU-RP-4
def _register_rows(partial: Path) -> list[tuple[str, str, str]]:
    rows = [json.loads(line) for line in (partial / "register.jsonl").read_text().splitlines()]
    return sorted((r["code"], r["disposition"], r["subject"].get("path", "")) for r in rows)


def test_a_copy_of_a_file_that_is_not_an_execution_is_not_imported_like_its_twin(tmp_path):
    """Before, the second of two byte-identical files that are not executions was registered dedup.collapsed with
    disposition sealed ('already selected in this snapshot'), although no execution holds its bytes (H.6.3, H.7.2)."""
    other = {"not": "an agentdojo log"}
    first, second = _label("user_task_1"), _label("user_task_2")
    root = _tree(tmp_path / "in", {_label("user_task_0"): _log("user_task_0"), first: other, second: other})
    report = _import(root, tmp_path / "c")
    assert report.counters["duplicates"] == 0 and report.counters["registered"] == 2
    partial = tmp_path / "c.partial"
    assert [r for r in _register_rows(partial) if r[0].startswith(("select.", "dedup."))] == [
        ("select.not_execution_artefact", "not_imported", first),
        ("select.not_execution_artefact", "not_imported", second)]
    counts = _snapshot(partial)["counts"]
    assert counts["executions"] == 1 and counts["not_imported"] == 2


def test_a_copy_of_an_execution_still_collapses_into_it(tmp_path):
    log = _log("user_task_0")
    root = _tree(tmp_path / "in", {_label("user_task_0"): log, _label("user_task_9"): log})
    report = _import(root, tmp_path / "c")
    assert report.counters["duplicates"] == 1
    partial = tmp_path / "c.partial"
    assert ("dedup.collapsed", "sealed", _label("user_task_9")) in _register_rows(partial)
    assert len((partial / "executions.jsonl").read_text().splitlines()) == 1


def test_a_copy_of_a_file_not_mapped_in_this_run_still_collapses(tmp_path):
    """--until raw maps nothing: the copy keeps the collapse it had (its twin's fate is never decided there)."""
    other = {"not": "an agentdojo log"}
    root = _tree(tmp_path / "in", {_label("user_task_1"): other, _label("user_task_2"): other})
    with CorpusWriter(tmp_path / "c") as corpus:
        report = import_source("agentdojo", LocalTree(root), corpus=corpus, part="2024-06",
                               pin_check=support.vouch(root), in_process=True, until="raw")
    assert report.counters["duplicates"] == 1


# ------------------------------------------------------------------------------------------------ AU-NC-2
def _archive_input(tmp_path: Path, members: dict[str, bytes]) -> tuple[dict[str, Any], Any]:
    import hashlib
    import io
    import zipfile

    from agentprov.adapters.profiles import load_profile
    from agentprov.adapters.runner.importer import ArchiveTree

    pin = dict(load_profile("dca-agentdojo").data["source"]["pins"][0])
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    data = buffer.getvalue()
    (tmp_path / pin["file"]).write_bytes(data)
    pin.update(sha256=hashlib.sha256(data).hexdigest(), size=len(data))
    return pin, lambda: ArchiveTree(tmp_path / pin["file"], pin=pin, sha256=pin["sha256"], size=len(data))


def _archive_import(tmp_path: Path, pin: dict[str, Any], tree: Any, **kwargs: Any) -> Any:
    with CorpusWriter(tmp_path / "c") as writer:
        return import_source("dca-agentdojo", tree(), corpus=writer, profile_id="dca-agentdojo", part="v1", pin=pin,
                             in_process=True, until="aer", **kwargs)


def _corpus_bytes(partial: Path) -> dict[str, bytes]:
    return {**{name: (partial / name).read_bytes() for name in ("executions.jsonl", "register.jsonl", "raw/origins.jsonl",
                                                                  "raw/members.jsonl")},
            **{str(p.relative_to(partial)): p.read_bytes() for p in sorted((partial / "aer").rglob("*.aer.jsonl"))}}


def test_a_purged_archive_member_is_resumed_never_read(tmp_path):
    """Before, a re-run of an archive import after one member's object was purged re-expanded the archive, the store
    refused the tombstoned member and _MemberTree.read raised KeyError for it: the import died and left the snapshot
    incomplete, so the corpus could no longer be packaged (D-610)."""
    import hashlib

    from agentprov.corpus.purge import apply, plan_corpus
    from agentprov.corpus.verify import verify_corpus

    top = "DCA_AgentDojo_artifact_v1_20260612/results/logs/m/run/pipe/banking"
    members = {f"{top}/user_task_{i}/none/none.json": json.dumps(_log(f"user_task_{i}", text=f"r{i}")).encode()
               for i in range(2)}
    pin, tree = _archive_input(tmp_path, members)
    first = _archive_import(tmp_path, pin, tree)
    assert first.exit_code == 0 and first.counters["mapped"] == 2
    partial = tmp_path / "c.partial"
    apply(plan_corpus(partial, hashlib.sha256(list(members.values())[1]).hexdigest(), "secret"))
    before = _corpus_bytes(partial)
    for kwargs in ({}, {"retry_failed": True}):
        report = _archive_import(tmp_path, pin, tree, **kwargs)
        assert report.exit_code == 0 and report.counters["mapped"] == 0 and report.counters["skipped_resume"] == 2
        assert _corpus_bytes(partial) == before
        assert _snapshot(partial).get("incomplete") is None
        assert not verify_corpus(partial, level="chain", in_process=True).failures



def test_a_purged_archive_member_collapses_into_its_execution_in_another_snapshot(tmp_path):
    """The same archive imported as a second snapshot: the purged member is collapsed into the execution the corpus holds
    (H.7.2(1)), as an identical member that was not purged is; nothing is read or stored again."""
    import hashlib

    from agentprov.corpus.purge import apply, plan_corpus

    top = "DCA_AgentDojo_artifact_v1_20260612/results/logs/m/run/pipe/banking"
    members = {f"{top}/user_task_{i}/none/none.json": json.dumps(_log(f"user_task_{i}", text=f"r{i}")).encode()
               for i in range(2)}
    pin, tree = _archive_input(tmp_path, members)
    _archive_import(tmp_path, pin, tree)
    apply(plan_corpus(tmp_path / "c.partial", hashlib.sha256(list(members.values())[1]).hexdigest(), "secret"))
    report = _archive_import(tmp_path, pin, tree, snapshot_id="again")
    assert report.exit_code == 0 and report.counters["mapped"] == 0 and report.counters["duplicates"] == 2


# ------------------------------------------------------------------------------------------------ AU-NC-1
class _Fetcher:
    """A fetch cache double: a git tree of the given paths (no network, no git)."""

    def __init__(self, paths: list[str]) -> None:
        self.paths = paths

    def git_tree_named(self, recipe: Any) -> tuple[list[Any], list[str]]:
        from agentprov.raw.fetch import TreeEntry

        return [TreeEntry("100644", "blob", "a" * 40, 10, p) for p in self.paths], []

    def history_index(self, recipe: Any) -> None:
        return None


class _Recipe:
    repo, commit, paths = "https://example.invalid/r.git", "b" * 40, ()


def _git_tree(paths: list[str]) -> Any:
    from agentprov.adapters.runner.importer import GitPinTree

    return GitPinTree(_Fetcher(paths), _Recipe())  # type: ignore[arg-type]


def test_a_fetched_tree_applies_discover_s_case_and_normalisation_rules():
    """Before, GitPinTree kept runs/A.json, runs/a.json and an NFD name as three candidates under their raw spelling,
    where discover rejects both colliding names (ingest.path.duplicate) and a name not in NFC whose NFC form is another
    entry (ingest.name.invalid): one pin gave different corpora by --fetch and by --input --verify-against-pin."""
    import unicodedata

    nfd = unicodedata.normalize("NFD", "runs/café.json")
    tree = _git_tree(["runs/A.json", "runs/a.json", nfd, "runs/b.json"])
    assert [c.label for c in tree.walk()] == ["runs/b.json"]
    assert sorted((r.label, r.code) for r in tree.rejections) == [
        ("runs/A.json", "ingest.path.duplicate"), ("runs/a.json", "ingest.path.duplicate"),
        (unicodedata.normalize("NFC", nfd), "ingest.name.invalid")]


def test_a_fetched_directory_whose_name_collides_is_one_rejection_and_nothing_below_it():
    tree = _git_tree(["runs/X/one.json", "runs/x/two.json", "runs/x/three.json", "runs/y/four.json"])
    assert [c.label for c in tree.walk()] == ["runs/y/four.json"]
    assert sorted((r.label, r.code) for r in tree.rejections) == [
        ("runs/X", "ingest.path.duplicate"), ("runs/x", "ingest.path.duplicate")]


def test_discover_and_the_fetched_tree_share_one_rule_set(tmp_path):
    """The rules are one function (``ingest.paths.sibling_verdicts``): an --input tree with the same names (as far as the
    host file system can hold them) gets the same verdicts."""
    from agentprov.ingest.paths import discover, sibling_verdicts

    verdicts = {name: (r.code if r else None) for name, _nfc, r in sibling_verdicts(["A.json", "a.json", "b.json"],
                                                                                    lambda _r, _n: False)}
    assert verdicts == {"A.json": "ingest.path.duplicate", "a.json": "ingest.path.duplicate", "b.json": None}
    (tmp_path / "runs").mkdir()
    for name in ("b.json", "c.json"):
        (tmp_path / "runs" / name).write_bytes(b"{}")
    found = discover(tmp_path)
    assert [f.label for f in found.files] == [c.label for c in _git_tree(["runs/b.json", "runs/c.json"]).walk()]
