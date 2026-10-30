"""``agentprov import``: per-unit inputs from a profile's declared pins (D-530 regen item 99; runner items R2, R3).

Every ``[import] context_artefacts`` role ``"<role>:<glob>"`` is resolved from ``--context ROLE=PATH`` (checked against the
role's pin) or the verified fetch cache, and is never dropped silently: an unresolved role is refused unless
``--no-context ROLE`` is given. ``lfs_object`` pins give the pinned objects of the pointers the input holds (item 6).
The fetch cache is seeded from local repositories and files (the ``raw.fetch`` test seam); no network.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

_TESTS = Path(__file__).resolve().parents[1]
if str(_TESTS / "unit" / "raw") not in sys.path:
    sys.path.insert(0, str(_TESTS / "unit" / "raw"))
from fetch_support import git, needs_git  # noqa: E402

from agentprov.adapters.runner.importer import ArchiveTree, GitPinTree, LocalTree  # noqa: E402
from agentprov.cli.common import CommandResult, Context, CliUsageError  # noqa: E402
from agentprov.cli.import_ import _per_unit_inputs  # noqa: E402
from agentprov.errors import AgentProvError  # noqa: E402
from agentprov.raw.fetch import Fetcher, Recipe  # noqa: E402

REPO = "https://github.com/example/tasks"
DATASET = "example/traces"
REVISION = "c" * 40


def _args(cache: Path, **kwargs: Any) -> argparse.Namespace:
    base = {"cache_dir": str(cache), "allow_network": False, "dry_run": False, "i_consent_to_large_download": False,
            "context": [], "no_context": [], "allow_hardlinks": False}
    return argparse.Namespace(**{**base, **kwargs})


def _profile(pins: list[dict[str, Any]], context: list[str]) -> Any:
    return SimpleNamespace(id="test-profile", data={"source": {"pins": pins}, "import": {"context_artefacts": context}})


def _tree(labels: list[str]) -> Any:
    return SimpleNamespace(walk=lambda: iter(SimpleNamespace(label=label) for label in labels))


@pytest.fixture
def tasks_repo(tmp_path: Path) -> dict[str, Any]:
    upstream = tmp_path / "upstream"
    (upstream / "tasks" / "code").mkdir(parents=True)
    (upstream / "tasks" / "code" / "001_x.yaml").write_bytes(b"id: code/001\n")
    (upstream / "src.py").write_bytes(b"never read\n")
    git(upstream, "init", "-q", "-b", "main")
    git(upstream, "add", "-A")
    git(upstream, "commit", "-q", "-m", "tasks")
    commit = git(upstream, "rev-parse", "HEAD")
    cache = tmp_path / "cache"
    Fetcher(cache, allow_network=True, remote_urls={REPO: f"file://{upstream}"}, file_protocol=True).fetch(
        Recipe(kind="git", repo=REPO, commit=commit, paths=("tasks/",)))
    pin = {"role": "tasks", "kind": "git", "repo": REPO, "commit": commit, "tree": "tasks/", "primary": False}
    return {"cache": cache, "pin": pin, "upstream": upstream}


@needs_git
def test_a_declared_git_context_pin_is_wired_from_the_cache_offline(tasks_repo):
    profile = _profile([tasks_repo["pin"]], ["tasks:tasks/*/*.yaml"])
    result = CommandResult(dry_run=False)
    contexts, objects, local = _per_unit_inputs(_args(tasks_repo["cache"]), Context(_args(tasks_repo["cache"])), profile,
                                                None, _tree([]), None, result)
    (ctx,) = contexts
    assert ctx.role == "tasks" and isinstance(ctx.tree, GitPinTree) and ctx.pin_check is None and ctx.pin == tasks_repo["pin"]
    assert objects == [] and local == []


@needs_git
def test_context_role_path_is_a_local_copy_checked_against_the_pin(tasks_repo):
    profile = _profile([tasks_repo["pin"]], ["tasks:tasks/*/*.yaml"])
    args = _args(tasks_repo["cache"], context=[f"tasks={tasks_repo['upstream']}"])
    contexts, _objects, local = _per_unit_inputs(args, Context(args), profile, None, _tree([]), None, CommandResult(dry_run=False))
    (ctx,) = contexts
    assert isinstance(ctx.tree, LocalTree) and ctx.pin_check is not None and ctx.pin_check.kind == "blob"
    assert local == [tasks_repo["upstream"]]


def test_an_uncached_context_pin_is_refused_unless_no_context_names_it(tmp_path):
    pin = {"role": "tasks", "kind": "git", "repo": REPO, "commit": "a" * 40, "tree": "tasks/"}
    profile = _profile([pin], ["tasks:tasks/*/*.yaml"])
    args = _args(tmp_path / "cache")
    with pytest.raises(AgentProvError) as err:
        _per_unit_inputs(args, Context(args), profile, None, _tree([]), None, CommandResult(dry_run=False))
    assert err.value.exit_code == 4 and "--no-context tasks" in str(err.value)
    args = _args(tmp_path / "cache", no_context=["tasks"])
    result = CommandResult(dry_run=False)
    contexts, objects, _local = _per_unit_inputs(args, Context(args), profile, None, _tree([]), None, result)
    assert contexts == [] and objects == [] and any("--no-context tasks" in n for n in result.notices)


def test_an_unknown_context_role_is_a_usage_error(tmp_path):
    profile = _profile([], ["tasks:tasks/*/*.yaml"])
    args = _args(tmp_path / "cache", no_context=["judges"])
    with pytest.raises(CliUsageError):
        _per_unit_inputs(args, Context(args), profile, None, _tree([]), None, CommandResult(dry_run=False))


def test_a_download_context_pin_from_a_local_copy_is_an_archive_context(tmp_path):
    data = b"PK\x05\x06" + bytes(18)  # an empty zip: the importer expands it, this test only checks the wiring
    (tmp_path / "supp.zip").write_bytes(data)
    pin = {"role": "supp", "kind": "zenodo", "doi": "10.5281/zenodo.23168099", "file": "supp.zip",
           "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
    profile = _profile([pin], ["supp:results/**/index*.json"])
    args = _args(tmp_path / "cache", context=[f"supp={tmp_path / 'supp.zip'}"])
    contexts, _objects, _local = _per_unit_inputs(args, Context(args), profile, None, _tree([]), None, CommandResult(dry_run=False))
    (ctx,) = contexts
    assert isinstance(ctx.tree, ArchiveTree) and ctx.tree.sha256 == pin["sha256"] and ctx.pin == pin
    bad = _args(tmp_path / "cache", context=[f"supp={tmp_path / 'supp.zip'}"])
    with pytest.raises(AgentProvError):
        _per_unit_inputs(bad, Context(bad), _profile([{**pin, "sha256": "0" * 64}], ["supp:x"]), None, _tree([]), None,
                         CommandResult(dry_run=False))


def test_lfs_object_pins_give_pinned_objects_for_the_pointers_the_input_holds(tmp_path):
    body = b'{"traces": []}'
    held = {"role": "lfs_object", "kind": "hf", "dataset": DATASET, "revision": REVISION, "file": "main/a.json",
            "sha256": hashlib.sha256(body).hexdigest(), "bytes": len(body)}
    absent = {**held, "file": "main/b.json"}
    cache = tmp_path / "cache"
    target = Recipe.from_pin(held).cache_path(cache)  # seeded as the DTap driver seeds a verified object
    target.parent.mkdir(parents=True)
    target.write_bytes(body)
    profile = _profile([held, absent], [])
    args = _args(cache)
    contexts, objects, _local = _per_unit_inputs(args, Context(args), profile, None, _tree(["main/a.json", "main/c.json"]),
                                                 None, CommandResult(dry_run=False))
    (obj,) = objects
    assert contexts == [] and obj.label == "main/a.json" and obj.sha256 == held["sha256"] and obj.size == len(body)
    assert obj.origin.kind == "hf" and obj.origin.data["revision"] == REVISION


# ------------------------------------------------------------------------------------------------ bug pass NF-27, NF-28
def test_a_role_given_twice_to_context_is_refused_nf27(tmp_path):
    from agentprov.cli.import_ import _check_options

    (tmp_path / "a").mkdir()
    args = argparse.Namespace(source="x", spec=None, corpus=str(tmp_path / "c"), input=str(tmp_path / "a"), fetch=False,
                              verify_against_pin=True, select=[], release=False, limit=None, suite=None, attack=None,
                              pipeline=None, variant=None, artefacts=False, dry_run=False, in_process=False, sample=None,
                              sample_mode=None, seed=None, skip_prov_conformance=False, until=None,
                              context=[f"tasks={tmp_path / 'a'}", f"tasks={tmp_path / 'a'}"], no_context=[])
    with pytest.raises(CliUsageError, match="twice"):
        _check_options(args)


@needs_git
def test_a_context_path_holding_none_of_the_roles_files_is_refused_nf27(tasks_repo, tmp_path):
    profile = _profile([tasks_repo["pin"]], ["tasks:tasks/*/*.yaml"])
    empty = tmp_path / "elsewhere"
    (empty / "docs").mkdir(parents=True)
    (empty / "docs" / "note.txt").write_bytes(b"not a task\n")
    args = _args(tasks_repo["cache"], context=[f"tasks={empty}"])
    with pytest.raises(CliUsageError, match="none of the pin"):
        _per_unit_inputs(args, Context(args), profile, None, _tree([]), None, CommandResult(dry_run=False))


def test_a_context_download_pin_without_sha256_is_refused_nf28(tmp_path):
    data = b"PK\x05\x06" + bytes(18)
    (tmp_path / "supp.zip").write_bytes(data)
    pin = {"role": "supp", "kind": "zenodo", "doi": "10.5281/zenodo.23168099", "file": "supp.zip",
           "md5": hashlib.md5(data, usedforsecurity=False).hexdigest(), "bytes": len(data)}
    for given in ([f"supp={tmp_path / 'supp.zip'}"], []):  # a local copy and the fetch cache alike
        args = _args(tmp_path / "cache", context=given)
        with pytest.raises(AgentProvError) as err:
            _per_unit_inputs(args, Context(args), _profile([pin], ["supp:x/**"]), None, _tree([]), None,
                             CommandResult(dry_run=False))
        assert err.value.exit_code == 4 or err.value.code == "raw.fetch.unverifiable"


def test_a_url_context_pin_from_the_cache_takes_its_retrieval_time_from_the_acquisition_record_pr11_4(tmp_path, monkeypatch):
    """PR-11 #4 (D-455 x D-530): a url context pin resolved from the fetch cache passes the cache's ``retrieved_at`` to
    its archive tree, as a primary url input does. Before, a pin that records no ``retrieved_at`` itself was refused."""
    from agentprov.cli import import_

    data = b"PK\x05\x06" + bytes(18)
    (tmp_path / "supp.zip").write_bytes(data)
    pin = {"role": "supp", "kind": "url", "url": "https://example.invalid/files/1", "file": "supp.zip",
           "sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}

    class _Fetcher:  # the verified cache holds the file, with its acquisition record
        def plan(self, recipe):
            return SimpleNamespace(cached=True, host="example.invalid")

        def fetch(self, recipe):
            return SimpleNamespace(path=tmp_path / "supp.zip", sha256=pin["sha256"], bytes=len(data), problems=(),
                                   network_used=False, retrieved_at="2026-10-11T09:46:41Z")

    monkeypatch.setattr(import_, "_fetcher", lambda args, ctx: _Fetcher())
    args = _args(tmp_path / "cache")
    contexts, _objects, _local = _per_unit_inputs(args, Context(args), _profile([pin], ["supp:x/**"]), None, _tree([]),
                                                  None, CommandResult(dry_run=False))
    (ctx,) = contexts
    assert isinstance(ctx.tree, ArchiveTree) and ctx.tree.retrieved_at == "2026-10-11T09:46:41Z"


def test_an_lfs_object_pin_without_sha256_is_refused_nf28(tmp_path):
    pin = {"role": "lfs_object", "kind": "hf", "dataset": DATASET, "revision": REVISION, "file": "main/a.json",
           "md5": "0" * 32, "bytes": 3}
    args = _args(tmp_path / "cache")
    with pytest.raises(AgentProvError) as err:
        _per_unit_inputs(args, Context(args), _profile([pin], []), None, _tree(["main/a.json"]), None,
                         CommandResult(dry_run=False))
    assert err.value.exit_code == 4
