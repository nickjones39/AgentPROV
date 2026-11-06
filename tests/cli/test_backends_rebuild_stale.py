"""``agentprov backends rebuild-stale`` (MN N.2.10; D-1130) with fake environments and a fake builder.

No network, no ``uv``, no worker: the environments are synthetic trees whose T0 identity (RECORD-verified files, guarded
sources, the PEP 610 pin, Inspect task files and dataset) is computed by the real ``envs.compute_identity``, so stale
detection runs the same checks as ``run --catalogue``. The builder and the checker are fakes. The real build is
``tests/integration/test_run_live_agentdojo.py``'s, and the release log records a real rebuild-stale run.
"""

from __future__ import annotations

import base64
import hashlib
import json
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from agentprov.cli.live import envs, stale
from agentprov.progress import ProgressEvent

REPO = Path(__file__).resolve().parents[2]
ALL = ("agentdojo", "autodojo", "agentdyn", "inspect-agentharm")


# ------------------------------------------------------------------------------------------------ fakes
def _record_line(rel: str, data: bytes) -> str:
    digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
    return f"{rel},sha256={digest},{len(data)}"


def _dist(sp: Path, name: str, version: str, files: dict[str, bytes], direct_url: dict[str, Any] | None = None) -> None:
    info = sp / f"{name.replace('-', '_')}-{version}.dist-info"
    info.mkdir(parents=True)
    files = {**files, f"{info.name}/METADATA": f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n\n".encode()}
    if direct_url is not None:
        files[f"{info.name}/direct_url.json"] = json.dumps(direct_url).encode()
    lines = []
    for rel, data in sorted(files.items()):
        (sp / rel).parent.mkdir(parents=True, exist_ok=True)
        (sp / rel).write_bytes(data)
        lines.append(_record_line(rel, data))
    lines.append(f"{info.name}/RECORD,,")
    (info / "RECORD").write_text("\n".join(lines) + "\n")


def checkout(tmp_path: Path) -> Path:
    """A checkout with the four backend projects' pyproject.toml and uv.lock (copies; the trusted repository files)."""
    root = tmp_path / "checkout"
    (root / "backends").mkdir(parents=True)
    (root / "pyproject.toml").write_text('[project]\nname = "agentprov"\nversion = "0.0.0"\n')
    for backend in ALL:
        rel = envs.backend_kind(backend).project
        dest = root / "backends" / rel
        dest.mkdir(parents=True)
        for name in ("pyproject.toml", "uv.lock"):
            shutil.copyfile(REPO / "backends" / rel / name, dest / name)
    return root


def make_env(home: Path, backend: str, root: Path, *, dataset_files: bool = True) -> Path:
    """A synthetic environment with a complete marker that passes the T0 checks for the checkout at ``root``."""
    project = envs.backend_project(backend, root)
    kind = envs.backend_kind(backend)
    env = envs.env_dir(project, home)
    sp = env / "lib" / "python3.12" / "site-packages"
    sp.mkdir(parents=True)
    pinned = envs.pinned_source(project)
    for name in kind.watched:
        files: dict[str, bytes] = {f"{name.replace('-', '_')}/__init__.py": b""}
        if name == kind.primary:
            files.update({m.replace(".", "/") + ".py": f"# {m}\n".encode() for m in kind.guarded_modules})
            files.update({f"{d}/task.py": b"# task\n" for d in kind.task_dirs})
        direct = None
        if name == kind.primary and pinned is not None:
            direct = {"url": pinned["repo"], "vcs_info": {"vcs": "git", "commit_id": pinned["commit"]}}
            if "subdirectory" in pinned:
                direct["subdirectory"] = pinned["subdirectory"]
        _dist(sp, name, "0.1.35" if name == "agentdojo" else "1.0", files, direct)
    identity = envs.compute_identity(env, project)
    marker: dict[str, Any] = {"format": envs.MARKER_FORMAT, "backend": backend, "status": "complete",
                              "env_name": project.env_name, "commit": project.commit, "lock_sha256": project.lock_sha256,
                              "nltk_sha256": None, "t0_identity": identity.to_json(), "python": "3.12.14"}
    recipe = envs.dataset_recipe(project)
    if recipe is not None:
        marker["dataset"] = {"kind": "hf", "repo": recipe["repo"], "revision": recipe["revision"],
                             "benchmark": recipe["benchmark"],
                             "files": dict(sorted((f["path"], f["sha256"]) for f in recipe["files"]))}
        if dataset_files:
            write_dataset(envs.dataset_dir(env, recipe), recipe)
    (env / envs.ENV_MARKER).write_text(json.dumps(marker))
    return env


def fake_dataset(project: envs.BackendProject) -> envs.BackendProject:
    """The project with a pinned dataset of synthetic files (the real pins name AgentHarm's bytes)."""
    from dataclasses import replace

    files = [{"path": f"benchmark/f{i}.json", "sha256": hashlib.sha256(_data(i)).hexdigest(), "bytes": len(_data(i))}
             for i in range(2)]
    return replace(project, dataset={**dict(project.dataset or {}), "files": files})


def _data(i: int) -> bytes:
    return f'{{"synthetic": {i}}}\n'.encode()


def write_dataset(folder: Path, recipe: dict[str, Any]) -> None:
    for f in recipe["files"]:
        target = folder / f["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(_data(int(f["path"].split("/f")[1].split(".")[0])))


@pytest.fixture
def synthetic_dataset(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every Inspect project carries the synthetic dataset pins (so a test can write the matching bytes)."""
    real = envs.backend_project

    def patched(backend: str, root: Path) -> envs.BackendProject:
        project = real(backend, root)
        return fake_dataset(project) if project.dataset is not None else project

    monkeypatch.setattr(envs, "backend_project", patched)


def tree_digest(path: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(path.rglob("*")):
        h.update(p.relative_to(path).as_posix().encode() + b"\0")
        if p.is_file():
            h.update(hashlib.sha256(p.read_bytes()).digest())
    return h.hexdigest()


class Events:
    def __init__(self) -> None:
        self.events: list[ProgressEvent] = []

    def emit(self, event: ProgressEvent) -> None:
        self.events.append(event)

    def fold(self) -> Any:
        from agentprov.jobs.follow import ProgressState

        state = ProgressState()
        for ev in self.events:
            state.apply({"event": ev.kind, "total": ev.total, "unit": ev.unit, "status": ev.status,
                         "codes": list(ev.codes)})
        return state


def fake_builder(home: Path, root: Path, *, fail: tuple[str, ...] = (), calls: list[str] | None = None) -> Callable:
    def build(backend: str, progress: Any) -> tuple[list[str], list[str]]:
        if calls is not None:
            calls.append(f"build {backend}")
        progress.emit(ProgressEvent("stage", stage="uv_sync", fields={"phase": "begin"}))
        progress.emit(ProgressEvent("unit_start", unit="uv_sync"))
        if backend in fail:
            from agentprov.errors import BackendUnavailable

            raise BackendUnavailable(f"uv sync --locked failed for backends/{backend} (offline: the uv cache lacks a "
                                     "locked package; rerun with --allow-network)")
        project = envs.backend_project(backend, root)
        env = envs.env_dir(project, home)
        if env.exists():
            shutil.rmtree(env)
        make_env(home, backend, root)
        progress.emit(ProgressEvent("unit_done", unit="uv_sync", status="ok", duration_s=0.1))
        return [f"{project.env_name} built"], []

    return build


def fake_checker(*, fail: tuple[str, ...] = (), calls: list[str] | None = None) -> Callable:
    def check(backend: str, progress: Any) -> tuple[list[str], list[str]]:
        if calls is not None:
            calls.append(f"check {backend}")
        if backend in fail:
            from agentprov.errors import IdentityMismatch

            raise IdentityMismatch("IdentityMismatch: hello_ok lock_sha256 differs from the T0 digests")
        return [f"{backend} verified"], []

    return check


def run(root: Path, home: Path, backends: tuple[str, ...] = ALL, *, dry_run: bool = False, uv_found: bool = True,
        allow_network: bool = False, builder: Callable | None = None, checker: Callable | None = None,
        progress: Any = None, environ: dict[str, str] | None = None) -> list[stale.Outcome]:
    return stale.rebuild_stale(
        backends, root=root, home=home, environ=environ or {"AGENTPROV_HOME": str(home)},
        allow_network=allow_network, dry_run=dry_run, builder=builder or fake_builder(home, root),
        checker=checker or fake_checker(), uv_found=uv_found, progress=progress or Events())


# ------------------------------------------------------------------------------------------------ the backends
def test_the_backends_come_from_the_registry_in_its_order():
    from agentprov.adapters.registry import BACKENDS

    assert stale.live_backend_ids() == tuple(BACKENDS)
    assert set(stale.live_backend_ids()) == set(ALL) and set(ALL) <= set(envs.BACKEND_KINDS)


# ------------------------------------------------------------------------------------------------ detection
def test_a_fresh_environment_is_current(tmp_path, synthetic_dataset):
    root, home = checkout(tmp_path), tmp_path / "home"
    for backend in ALL:
        make_env(home, backend, root)
        state = stale.detect(backend, root, home)
        assert (state.status, state.code) == ("current", "current"), (backend, state.reason)
        assert state.files_verified > 0


def test_a_missing_environment_is_stale_not_built(tmp_path):
    root, home = checkout(tmp_path), tmp_path / "home"
    state = stale.detect("agentdojo", root, home)
    assert (state.status, state.code) == ("stale", "not_built")
    assert state.env_name == envs.backend_project("agentdojo", root).env_name


def test_a_relock_names_a_new_environment_and_the_old_one_is_only_listed(tmp_path):
    root, home = checkout(tmp_path), tmp_path / "home"
    old = make_env(home, "agentdojo", root)
    with (root / "backends" / "agentdojo" / "uv.lock").open("a") as lock:
        lock.write("\n# a deliberate re-lock\n")
    state = stale.detect("agentdojo", root, home)
    assert (state.status, state.code) == ("stale", "not_built")
    assert state.others == (old.name,) and old.name in state.reason


def test_same_name_with_another_lock_is_an_identity_mismatch(tmp_path):
    root, home = checkout(tmp_path), tmp_path / "home"
    make_env(home, "autodojo", root)  # git-pinned: the name follows the fork commit, not the lock
    with (root / "backends" / "autodojo" / "uv.lock").open("a") as lock:
        lock.write("\n# a version bump of the shared packages\n")
    state = stale.detect("autodojo", root, home)
    assert (state.status, state.code) == ("stale", "identity_mismatch")
    assert "lock_sha256" in state.reason


def test_a_modified_guarded_file_or_an_unfinished_build_is_stale(tmp_path):
    root, home = checkout(tmp_path), tmp_path / "home"
    env = make_env(home, "agentdojo", root)
    target = next(env.rglob("agentdojo/benchmark.py"))
    target.write_text("# changed\n")
    assert stale.detect("agentdojo", root, home).code == "identity_mismatch"
    marker = json.loads((env / envs.ENV_MARKER).read_text())
    (env / envs.ENV_MARKER).write_text(json.dumps({**marker, "status": "building"}))
    assert stale.detect("agentdojo", root, home).code == "incomplete"
    (env / envs.ENV_MARKER).write_text("{not json")
    assert stale.detect("agentdojo", root, home).code == "identity_mismatch"


def test_an_environment_without_its_dataset_is_stale(tmp_path, synthetic_dataset):
    root, home = checkout(tmp_path), tmp_path / "home"
    make_env(home, "inspect-agentharm", root, dataset_files=False)
    state = stale.detect("inspect-agentharm", root, home)
    assert (state.status, state.code) == ("stale", "identity_mismatch") and "dataset" in state.reason


def test_a_backend_this_host_cannot_build_is_unsupported_and_never_built(tmp_path, monkeypatch):
    from agentprov import platforms

    root, home = checkout(tmp_path), tmp_path / "home"
    real = platforms.unavailable
    monkeypatch.setattr(platforms, "unavailable", lambda feature, *a, subject=None, **k:
                        real(feature, "Windows", "ARM64", subject=subject))
    calls: list[str] = []
    outcomes = run(root, home, ("agentdojo",), builder=fake_builder(home, root, calls=calls))
    assert [o.status for o in outcomes] == ["unsupported"] and outcomes[0].ok and calls == []
    assert "not available" in outcomes[0].state.reason


def test_detection_writes_nothing(tmp_path, synthetic_dataset):
    root, home = checkout(tmp_path), tmp_path / "home"
    make_env(home, "agentdojo", root)
    before = tree_digest(home)
    for backend in ALL:
        stale.detect(backend, root, home)
    assert tree_digest(home) == before


# ------------------------------------------------------------------------------------------------ rebuild
def test_only_the_stale_ones_are_built_then_checked_and_other_environments_stay(tmp_path, synthetic_dataset):
    root, home = checkout(tmp_path), tmp_path / "home"
    for backend in ("autodojo", "agentdyn"):
        make_env(home, backend, root)
    old = home / "envs" / "agentdojo-0badc0de"  # an earlier agentdojo environment (another lock)
    old.mkdir(parents=True)
    (old / "anything").write_text("left alone\n")
    before = tree_digest(old)
    cache = home / "cache"
    recipe = envs.dataset_recipe(envs.backend_project("inspect-agentharm", root))
    assert recipe is not None
    write_dataset(cache / "hf" / recipe["repo"] / recipe["revision"], recipe)
    calls: list[str] = []
    events = Events()
    outcomes = run(root, home, builder=fake_builder(home, root, calls=calls), checker=fake_checker(calls=calls),
                   progress=events)
    assert [(o.state.backend, o.status) for o in outcomes] == [
        ("agentdojo", "rebuilt"), ("autodojo", "current"), ("agentdyn", "current"), ("inspect-agentharm", "rebuilt")]
    assert calls == ["build agentdojo", "check agentdojo", "build inspect-agentharm", "check inspect-agentharm"]
    assert tree_digest(old) == before
    assert all(o.ok for o in outcomes)
    state = events.fold()
    assert (state.total, state.done) == (4, 4)  # one unit per backend: the builds' own units are steps
    assert dict(state.statuses) == {"rebuilt": 2, "current": 2}
    assert [e.stage for e in events.events if e.kind == "step"] == ["uv_sync", "uv_sync"]
    assert {e.stage for e in events.events if e.kind == "stage"} == {"agentdojo/uv_sync", "inspect-agentharm/uv_sync"}


def test_a_failure_is_recorded_with_its_command_and_the_next_backend_follows(tmp_path, synthetic_dataset):
    root, home = checkout(tmp_path), tmp_path / "home"
    cache = home / "cache"
    recipe = envs.dataset_recipe(envs.backend_project("inspect-agentharm", root))
    assert recipe is not None
    write_dataset(cache / "hf" / recipe["repo"] / recipe["revision"], recipe)
    events = Events()
    outcomes = run(root, home, builder=fake_builder(home, root, fail=("agentdojo",)),
                   checker=fake_checker(fail=("agentdyn",)), progress=events)
    by = {o.state.backend: o for o in outcomes}
    assert by["agentdojo"].status == "failed" and by["agentdojo"].stage == "build"
    assert by["agentdojo"].code == "adapter.backend_unavailable"
    assert by["agentdojo"].commands == ["agentprov backends build agentdojo --allow-network",
                                        "agentprov backends build agentdojo --offline-check"]
    assert by["autodojo"].status == "rebuilt" and by["inspect-agentharm"].status == "rebuilt"
    assert by["agentdyn"].status == "failed" and by["agentdyn"].stage == "offline_check"
    assert by["agentdyn"].code == "adapter.identity_mismatch"
    assert by["agentdyn"].commands[0] == "agentprov backends build agentdyn --offline-check"
    assert events.fold().done == 4 and events.fold().codes["adapter.backend_unavailable"] == 1


def test_an_unexpected_error_in_one_backend_does_not_stop_the_others(tmp_path):
    root, home = checkout(tmp_path), tmp_path / "home"

    def build(backend: str, progress: Any) -> tuple[list[str], list[str]]:
        if backend == "agentdojo":
            raise KeyError("surprise")
        return fake_builder(home, root)(backend, progress)

    outcomes = run(root, home, ("agentdojo", "agentdyn"), builder=build)
    assert [o.status for o in outcomes] == ["failed", "rebuilt"]
    assert outcomes[0].code == "backend.build_error" and "KeyError" in (outcomes[0].reason or "")


def test_a_dry_run_lists_what_and_why_and_builds_nothing(tmp_path, synthetic_dataset):
    root, home = checkout(tmp_path), tmp_path / "home"
    make_env(home, "agentdyn", root)
    before = tree_digest(home)
    calls: list[str] = []
    outcomes = run(root, home, ("agentdojo", "agentdyn"), dry_run=True, builder=fake_builder(home, root, calls=calls),
                   checker=fake_checker(calls=calls))
    assert [(o.status, o.state.code) for o in outcomes] == [("stale", "not_built"), ("current", "current")]
    assert outcomes[0].commands == ["agentprov backends build agentdojo",
                                    "agentprov backends build agentdojo --offline-check"]
    assert calls == [] and tree_digest(home) == before


# ------------------------------------------------------------------------------------------------ missing inputs
def test_a_missing_dataset_blocks_that_build_with_the_consent_step(tmp_path, synthetic_dataset):
    root, home = checkout(tmp_path), tmp_path / "home"
    calls: list[str] = []
    outcomes = run(root, home, ("inspect-agentharm", "agentdojo"), builder=fake_builder(home, root, calls=calls))
    blocked = outcomes[0]
    assert blocked.status == "blocked" and blocked.code == "backend.input_missing" and not blocked.ok
    assert blocked.missing[0].kind == "dataset" and blocked.missing[0].blocking
    step = blocked.commands[0]
    assert "huggingface.co/datasets/ai-safety-institute/AgentHarm" in step and "consent" in step
    assert "rebuild-stale" in step
    assert calls == ["build agentdojo"]  # the next backend follows


def test_the_missing_dataset_names_an_earlier_environments_verified_copy(tmp_path, synthetic_dataset):
    root, home = checkout(tmp_path), tmp_path / "home"
    recipe = envs.dataset_recipe(envs.backend_project("inspect-agentharm", root))
    assert recipe is not None
    earlier = home / "envs" / "inspect-agentharm-0123abcd"
    write_dataset(envs.dataset_dir(earlier, recipe), recipe)
    found = stale.missing_inputs("inspect-agentharm", root, home, {"AGENTPROV_HOME": str(home)}, allow_network=True,
                                 uv_found=True)
    assert len(found) == 1 and "inspect-agentharm-0123abcd holds a verified copy" in found[0].step
    (envs.dataset_dir(earlier, recipe) / recipe["files"][0]["path"]).write_bytes(b"other bytes\n")
    found = stale.missing_inputs("inspect-agentharm", root, home, {"AGENTPROV_HOME": str(home)}, allow_network=True,
                                 uv_found=True)
    assert "verified copy" not in found[0].step


def test_a_cached_dataset_file_with_other_bytes_counts_as_missing(tmp_path, synthetic_dataset):
    root, home = checkout(tmp_path), tmp_path / "home"
    recipe = envs.dataset_recipe(envs.backend_project("inspect-agentharm", root))
    assert recipe is not None
    folder = home / "cache" / "hf" / recipe["repo"] / recipe["revision"]
    write_dataset(folder, recipe)
    assert stale.missing_inputs("inspect-agentharm", root, home, {"AGENTPROV_HOME": str(home)}, allow_network=False,
                                uv_found=True) == []
    (folder / recipe["files"][1]["path"]).write_bytes(_data(0))  # another file's bytes
    found = stale.missing_inputs("inspect-agentharm", root, home, {"AGENTPROV_HOME": str(home)}, allow_network=False,
                                 uv_found=True)
    assert [m.kind for m in found] == ["dataset"] and "lacks 1 of 2 files" in found[0].what


def test_uncached_nltk_data_is_a_notice_offline_and_nothing_with_the_network(tmp_path):
    root, home = checkout(tmp_path), tmp_path / "home"
    offline = stale.missing_inputs("autodojo", root, home, {"AGENTPROV_HOME": str(home)}, allow_network=False,
                                   uv_found=True)
    project = envs.backend_project("autodojo", root)
    if envs.nltk_recipe(project) is None:  # the recipe is not pinned in this checkout: built without it either way
        assert [(m.kind, m.blocking) for m in offline] == [("nltk", False)]
        return
    assert [(m.kind, m.blocking) for m in offline] == [("nltk", False)] and "--allow-network" in offline[0].step
    assert stale.missing_inputs("autodojo", root, home, {"AGENTPROV_HOME": str(home)}, allow_network=True,
                                uv_found=True) == []
    outcomes = run(root, home, ("autodojo",))
    assert outcomes[0].status == "rebuilt" and any("NLTK punkt_tab" in n for n in outcomes[0].notices)


def test_no_uv_blocks_every_stale_build_and_never_a_current_one(tmp_path):
    root, home = checkout(tmp_path), tmp_path / "home"
    make_env(home, "agentdyn", root)
    outcomes = run(root, home, ("agentdojo", "agentdyn"), uv_found=False)
    assert [o.status for o in outcomes] == ["blocked", "current"]
    assert outcomes[0].missing[0].kind == "uv" and "docs.astral.sh/uv" in outcomes[0].commands[0]


# ------------------------------------------------------------------------------------------------ the CLI
@pytest.fixture
def in_repo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(REPO)


def test_outside_a_checkout_it_refuses_with_repository_missing(cli, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = cli("backends", "rebuild-stale", "--dry-run")
    assert result.code == 3 and "backend.repository_missing" in result.err


def test_an_unknown_backend_is_a_usage_error(cli, in_repo):
    result = cli("backends", "rebuild-stale", "--backend", "nonesuch", "--dry-run")
    assert result.code == 2 and "not a registered backend" in result.err


def _patch_cli(monkeypatch: pytest.MonkeyPatch, home: Path, *, fail: tuple[str, ...] = ()) -> list[str]:
    from agentprov.cli import backends

    calls: list[str] = []
    builder = fake_builder(home, REPO, fail=fail, calls=calls)
    checker = fake_checker(calls=calls)
    monkeypatch.setattr(backends, "build_backend", lambda b, p, **kw: builder(b, p))
    monkeypatch.setattr(backends, "check_backend", lambda b, p, **kw: checker(b, p))
    return calls


def test_the_cli_rebuilds_reports_json_and_exits_by_the_result(cli, in_repo, tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("AGENTPROV_HOME", str(home))
    calls = _patch_cli(monkeypatch, home, fail=("agentdyn",))
    result = cli("backends", "rebuild-stale", "--backend", "agentdojo,agentdyn", "--format", "json")
    assert result.code == 3, result.err
    doc = json.loads(result.out)
    assert doc["format"] == "agentprov-backends-rebuild/0.1" and doc["ok"] is False
    assert [(b["backend"], b["outcome"]) for b in doc["backends"]] == [("agentdojo", "rebuilt"), ("agentdyn", "failed")]
    assert doc["counts"]["rebuilt"] == 1 and doc["counts"]["failed"] == 1
    assert calls == ["build agentdojo", "check agentdojo", "build agentdyn"]
    assert "agentprov backends build agentdyn --allow-network" in result.err
    again = cli("backends", "rebuild-stale", "--backend", "agentdojo", "--json")
    assert again.code == 0 and json.loads(again.out)["counters"]["current"] == 1


def test_the_summary_lists_each_failure_and_validates(cli, in_repo, tmp_path, monkeypatch, check_summary):
    home = tmp_path / "home"
    monkeypatch.setenv("AGENTPROV_HOME", str(home))
    _patch_cli(monkeypatch, home, fail=("agentdojo",))
    result = cli("backends", "rebuild-stale", "--backend", "agentdojo", "--json")
    assert result.code == 3
    summary = result.json()
    check_summary(summary)
    assert summary["failures"][0]["code"] == "adapter.backend_unavailable"
    assert summary["failures"][0]["subject"]["path"].startswith("envs/agentdojo-")


def test_a_cli_dry_run_writes_nothing_and_exits_0(cli, in_repo, tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("AGENTPROV_HOME", str(home))
    calls = _patch_cli(monkeypatch, home)
    result = cli("backends", "rebuild-stale", "--dry-run")
    assert result.code == 0, result.err
    assert calls == [] and not (home / "envs").exists()
    assert "would run: agentprov backends build agentdojo" in result.err
    assert "inspect-agentharm" in result.err and "backend.input_missing" in result.err  # no dataset in this home


def test_the_progress_file_counts_backends(cli, in_repo, tmp_path, monkeypatch):
    from agentprov.jobs.follow import ProgressState

    home = tmp_path / "home"
    monkeypatch.setenv("AGENTPROV_HOME", str(home))
    _patch_cli(monkeypatch, home)
    progress = tmp_path / "progress.jsonl"
    result = cli("--progress-file", str(progress), "backends", "rebuild-stale", "--backend", "agentdojo,autodojo")
    assert result.code == 0, result.err
    state = ProgressState()
    for line in progress.read_text().splitlines():
        state.apply(json.loads(line))
    assert (state.total, state.done, state.ended, state.exit_code) == (2, 2, True, 0)
    assert dict(state.statuses) == {"rebuilt": 2}


# ------------------------------------------------------------------------------------------------ never under a live job
def _jobs(monkeypatch: pytest.MonkeyPatch, *argvs: tuple[str, list[str]]) -> None:
    from agentprov.jobs import record

    jobs = [record.Job(f"job{i}", Path("/nonexistent"), {"subcommand_argv": argv, "argv": ["agentprov", *argv],
                                                         "command": argv[0]}, state)
            for i, (state, argv) in enumerate(argvs)]
    monkeypatch.setattr(record, "list_jobs", lambda home: jobs)


def test_a_backend_a_registered_run_uses_is_skipped_and_the_others_follow(tmp_path):
    from agentprov.io.locks import backend_use

    root, home = checkout(tmp_path), tmp_path / "home"
    name = envs.backend_project("agentdojo", root).env_name
    calls: list[str] = []
    with backend_use(home, name, command="run"):
        outcomes = run(root, home, ("agentdojo", "agentdyn"), builder=fake_builder(home, root, calls=calls))
    assert [o.status for o in outcomes] == ["busy", "rebuilt"] and not outcomes[0].ok
    assert outcomes[0].code == "io.resource_busy" and "uses " + name in (outcomes[0].reason or "")
    assert calls == ["build agentdyn"]


def test_a_running_run_job_of_the_backends_source_makes_it_busy(tmp_path, monkeypatch):
    root, home = checkout(tmp_path), tmp_path / "home"
    _jobs(monkeypatch, ("running", ["run", "agentdojo", "--corpus", "/c", "--plan", "/p.toml"]),
          ("ended", ["run", "agentdyn", "--corpus", "/c"]),
          ("running", ["backends", "rebuild-stale", "--backend", "agentdojo,agentdyn"]))  # this job itself
    outcomes = run(root, home, ("agentdojo", "agentdyn"))
    assert [o.status for o in outcomes] == ["busy", "rebuilt"]
    assert "the running job job0 (run agentdojo)" in (outcomes[0].reason or "")


def test_a_running_job_naming_a_path_in_the_environment_or_the_project_makes_it_busy(tmp_path, monkeypatch):
    root, home = checkout(tmp_path), tmp_path / "home"
    env = envs.env_dir(envs.backend_project("autodojo", root), home)
    project = root / "backends" / "agentdyn"
    _jobs(monkeypatch, ("running", ["inspect", "--python", f"{env}/bin/python"]),
          ("running", ["migrate", "gate-a", "--config", str(project / "x.toml")]))
    outcomes = run(root, home, ("autodojo", "agentdyn", "agentdojo"))
    assert [o.status for o in outcomes] == ["busy", "busy", "rebuilt"]
    assert outcomes[0].commands == ["wait for it to end, then run 'agentprov backends rebuild-stale' again"]


def test_a_current_backend_is_never_reported_busy(tmp_path, monkeypatch):
    root, home = checkout(tmp_path), tmp_path / "home"
    make_env(home, "agentdojo", root)
    _jobs(monkeypatch, ("running", ["run", "agentdojo", "--corpus", "/c"]))
    assert [o.status for o in run(root, home, ("agentdojo",))] == ["current"]


# ------------------------------------------------------------------------------------------------ D-1130 review
def test_a_stale_environment_with_defence_assets_is_never_rebuilt_without_them(tmp_path, monkeypatch):
    """B2: the same <backend>-<commit8> directory rebuilt by an exact uv sync without the defences group would lose
    its defence packages; it is blocked with the command that rebuilds it with them, and left byte for byte."""
    root, home = checkout(tmp_path), tmp_path / "home"
    env = make_env(home, "agentdojo", root)
    marker = json.loads((env / envs.ENV_MARKER).read_text())
    marker["defence_assets"] = {"no-such-defence": {"sha256": "0" * 64}}
    (env / envs.ENV_MARKER).write_text(json.dumps(marker))
    from agentprov.cli import backends
    from agentprov.errors import BackendUnavailable

    def moved(env_: Path, marker_: Any, project: Any) -> None:  # the defence's pin moved: the check fails, so stale
        if marker_.get("defence_assets"):
            raise BackendUnavailable("defence no-such-defence: its pinned bytes changed")

    monkeypatch.setattr(backends, "check_defence_assets", moved)
    before = tree_digest(env)
    calls: list[str] = []
    for dry_run in (True, False):
        outcomes = run(root, home, ("agentdojo", "agentdyn"), builder=fake_builder(home, root, calls=calls),
                       allow_network=True, dry_run=dry_run)
        assert [o.status for o in outcomes] == ["blocked", "stale" if dry_run else "rebuilt"]
        assert outcomes[0].code == stale.DEFENCE_ASSETS and "no-such-defence" in (outcomes[0].reason or "")
        assert outcomes[0].commands[0] == ("agentprov backends build agentdojo --defence-assets no-such-defence "
                                           "--allow-network")
    assert calls == ["build agentdyn"] and tree_digest(env) == before
    from types import SimpleNamespace

    from agentprov.cli.common import CommandResult

    report = backends._rebuild_report(outcomes, SimpleNamespace(dry_run=False, format="text", allow_network=True),
                                      CommandResult())
    line = next(text for kind, text in report.messages if kind == "output" and text.startswith("agentdojo:"))
    assert "holds defence assets" in line and "missing input" not in line  # nothing is missing


def test_a_gui_started_run_with_its_source_after_the_options_makes_the_backend_busy(tmp_path, monkeypatch):
    """The GUI's build_spec puts the positionals last: ["run", "--corpus", "/c", …, "agentdojo"]."""
    root, home = checkout(tmp_path), tmp_path / "home"
    _jobs(monkeypatch, ("running", ["run", "--corpus", "/c", "--plan", "/p.toml", "--allow-network", "agentdojo"]))
    outcomes = run(root, home, ("agentdojo", "agentdyn"))
    assert [o.status for o in outcomes] == ["busy", "rebuilt"]
    assert "(run agentdojo)" in (outcomes[0].reason or "")


def test_a_batch_driver_with_a_live_step_still_to_run_makes_the_backend_busy(tmp_path, monkeypatch):
    from agentprov.jobs.batch import Batch, BatchStep
    from agentprov.jobs.manager import JobRequest

    root, home = checkout(tmp_path), tmp_path / "home"
    steps = [BatchStep(JobRequest(argv=("run", "--corpus", "/c1", "agentdojo"), label="one"), state="done"),
             BatchStep(JobRequest(argv=("run", "--corpus", "/c2", "agentdojo"), label="two"))]
    batch = Batch.new(home, "campaign", steps)
    done = Batch.new(home, "done", [BatchStep(JobRequest(argv=("run", "agentdyn"), label="x"), state="done")])
    _jobs(monkeypatch, ("running", ["batch", "run", batch.batch_id]), ("running", ["batch", "run", done.batch_id]),
          ("running", ["batch", "run", "../../etc"]))
    outcomes = run(root, home, ("agentdojo", "agentdyn"))
    assert outcomes[0].status == "busy" and f"batch {batch.batch_id}" in (outcomes[0].reason or "")
    assert outcomes[1].status == "busy" and "../../etc" in (outcomes[1].reason or "")  # unreadable: never a guess
    assert f"batch {done.batch_id}" not in (outcomes[1].reason or "")


def test_a_run_registered_between_the_check_and_the_build_is_busy_not_failed(tmp_path):
    from agentprov.io.locks import ResourceBusyError

    root, home = checkout(tmp_path), tmp_path / "home"

    def builder(backend: str, progress: Any) -> tuple[list[str], list[str]]:
        raise ResourceBusyError("the environment is in use by a run (pid 4242)")

    [outcome] = run(root, home, ("agentdojo",), builder=builder)
    assert (outcome.status, outcome.stage, outcome.code) == ("busy", "busy", "io.resource_busy")
    assert outcome.commands == ["wait for it to end, then run 'agentprov backends rebuild-stale' again"]


def test_a_dry_run_leaves_dead_registrations_where_they_are(tmp_path):
    """A dry run writes nothing: a dead run's registration is pruned only by a real run (as every lock check does)."""
    import os
    import subprocess
    import sys

    from agentprov.io.locks import backend_use

    root, home = checkout(tmp_path), tmp_path / "home"
    name = envs.backend_project("agentdojo", root).env_name
    code = ("import os, sys; from pathlib import Path; from agentprov.io.locks import backend_use; "
            f"backend_use(Path({str(home)!r}), {name!r}, command='run').__enter__(); os._exit(0)")
    subprocess.run([sys.executable, "-c", code], check=True, timeout=60, env={**os.environ})
    folder = backend_use(home, name).directory
    before = sorted(p.name for p in folder.iterdir())
    assert len(before) == 1
    run(root, home, ("agentdojo",), dry_run=True)
    assert sorted(p.name for p in folder.iterdir()) == before
    run(root, home, ("agentdojo",), builder=fake_builder(home, root))
    assert sorted(p.name for p in folder.iterdir()) == []


def test_an_empty_backend_selection_is_a_usage_error(cli, in_repo, tmp_path, monkeypatch):
    _patch_cli(monkeypatch, tmp_path / "home")
    for value in ("", ","):
        result = cli("backends", "rebuild-stale", "--backend", value)
        assert result.code == 2 and "names no backend" in result.err
